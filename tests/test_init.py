"""Tests for the Yale Access Bluetooth Activity setup and lifecycle."""

from unittest.mock import Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import FRONT_ADDRESS, FRONT_TITLE, async_setup_owner


@pytest.mark.parametrize("read_activity_log", [False])
async def test_option_off_leaves_entry_idle(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
) -> None:
    """With the option off, the entry loads and runs nothing for the lock."""
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
    lock.register_log_record_callback.assert_not_called()
    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_option_on_holds_the_pushlock_of_its_lock(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """With the option on, the entry holds the PushLock of the loaded entry for its address."""
    await async_setup_owner(hass, FRONT_ADDRESS, FRONT_TITLE)
    owner_entry = await async_setup_owner(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is owner_entry.runtime_data.lock


async def test_option_on_waits_for_core_to_load_the_lock(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """With the option on and core's entry not loaded, setup is retried."""
    assert not await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.reason == "Yale Access Bluetooth has not loaded this lock"
