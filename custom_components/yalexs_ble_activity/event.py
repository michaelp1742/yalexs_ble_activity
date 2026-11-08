"""The activity event entity of the Yale Access Bluetooth Activity integration."""

from typing import TYPE_CHECKING, override

from yalexs_ble import GetLogError, PushLock, parse_log_event_packet

from homeassistant.components.event import EventEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YaleXSBLEActivityConfigEntry
from .activity import activity_for, attributes_for, credential_name
from .const import ATTR_NAME, CONF_LOCK_MODEL, EVENT_TYPES
from .models import LOCK_MODELS, LockModel


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YaleXSBLEActivityConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the activity event entity."""
    if TYPE_CHECKING:
        assert entry.runtime_data is not None
    models = {model.key: model for model in LOCK_MODELS}
    # A stored key that no row has, such as one a later release removed, takes the
    # row for any other lock.
    model = models.get(entry.options[CONF_LOCK_MODEL], models["other"])
    async_add_entities(
        [
            YaleXSBLEActivityEvent(
                entry.data[CONF_ADDRESS], entry.title, entry.runtime_data, model
            )
        ]
    )


class YaleXSBLEActivityEvent(EventEntity):
    """The event entity that fires one event for each record of the lock's activity log."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "activity"
    _attr_event_types = list(EVENT_TYPES)

    def __init__(
        self, address: str, title: str, lock: PushLock, model: LockModel
    ) -> None:
        """Initialize the event entity."""
        self._address = address
        self._lock = lock
        self._model = model
        self._attr_unique_id = f"{address}_activity"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, lock.address)}, name=title
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Register the activity log reader."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._lock.register_log_record_callback(self._async_log_record)
        )

    async def _async_log_record(self, raw: bytes, backlog: bool) -> None:
        """Fire the record's event, and none for a GetLogError."""
        record = parse_log_event_packet(raw)
        if isinstance(record, GetLogError):
            return
        activity = activity_for(record, self._model)
        attributes = attributes_for(record, backlog)
        if activity.credential_type is not None:
            if TYPE_CHECKING:
                assert activity.slot is not None
            attributes[ATTR_NAME] = credential_name(
                self.hass, self._address, activity.credential_type, activity.slot
            )
        self._trigger_event(activity.event_type, attributes)
        self.async_write_ha_state()
