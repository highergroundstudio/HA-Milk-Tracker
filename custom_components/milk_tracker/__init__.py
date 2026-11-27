"""The Milk Tracker integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, FRONTEND_FILE, FRONTEND_URL_BASE
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

VERSION = "1.0.0-beta.1"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up services, websocket API and the bundled Lovelace cards."""
    async_setup_services(hass)
    async_setup_websocket(hass)

    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_BASE, str(frontend_dir), cache_headers=False)]
    )
    # Cards load automatically on every dashboard — no manual resource needed.
    add_extra_js_url(hass, f"{FRONTEND_URL_BASE}/{FRONTEND_FILE}?v={VERSION}")
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
