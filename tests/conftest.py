"""Fixtures for the Yale Access Bluetooth Activity tests."""

from collections.abc import Iterator
import time
from typing import Any
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    async_capture_events,
    mock_config_flow,
    mock_integration,
    mock_platform,
)
from yalexs_ble import PushLock

from custom_components.yalexs_ble_activity.const import (
    CONF_LOCK_MODEL,
    CONF_READ_ACTIVITY_LOG,
    DOMAIN,
    EVENT_LOG_RECORD,
    OWNER_DOMAIN,
)
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import ADDRESS, TITLE, async_setup_owner, status_reply, store_key, times_now


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


async def _async_setup_owner_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load core's entry with a new PushLock, as core does on every load."""
    lock = create_autospec(PushLock, instance=True, address=entry.data[CONF_ADDRESS])
    # The lock's clock shows Home Assistant's time, so setup writes nothing.
    lock.get_status.side_effect = lambda status_type: status_reply(int(time.time()))
    lock.set_rtc.side_effect = lambda offset=0.0: times_now()
    entry.runtime_data = Mock(lock=lock)
    return True


class _OwnerConfigFlow(ConfigFlow):
    """Stand in for the config flow of core's yalexs_ble."""


@pytest.fixture(autouse=True)
def mock_owner_integration(hass: HomeAssistant) -> Iterator[None]:
    """Stand in for core's yalexs_ble, which needs Bluetooth."""
    mock_integration(
        hass,
        MockModule(
            OWNER_DOMAIN,
            async_setup_entry=_async_setup_owner_entry,
            async_unload_entry=AsyncMock(return_value=True),
        ),
    )
    mock_platform(hass, f"{OWNER_DOMAIN}.config_flow")
    with mock_config_flow(OWNER_DOMAIN, _OwnerConfigFlow):
        yield


@pytest.fixture
async def owner_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a loaded entry of core's yalexs_ble."""
    return await async_setup_owner(hass)


@pytest.fixture
def read_activity_log() -> bool:
    """Return the read_activity_log option of the activity entry."""
    return True


@pytest.fixture
def lock_model() -> str:
    """Return the lock_model option of the activity entry."""
    return "unity"


@pytest.fixture
def stored_line() -> dict[str, Any] | None:
    """Return the activity entry's store at its setup, or None for nothing stored."""
    # An earliest time of 0 puts no captured or constructed reply before the
    # window's start.
    return {"earliest_time": 0, "last_line_time": None, "serial": 0}


@pytest.fixture
def config_entry(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    read_activity_log: bool,
    lock_model: str,
    stored_line: dict[str, Any] | None,
) -> MockConfigEntry:
    """Return the activity entry for the lock, not yet set up, with stored_line in its store."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TITLE,
        data={CONF_ADDRESS: ADDRESS},
        options={
            CONF_READ_ACTIVITY_LOG: read_activity_log,
            CONF_LOCK_MODEL: lock_model,
        },
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    if stored_line is not None:
        hass_storage[store_key(entry)] = {"version": 1, "data": stored_line}
    return entry


@pytest.fixture
def log_records(hass: HomeAssistant) -> list[Event]:
    """Return the log record events fired from now on."""
    return async_capture_events(hass, EVENT_LOG_RECORD)


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Return the activity entry, loaded with the option on."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def core_lock(
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    owner_entry: MockConfigEntry,
) -> er.RegistryEntry:
    """Register core's lock device, named TITLE, and its main lock entity."""
    device = device_registry.async_get_or_create(
        config_entry_id=owner_entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, ADDRESS)},
        identifiers={(OWNER_DOMAIN, "serial")},
        name=TITLE,
    )
    return entity_registry.async_get_or_create(
        LOCK_DOMAIN,
        OWNER_DOMAIN,
        ADDRESS,
        suggested_object_id="back_door_lock",
        config_entry=owner_entry,
        device_id=device.id,
    )
