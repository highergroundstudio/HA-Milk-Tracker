"""Data coordinator for Milk Tracker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BABY_NAME,
    CONF_DAILY_INTAKE,
    CONF_DEFAULT_LOCATION,
    CONF_EXPIRY_WARNING_HOURS,
    CONF_FREEZER_DAYS,
    CONF_FRIDGE_DAYS,
    CONF_INITIAL_FREEZER,
    CONF_INITIAL_FRIDGE,
    CONF_INTAKE_MODE,
    CONF_PUMP_INTERVAL_HOURS,
    CONF_UNIT,
    CONF_USE_FRIDGE,
    DEFAULT_DAILY_INTAKE_OZ,
    DEFAULT_EXPIRY_WARNING_HOURS,
    DEFAULT_FREEZER_DAYS,
    DEFAULT_FRIDGE_DAYS,
    DEFAULT_PUMP_INTERVAL_HOURS,
    DOMAIN,
    EVENT_MILK_LOGGED,
    INTAKE_AUTO,
    INTAKE_FIXED,
    LOC_FREEZER,
    LOC_FRIDGE,
    STORAGE_VERSION,
    UNIT_OZ,
)
from .tracker import MilkTracker

_LOGGER = logging.getLogger(__name__)

type MilkTrackerConfigEntry = ConfigEntry["MilkTrackerCoordinator"]


class MilkTrackerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns the persistent tracker and publishes a computed summary."""

    config_entry: MilkTrackerConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MilkTrackerConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            # Periodic refresh keeps "time since", expiry and pump-due fresh.
            update_interval=timedelta(minutes=1),
            always_update=False,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.tracker = MilkTracker()
        self._unsub_midnight: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------ #
    @property
    def unit(self) -> str:
        return self.config_entry.data.get(CONF_UNIT, UNIT_OZ)

    @property
    def baby_name(self) -> str:
        return self.config_entry.data.get(CONF_BABY_NAME) or "Baby"

    @property
    def use_fridge(self) -> bool:
        return bool(self._opt(CONF_USE_FRIDGE, True))

    @property
    def default_location(self) -> str:
        """Where new pumps go when no location is given."""
        if not self.use_fridge:
            return LOC_FREEZER
        return self._opt(CONF_DEFAULT_LOCATION, LOC_FREEZER)

    def _opt(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    def apply_options(self) -> None:
        self.tracker.fridge_days = float(self._opt(CONF_FRIDGE_DAYS, DEFAULT_FRIDGE_DAYS))
        self.tracker.freezer_days = float(self._opt(CONF_FREEZER_DAYS, DEFAULT_FREEZER_DAYS))

    # ------------------------------------------------------------------ #
    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data is None:
            # First run: seed the stash with whatever the user already has.
            self.tracker = MilkTracker()
            now = dt_util.utcnow()
            fridge = float(self.config_entry.data.get(CONF_INITIAL_FRIDGE, 0) or 0)
            freezer = float(self.config_entry.data.get(CONF_INITIAL_FREEZER, 0) or 0)
            if fridge > 0:
                self.tracker.set_stash(LOC_FRIDGE, fridge, now)
            if freezer > 0:
                self.tracker.set_stash(LOC_FREEZER, freezer, now)
            # Starting stash shouldn't appear as a correction in the log.
            self.tracker.log.clear()
            for batch in self.tracker.batches:
                batch["note"] = "Starting stash"
            self.tracker.set_setting(
                "daily_intake",
                float(self.config_entry.data.get(CONF_DAILY_INTAKE, DEFAULT_DAILY_INTAKE_OZ)),
            )
            await self._store.async_save(self.tracker.as_dict())
        else:
            self.tracker = MilkTracker(data)
        self.apply_options()

        @callback
        def _midnight(_now: datetime) -> None:
            self.async_set_updated_data(self.compute())

        self._unsub_midnight = async_track_time_change(
            self.hass, _midnight, hour=0, minute=0, second=1
        )

    @callback
    def async_shutdown_listeners(self) -> None:
        if self._unsub_midnight:
            self._unsub_midnight()
            self._unsub_midnight = None

    def compute(self) -> dict[str, Any]:
        intake_mode = self._opt(CONF_INTAKE_MODE, INTAKE_FIXED)
        return self.tracker.summary(
            dt_util.utcnow(),
            dt_util.get_default_time_zone(),
            fixed_intake=float(self.tracker.get_setting("daily_intake", DEFAULT_DAILY_INTAKE_OZ)),
            auto_intake=intake_mode == INTAKE_AUTO,
            expiry_warning_hours=float(
                self._opt(CONF_EXPIRY_WARNING_HOURS, DEFAULT_EXPIRY_WARNING_HOURS)
            ),
            pump_interval_hours=float(
                self._opt(CONF_PUMP_INTERVAL_HOURS, DEFAULT_PUMP_INTERVAL_HOURS)
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        return self.compute()

    async def async_commit(self, entry: dict[str, Any] | None = None) -> None:
        """Persist changes, refresh entities, and fire an event for automations."""
        await self._store.async_save(self.tracker.as_dict())
        self.async_set_updated_data(self.compute())
        if entry is not None:
            self.hass.bus.async_fire(
                EVENT_MILK_LOGGED,
                {
                    "config_entry_id": self.config_entry.entry_id,
                    "kind": entry.get("kind"),
                    "amount": entry.get("amount"),
                    "location": entry.get("location"),
                    "entry_id": entry.get("id"),
                    "unit": self.unit,
                    "undone": bool(entry.get("undone")),
                },
            )

    async def async_remove_store(self) -> None:
        await self._store.async_remove()

    def recent_log(self, limit: int = 50) -> list[dict[str, Any]]:
        entries = sorted(self.tracker.log, key=lambda e: e["ts"], reverse=True)[:limit]
        return [{k: v for k, v in e.items() if k != "ops"} for e in entries]

    def frontend_payload(self, log_limit: int = 50) -> dict[str, Any]:
        return {
            "entry_id": self.config_entry.entry_id,
            "name": self.baby_name,
            "title": self.config_entry.title,
            "unit": self.unit,
            "fridge_days": self.tracker.fridge_days,
            "freezer_days": self.tracker.freezer_days,
            "use_fridge": self.use_fridge,
            "default_location": self.default_location,
            "summary": self.data or self.compute(),
            "log": self.recent_log(log_limit),
        }

    def add_payload_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        return self.async_add_listener(cb)
