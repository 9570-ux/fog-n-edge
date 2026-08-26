"""Deterministic operational recommendations based on validated Edge risk."""

from __future__ import annotations

from typing import Any


class DecisionEngine:
    """Map the existing Phase 1 risk result to a careful prototype action."""

    RULES = {
        "LOW": {
            "action": "MONITOR", "sampling_required": False, "priority": "NORMAL",
            "reason": "Environmental parameters within prototype baseline range.",
        },
        "MEDIUM": {
            "action": "RETEST", "sampling_required": False, "priority": "WARNING",
            "reason": "Moderate environmental stress detected; increased monitoring recommended.",
        },
        "HIGH": {
            "action": "HOLD_HARVEST", "sampling_required": True, "priority": "HIGH",
            "reason": "High environmental HAB-associated risk; hold/verification and sampling recommended.",
        },
        "CRITICAL": {
            "action": "COLLECT_SAMPLE", "sampling_required": True, "priority": "CRITICAL",
            "reason": "Critical environmental conditions detected; immediate verification sampling recommended.",
        },
        "INVALID": {
            "action": "SENSOR_MAINTENANCE", "sampling_required": False,
            "priority": "SENSOR_WARNING",
            "reason": "Sensor validity failed; risk decision blocked until sensor verification.",
        },
    }

    def decide(self, message: dict[str, Any]) -> dict[str, Any]:
        level = "INVALID" if not message["sensor_valid"] else message["edge_risk_level"]
        if level not in self.RULES:
            raise ValueError(f"Unsupported risk level for decision: {level}")
        return {
            "device_id": message["device_id"],
            "zone_id": message["zone_id"],
            "timestamp": message["timestamp"],
            "risk_level": level,
            "risk_score": message["edge_risk_score"] if level != "INVALID" else None,
            **self.RULES[level],
            "status": "GENERATED",
        }
