"""Date entity (goal date) for Milk Tracker."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MilkTrackerConfigEntry
from .entity import MilkTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MilkTrackerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([GoalDate(entry.runtime_data, "goal_date")])


class GoalDate(MilkTrackerEntity, DateEntity):
    _attr_icon = "mdi:calendar-star"

    @property
    def native_value(self) -> date | None:
        value = self.coordinator.tracker.get_setting("goal_date")
        return date.fromisoformat(value) if value else None

    async def async_set_value(self, value: date) -> None:
        self.coordinator.tracker.set_setting("goal_date", value.isoformat())
        await self.coordinator.async_commit()
