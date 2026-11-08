"""Tests for the Yale Access Bluetooth Activity log reader: the line's time, the window, and the store."""

from datetime import UTC, datetime
import logging
from typing import Any
from unittest.mock import Mock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yalexs_ble import LockCred

from custom_components.yalexs_ble_activity.const import DOMAIN
from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from . import (
    ADDRESS,
    AUTO_RELOCK_LOCKED,
    CODE_OPERATION_SLOT_1,
    KEYPAD_INFO_AT_CODE_OPERATION_SLOT_1,
    NO_DECODER,
    PIN_SLOT_3_UNLOCKED,
    TITLE,
    async_advance,
    async_deliver,
    async_setup_platform,
    door_opened_at,
    store_key,
)

LOGGER = f"custom_components.{DOMAIN}.reader"
NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)
NOW_TIME = int(NOW.timestamp())
# An earliest time an hour before NOW.
T = NOW_TIME - 3600
DAY = 86400
# The own time of CODE_OPERATION_SLOT_1.
CODE_OPERATION_SLOT_1_TIME = 1793077244


def _lines(events: list[Event]) -> list[tuple[str, float, int]]:
    """Return the event type, the line's time, and the serial of each log record event."""
    return [
        (event.data[ATTR_EVENT_TYPE], event.time_fired_timestamp, event.data["serial"])
        for event in events
    ]


def _discards(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return the messages of the reader's debug lines."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER and record.levelno == logging.DEBUG
    ]


async def _async_setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the activity entry."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_records_in_one_own_second_are_placed_a_millisecond_apart(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A KeypadInfo and the CodeOperation read 0.6 s after it in the same own second fire in that order, the second line 1 ms after the first."""
    await async_deliver(owner_entry, KEYPAD_INFO_AT_CODE_OPERATION_SLOT_1)
    await async_advance(hass, freezer, 0.6)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    keypad_info, pin = log_records
    assert keypad_info.data[ATTR_EVENT_TYPE] == "keypad_info"
    assert keypad_info.data["battery_level"] == 195
    assert keypad_info.data["stats"] == 0x80000000
    assert pin.data[ATTR_EVENT_TYPE] == "pin"
    assert keypad_info.time_fired_timestamp == CODE_OPERATION_SLOT_1_TIME
    assert pin.time_fired_timestamp == keypad_info.time_fired_timestamp + 0.001


async def test_a_backlog_record_before_the_last_fired_is_discarded(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """Of three backlog records, the second older than the first, the first and third fire at their own times with the next two serials, and the second is logged at debug."""
    freezer.move_to(NOW)
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    for raw in (CODE_OPERATION_SLOT_1, AUTO_RELOCK_LOCKED, PIN_SLOT_3_UNLOCKED):
        await async_deliver(owner_entry, raw, backlog=True)

    assert [
        (
            event.data[ATTR_EVENT_TYPE],
            event.time_fired.isoformat(),
            event.data["backlog"],
            event.data["serial"],
        )
        for event in log_records
    ] == [
        ("pin", "2026-10-27T05:00:44+00:00", True, 1),
        ("pin", "2026-10-30T01:50:43+00:00", True, 2),
    ]
    assert _discards(caplog) == [
        f"{TITLE}: discarded LockOperation at 2026-10-25T07:19:23+00:00, outside the "
        "window from 2026-10-27T05:00:44+00:00 to 2026-11-08T12:00:05+00:00"
    ]


@pytest.mark.parametrize(
    "stored_line", [{"earliest_time": T, "last_line_time": T + 0.001, "serial": 5}]
)
async def test_the_window_runs_from_the_earliest_time_to_five_seconds_ahead(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A record at the earliest time fires after the stored line, one before it or more than 5 s ahead of now is discarded, and only a fired record takes a serial."""
    freezer.move_to(NOW)
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    for own_time in (T, T + 3, T - 1, NOW_TIME + 4, NOW_TIME + 6):
        await async_deliver(owner_entry, door_opened_at(own_time))

    assert _lines(log_records) == [
        ("door_opened", T + 0.001 + 0.001, 6),
        ("door_opened", T + 3, 7),
        ("door_opened", NOW_TIME + 4, 8),
    ]
    assert len(_discards(caplog)) == 2


@pytest.mark.parametrize("stored_line", [None])
async def test_a_first_read_takes_the_records_of_the_last_day(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """With nothing stored, a backlog record 25 hours old is discarded and one 23 hours old fires at its own time."""
    freezer.move_to(NOW)
    await _async_setup(hass, config_entry)

    for own_time in (NOW_TIME - DAY - 3600, NOW_TIME - DAY + 3600):
        await async_deliver(owner_entry, door_opened_at(own_time), backlog=True)

    assert _lines(log_records) == [("door_opened", NOW_TIME - DAY + 3600, 1)]


async def test_the_store_holds_the_window_across_a_restart(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """The store is written a second after a fired record and at the unload, and the next setup reads back the earliest time, the last line's time, and the serial."""
    freezer.move_to(NOW)
    await async_deliver(owner_entry, door_opened_at(T))
    await async_advance(hass, freezer, 1)

    assert hass_storage[store_key(loaded_entry)]["data"] == {
        "earliest_time": T,
        "last_line_time": T,
        "serial": 1,
    }

    await async_deliver(owner_entry, door_opened_at(T))
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)

    assert hass_storage[store_key(loaded_entry)]["data"] == {
        "earliest_time": T,
        "last_line_time": T + 0.001,
        "serial": 2,
    }

    await _async_setup(hass, loaded_entry)
    await async_deliver(owner_entry, door_opened_at(T - 1))
    await async_deliver(owner_entry, door_opened_at(T))

    assert _lines(log_records) == [
        ("door_opened", T, 1),
        ("door_opened", T + 0.001, 2),
        ("door_opened", T + 0.001 + 0.001, 3),
    ]


@pytest.mark.parametrize("stored_line", [None])
async def test_an_unload_with_no_record_fired_writes_no_store(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """An entry that fired no record writes no store at its unload."""
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)

    assert log_records == []
    assert store_key(loaded_entry) not in hass_storage


async def test_a_record_with_no_own_time_follows_the_last_line(
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A record of a log_type the library does not decode is placed 1 ms after the last line and leaves the earliest time where it was."""
    freezer.move_to(NOW)

    for raw in (door_opened_at(T), NO_DECODER, door_opened_at(T)):
        await async_deliver(owner_entry, raw)

    assert _lines(log_records) == [
        ("door_opened", T, 1),
        ("unknown_record", T + 0.001, 2),
        ("door_opened", T + 0.001 + 0.001, 3),
    ]


async def test_a_record_with_no_own_time_and_no_line_is_placed_at_the_read_time(
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A record of a log_type the library does not decode, read with no line before it, is placed at the time it was read."""
    freezer.move_to(NOW)

    await async_deliver(owner_entry, NO_DECODER)

    assert _lines(log_records) == [("unknown_record", NOW_TIME, 1)]


async def test_records_read_at_a_start_fire_once_home_assistant_has_started(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """Records read before Home Assistant has started fire once it has, in the order read, at their own times, and named by a platform collected meanwhile."""
    hass.set_state(CoreState.starting)
    await _async_setup(hass, config_entry)

    await async_deliver(owner_entry, AUTO_RELOCK_LOCKED, backlog=True)
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1, backlog=True)
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)
    assert log_records == []

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert [
        (
            event.data[ATTR_EVENT_TYPE],
            event.data.get("name"),
            event.data["backlog"],
            event.time_fired.isoformat(),
        )
        for event in log_records
    ] == [
        ("auto_lock", None, True, "2026-10-25T07:19:23+00:00"),
        ("pin", "Michael", True, "2026-10-27T05:00:44+00:00"),
    ]
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)
