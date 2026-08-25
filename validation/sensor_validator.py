"""Validate marine readings independently of generation and risk logic."""

from __future__ import annotations

from collections import defaultdict, deque
from math import isclose
from typing import Any

from config import (
    FLOAT_EQUALITY_TOLERANCE,
    MAX_RATE_OF_CHANGE,
    SENSOR_FIELDS,
    SENSOR_LIMITS,
    STUCK_READING_COUNT,
)


class SensorValidator:
    """Stateful validator that detects ranges, jumps, and stuck sensors."""

    def __init__(self) -> None:
        self._history: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: {
                field: deque(maxlen=STUCK_READING_COUNT)
                for field in SENSOR_FIELDS
            }
        )

    def reset(self) -> None:
        """Clear historical values used for temporal checks."""
        self._history.clear()

    def validate(self, event: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        invalid_fields: list[str] = []
        device_id = str(event.get("device_id", "unknown-device"))
        histories = self._history[device_id]

        for field, label in SENSOR_FIELDS.items():
            value = event.get(field)
            if value is None:
                errors.append(f"{label} reading is missing")
                invalid_fields.append(field)
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{label} reading is not numeric")
                invalid_fields.append(field)
                continue

            limits = SENSOR_LIMITS[field]
            if value < limits["min"] or value > limits["max"]:
                errors.append(
                    f"{label} value outside allowed range "
                    f"({limits['min']} to {limits['max']})"
                )
                invalid_fields.append(field)

            history = histories[field]
            if history:
                change = abs(float(value) - history[-1])
                if change > MAX_RATE_OF_CHANGE[field]:
                    warnings.append(
                        f"{label} changed unrealistically by {change:.2f} "
                        "between consecutive readings"
                    )

            history.append(float(value))
            if len(history) == STUCK_READING_COUNT and all(
                isclose(
                    item,
                    history[0],
                    rel_tol=0.0,
                    abs_tol=FLOAT_EQUALITY_TOLERANCE,
                )
                for item in history
            ):
                warnings.append(
                    f"{label} appears stuck after "
                    f"{STUCK_READING_COUNT} identical readings"
                )

        # Missing/out-of-range data blocks prediction. Temporal warnings also
        # block prediction because their reliability must be checked first.
        valid = not errors and not warnings
        deductions = len(errors) * 0.20 + len(warnings) * 0.12
        validity_score = round(max(0.0, 1.0 - deductions), 2)
        return {
            "valid": valid,
            "validity_score": validity_score,
            "errors": errors,
            "warnings": warnings,
            "invalid_fields": invalid_fields,
        }

