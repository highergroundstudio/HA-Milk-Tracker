"""Integration tests against a real Home Assistant instance."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.milk_tracker.const import DOMAIN


async def _setup(hass: HomeAssistant):
    with patch("custom_components.milk_tracker.cards.add_extra_js_url"):
        assert await async_setup_component(hass, "http", {})
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"baby_name": "Ava", "unit": "oz"}
        )
        assert result["step_id"] == "stash"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"initial_fridge": 6, "initial_freezer": 20, "daily_intake": 24}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    return result["result"]


async def test_full_flow(hass: HomeAssistant, hass_ws_client) -> None:
    entry = await _setup(hass)
    assert entry.title == "Ava's milk"

    stash = hass.states.get("sensor.ava_s_milk_stash")
    assert stash is not None, sorted(hass.states.async_entity_ids())
    assert float(stash.state) == 26
    assert float(hass.states.get("sensor.ava_s_milk_fridge").state) == 6
    assert hass.states.get("sensor.ava_s_milk_goal_progress").state == "unavailable"

    resp = await hass.services.async_call(
        DOMAIN, "log_pump", {"amount": 4, "location": "fridge"}, blocking=True, return_response=True
    )
    pump_id = resp["entry"]["id"]
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_stash").state) == 30
    assert float(hass.states.get("sensor.ava_s_milk_pumped_today").state) == 4

    await hass.services.async_call(DOMAIN, "log_feed", {"amount": 3}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_fridge").state) == 7

    await hass.services.async_call(DOMAIN, "delete_entry", {"entry_id": pump_id}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_stash").state) == 23

    await hass.services.async_call(
        DOMAIN, "configure",
        {"goal_active": True, "goal_amount": 46, "goal_date": "2099-01-01", "goal_name": "Trip"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_goal_progress").state) == 50
    assert hass.states.get("switch.ava_s_milk_goal_tracking").state == "on"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.ava_s_milk_daily_intake", "value": 23},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_days_of_supply").state) == 1

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.ava_s_milk_undo_last_entry"}, blocking=True
    )
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_stash").state) == 26

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    msg = await client.receive_json()
    assert msg["success"]
    msg = await client.receive_json()
    assert msg["type"] == "event"
    assert msg["event"]["summary"]["total"] == 26
    assert msg["event"]["unit"] == "oz"

    await hass.services.async_call(DOMAIN, "log_pump", {"amount": 2}, blocking=True)
    msg = await client.receive_json()
    assert msg["event"]["summary"]["total"] == 28
    assert msg["event"]["log"][0]["kind"] == "pump"

    # Options flow
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"use_fridge": False, "default_location": "fridge", "intake_mode": "auto",
         "pump_interval_hours": 3, "fridge_days": 4, "freezer_days": 180,
         "expiry_warning_hours": 12},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()
    freezer_before = float(hass.states.get("sensor.ava_s_milk_freezer").state)
    # Fridge turned off -> pumps without a location go to the freezer.
    await hass.services.async_call(DOMAIN, "log_pump", {"amount": 3}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_freezer").state) == freezer_before + 3

    # Date existing freezer milk without changing the total.
    resp = await hass.services.async_call(
        DOMAIN, "add_stored", {"amount": 5, "pumped_at": "2026-10-01"},
        blocking=True, return_response=True,
    )
    assert resp["entry"]["replaced"] == 5
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ava_s_milk_freezer").state) == freezer_before + 3

    await client.send_json({"id": 2, "type": f"{DOMAIN}/subscribe"})
    msg = await client.receive_json()
    msg = await client.receive_json()
    assert msg["event"]["use_fridge"] is False
    assert msg["event"]["default_location"] == "freezer"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_cards_served_fresh(hass: HomeAssistant, hass_client_no_auth) -> None:
    """Cards are re-validated by ETag so card-only updates need no restart."""
    await _setup(hass)
    client = await hass_client_no_auth()
    resp = await client.get("/milk_tracker_static/milk-tracker-cards.js")
    assert resp.status == 200
    assert resp.headers["Cache-Control"] == "no-cache"
    assert "customElements.define" in await resp.text()
    etag = resp.headers["ETag"]
    resp = await client.get(
        "/milk_tracker_static/milk-tracker-cards.js", headers={"If-None-Match": etag}
    )
    assert resp.status == 304

    # Simulate HACS replacing the file on disk (no restart).
    from custom_components.milk_tracker import cards as frontend

    original = frontend.CARDS_PATH.read_bytes()
    try:
        frontend.CARDS_PATH.write_bytes(original + b"\n// updated\n")
        import os
        import time

        os.utime(frontend.CARDS_PATH, (time.time() + 5, time.time() + 5))
        resp = await client.get(
            "/milk_tracker_static/milk-tracker-cards.js", headers={"If-None-Match": etag}
        )
        assert resp.status == 200
        assert resp.headers["ETag"] != etag
        assert (await resp.text()).endswith("// updated\n")
    finally:
        frontend.CARDS_PATH.write_bytes(original)
