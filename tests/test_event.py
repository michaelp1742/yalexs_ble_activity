"""Tests for the Yale Access Bluetooth Activity event entity."""

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)
from pytest_homeassistant_custom_component.components.common import arm_trigger
from pytest_homeassistant_custom_component.typing import WebSocketGenerator
from yalexs_ble import (
    CodeAdded,
    CredentialAdded,
    KeypadInfo,
    LockCred,
    LogRecord,
    OpCode,
)

from custom_components.yalexs_ble_activity.const import DOMAIN, EVENT_TYPES
from homeassistant.components.config import device_registry as config_device_registry
from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    CONF_ENTITY_ID,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_STATE_CHANGED,
    Platform,
)
from homeassistant.core import CoreState, Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    ADDRESS,
    ALIRO_SLOT_2_UNLOCKED,
    ALL_CODES_DELETED,
    AUTO_RELOCK_LOCKED,
    AUTO_RELOCK_SECUREMODE,
    BATTERY_INFO,
    BCM_TEST,
    CODE_ADDED_SLOT_5,
    CODE_ADDED_V2_SLOT_4,
    CODE_DELETED_SLOT_5,
    CODE_DELETED_V2_SLOT_260,
    CODE_OPERATION_SLOT_1,
    CODE_OPERATION_SLOT_FFEE,
    CREDENTIAL_ADDED_RF_SLOT_7,
    CREDENTIAL_DELETED_RF_SLOT_7,
    CREDENTIAL_TYPE_3_SLOT_2_UNLOCKED,
    DIALOG_REBOOT,
    DOOR_AJAR,
    DOOR_CLOSED,
    DOOR_OPENED,
    DOOR_UNKNOWN,
    DPS_INFO,
    END_OF_LOG,
    END_OF_LOG_DIRTY,
    ENTITY_ID,
    FACE_SLOT_2_UNLOCKED,
    FACTORY_RESET,
    FINGER_SLOT_2_UNLOCKED,
    HOMEKEY_OPERATION,
    INSIDE_BUTTON_LOCKED,
    INSIDE_DOOR_PIN_SLOT_3_UNLOCKED,
    KEYPAD_BUTTON_LOCKED,
    KEYPAD_CLOSE,
    KEYPAD_INFO,
    KEYPAD_OPEN,
    KEYPAD_WRONG_CODE,
    LOCAL_EVENT_NOTIFICATION,
    MANUAL_UNLOCKED,
    MATTER_MESSAGE,
    NO_DECODER,
    ONE_TOUCH_LOCKED,
    PALM_SLOT_2_UNLOCKED,
    PIN_SLOT_3_UNLOCKED,
    PRODUCT_MESSAGE,
    REMOTE_UNLOCKED,
    RF_SLOT_7_UNLOCKED,
    RF_SLOT_8_ERROR,
    TAMPER_DOOR_FORCED_OPEN,
    TIME,
    TITLE,
    async_advance,
    async_deliver,
    async_setup_platform,
    event_attributes,
    lock_operation,
)

# The attributes of CODE_OPERATION_SLOT_1 without the event type and the name.
CODE_OPERATION_SLOT_1_ATTRIBUTES = {
    "backlog": False,
    "timestamp": "2026-10-27T05:00:44+00:00",
    "log_type": 7,
    "current_lock_state": "unlocked",
    "current_door_state": "closed",
    "slot": 1,
    "error": 0,
    "battery_level": 5899,
    "battery_level_percent": 71,
}
# The attributes of CODE_OPERATION_SLOT_FFEE without the event type and the name.
CODE_OPERATION_SLOT_FFEE_ATTRIBUTES = {
    "backlog": False,
    "timestamp": "2056-11-26T10:17:13+00:00",
    "log_type": 7,
    "current_lock_state": "unlocked",
    "current_door_state": "opened",
    "slot": 0xFFEE,
    "error": 0,
    "battery_level": 5348,
    "battery_level_percent": 73,
}
# The attributes shared by the CredentialOperation replies constructed from a
# captured one.
CREDENTIAL_OPERATION_ATTRIBUTES = {
    "backlog": False,
    "timestamp": "2026-10-30T01:50:43+00:00",
    "log_type": 14,
    "credential_error": None,
    "current_lock_state": "unlocked",
    "current_door_state": "closed",
    "battery_level": 5874,
    "battery_level_percent": 55,
}

# The OpCode members whose event type names the operation's source, listed in
# EVENT_TYPES before the other members.
SOURCE_OP_CODES = {
    OpCode.DOOR_STATE_CHANGED,
    OpCode.DOOR_MANUAL_STATE_CHANGE,
    OpCode.AUTO_RELOCK,
    OpCode.ONE_TOUCH,
    OpCode.INSIDE_BUTTON,
}

# One reply for each event type, in the order the types are listed.
ONE_REPLY_PER_TYPE = [
    CODE_OPERATION_SLOT_FFEE,
    CODE_OPERATION_SLOT_1,
    RF_SLOT_7_UNLOCKED,
    FINGER_SLOT_2_UNLOCKED,
    FACE_SLOT_2_UNLOCKED,
    PALM_SLOT_2_UNLOCKED,
    ALIRO_SLOT_2_UNLOCKED,
    CREDENTIAL_TYPE_3_SLOT_2_UNLOCKED,
    RF_SLOT_8_ERROR,
    KEYPAD_BUTTON_LOCKED,
    REMOTE_UNLOCKED,
    INSIDE_BUTTON_LOCKED,
    AUTO_RELOCK_LOCKED,
    *[lock_operation(op_code) for op_code in OpCode if op_code not in SOURCE_OP_CODES],
    lock_operation(0x16),
    DOOR_OPENED,
    DOOR_CLOSED,
    DOOR_AJAR,
    DOOR_UNKNOWN,
    CODE_ADDED_SLOT_5,
    CODE_DELETED_SLOT_5,
    CODE_ADDED_V2_SLOT_4,
    CODE_DELETED_V2_SLOT_260,
    CREDENTIAL_ADDED_RF_SLOT_7,
    CREDENTIAL_DELETED_RF_SLOT_7,
    KEYPAD_OPEN,
    KEYPAD_WRONG_CODE,
    KEYPAD_CLOSE,
    KEYPAD_INFO,
    ALL_CODES_DELETED,
    FACTORY_RESET,
    TAMPER_DOOR_FORCED_OPEN,
    BCM_TEST,
    HOMEKEY_OPERATION,
    DPS_INFO,
    BATTERY_INFO,
    LOCAL_EVENT_NOTIFICATION,
    PRODUCT_MESSAGE,
    MATTER_MESSAGE,
    DIALOG_REBOOT,
    NO_DECODER,
]


def _entity_changes(events: list[Event]) -> list[Event]:
    """Return the state changes of the activity entity among events."""
    return [event for event in events if event.data["entity_id"] == ENTITY_ID]


def _asks(namer: Mock) -> list[tuple[Any, ...]]:
    """Return the arguments after hass of each call of namer."""
    return [called.args[1:] for called in namer.call_args_list]


@pytest.mark.usefixtures("loaded_entry")
async def test_a_code_record_fires_pin_with_its_decoded_fields(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """A CodeOperation fires pin with its lock time and decoded fields, and name None with no platform collected."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert len(_entity_changes(events)) == 1
    assert event_attributes(hass) == {
        ATTR_EVENT_TYPE: "pin",
        **CODE_OPERATION_SLOT_1_ATTRIBUTES,
        "name": None,
    }


async def test_the_entity_sits_on_a_device_linked_to_cores(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """The entity is named Activity, on a device of its own linked to core's by the PushLock's address."""
    lock = owner_entry.runtime_data.lock
    # A lower-case lock.address fails the test if the device connection takes
    # the entry's address, which core's device connection does not use.
    lock.address = ADDRESS.lower()
    core_device = device_registry.async_get_or_create(
        config_entry_id=owner_entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, lock.address)},
        identifiers={("yalexs_ble", "serial")},
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = entity_registry.async_get(ENTITY_ID)
    assert entity.unique_id == f"{ADDRESS}_activity"
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FRIENDLY_NAME] == (
        f"{TITLE} Activity"
    )
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EVENT_TYPES] == list(EVENT_TYPES)
    device = device_registry.async_get(entity.device_id)
    assert device.config_entry_id == config_entry.entry_id
    assert device.connections == {(dr.CONNECTION_BLUETOOTH, lock.address)}
    assert device.name == TITLE
    config_device_registry.async_setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "config/device_registry/list_linked_devices",
            "device_id": core_device.id,
        }
    )
    msg = await client.receive_json()
    assert msg["result"]["linked_devices"] == [device.id]


async def test_a_platform_loaded_before_setup_names_the_slot(
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> None:
    """A platform of an integration loaded before setup names the slot it is asked for."""
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert event_attributes(hass)["name"] == "Michael"
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)


@pytest.mark.usefixtures("loaded_entry")
async def test_a_platform_loaded_after_setup_names_the_slot(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """A platform of an integration loaded after setup is collected and names the slot."""
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert event_attributes(hass)["name"] == "Michael"
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)


@pytest.mark.usefixtures("loaded_entry")
async def test_the_first_platform_with_a_name_names_the_slot(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """The platforms are asked in the order collected, and the first name wins."""
    first = Mock(return_value=None)
    second = Mock(return_value="Guest")
    await async_setup_platform(hass, "first", async_credential_name=first)
    await async_setup_platform(hass, "second", async_credential_name=second)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert event_attributes(hass)["name"] == "Guest"

    first.return_value = "Michael"
    second.reset_mock()
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert event_attributes(hass)["name"] == "Michael"
    second.assert_not_called()


@pytest.mark.usefixtures("loaded_entry")
async def test_a_platform_that_raises_is_logged_and_passed_over(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, owner_entry: MockConfigEntry
) -> None:
    """A platform that raises is logged with its module, and the next platform names the slot."""
    raising = Mock(side_effect=RuntimeError("broken"))
    await async_setup_platform(hass, "raising", async_credential_name=raising)
    await async_setup_platform(
        hass, "second", async_credential_name=Mock(return_value="Guest")
    )

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert event_attributes(hass)["name"] == "Guest"
    (record,) = [
        record
        for record in caplog.records
        if record.name.startswith(f"custom_components.{DOMAIN}")
    ]
    assert record.levelno == logging.ERROR
    assert f"custom_components.raising.{DOMAIN}" in record.getMessage()
    assert record.exc_info[0] is RuntimeError


@pytest.mark.usefixtures("loaded_entry")
async def test_a_platform_without_the_function_warns_and_is_not_collected(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, owner_entry: MockConfigEntry
) -> None:
    """A platform module without async_credential_name is logged at warning, and the event fires with name None."""
    await async_setup_platform(hass, "broken")

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    (record,) = [
        record
        for record in caplog.records
        if record.name.startswith(f"custom_components.{DOMAIN}")
    ]
    assert record.levelno == logging.WARNING
    assert "broken" in record.getMessage()
    assert event_attributes(hass) == {
        ATTR_EVENT_TYPE: "pin",
        **CODE_OPERATION_SLOT_1_ATTRIBUTES,
        "name": None,
    }


@pytest.mark.parametrize(
    ("lock_model", "expected", "asks"),
    [
        pytest.param(
            "unity",
            {ATTR_EVENT_TYPE: "master_code", **CODE_OPERATION_SLOT_FFEE_ATTRIBUTES},
            [],
            id="unity_master_code",
        ),
        pytest.param(
            "doorman_classic",
            {
                ATTR_EVENT_TYPE: "pin",
                **CODE_OPERATION_SLOT_FFEE_ATTRIBUTES,
                "name": None,
            },
            [(ADDRESS, LockCred.PIN, 0xFFEE)],
            id="doorman_classic_no_master_code_slot",
        ),
        pytest.param(
            "retired_model",
            {
                ATTR_EVENT_TYPE: "pin",
                **CODE_OPERATION_SLOT_FFEE_ATTRIBUTES,
                "name": None,
            },
            [(ADDRESS, LockCred.PIN, 0xFFEE)],
            id="unknown_key_takes_the_other_row",
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_the_master_code_slot_comes_from_the_model_row(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    expected: dict[str, Any],
    asks: list[tuple[Any, ...]],
) -> None:
    """The model row's master code slot fires master_code with no platform asked; a row without one fires pin."""
    namer = Mock(return_value=None)
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_FFEE)

    assert event_attributes(hass) == expected
    assert _asks(namer) == asks


@pytest.mark.parametrize(
    ("raw", "expected", "asks"),
    [
        pytest.param(
            RF_SLOT_7_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "rf",
                "backlog": False,
                "timestamp": "2026-10-25T07:18:41+00:00",
                "log_type": 14,
                "credential_type": "rf",
                "slot": 7,
                "credential_error": None,
                "current_lock_state": "unlocked",
                "current_door_state": "closed",
                "battery_level": 5919,
                "battery_level_percent": 66,
                "name": None,
            },
            [(ADDRESS, LockCred.RF, 7)],
            id="rf",
        ),
        pytest.param(
            PIN_SLOT_3_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "pin",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "pin",
                "slot": 3,
                "name": None,
            },
            [(ADDRESS, LockCred.PIN, 3)],
            id="pin",
        ),
        pytest.param(
            INSIDE_DOOR_PIN_SLOT_3_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "pin",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "inside_door_pin",
                "slot": 3,
                "name": None,
            },
            [(ADDRESS, LockCred.INSIDE_DOOR_PIN, 3)],
            id="inside_door_pin",
        ),
        pytest.param(
            FINGER_SLOT_2_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "finger",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "finger",
                "slot": 2,
                "name": None,
            },
            [(ADDRESS, LockCred.FINGER, 2)],
            id="finger",
        ),
        pytest.param(
            FACE_SLOT_2_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "face",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "face",
                "slot": 2,
                "name": None,
            },
            [(ADDRESS, LockCred.FACE, 2)],
            id="face",
        ),
        pytest.param(
            PALM_SLOT_2_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "palm",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "palm",
                "slot": 2,
                "name": None,
            },
            [(ADDRESS, LockCred.PALM, 2)],
            id="palm",
        ),
        pytest.param(
            ALIRO_SLOT_2_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "aliro",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "aliro",
                "slot": 2,
                "name": None,
            },
            [(ADDRESS, LockCred.ALIRO, 2)],
            id="aliro",
        ),
        pytest.param(
            CREDENTIAL_TYPE_3_SLOT_2_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "credential",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": 3,
                "slot": 2,
            },
            [],
            id="type_outside_lockcred",
        ),
        pytest.param(
            RF_SLOT_8_ERROR,
            {
                ATTR_EVENT_TYPE: "credential_error",
                **CREDENTIAL_OPERATION_ATTRIBUTES,
                "credential_type": "rf",
                "slot": 8,
                "credential_error": 0xF3,
                "current_lock_state": None,
                "current_door_state": None,
            },
            [],
            id="credential_error",
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_a_credential_operation_fires_the_type_of_its_credential(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    raw: bytes,
    expected: dict[str, Any],
    asks: list[tuple[Any, ...]],
) -> None:
    """A CredentialOperation fires its credential's type, and a name is asked for the record's LockCred."""
    namer = Mock(return_value=None)
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, raw)

    assert event_attributes(hass) == expected
    assert _asks(namer) == asks


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            KEYPAD_BUTTON_LOCKED,
            {
                ATTR_EVENT_TYPE: "keypad_button",
                "op_code": "door_state_changed",
                "key_slot": 0xFF,
            },
            id="keypad_button_key_slot_ff",
        ),
        pytest.param(
            ONE_TOUCH_LOCKED,
            {ATTR_EVENT_TYPE: "keypad_button", "op_code": "one_touch"},
            id="keypad_button_one_touch",
        ),
        pytest.param(
            REMOTE_UNLOCKED,
            {
                ATTR_EVENT_TYPE: "remote",
                "op_code": "door_state_changed",
                "key_slot": 0,
                "current_lock_state": "unlocked",
            },
            id="remote",
        ),
        pytest.param(
            INSIDE_BUTTON_LOCKED,
            {ATTR_EVENT_TYPE: "manual", "op_code": "inside_button"},
            id="manual_inside_button",
        ),
        pytest.param(
            MANUAL_UNLOCKED,
            {ATTR_EVENT_TYPE: "manual", "op_code": "door_manual_state_change"},
            id="manual_door_manual_state_change",
        ),
        pytest.param(
            AUTO_RELOCK_LOCKED,
            {ATTR_EVENT_TYPE: "auto_lock", "current_lock_state": "locked"},
            id="auto_lock",
        ),
        pytest.param(
            AUTO_RELOCK_SECUREMODE,
            {ATTR_EVENT_TYPE: "auto_lock", "current_lock_state": "securemode"},
            id="auto_lock_securemode",
        ),
        pytest.param(
            lock_operation(OpCode.LOW_BAT_AUTO_UNLOCK),
            {
                ATTR_EVENT_TYPE: "low_bat_auto_unlock",
                "op_code": "low_bat_auto_unlock",
            },
            id="op_code_member",
        ),
        pytest.param(
            lock_operation(OpCode.ALIRO),
            {ATTR_EVENT_TYPE: "aliro_operation", "op_code": "aliro"},
            id="op_code_aliro",
        ),
        pytest.param(
            lock_operation(0x16),
            {ATTR_EVENT_TYPE: "lock_operation", "op_code": 0x16},
            id="op_code_outside_opcode",
        ),
        pytest.param(
            DOOR_OPENED,
            {ATTR_EVENT_TYPE: "door_opened", "current_door_state": "opened"},
            id="door_opened",
        ),
        pytest.param(
            DOOR_CLOSED,
            {ATTR_EVENT_TYPE: "door_closed", "current_door_state": "closed"},
            id="door_closed",
        ),
        pytest.param(
            DOOR_AJAR,
            {ATTR_EVENT_TYPE: "door_ajar", "current_door_state": "ajar"},
            id="door_ajar",
        ),
        pytest.param(
            DOOR_UNKNOWN,
            {ATTR_EVENT_TYPE: "door_state_changed", "current_door_state": "unknown"},
            id="door_state_changed",
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_an_operation_or_door_record_fires_the_type_of_its_source(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    raw: bytes,
    expected: dict[str, Any],
) -> None:
    """A LockOperation fires the type of its source, and a DoorStateChanged the door's new state, with no name."""
    await async_deliver(owner_entry, raw)

    attributes = event_attributes(hass)
    assert attributes.items() >= expected.items()
    assert "name" not in attributes


@pytest.mark.parametrize("raw", [END_OF_LOG, END_OF_LOG_DIRTY])
@pytest.mark.usefixtures("loaded_entry")
async def test_a_get_log_error_fires_no_event(
    hass: HomeAssistant, owner_entry: MockConfigEntry, raw: bytes
) -> None:
    """A GetLogError, with its dirty bit clear or set, fires no event and writes no state."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await async_deliver(owner_entry, raw)

    assert _entity_changes(events) == []
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    assert len(_entity_changes(events)) == 1


@pytest.mark.usefixtures("loaded_entry")
async def test_keypad_info_and_its_code_fire_two_events_in_order(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, owner_entry: MockConfigEntry
) -> None:
    """A KeypadInfo and the CodeOperation after it fire keypad_info, then pin."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await async_deliver(owner_entry, KEYPAD_INFO)
    await async_advance(hass, freezer, 0.6)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    keypad_info, pin = (
        event.data["new_state"].attributes for event in _entity_changes(events)
    )
    assert keypad_info[ATTR_EVENT_TYPE] == "keypad_info"
    assert keypad_info["battery_level"] == 195
    assert keypad_info["stats"] == 0x80000000
    assert pin[ATTR_EVENT_TYPE] == "pin"


@pytest.mark.usefixtures("loaded_entry")
async def test_two_records_in_one_millisecond_run_an_automation_twice(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """Two records read in one millisecond are two state changes, each matching event.received."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    matched: list[str] = []
    unmatched: list[str] = []
    target = {CONF_ENTITY_ID: [ENTITY_ID]}
    await arm_trigger(
        hass, "event.received", {"event_type": ["pin", "rf"]}, target, matched
    )
    await arm_trigger(
        hass, "event.received", {"event_type": ["remote"]}, target, unmatched
    )

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_deliver(owner_entry, RF_SLOT_7_UNLOCKED)
    await hass.async_block_till_done()

    first, second = (
        datetime.fromisoformat(event.data["new_state"].state)
        for event in _entity_changes(events)
    )
    assert second - first == timedelta(milliseconds=1)
    assert matched == [ENTITY_ID, ENTITY_ID]
    assert unmatched == []


@pytest.mark.usefixtures("loaded_entry")
async def test_backlog_records_fire_in_the_order_read(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, owner_entry: MockConfigEntry
) -> None:
    """Backlog records fire with backlog true in the order read, whatever their time stamps."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    for raw in (CODE_OPERATION_SLOT_1, AUTO_RELOCK_LOCKED, INSIDE_BUTTON_LOCKED):
        await async_deliver(owner_entry, raw, backlog=True)
        await async_advance(hass, freezer, 0.6)

    states = [event.data["new_state"] for event in _entity_changes(events)]
    assert [
        (
            state.attributes[ATTR_EVENT_TYPE],
            state.attributes["timestamp"],
            state.attributes["backlog"],
        )
        for state in states
    ] == [
        ("pin", "2026-10-27T05:00:44+00:00", True),
        ("auto_lock", "2026-10-25T07:19:23+00:00", True),
        ("manual", "2026-10-25T11:57:27+00:00", True),
    ]
    times = [datetime.fromisoformat(state.state) for state in states]
    assert times[0] < times[1] < times[2]


async def test_records_read_at_a_start_fire_once_home_assistant_has_started(
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> None:
    """Records read before Home Assistant has started fire once it has, in the order read and named by a platform collected meanwhile."""
    hass.set_state(CoreState.starting)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1, backlog=True)
    await async_deliver(owner_entry, AUTO_RELOCK_LOCKED, backlog=True)
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)
    assert _entity_changes(events) == []

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert [
        (
            event.data["new_state"].attributes[ATTR_EVENT_TYPE],
            event.data["new_state"].attributes.get("name"),
            event.data["new_state"].attributes["backlog"],
        )
        for event in _entity_changes(events)
    ] == [("pin", "Michael", True), ("auto_lock", None, True)]
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)


async def test_a_disabled_entity_registers_no_reader(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """An entity disabled in the registry is not added, and registers no reader."""
    entity_registry.async_get_or_create(
        Platform.EVENT,
        DOMAIN,
        f"{ADDRESS}_activity",
        config_entry=config_entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID) is None
    owner_entry.runtime_data.lock.register_log_record_callback.assert_not_called()


async def test_unloading_the_entry_removes_the_reader(
    hass: HomeAssistant, owner_entry: MockConfigEntry, loaded_entry: MockConfigEntry
) -> None:
    """The entry's unload removes the reader the entity registered."""
    register = owner_entry.runtime_data.lock.register_log_record_callback
    register.assert_called_once()
    register.return_value.assert_not_called()

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)

    register.return_value.assert_called_once_with()


@pytest.mark.usefixtures("loaded_entry")
async def test_code_records_hold_their_codes_and_are_named(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """A CodeAddedv2 holds its code and is named by its PIN slot, and a KeypadWrongCode holds its keycode."""
    namer = Mock(return_value="Guest")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_ADDED_V2_SLOT_4)

    assert event_attributes(hass) == {
        ATTR_EVENT_TYPE: "code_added_v2",
        "backlog": False,
        "timestamp": TIME,
        "log_type": 0x0A,
        "slot": 4,
        "code": "000000000001E240",
        "name": "Guest",
    }
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 4)

    await async_deliver(owner_entry, KEYPAD_WRONG_CODE)

    assert event_attributes(hass) == {
        ATTR_EVENT_TYPE: "keypad_wrong_code",
        "backlog": False,
        "timestamp": TIME,
        "log_type": 0x02,
        "keycode": "123456FFFFFFFFFF",
    }
    namer.assert_called_once()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            KEYPAD_OPEN,
            {
                ATTR_EVENT_TYPE: "keypad_open",
                "timestamp": TIME,
                "log_type": 0x01,
                "keycode": "123456FFFFFFFFFF",
            },
            id="keypad_open",
        ),
        pytest.param(
            KEYPAD_CLOSE,
            {
                ATTR_EVENT_TYPE: "keypad_close",
                "timestamp": TIME,
                "log_type": 0x08,
                "keycode": "123456FFFFFFFFFF",
            },
            id="keypad_close",
        ),
        pytest.param(
            CODE_ADDED_SLOT_5,
            {
                ATTR_EVENT_TYPE: "code_added",
                "timestamp": TIME,
                "log_type": 0x03,
                "slot": 5,
                "code": "123456FFFFFFFFFF",
                "name": None,
            },
            id="code_added",
        ),
        pytest.param(
            CODE_DELETED_SLOT_5,
            {
                ATTR_EVENT_TYPE: "code_deleted",
                "timestamp": TIME,
                "log_type": 0x05,
                "slot": 5,
                "name": None,
            },
            id="code_deleted",
        ),
        pytest.param(
            ALL_CODES_DELETED,
            {ATTR_EVENT_TYPE: "all_codes_deleted", "timestamp": TIME, "log_type": 0x06},
            id="all_codes_deleted",
        ),
        pytest.param(
            FACTORY_RESET,
            {ATTR_EVENT_TYPE: "factory_reset", "timestamp": TIME, "log_type": 0x09},
            id="factory_reset",
        ),
        pytest.param(
            CODE_DELETED_V2_SLOT_260,
            {
                ATTR_EVENT_TYPE: "code_deleted_v2",
                "timestamp": TIME,
                "log_type": 0x0B,
                "slot": 260,
                "name": None,
            },
            id="code_deleted_v2",
        ),
        pytest.param(
            CREDENTIAL_ADDED_RF_SLOT_7,
            {
                ATTR_EVENT_TYPE: "credential_added",
                "timestamp": TIME,
                "log_type": 0x0C,
                "credential_type": "rf",
                "slot": 7,
                "credential_error": None,
                "current_lock_state": "unlocked",
                "current_door_state": "closed",
                "battery_level": 5919,
                "battery_level_percent": 66,
                "name": None,
            },
            id="credential_added",
        ),
        pytest.param(
            CREDENTIAL_DELETED_RF_SLOT_7,
            {
                ATTR_EVENT_TYPE: "credential_deleted",
                "timestamp": TIME,
                "log_type": 0x0D,
                "credential_type": "rf",
                "slot": 7,
                "credential_error": None,
                "current_lock_state": "unlocked",
                "current_door_state": "closed",
                "battery_level": 5919,
                "battery_level_percent": 66,
                "name": None,
            },
            id="credential_deleted",
        ),
        pytest.param(
            TAMPER_DOOR_FORCED_OPEN,
            {
                ATTR_EVENT_TYPE: "tamper",
                "timestamp": TIME,
                "log_type": 0x0F,
                "tamper_type": "door_forced_open",
            },
            id="tamper",
        ),
        pytest.param(
            BCM_TEST,
            {
                ATTR_EVENT_TYPE: "bcm_test",
                "timestamp": TIME,
                "log_type": 0x10,
                "error": 1,
                "seconds": 60,
                "adv_counter": 10000,
            },
            id="bcm_test",
        ),
        pytest.param(
            HOMEKEY_OPERATION,
            {
                ATTR_EVENT_TYPE: "homekey_operation",
                "timestamp": TIME,
                "log_type": 0x12,
                "current_lock_state": "unlocked",
                "battery_level_decivolt": 58,
                "key_id": 0xDEADBEEF,
                "error": 0,
            },
            id="homekey_operation",
        ),
        pytest.param(
            DPS_INFO,
            {
                ATTR_EVENT_TYPE: "dps_info",
                "timestamp": TIME,
                "log_type": 0x13,
                "battery_level_percent": 80,
            },
            id="dps_info",
        ),
        pytest.param(
            BATTERY_INFO,
            {
                ATTR_EVENT_TYPE: "battery_info",
                "timestamp": TIME,
                "log_type": 0x15,
                "battery_level_millivolt": 5880,
                "temperature": -5,
                "state_of_charge": 90,
                "state_of_health": 100,
                "battery_index": 1,
                "error": 0,
            },
            id="battery_info",
        ),
        pytest.param(
            LOCAL_EVENT_NOTIFICATION,
            {
                ATTR_EVENT_TYPE: "local_event_notification",
                "timestamp": TIME,
                "log_type": 0x16,
                "notification": 7,
            },
            id="local_event_notification",
        ),
        pytest.param(
            PRODUCT_MESSAGE,
            {
                ATTR_EVENT_TYPE: "product_message",
                "timestamp": TIME,
                "log_type": 0x17,
                "msg_type": 0x1234,
                "data": [1, 2, 3, 4, 5],
            },
            id="product_message",
        ),
        pytest.param(
            MATTER_MESSAGE,
            {
                ATTR_EVENT_TYPE: "matter_message",
                "timestamp": TIME,
                "log_type": 0x18,
                "msg_type": 0x1234,
                "data": [1, 2, 3, 4, 5],
            },
            id="matter_message",
        ),
        pytest.param(
            DIALOG_REBOOT,
            {
                ATTR_EVENT_TYPE: "dialog_reboot",
                "timestamp": TIME,
                "log_type": 0x40,
                "lock_state": "locked",
                "door_state": "closed",
                "num_ble_conn": 2,
                "reboot_reason": 3,
                "task_id": 7,
                "pc": 0x12345678,
            },
            id="dialog_reboot",
        ),
        pytest.param(
            NO_DECODER,
            {
                ATTR_EVENT_TYPE: "unknown_record",
                "log_type": 0x11,
                "raw": NO_DECODER.hex(),
            },
            id="unknown_record",
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_each_record_class_fires_its_kind_with_its_decoded_fields(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    raw: bytes,
    expected: dict[str, Any],
) -> None:
    """Every other record class fires its kind with each decoded field, and an undecoded record its raw bytes."""
    await async_deliver(owner_entry, raw)

    assert event_attributes(hass) == {"backlog": False, **expected}


class _LaterCodeAdded(CodeAdded):
    """Stand in for a subclass of CodeAdded that a later version of the library adds."""


class _LaterCredentialAdded(CredentialAdded):
    """Stand in for a subclass of CredentialAdded that a later version of the library adds."""


class _LaterKeypadInfo(KeypadInfo):
    """Stand in for a subclass of KeypadInfo that a later version of the library adds."""


@pytest.mark.parametrize(
    ("record_class", "raw", "event_type"),
    [
        pytest.param(_LaterCodeAdded, CODE_ADDED_SLOT_5, "code_added", id="code"),
        pytest.param(
            _LaterCredentialAdded,
            CREDENTIAL_ADDED_RF_SLOT_7,
            "credential_added",
            id="credential",
        ),
        pytest.param(_LaterKeypadInfo, KEYPAD_INFO, "keypad_info", id="other"),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_a_subclass_of_a_record_class_fires_the_type_of_its_class(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    record_class: type[LogRecord],
    raw: bytes,
    event_type: str,
) -> None:
    """A record of a subclass the library adds fires the type of the record class it derives from."""
    with patch(
        "custom_components.yalexs_ble_activity.event.parse_log_event_packet",
        side_effect=record_class.decode,
    ):
        await async_deliver(owner_entry, raw)

    assert hass.states.get(ENTITY_ID).attributes[ATTR_EVENT_TYPE] == event_type


@pytest.mark.usefixtures("loaded_entry")
async def test_event_types_lists_each_type_once_in_the_table_order(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """EVENT_TYPES holds each type once, in the order of one record of each type."""
    fired = []
    for raw in ONE_REPLY_PER_TYPE:
        await async_deliver(owner_entry, raw)
        fired.append(hass.states.get(ENTITY_ID).attributes[ATTR_EVENT_TYPE])

    assert fired == list(EVENT_TYPES)
    assert len(set(EVENT_TYPES)) == len(EVENT_TYPES)


def test_translations_name_each_event_type_and_no_other() -> None:
    """The translations hold a state name for each event type and for no other."""
    translations = json.loads(
        (
            Path(__file__).parents[1]
            / "custom_components"
            / DOMAIN
            / "translations"
            / "en.json"
        ).read_text()
    )

    activity = translations["entity"]["event"]["activity"]
    assert activity["name"] == "Activity"
    assert activity["state_attributes"]["event_type"]["state"].keys() == set(
        EVENT_TYPES
    )
