"""Describe Yale Access Bluetooth Activity logbook events."""

from collections.abc import Callable

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_CURRENT_LOCK_STATE,
    ATTR_NAME,
    ATTR_SLOT,
    ATTR_SOURCE,
    EVENT_LOG_RECORD,
    EVENT_TYPE_CODE_ADDED,
    EVENT_TYPE_CODE_ADDED_V2,
    EVENT_TYPE_CODE_DELETED,
    EVENT_TYPE_CODE_DELETED_V2,
    EVENT_TYPE_CREDENTIAL_ADDED,
    EVENT_TYPE_CREDENTIAL_DELETED,
    EVENT_TYPE_WORDS,
    LOCK_STATE_WORDS,
    OWNER_DOMAIN,
    SOURCE_MASTER_CODE,
)

DEFAULT_NAME = "Yale Access Bluetooth lock"

ADD_OR_DELETE_EVENT_TYPES = frozenset(
    {
        EVENT_TYPE_CODE_ADDED,
        EVENT_TYPE_CODE_DELETED,
        EVENT_TYPE_CODE_ADDED_V2,
        EVENT_TYPE_CODE_DELETED_V2,
        EVENT_TYPE_CREDENTIAL_ADDED,
        EVENT_TYPE_CREDENTIAL_DELETED,
    }
)


def _slot_text(slot: int) -> str:
    """Return the slot in decimal, or in hex above 0xFF."""
    return f"0x{slot:X}" if slot > 0xFF else str(slot)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe logbook events."""
    device_registry = dr.async_get(hass)

    @callback
    def async_describe_log_record(event: Event) -> dict[str, str]:
        """Describe a log record under the name of the integration's device."""
        data = event.data
        device = device_registry.async_get(data[ATTR_DEVICE_ID])
        device_name = (device.name_by_user or device.name) if device else None
        event_type = data[ATTR_EVENT_TYPE]
        source = data.get(ATTR_SOURCE)
        words_key = source or event_type
        message = EVENT_TYPE_WORDS.get(words_key, words_key)
        if (name := data.get(ATTR_NAME)) is not None:
            preposition = "for" if event_type in ADD_OR_DELETE_EVENT_TYPES else "by"
            message = f"{message} {preposition} {name}"
        # The master code's slot is the lock model's, not a user's.
        if (
            slot := data.get(ATTR_SLOT)
        ) is not None and words_key != SOURCE_MASTER_CODE:
            message = f"{message} at slot {_slot_text(slot)}"
        if source is not None:
            state = data[ATTR_CURRENT_LOCK_STATE]
            message = f"{LOCK_STATE_WORDS.get(state, state)} ({message})"
        return {
            LOGBOOK_ENTRY_NAME: device_name or DEFAULT_NAME,
            LOGBOOK_ENTRY_MESSAGE: message,
        }

    # The logbook returns this event for the lock's entities only when it is described
    # under the domain of their config entry.
    async_describe_event(OWNER_DOMAIN, EVENT_LOG_RECORD, async_describe_log_record)
