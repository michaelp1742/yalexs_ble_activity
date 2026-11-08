"""The Yale Access Bluetooth Activity integration."""

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.start import async_at_started

from .activity import async_collect_namers
from .clock import LockClock
from .const import CONF_READ_ACTIVITY_LOG, DOMAIN, OWNER_DOMAIN
from .reader import LogReader, store_for

if TYPE_CHECKING:
    from homeassistant.components.yalexs_ble import YALEXSBLEConfigEntry

PLATFORMS = [Platform.EVENT]

type YaleXSBLEActivityConfigEntry = ConfigEntry[LogReader | None]


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
    lock = owner.runtime_data.lock
    # The PushLock's address, which core's lock device uses, links the two devices.
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, lock.address)},
        name=entry.title,
    )
    clock = LockClock(hass, entry, lock)
    reader = LogReader(hass, entry, device, clock)
    await reader.async_load()
    entry.runtime_data = reader
    entry.async_on_unload(reader.async_save)
    entry.async_on_unload(async_at_started(hass, reader.async_started))
    # The Yale Home and August apps set the clock before they read the log, so the
    # clock starts before the reader registers.
    await clock.async_start()
    entry.async_on_unload(clock.async_stop)
    entry.async_on_unload(lock.register_log_record_callback(reader.async_log_record))

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


async def async_remove_entry(
    hass: HomeAssistant, entry: YaleXSBLEActivityConfigEntry
) -> None:
    """Remove the entry's store."""
    await store_for(hass, entry.entry_id).async_remove()
