"""Reproducible synthetic policy comparison, not real-world HAB accuracy."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from time import perf_counter

from database import MarineDatabase
from decision.adaptive_sampling import AdaptiveSamplingPlanner
from mqtt.message_utils import build_sensor_message
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


def evaluate(seed: int = 42, budget: int = 2, cycles: int = 12) -> dict:
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError("Budget must be a nonnegative integer")
    if not isinstance(cycles, int) or isinstance(cycles, bool) or cycles < 1:
        raise ValueError("Cycles must be a positive integer")
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    zones = [f"zone-{index}" for index in range(8)]
    scenarios = []
    for cycle in range(cycles):
        events = []
        for index, zone in enumerate(zones):
            scenario = rng.choice(["normal", "medium", "high"])
            event = MarineSensorSimulator(device_id=zone, zone_id=zone, seed=seed + cycle * 8 + index).generate(scenario)
            timestamp = start + timedelta(minutes=10 * cycle)
            event.update(sequence_number=cycle + 1, timestamp=timestamp.isoformat())
            validation = SensorValidator().validate(event)
            risk = EdgeRiskEngine().calculate(event, validation)
            message = build_sensor_message(event, validation, risk)
            # Controlled missing/stale perturbations. The original score is only
            # a synthetic reference, never treated as an observed HAB label.
            if cycle % 3 == 1 and index % 3 == 0:
                message.update(dissolved_oxygen_mg_l=None, sensor_valid=False,
                               validity_score=0.8, edge_risk_score=None, edge_risk_level="INVALID")
            if cycle % 3 == 2 and index % 3 == 0:
                message["timestamp"] = (timestamp - timedelta(minutes=30)).isoformat()
            events.append(message)
        scenarios.append(events)
    report = {"data_kind": "SYNTHETIC_SIMULATION", "seed": seed, "budget_per_cycle": budget,
              "cycles": cycles, "limitations": "Coverage refers to observed prototype risk, not HAB detection. Latency varies by machine.",
              "strategies": {}}
    with TemporaryDirectory(prefix="marine-evaluation-") as directory:
        for strategy in ("round_robin", "risk_only", "adaptive"):
            database = MarineDatabase(Path(directory) / f"{strategy}.db")
            planner = AdaptiveSamplingPlanner(database)
            history = []
            cursor = 0
            previous = set()
            for cycle, messages in enumerate(scenarios):
                now = start + timedelta(minutes=10 * cycle)
                for message in messages:
                    database.insert_event(message)
                started = perf_counter()
                with closing(database._connect()) as connection:
                    candidates, blocked = planner._candidates(connection, now)
                if strategy == "adaptive":
                    ordered = candidates
                elif strategy == "risk_only":
                    ordered = sorted(candidates, key=lambda item: (-item["components"]["risk"], item["zone_id"]))
                else:
                    rotation = zones[cursor:] + zones[:cursor]
                    ordered = sorted(candidates, key=lambda item: rotation.index(item["zone_id"]))
                    cursor = (cursor + min(budget, len(zones))) % len(zones)
                selected = ordered[:budget]
                latency = (perf_counter() - started) * 1000
                selected_zones = {item["zone_id"] for item in selected}
                high = {m["zone_id"] for m in messages if m["sensor_valid"] and m["edge_risk_level"] in {"HIGH", "CRITICAL"}}
                degraded = {item["zone_id"] for item in candidates if item["components"]["quality_proxy"] >= 100}
                history.append({"cycle": cycle, "condition": ("complete", "missing", "stale")[cycle % 3], "selected_zones": sorted(selected_zones),
                                "number_selected": len(selected), "budget_utilization": len(selected) / budget if budget else 0.0,
                                "high_risk_zones": len(high), "high_risk_selected": len(high & selected_zones),
                                "high_risk_coverage": len(high & selected_zones) / len(high) if high else None,
                                "repeat_previous_cycle": len(previous & selected_zones),
                                "pending_redundant_selections": len(set(blocked) & selected_zones),
                                "degraded_zones_selected": len(degraded & selected_zones),
                                "degraded_zone_coverage": len(degraded & selected_zones) / len(degraded) if degraded else None,
                                "selection_latency_ms": latency})
                # Give all strategies the same explicit synthetic completion
                # history, maintained in their own isolated DB.
                with closing(database._connect()) as connection, connection:
                    plan_id = f"evaluation-{cycle}"
                    connection.execute("INSERT INTO sampling_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                       (plan_id, plan_id, "synthetic", now.isoformat(), budget, strategy, "{}", "{}"))
                    for rank, item in enumerate(selected, 1):
                        connection.execute("""INSERT INTO sampling_plan_zones VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?)""",
                                           (plan_id, item["zone_id"], rank, json.dumps(item),
                                            f"synthetic-{cycle}-{rank}", now.isoformat()))
                previous = selected_zones
            total_high = sum(row["high_risk_zones"] for row in history)
            report["strategies"][strategy] = {
                "high_risk_coverage": sum(row["high_risk_selected"] for row in history) / total_high if total_high else None,
                "number_selected": sum(row["number_selected"] for row in history),
                "budget_utilization": sum(row["number_selected"] for row in history) / (budget * cycles) if budget else 0.0,
                "repeat_previous_cycle": sum(row["repeat_previous_cycle"] for row in history),
                "pending_redundant_selections": sum(row["pending_redundant_selections"] for row in history),
                "mean_selection_latency_ms": sum(row["selection_latency_ms"] for row in history) / cycles,
                "cycles": history,
            }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--budget", type=int, default=2)
    parser.add_argument("--cycles", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(args.seed, args.budget, args.cycles)
    except ValueError as exc:
        parser.error(str(exc))
    output = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
