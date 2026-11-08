"""The activity event entity of the Yale Access Bluetooth Activity integration."""

from typing import TYPE_CHECKING, override

from yalexs_ble import GetLogError, PushLock, parse_log_event_packet

from homeassistant.components.event import ATTR_EVENT_TYPE, EventEntity
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, CONF_ADDRESS
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.start import async_at_started

from . import YaleXSBLEActivityConfigEntry
from .activity import activity_for, attributes_for, credential_name
from .const import (
    ATTR_BACKLOG,
    ATTR_CREDENTIAL_TYPE,
    ATTR_NAME,
    ATTR_RAW,
    ATTR_SLOT,
    CONF_LOCK_MODEL,
    EVENT_CREDENTIAL_ACTIVITY,
    EVENT_TYPE_UNKNOWN_RECORD,
    EVENT_TYPES,
    OWNER_DOMAIN,
)
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
        self._held: list[tuple[bytes, bool]] | None = []
        self._core_lock: tuple[str | None, str | None] | None = None
        self._attr_unique_id = f"{address}_activity"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, lock.address)}, name=title
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Register the activity log reader."""
        await super().async_added_to_hass()
        self.async_on_remove(async_at_started(self.hass, self._async_started))
        self.async_on_remove(
            self._lock.register_log_record_callback(self._async_log_record)
        )

    @callback
    def _async_started(self, hass: HomeAssistant) -> None:
        """Fire the records held until Home Assistant started, in the order read."""
        held, self._held = self._held, None
        if TYPE_CHECKING:
            assert held is not None
        for raw, backlog in held:
            self._async_fire(raw, backlog)

    async def _async_log_record(self, raw: bytes, backlog: bool) -> None:
        """Fire the record's event, or hold it until Home Assistant has started."""
        if self._held is not None:
            # The credential integrations' entries and this one load in any order, so
            # a record read while Home Assistant starts waits until every entry loaded
            # at the start can name it.
            self._held.append((raw, backlog))
            return
        self._async_fire(raw, backlog)

    @callback
    def _async_fire(self, raw: bytes, backlog: bool) -> None:
        """Fire the record's event, and none for a GetLogError."""
        record = parse_log_event_packet(raw)
        if isinstance(record, GetLogError):
            return
        activity = activity_for(record, self._model)
        attributes = attributes_for(record, backlog)
        # Each record is written under a context of its own, since an entity writes
        # under a set context for CONTEXT_RECENT_TIME_SECONDS and the next record's
        # write must not take this one.
        context = Context()
        if activity.credential_type is not None:
            if TYPE_CHECKING:
                assert activity.slot is not None
            name = attributes[ATTR_NAME] = credential_name(
                self.hass, self._address, activity.credential_type, activity.slot
            )
            entity_id, device_id = self._async_core_lock()
            # Fired before the write under the same context, so the logbook finds this
            # event first under the context and shows it as the write's cause.
            self.hass.bus.async_fire(
                EVENT_CREDENTIAL_ACTIVITY,
                {
                    ATTR_DEVICE_ID: device_id,
                    ATTR_ENTITY_ID: entity_id,
                    ATTR_EVENT_TYPE: activity.event_type,
                    ATTR_CREDENTIAL_TYPE: activity.credential_type.name.lower(),
                    ATTR_SLOT: activity.slot,
                    ATTR_NAME: name,
                    ATTR_BACKLOG: backlog,
                },
                context=context,
            )
        if activity.event_type == EVENT_TYPE_UNKNOWN_RECORD:
            attributes[ATTR_RAW] = raw.hex()
        self.async_set_context(context)
        self._trigger_event(activity.event_type, attributes)
        self.async_write_ha_state()

    @callback
    def _async_core_lock(self) -> tuple[str | None, str | None]:
        """Return core's lock entity and its device, read at the first credential record."""
        if self._core_lock is None:
            registry = er.async_get(self.hass)
            entity_id = registry.async_get_entity_id(
                LOCK_DOMAIN, OWNER_DOMAIN, self._lock.address
            )
            lock = registry.async_get(entity_id) if entity_id else None
            self._core_lock = (entity_id, lock.device_id if lock else None)
        return self._core_lock
