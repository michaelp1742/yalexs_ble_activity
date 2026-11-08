"""Tests for the Yale Access Bluetooth Activity setup and lifecycle."""

from typing import Any
from unittest.mock import Mock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yalexs_ble import LockCred

from custom_components.yalexs_ble_activity.const import (
    CONF_LOCK_MODEL,
    CONF_READ_ACTIVITY_LOG,
    DOMAIN,
)
from custom_components.yalexs_ble_activity.reader import LogReader
from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_RESTORED, CONF_ADDRESS, STATE_UNAVAILABLE, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.integration_platform import DATA_INTEGRATION_PLATFORMS

from . import (
    ADDRESS,
    CODE_OPERATION_SLOT_1,
    ENTITY_ID,
    FRONT_ADDRESS,
    FRONT_TITLE,
    async_advance,
    async_deliver,
    async_setup_owner,
    async_setup_platform,
    enable_entity,
    last_data,
    store_key,
)

# The own time of CODE_OPERATION_SLOT_1.
CODE_OPERATION_SLOT_1_TIME = 1793077244


def _collected_platforms(hass: HomeAssistant) -> list[str]:
    """Return the integration platform names Home Assistant collects."""
    return [
        platform.platform_name
        for platform in hass.data.get(DATA_INTEGRATION_PLATFORMS, [])
    ]


@pytest.mark.parametrize(("read_activity_log", "stored_line"), [(False, None)])
async def test_option_off_leaves_entry_idle(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
) -> None:
    """With the option off, the entry loads and runs nothing for the lock, and creates no device and no store."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    # Core's entry does not exist yet, and setup does not need it.
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is None

    owner_entry = await async_setup_owner(hass)
    lock = owner_entry.runtime_data.lock
    core_listener = Mock()
    owner_entry.async_on_state_change(core_listener)
    entry_listener = Mock()
    config_entry.async_on_state_change(entry_listener)
    assert await hass.config_entries.async_unload(owner_entry.entry_id)
    await hass.async_block_till_done()

    core_listener.assert_called()
    entry_listener.assert_not_called()
    assert (
        er.async_entries_for_config_entry(entity_registry, config_entry.entry_id) == []
    )
    assert DOMAIN not in _collected_platforms(hass)
    assert Platform.EVENT not in hass.config.components
    lock.register_log_record_callback.assert_not_called()
    assert (
        dr.async_entries_for_config_entry(device_registry, config_entry.entry_id) == []
    )
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert store_key(config_entry) not in hass_storage


async def test_option_on_registers_the_entrys_reader_on_the_pushlock_of_its_lock(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
) -> None:
    """With the option on, the entry's reader registers on the PushLock of its address, the platforms are collected, and the entity is registered."""
    front_entry = await async_setup_owner(hass, FRONT_ADDRESS, FRONT_TITLE)
    owner_entry = await async_setup_owner(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert isinstance(config_entry.runtime_data, LogReader)
    owner_entry.runtime_data.lock.register_log_record_callback.assert_called_once_with(
        config_entry.runtime_data.async_log_record
    )
    front_entry.runtime_data.lock.register_log_record_callback.assert_not_called()
    assert _collected_platforms(hass).count(DOMAIN) == 1
    assert entity_registry.async_get(ENTITY_ID) is not None


async def test_two_entries_collect_the_platforms_once(
    hass: HomeAssistant,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """A second entry with the option on starts no second collection, so a platform is asked once."""
    await async_setup_owner(hass, FRONT_ADDRESS, FRONT_TITLE)
    front_entry = MockConfigEntry(
        domain=DOMAIN,
        title=FRONT_TITLE,
        data={CONF_ADDRESS: FRONT_ADDRESS},
        options={CONF_READ_ACTIVITY_LOG: True, CONF_LOCK_MODEL: "unity"},
        unique_id=FRONT_ADDRESS,
    )
    front_entry.add_to_hass(hass)
    # The setup of one entry of the domain sets up both.
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert front_entry.state is ConfigEntryState.LOADED
    namer = Mock(return_value="Michael")
    await async_setup_platform(hass, "keypad", async_credential_name=namer)

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert _collected_platforms(hass).count(DOMAIN) == 1
    assert last_data(log_records)["name"] == "Michael"
    namer.assert_called_once_with(hass, ADDRESS, LockCred.PIN, 1)


async def test_option_on_waits_for_core_to_load_the_lock(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """With the option on and core's entry not loaded, setup is retried."""
    assert not await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.reason == "Yale Access Bluetooth has not loaded this lock"


async def test_core_unload_reloads_entry_until_core_loads(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """Core's unload reloads the entry, which retries until core's entry has loaded and then registers its reader on the new PushLock."""
    old_lock = owner_entry.runtime_data.lock
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    states: list[ConfigEntryState] = []
    config_entry.async_on_state_change(lambda: states.append(config_entry.state))

    assert await hass.config_entries.async_unload(owner_entry.entry_id)
    await hass.async_block_till_done()

    assert states.count(ConfigEntryState.SETUP_IN_PROGRESS) == 1
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.reason == "Yale Access Bluetooth has not loaded this lock"

    assert await hass.config_entries.async_setup(owner_entry.entry_id)
    await async_advance(hass, freezer, 6)

    assert config_entry.state is ConfigEntryState.LOADED
    new_lock = owner_entry.runtime_data.lock
    assert new_lock is not old_lock
    new_lock.register_log_record_callback.assert_called_once_with(
        config_entry.runtime_data.async_log_record
    )
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    assert last_data(log_records)[ATTR_EVENT_TYPE] == "pin"


async def test_core_change_reaches_the_next_listener(
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> None:
    """The entry's reload waits until core's entry has called every listener."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    seen: list[tuple[ConfigEntryState, ConfigEntryState]] = []
    owner_entry.async_on_state_change(
        lambda: seen.append((owner_entry.state, config_entry.state))
    )

    assert await hass.config_entries.async_unload(owner_entry.entry_id)
    await hass.async_block_till_done()

    assert seen == [
        (ConfigEntryState.UNLOAD_IN_PROGRESS, ConfigEntryState.LOADED),
        (ConfigEntryState.NOT_LOADED, ConfigEntryState.LOADED),
    ]
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_core_change_reloads_entry_once(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """Each reload or unload of core's entry reloads the entry once, and after a reload the reader is on the new PushLock and continues the serial from the store the unload wrote."""
    old_lock = owner_entry.runtime_data.lock
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    states: list[ConfigEntryState] = []
    config_entry.async_on_state_change(lambda: states.append(config_entry.state))
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    assert await hass.config_entries.async_reload(owner_entry.entry_id)
    await hass.async_block_till_done()

    assert states.count(ConfigEntryState.SETUP_IN_PROGRESS) == 1
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass_storage[store_key(config_entry)]["data"] == {
        "earliest_time": CODE_OPERATION_SLOT_1_TIME,
        "last_line_time": CODE_OPERATION_SLOT_1_TIME,
        "serial": 1,
    }
    new_lock = owner_entry.runtime_data.lock
    assert new_lock is not old_lock
    old_lock.register_log_record_callback.return_value.assert_called_once_with()
    new_lock.register_log_record_callback.assert_called_once_with(
        config_entry.runtime_data.async_log_record
    )
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    assert [event.data["serial"] for event in log_records] == [1, 2]

    assert await hass.config_entries.async_unload(owner_entry.entry_id)
    await hass.async_block_till_done()

    assert states.count(ConfigEntryState.SETUP_IN_PROGRESS) == 2
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unloading_the_entry_removes_the_reader_and_the_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    owner_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """The entry's unload removes the reader from the PushLock, and the entity's state becomes unavailable with restored set."""
    enable_entity(entity_registry, config_entry)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    register = owner_entry.runtime_data.lock.register_log_record_callback
    register.return_value.assert_not_called()
    assert hass.states.get(ENTITY_ID) is not None

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    register.return_value.assert_called_once_with()
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_UNAVAILABLE
    assert state.attributes[ATTR_RESTORED] is True


async def test_removing_the_entry_removes_its_store(
    hass: HomeAssistant, hass_storage: dict[str, Any], loaded_entry: MockConfigEntry
) -> None:
    """Removing the entry removes its store."""
    assert store_key(loaded_entry) in hass_storage

    await hass.config_entries.async_remove(loaded_entry.entry_id)
    await hass.async_block_till_done()

    assert store_key(loaded_entry) not in hass_storage
