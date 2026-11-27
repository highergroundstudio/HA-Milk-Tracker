"""Buttons for Milk Tracker."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MilkTrackerConfigEntry
from .entity import MilkTrackerEntity
from .tracker import MilkTrackerError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MilkTrackerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities([UndoButton(c, "undo"), DiscardExpiredButton(c, "discard_expired")])


class UndoButton(MilkTrackerEntity, ButtonEntity):
    _attr_icon = "mdi:undo-variant"

    async def async_press(self) -> None:
        try:
            entry = self.coordinator.tracker.undo()
        except MilkTrackerError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_commit({**entry, "undone": True})


class DiscardExpiredButton(MilkTrackerEntity, ButtonEntity):
    _attr_icon = "mdi:delete-clock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        entry = self.coordinator.tracker.discard_expired(dt_util.utcnow())
        await self.coordinator.async_commit(entry)
