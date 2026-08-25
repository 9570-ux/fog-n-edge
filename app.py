"""Interactive terminal application for Phase 1."""

from __future__ import annotations

import time
from typing import Any

from config import AUTOMATIC_INTERVAL_SECONDS
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator

MENU = """
========================================
MARINE EDGE MONITORING - PHASE 1
========================================

Choose simulation scenario:

1. Normal
2. Medium Risk
3. High Risk
4. Invalid pH
5. Low Dissolved Oxygen
6. High Turbidity
7. Missing Sensor
8. Stuck Sensor
9. Sudden Sensor Change
10. Automatic Random Simulation
0. Exit
"""

CHOICES = {
    "1": "normal", "2": "medium", "3": "high", "4": "invalid_ph",
    "5": "low_do", "6": "high_turbidity", "7": "missing_sensor",
}


def format_value(value: Any, unit: str = "") -> str:
    if value is None: return "MISSING"
    return f"{value}{unit}"


def recommended_action(validation: dict[str, Any], risk: dict[str, Any]) -> list[str]:
    if not validation["valid"]:
        return ["CHECK / RECALIBRATE SENSOR"]
    return {
        "LOW": ["CONTINUE MONITORING"],
        "MEDIUM": ["WARNING", "INCREASE MONITORING FREQUENCY"],
        "HIGH": ["ALERT", "SAMPLING VERIFICATION REQUIRED"],
        "CRITICAL": ["CRITICAL ALERT", "SAMPLING VERIFICATION REQUIRED"],
    }[risk["risk_level"]]


def display_result(event: dict[str, Any], validation: dict[str, Any], risk: dict[str, Any]) -> None:
    print("\n----------------------------------------")
    print("MARINE SENSOR EVENT")
    print("----------------------------------------\n")
    print(f"Device             : {event['device_id']}")
    print(f"Zone               : {event['zone_id']}")
    print(f"Timestamp          : {event['timestamp']}")
    print(f"Sequence           : {event['sequence_number']}\n")
    # ASCII unit avoids mojibake in older Windows terminal code pages.
    print(f"Temperature        : {format_value(event.get('temperature_c'), ' deg C')}")
    print(f"pH                 : {format_value(event.get('ph'))}")
    print(f"Salinity           : {format_value(event.get('salinity_psu'), ' PSU')}")
    print(f"Turbidity          : {format_value(event.get('turbidity_ntu'), ' NTU')}")
    print(f"Dissolved Oxygen   : {format_value(event.get('dissolved_oxygen_mg_l'), ' mg/L')}\n")
    print(f"Sensor Validity    : {'VALID' if validation['valid'] else 'INVALID'}")
    print(f"Validity Score     : {validation['validity_score']:.2f}")
    if not validation["valid"]:
        print("Risk Prediction    : BLOCKED")
        messages = validation["errors"] + validation["warnings"]
        print("\nErrors / Warnings:")
        for message in messages: print(f"- {message}")
    else:
        print(f"\nEdge Risk Score    : {risk['risk_score']} / 100")
        print(f"Edge Risk Level    : {risk['risk_level']}")
        print("\nReasons:")
        for reason in risk["reasons"]: print(f"- {reason}")
    print("\nRecommended Action:")
    for line in recommended_action(validation, risk): print(line)
    print("----------------------------------------")


def process_event(event: dict[str, Any], validator: SensorValidator, engine: EdgeRiskEngine) -> None:
    validation = validator.validate(event)
    risk = engine.calculate(event, validation)
    display_result(event, validation, risk)


def run_repeated_scenario(simulator: MarineSensorSimulator, scenario: str, count: int) -> None:
    validator = SensorValidator(); engine = EdgeRiskEngine()
    for _ in range(count): process_event(simulator.generate(scenario), validator, engine)


def run_automatic(simulator: MarineSensorSimulator) -> None:
    validator = SensorValidator(); engine = EdgeRiskEngine()
    print("\nAutomatic simulation started. Press Ctrl+C to stop.")
    try:
        while True:
            process_event(simulator.generate_random(), validator, engine)
            time.sleep(AUTOMATIC_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nAutomatic simulation stopped.")


def main() -> None:
    simulator = MarineSensorSimulator()
    while True:
        print(MENU)
        choice = input("Enter choice: ").strip()
        if choice == "0":
            print("Exiting Phase 1 simulation."); break
        if choice in CHOICES:
            process_event(simulator.generate(CHOICES[choice]), SensorValidator(), EdgeRiskEngine())
        elif choice == "8":
            run_repeated_scenario(simulator, "stuck_sensor", 4)
        elif choice == "9":
            run_repeated_scenario(simulator, "sudden_change", 2)
        elif choice == "10":
            run_automatic(simulator)
        else:
            print("Invalid choice. Enter a number from 0 to 10.")


if __name__ == "__main__":
    main()
