"""Pure-Python milk stash model.

This module has no Home Assistant imports so the bookkeeping can be unit
tested in isolation. The stash is modelled as a list of *batches* (one per
pump session) that live in the fridge or the freezer. Using milk always
consumes the oldest batch first (FIFO), which is what lets us tell you when
milk is about to expire.

Every log entry records the batch-level operations it performed, so any
entry can be undone exactly, not just the last one.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from .const import (
    HISTORY_DAYS,
    KIND_ADJUST,
    KIND_DISCARD,
    KIND_FEED,
    KIND_FREEZE,
    KIND_PUMP,
    KIND_STOCK,
    KIND_THAW,
    LOC_FREEZER,
    LOC_FRIDGE,
    LOG_LIMIT,
    SOURCE_AUTO,
)

EPSILON = 1e-6
THAWED_HOURS = 24


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _iso(ts: datetime) -> str:
    return ts.isoformat()


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts)


def _r(value: float, digits: int = 2) -> float:
    return round(value + 0.0, digits)


class MilkTrackerError(Exception):
    """Raised for invalid operations (e.g. undoing an unknown entry)."""


class MilkTracker:
    """In-memory milk stash with an undoable log."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        *,
        fridge_days: float = 4,
        freezer_days: float = 180,
    ) -> None:
        data = data or {}
        self.batches: list[dict[str, Any]] = data.get("batches", [])
        self.log: list[dict[str, Any]] = data.get("log", [])
        self.settings: dict[str, Any] = data.get("settings", {})
        self.fridge_days = fridge_days
        self.freezer_days = freezer_days

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def as_dict(self) -> dict[str, Any]:
        return {"batches": self.batches, "log": self.log, "settings": self.settings}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _batch(self, batch_id: str) -> dict[str, Any] | None:
        return next((b for b in self.batches if b["id"] == batch_id), None)

    def _batches(self, batch_ids: str | list[str]) -> list[dict[str, Any]]:
        ids = [batch_ids] if isinstance(batch_ids, str) else list(batch_ids)
        found = []
        for bid in ids:
            batch = self._batch(bid)
            if batch is None:
                raise MilkTrackerError(f"Unknown batch {bid}")
            found.append(batch)
        if len({b["location"] for b in found}) > 1:
            raise MilkTrackerError("Batches must all be in the same place")
        return found

    def expires_at(self, batch: dict[str, Any]) -> datetime:
        """Return when a batch should be used by."""
        pumped = _parse(batch["pumped_at"])
        assert pumped is not None
        if batch["location"] == LOC_FREEZER:
            return pumped + timedelta(days=self.freezer_days)
        thawed = _parse(batch.get("thawed_at"))
        fridge_limit = pumped + timedelta(days=self.fridge_days)
        if thawed is not None:
            return thawed + timedelta(hours=THAWED_HOURS)
        return fridge_limit

    @staticmethod
    def is_undated(batch: dict[str, Any]) -> bool:
        """Milk entered as a lump sum (setup / correction) with no real pump date."""
        return bool(batch.get("undated")) or batch.get("note") in ("Correction", "Starting stash")

    def amount_in(self, location: str) -> float:
        return sum(b["remaining"] for b in self.batches if b["location"] == location)

    def _fifo(self, source: str) -> list[dict[str, Any]]:
        """Batches to draw from, in the order they should be used."""
        if source == SOURCE_AUTO:
            locations = [LOC_FRIDGE, LOC_FREEZER]
        else:
            locations = [source]
        ordered: list[dict[str, Any]] = []
        for loc in locations:
            ordered.extend(
                sorted(
                    (b for b in self.batches if b["location"] == loc),
                    key=lambda b: (self.expires_at(b), b["pumped_at"]),
                )
            )
        return ordered

    def _snapshot(self, batch: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in batch.items() if k != "remaining"}

    def _create_batch(
        self,
        amount: float,
        location: str,
        pumped_at: datetime,
        *,
        thawed_at: datetime | None = None,
        note: str | None = None,
        source_batch: str | None = None,
    ) -> dict[str, Any]:
        batch = {
            "id": _new_id(),
            "amount": _r(amount),
            "remaining": _r(amount),
            "location": location,
            "pumped_at": _iso(pumped_at),
            "thawed_at": _iso(thawed_at) if thawed_at else None,
            "note": note,
            "from": source_batch,
        }
        self.batches.append(batch)
        return batch

    def _take(self, amount: float, source: str) -> tuple[float, list[dict[str, Any]]]:
        """Remove ``amount`` FIFO from ``source``. Returns (taken, ops)."""
        ops: list[dict[str, Any]] = []
        left = amount
        for batch in self._fifo(source):
            if left <= EPSILON:
                break
            take = min(batch["remaining"], left)
            if take <= EPSILON:
                continue
            batch["remaining"] = _r(batch["remaining"] - take, 4)
            left -= take
            ops.append({"b": batch["id"], "d": -_r(take, 4), "snap": self._snapshot(batch)})
        self._prune()
        return amount - max(left, 0.0), ops

    def _prune(self) -> None:
        self.batches = [b for b in self.batches if b["remaining"] > EPSILON]

    def _append(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry.setdefault("id", _new_id())
        entry.setdefault("logged_at", datetime.now(UTC).isoformat())
        self.log.append(entry)
        self.log.sort(key=lambda e: e["ts"])
        if len(self.log) > LOG_LIMIT:
            self.log = self.log[-LOG_LIMIT:]
        return entry

    @staticmethod
    def _validate_amount(amount: float) -> float:
        amount = float(amount)
        if not math.isfinite(amount) or amount <= 0:
            raise MilkTrackerError("Amount must be greater than zero")
        return amount

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #
    def pump(
        self,
        amount: float,
        ts: datetime,
        *,
        location: str = LOC_FRIDGE,
        note: str | None = None,
        duration: float | None = None,
    ) -> dict[str, Any]:
        amount = self._validate_amount(amount)
        batch = self._create_batch(amount, location, ts, note=note)
        return self._append(
            {
                "ts": _iso(ts),
                "kind": KIND_PUMP,
                "amount": _r(amount),
                "location": location,
                "note": note,
                "duration": duration,
                "ops": [{"b": batch["id"], "d": batch["amount"], "new": True,
                         "snap": self._snapshot(batch)}],
            }
        )

    def feed(
        self,
        amount: float,
        ts: datetime,
        *,
        source: str = SOURCE_AUTO,
        note: str | None = None,
        kind: str = KIND_FEED,
    ) -> dict[str, Any]:
        amount = self._validate_amount(amount)
        taken, ops = self._take(amount, source)
        return self._append(
            {
                "ts": _iso(ts),
                "kind": kind,
                "amount": _r(amount),
                "from_stash": _r(taken),
                "location": source,
                "note": note,
                "ops": ops,
            }
        )

    def discard(
        self,
        amount: float | None,
        ts: datetime,
        *,
        source: str = SOURCE_AUTO,
        batch_id: str | list[str] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        if batch_id:
            batches = self._batches(batch_id)
            left = sum(b["remaining"] for b in batches) if amount is None else float(amount)
            left = self._validate_amount(left)
            ops = []
            total = 0.0
            for batch in batches:
                take = min(batch["remaining"], left)
                if take <= EPSILON:
                    continue
                batch["remaining"] = _r(batch["remaining"] - take, 4)
                ops.append({"b": batch["id"], "d": -_r(take, 4), "snap": self._snapshot(batch)})
                left -= take
                total += take
            self._prune()
            return self._append(
                {"ts": _iso(ts), "kind": KIND_DISCARD, "amount": _r(total),
                 "from_stash": _r(total), "location": batches[0]["location"],
                 "note": note, "ops": ops}
            )
        if amount is None:
            raise MilkTrackerError("Provide an amount or a batch_id")
        return self.feed(amount, ts, source=source, note=note, kind=KIND_DISCARD)

    def discard_expired(self, now: datetime) -> dict[str, Any] | None:
        ops: list[dict[str, Any]] = []
        total = 0.0
        for batch in list(self.batches):
            if self.expires_at(batch) <= now:
                total += batch["remaining"]
                ops.append({"b": batch["id"], "d": -batch["remaining"], "snap": self._snapshot(batch)})
                batch["remaining"] = 0
        if not ops:
            return None
        self._prune()
        return self._append(
            {"ts": _iso(now), "kind": KIND_DISCARD, "amount": _r(total),
             "from_stash": _r(total), "location": SOURCE_AUTO,
             "note": "Expired", "ops": ops}
        )

    def move(
        self,
        amount: float | None,
        ts: datetime,
        *,
        source: str,
        destination: str,
        batch_id: str | list[str] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Move milk between fridge and freezer (freezing or thawing)."""
        if batch_id:
            candidates = self._batches(batch_id)
            source = candidates[0]["location"]
            available = sum(b["remaining"] for b in candidates)
            left = available if amount is None else min(float(amount), available)
        else:
            if amount is None:
                raise MilkTrackerError("Provide an amount or a batch_id")
            candidates = self._fifo(source)
            left = float(amount)
        if source == destination:
            raise MilkTrackerError("Source and destination must differ")
        left = self._validate_amount(left) if left > 0 else 0.0
        if left <= EPSILON:
            raise MilkTrackerError(f"No milk in the {source} to move")

        ops: list[dict[str, Any]] = []
        moved = 0.0
        thawing = source == LOC_FREEZER and destination == LOC_FRIDGE
        for batch in candidates:
            if left <= EPSILON:
                break
            take = min(batch["remaining"], left)
            if take <= EPSILON:
                continue
            batch["remaining"] = _r(batch["remaining"] - take, 4)
            ops.append({"b": batch["id"], "d": -_r(take, 4), "snap": self._snapshot(batch)})
            new = self._create_batch(
                take,
                destination,
                _parse(batch["pumped_at"]),  # type: ignore[arg-type]
                thawed_at=ts if thawing else None,
                note=batch.get("note"),
                source_batch=batch["id"],
            )
            ops.append({"b": new["id"], "d": new["amount"], "new": True, "snap": self._snapshot(new)})
            moved += take
            left -= take
        self._prune()
        if moved <= EPSILON:
            raise MilkTrackerError(f"No milk in the {source} to move")
        return self._append(
            {"ts": _iso(ts), "kind": KIND_THAW if thawing else KIND_FREEZE,
             "amount": _r(moved), "location": source, "destination": destination,
             "note": note, "ops": ops}
        )

    def set_stash(self, location: str, target: float, ts: datetime) -> dict[str, Any] | None:
        """Correct the amount stored in a location to ``target``."""
        target = max(0.0, float(target))
        current = self.amount_in(location)
        diff = target - current
        if abs(diff) <= EPSILON:
            return None
        if diff > 0:
            batch = self._create_batch(diff, location, ts, note="Correction")
            batch["undated"] = True
            ops = [{"b": batch["id"], "d": batch["amount"], "new": True, "snap": self._snapshot(batch)}]
        else:
            _, ops = self._take(-diff, location)
        return self._append(
            {"ts": _iso(ts), "kind": KIND_ADJUST, "amount": _r(diff),
             "location": location, "note": "Stash correction", "ops": ops}
        )

    def add_stored(
        self,
        amount: float,
        pumped_at: datetime,
        ts: datetime,
        *,
        location: str,
        replace_undated: bool = True,
        note: str | None = None,
        date_only: bool = False,
    ) -> dict[str, Any]:
        """Record milk that is already stored, with the date it was pumped.

        With ``replace_undated`` the same amount is taken out of undated milk
        (the starting stash / corrections), so the total stays the same and
        the milk simply gains a real date. It never counts as pumping.
        """
        amount = self._validate_amount(amount)
        ops: list[dict[str, Any]] = []
        replaced = 0.0
        if replace_undated:
            left = amount
            for batch in sorted(
                (b for b in self.batches if b["location"] == location and self.is_undated(b)),
                key=lambda b: b["pumped_at"],
            ):
                if left <= EPSILON:
                    break
                take = min(batch["remaining"], left)
                batch["remaining"] = _r(batch["remaining"] - take, 4)
                ops.append({"b": batch["id"], "d": -_r(take, 4), "snap": self._snapshot(batch)})
                left -= take
                replaced += take
            self._prune()
        batch = self._create_batch(amount, location, pumped_at, note=note)
        if date_only:
            batch["date_only"] = True
        ops.append({"b": batch["id"], "d": batch["amount"], "new": True, "snap": self._snapshot(batch)})
        return self._append(
            {"ts": _iso(ts), "kind": KIND_STOCK, "amount": _r(amount), "replaced": _r(replaced),
             "pumped_at": _iso(pumped_at), "location": location, "note": note, "ops": ops}
        )

    def undo(self, entry_id: str | None = None) -> dict[str, Any]:
        """Reverse a log entry (the most recent one if no id given)."""
        if not self.log:
            raise MilkTrackerError("Nothing to undo")
        if entry_id is None:
            entry = max(self.log, key=lambda e: e.get("logged_at", e["ts"]))
        else:
            entry = next((e for e in self.log if e["id"] == entry_id), None)
            if entry is None:
                raise MilkTrackerError(f"Unknown log entry {entry_id}")
        for op in reversed(entry.get("ops", [])):
            batch = self._batch(op["b"])
            if batch is None:
                if op["d"] > 0:
                    # Created batch already used up by later entries; nothing to remove.
                    continue
                batch = dict(op["snap"], remaining=0.0)
                self.batches.append(batch)
            batch["remaining"] = _r(max(0.0, batch["remaining"] - op["d"]), 4)
        self._prune()
        self.log.remove(entry)
        return entry

    # ------------------------------------------------------------------ #
    # Settings (stored alongside the data, edited through entities)
    # ------------------------------------------------------------------ #
    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    def summary(
        self,
        now: datetime,
        tz: tzinfo,
        *,
        fixed_intake: float,
        auto_intake: bool,
        expiry_warning_hours: float,
        pump_interval_hours: float,
    ) -> dict[str, Any]:
        local_now = now.astimezone(tz)
        today = local_now.date()

        def local_date(ts: str) -> date:
            return datetime.fromisoformat(ts).astimezone(tz).date()

        days: dict[date, dict[str, float]] = {
            today - timedelta(days=i): {"pumped": 0.0, "fed": 0.0, "discarded": 0.0,
                                        "sessions": 0, "feeds": 0}
            for i in range(HISTORY_DAYS)
        }
        last_pump: datetime | None = None
        last_feed: datetime | None = None
        last_pump_amount: float | None = None
        first_ts: datetime | None = None
        for entry in self.log:
            ts = datetime.fromisoformat(entry["ts"])
            if entry["kind"] in (KIND_PUMP, KIND_FEED):
                first_ts = ts if first_ts is None else min(first_ts, ts)
            bucket = days.get(local_date(entry["ts"]))
            if entry["kind"] == KIND_PUMP:
                if last_pump is None or ts > last_pump:
                    last_pump, last_pump_amount = ts, entry["amount"]
                if bucket is not None:
                    bucket["pumped"] += entry["amount"]
                    bucket["sessions"] += 1
            elif entry["kind"] == KIND_FEED:
                if last_feed is None or ts > last_feed:
                    last_feed = ts
                if bucket is not None:
                    bucket["fed"] += entry["amount"]
                    bucket["feeds"] += 1
            elif entry["kind"] == KIND_DISCARD and bucket is not None:
                bucket["discarded"] += entry["amount"]

        # Rolling 7-day averages, scaled to how long we've actually been tracking.
        window_start = now - timedelta(days=7)
        pumped_7d = sum(
            e["amount"] for e in self.log
            if e["kind"] == KIND_PUMP and datetime.fromisoformat(e["ts"]) > window_start
        )
        fed_7d = sum(
            e["amount"] for e in self.log
            if e["kind"] == KIND_FEED and datetime.fromisoformat(e["ts"]) > window_start
        )
        fed_from_stash_7d = sum(
            e.get("from_stash", e["amount"]) for e in self.log
            if e["kind"] in (KIND_FEED, KIND_DISCARD) and datetime.fromisoformat(e["ts"]) > window_start
        )
        if first_ts is None:
            tracked_days = 1.0
        else:
            tracked_days = min(7.0, max(1.0, (now - first_ts).total_seconds() / 86400))
        avg_pumped = pumped_7d / tracked_days
        avg_fed = fed_7d / tracked_days
        net_per_day = (pumped_7d - fed_from_stash_7d) / tracked_days

        intake = avg_fed if (auto_intake and avg_fed > EPSILON) else fixed_intake

        fridge = self.amount_in(LOC_FRIDGE)
        freezer = self.amount_in(LOC_FREEZER)
        total = fridge + freezer

        warn_until = now + timedelta(hours=expiry_warning_hours)
        expired = expiring = undated_amount = 0.0
        next_expiry: datetime | None = None
        batches_out = []
        for batch in sorted(self.batches, key=lambda b: (b["location"], self.expires_at(b))):
            exp = self.expires_at(batch)
            if exp <= now:
                expired += batch["remaining"]
                status = "expired"
            elif exp <= warn_until:
                expiring += batch["remaining"]
                status = "expiring"
            else:
                status = "ok"
            if exp > now and (next_expiry is None or exp < next_expiry):
                next_expiry = exp
            undated = self.is_undated(batch)
            if undated:
                undated_amount += batch["remaining"]
            batches_out.append(
                {**batch, "expires_at": _iso(exp), "status": status, "undated": undated}
            )

        hours_since_pump = (now - last_pump).total_seconds() / 3600 if last_pump else None

        # Goal
        goal_active = bool(self.get_setting("goal_active", False))
        goal_amount = float(self.get_setting("goal_amount", 0) or 0)
        goal_date_s = self.get_setting("goal_date")
        goal: dict[str, Any] = {
            "active": goal_active,
            "amount": goal_amount,
            "date": goal_date_s,
            "name": self.get_setting("goal_name") or "Goal",
        }
        if goal_amount > 0:
            remaining = max(0.0, goal_amount - total)
            goal["remaining"] = _r(remaining, 1)
            goal["progress"] = _r(min(100.0, total / goal_amount * 100), 1)
            goal["reached"] = remaining <= EPSILON
            if goal_date_s:
                goal_day = date.fromisoformat(goal_date_s)
                days_left = (goal_day - today).days
                goal["days_left"] = days_left
                if days_left > 0:
                    goal["needed_per_day"] = _r(remaining / days_left, 1)
                    projected = total + net_per_day * days_left
                    goal["projected"] = _r(max(0.0, projected), 1)
                    goal["on_track"] = projected >= goal_amount
                else:
                    goal["needed_per_day"] = _r(remaining, 1) if remaining else 0.0
                    goal["projected"] = _r(total, 1)
                    goal["on_track"] = remaining <= EPSILON

        today_bucket = days[today]
        history = [
            {"date": d.isoformat(), **{k: _r(v, 2) for k, v in vals.items()}}
            for d, vals in sorted(days.items())
        ]
        return {
            "fridge": _r(fridge),
            "freezer": _r(freezer),
            "total": _r(total),
            "pumped_today": _r(today_bucket["pumped"]),
            "fed_today": _r(today_bucket["fed"]),
            "sessions_today": int(today_bucket["sessions"]),
            "feeds_today": int(today_bucket["feeds"]),
            "pumped_7d": _r(pumped_7d),
            "avg_pumped_per_day": _r(avg_pumped, 1),
            "avg_fed_per_day": _r(avg_fed, 1),
            "net_per_day": _r(net_per_day, 1),
            "daily_intake": _r(intake, 1),
            "intake_is_auto": bool(auto_intake and avg_fed > EPSILON),
            "days_of_supply": _r(total / intake, 1) if intake > EPSILON else None,
            "last_pump": _iso(last_pump) if last_pump else None,
            "last_pump_amount": last_pump_amount,
            "last_feed": _iso(last_feed) if last_feed else None,
            "hours_since_pump": _r(hours_since_pump, 2) if hours_since_pump is not None else None,
            "pump_due": hours_since_pump is not None and hours_since_pump >= pump_interval_hours,
            "pump_interval_hours": pump_interval_hours,
            "next_pump_due": _iso(last_pump + timedelta(hours=pump_interval_hours)) if last_pump else None,
            "next_expiry": _iso(next_expiry) if next_expiry else None,
            "expiring_amount": _r(expiring),
            "expired_amount": _r(expired),
            "undated_amount": _r(undated_amount),
            "batches": batches_out,
            "goal": goal,
            "history": history,
        }
