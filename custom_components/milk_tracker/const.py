"""Constants for the Milk Tracker integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "milk_tracker"
STORAGE_VERSION: Final = 1

# Config entry data / options
CONF_BABY_NAME: Final = "baby_name"
CONF_UNIT: Final = "unit"
CONF_INITIAL_FRIDGE: Final = "initial_fridge"
CONF_INITIAL_FREEZER: Final = "initial_freezer"
CONF_DAILY_INTAKE: Final = "daily_intake"
CONF_INTAKE_MODE: Final = "intake_mode"
CONF_FRIDGE_DAYS: Final = "fridge_days"
CONF_FREEZER_DAYS: Final = "freezer_days"
CONF_EXPIRY_WARNING_HOURS: Final = "expiry_warning_hours"
CONF_PUMP_INTERVAL_HOURS: Final = "pump_interval_hours"

UNIT_OZ: Final = "oz"
UNIT_ML: Final = "ml"
ML_PER_OZ: Final = 29.5735

INTAKE_FIXED: Final = "fixed"
INTAKE_AUTO: Final = "auto"

# CDC guidance: fridge up to 4 days, freezer best within 6 months.
DEFAULT_FRIDGE_DAYS: Final = 4
DEFAULT_FREEZER_DAYS: Final = 180
DEFAULT_EXPIRY_WARNING_HOURS: Final = 24
DEFAULT_PUMP_INTERVAL_HOURS: Final = 4.0
DEFAULT_DAILY_INTAKE_OZ: Final = 25.0
DEFAULT_DAILY_INTAKE_ML: Final = 750.0

LOC_FRIDGE: Final = "fridge"
LOC_FREEZER: Final = "freezer"
LOCATIONS: Final = [LOC_FRIDGE, LOC_FREEZER]
SOURCE_AUTO: Final = "auto"

# Log entry kinds
KIND_PUMP: Final = "pump"
KIND_FEED: Final = "feed"
KIND_DISCARD: Final = "discard"
KIND_FREEZE: Final = "freeze"
KIND_THAW: Final = "thaw"
KIND_ADJUST: Final = "adjust"

# Services
SERVICE_LOG_PUMP: Final = "log_pump"
SERVICE_LOG_FEED: Final = "log_feed"
SERVICE_DISCARD: Final = "discard"
SERVICE_DISCARD_EXPIRED: Final = "discard_expired"
SERVICE_MOVE: Final = "move"
SERVICE_SET_STASH: Final = "set_stash"
SERVICE_UNDO: Final = "undo"
SERVICE_DELETE_ENTRY: Final = "delete_entry"
SERVICE_CONFIGURE: Final = "configure"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_AMOUNT: Final = "amount"
ATTR_LOCATION: Final = "location"
ATTR_SOURCE: Final = "source"
ATTR_DESTINATION: Final = "destination"
ATTR_TIMESTAMP: Final = "timestamp"
ATTR_NOTE: Final = "note"
ATTR_ENTRY_ID: Final = "entry_id"
ATTR_BATCH_ID: Final = "batch_id"
ATTR_DURATION: Final = "duration_minutes"

EVENT_MILK_LOGGED: Final = "milk_tracker_logged"

FRONTEND_URL_BASE: Final = "/milk_tracker_static"
FRONTEND_FILE: Final = "milk-tracker-cards.js"

HISTORY_DAYS: Final = 30
LOG_LIMIT: Final = 2000
