"""Phase 5 synthetic fixtures; all databases live in pytest temporary folders."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from database import MarineDatabase
from database.db import SCHEMA
from decision import DecisionEngine, SamplingManager
from decision.adaptive_sampling import AdaptiveSamplingPlanner
from decision.sampling_evaluation import evaluate
from tests.test_phase4_decision_sampling import message

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path):
    return MarineDatabase(tmp_path / "phase5.db")


def add(database, zone="zone-a", score=60, sequence=1, age=0, valid=True):
    event = message("HIGH" if score is not None and score >= 50 else "LOW", sequence, valid)
    event.update(device_id=zone, zone_id=zone, timestamp=(NOW - timedelta(seconds=age)).isoformat(),
                 edge_risk_score=score if valid else None)
    database.insert_event(event)
    return event


def test_formula_and_supported_explanation(database):
    add(database)
    plan = AdaptiveSamplingPlanner(database).generate(1, now=NOW)
    item = plan["selected"][0]
    assert item["components"] == {"risk": 60, "trend": 0, "overdue": 100, "quality_proxy": 0}
    assert item["priority_score"] == 50
    assert {r["code"] for r in item["reasons"]} == {"HIGH_RISK", "NO_VALID_SAMPLE"}
    assert item["status"] == "PLANNED" and item["sample_id"] is None
    assert database.sample_count() == 0


@pytest.mark.parametrize("budget,count", [(0, 0), (1, 1), (20, 2)])
def test_budget_and_ties(database, budget, count):
    add(database, "zone-b")
    add(database, "zone-a")
    result = AdaptiveSamplingPlanner(database).generate(budget, now=NOW)
    assert [item["zone_id"] for item in result["selected"]] == ["zone-a", "zone-b"][:count]
    assert [item["rank"] for item in result["selected"]] == list(range(1, count + 1))


@pytest.mark.parametrize("budget", [-1, 1.5, True, "2"])
def test_invalid_budget(database, budget):
    with pytest.raises(ValueError, match="Budget"):
        AdaptiveSamplingPlanner(database).generate(budget)


def test_empty_and_all_pending(database):
    planner = AdaptiveSamplingPlanner(database)
    assert planner.generate(now=NOW)["selected"] == []
    add(database)
    planner.generate(1, now=NOW)
    result = planner.generate(2, now=NOW)
    assert result["selected"] == []
    assert result["snapshot"]["blocked_zones"] == ["zone-a"]


def test_retry_safe_across_restart_and_parameter_conflict(database):
    add(database)
    result = AdaptiveSamplingPlanner(database).generate(1, request_id="cycle-1", now=NOW)
    restarted = AdaptiveSamplingPlanner(MarineDatabase(database.path))
    assert restarted.generate(1, request_id="cycle-1") == result
    with pytest.raises(ValueError, match="different"):
        restarted.generate(2, request_id="cycle-1")
    with pytest.raises(ValueError):
        restarted.generate(1, request_id="")


def test_concurrent_planning_reserves_once(database):
    add(database)
    def generate(index):
        return AdaptiveSamplingPlanner(database).generate(1, request_id=str(index), now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        plans = list(pool.map(generate, [1, 2]))
    assert sum(len(plan["selected"]) for plan in plans) == 1


def test_trend_uses_event_time_and_distinct_observations(database):
    add(database, score=70, sequence=2)
    add(database, score=20, sequence=1, age=60)
    item = AdaptiveSamplingPlanner(database).generate(1, now=NOW)["selected"][0]
    assert item["components"]["trend"] == 50
    assert item["sensor_event_id"] == 1
    assert "INCREASING_RISK" in {r["code"] for r in item["reasons"]}


def test_trend_does_not_cross_invalid_reading(database):
    add(database, score=10, sequence=1, age=120)
    add(database, score=None, sequence=2, age=60, valid=False)
    add(database, score=90, sequence=3)
    assert AdaptiveSamplingPlanner(database).generate(1, now=NOW)["selected"][0]["components"]["trend"] == 0


@pytest.mark.parametrize("age,valid,score", [(1800, True, 60), (0, False, None), (0, True, None)])
def test_stale_invalid_missing_risk_proxy(database, age, valid, score):
    add(database, age=age, valid=valid, score=score)
    item = AdaptiveSamplingPlanner(database).generate(1, now=NOW)["selected"][0]
    assert item["components"]["quality_proxy"] == 100
    assert item["evidence"]["uncertainty_kind"] == "DATA_QUALITY_PROXY"
    if score is None:
        assert item["risk_score"] is None
        assert item["risk_level"] == "UNKNOWN"


def test_incomplete_data_and_unusable_timestamp(database):
    event = add(database)
    with closing(database._connect()) as connection, connection:
        connection.execute("UPDATE sensor_events SET ph = NULL, event_timestamp = 'bad' WHERE id = 1")
    item = AdaptiveSamplingPlanner(database).generate(1, now=NOW)["selected"][0]
    assert "ph" in item["evidence"]["bad_fields"]
    assert item["risk_score"] is None
    assert item["evidence"]["malformed_timestamp_count"] == 1


def test_future_observation_not_used_as_current_risk(database):
    add(database, score=100, age=-3600)
    item = AdaptiveSamplingPlanner(database).generate(1, now=NOW)["selected"][0]
    assert item["risk_score"] is None


def test_legacy_ack_remains_pending_and_history_is_preserved(database):
    event = message("HIGH")
    event.update(timestamp=NOW.isoformat())
    processed = database.process_event(event, DecisionEngine(), SamplingManager())
    database.update_sample_command_ack(processed["sample"]["sample_id"], "SIMULATED_ACK")
    before = database.samples()
    assert AdaptiveSamplingPlanner(database).generate(5, now=NOW)["selected"] == []
    assert database.samples() == before


def test_virtual_completion_is_explicit_and_overdue_is_prioritized(database):
    add(database, "zone-a", score=0)
    add(database, "zone-b", score=0)
    planner = AdaptiveSamplingPlanner(database)
    plan = planner.generate(1, now=NOW)
    progressing = planner.transition(plan["plan_id"], "zone-a", "IN_PROGRESS", now=NOW)
    assert progressing["selected"][0]["sample_id"].startswith("VIRTUAL-")
    assert progressing["selected"][0]["completed_at"] is None
    completed = planner.transition(plan["plan_id"], "zone-a", "COMPLETED", now=NOW)
    assert planner.transition(plan["plan_id"], "zone-a", "COMPLETED") == completed
    later = planner.generate(2, now=NOW + timedelta(seconds=30))
    assert later["selected"][0]["zone_id"] == "zone-b"
    assert later["selected"][1]["components"]["overdue"] < 1
    with pytest.raises(ValueError, match="Terminal"):
        planner.transition(plan["plan_id"], "zone-a", "IN_PROGRESS")
    assert database.samples() == []


def test_cancel_releases_reservation_and_invalid_transition(database):
    add(database)
    planner = AdaptiveSamplingPlanner(database)
    plan = planner.generate(1, now=NOW)
    with pytest.raises(ValueError, match="precedes"):
        planner.transition(plan["plan_id"], "zone-a", "COMPLETED", now=NOW - timedelta(seconds=1))
    planner.transition(plan["plan_id"], "zone-a", "CANCELLED", now=NOW)
    assert len(planner.generate(1, now=NOW)["selected"]) == 1
    with pytest.raises(ValueError):
        planner.transition("unknown", "zone-a", "COMPLETED")


def test_feedback_is_actual_subsequent_observation_not_lab_label(database):
    add(database)
    planner = AdaptiveSamplingPlanner(database)
    plan = planner.generate(1, now=NOW)
    assert planner.feedback(plan["plan_id"])[0]["subsequent_observation"] is None
    add(database, sequence=2, age=-60, score=80)
    feedback = planner.feedback(plan["plan_id"])[0]
    assert feedback["subsequent_observation"]["edge_risk_score"] == 80
    assert feedback["observed_risk_score_change"] == 20
    assert feedback["laboratory_outcome"] is None


def test_additive_schema_preserves_legacy_records(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_schema = SCHEMA.split("-- Phase 5 additive migration")[0]
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(legacy_schema)
        event = message("LOW")
        event["timestamp"] = NOW.isoformat()
        MarineDatabase._insert_event_row(connection, event, NOW.isoformat())
        before = tuple(connection.execute("SELECT * FROM sensor_events").fetchone())
    database = MarineDatabase(path)
    AdaptiveSamplingPlanner(database).generate(1, now=NOW)
    with closing(database._connect()) as connection:
        assert tuple(connection.execute("SELECT * FROM sensor_events").fetchone()) == before
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("weights,stale", [({"risk": 1}, 1),
    ({"risk": -1, "trend": 1, "overdue": 1, "quality_proxy": 1}, 1),
    ({"risk": 0, "trend": 0, "overdue": 0, "quality_proxy": 0}, 1),
    ({"risk": float("nan"), "trend": 1, "overdue": 1, "quality_proxy": 1}, 1),
    ({"risk": 1, "trend": 1, "overdue": 1, "quality_proxy": 1}, 0)])
def test_configuration_validation(database, weights, stale):
    with pytest.raises(ValueError):
        AdaptiveSamplingPlanner(database, weights=weights, stale_seconds=stale)


def test_evaluation_equal_budgets_and_repeatability():
    first = evaluate(seed=10, budget=2, cycles=4)
    second = evaluate(seed=10, budget=2, cycles=4)
    assert first["data_kind"] == "SYNTHETIC_SIMULATION"
    for name in first["strategies"]:
        a, b = first["strategies"][name], second["strategies"][name]
        assert a["number_selected"] == b["number_selected"] == 8
        assert a["budget_utilization"] == 1
        assert a["pending_redundant_selections"] == 0
        assert [c["selected_zones"] for c in a["cycles"]] == [c["selected_zones"] for c in b["cycles"]]
    assert all(s["number_selected"] == 0 for s in evaluate(budget=0, cycles=1)["strategies"].values())


def test_cli_plan_inspection_and_errors(tmp_path):
    import subprocess
    import sys
    path = tmp_path / "cli.db"
    prefix = [sys.executable, "-m", "decision.adaptive_sampling", "--database", str(path)]
    planned = subprocess.run(prefix + ["plan", "--budget", "0", "--request-id", "cli-cycle"], capture_output=True, text=True)
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(planned.stdout)
    assert plan["selected"] == [] and plan["budget"] == 0
    inspected = subprocess.run(prefix + ["inspect", "--plan-id", plan["plan_id"]], capture_output=True, text=True)
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout) == [plan]
    invalid = subprocess.run(prefix + ["plan", "--budget", "-1"], capture_output=True, text=True)
    assert invalid.returncode != 0 and "Budget must" in invalid.stderr


def test_custom_weights_and_decreasing_risk(database):
    add(database, score=70, sequence=1, age=60)
    add(database, score=20, sequence=2)
    planner = AdaptiveSamplingPlanner(database, weights={"risk": 1, "trend": 0, "overdue": 0, "quality_proxy": 0})
    item = planner.generate(1, now=NOW)["selected"][0]
    assert item["priority_score"] == 20
    assert item["components"]["trend"] == 0
    assert "INCREASING_RISK" not in {r["code"] for r in item["reasons"]}


@pytest.mark.parametrize("command_status", ["PENDING", "PUBLISHED", "SIMULATED_ACK"])
def test_phase4_block_is_zone_scoped_and_transport_status_does_not_close_it(database, command_status):
    event = message("HIGH")
    event.update(device_id="zone-b", zone_id="zone-b", timestamp=NOW.isoformat())
    result = database.process_event(event, DecisionEngine(), SamplingManager())
    database.update_sample_command_ack(result["sample"]["sample_id"], command_status)
    before = database.samples()
    add(database, "zone-a", score=45)
    add(database, "zone-c", score=0)
    plan = AdaptiveSamplingPlanner(database).generate(2, now=NOW)
    assert plan["snapshot"]["blocked_zones"] == ["zone-b"]
    assert [item["zone_id"] for item in plan["snapshot"]["candidates"]] == ["zone-a", "zone-c"]
    assert [item["zone_id"] for item in plan["selected"]] == ["zone-a", "zone-c"]
    assert all(item["status"] == "PLANNED" and item["sample_id"] is None and item["completed_at"] is None for item in plan["selected"])
    assert database.samples() == before
    assert before[0]["status"] == "REQUESTED"
    assert before[0]["collection_status"] == "SIMULATED_PENDING"
    assert before[0]["laboratory_status"] == "NOT_SUBMITTED"


def test_empty_plan_retry_does_not_recompute_after_new_zone_is_observed(database):
    event = message("HIGH")
    event.update(timestamp=NOW.isoformat())
    database.process_event(event, DecisionEngine(), SamplingManager())
    planner = AdaptiveSamplingPlanner(database)
    empty = planner.generate(2, request_id="cycle-001", now=NOW)
    assert empty["selected"] == []
    add(database, "zone-a", score=30)
    assert planner.generate(2, request_id="cycle-001", now=NOW) == empty
    fresh = planner.generate(2, request_id="cycle-002", now=NOW)
    assert [item["zone_id"] for item in fresh["selected"]] == ["zone-a"]
    assert database.samples()[0]["status"] == "REQUESTED"


def test_disposable_demo_selects_eligible_zones_without_opening_production(monkeypatch, tmp_path):
    from config import DATABASE_PATH
    from decision.sampling_demo import run_demo
    paths = []
    original_init = MarineDatabase.__init__
    def isolated_init(self, path=DATABASE_PATH):
        resolved = __import__("pathlib").Path(path).resolve()
        assert resolved != DATABASE_PATH.resolve()
        paths.append(resolved)
        original_init(self, path)
    monkeypatch.setattr(MarineDatabase, "__init__", isolated_init)
    result = run_demo()
    assert result["data_kind"] == "SYNTHETIC_TEST_FIXTURE"
    assert result["inspection_matches"]
    assert result["plan"]["snapshot"]["blocked_zones"] == ["zone-b"]
    assert [item["zone_id"] for item in result["plan"]["selected"]] == ["zone-a", "zone-c"]
    assert all(item["status"] == "PLANNED" and item["sample_id"] is None for item in result["plan"]["selected"])
    assert result["phase4_samples"][0]["status"] == "REQUESTED"
    assert result["phase4_samples"][0]["laboratory_status"] == "NOT_SUBMITTED"
    assert paths and all(not path.exists() for path in paths)
