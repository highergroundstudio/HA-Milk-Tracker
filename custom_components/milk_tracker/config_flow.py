"""Config flow for Milk Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_BABY_NAME,
    CONF_DAILY_INTAKE,
    CONF_EXPIRY_WARNING_HOURS,
    CONF_FREEZER_DAYS,
    CONF_FRIDGE_DAYS,
    CONF_INITIAL_FREEZER,
    CONF_INITIAL_FRIDGE,
    CONF_INTAKE_MODE,
    CONF_PUMP_INTERVAL_HOURS,
    CONF_UNIT,
    DEFAULT_DAILY_INTAKE_ML,
    DEFAULT_DAILY_INTAKE_OZ,
    DEFAULT_EXPIRY_WARNING_HOURS,
    DEFAULT_FREEZER_DAYS,
    DEFAULT_FRIDGE_DAYS,
    DEFAULT_PUMP_INTERVAL_HOURS,
    DOMAIN,
    INTAKE_AUTO,
    INTAKE_FIXED,
    UNIT_ML,
    UNIT_OZ,
)


def _num(min_: float, max_: float, step: float, unit: str | None = None) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=min_, max=max_, step=step, mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


class MilkTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step setup: who + unit, then your current stash."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            name = (user_input.get(CONF_BABY_NAME) or "").strip()
            self._data[CONF_BABY_NAME] = name
            await self.async_set_unique_id(f"{DOMAIN}_{name.lower() or 'default'}")
            self._abort_if_unique_id_configured()
            return await self.async_step_stash()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_BABY_NAME, default=""): TextSelector(),
                    vol.Required(CONF_UNIT, default=UNIT_OZ): SelectSelector(
                        SelectSelectorConfig(
                            options=[UNIT_OZ, UNIT_ML],
                            translation_key=CONF_UNIT,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_stash(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        unit = self._data[CONF_UNIT]
        if user_input is not None:
            self._data.update(user_input)
            name = self._data[CONF_BABY_NAME]
            title = f"{name}'s milk" if name else "Milk Tracker"
            return self.async_create_entry(title=title, data=self._data)

        ml = unit == UNIT_ML
        big = 50000 if ml else 2000
        return self.async_show_form(
            step_id="stash",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INITIAL_FRIDGE, default=0): _num(0, big, 0.1, unit),
                    vol.Required(CONF_INITIAL_FREEZER, default=0): _num(0, big, 0.1, unit),
                    vol.Required(
                        CONF_DAILY_INTAKE,
                        default=DEFAULT_DAILY_INTAKE_ML if ml else DEFAULT_DAILY_INTAKE_OZ,
                    ): _num(0, 3000 if ml else 100, 0.5, f"{unit}/day"),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MilkTrackerOptionsFlow()


class MilkTrackerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        o = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTAKE_MODE, default=o.get(CONF_INTAKE_MODE, INTAKE_FIXED)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[INTAKE_FIXED, INTAKE_AUTO],
                            translation_key=CONF_INTAKE_MODE,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(
                        CONF_PUMP_INTERVAL_HOURS,
                        default=o.get(CONF_PUMP_INTERVAL_HOURS, DEFAULT_PUMP_INTERVAL_HOURS),
                    ): _num(0.5, 24, 0.5, "h"),
                    vol.Required(
                        CONF_FRIDGE_DAYS, default=o.get(CONF_FRIDGE_DAYS, DEFAULT_FRIDGE_DAYS)
                    ): _num(1, 8, 0.5, "d"),
                    vol.Required(
                        CONF_FREEZER_DAYS, default=o.get(CONF_FREEZER_DAYS, DEFAULT_FREEZER_DAYS)
                    ): _num(30, 365, 1, "d"),
                    vol.Required(
                        CONF_EXPIRY_WARNING_HOURS,
                        default=o.get(CONF_EXPIRY_WARNING_HOURS, DEFAULT_EXPIRY_WARNING_HOURS),
                    ): _num(1, 168, 1, "h"),
                }
            ),
        )
