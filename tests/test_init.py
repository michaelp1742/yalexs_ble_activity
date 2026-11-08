"""Tests for the Yale Access Bluetooth Activity setup and lifecycle."""

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
from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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
)


def _collected_platforms(hass: HomeAssistant) -> list[str]:
    """Return the integration platform names Home Assistant collects."""
    return [
        platform.platform_name
        for platform in hass.data.get(DATA_INTEGRATION_PLATFORMS, [])
    ]


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
    assert DOMAIN not in _collected_platforms(hass)
    assert Platform.EVENT not in hass.config.components
    lock.register_log_record_callback.assert_not_called()
    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_option_on_holds_the_pushlock_of_its_lock(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """With the option on, the entry holds the PushLock of its address, collects the platforms, and adds the entity."""
    await async_setup_owner(hass, FRONT_ADDRESS, FRONT_TITLE)
    owner_entry = await async_setup_owner(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is owner_entry.runtime_data.lock
    assert _collected_platforms(hass).count(DOMAIN) == 1
    assert hass.states.get(ENTITY_ID) is not None
    owner_entry.runtime_data.lock.register_log_record_callback.assert_called_once()


async def test_two_entries_collect_the_platforms_once(
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
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
    assert hass.states.get(ENTITY_ID).attributes["name"] == "Michael"
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
) -> None:
    """Core's unload reloads the entry, which retries until core's entry has loaded and then reads its new PushLock."""
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
    new_lock.register_log_record_callback.assert_called_once()
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EVENT_TYPE] == "pin"


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
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> None:
    """Each reload or unload of core's entry reloads the entry once, and a reload reads the new PushLock."""
    old_lock = owner_entry.runtime_data.lock
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    states: list[ConfigEntryState] = []
    config_entry.async_on_state_change(lambda: states.append(config_entry.state))

    assert await hass.config_entries.async_reload(owner_entry.entry_id)
    await hass.async_block_till_done()

    assert states.count(ConfigEntryState.SETUP_IN_PROGRESS) == 1
    assert config_entry.state is ConfigEntryState.LOADED
    new_lock = owner_entry.runtime_data.lock
    assert new_lock is not old_lock
    old_lock.register_log_record_callback.return_value.assert_called_once_with()
    new_lock.register_log_record_callback.assert_called_once()
    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EVENT_TYPE] == "pin"

    assert await hass.config_entries.async_unload(owner_entry.entry_id)
    await hass.async_block_till_done()

    assert states.count(ConfigEntryState.SETUP_IN_PROGRESS) == 2
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
