"""Sensors for Milk Tracker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import UNIT_ML
from .coordinator import MilkTrackerConfigEntry, MilkTrackerCoordinator
from .entity import MilkTrackerEntity

VOLUME = "volume"
RATE = "rate"


def _ts(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


@dataclass(frozen=True, kw_only=True)
class MilkSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    unit_kind: str | None = None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    goal: bool = False


def _goal(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d["goal"].get(key) if d["goal"].get("amount") else None


SENSORS: tuple[MilkSensorDescription, ...] = (
    MilkSensorDescription(
        key="stash",
        icon="mdi:baby-bottle",
        unit_kind=VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d["total"],
        attrs_fn=lambda d: {"fridge": d["fridge"], "freezer": d["freezer"],
                            "batches": len(d["batches"])},
    ),
    MilkSensorDescription(
        key="fridge", icon="mdi:fridge-outline", unit_kind=VOLUME,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=lambda d: d["fridge"],
    ),
    MilkSensorDescription(
        key="freezer", icon="mdi:snowflake", unit_kind=VOLUME,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=lambda d: d["freezer"],
    ),
    MilkSensorDescription(
        key="pumped_today", icon="mdi:water-plus", unit_kind=VOLUME,
        state_class=SensorStateClass.TOTAL, suggested_display_precision=1,
        value_fn=lambda d: d["pumped_today"],
        attrs_fn=lambda d: {"sessions": d["sessions_today"]},
    ),
    MilkSensorDescription(
        key="fed_today", icon="mdi:water-minus", unit_kind=VOLUME,
        state_class=SensorStateClass.TOTAL, suggested_display_precision=1,
        value_fn=lambda d: d["fed_today"],
        attrs_fn=lambda d: {"feeds": d["feeds_today"]},
    ),
    MilkSensorDescription(
        key="pumped_last_7_days", icon="mdi:chart-bar", unit_kind=VOLUME,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=lambda d: d["pumped_7d"],
    ),
    MilkSensorDescription(
        key="avg_pumped_per_day", icon="mdi:chart-line", unit_kind=RATE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=lambda d: d["avg_pumped_per_day"],
    ),
    MilkSensorDescription(
        key="avg_fed_per_day", icon="mdi:chart-line-variant", unit_kind=RATE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=lambda d: d["avg_fed_per_day"],
    ),
    MilkSensorDescription(
        key="days_of_supply", icon="mdi:calendar-clock",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=lambda d: d["days_of_supply"],
        attrs_fn=lambda d: {"daily_intake": d["daily_intake"], "auto": d["intake_is_auto"]},
    ),
    MilkSensorDescription(
        key="last_pumped", icon="mdi:clock-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _ts(d["last_pump"]),
        attrs_fn=lambda d: {"amount": d["last_pump_amount"],
                            "next_due": d["next_pump_due"]},
    ),
    MilkSensorDescription(
        key="last_fed", icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _ts(d["last_feed"]),
    ),
    MilkSensorDescription(
        key="next_expiry", icon="mdi:timer-sand",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _ts(d["next_expiry"]),
        attrs_fn=lambda d: {"expiring_soon": d["expiring_amount"],
                            "expired": d["expired_amount"]},
    ),
    MilkSensorDescription(
        key="goal_progress", icon="mdi:bullseye-arrow",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
        value_fn=_goal("progress"), goal=True,
        attrs_fn=lambda d: {k: v for k, v in d["goal"].items() if k != "progress"},
    ),
    MilkSensorDescription(
        key="goal_remaining", icon="mdi:flag-checkered", unit_kind=VOLUME,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=_goal("remaining"), goal=True,
    ),
    MilkSensorDescription(
        key="goal_needed_per_day", icon="mdi:speedometer", unit_kind=RATE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=_goal("needed_per_day"), goal=True,
    ),
    MilkSensorDescription(
        key="days_until_goal", icon="mdi:airplane-clock",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=_goal("days_left"), goal=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MilkTrackerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MilkSensor(coordinator, desc) for desc in SENSORS)


class MilkSensor(MilkTrackerEntity, SensorEntity):
    entity_description: MilkSensorDescription

    def __init__(self, coordinator: MilkTrackerCoordinator, description: MilkSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.unit_kind is not None:
            # Stash volumes use volume_storage; HA does not allow unit conversion
            # on "per day" rates so those stay plain.
            base = (
                UnitOfVolume.MILLILITERS if coordinator.unit == UNIT_ML else UnitOfVolume.FLUID_OUNCES
            )
            if description.unit_kind == VOLUME:
                self._attr_native_unit_of_measurement = base
                # Keep the unit the user chose even on a metric/imperial system.
                self._attr_suggested_unit_of_measurement = base
                self._attr_device_class = (
                    SensorDeviceClass.VOLUME
                    if description.state_class == SensorStateClass.TOTAL
                    else SensorDeviceClass.VOLUME_STORAGE
                )
            else:
                self._attr_native_unit_of_measurement = f"{coordinator.unit}/d"

    @property
    def native_value(self) -> float | datetime | date | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if self.entity_description.goal and not self.coordinator.data["goal"].get("active"):
            return False
        return super().available

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
