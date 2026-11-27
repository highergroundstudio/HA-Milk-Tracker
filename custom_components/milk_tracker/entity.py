"""Base entity for Milk Tracker."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MilkTrackerCoordinator


class MilkTrackerEntity(CoordinatorEntity[MilkTrackerCoordinator]):
    """Groups every entity under one service device per tracker."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MilkTrackerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Milk Tracker",
            model="Breast milk stash",
            entry_type=DeviceEntryType.SERVICE,
        )
