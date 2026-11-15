"""Tests for the Yale Access Bluetooth Activity lock clock."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
import logging
from unittest.mock import call

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yalexs_ble import ExchangeTimes, StatusReply, StatusType

from custom_components.yalexs_ble_activity.clock import MAX_SAMPLE_ROUND_TRIP
from custom_components.yalexs_ble_activity.const import DOMAIN
from homeassistant.core import Event, HomeAssistant

from . import (
    CODE_OPERATION_SLOT_1,
    END_OF_LOG,
    TITLE,
    async_advance,
    async_deliver,
    status_reply,
    times_now,
    with_checksum,
)

LOGGER = f"custom_components.{DOMAIN}.clock"
NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)
NOW_TIME = int(NOW.timestamp())
SIX_HOURS = 6 * 3600
STEP = "moved up to 1 s toward Home Assistant's time"
SET = "set to Home Assistant's time"


@pytest.fixture(autouse=True)
def frozen_now(freezer: FrozenDateTimeFactory) -> None:
    """Freeze Home Assistant's time at NOW."""
    freezer.move_to(NOW)


def end_of_log_at(cleared_time: int, *, dirty: bool = False) -> bytes:
    """Return a GetLogError frame built from END_OF_LOG, with dirty_bit_cleared_time in bytes 12 to 15 and the dirty bit set when dirty."""
    raw = bytearray(END_OF_LOG)
    raw[12:16] = cleared_time.to_bytes(4, "little")
    raw[5] |= 0x08 if dirty else 0
    return with_checksum(raw.hex())


def read_at(
    lock_time: int, request_written: float, reply_received: float
) -> Callable[[StatusType], StatusReply]:
    """Return a get_status stand-in answering lock_time with the given times."""
    reply = StatusReply(lock_time, ExchangeTimes(request_written, reply_received))
    return lambda status_type: reply


def _lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """Return the clock's log messages at level."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER and record.levelno == level
    ]


async def _async_drain(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    cleared_time: int,
    *,
    round_trip: float = 0.0,
) -> None:
    """Hand the reader a record arriving now and the GetLogError ending its drain, and run the write it orders."""
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1, round_trip=round_trip)
    await async_deliver(owner_entry, end_of_log_at(cleared_time))
    await async_advance(hass, freezer, 1)


@pytest.mark.parametrize(
    ("lock_offset", "round_trip", "writes", "info"),
    [
        pytest.param(
            -12,
            0.3,
            [call(0.0)],
            [f"{TITLE} clock 12.0 to 10.7 s behind; {SET}"],
            id="12_s_behind",
        ),
        pytest.param(
            12,
            0.3,
            [call(MAX_SAMPLE_ROUND_TRIP)],
            [f"{TITLE} clock 12.0 to 13.3 s ahead; {SET}"],
            id="12_s_ahead",
        ),
        pytest.param(-8, 0.3, [], [], id="8_s_behind"),
        pytest.param(-12, 0.45, [], [], id="12_s_behind_slow_reply"),
    ],
)
async def test_setup_sets_a_clock_more_than_10_s_off_before_the_reader(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    lock_offset: int,
    round_trip: float,
    writes: list[object],
    info: list[str],
) -> None:
    """Setup reads the lock's clock and sets it before it registers the reader, only when the read's whole window lies more than 10 s off."""
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = read_at(
        NOW_TIME + lock_offset, NOW_TIME - round_trip, NOW_TIME
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)

    assert lock.get_status.call_args_list == [call(StatusType.RTC)]
    assert lock.set_rtc.call_args_list == writes
    assert [name for name, _, _ in lock.mock_calls] == [
        "get_status",
        *(["set_rtc"] * len(writes)),
        "register_log_record_callback",
    ]
    assert _lines(caplog, logging.INFO) == info


@pytest.mark.parametrize(
    ("cleared_time", "round_trip", "writes", "info"),
    [
        pytest.param(
            NOW_TIME - 1,
            0.3,
            [call(pytest.approx(-0.7))],
            [f"{TITLE} clock 1.7 to 1.5 s behind; {STEP}"],
            id="step_behind",
        ),
        pytest.param(
            NOW_TIME - 15,
            0.32,
            [call(0.0)],
            [f"{TITLE} clock 15.7 to 14.4 s behind; {SET}"],
            id="set_behind",
        ),
        pytest.param(
            NOW_TIME + 16,
            0.32,
            [call(MAX_SAMPLE_ROUND_TRIP)],
            [f"{TITLE} clock 15.3 to 16.6 s ahead; {SET}"],
            id="set_ahead",
        ),
        pytest.param(NOW_TIME - 1, 0.45, [], [], id="slow_reply"),
    ],
)
async def test_a_drain_sample_orders_a_write_in_a_task(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    cleared_time: int,
    round_trip: float,
    writes: list[object],
    info: list[str],
) -> None:
    """The GetLogError ending a drain bounds the clock with its last record's times, and the write it orders runs in a task the reader does not await."""
    lock = owner_entry.runtime_data.lock
    # The setup read's window, (-2.80, -1.50], narrows the step's sample of
    # (-1.70, -0.40] to (-1.70, -1.50].
    lock.get_status.side_effect = read_at(NOW_TIME - 2, NOW_TIME + 0.5, NOW_TIME + 0.8)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    release = asyncio.Event()

    async def _async_set_rtc(offset: float) -> ExchangeTimes:
        await release.wait()
        return times_now(0.3)

    lock.set_rtc.side_effect = _async_set_rtc

    await async_advance(hass, freezer, 0.7)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1, round_trip=round_trip)
    await async_deliver(owner_entry, end_of_log_at(cleared_time))
    await hass.async_block_till_done()

    # The reader returned while the write still waits for the lock.
    assert lock.set_rtc.call_args_list == writes
    assert _lines(caplog, logging.INFO) == []
    release.set()
    await hass.async_block_till_done()
    assert _lines(caplog, logging.INFO) == info


@pytest.mark.parametrize(
    ("elapsed", "round_trip", "cleared_time", "later_cleared_time", "miss"),
    [
        pytest.param(
            0.65,
            0.35,
            NOW_TIME - 2,
            NOW_TIME + 1,
            "-0.65 to 0.35 s misses the estimate -2.65 to -1.30 s",
            id="one_sample_behind",
        ),
        pytest.param(
            0.65,
            0.35,
            NOW_TIME + 2,
            NOW_TIME + 1,
            "-0.65 to 0.35 s misses the estimate 1.35 to 2.70 s",
            id="one_sample_ahead",
        ),
        pytest.param(
            0.29,
            0.18,
            NOW_TIME - 1,
            NOW_TIME + 2,
            "0.71 to 1.71 s misses the estimate -1.29 to -0.11 s",
            id="one_fast_sample_behind",
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_a_step_waits_for_an_estimate_narrower_than_1_s_less_max_round_trip(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    elapsed: float,
    round_trip: float,
    cleared_time: int,
    later_cleared_time: int,
    miss: str,
) -> None:
    """A sample of (-2.65, -1.30], (1.35, 2.70] or (-1.29, -0.11] orders no write, though a step would stay on its side of zero, and becomes the estimate a later sample misses."""
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    lock = owner_entry.runtime_data.lock

    await async_advance(hass, freezer, elapsed)
    await _async_drain(hass, freezer, owner_entry, cleared_time, round_trip=round_trip)
    caplog.clear()
    await _async_drain(hass, freezer, owner_entry, later_cleared_time)

    lock.set_rtc.assert_not_called()
    assert _lines(caplog, logging.DEBUG) == [
        f"{TITLE} clock sample {miss} with no write before it; "
        "the estimate starts again from the sample"
    ]


async def test_each_sample_narrows_the_estimate(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """A setup read of (-2.10, -0.90] and a drain sample of (-2.65, -1.30] leave the estimate (-2.10, -1.30], too wide to step, and a sample of (-1.70, -0.70] narrows it to (-1.70, -1.30], which steps to its far edge moved 1 s."""
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = read_at(NOW_TIME - 2, NOW_TIME - 0.1, NOW_TIME + 0.1)
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    await async_advance(hass, freezer, 0.65)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME - 2, round_trip=0.35)
    lock.set_rtc.assert_not_called()
    await async_advance(hass, freezer, 0.05)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME)

    assert lock.set_rtc.call_args_list == [call(pytest.approx(-0.7))]
    assert _lines(caplog, logging.INFO) == [
        f"{TITLE} clock 1.7 to 1.3 s behind; {STEP}"
    ]


async def test_a_sample_outside_the_estimate_starts_it_again(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """A sample of (-1.10, 0.25] after an estimate of (-2.65, -1.30] logs one debug line and becomes the estimate, and a window across zero orders no write."""
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = read_at(NOW_TIME - 2, NOW_TIME + 0.3, NOW_TIME + 0.65)
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    await async_advance(hass, freezer, 0.1)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME - 1, round_trip=0.35)
    # (-0.90, 0.10] meets (-1.10, 0.25] and not (-2.65, -1.30].
    await async_advance(hass, freezer, 0.8)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 1)

    lock.set_rtc.assert_not_called()
    assert _lines(caplog, logging.DEBUG) == [
        f"{TITLE} clock sample -1.10 to 0.25 s misses the estimate -2.65 to -1.30 s "
        "with no write before it; the estimate starts again from the sample"
    ]


@pytest.mark.parametrize(
    ("request_written", "reply_received", "elapsed", "step_offset", "window"),
    [
        pytest.param(0.1, 0.3, 0.4, 0.9, "1.6 to 1.9", id="next_offset_below_zero"),
        pytest.param(
            -0.2, 0.0, 0.2, 1.2, "1.8 to 2.2", id="next_offset_below_max_round_trip"
        ),
    ],
)
async def test_a_lock_ahead_steps_toward_zero_and_stays_ahead(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    request_written: float,
    reply_received: float,
    elapsed: float,
    step_offset: float,
    window: str,
) -> None:
    """An estimate of (1.60, 1.90] steps to 0.90, and with the estimate then (0.70, 0.90] no write follows, since its far edge moved 1 s is -0.10, below MAX_SAMPLE_ROUND_TRIP. An estimate of (1.80, 2.20] steps to 1.20, and with the estimate then (1.00, 1.20] no write follows, since its far edge moved 1 s is 0.20, at or above zero but below MAX_SAMPLE_ROUND_TRIP."""
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = read_at(
        NOW_TIME + 1, NOW_TIME + request_written, NOW_TIME + reply_received
    )
    lock.set_rtc.side_effect = lambda offset: times_now(0.2)
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    await async_advance(hass, freezer, elapsed)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 2)
    await async_advance(hass, freezer, 0.6)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 2)

    assert lock.set_rtc.call_args_list == [call(pytest.approx(step_offset))]
    assert _lines(caplog, logging.INFO) == [f"{TITLE} clock {window} s ahead; {STEP}"]


async def _async_step_to_1_65_s_behind(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """Set the entry up with a read of (-3.65, -2.35], then 0.65 s after NOW hand it a drain sample of (-2.65, -1.30], which steps to -1.65; the write's reply arrives 0.65 s after NOW, and the helper returns 1.65 s after NOW."""
    owner_entry.runtime_data.lock.get_status.side_effect = read_at(
        NOW_TIME - 3, NOW_TIME + 0.35, NOW_TIME + 0.65
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await async_advance(hass, freezer, 0.65)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME - 2, round_trip=0.35)


@pytest.mark.parametrize(
    ("write_round_trip", "writes"),
    [
        pytest.param(0.35, [-1.65, -1.0], id="write_window"),
        pytest.param(0.5, [-1.65], id="slow_write_leaves_no_window"),
    ],
)
async def test_a_write_starts_the_estimate_from_its_offset_less_its_round_trip(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    write_round_trip: float,
    writes: list[float],
) -> None:
    """A write with offset -1.65 and a 0.35 s round trip starts the estimate (-2.00, -1.65], which narrows a sample of (-2.00, -1.00] to step, and one slower than MAX_SAMPLE_ROUND_TRIP leaves the sample alone, too wide to step."""
    lock = owner_entry.runtime_data.lock
    lock.set_rtc.side_effect = lambda offset: times_now(write_round_trip)

    await _async_step_to_1_65_s_behind(hass, freezer, owner_entry, config_entry)
    await async_advance(hass, freezer, 0.35)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME)

    assert lock.set_rtc.call_args_list == [
        call(pytest.approx(offset)) for offset in writes
    ]


async def test_a_sample_outside_a_writes_window_names_the_write(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """A sample of (-0.65, 0.35] after a write's window of (-2.00, -1.65] logs that the estimate was set by a write."""
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    owner_entry.runtime_data.lock.set_rtc.side_effect = lambda offset: times_now(0.35)

    await _async_step_to_1_65_s_behind(hass, freezer, owner_entry, config_entry)
    caplog.clear()
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 1)

    assert _lines(caplog, logging.DEBUG) == [
        f"{TITLE} clock sample -0.65 to 0.35 s misses the estimate -2.00 to -1.65 s "
        "set by a write; the estimate starts again from the sample"
    ]


async def test_a_read_during_a_write_or_before_its_reply_is_no_sample(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """A drain while a write waits, and one whose last record's request was written before the write's reply, order no write; a drain after the reply does."""
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = read_at(
        NOW_TIME - 3, NOW_TIME + 0.32, NOW_TIME + 0.62
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    release = asyncio.Event()

    async def _async_set_rtc(offset: float) -> ExchangeTimes:
        await release.wait()
        return times_now(0.3)

    lock.set_rtc.side_effect = _async_set_rtc

    # (-2.62, -1.30] narrows the setup read's (-3.62, -2.32] to (-2.62, -2.32].
    await async_advance(hass, freezer, 0.62)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1, round_trip=0.32)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME - 2))
    # As a sample, (-2.62, -1.62] would order a second step.
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME - 2))
    await async_advance(hass, freezer, 0.5)
    release.set()
    await hass.async_block_till_done()
    # As a sample, (-2.42, -1.07] would meet the write's (-1.92, -1.62] and step.
    await async_advance(hass, freezer, 0.3)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1, round_trip=0.35)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME - 1))
    await async_advance(hass, freezer, 1)
    assert lock.set_rtc.call_args_list == [call(pytest.approx(-1.62))]

    # (-2.42, -1.42] meets the write's (-1.92, -1.62].
    await _async_drain(hass, freezer, owner_entry, NOW_TIME)
    assert lock.set_rtc.call_args_list == [
        call(pytest.approx(-1.62)),
        call(pytest.approx(-0.92)),
    ]


@pytest.mark.usefixtures("loaded_entry")
async def test_a_drain_that_read_nothing_is_no_sample(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, owner_entry: MockConfigEntry
) -> None:
    """A sample of (-0.70, 0.30] narrows the setup estimate (0.00, 1.00] to (0.00, 0.30], which orders no write; a GetLogError after a drain that read no record is no sample, and the next drain that read one is."""
    lock = owner_entry.runtime_data.lock

    await async_advance(hass, freezer, 0.7)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_advance(hass, freezer, 0.6)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME))
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + 15))
    await async_advance(hass, freezer, 2)

    lock.set_rtc.assert_not_called()
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 18)
    lock.set_rtc.assert_called_once_with(MAX_SAMPLE_ROUND_TRIP)


@pytest.mark.usefixtures("loaded_entry")
async def test_a_get_log_error_with_the_dirty_bit_set_is_no_sample(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
) -> None:
    """A GetLogError with the dirty bit set after a record is no sample, and the GetLogError ending the drain is: its sample misses the setup estimate."""
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    lock = owner_entry.runtime_data.lock

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + 15, dirty=True))
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + 3))
    await async_advance(hass, freezer, 1)

    lock.set_rtc.assert_not_called()
    assert _lines(caplog, logging.DEBUG) == [
        f"{TITLE} clock sample 3.00 to 4.00 s misses the estimate 0.00 to 1.00 s "
        "with no write before it; the estimate starts again from the sample"
    ]


@pytest.mark.usefixtures("loaded_entry")
async def test_a_quiet_lock_is_read_6_h_after_the_last_sample(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, owner_entry: MockConfigEntry
) -> None:
    """With no sample for 6 h the clock is read and taken as a sample, and each sample moves the read 6 h on."""
    lock = owner_entry.runtime_data.lock
    await async_advance(hass, freezer, 3600)
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 3600)
    quiet_time = NOW_TIME + 3600 + SIX_HOURS

    await async_advance(hass, freezer, SIX_HOURS - 2)
    assert lock.get_status.call_count == 1
    lock.get_status.side_effect = lambda status_type: status_reply(quiet_time + 13)
    await async_advance(hass, freezer, 1)
    await async_advance(hass, freezer, 1)

    assert lock.get_status.call_args_list == [call(StatusType.RTC)] * 2
    lock.set_rtc.assert_called_once_with(MAX_SAMPLE_ROUND_TRIP)
    await async_advance(hass, freezer, SIX_HOURS)
    assert lock.get_status.call_count == 3


async def test_a_failed_read_or_write_logs_at_debug_and_the_records_still_fire(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A read or write that times out logs one debug line, the reader registers and fires as usual, and the next sample is tried."""
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = TimeoutError("lock did not answer get_status 0x0A")
    lock.set_rtc.side_effect = TimeoutError("lock did not answer set_rtc")

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 15)
    lock.set_rtc.side_effect = lambda offset: times_now(0.3)
    # (17, 18] would miss the first sample's (15, 16], but the failed write cleared it.
    await _async_drain(hass, freezer, owner_entry, NOW_TIME + 18)

    assert _lines(caplog, logging.DEBUG) == [
        f"{TITLE} clock not read: lock did not answer get_status 0x0A",
        f"{TITLE} clock not set: lock did not answer set_rtc",
    ]
    assert [event.data["serial"] for event in log_records] == [1, 2]
    assert lock.set_rtc.call_args_list == [call(MAX_SAMPLE_ROUND_TRIP)] * 2
    assert _lines(caplog, logging.INFO) == [
        f"{TITLE} clock 17.0 to 18.0 s ahead; {SET}"
    ]


async def test_unloading_the_entry_cancels_the_read_of_a_quiet_lock(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
) -> None:
    """After the entry's unload, no read follows 6 h on."""
    lock = owner_entry.runtime_data.lock

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    await async_advance(hass, freezer, SIX_HOURS)

    assert lock.get_status.call_count == 1


@pytest.mark.usefixtures("loaded_entry")
async def test_a_failed_read_of_a_quiet_lock_is_tried_again_6_h_later(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, owner_entry: MockConfigEntry
) -> None:
    """A read of a quiet lock that times out writes nothing, and the clock is read again 6 h later."""
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = TimeoutError

    await async_advance(hass, freezer, SIX_HOURS)
    await async_advance(hass, freezer, SIX_HOURS)

    assert lock.get_status.call_count == 3
    lock.set_rtc.assert_not_called()
