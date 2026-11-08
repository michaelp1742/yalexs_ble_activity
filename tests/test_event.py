"""Tests for the Yale Access Bluetooth Activity log record events and event entity."""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Any, Self
from unittest.mock import Mock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator
from yalexs_ble import (
    CodeAdded,
    CredentialAdded,
    KeypadInfo,
    LockCred,
    LogRecord,
    OpCode,
    parse_log_event_packet,
)

from custom_components.yalexs_ble_activity.activity import activity_for
from custom_components.yalexs_ble_activity.const import (
    DOMAIN,
    EVENT_LOG_RECORD,
    EVENT_TYPE_WORDS,
    EVENT_TYPES,
)
from custom_components.yalexs_ble_activity.models import LOCK_MODELS
from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.components.config import device_registry as config_device_registry
from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.const import ATTR_FRIENDLY_NAME, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

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
    RF_SLOT_7_AT_PIN_SLOT_3,
    RF_SLOT_7_UNLOCKED,
    RF_SLOT_8_ERROR,
    TAMPER_DOOR_FORCED_OPEN,
    TIME,
    TITLE,
    activity_device,
    async_deliver,
    async_setup_platform,
    enable_entity,
    last_data,
    lock_operation,
)

# A time after the own times of CODE_OPERATION_SLOT_FFEE and ONE_TOUCH_LOCKED, both
# in 2056, so that the two records are inside the window.
AFTER_SLOT_FFEE = "2057-01-01T00:00:00+00:00"
# A time after every other captured and constructed reply.
NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)

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


def _asks(namer: Mock) -> list[tuple[Any, ...]]:
    """Return the arguments after hass of each call of namer."""
    return [called.args[1:] for called in namer.call_args_list]


async def test_a_code_record_fires_pin_with_its_decoded_fields(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A CodeOperation fires one pin log record event with its lock time, its decoded fields, the first serial, the integration's device, and name None with no platform collected."""
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    (event,) = log_records
    assert event.data == {
        ATTR_EVENT_TYPE: "pin",
        **CODE_OPERATION_SLOT_1_ATTRIBUTES,
        "name": None,
        "serial": 1,
        "device_id": activity_device(hass, loaded_entry).id,
    }


async def test_the_entity_is_disabled_on_a_device_linked_to_cores(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """A new entry's entity is disabled by the integration, on the integration's device, created at setup with the PushLock's address and the entry's title."""
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
    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(ENTITY_ID) is None
    device = activity_device(hass, config_entry)
    assert entity.device_id == device.id
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
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A platform of an integration loaded before setup names the slot it is asked for."""
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert last_data(log_records)["name"] == "Michael"
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)


@pytest.mark.usefixtures("loaded_entry")
async def test_a_platform_loaded_after_setup_names_the_slot(
    hass: HomeAssistant, owner_entry: MockConfigEntry, log_records: list[Event]
) -> None:
    """A platform of an integration loaded after setup is collected and names the slot."""
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert last_data(log_records)["name"] == "Michael"
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)


@pytest.mark.usefixtures("loaded_entry")
async def test_the_first_platform_with_a_name_names_the_slot(
    hass: HomeAssistant, owner_entry: MockConfigEntry, log_records: list[Event]
) -> None:
    """The platforms are asked in the order collected, and the first name wins."""
    first = Mock(return_value=None)
    second = Mock(return_value="Guest")
    await async_setup_platform(hass, "first", async_credential_name=first)
    await async_setup_platform(hass, "second", async_credential_name=second)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert last_data(log_records)["name"] == "Guest"

    first.return_value = "Michael"
    second.reset_mock()
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert last_data(log_records)["name"] == "Michael"
    second.assert_not_called()


@pytest.mark.usefixtures("loaded_entry")
async def test_a_platform_that_raises_is_logged_and_passed_over(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    owner_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A platform that raises is logged with its module, and the next platform names the slot."""
    raising = Mock(side_effect=RuntimeError("broken"))
    await async_setup_platform(hass, "raising", async_credential_name=raising)
    await async_setup_platform(
        hass, "second", async_credential_name=Mock(return_value="Guest")
    )

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert last_data(log_records)["name"] == "Guest"
    (record,) = [
        record
        for record in caplog.records
        if record.name.startswith(f"custom_components.{DOMAIN}")
    ]
    assert record.levelno == logging.ERROR
    assert f"custom_components.raising.{DOMAIN}" in record.getMessage()
    assert record.exc_info[0] is RuntimeError


async def test_a_platform_without_the_function_warns_and_is_not_collected(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
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
    assert last_data(log_records) == {
        ATTR_EVENT_TYPE: "pin",
        **CODE_OPERATION_SLOT_1_ATTRIBUTES,
        "name": None,
        "serial": 1,
        "device_id": activity_device(hass, loaded_entry).id,
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
async def test_the_master_code_slot_comes_from_the_model_row(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
    expected: dict[str, Any],
    asks: list[tuple[Any, ...]],
) -> None:
    """The model row's master code slot fires master_code with no platform asked; a row without one fires pin."""
    freezer.move_to(AFTER_SLOT_FFEE)
    namer = Mock(return_value=None)
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_FFEE)

    assert last_data(log_records) == {
        **expected,
        "serial": 1,
        "device_id": activity_device(hass, loaded_entry).id,
    }
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
async def test_a_credential_operation_fires_the_type_of_its_credential(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
    raw: bytes,
    expected: dict[str, Any],
    asks: list[tuple[Any, ...]],
) -> None:
    """A CredentialOperation fires its credential's type, and a name is asked for the record's LockCred."""
    namer = Mock(return_value=None)
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, raw)

    assert last_data(log_records) == {
        **expected,
        "serial": 1,
        "device_id": activity_device(hass, loaded_entry).id,
    }
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
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    log_records: list[Event],
    raw: bytes,
    expected: dict[str, Any],
) -> None:
    """A LockOperation fires the type of its source, and a DoorStateChanged the door's new state, with no name."""
    # The own time of ONE_TOUCH_LOCKED is in 2056.
    freezer.move_to(AFTER_SLOT_FFEE)

    await async_deliver(owner_entry, raw)

    data = last_data(log_records)
    assert data.items() >= expected.items()
    assert "name" not in data


@pytest.mark.parametrize("raw", [END_OF_LOG, END_OF_LOG_DIRTY])
@pytest.mark.usefixtures("loaded_entry")
async def test_a_get_log_error_fires_no_event(
    owner_entry: MockConfigEntry, log_records: list[Event], raw: bytes
) -> None:
    """A GetLogError, with its dirty bit clear or set, fires no log record event and takes no serial."""
    await async_deliver(owner_entry, raw)

    assert log_records == []
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    assert [event.data["serial"] for event in log_records] == [1]


async def test_automations_on_the_log_record_event_run_once_per_matching_record(
    hass: HomeAssistant, owner_entry: MockConfigEntry, loaded_entry: MockConfigEntry
) -> None:
    """Two records in one own second each run the automation whose event data matches their event type, and no other."""
    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        AUTOMATION_DOMAIN,
        {
            AUTOMATION_DOMAIN: [
                {
                    "triggers": {
                        "trigger": "event",
                        "event_type": EVENT_LOG_RECORD,
                        "event_data": {"event_type": event_type},
                    },
                    "actions": {
                        "action": "test.automation",
                        "data": {"event_type": event_type},
                    },
                }
                for event_type in ("pin", "rf", "remote")
            ]
        },
    )

    await async_deliver(owner_entry, PIN_SLOT_3_UNLOCKED)
    await async_deliver(owner_entry, RF_SLOT_7_AT_PIN_SLOT_3)
    await hass.async_block_till_done()

    assert [call.data["event_type"] for call in calls] == ["pin", "rf"]


async def test_a_disabled_entity_leaves_the_reader_firing_log_record_events(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """With the entity disabled, the entry's reader is registered and fires log record events, and the entity has no state."""
    owner_entry.runtime_data.lock.register_log_record_callback.assert_called_once_with(
        loaded_entry.runtime_data.async_log_record
    )

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert [event.data[ATTR_EVENT_TYPE] for event in log_records] == ["pin"]
    assert hass.states.get(ENTITY_ID) is None


async def test_an_enabled_entity_fires_each_record_under_its_log_record_event(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    entity_registry: er.EntityRegistry,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """An enabled entity takes each fired record's data less the device, under the log record event's context, at the time received; a discarded record writes no state."""
    freezer.move_to(NOW)
    enable_entity(entity_registry, config_entry)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    changes = async_capture_events(hass, EVENT_STATE_CHANGED)
    namer = Mock(return_value="Guest")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    (event,) = log_records
    (change,) = changes
    expected = dict(event.data)
    del expected["device_id"]
    state = change.data["new_state"]
    assert state.entity_id == ENTITY_ID
    assert state.attributes == {
        **expected,
        ATTR_EVENT_TYPES: list(EVENT_TYPES),
        ATTR_FRIENDLY_NAME: f"{TITLE} Activity",
    }
    assert state.context.id == event.context.id
    assert datetime.fromisoformat(state.state) == NOW

    # The own time of CODE_OPERATION_SLOT_FFEE is decades after NOW.
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_FFEE)

    assert len(log_records) == 1
    assert len(changes) == 1


async def test_code_records_hold_their_codes_and_are_named(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A CodeAddedv2 holds its code and is named by its PIN slot, and a KeypadWrongCode holds its keycode."""
    device_id = activity_device(hass, loaded_entry).id
    namer = Mock(return_value="Guest")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_ADDED_V2_SLOT_4)

    assert last_data(log_records) == {
        ATTR_EVENT_TYPE: "code_added_v2",
        "backlog": False,
        "timestamp": TIME,
        "log_type": 0x0A,
        "slot": 4,
        "code": "000000000001E240",
        "name": "Guest",
        "serial": 1,
        "device_id": device_id,
    }
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 4)

    await async_deliver(owner_entry, KEYPAD_WRONG_CODE)

    assert last_data(log_records) == {
        ATTR_EVENT_TYPE: "keypad_wrong_code",
        "backlog": False,
        "timestamp": TIME,
        "log_type": 0x02,
        "keycode": "123456FFFFFFFFFF",
        "serial": 2,
        "device_id": device_id,
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
async def test_each_record_class_fires_its_kind_with_its_decoded_fields(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
    raw: bytes,
    expected: dict[str, Any],
) -> None:
    """Every other record class fires its kind with each decoded field, and an undecoded record its raw bytes."""
    await async_deliver(owner_entry, raw)

    assert last_data(log_records) == {
        "backlog": False,
        **expected,
        "serial": 1,
        "device_id": activity_device(hass, loaded_entry).id,
    }


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
    owner_entry: MockConfigEntry,
    log_records: list[Event],
    record_class: type[LogRecord],
    raw: bytes,
    event_type: str,
) -> None:
    """A record of a subclass the library adds fires the type of the record class it derives from."""
    with patch(
        "custom_components.yalexs_ble_activity.reader.parse_log_event_packet",
        side_effect=record_class.decode,
    ):
        await async_deliver(owner_entry, raw)

    assert last_data(log_records)[ATTR_EVENT_TYPE] == event_type


@dataclass(frozen=True)
class _LaterRecord(LogRecord):
    """Stand in for a record class that a later version of the library adds and that has no event type here."""

    value: int

    @classmethod
    def decode(cls, raw: bytes) -> Self:
        """Build the record with byte 5 as its value."""
        return cls(raw, raw[4], value=raw[5])


async def test_a_record_class_with_no_type_fires_unknown_record_with_its_bytes(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A record of a class with no event type fires unknown_record with its decoded fields and its raw bytes."""
    with patch(
        "custom_components.yalexs_ble_activity.reader.parse_log_event_packet",
        side_effect=_LaterRecord.decode,
    ):
        await async_deliver(owner_entry, NO_DECODER)

    assert last_data(log_records) == {
        ATTR_EVENT_TYPE: "unknown_record",
        "backlog": False,
        "log_type": 0x11,
        "value": 0x78,
        "raw": NO_DECODER.hex(),
        "serial": 1,
        "device_id": activity_device(hass, loaded_entry).id,
    }


def test_event_types_lists_each_type_once_in_the_table_order() -> None:
    """EVENT_TYPES holds each type once, in the order of the types of one record of each type."""
    unity = next(model for model in LOCK_MODELS if model.key == "unity")

    # The replies' own times are out of order, so the types are read without the
    # reader's window.
    types = [
        activity_for(parse_log_event_packet(raw), unity).event_type
        for raw in ONE_REPLY_PER_TYPE
    ]

    assert types == list(EVENT_TYPES)
    assert len(set(EVENT_TYPES)) == len(EVENT_TYPES)


def test_translations_name_each_event_type_and_no_other() -> None:
    """The translations hold a state name for each event type and for no other, each the type's word in EVENT_TYPE_WORDS."""
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
    words = activity["state_attributes"]["event_type"]["state"]
    assert words.keys() == set(EVENT_TYPES)
    assert words == EVENT_TYPE_WORDS
