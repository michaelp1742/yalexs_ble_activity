"""The Yale Access Bluetooth Activity integration."""

from typing import TYPE_CHECKING

from yalexs_ble import PushLock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .activity import async_collect_namers
from .const import CONF_READ_ACTIVITY_LOG, DOMAIN, OWNER_DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.yalexs_ble import YALEXSBLEConfigEntry

PLATFORMS = [Platform.EVENT]

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
    await async_collect_namers(hass)
    entry.runtime_data = owner.runtime_data.lock

    reload_scheduled = False

    @callback
    def _async_owner_changed() -> None:
        """Schedule one reload of this entry when core's entry changes state."""
        nonlocal reload_scheduled
        if reload_scheduled:
            return
        reload_scheduled = True
        # A reload started inside the listener loop of core's entry can remove this
        # listener while the loop runs, and the loop then skips the listener after it.
        hass.loop.call_soon(hass.config_entries.async_schedule_reload, entry.entry_id)

    entry.async_on_unload(owner.async_on_state_change(_async_owner_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: YaleXSBLEActivityConfigEntry
) -> bool:
    """Unload a config entry."""
    if entry.runtime_data is None:
        # Setup forwarded no platform. The option is not checked here: the options
        # flow stores its new value before the reload that runs this unload.
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
