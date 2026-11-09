"""The lock's clock, kept in step with Home Assistant's."""

import asyncio
from collections.abc import Coroutine
import logging
import math
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
# Home Assistant's time. A sample is within 0.5 s of the lock's offset, so a clock
# less than 1 s off is never moved.
STEP_LIMIT = 1.5
# The lock's clock reads in whole seconds, truncated; a sample takes the middle of
# the second.
HALF_SECOND = 0.5
# The time from a set_rtc call to the moment the lock applies it, used until a
# write has measured one: half the 0.6 s call-to-reply time of the 2026-11-09
# field test.
FIRST_WRITE_DELAY = 0.3
# With no sample for this long, the clock is read.
QUIET_TIME = 6 * 3600


def _toward_zero(offset: float) -> int:
    """Return the offset rounded to the whole second, one second nearer zero."""
    seconds = math.floor(abs(offset) + 0.5) - 1
    return seconds if offset > 0 else -seconds


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
        self._record_read_time: float | None = None
        self._write_delay = FIRST_WRITE_DELAY
        self._writing = False
        self._write_reply_time: float | None = None
        self._cancel_quiet: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Read the lock's clock and set it to Home Assistant's time when it is more than SET_LIMIT off."""
        if (read := await self._async_read()) is not None and abs(read[0]) > SET_LIMIT:
            self._writing = True
            await self._async_write(read[0], 0)
        self._async_wait_quiet()

    @callback
    def async_stop(self) -> None:
        """Cancel the read of a quiet lock."""
        if self._cancel_quiet is not None:
            self._cancel_quiet()
            self._cancel_quiet = None

    @callback
    def async_record_read(self, read_time: float) -> None:
        """Note when a record's reply arrived, so the GetLogError that ends its drain is a sample."""
        self._record_read_time = read_time

    @callback
    def async_sample(self, record: GetLogError) -> None:
        """Take the GetLogError ending a drain that read a record as a sample of the lock's clock."""
        if record.dirty_bit:
            # A GetLogError with the dirty bit set answers a GetLog that raced a
            # record's write, and the drain reads on.
            return
        if (read_time := self._record_read_time) is None:
            # After a drain that read nothing, the lock repeats the previous
            # GetLogError's times, those of an earlier read.
            return
        self._record_read_time = None
        # dirty_bit_cleared_time is the lock's time at the read that emptied the log,
        # the drain's last record.
        self._async_correct(
            record.dirty_bit_cleared_time + HALF_SECOND - read_time, read_time
        )

    @callback
    def _async_correct(self, offset: float, read_time: float) -> bool:
        """Correct the lock's clock for a sample offset seconds off, read at read_time, as a task; return False when the read is no sample."""
        if self._writing or (
            self._write_reply_time is not None and read_time < self._write_reply_time
        ):
            # The write sets the clock after the read sampled it.
            return False
        self._async_wait_quiet()
        if abs(offset) > SET_LIMIT:
            new_offset = 0
        elif abs(offset) >= STEP_LIMIT:
            new_offset = _toward_zero(offset)
        else:
            return True
        self._writing = True
        self._async_create_task(self._async_write(offset, new_offset))
        return True

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
        if (read := await self._async_read()) is None or not self._async_correct(*read):
            self._async_wait_quiet()

    @callback
    def _async_create_task(self, target: Coroutine[Any, Any, None]) -> None:
        """Run a read or a write of the clock as a task of the entry's."""
        self._entry.async_create_background_task(
            self._hass, target, f"{self._entry.title} clock"
        )

    async def _async_read(self) -> tuple[float, float] | None:
        """Return how many seconds the lock's clock is ahead of Home Assistant's and when the reply arrived, or None when the read fails."""
        try:
            lock_time = await self._lock.get_status(StatusType.RTC)
        except CLOCK_ERRORS as err:
            _LOGGER.debug("%s clock not read: %s", self._entry.title, err)
            return None
        read_time = time.time()
        return lock_time + HALF_SECOND - read_time, read_time

    async def _async_write(self, offset: float, new_offset: int) -> None:
        """Set the lock's clock new_offset seconds from Home Assistant's, timed so the lock applies it on a whole second, and log the offset found."""
        applied = math.ceil(time.time() + self._write_delay)
        await asyncio.sleep(applied - self._write_delay - time.time())
        called = time.time()
        try:
            await self._lock.set_rtc(applied + new_offset)
        except CLOCK_ERRORS as err:
            _LOGGER.debug("%s clock not set: %s", self._entry.title, err)
            return
        finally:
            self._writing = False
        self._write_reply_time = time.time()
        # The lock applies the value about half the call-to-reply time after the call.
        self._write_delay = (self._write_reply_time - called) / 2
        found = f"{abs(offset):.1f} s {'ahead' if offset > 0 else 'behind'}"
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
