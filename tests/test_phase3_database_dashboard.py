"""Phase 3 database and dashboard tests using an isolated SQLite file."""

from pathlib import Path

import pytest

from dashboard.app import create_app
from database import MarineDatabase
from mqtt.message_utils import build_sensor_message
from mqtt.message_utils import serialize_message
from mqtt.fog_receiver import FogReceiver
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


TEST_DB = Path("data/test_phase3.db")


def remove_test_database():
    for suffix in ("", "-shm", "-wal"):
        Path(str(TEST_DB) + suffix).unlink(missing_ok=True)


@pytest.fixture
def database():
    remove_test_database()
    instance = MarineDatabase(TEST_DB)
    yield instance
    remove_test_database()


def message(scenario="normal", sequence=1):
    event = MarineSensorSimulator(seed=8).generate(scenario)
    event["sequence_number"] = sequence
    validation = SensorValidator().validate(event)
    risk = EdgeRiskEngine().calculate(event, validation)
    return build_sensor_message(event, validation, risk)


def test_database_initializes_empty_tables(database):
    assert TEST_DB.exists()
    assert database.event_count() == 0
    assert database.latest_event() is None
    assert database.history() == []
    assert database.alerts() == []


def test_event_insertion_and_latest_query(database):
    inserted, event_id = database.insert_event(message())
    assert inserted is True
    assert event_id is not None
    latest = database.latest_event()
    assert latest["device_id"] == "coastal-node-01"
    assert latest["sensor_valid"] is True


def test_database_duplicate_prevention(database):
    event = message()
    assert database.insert_event(event)[0] is True
    assert database.insert_event(event)[0] is False
    assert database.event_count() == 1


def test_history_is_newest_first_and_limited(database):
    for sequence in range(1, 4):
        database.insert_event(message(sequence=sequence))
    history = database.history(2)
    assert [item["sequence_number"] for item in history] == [3, 2]


@pytest.mark.parametrize("scenario,expected", [
    ("medium", "MEDIUM"),
    ("high", "CRITICAL"),
    ("invalid_ph", "INVALID SENSOR"),
])
def test_alert_creation_for_actionable_results(database, scenario, expected):
    database.insert_event(message(scenario))
    assert database.alerts()[0]["alert_level"] == expected


def test_low_risk_does_not_create_alert(database):
    database.insert_event(message("normal"))
    assert database.alerts() == []


def test_alert_query_can_filter_level(database):
    database.insert_event(message("medium", 1))
    database.insert_event(message("high", 2))
    assert len(database.alerts("MEDIUM")) == 1
    assert database.alerts("MEDIUM")[0]["alert_level"] == "MEDIUM"


def test_invalid_sensor_is_stored_without_fake_score(database):
    database.insert_event(message("invalid_ph"))
    latest = database.latest_event()
    assert latest["sensor_valid"] is False
    assert latest["edge_risk_score"] is None
    assert latest["edge_risk_level"] == "INVALID"


@pytest.fixture
def client(database):
    app = create_app(TEST_DB)
    app.config.update(TESTING=True)
    return app.test_client()


def test_dashboard_and_empty_api_responses(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/latest").get_json() == {"event": None}
    assert client.get("/api/history").get_json()["events"] == []
    assert client.get("/api/alerts").get_json()["alerts"] == []
    status = client.get("/api/status").get_json()
    assert status["fog_data_status"] == "WAITING"
    assert status["total_readings"] == 0


def test_latest_history_alert_and_status_apis(client, database):
    database.insert_event(message("medium"))
    assert client.get("/api/latest").get_json()["event"]["edge_risk_level"] == "MEDIUM"
    assert len(client.get("/api/history?limit=50").get_json()["events"]) == 1
    assert len(client.get("/api/alerts?level=MEDIUM").get_json()["alerts"]) == 1
    status = client.get("/api/status").get_json()
    assert status["total_readings"] == 1
    assert status["fog_data_status"] == "DATA AVAILABLE"


def test_fog_message_stores_once_and_acknowledges_duplicate(database):
    class Incoming:
        payload = serialize_message(message()).encode()

    class FakeClient:
        def __init__(self):
            self.published = []

        def publish(self, topic_name, payload, qos):
            self.published.append((topic_name, payload, qos))

    receiver = FogReceiver(database)
    client = FakeClient()
    receiver._on_message(client, None, Incoming())
    receiver._on_message(client, None, Incoming())
    assert database.event_count() == 1
    assert len(client.published) == 2
    assert '"status":"RECEIVED"' in client.published[0][1]
    assert '"status":"DUPLICATE"' in client.published[1][1]
