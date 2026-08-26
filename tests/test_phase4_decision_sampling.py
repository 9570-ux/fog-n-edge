"""Phase 4 deterministic decision and simulated sampling regression tests."""

from pathlib import Path

import pytest

from config import (
    EDGE_MQTT_CLIENT_ID, FOG_MQTT_CLIENT_ID, SAMPLING_RECEIVER_MQTT_CLIENT_ID,
)
from dashboard.app import create_app
from database import MarineDatabase
from decision import DecisionEngine, SamplingManager
from decision.sampling_manager import (
    build_command_ack, parse_command_ack, parse_sampling_command,
)
from mqtt.fog_receiver import FogReceiver
from mqtt.message_utils import build_sensor_message, serialize_message
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


TEST_DB = Path("data/test_phase4.db")


def remove_test_database():
    for suffix in ("", "-shm", "-wal"):
        Path(str(TEST_DB) + suffix).unlink(missing_ok=True)


@pytest.fixture
def database():
    remove_test_database()
    instance = MarineDatabase(TEST_DB)
    yield instance
    remove_test_database()


def message(level="LOW", sequence=1, valid=True):
    event = MarineSensorSimulator(seed=8).generate("normal")
    event["sequence_number"] = sequence
    validation = SensorValidator().validate(event)
    risk = EdgeRiskEngine().calculate(event, validation)
    result = build_sensor_message(event, validation, risk)
    result["sensor_valid"] = valid
    result["validity_score"] = 1.0 if valid else 0.0
    result["edge_risk_level"] = level if valid else "INVALID"
    result["edge_risk_score"] = {
        "LOW": 12, "MEDIUM": 45, "HIGH": 72, "CRITICAL": 91,
    }.get(level) if valid else None
    return result


@pytest.mark.parametrize("level,action,sampling,priority", [
    ("LOW", "MONITOR", False, "NORMAL"),
    ("MEDIUM", "RETEST", False, "WARNING"),
    ("HIGH", "HOLD_HARVEST", True, "HIGH"),
    ("CRITICAL", "COLLECT_SAMPLE", True, "CRITICAL"),
])
def test_decision_rules(level, action, sampling, priority):
    result = DecisionEngine().decide(message(level))
    assert (result["action"], result["sampling_required"], result["priority"]) == (
        action, sampling, priority,
    )


def test_invalid_sensor_blocks_risk_decision():
    result = DecisionEngine().decide(message("LOW", valid=False))
    assert result["risk_level"] == "INVALID"
    assert result["risk_score"] is None
    assert result["action"] == "SENSOR_MAINTENANCE"
    assert result["sampling_required"] is False


def test_all_phase4_mqtt_components_have_unique_client_ids():
    assert len({
        EDGE_MQTT_CLIENT_ID, FOG_MQTT_CLIENT_ID,
        SAMPLING_RECEIVER_MQTT_CLIENT_ID,
    }) == 3


def process(database, event, cooldown=900):
    return database.process_event(event, DecisionEngine(), SamplingManager(cooldown))


def test_low_and_medium_create_decisions_without_samples(database):
    process(database, message("LOW", 1))
    process(database, message("MEDIUM", 2))
    assert len(database.decisions()) == 2
    assert database.samples() == []


def test_high_creates_linked_persistent_sample_and_command(database):
    result = process(database, message("HIGH"))
    assert result["decision"]["decision_id"].startswith("DEC-")
    assert result["sample"]["sample_id"].startswith("SAMPLE-")
    assert result["sample"]["decision_id"] == result["decision"]["decision_id"]
    assert result["command"]["sample_id"] == result["sample"]["sample_id"]
    assert database.latest_decision()["sample_id"] == result["sample"]["sample_id"]


def test_repeated_elevated_risk_is_suppressed_during_cooldown(database):
    first = process(database, message("HIGH", 1))
    second = process(database, message("CRITICAL", 2))
    assert first["sample"] is not None
    assert second["sample"] is None
    assert second["command"] is None
    assert second["decision"]["status"] == "SAMPLE_SUPPRESSED_COOLDOWN_ACTIVE"
    assert len(database.samples()) == 1


def test_low_reset_allows_new_high_sample_even_inside_cooldown(database):
    process(database, message("HIGH", 1))
    process(database, message("LOW", 2))
    result = process(database, message("HIGH", 3))
    assert result["sample"] is not None
    assert len(database.samples()) == 2


def test_duplicate_event_creates_no_duplicate_decision_or_sample(database):
    event = message("CRITICAL")
    first = process(database, event)
    duplicate = process(database, event)
    assert first["inserted"] is True
    assert duplicate["inserted"] is False
    assert len(database.decisions()) == 1
    assert len(database.samples()) == 1


def test_command_and_ack_round_trip(database):
    command = process(database, message("HIGH"))["command"]
    parsed = parse_sampling_command(serialize_message(command))
    acknowledgement = build_command_ack(parsed)
    assert parse_command_ack(serialize_message(acknowledgement)) == acknowledgement
    assert database.update_sample_command_ack(command["sample_id"], "SIMULATED_ACK")
    assert database.samples()[0]["command_status"] == "SIMULATED_ACK"


def test_invalid_command_payloads_are_rejected():
    with pytest.raises(ValueError):
        parse_sampling_command("{}")
    with pytest.raises(ValueError):
        parse_command_ack("not-json")


def test_phase4_dashboard_apis(database):
    process(database, message("HIGH"))
    app = create_app(TEST_DB)
    app.config.update(TESTING=True)
    client = app.test_client()
    assert client.get("/api/decision/latest").get_json()["decision"]["action"] == "HOLD_HARVEST"
    assert len(client.get("/api/decisions?limit=20").get_json()["decisions"]) == 1
    assert len(client.get("/api/samples?limit=20").get_json()["samples"]) == 1


def test_fog_persists_before_publishing_command_and_sensor_ack(database):
    event = message("HIGH")

    class Incoming:
        topic = f"marine/{event['zone_id']}/sensors"
        payload = serialize_message(event).encode()

    class PublishResult:
        rc = 0

    class FakeClient:
        def __init__(self):
            self.published = []

        def publish(self, topic_name, payload, qos):
            self.published.append((topic_name, payload, qos))
            return PublishResult()

    receiver = FogReceiver(database)
    client = FakeClient()
    receiver._on_message(client, None, Incoming())
    assert len(database.decisions()) == 1
    assert len(database.samples()) == 1
    assert [item[0] for item in client.published] == [
        f"marine/{event['zone_id']}/commands", f"marine/{event['zone_id']}/ack",
    ]
    assert database.samples()[0]["command_status"] == "PUBLISHED"
