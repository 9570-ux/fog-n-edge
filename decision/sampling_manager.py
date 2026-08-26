"""Sampling cooldown/state logic and simulated MQTT command messages."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

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
    return acknowledgement
