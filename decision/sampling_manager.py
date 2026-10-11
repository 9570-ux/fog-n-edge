"""Sampling cooldown/state logic and simulated MQTT command messages."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any
from uuid import uuid4

from config import SAMPLING_COMMAND_DURATION_SECONDS, SAMPLING_COOLDOWN_SECONDS
from mqtt.message_utils import MQTT_SCHEMA_VERSION


class SamplingManager:
    """Determine whether a persistent sample should be created."""

    TRIGGER_LEVELS = {"HIGH", "CRITICAL"}
    RESET_LEVELS = {"LOW", "MEDIUM", "INVALID"}

    def __init__(self, cooldown_seconds: int = SAMPLING_COOLDOWN_SECONDS) -> None:
        self.cooldown_seconds = cooldown_seconds

    def should_request(
        self, risk_level: str, previous_risk_level: str | None,
        last_sample_at: str | None, now: datetime,
    ) -> tuple[bool, str]:
        if risk_level not in self.TRIGGER_LEVELS:
            return False, "RISK_LEVEL_DOES_NOT_REQUIRE_SAMPLE"
        if previous_risk_level in self.RESET_LEVELS or previous_risk_level is None:
            return True, "RISK_TRANSITION_TRIGGER"
        if not last_sample_at:
            return True, "NO_PREVIOUS_SAMPLE"
        previous_time = datetime.fromisoformat(last_sample_at)
        if previous_time.tzinfo is None:
            previous_time = previous_time.replace(tzinfo=timezone.utc)
        elapsed = (now - previous_time.astimezone(timezone.utc)).total_seconds()
        if elapsed >= self.cooldown_seconds:
            return True, "COOLDOWN_EXPIRED"
        return False, "COOLDOWN_ACTIVE"

    @staticmethod
    def build_command(sample: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": MQTT_SCHEMA_VERSION,
            "command": "COLLECT_SAMPLE",
            "sample_id": sample["sample_id"],
            "device_id": sample["device_id"],
            "zone_id": sample["zone_id"],
            "requested_at": sample["requested_at"],
            "reason": sample["trigger_reason"],
            "duration_seconds": SAMPLING_COMMAND_DURATION_SECONDS,
            **({"simulation_lifecycle": True} if sample.get("collection_status") in
               {"SIMULATED_PENDING", "SIMULATED_IN_PROGRESS", "SIMULATED_COMPLETED"} else {}),
        }


COMMAND_FIELDS = {
    "schema_version", "command", "sample_id", "device_id", "zone_id",
    "requested_at", "reason", "duration_seconds",
}
COMMAND_ACK_FIELDS = {
    "schema_version", "sample_id", "device_id", "status", "timestamp",
}


def parse_sampling_command(payload: bytes | str) -> dict[str, Any]:
    try:
        command = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid sampling command JSON: {exc}") from exc
    if not isinstance(command, dict) or not COMMAND_FIELDS.issubset(command):
        raise ValueError("Invalid sampling command fields")
    if command["schema_version"] != MQTT_SCHEMA_VERSION:
        raise ValueError("Unsupported sampling command schema")
    if command["command"] != "COLLECT_SAMPLE":
        raise ValueError("Unsupported sampling command")
    if "simulation_lifecycle" in command:
        duration = command["duration_seconds"]
        if command["simulation_lifecycle"] is not True or not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration < 0:
            raise ValueError("Invalid explicit simulation command")
        for field in ("sample_id", "device_id", "zone_id", "requested_at"):
            if not isinstance(command[field], str) or not command[field].strip():
                raise ValueError(f"Invalid simulation command {field}")
        from mqtt.message_utils import topic
        topic(command["zone_id"], "commands")
        if any(character in command["zone_id"] for character in ("+", "#")):
            raise ValueError("Simulation zone cannot contain MQTT wildcards")
        try:
            requested = datetime.fromisoformat(command["requested_at"])
        except ValueError as exc:
            raise ValueError("Invalid simulation request timestamp") from exc
        if requested.tzinfo is None:
            raise ValueError("Simulation request timestamp must include timezone")
    return command


def build_command_ack(command: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": MQTT_SCHEMA_VERSION,
        "sample_id": command["sample_id"],
        "device_id": command["device_id"],
        "status": "SIMULATED_ACK",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def parse_command_ack(payload: bytes | str) -> dict[str, Any]:
    try:
        acknowledgement = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid command acknowledgement JSON: {exc}") from exc
    if not isinstance(acknowledgement, dict) or not COMMAND_ACK_FIELDS.issubset(acknowledgement):
        raise ValueError("Invalid command acknowledgement fields")
    if acknowledgement["schema_version"] != MQTT_SCHEMA_VERSION:
        raise ValueError("Unsupported command acknowledgement schema")
    if acknowledgement["status"] != "SIMULATED_ACK":
        raise ValueError("Unsupported command acknowledgement status")
    for field in ("sample_id", "device_id", "timestamp"):
        if not isinstance(acknowledgement[field], str) or not acknowledgement[field].strip():
            raise ValueError(f"Invalid command acknowledgement {field}")
    try:
        timestamp = datetime.fromisoformat(acknowledgement["timestamp"])
    except ValueError as exc:
        raise ValueError("Invalid command acknowledgement timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError("Command acknowledgement timestamp must include a timezone")
    return acknowledgement


SIMULATION_EVENT_FIELDS = {
    "schema_version", "event_id", "event_type", "sample_id", "device_id", "zone_id",
    "simulator_run_id", "started_at", "completed_at", "is_simulation",
}


def validate_simulation_event(event: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize simulation evidence, never physical measurements."""
    if not isinstance(event, dict) or set(event) != SIMULATION_EVENT_FIELDS:
        raise ValueError("Invalid simulation event fields")
    if event["schema_version"] != MQTT_SCHEMA_VERSION or event["is_simulation"] is not True:
        raise ValueError("Simulation schema/marker is invalid")
    if event["event_type"] not in ("SIMULATION_STARTED", "SIMULATION_COMPLETED"):
        raise ValueError("Unsupported simulation event type")
    result = dict(event)
    for field in ("event_id", "sample_id", "device_id", "zone_id", "simulator_run_id"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise ValueError(f"Invalid simulation {field}")
    from mqtt.message_utils import topic
    topic(event["zone_id"], "simulation-events")
    if any(character in event["zone_id"] for character in ("+", "#")):
        raise ValueError("Simulation zone cannot contain MQTT wildcards")
    for field in ("started_at", "completed_at"):
        value = event[field]
        if field == "completed_at" and event["event_type"] == "SIMULATION_STARTED":
            if value is not None:
                raise ValueError("Start event cannot assert completion")
            continue
        if not isinstance(value, str):
            raise ValueError(f"Invalid simulation {field}")
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid simulation {field}") from exc
        if timestamp.tzinfo is None:
            raise ValueError("Simulation timestamps must include a timezone")
        result[field] = timestamp.astimezone(timezone.utc).isoformat()
    if result["completed_at"] is not None and datetime.fromisoformat(result["completed_at"]) < datetime.fromisoformat(result["started_at"]):
        raise ValueError("Completion precedes simulation start")
    return result


def build_simulation_event(command: dict[str, Any], event_type: str,
                           simulator_run_id: str, started_at: str,
                           completed_at: str | None = None, *, event_id: str | None = None) -> dict[str, Any]:
    return validate_simulation_event({
        "schema_version": MQTT_SCHEMA_VERSION, "event_id": event_id or str(uuid4()),
        "event_type": event_type, "sample_id": command["sample_id"],
        "device_id": command["device_id"], "zone_id": command["zone_id"],
        "simulator_run_id": simulator_run_id, "started_at": started_at,
        "completed_at": completed_at, "is_simulation": True,
    })


def parse_simulation_event(payload: bytes | str) -> dict[str, Any]:
    try:
        event = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid simulation JSON: {exc}") from exc
    return validate_simulation_event(event)
