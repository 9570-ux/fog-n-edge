"""Synthetic Phase 5 selection demo in a disposable, isolated database."""
from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from database import MarineDatabase
from decision import DecisionEngine, SamplingManager
from decision.adaptive_sampling import AdaptiveSamplingPlanner
from mqtt.message_utils import build_sensor_message
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


def run_demo() -> dict:
    """Keep one synthetic Phase 4 request pending and select two other zones.

    No production path is accepted, no MQTT commands are published, and no
    sample lifecycle is advanced to collection or laboratory verification.
    """
    with TemporaryDirectory(prefix="marine-phase5-demo-") as directory:
        database = MarineDatabase(Path(directory) / "synthetic.db")
        for zone, scenario in (("zone-b", "high"), ("zone-a", "medium"), ("zone-c", "normal")):
            event = MarineSensorSimulator(device_id=f"synthetic-{zone}", zone_id=zone, seed=8).generate(scenario)
            validation = SensorValidator().validate(event)
            risk = EdgeRiskEngine().calculate(event, validation)
            message = build_sensor_message(event, validation, risk)
            database.process_event(message, DecisionEngine(), SamplingManager())
        planner = AdaptiveSamplingPlanner(database)
        plan = planner.generate(2, request_id="synthetic-demo-cycle-001")
        return {
            "data_kind": "SYNTHETIC_TEST_FIXTURE",
            "database_scope": "Disposable temporary database; production database is never opened.",
            "plan": plan,
            "phase4_samples": database.samples(),
            "inspection_matches": planner.inspect(plan["plan_id"]) == [plan],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end-to-end', action='store_true', help='Execute the isolated planner, virtual lifecycle and in-process MQTT workflow')
    args = parser.parse_args()
    if args.end_to_end:
        from decision.sampling_e2e import run_end_to_end
        report = run_end_to_end()
    else:
        report = run_demo()
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
