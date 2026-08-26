# AI-Enabled Edge-Fog Marine HAB Early-Warning System

Software prototype for a B.Tech project that simulates marine measurements,
checks sensor quality, estimates preliminary environmental HAB risk at an Edge
node, and delivers traceable events to a Fog node through MQTT.

> **Safety limitation:** This prototype predicts environmental HAB risk only.
> It does not directly detect toxins, identify toxin-producing algal strains, or
> certify seafood safety. High-risk results require laboratory confirmation.

## Project progress

| Phase | Status |
|---|---|
| Phase 1 — Sensor Simulation & Edge Risk | ✅ Completed |
| Phase 2 — MQTT Edge-Fog Communication | ✅ Completed |
| Phase 3 — Database & Dashboard | ⏳ Pending |
| Phase 4 — Decision / Sampling Logic | ⏳ Pending |
| Phase 5 — ESP32 Hardware Integration | ⏳ Pending |
| Phase 6 — Pump & Alert Integration | ⏳ Pending |
| Phase 7 — AI Model | ⏳ Pending |
| Phase 8 — Final Integration & Testing | ⏳ Pending |

Phase 1 remains independently runnable. Phase 2 is software-only on one Windows
laptop; no ESP32, Raspberry Pi, physical sensor, pump, database, dashboard, or
machine-learning component is included.

## Architecture

```text
Phase 1 simulator -> validation -> Edge risk engine
                                      |
                                      v
                              Edge MQTT publisher
                                      |
                           Mosquitto broker (QoS 1)
                                      |
                                      v
                               Fog MQTT receiver
                                      |
                         validation + duplicate check
                                      |
                                application ACK
```

Edge saves every event to `data/offline_queue.jsonl` before publishing and
removes it only after Fog returns a `RECEIVED` or `DUPLICATE` acknowledgement.
This is the Phase 2 store-and-forward mechanism when the broker is unavailable.
In simple terms, Phase 1 creates and checks the marine reading; Edge sends it,
Mosquitto carries it, and Fog validates and confirms receipt.

When MQTT is unavailable:

```text
Event generated -> MQTT unavailable -> Event stored in offline queue
```

When the connection returns:

```text
Reconnect -> Queued events replayed -> Fog receives event
          -> Fog acknowledgement -> Acknowledged event removed from queue
```

## Project structure

```text
marine-edge-fog/
|-- app.py
|-- config.py
|-- pytest.ini
|-- requirements.txt
|-- README.md
|-- simulator/
|   `-- sensor_simulator.py
|-- validation/
|   `-- sensor_validator.py
|-- risk/
|   `-- edge_risk_engine.py
|-- mqtt/
|   |-- __init__.py
|   |-- message_utils.py
|   |-- edge_publisher.py
|   `-- fog_receiver.py
|-- data/
|   `-- .gitkeep
`-- tests/
    |-- test_scenarios.py
    `-- test_phase2_mqtt.py
```

The runtime queue is generated automatically and ignored by Git.

## Requirements and initial setup

- Windows 10/11
- Python 3.10 or newer (Python 3)
- Existing project virtual environment at `..\.venv`
- `paho-mqtt` (installed through `requirements.txt`)
- Eclipse Mosquitto MQTT Broker for Windows

The working virtual environment is in the parent `fog and edge computin`
folder. For a first-time setup, run:

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If script activation is blocked for the current PowerShell session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
..\.venv\Scripts\Activate.ps1
```

This policy is temporary. You can instead call
`..\.venv\Scripts\python.exe` in place of `python`.

## Install Mosquitto on Windows

Mosquitto is system software and is not installed by `requirements.txt`.
The working Windows installation path is `C:\Program Files\Mosquitto`.

1. Visit the official Eclipse Mosquitto website and open its Download page.
2. Download the Windows 64-bit installer.
3. Run it, keep the default components and default installation path.
4. The Mosquitto Windows service may start automatically after installation.
5. Open a new PowerShell and verify the executable:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -h
```

## Check whether the MQTT broker is running

Before starting another broker, check port 1883:

```powershell
netstat -ano | findstr :1883
```

If the result contains `LISTENING`, an MQTT broker is already running and a
separate broker terminal is not required. Otherwise, start it manually:

```powershell
& "C:\Program Files\Mosquitto\mosquitto.exe" -v
```

If this command reports `Only one usage of each socket address...`, the
Mosquitto service or another broker instance is normally already using port
1883. Do not start a second instance; use the broker that is already listening.

# Running Phase 2

## Phase 2 Quick Start

Open three separate PowerShell terminals.

### 1. Terminal 1 — Broker

```powershell
& "C:\Program Files\Mosquitto\mosquitto.exe" -v
```

Expected output includes `Opening ipv4 listen socket on port 1883`.
If `netstat -ano | findstr :1883` already shows `LISTENING`, skip Terminal 1.

### 2. Terminal 2 — Fog receiver

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m mqtt.fog_receiver
```

Expected output:

```text
Connecting to MQTT broker at localhost:1883...
Connected to MQTT broker. Subscribed to marine/+/sensors

FOG NODE - MQTT EVENT RECEIVED
Device          : coastal-node-01
Zone            : zone-b
Sequence        : 1
Sensor Validity : VALID
Edge Risk Level : LOW
MQTT Status     : RECEIVED
```

### 3. Terminal 3 — Edge publisher

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m mqtt.edge_publisher
```

Expected output includes:

```text
Connecting to MQTT broker at localhost:1883...
Connected to MQTT broker (ONLINE).
Published sequence 1 (awaiting Fog acknowledgement).
Fog acknowledged sequence 1; removed from offline queue.
```

### 4. Observe messages

Leave all terminals running. Sequence numbers increase 1, 2, 3, and so on,
and Fog acknowledges each event.

### 5. Test offline mode

Press `Ctrl+C` in Terminal 1. Edge continues generating data and reports that
events were safely queued in `data/offline_queue.jsonl`.

### 6. Restart Broker

```powershell
& "C:\Program Files\Mosquitto\mosquitto.exe" -v
```

### 7. Verify synchronization

Edge reports `RECONNECTED`, replays queued messages in sequence order, receives
Fog acknowledgements, and removes acknowledged records. An empty queue file is
normal.

## Stopping the services

Press `Ctrl+C` once in the Edge, Fog, and manually started Mosquitto terminals.
A graceful shutdown returns each terminal to its PowerShell prompt without an
unnecessary traceback. Then deactivate Python with:

```powershell
deactivate
```

## Phase 1 application

The original interactive menu is unchanged:

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python app.py
```

It supports normal, medium, high/critical, invalid pH, low dissolved oxygen,
high turbidity, missing sensor, stuck sensor, sudden change, and automatic
simulation scenarios. Invalid sensor input blocks risk prediction.

## MQTT protocol

The reusable topic builder supports `zone-a`, `zone-b`, `zone-c`, and future
single-level zone names.

| Topic | Purpose |
|---|---|
| `marine/zone-b/sensors` | Complete event consumed by Fog |
| `marine/zone-b/edge-risk` | Edge risk event for future consumers |
| `marine/zone-b/status` | Retained ONLINE/OFFLINE/RECONNECTED state and LWT |
| `marine/zone-b/commands` | Reserved Phase 2 route for Fog commands |
| `marine/zone-b/ack` | Fog application acknowledgement |

Sensor events use MQTT QoS 1. JSON includes schema version, device, zone,
timestamp, sequence, five readings, sensor validity and score, plus Edge risk
score and level. Fog rejects empty/invalid JSON, missing fields, unsupported
schemas, and invalid sequences without stopping. Duplicate identity is
`device_id + sequence_number`.

Configuration is centralized in `config.py`. Optional local overrides:

```powershell
$env:MARINE_MQTT_HOST = "localhost"
$env:MARINE_MQTT_PORT = "1883"
$env:MARINE_EDGE_INTERVAL = "3"
```

Never put usernames, passwords, or tokens in source control.

## Automated tests

Tests do not require a running broker:

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m pytest
```

They cover all Phase 1 scenarios plus topics, JSON, malformed/missing data,
schemas/sequences, duplicates, queue ordering/cleanup, and acknowledgements.

Verified result:

```text
20 passed
Phase 1 tests: 11
Phase 2 tests: 9
```

## Manual Phase 2 verification results

The following behavior has been manually verified with Mosquitto:

- Fog receiver and Edge publisher connected successfully.
- Events arrived in sequential order.
- LOW, MEDIUM, CRITICAL, and INVALID sensor messages were received.
- Fog acknowledgements reached Edge.
- An event queued while MQTT was unavailable was replayed after reconnect.
- Acknowledged events were removed from `data/offline_queue.jsonl`.

## Optional malformed-message test

With Broker and Fog running:

```powershell
& "C:\Program Files\Mosquitto\mosquitto_pub.exe" -h localhost -t "marine/zone-b/sensors" -m "{bad-json"
```

Fog logs `INVALID MQTT MESSAGE` and continues. Automated tests also cover
missing fields and duplicate events.

## Troubleshooting

| Problem | Solution |
|---|---|
| `mosquitto` not recognized | Mosquitto is absent or not in PATH. Use `& "C:\Program Files\Mosquitto\mosquitto.exe" -v` or install the official Eclipse Mosquitto Windows package. |
| Connection refused / Edge cannot connect | Start Terminal 1 and confirm it listens on 1883; check environment host/port. |
| Port 1883 already in use | Run `netstat -ano \| findstr :1883`. A Mosquitto Windows service may already be running; do not start a second broker. |
| `No module named mqtt` | The terminal is in the parent folder. `cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"`, then run the module command again. |
| `No module named paho` | Activate `..\.venv`, then run `python -m pip install paho-mqtt` or install all requirements. |
| `pytest` not recognized | Use `python -m pytest`. If missing, run `python -m pip install pytest`. |
| `requirements.txt` not found | Run `dir`, then enter the real project folder with `cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"`. |
| Fog receives no messages | Start Broker, Fog, then Edge; verify all use the same host, port, and zone. |
| Offline queue not clearing | Fog must be running to send ACKs. Wait for replay and check queue warnings; do not delete unacknowledged data. |
| Wrong working directory | `Get-Location` must end in `marine-edge-fog` before `python -m mqtt...`. |
| Virtual environment inactive | Run `..\.venv\Scripts\Activate.ps1`, or use `..\.venv\Scripts\python.exe`. |
| Graceful shutdown / Ctrl+C | Press once and allow a few seconds for the current MQTT operation to close. |

## Quick start for later runs

1. Check the broker: `netstat -ano | findstr :1883`.
2. In the Fog terminal, enter the project, activate `..\.venv`, and run
   `python -m mqtt.fog_receiver`.
3. In the Edge terminal, enter the project, activate `..\.venv`, and run
   `python -m mqtt.edge_publisher`.
4. Observe events and acknowledgements; use `Ctrl+C` to stop.

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m mqtt.fog_receiver
```

In a second project terminal:

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m mqtt.edge_publisher
```

## Basic Git commands

```powershell
git status
git add .
git commit -m "Complete Phase 2 MQTT Edge-Fog communication"
git push
```

Never paste a GitHub password, personal access token, or credential into a
tracked project file.

## Risk disclaimer

Limits and risk rules in `config.py` are prototype engineering assumptions.
They require validation with local history and laboratory-confirmed data before
operational or seafood-safety use.
