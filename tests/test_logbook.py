"""Tests for the Yale Access Bluetooth Activity logbook descriptions."""

from collections.abc import Callable
from typing import Any

import pytest

from custom_components.yalexs_ble_activity.const import (
    EVENT_CREDENTIAL_ACTIVITY,
    OWNER_DOMAIN,
)
from custom_components.yalexs_ble_activity.logbook import async_describe_events
from homeassistant.components.logbook import DOMAIN as LOGBOOK_DOMAIN
from homeassistant.components.logbook.helpers import async_determine_event_types
from homeassistant.components.logbook.models import LogbookConfig
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import TITLE


def _describer(hass: HomeAssistant) -> Callable[[Event], dict[str, Any]]:
    """Return the logbook's describer of the credential event."""
    describers: dict[tuple[str, str], Callable[[Event], dict[str, Any]]] = {}
    async_describe_events(
        hass,
        lambda domain, event_type, describe: describers.update(
            {(domain, event_type): describe}
        ),
    )
    return describers[OWNER_DOMAIN, EVENT_CREDENTIAL_ACTIVITY]


def _event(
    core_lock: er.RegistryEntry | None,
    event_type: str = "pin",
    credential_type: str = "pin",
    slot: int = 15,
    name: str | None = "Guest",
) -> Event:
    """Return a credential event of core's lock, or of no lock."""
    return Event(
        EVENT_CREDENTIAL_ACTIVITY,
        {
            "device_id": core_lock.device_id if core_lock else None,
            "entity_id": core_lock.entity_id if core_lock else None,
            "event_type": event_type,
            "credential_type": credential_type,
            "slot": slot,
            "name": name,
            "backlog": False,
        },
    )


@pytest.mark.parametrize(
    ("event_type", "credential_type", "slot", "name", "message"),
    [
        pytest.param(
            "pin", "pin", 15, "Guest", "keypad code by Guest at slot 15", id="named"
        ),
        pytest.param("pin", "pin", 1, None, "keypad code at slot 1", id="unnamed"),
        pytest.param(
            "code_added_v2",
            "pin",
            4,
            "Guest",
            "code added (v2) for Guest at slot 4",
            id="added",
        ),
        pytest.param("rf", "rf", 7, "Tag", "RF tag by Tag at slot 7", id="initialism"),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_the_logbook_describes_a_credential_record_by_its_word_and_name(
    hass: HomeAssistant,
    core_lock: er.RegistryEntry,
    event_type: str,
    credential_type: str,
    slot: int,
    name: str | None,
    message: str,
) -> None:
    """The logbook describes a credential record under the lock device's name, by its type's word, its name, and its slot."""
    description = _describer(hass)(
        _event(core_lock, event_type, credential_type, slot, name)
    )

    assert description == {
        "name": TITLE,
        "message": message,
        "entity_id": core_lock.entity_id,
    }


@pytest.mark.usefixtures("loaded_entry")
async def test_the_logbook_names_the_entry_after_the_lock_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    core_lock: er.RegistryEntry,
) -> None:
    """The entry's name is the lock device's name, the user's name for it once set, and the default with no lock."""
    describe = _describer(hass)

    names = [describe(_event(core_lock))["name"]]
    device_registry.async_update_device(core_lock.device_id, name_by_user="Porch")
    names.append(describe(_event(core_lock))["name"])
    names.append(describe(_event(None))["name"])

    assert names == [TITLE, "Porch", "Yale Access Bluetooth lock"]
    assert describe(_event(None))["entity_id"] is None


async def test_the_logbook_of_the_lock_and_its_device_keeps_the_event(
    hass: HomeAssistant, core_lock: er.RegistryEntry
) -> None:
    """The logbook filtered to core's lock entity, or to its device, keeps the credential event."""
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

    assert EVENT_CREDENTIAL_ACTIVITY in async_determine_event_types(
        hass, [core_lock.entity_id], None
    )
    assert EVENT_CREDENTIAL_ACTIVITY in async_determine_event_types(
        hass, None, [core_lock.device_id]
    )
