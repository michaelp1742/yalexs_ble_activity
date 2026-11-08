"""The activity event entity of the Yale Access Bluetooth Activity integration."""

from typing import TYPE_CHECKING, Any, override

from homeassistant.components.event import EventEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YaleXSBLEActivityConfigEntry
from .const import EVENT_TYPES
from .reader import LogReader


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YaleXSBLEActivityConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the activity event entity."""
    if TYPE_CHECKING:
        assert entry.runtime_data is not None
    async_add_entities(
        [YaleXSBLEActivityEvent(entry.data[CONF_ADDRESS], entry.runtime_data)]
    )


class YaleXSBLEActivityEvent(EventEntity):
    """The event entity that the entry's reader triggers for each record it fires."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "activity"
    _attr_event_types = list(EVENT_TYPES)
    _attr_entity_registry_enabled_default = False

    def __init__(self, address: str, reader: LogReader) -> None:
        """Initialize the event entity on the integration's device."""
        self._reader = reader
        self._attr_unique_id = f"{address}_activity"
        self._attr_device_info = DeviceInfo(connections=reader.device.connections)

    @override
    async def async_added_to_hass(self) -> None:
        """Attach the entity to the entry's reader."""
        await super().async_added_to_hass()
        self.async_on_remove(self._reader.async_attach(self))

    @callback
    def async_record(
        self, event_type: str, data: dict[str, Any], context: Context
    ) -> None:
        """Trigger an entity event with a fired record's data, under its log record event's context."""
        self.async_set_context(context)
        self._trigger_event(event_type, data)
        self.async_write_ha_state()
