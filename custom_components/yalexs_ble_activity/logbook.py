"""Describe Yale Access Bluetooth Activity logbook events."""

from collections.abc import Callable

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_NAME,
    ATTR_SLOT,
    DOMAIN,
    EVENT_LOG_RECORD,
    EVENT_TYPE_CODE_ADDED,
    EVENT_TYPE_CODE_ADDED_V2,
    EVENT_TYPE_CODE_DELETED,
    EVENT_TYPE_CODE_DELETED_V2,
    EVENT_TYPE_CREDENTIAL_ADDED,
    EVENT_TYPE_CREDENTIAL_DELETED,
    EVENT_TYPE_WORDS,
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


def _word(event_type: str) -> str:
    """Return the event type's word with its first letter in lower case, unless its first word is an initialism."""
    word = EVENT_TYPE_WORDS.get(event_type, event_type)
    if word.split()[0].isupper():
        return word
    return word[0].lower() + word[1:]


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
        message = _word(event_type)
        if (name := data.get(ATTR_NAME)) is not None:
            preposition = "for" if event_type in ADD_OR_DELETE_EVENT_TYPES else "by"
            message = f"{message} {preposition} {name}"
        if (slot := data.get(ATTR_SLOT)) is not None:
            message = f"{message} at slot {slot}"
        return {
            LOGBOOK_ENTRY_NAME: device_name or DEFAULT_NAME,
            LOGBOOK_ENTRY_MESSAGE: message,
        }

    async_describe_event(DOMAIN, EVENT_LOG_RECORD, async_describe_log_record)
