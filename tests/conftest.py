"""Fixtures for the Yale Access Bluetooth Activity tests."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_config_flow,
    mock_integration,
    mock_platform,
)
from yalexs_ble import PushLock

from custom_components.yalexs_ble_activity.const import (
    CONF_LOCK_MODEL,
    CONF_READ_ACTIVITY_LOG,
    DOMAIN,
    OWNER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import ADDRESS, TITLE, async_setup_owner


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


async def _async_setup_owner_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load core's entry with a new PushLock, as core does on every load."""
    entry.runtime_data = Mock(
        lock=create_autospec(PushLock, instance=True, address=entry.data[CONF_ADDRESS])
    )
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
def config_entry(
    hass: HomeAssistant, read_activity_log: bool, lock_model: str
) -> MockConfigEntry:
    """Return the activity entry for the lock, not yet set up."""
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
    return entry


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, owner_entry: MockConfigEntry, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Return the activity entry, loaded with the option on and its entity added."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
