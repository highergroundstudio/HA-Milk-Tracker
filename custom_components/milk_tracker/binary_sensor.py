"""Binary sensors for Milk Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MilkTrackerConfigEntry
from .entity import MilkTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MilkTrackerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities([PumpDueSensor(c, "pump_due"), ExpiringSensor(c, "milk_expiring")])


class PumpDueSensor(MilkTrackerEntity, BinarySensorEntity):
    """On when it has been longer than the configured interval since pumping."""

    _attr_icon = "mdi:bell-ring-outline"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["pump_due"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {"hours_since_pump": d["hours_since_pump"], "next_due": d["next_pump_due"],
                "interval_hours": d["pump_interval_hours"]}


class ExpiringSensor(MilkTrackerEntity, BinarySensorEntity):
    """On when milk is expiring soon or already expired."""

    _attr_icon = "mdi:alert-circle-outline"

    @property
    def is_on(self) -> bool:
        d = self.coordinator.data
        return d["expiring_amount"] > 0 or d["expired_amount"] > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {"expiring_soon": d["expiring_amount"], "expired": d["expired_amount"],
                "next_expiry": d["next_expiry"]}
