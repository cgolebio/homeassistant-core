"""The tests for the UniFi Network device tracker platform."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from aiounifi.models.message import MessageKey
from freezegun.api import FrozenDateTimeFactory, freeze_time
import pytest

from homeassistant.components.device_tracker import DOMAIN as TRACKER_DOMAIN
from homeassistant.components.unifi.const import (
    CONF_BLOCK_CLIENT,
    CONF_CLIENT_SOURCE,
    CONF_DETECTION_TIME,
    CONF_IGNORE_WIRED_BUG,
    CONF_SSID_FILTER,
    CONF_TRACK_CLIENTS,
    CONF_TRACK_DEVICES,
    CONF_TRACK_WIRED_CLIENTS,
    DEFAULT_DETECTION_TIME,
    DOMAIN as UNIFI_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util

from tests.common import async_fire_time_changed


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "ap_mac": "00:00:00:00:02:01",
                "essid": "ssid",
                "hostname": "client",
                "ip": "10.0.0.1",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            }
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_tracked_wireless_clients(
    hass: HomeAssistant,
    mock_websocket_message,
    config_entry_setup: ConfigEntry,
    client_payload: list[dict[str, Any]],
) -> None:
    """Verify tracking of wireless clients."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1
    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME

    # Updated timestamp marks client as home
    client = client_payload[0]
    client["last_seen"] = dt_util.as_timestamp(dt_util.utcnow())
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_HOME

    # Change time to mark client as away
    new_time = dt_util.utcnow() + timedelta(
        seconds=config_entry_setup.options.get(
            CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME
        )
    )
    with freeze_time(new_time):
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME

    # Same timestamp doesn't explicitly mark client as away
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_HOME


@pytest.mark.parametrize(
    "config_entry_options",
    [{CONF_SSID_FILTER: ["ssid"], CONF_CLIENT_SOURCE: ["00:00:00:00:00:06"]}],
)
@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "ap_mac": "00:00:00:00:02:01",
                "essid": "ssid",
                "hostname": "client_1",
                "ip": "10.0.0.1",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
            {
                "ip": "10.0.0.2",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
                "name": "Client 2",
            },
            {
                "essid": "ssid2",
                "hostname": "client_3",
                "ip": "10.0.0.3",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:03",
            },
            {
                "essid": "ssid",
                "hostname": "client_4",
                "ip": "10.0.0.4",
                "is_wired": True,
                "last_seen": dt_util.as_timestamp(dt_util.utcnow()),
                "mac": "00:00:00:00:00:04",
            },
            {
                "essid": "ssid",
                "hostname": "client_5",
                "ip": "10.0.0.5",
                "is_wired": True,
                "last_seen": None,
                "mac": "00:00:00:00:00:05",
            },
            {
                "hostname": "client_6",
                "ip": "10.0.0.6",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:06",
            },
        ]
    ],
)
@pytest.mark.parametrize("known_wireless_clients", [["00:00:00:00:00:04"]])
@pytest.mark.usefixtures("config_entry_setup")
@pytest.mark.usefixtures("mock_device_registry")
async def test_tracked_clients(
    hass: HomeAssistant, mock_websocket_message, client_payload: list[dict[str, Any]]
) -> None:
    """Test the update_items function with some clients."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 5
    assert hass.states.get("device_tracker.client_1").state == STATE_NOT_HOME
    assert hass.states.get("device_tracker.client_2").state == STATE_NOT_HOME
    assert (
        hass.states.get("device_tracker.client_5").attributes["host_name"] == "client_5"
    )
    assert hass.states.get("device_tracker.client_6").state == STATE_NOT_HOME

    # Client on SSID not in SSID filter
    assert not hass.states.get("device_tracker.client_3")

    # Wireless client with wired bug, if bug active on restart mark device away
    assert hass.states.get("device_tracker.client_4").state == STATE_NOT_HOME

    # A client that has never been seen should be marked away.
    assert hass.states.get("device_tracker.client_5").state == STATE_NOT_HOME

    # State change signalling works

    client_1 = client_payload[0]
    client_1["last_seen"] = dt_util.as_timestamp(dt_util.utcnow())
    mock_websocket_message(message=MessageKey.CLIENT, data=client_1)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client_1").state == STATE_HOME


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "ap_mac": "00:00:00:00:02:01",
                "essid": "ssid",
                "hostname": "client",
                "ip": "10.0.0.1",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            }
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_tracked_wireless_clients_event_source(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_websocket_message,
    config_entry_setup: ConfigEntry,
    client_payload: list[dict[str, Any]],
) -> None:
    """Verify tracking of wireless clients based on event source."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1
    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME

    # State change signalling works with events

    # Connected event
    client = client_payload[0]
    event = {
        "user": client["mac"],
        "ssid": client["essid"],
        "ap": client["ap_mac"],
        "radio": "na",
        "channel": "44",
        "hostname": client["hostname"],
        "key": "EVT_WU_Connected",
        "subsystem": "wlan",
        "site_id": "name",
        "time": 1587753456179,
        "datetime": "2020-04-24T18:37:36Z",
        "msg": (
            f'User{[client["mac"]]} has connected to AP[{client["ap_mac"]}] '
            f'with SSID "{client["essid"]}" on "channel 44(na)"'
        ),
        "_id": "5ea331fa30c49e00f90ddc1a",
    }
    mock_websocket_message(message=MessageKey.EVENT, data=event)
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.client").state == STATE_HOME

    # Disconnected event
    event = {
        "user": client["mac"],
        "ssid": client["essid"],
        "hostname": client["hostname"],
        "ap": client["ap_mac"],
        "duration": 467,
        "bytes": 459039,
        "key": "EVT_WU_Disconnected",
        "subsystem": "wlan",
        "site_id": "name",
        "time": 1587752927000,
        "datetime": "2020-04-24T18:28:47Z",
        "msg": (
            f'User{[client["mac"]]} disconnected from "{client["essid"]}" '
            f'(7m 47s connected, 448.28K bytes, last AP[{client["ap_mac"]}])'
        ),
        "_id": "5ea32ff730c49e00f90dca1a",
    }
    mock_websocket_message(message=MessageKey.EVENT, data=event)
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.client").state == STATE_HOME

    # Change time to mark client as away
    freezer.tick(
        timedelta(
            seconds=(
                config_entry_setup.options.get(
                    CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME
                )
                + 1
            )
        )
    )
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME

    # To limit false positives in client tracker
    # data sources are prioritized when available
    # once real data is received events will be ignored.

    # New data
    client["last_seen"] = dt_util.as_timestamp(dt_util.utcnow())
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.client").state == STATE_HOME

    # Disconnection event will be ignored
    event = {
        "user": client["mac"],
        "ssid": client["essid"],
        "hostname": client["hostname"],
        "ap": client["ap_mac"],
        "duration": 467,
        "bytes": 459039,
        "key": "EVT_WU_Disconnected",
        "subsystem": "wlan",
        "site_id": "name",
        "time": 1587752927000,
        "datetime": "2020-04-24T18:28:47Z",
        "msg": (
            f'User{[client["mac"]]} disconnected from "{client["essid"]}" '
            f'(7m 47s connected, 448.28K bytes, last AP[{client["ap_mac"]}])'
        ),
        "_id": "5ea32ff730c49e00f90dca1a",
    }
    mock_websocket_message(message=MessageKey.EVENT, data=event)
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.client").state == STATE_HOME

    # Change time to mark client as away
    freezer.tick(
        timedelta(
            seconds=(
                config_entry_setup.options.get(
                    CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME
                )
                + 1
            )
        )
    )
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME


@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "fan_level": 0,
                "ip": "10.0.1.1",
                "last_seen": 1562600145,
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device 1",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            },
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "ip": "10.0.1.2",
                "mac": "00:00:00:00:01:02",
                "model": "US16P150",
                "name": "Device 2",
                "next_interval": 20,
                "state": 0,
                "type": "usw",
                "version": "4.0.42.10433",
            },
        ]
    ],
)
@pytest.mark.usefixtures("config_entry_setup")
@pytest.mark.usefixtures("mock_device_registry")
async def test_tracked_devices(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_websocket_message,
    device_payload: list[dict[str, Any]],
) -> None:
    """Test the update_items function with some devices."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.device_1").state == STATE_HOME
    assert hass.states.get("device_tracker.device_2").state == STATE_NOT_HOME

    # State change signalling work
    device_1 = device_payload[0]
    device_1["next_interval"] = 20
    device_2 = device_payload[1]
    device_2["state"] = 1
    device_2["next_interval"] = 50
    mock_websocket_message(message=MessageKey.DEVICE, data=[device_1, device_2])
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.device_1").state == STATE_HOME
    assert hass.states.get("device_tracker.device_2").state == STATE_HOME

    # Change of time can mark device not_home outside of expected reporting interval
    new_time = dt_util.utcnow() + timedelta(seconds=90)
    freezer.move_to(new_time)
    async_fire_time_changed(hass, new_time)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.device_1").state == STATE_NOT_HOME
    assert hass.states.get("device_tracker.device_2").state == STATE_HOME

    # Disabled device is unavailable
    device_1["disabled"] = True
    mock_websocket_message(message=MessageKey.DEVICE, data=device_1)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.device_1").state == STATE_UNAVAILABLE
    assert hass.states.get("device_tracker.device_2").state == STATE_HOME


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "essid": "ssid",
                "hostname": "client_1",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
            {
                "hostname": "client_2",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
            },
        ]
    ],
)
@pytest.mark.usefixtures("config_entry_setup")
@pytest.mark.usefixtures("mock_device_registry")
async def test_remove_clients(
    hass: HomeAssistant, mock_websocket_message, client_payload: list[dict[str, Any]]
) -> None:
    """Test the remove_items function with some clients."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.client_1")
    assert hass.states.get("device_tracker.client_2")

    # Remove client
    mock_websocket_message(message=MessageKey.CLIENT_REMOVED, data=client_payload[0])
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1
    assert not hass.states.get("device_tracker.client_1")
    assert hass.states.get("device_tracker.client_2")


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "essid": "ssid",
                "hostname": "client",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            }
        ]
    ],
)
@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "fan_level": 0,
                "ip": "10.0.1.1",
                "last_seen": 1562600145,
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            }
        ]
    ],
)
@pytest.mark.usefixtures("config_entry_setup")
@pytest.mark.usefixtures("mock_device_registry")
async def test_hub_state_change(hass: HomeAssistant, mock_websocket_state) -> None:
    """Verify entities state reflect on hub connection becoming unavailable."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME
    assert hass.states.get("device_tracker.device").state == STATE_HOME

    # Controller unavailable
    await mock_websocket_state.disconnect()
    assert hass.states.get("device_tracker.client").state == STATE_UNAVAILABLE
    assert hass.states.get("device_tracker.device").state == STATE_UNAVAILABLE

    # Controller available
    await mock_websocket_state.reconnect()
    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME
    assert hass.states.get("device_tracker.device").state == STATE_HOME


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "essid": "ssid",
                "hostname": "wireless_client",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
            {
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
                "name": "Wired Client",
            },
        ]
    ],
)
@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "fan_level": 0,
                "ip": "10.0.1.1",
                "last_seen": 1562600145,
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            }
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_option_track_clients(
    hass: HomeAssistant, config_entry_setup: ConfigEntry
) -> None:
    """Test the tracking of clients can be turned off."""

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 3
    assert hass.states.get("device_tracker.wireless_client")
    assert hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_CLIENTS: False}
    )
    await hass.async_block_till_done()

    assert not hass.states.get("device_tracker.wireless_client")
    assert not hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_CLIENTS: True}
    )
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.wireless_client")
    assert hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "essid": "ssid",
                "hostname": "wireless_client",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
            {
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
                "name": "Wired Client",
            },
        ]
    ],
)
@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "fan_level": 0,
                "ip": "10.0.1.1",
                "last_seen": 1562600145,
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            }
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_option_track_wired_clients(
    hass: HomeAssistant, config_entry_setup: ConfigEntry
) -> None:
    """Test the tracking of wired clients can be turned off."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 3
    assert hass.states.get("device_tracker.wireless_client")
    assert hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_WIRED_CLIENTS: False}
    )
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.wireless_client")
    assert not hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_WIRED_CLIENTS: True}
    )
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.wireless_client")
    assert hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")


@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "hostname": "client",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            }
        ]
    ],
)
@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "last_seen": 1562600145,
                "ip": "10.0.1.1",
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            }
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_option_track_devices(
    hass: HomeAssistant, config_entry_setup: ConfigEntry
) -> None:
    """Test the tracking of devices can be turned off."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.client")
    assert hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_DEVICES: False}
    )
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client")
    assert not hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_DEVICES: True}
    )
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client")
    assert hass.states.get("device_tracker.device")


@pytest.mark.usefixtures("mock_device_registry")
async def test_option_ssid_filter(
    hass: HomeAssistant,
    mock_websocket_message,
    config_entry_factory: Callable[[], ConfigEntry],
    client_payload: list[dict[str, Any]],
) -> None:
    """Test the SSID filter works.

    Client will travel from a supported SSID to an unsupported ssid.
    Client on SSID2 will be removed on change of options.
    """
    client_payload += [
        {
            "essid": "ssid",
            "hostname": "client",
            "is_wired": False,
            "last_seen": dt_util.as_timestamp(dt_util.utcnow()),
            "mac": "00:00:00:00:00:01",
        },
        {
            "essid": "ssid2",
            "hostname": "client_on_ssid2",
            "is_wired": False,
            "last_seen": 1562600145,
            "mac": "00:00:00:00:00:02",
        },
    ]
    config_entry = await config_entry_factory()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.client").state == STATE_HOME
    assert hass.states.get("device_tracker.client_on_ssid2").state == STATE_NOT_HOME

    # Setting SSID filter will remove clients outside of filter
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_SSID_FILTER: ["ssid"]}
    )
    await hass.async_block_till_done()

    # Not affected by SSID filter
    assert hass.states.get("device_tracker.client").state == STATE_HOME

    # Removed due to SSID filter
    assert not hass.states.get("device_tracker.client_on_ssid2")

    # Roams to SSID outside of filter
    client = client_payload[0]
    client["essid"] = "other_ssid"
    mock_websocket_message(message=MessageKey.CLIENT, data=client)

    # Data update while SSID filter is in effect shouldn't create the client
    client_on_ssid2 = client_payload[1]
    client_on_ssid2["last_seen"] = dt_util.as_timestamp(dt_util.utcnow())
    mock_websocket_message(message=MessageKey.CLIENT, data=client_on_ssid2)
    await hass.async_block_till_done()

    new_time = dt_util.utcnow() + timedelta(
        seconds=(
            config_entry.options.get(CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME) + 1
        )
    )
    with freeze_time(new_time):
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

    # SSID filter marks client as away
    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME

    # SSID still outside of filter
    assert not hass.states.get("device_tracker.client_on_ssid2")

    # Remove SSID filter
    hass.config_entries.async_update_entry(config_entry, options={CONF_SSID_FILTER: []})
    await hass.async_block_till_done()

    client["last_seen"] += 1
    client_on_ssid2["last_seen"] += 1
    mock_websocket_message(message=MessageKey.CLIENT, data=[client, client_on_ssid2])
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_HOME
    assert hass.states.get("device_tracker.client_on_ssid2").state == STATE_HOME

    # Time pass to mark client as away
    new_time += timedelta(
        seconds=(
            config_entry.options.get(CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME) + 1
        )
    )
    with freeze_time(new_time):
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client").state == STATE_NOT_HOME

    client_on_ssid2["last_seen"] += 1
    mock_websocket_message(message=MessageKey.CLIENT, data=client_on_ssid2)
    await hass.async_block_till_done()

    # Client won't go away until after next update
    assert hass.states.get("device_tracker.client_on_ssid2").state == STATE_HOME

    # Trigger update to get client marked as away
    client_on_ssid2["last_seen"] += 1
    mock_websocket_message(message=MessageKey.CLIENT, data=client_on_ssid2)
    await hass.async_block_till_done()

    new_time += timedelta(
        seconds=(config_entry.options.get(CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME))
    )
    with freeze_time(new_time):
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

    assert hass.states.get("device_tracker.client_on_ssid2").state == STATE_NOT_HOME


@pytest.mark.usefixtures("mock_device_registry")
async def test_wireless_client_go_wired_issue(
    hass: HomeAssistant,
    mock_websocket_message,
    config_entry_factory: Callable[[], ConfigEntry],
    client_payload: list[dict[str, Any]],
) -> None:
    """Test the solution to catch wireless device go wired UniFi issue.

    UniFi Network has a known issue that when a wireless device goes away it sometimes gets marked as wired.
    """
    client_payload.append(
        {
            "essid": "ssid",
            "hostname": "client",
            "ip": "10.0.0.1",
            "is_wired": False,
            "last_seen": dt_util.as_timestamp(dt_util.utcnow()),
            "mac": "00:00:00:00:00:01",
        }
    )
    config_entry = await config_entry_factory()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1

    # Client is wireless
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME

    # Trigger wired bug
    client = client_payload[0]
    client["last_seen"] = dt_util.as_timestamp(dt_util.utcnow())
    client["is_wired"] = True
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    # Wired bug fix keeps client marked as wireless
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME

    # Pass time
    new_time = dt_util.utcnow() + timedelta(
        seconds=(config_entry.options.get(CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME))
    )
    with freeze_time(new_time):
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

    # Marked as home according to the timer
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_NOT_HOME

    # Try to mark client as connected
    client["last_seen"] += 1
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    # Make sure it don't go online again until wired bug disappears
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_NOT_HOME

    # Make client wireless
    client["last_seen"] += 1
    client["is_wired"] = False
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    # Client is no longer affected by wired bug and can be marked online
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME


@pytest.mark.parametrize("config_entry_options", [{CONF_IGNORE_WIRED_BUG: True}])
@pytest.mark.usefixtures("mock_device_registry")
async def test_option_ignore_wired_bug(
    hass: HomeAssistant,
    mock_websocket_message,
    config_entry_factory: Callable[[], ConfigEntry],
    client_payload: list[dict[str, Any]],
) -> None:
    """Test option to ignore wired bug."""
    client_payload.append(
        {
            "ap_mac": "00:00:00:00:02:01",
            "essid": "ssid",
            "hostname": "client",
            "ip": "10.0.0.1",
            "is_wired": False,
            "last_seen": dt_util.as_timestamp(dt_util.utcnow()),
            "mac": "00:00:00:00:00:01",
        }
    )
    config_entry = await config_entry_factory()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1

    # Client is wireless
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME

    # Trigger wired bug
    client = client_payload[0]
    client["is_wired"] = True
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    # Wired bug in effect
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME

    # pass time
    new_time = dt_util.utcnow() + timedelta(
        seconds=config_entry.options.get(CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME)
    )
    with freeze_time(new_time):
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

    # Timer marks client as away
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_NOT_HOME

    # Mark client as connected again
    client["last_seen"] += 1
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    # Ignoring wired bug allows client to go home again even while affected
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME

    # Make client wireless
    client["last_seen"] += 1
    client["is_wired"] = False
    mock_websocket_message(message=MessageKey.CLIENT, data=client)
    await hass.async_block_till_done()

    # Client is wireless and still connected
    client_state = hass.states.get("device_tracker.client")
    assert client_state.state == STATE_HOME


@pytest.mark.parametrize(
    "config_entry_options", [{CONF_BLOCK_CLIENT: ["00:00:00:00:00:02"]}]
)
@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "hostname": "client",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            }
        ]
    ],
)
@pytest.mark.parametrize(
    "clients_all_payload",
    [
        [
            {
                "hostname": "restored",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
            },
            {  # Not previously seen by integration, will not be restored
                "hostname": "not_restored",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:03",
            },
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_restoring_client(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: ConfigEntry,
    config_entry_factory: Callable[[], ConfigEntry],
    client_payload: list[dict[str, Any]],
    clients_all_payload: list[dict[str, Any]],
) -> None:
    """Verify clients are restored from clients_all if they ever was registered to entity registry."""
    entity_registry.async_get_or_create(  # Make sure unique ID converts to site_id-mac
        TRACKER_DOMAIN,
        UNIFI_DOMAIN,
        f'{clients_all_payload[0]["mac"]}-site_id',
        suggested_object_id=clients_all_payload[0]["hostname"],
        config_entry=config_entry,
    )
    entity_registry.async_get_or_create(  # Unique ID already follow format site_id-mac
        TRACKER_DOMAIN,
        UNIFI_DOMAIN,
        f'site_id-{client_payload[0]["mac"]}',
        suggested_object_id=client_payload[0]["hostname"],
        config_entry=config_entry,
    )

    await config_entry_factory()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.client")
    assert hass.states.get("device_tracker.restored")
    assert not hass.states.get("device_tracker.not_restored")


@pytest.mark.parametrize("config_entry_options", [{CONF_TRACK_CLIENTS: False}])
@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "essid": "ssid",
                "hostname": "Wireless client",
                "ip": "10.0.0.1",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
            {
                "hostname": "Wired client",
                "ip": "10.0.0.2",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
            },
        ]
    ],
)
@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "fan_level": 0,
                "ip": "10.0.1.1",
                "last_seen": 1562600145,
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            },
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_dont_track_clients(
    hass: HomeAssistant, config_entry_setup: ConfigEntry
) -> None:
    """Test don't track clients config works."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1
    assert not hass.states.get("device_tracker.wireless_client")
    assert not hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_CLIENTS: True}
    )
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 3
    assert hass.states.get("device_tracker.wireless_client")
    assert hass.states.get("device_tracker.wired_client")
    assert hass.states.get("device_tracker.device")


@pytest.mark.parametrize("config_entry_options", [{CONF_TRACK_DEVICES: False}])
@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "hostname": "client",
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
        ]
    ],
)
@pytest.mark.parametrize(
    "device_payload",
    [
        [
            {
                "board_rev": 3,
                "device_id": "mock-id",
                "has_fan": True,
                "fan_level": 0,
                "ip": "10.0.1.1",
                "last_seen": 1562600145,
                "mac": "00:00:00:00:01:01",
                "model": "US16P150",
                "name": "Device",
                "next_interval": 20,
                "overheating": True,
                "state": 1,
                "type": "usw",
                "upgradable": True,
                "version": "4.0.42.10433",
            },
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_dont_track_devices(
    hass: HomeAssistant, config_entry_setup: ConfigEntry
) -> None:
    """Test don't track devices config works."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1
    assert hass.states.get("device_tracker.client")
    assert not hass.states.get("device_tracker.device")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_DEVICES: True}
    )
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.client")
    assert hass.states.get("device_tracker.device")


@pytest.mark.parametrize("config_entry_options", [{CONF_TRACK_WIRED_CLIENTS: False}])
@pytest.mark.parametrize(
    "client_payload",
    [
        [
            {
                "essid": "ssid",
                "hostname": "Wireless Client",
                "is_wired": False,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:01",
            },
            {
                "is_wired": True,
                "last_seen": 1562600145,
                "mac": "00:00:00:00:00:02",
                "name": "Wired Client",
            },
        ]
    ],
)
@pytest.mark.usefixtures("mock_device_registry")
async def test_dont_track_wired_clients(
    hass: HomeAssistant, config_entry_setup: ConfigEntry
) -> None:
    """Test don't track wired clients config works."""
    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 1
    assert hass.states.get("device_tracker.wireless_client")
    assert not hass.states.get("device_tracker.wired_client")

    hass.config_entries.async_update_entry(
        config_entry_setup, options={CONF_TRACK_WIRED_CLIENTS: True}
    )
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids(TRACKER_DOMAIN)) == 2
    assert hass.states.get("device_tracker.wireless_client")
    assert hass.states.get("device_tracker.wired_client")
