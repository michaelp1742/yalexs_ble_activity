"""Tests for the Yale Access Bluetooth Activity lock clock."""

import asyncio
from datetime import UTC, datetime
import logging
from unittest.mock import call

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yalexs_ble import StatusType

from custom_components.yalexs_ble_activity.const import DOMAIN
from homeassistant.core import Event, HomeAssistant

from . import (
    CODE_OPERATION_SLOT_1,
    END_OF_LOG,
    TITLE,
    async_advance,
    async_deliver,
    with_checksum,
)

LOGGER = f"custom_components.{DOMAIN}.clock"
NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)
NOW_TIME = int(NOW.timestamp())
SIX_HOURS = 6 * 3600


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


def _lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """Return the clock's log messages at level."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER and record.levelno == level
    ]


async def _async_drain(
    hass: HomeAssistant, owner_entry: MockConfigEntry, cleared_time: int
) -> None:
    """Hand the reader a record and the GetLogError ending its drain, and run the tasks."""
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_deliver(owner_entry, end_of_log_at(cleared_time))
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("lock_offset", "writes", "info"),
    [
        pytest.param(
            -12,
            [call(NOW_TIME)],
            [f"{TITLE} clock 12 s behind; set to Home Assistant's time"],
            id="12_s_behind",
        ),
        pytest.param(-8, [], [], id="8_s_behind"),
    ],
)
async def test_setup_sets_a_clock_more_than_10_s_off_before_the_reader(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    lock_offset: int,
    writes: list[object],
    info: list[str],
) -> None:
    """Setup reads the lock's clock and sets it to Home Assistant's time before it registers the reader, only when it is more than 10 s off."""
    lock = owner_entry.runtime_data.lock
    lock.get_status.side_effect = None
    lock.get_status.return_value = NOW_TIME + lock_offset

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert lock.get_status.call_args_list == [call(StatusType.RTC)]
    assert lock.set_rtc.call_args_list == writes
    assert [name for name, _, _ in lock.mock_calls] == [
        "get_status",
        *(["set_rtc"] * len(writes)),
        "register_log_record_callback",
    ]
    assert _lines(caplog, logging.INFO) == info


@pytest.mark.parametrize(
    ("lock_offset", "write", "info"),
    [
        pytest.param(
            3,
            NOW_TIME + 2,
            f"{TITLE} clock 3 s ahead; moved 1 s toward Home Assistant's time",
            id="3_s_ahead",
        ),
        pytest.param(
            -2,
            NOW_TIME - 1,
            f"{TITLE} clock 2 s behind; moved 1 s toward Home Assistant's time",
            id="2_s_behind",
        ),
        pytest.param(
            15,
            NOW_TIME,
            f"{TITLE} clock 15 s ahead; set to Home Assistant's time",
            id="15_s_ahead",
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_a_sample_off_by_2_s_or_more_corrects_the_clock_in_a_task(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    owner_entry: MockConfigEntry,
    lock_offset: int,
    write: int,
    info: str,
) -> None:
    """The GetLogError ending a drain that read a record corrects a clock 2 to 10 s off by 1 s, and one more than 10 s off to Home Assistant's time, in a task the reader does not await."""
    lock = owner_entry.runtime_data.lock
    release = asyncio.Event()

    async def _async_set_rtc(seconds: int) -> None:
        await release.wait()

    lock.set_rtc.side_effect = _async_set_rtc

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + lock_offset))

    # The reader returned while the write still waits for the lock.
    assert lock.set_rtc.call_args_list == [call(write)]
    assert _lines(caplog, logging.INFO) == []
    release.set()
    await hass.async_block_till_done()
    assert _lines(caplog, logging.INFO) == [info]


@pytest.mark.usefixtures("loaded_entry")
async def test_no_write_for_a_clock_1_s_off_or_a_drain_that_read_nothing(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """A sample 1 s off writes nothing, and a GetLogError after a drain that read no record is no sample."""
    lock = owner_entry.runtime_data.lock

    await _async_drain(hass, owner_entry, NOW_TIME + 1)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + 15))
    await hass.async_block_till_done()

    lock.set_rtc.assert_not_called()
    await _async_drain(hass, owner_entry, NOW_TIME + 15)
    lock.set_rtc.assert_called_once_with(NOW_TIME)


@pytest.mark.usefixtures("loaded_entry")
async def test_a_quiet_lock_is_read_6_h_after_the_last_sample(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, owner_entry: MockConfigEntry
) -> None:
    """With no sample for 6 h the clock is read and corrected as a sample, and each sample moves the read 6 h on."""
    lock = owner_entry.runtime_data.lock
    await async_advance(hass, freezer, 3600)
    await _async_drain(hass, owner_entry, NOW_TIME + 3600)

    await async_advance(hass, freezer, SIX_HOURS - 1)
    assert lock.get_status.call_count == 1
    lock.get_status.side_effect = lambda status_type: NOW_TIME + 3600 + SIX_HOURS + 3
    await async_advance(hass, freezer, 1)

    assert lock.get_status.call_args_list == [call(StatusType.RTC)] * 2
    lock.set_rtc.assert_called_once_with(NOW_TIME + 3600 + SIX_HOURS + 2)
    await async_advance(hass, freezer, SIX_HOURS)
    assert lock.get_status.call_count == 3


async def test_a_failed_read_or_write_logs_at_debug_and_the_records_still_fire(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
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
    await _async_drain(hass, owner_entry, NOW_TIME + 15)
    lock.set_rtc.side_effect = None
    await _async_drain(hass, owner_entry, NOW_TIME + 15)

    assert _lines(caplog, logging.DEBUG) == [
        f"{TITLE} clock not read: lock did not answer get_status 0x0A",
        f"{TITLE} clock not set: lock did not answer set_rtc",
    ]
    assert [event.data["serial"] for event in log_records] == [1, 2]
    assert lock.set_rtc.call_args_list == [call(NOW_TIME)] * 2
    assert _lines(caplog, logging.INFO) == [
        f"{TITLE} clock 15 s ahead; set to Home Assistant's time"
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


@pytest.mark.usefixtures("loaded_entry")
async def test_a_get_log_error_with_the_dirty_bit_set_is_no_sample(
    hass: HomeAssistant, owner_entry: MockConfigEntry
) -> None:
    """A GetLogError with the dirty bit set after a record is no sample, and the GetLogError ending the drain is."""
    lock = owner_entry.runtime_data.lock

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + 15, dirty=True))
    await async_deliver(owner_entry, end_of_log_at(NOW_TIME + 3))
    await hass.async_block_till_done()

    lock.set_rtc.assert_called_once_with(NOW_TIME + 2)
