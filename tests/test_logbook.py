"""Tests for the Yale Access Bluetooth Activity logbook descriptions."""

from collections.abc import Callable
from typing import Any
from unittest.mock import ANY, Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yalexs_ble_activity.const import EVENT_LOG_RECORD, OWNER_DOMAIN
from custom_components.yalexs_ble_activity.logbook import async_describe_events
from homeassistant.components.logbook import DOMAIN as LOGBOOK_DOMAIN
from homeassistant.components.logbook.helpers import async_determine_event_types
from homeassistant.components.logbook.models import LogbookConfig
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    CODE_OPERATION_SLOT_1,
    TITLE,
    activity_device,
    async_deliver,
    async_setup_platform,
)


def _describer(hass: HomeAssistant) -> Callable[[Event], dict[str, Any]]:
    """Return the logbook's describer of the log record event."""
    describers: dict[tuple[str, str], Callable[[Event], dict[str, Any]]] = {}
    async_describe_events(
        hass,
        lambda domain, event_type, describe: describers.update(
            {(domain, event_type): describe}
        ),
    )
    return describers[OWNER_DOMAIN, EVENT_LOG_RECORD]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(
            {"event_type": "pin", "slot": 15, "name": "Guest"},
            "keypad code by Guest at slot 15",
            id="named_use",
        ),
        pytest.param(
            {"event_type": "pin", "slot": 1, "name": None},
            "keypad code at slot 1",
            id="unnamed_use",
        ),
        pytest.param(
            {"event_type": "code_added_v2", "slot": 4, "name": "Guest"},
            "code added for Guest at slot 4",
            id="named_add",
        ),
        pytest.param(
            {"event_type": "door_opened", "current_door_state": "opened"},
            "door opened",
            id="no_slot_no_name",
        ),
        pytest.param(
            {"event_type": "rf", "slot": 7, "name": None},
            "RF tag at slot 7",
            id="initialism",
        ),
        pytest.param(
            {"event_type": "master_code", "slot": 0xFFEE},
            "master code",
            id="master_code",
        ),
        pytest.param(
            {"event_type": "code_added_v2", "slot": 0xFFEE, "name": None},
            "code added at slot 0xFFEE",
            id="slot_in_hex",
        ),
        pytest.param({"event_type": "home_kit"}, "HomeKit", id="proper_name"),
        pytest.param({"event_type": "z_wave"}, "Z-Wave", id="proper_name_hyphen"),
    ],
)
async def test_the_logbook_describes_a_log_record_by_its_word_name_and_slot(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    data: dict[str, Any],
    message: str,
) -> None:
    """A log record is described under the integration's device's name by its type's word, its name, and its slot, with no entity."""
    device_id = activity_device(hass, loaded_entry).id

    description = _describer(hass)(
        Event(EVENT_LOG_RECORD, {**data, "device_id": device_id})
    )

    assert (description["name"], description["message"]) == (TITLE, message)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(
            {
                "event_type": "unlocked",
                "source": "rf",
                "slot": 7,
                "current_lock_state": "unlocked",
            },
            "unlocked (RF tag at slot 7)",
            id="rf",
        ),
        pytest.param(
            {
                "event_type": "secured",
                "source": "remote",
                "current_lock_state": "securemode",
            },
            "secured (remote)",
            id="securemode",
        ),
        pytest.param(
            {
                "event_type": "locked",
                "source": "auto_lock",
                "current_lock_state": "locked",
            },
            "locked (auto lock)",
            id="auto_lock",
        ),
        pytest.param(
            {
                "event_type": "unlocked",
                "source": "pin",
                "slot": 15,
                "name": "Guest",
                "current_lock_state": "unlocked",
            },
            "unlocked (keypad code by Guest at slot 15)",
            id="named_use",
        ),
        pytest.param(
            {
                "event_type": "locked",
                "source": "master_code",
                "slot": 0xFFEE,
                "current_lock_state": "locked",
            },
            "locked (master code)",
            id="master_code",
        ),
        pytest.param(
            {"event_type": "credential_error", "current_lock_state": None},
            "credential refused",
            id="refused_credential",
        ),
        pytest.param(
            {
                "event_type": "credential_added",
                "slot": 4,
                "name": "Guest",
                "current_lock_state": "locked",
            },
            "credential added for Guest at slot 4",
            id="add",
        ),
        pytest.param(
            {
                "event_type": "lock_state",
                "source": "rf",
                "slot": 7,
                "current_lock_state": "unknown_08",
            },
            "unknown_08 (RF tag at slot 7)",
            id="state_with_no_words",
        ),
    ],
)
async def test_the_logbook_line_of_a_record_with_a_source_leads_with_the_lock_state(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    data: dict[str, Any],
    message: str,
) -> None:
    """A log record with a source is described by its lock state's words, then the line of its source in parentheses, and a record with no source by its line alone."""
    device_id = activity_device(hass, loaded_entry).id

    description = _describer(hass)(
        Event(EVENT_LOG_RECORD, {**data, "device_id": device_id})
    )

    assert (description["name"], description["message"]) == (TITLE, message)


async def test_the_logbook_describes_a_fired_log_record_event(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """The log record event the reader fires for a named CodeOperation is described by its lock state, then its name and slot."""
    await async_setup_platform(
        hass, "keypad", async_credential_name=Mock(return_value="Guest")
    )

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    (event,) = log_records
    assert _describer(hass)(event) == {
        "name": TITLE,
        "message": "unlocked (keypad code by Guest at slot 1)",
        "icon": "mdi:lock-open-variant",
    }


async def test_the_logbook_names_the_line_after_the_integrations_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    loaded_entry: MockConfigEntry,
) -> None:
    """A line is named after the integration's device, the user's name for it once set, and the default for a device not in the registry."""
    describe = _describer(hass)
    device_id = activity_device(hass, loaded_entry).id
    data = {"event_type": "door_opened"}

    descriptions = [describe(Event(EVENT_LOG_RECORD, {**data, "device_id": device_id}))]
    device_registry.async_update_device(device_id, name_by_user="Porch")
    descriptions.append(
        describe(Event(EVENT_LOG_RECORD, {**data, "device_id": device_id}))
    )
    descriptions.append(
        describe(Event(EVENT_LOG_RECORD, {**data, "device_id": "removed"}))
    )

    assert [description["name"] for description in descriptions] == [
        TITLE,
        "Porch",
        "Yale Access Bluetooth lock",
    ]


@pytest.mark.parametrize(
    ("event_type", "icon"),
    [
        ("locked", "mdi:lock"),
        ("unlocked", "mdi:lock-open-variant"),
        ("secured", "mdi:shield-lock"),
        ("unlatched", "mdi:lock-open-variant"),
        ("jammed", "mdi:lock-alert"),
        ("lock_state", "mdi:lock-question"),
        ("credential_error", "mdi:key-alert"),
        ("door_opened", "mdi:door-open"),
        ("door_closed", "mdi:door-closed"),
        ("door_ajar", "mdi:door-open"),
        ("door_state_changed", "mdi:door"),
        ("code_added", "mdi:key-plus"),
        ("code_deleted", "mdi:key-minus"),
        ("code_added_v2", "mdi:key-plus"),
        ("code_deleted_v2", "mdi:key-minus"),
        ("credential_added", "mdi:key-plus"),
        ("credential_deleted", "mdi:key-minus"),
        ("keypad_open", "mdi:dialpad"),
        ("keypad_wrong_code", "mdi:key-alert"),
        ("keypad_close", "mdi:dialpad"),
        ("keypad_info", "mdi:dialpad"),
        ("all_codes_deleted", "mdi:key-remove"),
        ("factory_reset", "mdi:restore"),
        ("tamper", "mdi:alert-circle"),
        ("bcm_test", "mdi:test-tube"),
        ("dps_info", "mdi:information-outline"),
        ("battery_info", "mdi:battery"),
        ("local_event_notification", "mdi:bell-outline"),
        ("product_message", "mdi:message-text-outline"),
        ("matter_message", "mdi:message-text-outline"),
        ("dialog_reboot", "mdi:restart"),
        ("unknown_record", "mdi:help-circle-outline"),
        ("pin", None),
    ],
)
async def test_the_logbook_line_has_the_icon_of_its_event_type(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    event_type: str,
    icon: str | None,
) -> None:
    """Each event type has its icon, and an event type only an earlier release fired has none."""
    description = _describer(hass)(
        Event(
            EVENT_LOG_RECORD,
            {
                "event_type": event_type,
                "device_id": activity_device(hass, loaded_entry).id,
            },
        )
    )

    assert description == {"name": TITLE, "message": ANY} | (
        {} if icon is None else {"icon": icon}
    )


async def test_the_logbook_of_cores_lock_entity_keeps_the_log_record_event(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, core_lock: er.RegistryEntry
) -> None:
    """The logbook filtered to core's lock entity keeps the log record event, and the logbook of the integration's device does not."""
    external_events: dict[str, tuple[str, Callable[[Event], dict[str, Any]]]] = {}
    hass.data[LOGBOOK_DOMAIN] = LogbookConfig(external_events)

    # This mirrors the logbook's platform hook, which stores a described event under
    # its event type with its domain and describer.
    async_describe_events(
        hass,
        lambda domain, event_type, describe: external_events.update(
            {event_type: (domain, describe)}
        ),
    )

    assert EVENT_LOG_RECORD in async_determine_event_types(
        hass, [core_lock.entity_id], None
    )
    assert EVENT_LOG_RECORD not in async_determine_event_types(
        hass, None, [activity_device(hass, loaded_entry).id]
    )
