"""The Yale Access Bluetooth Activity integration."""

from typing import TYPE_CHECKING

from yalexs_ble import PushLock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_READ_ACTIVITY_LOG, DOMAIN, OWNER_DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.yalexs_ble import YALEXSBLEConfigEntry

type YaleXSBLEActivityConfigEntry = ConfigEntry[PushLock | None]


@callback
def async_loaded_owners(hass: HomeAssistant) -> dict[str, YALEXSBLEConfigEntry]:
    """Return the loaded entries of core's yalexs_ble by lock address."""
    return {
        owner.data[CONF_ADDRESS]: owner
        for owner in hass.config_entries.async_loaded_entries(OWNER_DOMAIN)
    }


async def async_setup_entry(
    hass: HomeAssistant, entry: YaleXSBLEActivityConfigEntry
) -> bool:
    """Set up the entry, which runs nothing while its option is off."""
    if not entry.options[CONF_READ_ACTIVITY_LOG]:
        entry.runtime_data = None
        return True
    if (owner := async_loaded_owners(hass).get(entry.data[CONF_ADDRESS])) is None:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="owner_not_loaded"
        )
    entry.runtime_data = owner.runtime_data.lock
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: YaleXSBLEActivityConfigEntry
) -> bool:
    """Unload a config entry."""
    return True
