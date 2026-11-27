"""The Milk Tracker integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .cards import async_register_frontend
from .const import DOMAIN, VERSION  # noqa: F401
from .coordinator import MilkTrackerConfigEntry, MilkTrackerCoordinator
from .services import async_setup_services
from .websocket import async_setup_websocket

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up services, websocket API and the bundled Lovelace cards."""
    async_setup_services(hass)
    async_setup_websocket(hass)

    # Cards load automatically on every dashboard — no manual resource needed.
    async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MilkTrackerConfigEntry) -> bool:
    coordinator = MilkTrackerCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(coordinator.async_shutdown_listeners)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: MilkTrackerConfigEntry) -> None:
    coordinator = entry.runtime_data
    coordinator.apply_options()
    coordinator.async_set_updated_data(coordinator.compute())


async def async_unload_entry(hass: HomeAssistant, entry: MilkTrackerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MilkTrackerConfigEntry) -> None:
    """Delete the stored log when the integration is removed."""
    from homeassistant.helpers.storage import Store

    from .const import STORAGE_VERSION

    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
