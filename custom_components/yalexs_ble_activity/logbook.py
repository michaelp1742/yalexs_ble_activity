"""Describe Yale Access Bluetooth Activity logbook events."""

from collections.abc import Callable

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.translation import async_get_cached_translations

from .const import (
    ATTR_NAME,
    ATTR_SLOT,
    DOMAIN,
    EVENT_CREDENTIAL_ACTIVITY,
    EVENT_TYPE_CODE_ADDED,
    EVENT_TYPE_CODE_ADDED_V2,
    EVENT_TYPE_CODE_DELETED,
    EVENT_TYPE_CODE_DELETED_V2,
    EVENT_TYPE_CREDENTIAL_ADDED,
    EVENT_TYPE_CREDENTIAL_DELETED,
    OWNER_DOMAIN,
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


def _word(hass: HomeAssistant, event_type: str) -> str:
    """Return the event type's translated word with its first letter in lower case, unless its first word is an initialism."""
    words = async_get_cached_translations(hass, hass.config.language, "entity", DOMAIN)
    word = words.get(
        f"component.{DOMAIN}.entity.event.activity.state_attributes.event_type.state.{event_type}",
        event_type,
    )
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
    def async_describe_credential_activity(event: Event) -> dict[str, str]:
        """Describe a credential record under the name of the lock's device."""
        data = event.data
        device = (
            device_registry.async_get(device_id)
            if (device_id := data[ATTR_DEVICE_ID])
            else None
        )
        lock_name = (device.name_by_user or device.name) if device else None
        event_type = data[ATTR_EVENT_TYPE]
        message = _word(hass, event_type)
        if (name := data[ATTR_NAME]) is not None:
            preposition = "for" if event_type in ADD_OR_DELETE_EVENT_TYPES else "by"
            message = f"{message} {preposition} {name}"
        return {
            LOGBOOK_ENTRY_NAME: lock_name or DEFAULT_NAME,
            LOGBOOK_ENTRY_MESSAGE: f"{message} at slot {data[ATTR_SLOT]}",
            LOGBOOK_ENTRY_ENTITY_ID: data[ATTR_ENTITY_ID],
        }

    # Described under yalexs_ble, since the logbook of an entity or device keeps only
    # the events of its config entries' domains, and the lock is yalexs_ble's.
    async_describe_event(
        OWNER_DOMAIN, EVENT_CREDENTIAL_ACTIVITY, async_describe_credential_activity
    )
