# Marine Edge-Fog Monitoring - Phase 1

Software-only simulation prototype for the B.Tech project **AI-Enabled
Edge-Fog Early-Warning and Automated Sampling System for Marine Harmful Algal
Bloom Risk Monitoring**.

> This prototype predicts environmental HAB risk only. It does not directly
> detect toxins, identify an algal strain, or certify seafood safety.

## Phase 1 objective

Phase 1 demonstrates the following local pipeline without hardware, networking,
machine learning, or a database:

```text
Marine Sensor Simulator -> Sensor Validation -> Edge Risk Engine -> Terminal Output
```

It creates simulated temperature, pH, salinity, turbidity, and dissolved-oxygen
readings; validates their quality; and calculates a transparent preliminary
Edge risk using configurable prototype rules.

## Folder structure

```text
marine-edge-fog/
|-- app.py
|-- config.py
|-- requirements.txt
|-- README.md
|-- simulator/
|   |-- __init__.py
|   `-- sensor_simulator.py
|-- validation/
|   |-- __init__.py
|   `-- sensor_validator.py
|-- risk/
|   |-- __init__.py
|   `-- edge_risk_engine.py
`-- tests/
    |-- __init__.py
    `-- test_scenarios.py
```

## Requirements

- Windows 10/11
- Python 3.10 or newer (Python 3.11 or 3.12 recommended)
- `pytest` for the Phase 1 automated test suite

## Installation (Windows PowerShell)

Open PowerShell in the `marine-edge-fog` folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, this project can still be run with:

```powershell
.\.venv\Scripts\python.exe app.py
```

## Run the application

```powershell
python app.py
```

Choose a numbered scenario from the terminal menu. Automatic mode produces one
event approximately every three seconds and stops with `Ctrl+C`.

## Run automated tests

```powershell
python -m pytest
```

## Simulation scenarios

| Scenario | Purpose | Expected behaviour |
|---|---|---|
| Normal | Baseline marine values | Valid, LOW, continue monitoring |
| Medium Risk | Moderate temperature/turbidity/DO stress | Valid, MEDIUM, increase monitoring |
| High Risk | Combined high temperature/turbidity and low DO | Valid, HIGH/CRITICAL, sampling verification |
| Invalid pH | Impossible pH 15.2 | Invalid, prediction blocked |
| Low DO | Very low dissolved oxygen | Elevated risk with DO reason |
| High Turbidity | Abnormally high turbidity | Elevated risk with turbidity reason |
| Missing Sensor | DO value is `None` | Missing value detected, prediction blocked |
| Stuck Sensor | Identical temperature repeated four times | Stuck warning, prediction blocked |
| Sudden Change | Temperature jumps from 27.1 to 45.0 | Range/jump detected, prediction blocked |
| Automatic | Weighted mixture of valid scenarios | Repeated validation and risk output |

## Example output

```text
Sensor Validity    : VALID
Validity Score     : 1.00

Edge Risk Score    : 72 / 100
Edge Risk Level    : HIGH

Recommended Action:
ALERT
SAMPLING VERIFICATION REQUIRED
```

Invalid input is never converted into a normal risk classification:

```text
Sensor Validity    : INVALID
Risk Prediction    : BLOCKED
Recommended Action:
CHECK / RECALIBRATE SENSOR
```

## Configuration

All physical limits, rate-of-change thresholds, stuck-reading count, risk
rules, risk categories, device identifiers, and automatic-mode interval are in
`config.py`. The risk thresholds are prototype assumptions and require review
against local historical and laboratory-confirmed data before field use.

## Planned Phase 2 (not implemented here)

Phase 2 can add MQTT communication between the simulated/physical Edge node and
a Fog service, duplicate-event protection, offline synchronisation, and a
simulated sampling-command acknowledgement. ESP32, Raspberry Pi, database,
dashboard, machine learning, and physical pump control remain outside Phase 1.
