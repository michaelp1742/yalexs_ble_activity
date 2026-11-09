"""The lock's clock, kept in step with Home Assistant's."""

from collections.abc import Coroutine
import logging
from typing import TYPE_CHECKING, Any, NamedTuple

from bleak.exc import BleakError
from yalexs_ble import (
    ExchangeTimes,
    GetLogError,
    PushLock,
    StatusReply,
    StatusType,
    YaleXSBLEError,
)

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

if TYPE_CHECKING:
    from . import YaleXSBLEActivityConfigEntry

_LOGGER = logging.getLogger(__name__)

# The failures a status poll or a clock write raises. The library warns of a command
# that fails, so the clock logs at debug.
CLOCK_ERRORS = (TimeoutError, RuntimeError, YaleXSBLEError, BleakError)

# A clock whose whole window lies more than this many seconds off is set in one
# write.
SET_LIMIT = 10
# A reading whose reply came longer than this many seconds after its request is no
# sample: its window is 1 s plus the round trip wide. In testing the round trip
# was 0.23 to 0.68 s, and 0.4 s kept 65 of 68 readings.
MAX_SAMPLE_ROUND_TRIP = 0.4
# With no sample for this long, the clock is read.
QUIET_TIME = 6 * 3600


class Window(NamedTuple):
    """The lock's clock less Home Assistant's lies above low and at or below high."""

    low: float
    high: float

    def describe(self) -> str:
        """Return the window in words, to a tenth of a second."""
        side = "ahead" if self.low >= 0 else "behind"
        return f"{abs(self.low):.1f} to {abs(self.high):.1f} s {side}"


def _sample_window(lock_time: int, times: ExchangeTimes) -> Window | None:
    """Return the window of a reading of the lock's second lock_time, or None when its reply was too slow."""
    if times.reply_received - times.request_written > MAX_SAMPLE_ROUND_TRIP:
        return None
    # The lock read its clock between the request's write and its reply.
    return Window(
        lock_time - times.reply_received, lock_time + 1 - times.request_written
    )


def _set_offset(window: Window) -> float | None:
    """Return the offset a clock whose whole window lies more than SET_LIMIT off is set to, or None."""
    if window.high < -SET_LIMIT:
        return 0.0
    if window.low > SET_LIMIT:
        # A write lands late, so a lock ahead is aimed short of zero to stay ahead.
        return MAX_SAMPLE_ROUND_TRIP
    return None


def _step_offset(window: Window) -> float | None:
    """Return the offset that moves the clock up to 1 s toward Home Assistant's time without crossing it, or None."""
    if window.high <= 0 and window.low + 1 <= 0:
        return window.low + 1
    if window.low >= 0 and window.high - 1 >= MAX_SAMPLE_ROUND_TRIP:
        return window.high - 1
    return None


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
        self._record_times: ExchangeTimes | None = None
        self._estimate: Window | None = None
        self._estimate_from_write = False
        self._writing = False
        self._write_reply_time: float | None = None
        self._cancel_quiet: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Read the lock's clock and set it to Home Assistant's time when its whole window lies more than SET_LIMIT off."""
        if (
            (reply := await self._async_read()) is not None
            and (window := self._async_estimate(reply.value, reply.times)) is not None
            and (offset := _set_offset(window)) is not None
        ):
            self._writing = True
            await self._async_write(window, offset)
        self._async_wait_quiet()

    @callback
    def async_stop(self) -> None:
        """Cancel the read of a quiet lock."""
        if self._cancel_quiet is not None:
            self._cancel_quiet()
            self._cancel_quiet = None

    @callback
    def async_record_read(self, times: ExchangeTimes) -> None:
        """Keep a record's times, so the GetLogError that ends its drain is a sample."""
        self._record_times = times

    @callback
    def async_sample(self, record: GetLogError) -> None:
        """Take the GetLogError ending a drain that read a record as a sample of the lock's clock."""
        if record.dirty_bit:
            # A GetLogError with the dirty bit set answers a GetLog that raced a
            # record's write, and the drain reads on.
            return
        if (times := self._record_times) is None:
            # After a drain that read nothing, the lock repeats the previous
            # GetLogError's times, those of an earlier read.
            return
        self._record_times = None
        # dirty_bit_cleared_time is the lock's time at the read that emptied the log,
        # the drain's last record.
        self._async_correct(record.dirty_bit_cleared_time, times)

    @callback
    def _async_estimate(self, lock_time: int, times: ExchangeTimes) -> Window | None:
        """Narrow the estimate with a reading of the lock's second lock_time and return it, or None when the reading is no sample."""
        if self._writing or (
            self._write_reply_time is not None
            and times.request_written < self._write_reply_time
        ):
            # A request written before the write's reply may have been answered
            # from the clock before the write.
            return None
        if (window := _sample_window(lock_time, times)) is None:
            return None
        self._async_wait_quiet()
        if (estimate := self._estimate) is not None:
            low = max(estimate.low, window.low)
            high = min(estimate.high, window.high)
            if low < high:
                self._estimate = Window(low, high)
                return self._estimate
            _LOGGER.debug(
                "%s clock sample %.2f to %.2f s misses the estimate %.2f to %.2f s %s; the estimate starts again from the sample",
                self._entry.title,
                window.low,
                window.high,
                estimate.low,
                estimate.high,
                "set by a write"
                if self._estimate_from_write
                else "with no write before it",
            )
        self._estimate = window
        self._estimate_from_write = False
        return window

    @callback
    def _async_correct(self, lock_time: int, times: ExchangeTimes) -> bool:
        """Take a reading as a sample and order a write when one is due, as a task; return False when the reading is no sample."""
        if (window := self._async_estimate(lock_time, times)) is None:
            return False
        if (offset := _set_offset(window)) is None:
            offset = _step_offset(window)
        if offset is not None:
            self._writing = True
            self._async_create_task(self._async_write(window, offset))
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
        if (reply := await self._async_read()) is None or not self._async_correct(
            reply.value, reply.times
        ):
            self._async_wait_quiet()

    @callback
    def _async_create_task(self, target: Coroutine[Any, Any, None]) -> None:
        """Run a read or a write of the clock as a task of the entry's."""
        self._entry.async_create_background_task(
            self._hass, target, f"{self._entry.title} clock"
        )

    async def _async_read(self) -> StatusReply | None:
        """Return the lock's clock read, or None when the read fails."""
        try:
            return await self._lock.get_status(StatusType.RTC)
        except CLOCK_ERRORS as err:
            _LOGGER.debug("%s clock not read: %s", self._entry.title, err)
            return None

    async def _async_write(self, window: Window, offset: float) -> None:
        """Set the lock's clock offset seconds from Home Assistant's, start the estimate from the write, and log the window found."""
        try:
            times = await self._lock.set_rtc(offset)
        except CLOCK_ERRORS as err:
            _LOGGER.debug("%s clock not set: %s", self._entry.title, err)
            # The write may have reached the lock.
            self._estimate = None
            return
        finally:
            self._writing = False
        self._write_reply_time = times.reply_received
        round_trip = times.reply_received - times.request_written
        # The lock applied the write between its request and its reply, so it lands
        # up to the round trip late. The window takes the lock's second to start at
        # the write, which is not established; a sample that misses it logs the miss.
        self._estimate = (
            Window(offset - round_trip, offset)
            if round_trip <= MAX_SAMPLE_ROUND_TRIP
            else None
        )
        self._estimate_from_write = True
        if _set_offset(window) is not None:
            _LOGGER.info(
                "%s clock %s; set to Home Assistant's time",
                self._entry.title,
                window.describe(),
            )
        else:
            _LOGGER.info(
                "%s clock %s; moved up to 1 s toward Home Assistant's time",
                self._entry.title,
                window.describe(),
            )
