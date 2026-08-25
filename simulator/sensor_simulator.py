"""Generate repeatable marine sensor scenarios for Phase 1."""

from __future__ import annotations

from datetime import datetime
import random
from typing import Any

from config import DEVICE_ID, ZONE_ID


class MarineSensorSimulator:
    """Create marine sensor events with an increasing sequence number."""

    SCENARIOS = (
        "normal",
        "medium",
        "high",
        "invalid_ph",
        "low_do",
        "high_turbidity",
        "missing_sensor",
        "stuck_sensor",
        "sudden_change",
    )

    def __init__(
        self,
        device_id: str = DEVICE_ID,
        zone_id: str = ZONE_ID,
        seed: int | None = None,
    ) -> None:
        self.device_id = device_id
        self.zone_id = zone_id
        self.sequence_number = 0
        self.random = random.Random(seed)
        self._stuck_temperature = 27.2
        self._sudden_change_calls = 0

    def _uniform(self, low: float, high: float, digits: int = 2) -> float:
        return round(self.random.uniform(low, high), digits)

    def _base_event(self) -> dict[str, Any]:
        self.sequence_number += 1
        return {
            "device_id": self.device_id,
            "zone_id": self.zone_id,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sequence_number": self.sequence_number,
        }

    def generate(self, scenario: str = "normal") -> dict[str, Any]:
        """Generate one event for a named scenario."""
        scenario = scenario.strip().lower()
        if scenario not in self.SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")

        event = self._base_event()
        generators = {
            "normal": self._normal_values,
            "medium": self._medium_values,
            "high": self._high_values,
            "invalid_ph": self._invalid_ph_values,
            "low_do": self._low_do_values,
            "high_turbidity": self._high_turbidity_values,
            "missing_sensor": self._missing_sensor_values,
            "stuck_sensor": self._stuck_sensor_values,
            "sudden_change": self._sudden_change_values,
        }
        event.update(generators[scenario]())
        return event

    def generate_random(self) -> dict[str, Any]:
        """Generate a realistic mixture of normal and stressed events."""
        scenario = self.random.choices(
            ["normal", "medium", "high", "low_do", "high_turbidity"],
            weights=[50, 25, 10, 8, 7],
            k=1,
        )[0]
        return self.generate(scenario)

    def _normal_values(self) -> dict[str, float]:
        return {
            "temperature_c": self._uniform(24.0, 28.5),
            "ph": self._uniform(7.8, 8.3),
            "salinity_psu": self._uniform(31.0, 35.5),
            "turbidity_ntu": self._uniform(5.0, 22.0),
            "dissolved_oxygen_mg_l": self._uniform(5.5, 8.0),
        }

    def _medium_values(self) -> dict[str, float]:
        return {
            "temperature_c": self._uniform(29.1, 30.5),
            "ph": self._uniform(7.7, 8.4),
            "salinity_psu": self._uniform(30.0, 36.0),
            "turbidity_ntu": self._uniform(28.0, 42.0),
            "dissolved_oxygen_mg_l": self._uniform(4.3, 4.9),
        }

    def _high_values(self) -> dict[str, float]:
        return {
            "temperature_c": self._uniform(31.2, 33.8),
            "ph": self._uniform(8.1, 8.6),
            "salinity_psu": self._uniform(32.0, 38.0),
            "turbidity_ntu": self._uniform(50.0, 78.0),
            "dissolved_oxygen_mg_l": self._uniform(2.6, 3.8),
        }

    def _invalid_ph_values(self) -> dict[str, float]:
        values = self._normal_values()
        values["ph"] = 15.2
        return values

    def _low_do_values(self) -> dict[str, float]:
        values = self._normal_values()
        values["dissolved_oxygen_mg_l"] = self._uniform(1.0, 2.3)
        return values

    def _high_turbidity_values(self) -> dict[str, float]:
        values = self._normal_values()
        values["turbidity_ntu"] = self._uniform(85.0, 140.0)
        return values

    def _missing_sensor_values(self) -> dict[str, Any]:
        values: dict[str, Any] = self._normal_values()
        values["dissolved_oxygen_mg_l"] = None
        return values

    def _stuck_sensor_values(self) -> dict[str, float]:
        values = self._normal_values()
        values["temperature_c"] = self._stuck_temperature
        return values

    def _sudden_change_values(self) -> dict[str, float]:
        values = self._normal_values()
        self._sudden_change_calls += 1
        values["temperature_c"] = 27.1 if self._sudden_change_calls == 1 else 45.0
        return values

