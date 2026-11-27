"""Switch for Milk Tracker (goal tracking on/off)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MilkTrackerConfigEntry
from .entity import MilkTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MilkTrackerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([GoalSwitch(entry.runtime_data, "goal_active")])


class GoalSwitch(MilkTrackerEntity, SwitchEntity):
    _attr_icon = "mdi:airplane"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.tracker.get_setting("goal_active", False))

    async def _set(self, value: bool) -> None:
        self.coordinator.tracker.set_setting("goal_active", value)
        await self.coordinator.async_commit()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
