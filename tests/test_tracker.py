"""Unit tests for the pure stash model."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.milk_tracker.tracker import MilkTracker, MilkTrackerError

UTC = UTC
T0 = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)


def summary(t: MilkTracker, now=None, **kw):
    args = dict(fixed_intake=24, auto_intake=False, expiry_warning_hours=24, pump_interval_hours=4)
    args.update(kw)
    return t.summary(now or T0, UTC, **args)


def test_pump_and_feed_fifo():
    t = MilkTracker()
    t.pump(4, T0, location="fridge")
    t.pump(3, T0 + timedelta(hours=3), location="fridge")
    t.pump(5, T0, location="freezer")
    feed = t.feed(5, T0 + timedelta(hours=5))
    assert feed["from_stash"] == 5
    assert t.amount_in("fridge") == pytest.approx(2)  # oldest 4 gone, 1 taken from second
    assert t.amount_in("freezer") == 5
    s = summary(t, T0 + timedelta(hours=6))
    assert s["total"] == 7
    assert s["pumped_today"] == 12
    assert s["fed_today"] == 5
    assert s["sessions_today"] == 3


def test_feed_more_than_stash_records_full_amount():
    t = MilkTracker()
    t.pump(2, T0)
    e = t.feed(5, T0 + timedelta(minutes=5))
    assert e["amount"] == 5 and e["from_stash"] == 2
    assert t.amount_in("fridge") == 0


def test_undo_any_entry_restores_exactly():
    t = MilkTracker()
    p1 = t.pump(4, T0)
    t.pump(4, T0 + timedelta(hours=1))
    f = t.feed(6, T0 + timedelta(hours=2))
    assert t.amount_in("fridge") == pytest.approx(2)
    t.undo(f["id"])
    assert t.amount_in("fridge") == pytest.approx(8)
    assert len(t.batches) == 2
    t.undo(p1["id"])
    assert t.amount_in("fridge") == pytest.approx(4)
    t.undo()
    assert t.amount_in("fridge") == 0
    with pytest.raises(MilkTrackerError):
        t.undo()


def test_freeze_thaw_and_expiry():
    t = MilkTracker(fridge_days=4, freezer_days=180)
    t.pump(4, T0)
    batch = t.batches[0]
    t.move(None, T0 + timedelta(hours=1), source="fridge", destination="freezer", batch_id=batch["id"])
    assert t.amount_in("freezer") == 4
    frozen = t.batches[0]
    assert t.expires_at(frozen) == T0 + timedelta(days=180)
    thaw_at = T0 + timedelta(days=30)
    e = t.move(2, thaw_at, source="freezer", destination="fridge")
    assert e["kind"] == "thaw"
    thawed = next(b for b in t.batches if b["location"] == "fridge")
    assert t.expires_at(thawed) == thaw_at + timedelta(hours=24)
    s = summary(t, thaw_at + timedelta(hours=1))
    assert s["expiring_amount"] == 2
    s = summary(t, thaw_at + timedelta(hours=25))
    assert s["expired_amount"] == 2
    d = t.discard_expired(thaw_at + timedelta(hours=25))
    assert d["amount"] == 2
    assert t.amount_in("fridge") == 0
    t.undo(d["id"])
    assert t.amount_in("fridge") == 2


def test_set_stash_and_days_of_supply():
    t = MilkTracker()
    t.set_stash("fridge", 10, T0)
    t.set_stash("freezer", 38, T0)
    t.set_stash("fridge", 6, T0)
    s = summary(t)
    assert s["total"] == 44
    assert s["days_of_supply"] == pytest.approx(44 / 24, abs=0.05)


def test_goal_projection():
    t = MilkTracker()
    for day in range(10):
        t.pump(10, T0 - timedelta(days=day, hours=1))
        t.feed(4, T0 - timedelta(days=day, hours=0.5))
    t.set_setting("goal_active", True)
    t.set_setting("goal_amount", 100)
    t.set_setting("goal_date", (T0 + timedelta(days=10)).date().isoformat())
    s = summary(t)
    g = s["goal"]
    assert s["total"] == 60
    assert g["remaining"] == 40
    assert g["days_left"] == 10
    assert g["needed_per_day"] == 4
    assert s["net_per_day"] == pytest.approx(6, abs=0.1)
    assert g["on_track"] is True


def test_pump_due():
    t = MilkTracker()
    t.pump(3, T0)
    assert summary(t, T0 + timedelta(hours=3))["pump_due"] is False
    assert summary(t, T0 + timedelta(hours=4, minutes=1))["pump_due"] is True


def test_invalid_amount():
    with pytest.raises(MilkTrackerError):
        MilkTracker().pump(0, T0)


def test_roundtrip_serialisation():
    t = MilkTracker()
    t.pump(4, T0, note="left")
    t2 = MilkTracker(t.as_dict())
    assert t2.amount_in("fridge") == 4
    assert t2.log[0]["note"] == "left"


def test_group_move_and_discard_by_batch_list():
    t = MilkTracker()
    t.pump(2, T0)
    t.pump(3, T0 + timedelta(hours=3))
    ids = [b["id"] for b in t.batches]
    e = t.move(None, T0 + timedelta(hours=4), source="fridge", destination="freezer", batch_id=ids)
    assert e["kind"] == "freeze" and e["amount"] == 5
    assert t.amount_in("freezer") == 5
    ids = [b["id"] for b in t.batches]
    d = t.discard(None, T0 + timedelta(hours=5), batch_id=ids)
    assert d["amount"] == 5 and t.amount_in("freezer") == 0
    t.undo(d["id"])
    t.undo(e["id"])
    assert t.amount_in("fridge") == 5 and t.amount_in("freezer") == 0


def test_add_stored_dates_undated_milk_without_changing_total():
    t = MilkTracker()
    t.set_stash("freezer", 144, T0)
    assert all(t.is_undated(b) for b in t.batches)
    e = t.add_stored(10, T0 - timedelta(days=40), T0, location="freezer")
    assert e["kind"] == "stock" and e["replaced"] == 10
    assert t.amount_in("freezer") == 144
    s = summary(t, T0)
    assert s["undated_amount"] == 134
    assert s["pumped_today"] == 0  # stored milk never counts as pumping
    dated = next(b for b in s["batches"] if not b["undated"])
    assert dated["expires_at"].startswith((T0 - timedelta(days=40) + timedelta(days=180)).date().isoformat())
    # Adding more than the undated amount only replaces what's left.
    e2 = t.add_stored(200, T0 - timedelta(days=30), T0, location="freezer")
    assert e2["replaced"] == 134
    assert t.amount_in("freezer") == 210
    t.undo(e2["id"])
    t.undo(e["id"])
    assert t.amount_in("freezer") == 144
    assert summary(t, T0)["undated_amount"] == 144


def test_add_stored_without_replacing_adds_on_top():
    t = MilkTracker()
    t.set_stash("freezer", 20, T0)
    t.add_stored(5, T0 - timedelta(days=3), T0, location="freezer", replace_undated=False)
    assert t.amount_in("freezer") == 25
