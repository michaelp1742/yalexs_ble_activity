"""The log reader of the Yale Access Bluetooth Activity integration."""

from collections.abc import Callable
import logging
import time
from typing import TYPE_CHECKING, TypedDict

from yalexs_ble import GetLogError, LogRecord, parse_log_event_packet

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import ATTR_DEVICE_ID, CONF_ADDRESS
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .activity import activity_for, attributes_for, credential_name
from .clock import LockClock
from .const import (
    ATTR_NAME,
    ATTR_RAW,
    ATTR_SERIAL,
    CONF_LOCK_MODEL,
    DOMAIN,
    EVENT_LOG_RECORD,
    EVENT_TYPE_UNKNOWN_RECORD,
)
from .models import LOCK_MODELS

if TYPE_CHECKING:
    from . import YaleXSBLEActivityConfigEntry
    from .event import YaleXSBLEActivityEvent

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 1

# A record further ahead of Home Assistant's time than this is discarded.
AHEAD_LIMIT = 10
# The earliest time on a lock's first read is this long before the entry's setup.
FIRST_READ_SPAN = 86400
# A line in the same second as the previous line is placed this long after it.
LINE_STEP = 0.001


class _StoredLine(TypedDict):
    """The entry's store: the earliest time, the last line's time, and the serial of the last record fired."""

    earliest_time: float
    last_line_time: float | None
    serial: int


def store_for(hass: HomeAssistant, entry_id: str) -> Store[_StoredLine]:
    """Return the store of the entry with entry_id."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


class LogReader:
    """Fire one log record event for each record of the lock's log, at the record's own time."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: YaleXSBLEActivityConfigEntry,
        device: DeviceEntry,
        clock: LockClock,
    ) -> None:
        """Initialize the reader of one entry's lock."""
        self._hass = hass
        self._title = entry.title
        self._address: str = entry.data[CONF_ADDRESS]
        models = {model.key: model for model in LOCK_MODELS}
        # A stored key that no row has, such as one a later release removed, takes the
        # row for any other lock.
        self._model = models.get(entry.options[CONF_LOCK_MODEL], models["other"])
        self.device = device
        self._clock = clock
        self._store = store_for(hass, entry.entry_id)
        self._held: list[tuple[LogRecord, bool, float]] | None = []
        self._entity: YaleXSBLEActivityEvent | None = None
        self._line: _StoredLine = {
            "earliest_time": time.time() - FIRST_READ_SPAN,
            "last_line_time": None,
            "serial": 0,
        }
        self._unsaved = False

    async def async_load(self) -> None:
        """Read the earliest time, the last line's time, and the serial number from the store."""
        if (stored := await self._store.async_load()) is not None:
            self._line = stored

    async def async_save(self) -> None:
        """Write the store now when a record fired since the last write, in place of the delayed save."""
        if self._unsaved:
            self._unsaved = False
            await self._store.async_save(self._line)

    @callback
    def _async_line_saved(self) -> _StoredLine:
        """Return the store's data for the delayed save."""
        self._unsaved = False
        return self._line

    @callback
    def async_attach(self, entity: YaleXSBLEActivityEvent) -> Callable[[], None]:
        """Trigger entity for each fired record; return its remover."""
        self._entity = entity

        @callback
        def _async_detach() -> None:
            self._entity = None

        return _async_detach

    @callback
    def async_started(self, hass: HomeAssistant) -> None:
        """Fire the records held until Home Assistant started, in the order read."""
        held, self._held = self._held, None
        if TYPE_CHECKING:
            assert held is not None
        for record, backlog, read_time in held:
            self._async_fire(record, backlog, read_time)

    async def async_log_record(self, raw: bytes, backlog: bool) -> None:
        """Fire the record's log record event, or hold it until Home Assistant has started; give a GetLogError to the clock."""
        record = parse_log_event_packet(raw)
        if isinstance(record, GetLogError):
            self._clock.async_sample(record)
            return
        self._clock.async_record_read()
        if self._held is not None:
            # The credential integrations' entries and this one load in any order, so
            # a record read while Home Assistant starts waits until every entry loaded
            # at the start can name it.
            self._held.append((record, backlog, time.time()))
            return
        self._async_fire(record, backlog, time.time())

    @callback
    def _async_line_time(self, record: LogRecord, read_time: float) -> float | None:
        """Return the time of the record's line, or None for a record outside the window."""
        line = self._line
        last_line_time = line["last_line_time"]
        own_time: int | None = getattr(record, "time_stamp", None)
        if own_time is None:
            return read_time if last_line_time is None else last_line_time + LINE_STEP
        if own_time < line["earliest_time"] or own_time > read_time + AHEAD_LIMIT:
            _LOGGER.debug(
                "%s: discarded %s at %s, outside the window from %s to %s",
                self._title,
                type(record).__name__,
                dt_util.utc_from_timestamp(own_time).isoformat(),
                dt_util.utc_from_timestamp(line["earliest_time"]).isoformat(),
                dt_util.utc_from_timestamp(read_time + AHEAD_LIMIT).isoformat(),
            )
            return None
        line["earliest_time"] = own_time
        if last_line_time is None:
            return own_time
        return max(own_time, last_line_time + LINE_STEP)

    @callback
    def _async_fire(self, record: LogRecord, backlog: bool, read_time: float) -> None:
        """Fire the record's log record event at its line's time, and its entity event."""
        if (line_time := self._async_line_time(record, read_time)) is None:
            return
        activity = activity_for(record, self._model)
        data = attributes_for(record, backlog)
        if activity.credential_type is not None:
            if TYPE_CHECKING:
                assert activity.slot is not None
            data[ATTR_NAME] = credential_name(
                self._hass, self._address, activity.credential_type, activity.slot
            )
        if activity.event_type == EVENT_TYPE_UNKNOWN_RECORD:
            data[ATTR_RAW] = record.raw.hex()
        self._line["last_line_time"] = line_time
        self._line["serial"] += 1
        data[ATTR_SERIAL] = self._line["serial"]
        data[ATTR_EVENT_TYPE] = activity.event_type
        context = Context()
        self._hass.bus.async_fire(
            EVENT_LOG_RECORD,
            {**data, ATTR_DEVICE_ID: self.device.id},
            context=context,
            time_fired=line_time,
        )
        if self._entity is not None:
            self._entity.async_record(activity.event_type, data, context)
        self._unsaved = True
        self._store.async_delay_save(self._async_line_saved, SAVE_DELAY)
