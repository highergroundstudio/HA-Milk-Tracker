"""Service actions for Milk Tracker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_AMOUNT,
    ATTR_BATCH_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DESTINATION,
    ATTR_DURATION,
    ATTR_ENTRY_ID,
    ATTR_LOCATION,
    ATTR_NOTE,
    ATTR_PUMPED_AT,
    ATTR_REPLACE_UNDATED,
    ATTR_SOURCE,
    ATTR_TIMESTAMP,
    DOMAIN,
    LOC_FREEZER,
    LOC_FRIDGE,
    LOCATIONS,
    SERVICE_ADD_STORED,
    SERVICE_CONFIGURE,
    SERVICE_DELETE_ENTRY,
    SERVICE_DISCARD,
    SERVICE_DISCARD_EXPIRED,
    SERVICE_LOG_FEED,
    SERVICE_LOG_PUMP,
    SERVICE_MOVE,
    SERVICE_SET_STASH,
    SERVICE_UNDO,
    SOURCE_AUTO,
)
from .coordinator import MilkTrackerCoordinator
from .tracker import MilkTrackerError

_AMOUNT = vol.All(vol.Coerce(float), vol.Range(min=0.01, max=10000))
_BASE = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

PUMP_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Required(ATTR_AMOUNT): _AMOUNT,
        vol.Optional(ATTR_LOCATION): vol.In(LOCATIONS),
        vol.Optional(ATTR_TIMESTAMP): cv.datetime,
        vol.Optional(ATTR_NOTE): cv.string,
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(float), vol.Range(min=0, max=600)),
    }
)
FEED_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Required(ATTR_AMOUNT): _AMOUNT,
        vol.Optional(ATTR_SOURCE, default=SOURCE_AUTO): vol.In([SOURCE_AUTO, *LOCATIONS]),
        vol.Optional(ATTR_TIMESTAMP): cv.datetime,
        vol.Optional(ATTR_NOTE): cv.string,
    }
)
DISCARD_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Optional(ATTR_AMOUNT): _AMOUNT,
        vol.Optional(ATTR_SOURCE, default=SOURCE_AUTO): vol.In([SOURCE_AUTO, *LOCATIONS]),
        vol.Optional(ATTR_BATCH_ID): vol.Any(cv.string, [cv.string]),
        vol.Optional(ATTR_NOTE): cv.string,
    }
)
MOVE_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Optional(ATTR_AMOUNT): _AMOUNT,
        vol.Optional(ATTR_SOURCE, default=LOC_FRIDGE): vol.In(LOCATIONS),
        vol.Optional(ATTR_DESTINATION): vol.In(LOCATIONS),
        vol.Optional(ATTR_BATCH_ID): vol.Any(cv.string, [cv.string]),
    }
)
SET_STASH_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Optional(LOC_FRIDGE): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(LOC_FREEZER): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)
UNDO_SCHEMA = vol.Schema(_BASE)
ADD_STORED_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Required(ATTR_AMOUNT): _AMOUNT,
        vol.Required(ATTR_PUMPED_AT): vol.Any(cv.datetime, cv.date),
        vol.Optional(ATTR_LOCATION): vol.In(LOCATIONS),
        vol.Optional(ATTR_REPLACE_UNDATED, default=True): cv.boolean,
        vol.Optional(ATTR_NOTE): cv.string,
    }
)
CONFIGURE_SCHEMA = vol.Schema(
    {
        **_BASE,
        vol.Optional("goal_active"): cv.boolean,
        vol.Optional("goal_amount"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional("goal_date"): vol.Any(None, cv.date),
        vol.Optional("goal_name"): vol.All(cv.string, vol.Length(max=40)),
        vol.Optional("daily_intake"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)
DELETE_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_ENTRY_ID): cv.string})
EXPIRED_SCHEMA = vol.Schema(_BASE)


def get_coordinator(hass: HomeAssistant, config_entry_id: str | None) -> MilkTrackerCoordinator:
    """Resolve the tracker to act on (defaults to the only/first one)."""
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if config_entry_id:
        entries = [e for e in entries if e.entry_id == config_entry_id]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_tracker"
        )
    return entries[0].runtime_data


def _ts(call: ServiceCall):
    ts = call.data.get(ATTR_TIMESTAMP)
    if ts is None:
        return dt_util.utcnow()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(ts)


def _strip(entry: dict[str, Any] | None) -> dict[str, Any]:
    if entry is None:
        return {}
    return {k: v for k, v in entry.items() if k != "ops"}


async def _run(
    hass: HomeAssistant,
    call: ServiceCall,
    action: Callable[[MilkTrackerCoordinator], dict[str, Any] | None],
) -> ServiceResponse:
    coordinator = get_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    try:
        entry = action(coordinator)
    except MilkTrackerError as err:
        raise ServiceValidationError(str(err)) from err
    await coordinator.async_commit(entry)
    return {"entry": _strip(entry), "summary": {
        k: v for k, v in (coordinator.data or {}).items() if k not in ("history", "batches")
    }}


def async_setup_services(hass: HomeAssistant) -> None:
    def register(
        name: str,
        schema: vol.Schema,
        action: Callable[[ServiceCall, MilkTrackerCoordinator], dict[str, Any] | None],
    ) -> None:
        async def handler(call: ServiceCall) -> ServiceResponse:
            return await _run(hass, call, lambda c: action(call, c))

        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=SupportsResponse.OPTIONAL
        )

    register(
        SERVICE_LOG_PUMP,
        PUMP_SCHEMA,
        lambda call, c: c.tracker.pump(
            call.data[ATTR_AMOUNT],
            _ts(call),
            location=call.data.get(ATTR_LOCATION) or c.default_location,
            note=call.data.get(ATTR_NOTE),
            duration=call.data.get(ATTR_DURATION),
        ),
    )
    register(
        SERVICE_LOG_FEED,
        FEED_SCHEMA,
        lambda call, c: c.tracker.feed(
            call.data[ATTR_AMOUNT],
            _ts(call),
            source=call.data[ATTR_SOURCE],
            note=call.data.get(ATTR_NOTE),
        ),
    )
    register(
        SERVICE_DISCARD,
        DISCARD_SCHEMA,
        lambda call, c: c.tracker.discard(
            call.data.get(ATTR_AMOUNT),
            dt_util.utcnow(),
            source=call.data[ATTR_SOURCE],
            batch_id=call.data.get(ATTR_BATCH_ID),
            note=call.data.get(ATTR_NOTE),
        ),
    )
    register(
        SERVICE_DISCARD_EXPIRED,
        EXPIRED_SCHEMA,
        lambda call, c: c.tracker.discard_expired(dt_util.utcnow()),
    )

    def _move(call: ServiceCall, c: MilkTrackerCoordinator) -> dict[str, Any]:
        source = call.data[ATTR_SOURCE]
        if call.data.get(ATTR_BATCH_ID):
            source = c.tracker._batches(call.data[ATTR_BATCH_ID])[0]["location"]  # noqa: SLF001
        destination = call.data.get(ATTR_DESTINATION) or (
            LOC_FRIDGE if source == LOC_FREEZER else LOC_FREEZER
        )
        return c.tracker.move(
            call.data.get(ATTR_AMOUNT),
            dt_util.utcnow(),
            source=source,
            destination=destination,
            batch_id=call.data.get(ATTR_BATCH_ID),
        )

    register(SERVICE_MOVE, MOVE_SCHEMA, _move)

    def _set_stash(call: ServiceCall, c: MilkTrackerCoordinator) -> dict[str, Any] | None:
        now = dt_util.utcnow()
        last = None
        for loc in LOCATIONS:
            if loc in call.data:
                last = c.tracker.set_stash(loc, call.data[loc], now) or last
        return last

    register(SERVICE_SET_STASH, SET_STASH_SCHEMA, _set_stash)
    def _configure(call: ServiceCall, c: MilkTrackerCoordinator) -> dict[str, Any] | None:
        for key in ("goal_active", "goal_amount", "goal_name", "daily_intake"):
            if key in call.data:
                c.tracker.set_setting(key, call.data[key])
        if "goal_date" in call.data:
            value = call.data["goal_date"]
            c.tracker.set_setting("goal_date", value.isoformat() if value else None)
        return None

    register(SERVICE_CONFIGURE, CONFIGURE_SCHEMA, _configure)

    def _add_stored(call: ServiceCall, c: MilkTrackerCoordinator) -> dict[str, Any]:
        pumped = call.data[ATTR_PUMPED_AT]
        date_only = not isinstance(pumped, datetime)
        if date_only:
            # A bare date: assume noon local time so it lands on the right day.
            pumped = datetime.combine(pumped, time(12, 0))
        if pumped.tzinfo is None:
            pumped = pumped.replace(tzinfo=dt_util.get_default_time_zone())
        pumped = dt_util.as_utc(pumped)
        if pumped > dt_util.utcnow():
            raise MilkTrackerError("The pumped date can't be in the future")
        return c.tracker.add_stored(
            call.data[ATTR_AMOUNT],
            pumped,
            dt_util.utcnow(),
            location=call.data.get(ATTR_LOCATION) or LOC_FREEZER,
            replace_undated=call.data[ATTR_REPLACE_UNDATED],
            note=call.data.get(ATTR_NOTE),
            date_only=date_only,
        )

    register(SERVICE_ADD_STORED, ADD_STORED_SCHEMA, _add_stored)
    register(SERVICE_UNDO, UNDO_SCHEMA, lambda call, c: {**c.tracker.undo(), "undone": True})
    register(
        SERVICE_DELETE_ENTRY,
        DELETE_SCHEMA,
        lambda call, c: {**c.tracker.undo(call.data[ATTR_ENTRY_ID]), "undone": True},
    )
