"""Transparent deterministic risk rules for the Phase 1 Edge node."""

from __future__ import annotations

from typing import Any

from config import RISK_LEVEL_THRESHOLDS, RISK_RULES


class EdgeRiskEngine:
    """Calculate a preliminary environmental risk score from valid input."""

    def calculate(
        self,
        event: dict[str, Any],
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        if not validation["valid"]:
            return {
                "risk_score": None,
                "risk_level": "INVALID",
                "risk_prediction": "BLOCKED",
                "reasons": ["Sensor validation failed"],
            }

        score = 0
        reasons: list[str] = []

        score += self._temperature_points(event["temperature_c"], reasons)
        score += self._ph_points(event["ph"], reasons)
        score += self._salinity_points(event["salinity_psu"], reasons)
        score += self._turbidity_points(event["turbidity_ntu"], reasons)
        score += self._do_points(event["dissolved_oxygen_mg_l"], reasons)

        score = min(100, score)
        return {
            "risk_score": score,
            "risk_level": self._level(score),
            "risk_prediction": "AVAILABLE",
            "reasons": reasons or ["All measured conditions are within prototype baseline ranges"],
        }

    @staticmethod
    def _temperature_points(value: float, reasons: list[str]) -> int:
        r = RISK_RULES["temperature"]
        if value >= r["critical"]:
            reasons.append("Critically high water temperature"); return r["points"][2]
        if value >= r["high"]:
            reasons.append("High water temperature"); return r["points"][1]
        if value >= r["medium"]:
            reasons.append("Elevated water temperature"); return r["points"][0]
        return 0

    @staticmethod
    def _ph_points(value: float, reasons: list[str]) -> int:
        r = RISK_RULES["ph"]
        if value < r["severe_low"] or value > r["severe_high"]:
            reasons.append("Severely abnormal pH"); return r["points"][1]
        if value < r["low"] or value > r["high"]:
            reasons.append("pH outside baseline range"); return r["points"][0]
        return 0

    @staticmethod
    def _salinity_points(value: float, reasons: list[str]) -> int:
        r = RISK_RULES["salinity"]
        if value < r["severe_low"] or value > r["severe_high"]:
            reasons.append("Severely abnormal salinity"); return r["points"][1]
        if value < r["low"] or value > r["high"]:
            reasons.append("Salinity outside baseline range"); return r["points"][0]
        return 0

    @staticmethod
    def _turbidity_points(value: float, reasons: list[str]) -> int:
        r = RISK_RULES["turbidity"]
        if value >= r["critical"]:
            reasons.append("Critically high turbidity"); return r["points"][2]
        if value >= r["high"]:
            reasons.append("High turbidity"); return r["points"][1]
        if value >= r["medium"]:
            reasons.append("Elevated turbidity"); return r["points"][0]
        return 0

    @staticmethod
    def _do_points(value: float, reasons: list[str]) -> int:
        r = RISK_RULES["dissolved_oxygen"]
        if value <= r["critical"]:
            reasons.append("Critically low dissolved oxygen"); return r["points"][2]
        if value <= r["high"]:
            reasons.append("Low dissolved oxygen"); return r["points"][1]
        if value <= r["medium"]:
            reasons.append("Reduced dissolved oxygen"); return r["points"][0]
        return 0

    @staticmethod
    def _level(score: int) -> str:
        if score >= RISK_LEVEL_THRESHOLDS["CRITICAL"]: return "CRITICAL"
        if score >= RISK_LEVEL_THRESHOLDS["HIGH"]: return "HIGH"
        if score >= RISK_LEVEL_THRESHOLDS["MEDIUM"]: return "MEDIUM"
        return "LOW"

