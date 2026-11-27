"""Number entities (settings) for Milk Tracker."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UNIT_ML
from .coordinator import MilkTrackerConfigEntry, MilkTrackerCoordinator
from .entity import MilkTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MilkTrackerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    ml = c.unit == UNIT_ML
    async_add_entities(
        [
            SettingNumber(c, "daily_intake", max_value=3000 if ml else 100,
                          step=5 if ml else 0.5, category=EntityCategory.CONFIG),
            SettingNumber(c, "goal_amount", max_value=60000 if ml else 2000,
                          step=10 if ml else 1, category=None),
        ]
    )


class SettingNumber(MilkTrackerEntity, NumberEntity):
    """A setting persisted in the tracker store."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0

    def __init__(self, coordinator: MilkTrackerCoordinator, key: str, *,
                 max_value: float, step: float, category: EntityCategory | None) -> None:
        super().__init__(coordinator, key)
        self._key = key
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = coordinator.unit + ("/d" if key == "daily_intake" else "")
        self._attr_entity_category = category
        self._attr_icon = "mdi:baby-bottle-outline" if key == "daily_intake" else "mdi:bullseye"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.tracker.get_setting(self._key, 0) or 0)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.tracker.set_setting(self._key, float(value))
        await self.coordinator.async_commit()
