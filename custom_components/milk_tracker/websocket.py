"""Websocket API used by the bundled Lovelace cards."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


def _loaded(hass: HomeAssistant):
    return [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_subscribe)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list"})
@callback
def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """List configured trackers (used by the card editors)."""
    connection.send_result(
        msg["id"],
        [
            {"entry_id": e.entry_id, "title": e.title, "name": e.runtime_data.baby_name,
             "unit": e.runtime_data.unit}
            for e in _loaded(hass)
        ],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/subscribe",
        vol.Optional("entry_id"): str,
        vol.Optional("log_limit", default=50): vol.All(int, vol.Range(min=0, max=500)),
    }
)
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Push the full tracker state now and whenever it changes."""
    entries = _loaded(hass)
    if msg.get("entry_id"):
        entries = [e for e in entries if e.entry_id == msg["entry_id"]]
    if not entries:
        connection.send_error(msg["id"], "not_found", "No Milk Tracker is set up")
        return
    coordinator = entries[0].runtime_data
    limit = msg["log_limit"]

    @callback
    def _push() -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], coordinator.frontend_payload(limit))
        )

    unsub = coordinator.async_add_listener(_push)
    connection.subscriptions[msg["id"]] = unsub
    connection.send_result(msg["id"])
    _push()
