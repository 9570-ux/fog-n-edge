"""Broker-independent Phase 2 unit tests."""

import json
from pathlib import Path

import pytest

from mqtt.message_utils import (
    DuplicateDetector, OfflineQueue, build_ack, build_sensor_message, parse_ack,
    parse_sensor_message, serialize_message, topic,
)
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


def sample_message():
    event = MarineSensorSimulator(seed=4).generate("normal")
    validation = SensorValidator().validate(event)
    risk = EdgeRiskEngine().calculate(event, validation)
    return build_sensor_message(event, validation, risk)


def test_topic_generation_for_multiple_zones():
    assert topic("zone-b", "sensors") == "marine/zone-b/sensors"
    assert topic("zone-a", "commands") == "marine/zone-a/commands"
    assert topic("zone-c", "ack") == "marine/zone-c/ack"


def test_sensor_serialization_and_parsing_round_trip():
    message = sample_message()
    assert parse_sensor_message(serialize_message(message)) == message


@pytest.mark.parametrize("payload,reason", [
    (b"{bad", "Invalid JSON"),
    (b"", "Empty payload"),
])
def test_invalid_payload_is_rejected(payload, reason):
    with pytest.raises(ValueError, match=reason):
        parse_sensor_message(payload)


def test_missing_required_field_is_rejected():
    message = sample_message()
    del message["device_id"]
    with pytest.raises(ValueError, match="device_id"):
        parse_sensor_message(json.dumps(message))


def test_unsupported_schema_and_invalid_sequence_are_rejected():
    message = sample_message()
    message["schema_version"] = "9.0"
    with pytest.raises(ValueError, match="Unsupported schema"):
        parse_sensor_message(json.dumps(message))
    message = sample_message()
    message["sequence_number"] = 0
    with pytest.raises(ValueError, match="sequence"):
        parse_sensor_message(json.dumps(message))


def test_duplicate_detection_uses_device_and_sequence():
    detector = DuplicateDetector()
    message = sample_message()
    assert detector.is_duplicate(message) is False
    assert detector.is_duplicate(message) is True
    message["device_id"] = "another-node"
    assert detector.is_duplicate(message) is False


def test_offline_queue_append_order_and_ack_cleanup():
    path = Path("data/test_offline_queue.jsonl")
    path.unlink(missing_ok=True)
    try:
        queue = OfflineQueue(path)
        second = sample_message(); second["sequence_number"] = 2
        first = sample_message(); first["sequence_number"] = 1
        queue.append(second); queue.append(first)
        assert [item["sequence_number"] for item in queue.read_all()] == [1, 2]
        assert queue.remove(first["device_id"], 1) is True
        assert [item["sequence_number"] for item in queue.read_all()] == [2]
        assert queue.remove(first["device_id"], 99) is False
    finally:
        path.unlink(missing_ok=True)


def test_acknowledgement_round_trip():
    message = sample_message()
    acknowledgement = build_ack(message)
    assert parse_ack(json.dumps(acknowledgement)) == acknowledgement
