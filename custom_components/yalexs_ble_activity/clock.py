"""The lock's clock, kept in step with Home Assistant's."""

from collections.abc import Coroutine
import logging
import time
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError
from yalexs_ble import GetLogError, PushLock, StatusType, YaleXSBLEError

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

if TYPE_CHECKING:
    from . import YaleXSBLEActivityConfigEntry

_LOGGER = logging.getLogger(__name__)

# The failures a status poll or a clock write raises. The library warns of a command
# that fails, so the clock logs at debug.
CLOCK_ERRORS = (TimeoutError, RuntimeError, YaleXSBLEError, BleakError)

# A clock found more than this many seconds off is set to Home Assistant's time.
SET_LIMIT = 10
# A sample at least this many seconds off moves the clock one second toward
# Home Assistant's time.
STEP_LIMIT = 2
# With no sample for this long, the clock is read.
QUIET_TIME = 6 * 3600


class LockClock:
    """Read the lock's clock and move it toward Home Assistant's time."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: YaleXSBLEActivityConfigEntry,
        lock: PushLock,
    ) -> None:
        """Initialize the clock of one entry's lock."""
        self._hass = hass
        self._entry = entry
        self._lock = lock
        self._record_read = False
        self._cancel_quiet: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Read the lock's clock and set it to Home Assistant's time when it is more than SET_LIMIT off."""
        offset = await self._async_read()
        if offset is not None and abs(offset) > SET_LIMIT:
            await self._async_write(offset, 0)
        self._async_wait_quiet()

    @callback
    def async_stop(self) -> None:
        """Cancel the read of a quiet lock."""
        if self._cancel_quiet is not None:
            self._cancel_quiet()
            self._cancel_quiet = None

    @callback
    def async_record_read(self) -> None:
        """Note a record read, so the GetLogError that ends its drain is a sample."""
        self._record_read = True

    @callback
    def async_sample(self, record: GetLogError) -> None:
        """Take the GetLogError ending a drain that read a record as a sample of the lock's clock."""
        if record.dirty_bit:
            # A GetLogError with the dirty bit set answers a GetLog that raced a
            # record's write, and the drain reads on.
            return
        if not self._record_read:
            # After a drain that read nothing, dirty_bit_cleared_time may hold the
            # time of an earlier read.
            return
        self._record_read = False
        self._async_correct(record.dirty_bit_cleared_time - int(time.time()))

    @callback
    def _async_correct(self, offset: int) -> None:
        """Correct the lock's clock for a sample offset seconds off, as a task."""
        self._async_wait_quiet()
        if abs(offset) > SET_LIMIT:
            self._async_create_task(self._async_write(offset, 0))
        elif abs(offset) >= STEP_LIMIT:
            self._async_create_task(
                self._async_write(offset, offset - (1 if offset > 0 else -1))
            )

    @callback
    def _async_wait_quiet(self) -> None:
        """Read the clock QUIET_TIME from now, unless a sample comes first."""
        self.async_stop()
        self._cancel_quiet = async_call_later(self._hass, QUIET_TIME, self._async_quiet)

    @callback
    def _async_quiet(self, _now: Any) -> None:
        """Read the clock of a lock with no sample for QUIET_TIME, as a sample."""
        self._cancel_quiet = None
        self._async_create_task(self._async_read_sample())

    async def _async_read_sample(self) -> None:
        """Read the lock's clock and correct it."""
        if (offset := await self._async_read()) is not None:
            self._async_correct(offset)
        else:
            self._async_wait_quiet()

    @callback
    def _async_create_task(self, target: Coroutine[Any, Any, None]) -> None:
        """Run a read or a write of the clock as a task of the entry's."""
        self._entry.async_create_background_task(
            self._hass, target, f"{self._entry.title} clock"
        )

    async def _async_read(self) -> int | None:
        """Return how many seconds the lock's clock is ahead of Home Assistant's, or None when the read fails."""
        try:
            lock_time = await self._lock.get_status(StatusType.RTC)
        except CLOCK_ERRORS as err:
            _LOGGER.debug("%s clock not read: %s", self._entry.title, err)
            return None
        return lock_time - int(time.time())

    async def _async_write(self, offset: int, new_offset: int) -> None:
        """Set the lock's clock new_offset seconds from Home Assistant's, for a lock offset seconds off."""
        try:
            await self._lock.set_rtc(int(time.time()) + new_offset)
        except CLOCK_ERRORS as err:
            _LOGGER.debug("%s clock not set: %s", self._entry.title, err)
            return
        found = f"{abs(offset)} s {'ahead' if offset > 0 else 'behind'}"
        if new_offset == 0:
            _LOGGER.info(
                "%s clock %s; set to Home Assistant's time", self._entry.title, found
            )
        else:
            _LOGGER.info(
                "%s clock %s; moved 1 s toward Home Assistant's time",
                self._entry.title,
                found,
            )
