"""Adaptive virtual planning over existing Fog records; never drives hardware."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from typing import Any
from uuid import uuid4

from config import (
    DATABASE_PATH, SENSOR_FIELDS, SENSOR_LIMITS, SAMPLING_PLAN_BUDGET,
    SAMPLING_PLAN_STALE_SECONDS, SAMPLING_PLAN_OVERDUE_SECONDS,
    SAMPLING_PLAN_WEIGHTS,
)
from database import MarineDatabase

ALGORITHM_VERSION = "adaptive-virtual-v1"
ACTIVE_STATUSES = {"PLANNED", "IN_PROGRESS"}
TERMINAL_SAMPLE_STATUSES = {"COMPLETED", "CANCELLED", "FAILED"}


def utc_time(value: str | datetime) -> datetime:
    """Legacy naive timestamps are interpreted as UTC (explicit limitation)."""
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def bounded(value: float) -> float:
    return max(0.0, min(100.0, value))


class AdaptiveSamplingPlanner:
    def __init__(self, database: MarineDatabase, *, weights: dict[str, float] | None = None,
                 stale_seconds: float = SAMPLING_PLAN_STALE_SECONDS,
                 overdue_seconds: float = SAMPLING_PLAN_OVERDUE_SECONDS) -> None:
        self.database = database
        self.weights = dict(SAMPLING_PLAN_WEIGHTS if weights is None else weights)
        if set(self.weights) != {"risk", "trend", "overdue", "quality_proxy"}:
            raise ValueError("Weights must specify risk, trend, overdue, quality_proxy")
        if any(not numeric(v) or v < 0 for v in self.weights.values()) or not math.isfinite(sum(self.weights.values())) or sum(self.weights.values()) <= 0:
            raise ValueError("Weights must be finite, nonnegative, with a positive sum")
        if not numeric(stale_seconds) or not numeric(overdue_seconds) or min(stale_seconds, overdue_seconds) <= 0:
            raise ValueError("Stale and overdue intervals must be finite and positive")
        self.stale_seconds = stale_seconds
        self.overdue_seconds = overdue_seconds

    def score_zone(self, observations: list[dict[str, Any]], samples: list[dict[str, Any]],
                   now: datetime) -> dict[str, Any]:
        """Score one zone using event time, including only observations at/before now."""
        now = utc_time(now)
        ordered = []
        malformed = 0
        for event in observations:
            try:
                timestamp = utc_time(event["event_timestamp"])
            except (ValueError, TypeError):
                malformed += 1
                continue
            if timestamp <= now:
                ordered.append((timestamp, event))
        ordered.sort(key=lambda pair: (pair[0], pair[1]["id"]), reverse=True)
        # Malformed/future-only zones remain eligible for data verification.
        latest = ordered[0][1] if ordered else max(observations, key=lambda item: item["id"])
        age = (now - ordered[0][0]).total_seconds() if ordered else None
        score = latest.get("edge_risk_score") if ordered and latest["sensor_valid"] else None
        risk = bounded(float(score)) if numeric(score) else 0.0
        unavailable = not numeric(score)
        level = latest["edge_risk_level"] if not unavailable else "UNKNOWN"
        validity = latest.get("validity_score")
        bad_fields = []
        for field, limits in SENSOR_LIMITS.items():
            value = latest.get(field)
            if not numeric(value) or not limits["min"] <= value <= limits["max"]:
                bad_fields.append(field)
        quality = max(
            100.0 if not ordered or not latest["sensor_valid"] or unavailable else 0.0,
            100.0 * len(bad_fields) / len(SENSOR_FIELDS),
            100.0 - bounded(float(validity) * 100) if numeric(validity) else 100.0,
            bounded(age / self.stale_seconds * 100) if age is not None else 100.0,
        )
        # Trend uses two distinct timestamps from the latest device, without
        # crossing an invalid observation. Out-of-order arrivals are sorted above.
        trend = 0.0
        trend_delta = None
        if ordered and numeric(score):
            for timestamp, event in ordered[1:]:
                if event["device_id"] != latest["device_id"]:
                    continue
                if not event["sensor_valid"] or not numeric(event["edge_risk_score"]):
                    break
                if timestamp < ordered[0][0]:
                    trend_delta = float(score) - float(event["edge_risk_score"])
                    trend = bounded(trend_delta)
                    break
        completed = []
        for sample in samples:
            # Phase 4 SIMULATED / SIMULATED_ACK are not valid completed samples.
            if sample.get("completed_at"):
                completed.append(utc_time(sample["completed_at"]))
            elif sample.get("collection_status") == "COLLECTED":
                # Legacy rows have no collection timestamp; request time is not
                # substituted for collection time.
                continue
        completed = [timestamp for timestamp in completed if timestamp <= now]
        last_valid = max(completed) if completed else None
        overdue = bounded((now - last_valid).total_seconds() / self.overdue_seconds * 100) if last_valid else 100.0
        reasons = []
        def reason(code: str, text: str) -> None:
            reasons.append({"code": code, "text": text})
        if risk >= 50:
            reason("HIGH_RISK", "High current environmental risk score.")
        elif risk > 0:
            reason("CURRENT_RISK", "Current environmental risk contributes to priority.")
        if trend > 0:
            reason("INCREASING_RISK", "Risk increased between the two latest usable observations.")
        if last_valid is None:
            reason("NO_VALID_SAMPLE", "No timestamped completed virtual sample is recorded.")
        elif overdue >= 100:
            reason("SAMPLE_OVERDUE", "Completed virtual sample is overdue.")
        elif overdue > 0:
            reason("SAMPLE_AGE", "Time since the completed virtual sample contributes to priority.")
        if unavailable:
            reason("RISK_UNAVAILABLE", "Current risk is unavailable; verification is needed.")
        if bad_fields or not latest["sensor_valid"] or not numeric(validity) or (numeric(validity) and validity < 1):
            reason("POOR_DATA_QUALITY", "Incomplete or unreliable readings require verification.")
        if age is None:
            reason("UNUSABLE_TIMESTAMP", "No usable observation timestamp at planning time.")
        elif age >= self.stale_seconds:
            reason("STALE_DATA", "Latest observation is stale.")
        elif age > 0:
            reason("DATA_AGE", "Observation age contributes to the data-quality proxy.")
        components = {"risk": risk, "trend": trend, "overdue": overdue, "quality_proxy": quality}
        priority = sum(self.weights[k] * v for k, v in components.items()) / sum(self.weights.values())
        return {
            "zone_id": latest["zone_id"], "device_id": latest["device_id"],
            "sensor_event_id": latest["id"], "risk_score": score if numeric(score) else None,
            "risk_level": level, "components": components, "priority_score": round(priority, 6),
            "reasons": reasons, "explanation": " ".join(r["text"] for r in reasons),
            "evidence": {"observation_age_seconds": age, "trend_delta": trend_delta,
                         "last_valid_sample_at": last_valid.isoformat() if last_valid else None,
                         "bad_fields": bad_fields, "malformed_timestamp_count": malformed,
                         "uncertainty_kind": "DATA_QUALITY_PROXY"},
        }

    def _candidates(self, connection, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
        events = [dict(row) for row in connection.execute("SELECT * FROM sensor_events")]
        legacy = [dict(row) for row in connection.execute("SELECT * FROM samples")]
        virtual = [dict(row) for row in connection.execute("SELECT * FROM sampling_plan_zones")]
        blocked = {s["zone_id"] for s in legacy if s["status"] not in TERMINAL_SAMPLE_STATUSES}
        blocked.update(s["zone_id"] for s in virtual if s["status"] in ACTIVE_STATUSES)
        by_zone: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            by_zone.setdefault(event["zone_id"], []).append(event)
        candidates = []
        for zone, observations in by_zone.items():
            if zone in blocked:
                continue
            history = [s for s in legacy + virtual if s["zone_id"] == zone]
            item = self.score_zone(observations, history, now)
            decision = connection.execute(
                "SELECT decision_id, action, reason FROM decisions WHERE sensor_event_id = ?",
                (item["sensor_event_id"],),
            ).fetchone()
            item["decision"] = dict(decision) if decision else None
            candidates.append(item)
        candidates.sort(key=lambda item: (-item["priority_score"], item["zone_id"]))
        return candidates, sorted(set(by_zone) & blocked)

    def generate(self, budget: int = SAMPLING_PLAN_BUDGET, *, request_id: str | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValueError("Budget must be a nonnegative integer")
        if request_id is not None and (not isinstance(request_id, str) or not request_id.strip()):
            raise ValueError("Request ID must be a nonempty string")
        request_id = request_id or str(uuid4())
        now = utc_time(now or datetime.now(timezone.utc))
        settings = {"weights": self.weights, "stale_seconds": self.stale_seconds,
                    "overdue_seconds": self.overdue_seconds}
        signature = json.dumps({"budget": budget, "settings": settings, "version": ALGORITHM_VERSION}, sort_keys=True)
        with closing(self.database._connect()) as connection, connection:
            # Serialize planning writers so two requests cannot reserve one zone.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM sampling_plans WHERE request_id = ?", (request_id,)).fetchone()
            if existing:
                if existing["request_signature"] != signature:
                    raise ValueError("Request ID was already used with different planning parameters")
                return self._read_plan(connection, existing["plan_id"])
            candidates, blocked = self._candidates(connection, now)
            plan_id = "PLAN-" + str(uuid4())
            created = now.isoformat(timespec="microseconds")
            connection.execute(
                "INSERT INTO sampling_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, request_id, signature, created, budget, ALGORITHM_VERSION,
                 json.dumps(settings, sort_keys=True), json.dumps({"blocked_zones": blocked, "candidates": candidates})),
            )
            for rank, item in enumerate(candidates[:budget], 1):
                connection.execute(
                    """INSERT INTO sampling_plan_zones
                    (plan_id, zone_id, rank, recommendation_json, status)
                    VALUES (?, ?, ?, ?, 'PLANNED')""",
                    (plan_id, item["zone_id"], rank, json.dumps(item)),
                )
            return self._read_plan(connection, plan_id)

    @staticmethod
    def _read_plan(connection, plan_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM sampling_plans WHERE plan_id = ?", (plan_id,)).fetchone()
        if not row:
            raise ValueError("Unknown plan ID")
        plan = dict(row)
        plan.pop("request_signature")
        plan["settings"] = json.loads(plan.pop("settings_json"))
        plan["snapshot"] = json.loads(plan.pop("snapshot_json"))
        plan["selected"] = []
        for row in connection.execute("SELECT * FROM sampling_plan_zones WHERE plan_id = ? ORDER BY rank", (plan_id,)):
            item = json.loads(row["recommendation_json"])
            item.update({k: row[k] for k in ("rank", "status", "sample_id", "completed_at")})
            item.update(plan_id=plan_id, created_at=plan["created_at"])
            plan["selected"].append(item)
        return plan

    def inspect(self, plan_id: str | None = None) -> list[dict[str, Any]]:
        with closing(self.database._connect()) as connection:
            ids = [plan_id] if plan_id else [row[0] for row in connection.execute("SELECT plan_id FROM sampling_plans ORDER BY created_at DESC, plan_id")]
            return [self._read_plan(connection, value) for value in ids]

    def transition(self, plan_id: str, zone_id: str, status: str,
                   *, now: datetime | None = None) -> dict[str, Any]:
        """Explicit software simulation lifecycle; completion is never a lab result."""
        if status not in {"IN_PROGRESS", "COMPLETED", "CANCELLED"}:
            raise ValueError("Status must be IN_PROGRESS, COMPLETED, or CANCELLED")
        timestamp = utc_time(now or datetime.now(timezone.utc))
        with closing(self.database._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sampling_plan_zones WHERE plan_id = ? AND zone_id = ?", (plan_id, zone_id)).fetchone()
            if not row:
                raise ValueError("Unknown plan/zone")
            if row["status"] == status:
                return self._read_plan(connection, plan_id)
            if row["status"] not in ACTIVE_STATUSES:
                raise ValueError("Terminal virtual sample status cannot be changed")
            created = connection.execute("SELECT created_at FROM sampling_plans WHERE plan_id = ?", (plan_id,)).fetchone()[0]
            if timestamp < utc_time(created):
                raise ValueError("Transition timestamp precedes plan creation")
            sample_id = row["sample_id"] or ("VIRTUAL-" + str(uuid4()) if status != "CANCELLED" else None)
            connection.execute("""UPDATE sampling_plan_zones SET status = ?, sample_id = ?, completed_at = ?
                               WHERE plan_id = ? AND zone_id = ?""",
                               (status, sample_id, timestamp.isoformat() if status == "COMPLETED" else None, plan_id, zone_id))
            return self._read_plan(connection, plan_id)

    def feedback(self, plan_id: str) -> list[dict[str, Any]]:
        """Expose the first subsequent observation; no invented laboratory labels."""
        with closing(self.database._connect()) as connection:
            plan = self._read_plan(connection, plan_id)
            result = []
            for item in plan["selected"]:
                later = []
                for row in connection.execute("SELECT * FROM sensor_events WHERE zone_id = ?", (item["zone_id"],)):
                    try:
                        timestamp = utc_time(row["event_timestamp"])
                    except (ValueError, TypeError):
                        continue
                    if timestamp > utc_time(plan["created_at"]):
                        later.append((timestamp, row["id"], dict(row)))
                later.sort(key=lambda entry: (entry[0], entry[1]))
                observation = later[0][2] if later else None
                subsequent_score = observation["edge_risk_score"] if observation and observation["sensor_valid"] else None
                delta = (float(subsequent_score) - float(item["risk_score"])) if numeric(subsequent_score) and numeric(item["risk_score"]) else None
                result.append({"zone_id": item["zone_id"], "planned_risk_score": item["risk_score"],
                               "observed_risk_score_change": delta,
                               "subsequent_observation": observation,
                               "laboratory_outcome": None,
                               "limitation": "Sensor follow-up is not a HAB or laboratory label."})
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DATABASE_PATH))
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("plan")
    generate.add_argument("--budget", type=int, default=SAMPLING_PLAN_BUDGET)
    generate.add_argument("--request-id")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--plan-id")
    transition = commands.add_parser("status")
    transition.add_argument("plan_id")
    transition.add_argument("zone_id")
    transition.add_argument("status", choices=["IN_PROGRESS", "COMPLETED", "CANCELLED"])
    feedback = commands.add_parser("feedback")
    feedback.add_argument("plan_id")
    args = parser.parse_args()
    try:
        planner = AdaptiveSamplingPlanner(MarineDatabase(args.database))
        if args.command == "plan":
            result = planner.generate(args.budget, request_id=args.request_id)
        elif args.command == "inspect":
            result = planner.inspect(args.plan_id)
        elif args.command == "feedback":
            result = planner.feedback(args.plan_id)
        else:
            result = planner.transition(args.plan_id, args.zone_id, args.status)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
