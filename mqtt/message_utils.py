"""MQTT message, topic, duplicate, and durable queue helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any, Iterable

from config import MQTT_SCHEMA_VERSION, MQTT_TOPIC_ROOT

READING_FIELDS = (
    "temperature_c", "ph", "salinity_psu", "turbidity_ntu",
    "dissolved_oxygen_mg_l",
)
REQUIRED_FIELDS = (
    "schema_version", "device_id", "zone_id", "timestamp",
    "sequence_number", *READING_FIELDS, "sensor_valid", "validity_score",
    "edge_risk_score", "edge_risk_level",
)


def topic(zone_id: str, channel: str) -> str:
    """Return a normalized zone topic for sensors/risk/status/commands/ack."""
    zone = zone_id.strip().lower()
    if not zone or "/" in zone:
        raise ValueError("zone_id must be a non-empty single topic level")
    if channel not in {"sensors", "edge-risk", "status", "commands", "ack"}:
        raise ValueError(f"Unsupported MQTT channel: {channel}")
    return f"{MQTT_TOPIC_ROOT}/{zone}/{channel}"


def build_sensor_message(
    event: dict[str, Any], validation: dict[str, Any], risk: dict[str, Any]
) -> dict[str, Any]:
    message = {
        "schema_version": MQTT_SCHEMA_VERSION,
        "device_id": event["device_id"],
        "zone_id": event["zone_id"],
        "timestamp": event["timestamp"],
        "sequence_number": event["sequence_number"],
        **{field: event.get(field) for field in READING_FIELDS},
        "sensor_valid": validation["valid"],
        "validity_score": validation["validity_score"],
        "edge_risk_score": risk["risk_score"],
        "edge_risk_level": risk["risk_level"],
    }
    return message


def serialize_message(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"), ensure_ascii=True)


def parse_sensor_message(payload: bytes | str) -> dict[str, Any]:
    if not payload:
        raise ValueError("Empty payload")
    try:
        message = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(message, dict):
        raise ValueError("JSON payload must be an object")
    missing = [field for field in REQUIRED_FIELDS if field not in message]
    if missing:
        raise ValueError(f"Missing required field '{missing[0]}'")
    if message["schema_version"] != MQTT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version '{message['schema_version']}'")
    sequence = message["sequence_number"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("Invalid sequence number")
    if not isinstance(message["device_id"], str) or not message["device_id"].strip():
        raise ValueError("Invalid device_id")
    if not isinstance(message["zone_id"], str) or not message["zone_id"].strip():
        raise ValueError("Invalid zone_id")
    return message


def build_ack(message: dict[str, Any], status: str = "RECEIVED") -> dict[str, Any]:
    return {
        "schema_version": MQTT_SCHEMA_VERSION,
        "device_id": message["device_id"],
        "sequence_number": message["sequence_number"],
        "status": status,
    }


def parse_ack(payload: bytes | str) -> dict[str, Any]:
    try:
        ack = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid acknowledgement JSON: {exc}") from exc
    required = ("schema_version", "device_id", "sequence_number", "status")
    if not isinstance(ack, dict) or any(field not in ack for field in required):
        raise ValueError("Invalid acknowledgement fields")
    if ack["schema_version"] != MQTT_SCHEMA_VERSION:
        raise ValueError("Unsupported acknowledgement schema version")
    if not isinstance(ack["sequence_number"], int) or ack["sequence_number"] < 1:
        raise ValueError("Invalid acknowledgement sequence number")
    return ack


class DuplicateDetector:
    """In-memory duplicate detection for a Phase 2 Fog process."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, int]] = set()

    def is_duplicate(self, message: dict[str, Any]) -> bool:
        key = (message["device_id"], message["sequence_number"])
        if key in self._seen:
            return True
        self._seen.add(key)
        return False


class OfflineQueue:
    """Crash-safe JSON Lines queue; records remain until Fog acknowledges."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def append(self, message: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(serialize_message(message) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            records: list[dict[str, Any]] = []
            with self.path.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Corrupt queue record at line {line_number}") from exc
                    records.append(item)
            return sorted(records, key=lambda item: item["sequence_number"])

    def remove(self, device_id: str, sequence_number: int) -> bool:
        with self._lock:
            records = self.read_all()
            retained = [
                item for item in records
                if (item.get("device_id"), item.get("sequence_number"))
                != (device_id, sequence_number)
            ]
            if len(retained) == len(records):
                return False
            self._replace(retained)
            return True

    def _replace(self, records: Iterable[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as stream:
            for item in records:
                stream.write(serialize_message(item) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, self.path)
