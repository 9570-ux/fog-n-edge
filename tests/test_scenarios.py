"""Unit and scenario tests using only Python's standard library."""

import unittest

from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


class PhaseOneScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.simulator = MarineSensorSimulator(seed=42)
        self.validator = SensorValidator()
        self.engine = EdgeRiskEngine()

    def evaluate(self, scenario: str):
        event = self.simulator.generate(scenario)
        validation = self.validator.validate(event)
        risk = self.engine.calculate(event, validation)
        return event, validation, risk

    def test_normal_readings_are_valid_and_low_risk(self):
        _, validation, risk = self.evaluate("normal")
        self.assertTrue(validation["valid"])
        self.assertEqual("LOW", risk["risk_level"])

    def test_invalid_ph_is_blocked(self):
        _, validation, risk = self.evaluate("invalid_ph")
        self.assertFalse(validation["valid"])
        self.assertEqual("INVALID", risk["risk_level"])
        self.assertEqual("BLOCKED", risk["risk_prediction"])
        self.assertTrue(any("pH" in error for error in validation["errors"]))

    def test_missing_value_is_detected(self):
        _, validation, risk = self.evaluate("missing_sensor")
        self.assertFalse(validation["valid"])
        self.assertEqual("INVALID", risk["risk_level"])
        self.assertTrue(any("missing" in error.lower() for error in validation["errors"]))

    def test_high_turbidity_contributes_to_risk(self):
        _, validation, risk = self.evaluate("high_turbidity")
        self.assertTrue(validation["valid"])
        self.assertTrue(any("turbidity" in reason.lower() for reason in risk["reasons"]))
        self.assertGreaterEqual(risk["risk_score"], 30)

    def test_low_do_contributes_to_risk(self):
        _, validation, risk = self.evaluate("low_do")
        self.assertTrue(validation["valid"])
        self.assertTrue(any("dissolved oxygen" in reason.lower() for reason in risk["reasons"]))
        self.assertGreaterEqual(risk["risk_score"], 40)

    def test_high_scenario_is_high_or_critical(self):
        _, validation, risk = self.evaluate("high")
        self.assertTrue(validation["valid"])
        self.assertIn(risk["risk_level"], {"HIGH", "CRITICAL"})

    def test_invalid_never_gets_normal_classification(self):
        for scenario in ("invalid_ph", "missing_sensor"):
            _, validation, risk = self.evaluate(scenario)
            self.assertFalse(validation["valid"])
            self.assertEqual("INVALID", risk["risk_level"])

    def test_sequence_numbers_increase(self):
        first = self.simulator.generate("normal")
        second = self.simulator.generate("normal")
        self.assertEqual(first["sequence_number"] + 1, second["sequence_number"])

    def test_stuck_sensor_detection(self):
        results = []
        for _ in range(4):
            event = self.simulator.generate("stuck_sensor")
            results.append(self.validator.validate(event))
        self.assertFalse(results[-1]["valid"])
        self.assertTrue(any("stuck" in warning.lower() for warning in results[-1]["warnings"]))

    def test_sudden_change_detection(self):
        first = self.simulator.generate("sudden_change")
        second = self.simulator.generate("sudden_change")
        self.assertTrue(self.validator.validate(first)["valid"])
        result = self.validator.validate(second)
        self.assertFalse(result["valid"])
        self.assertTrue(any("unrealistically" in warning.lower() for warning in result["warnings"]))

    def test_medium_scenario_is_medium(self):
        _, validation, risk = self.evaluate("medium")
        self.assertTrue(validation["valid"])
        self.assertEqual("MEDIUM", risk["risk_level"])


if __name__ == "__main__":
    unittest.main()

