# AI-Enabled Edge-Fog Marine HAB Early-Warning System

Software prototype for a B.Tech project that simulates marine measurements,
checks sensor quality, estimates preliminary environmental HAB risk at an Edge
node, delivers traceable events to a Fog node through MQTT, and stores and
visualizes them locally.

> **Safety limitation:** This prototype predicts environmental HAB risk only.
> It does not directly detect toxins, identify toxin-producing algal strains, or
> certify seafood safety. High-risk results require laboratory confirmation.

## Project progress

| Phase | Status |
|---|---|
| Phase 1 — Sensor Simulation & Edge Risk | ✅ Completed |
| Phase 2 — MQTT Edge-Fog Communication | ✅ Completed |
| Phase 3 — Database & Dashboard | ✅ Completed |
| Phase 4 — Decision & Automated Sampling Logic | ✅ Completed |
| Phase 5 — ESP32 Hardware Integration | ⏳ Pending |
| Phase 6 — Pump & Alert Integration | ⏳ Pending |
| Phase 7 — AI Model | ⏳ Pending |
| Phase 8 — Final Integration & Testing | ⏳ Pending |

Phase 1 remains independently runnable. Phase 2 is software-only on one Windows
laptop. Phase 3 adds local SQLite persistence and a Flask dashboard. Phase 4
adds deterministic Fog decisions, persistent sample requests, cooldown/reset
protection, and an MQTT sampling-command simulator. ESP32, physical sensors,
real pumps, laboratory integration, and machine learning remain future work.

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
                      decision + cooldown/reset rules
                              |
                SQLite event/alert/decision/sample transaction
                       |              |              |
                application ACK  Flask dashboard  sampling command
                                                     |
                                             simulated receiver ACK
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
|-- decision/
|   |-- __init__.py
|   |-- decision_engine.py
|   `-- sampling_manager.py
|-- mqtt/
|   |-- __init__.py
|   |-- message_utils.py
|   |-- edge_publisher.py
|   |-- fog_receiver.py
|   `-- sampling_receiver.py
|-- database/
|   |-- __init__.py
|   `-- db.py
|-- dashboard/
|   |-- __init__.py
|   |-- app.py
|   |-- templates/
|   |   `-- index.html
|   `-- static/
|       |-- style.css
|       `-- dashboard.js
|-- data/
|   `-- .gitkeep
`-- tests/
    |-- test_scenarios.py
    |-- test_phase2_mqtt.py
    |-- test_phase3_database_dashboard.py
    `-- test_phase4_decision_sampling.py
```

The runtime queue and SQLite database are generated automatically and ignored
by Git.

## Requirements and initial setup

- Windows 10/11
- Python 3.10 or newer (Python 3)
- Existing project virtual environment at `..\.venv`
- `paho-mqtt` (installed through `requirements.txt`)
- Flask (installed through `requirements.txt`)
- Eclipse Mosquitto MQTT Broker for Windows

The working virtual environment is in the parent `fog and edge computin`
folder. On a fresh computer, clone and set up with:

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin"
git clone https://github.com/9570-ux/fog-n-edge.git marine-edge-fog
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

SQLite uses Python's standard library and initializes its tables automatically.
There is no separate database setup command. The runtime database is created at
the canonical absolute project location
`C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog\data\marine_monitoring.db`
when Fog or the dashboard first starts. The default no longer depends on the
terminal's current working directory. Both Fog and Dashboard print this active
path at startup.

Inspect the active database without changing its contents:

```powershell
python -m database.diagnostics
```

This prints the canonical path, sensor-event, decision and sample counts, plus
the latest decision.

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
| `marine/zone-b/commands` | Phase 4 simulated sample command from Fog |
| `marine/zone-b/command-ack` | Phase 4 simulated receiver acknowledgement |
| `marine/zone-b/ack` | Fog application acknowledgement |

Sensor events use MQTT QoS 1. JSON includes schema version, device, zone,
timestamp, sequence, five readings, sensor validity and score, plus Edge risk
score and level. Fog rejects empty/invalid JSON, missing fields, unsupported
schemas, and invalid sequences without stopping. Duplicate identity is
`device_id + sequence_number`.

MQTT component client IDs are explicit and different:

```text
Edge Publisher : marine-edge-coastal-node-01
Fog Receiver   : marine-fog-node-01
```

Run only one Edge Publisher and one Fog Receiver for this single-node
prototype. Mosquitto disconnects an older connection when a second process uses
the same client ID. Repeated `broker unavailable` / `RECONNECTED` messages every
1–2 seconds usually mean the same Edge or Fog command is running in two
terminals—not that the healthy broker is unavailable.

Configuration is centralized in `config.py`. Optional local overrides:

```powershell
$env:MARINE_MQTT_HOST = "localhost"
$env:MARINE_MQTT_PORT = "1883"
$env:MARINE_EDGE_INTERVAL = "3"
$env:MARINE_EDGE_CLIENT_ID = "marine-edge-coastal-node-01"
$env:MARINE_FOG_CLIENT_ID = "marine-fog-node-01"
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
57 passed
Phase 1 tests: 11
Phase 2 tests: 11
Phase 3 tests: 13
Phase 4 tests: 22
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

# Running Phase 3

Phase 3 keeps the Phase 1 and Phase 2 commands and adds automatic SQLite
storage plus a fourth dashboard terminal. Fog stores each new event before
sending its acknowledgement. Database uniqueness on `device_id +
sequence_number` prevents duplicates even after Fog restarts.

## Terminal 1 — MQTT Broker (optional when service is running)

```powershell
netstat -ano | findstr :1883
```

If no `LISTENING` result appears:

```powershell
& "C:\Program Files\Mosquitto\mosquitto.exe" -v
```

## Terminal 2 — Fog Receiver + SQLite storage

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m mqtt.fog_receiver
```

The database and tables initialize automatically at
`data/marine_monitoring.db`. A new event produces `Stored event in SQLite
database.` before the normal Fog output and acknowledgement.

## Terminal 3 — Edge Publisher

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m mqtt.edge_publisher
```

## Terminal 4 — Dashboard

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m dashboard.app
```

Expected output:

```text
Dashboard running at http://127.0.0.1:5000
```

Open `http://127.0.0.1:5000` in a browser. The page polls its read-only APIs
every five seconds, so new database events appear without restarting Flask.
Chart.js is loaded from the jsDelivr CDN; charts require internet access to
load that frontend library, while cards, tables, APIs, and stored data remain
local.

## Terminal 5 — Automated testing

Testing can run in a separate terminal while the operating terminals are open:

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m pytest
```

Current verified result: `35 passed`.

## Dashboard content and APIs

- System status, latest timestamp, device, zone, and total stored readings.
- Five latest sensor cards and a prominent LOW/MEDIUM/HIGH/CRITICAL/INVALID
  screening result.
- Database-backed history graphs with latest 20, 50, or 100 readings.
- Recent-events table and filterable persistent alerts.
- Empty database displays `Waiting for sensor data...` safely.
- INVALID events remain traceable, show `BLOCKED` instead of a fake score, and
  create an `INVALID SENSOR` alert.

Read-only endpoints:

```text
GET /api/latest
GET /api/history?limit=20
GET /api/alerts?level=CRITICAL
GET /api/status
```

Alert records are created for MEDIUM, HIGH, CRITICAL, and INVALID results. LOW
readings are stored but do not create an alert. These are environmental
screening alerts, not confirmation of toxin contamination.

## Phase 3 automated verification

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
..\.venv\Scripts\Activate.ps1
python -m pytest
```

Current suite breakdown:

```text
Phase 1: 11 tests
Phase 2: 11 tests
Phase 3: 13 tests
Total:   35 tests
```

Phase 3 tests use an isolated test database and never modify
`data/marine_monitoring.db`.

## Phase 3 manual verification results

The complete local flow was verified on Windows with the installed Mosquitto
service:

- Fog connected, stored sequential MQTT events, then acknowledged Edge.
- LOW, MEDIUM, CRITICAL, and INVALID events were persisted and displayed.
- INVALID displayed `BLOCKED` with no fabricated numeric risk score.
- Publishing the same device/sequence twice created only one database event.
- MEDIUM, CRITICAL, and INVALID SENSOR alerts appeared; filtering worked.
- Dashboard cards, recent table, 20/50 history controls, both database-backed
  charts, and all four read-only APIs worked without restarting Flask.
- After stopping and restarting the dashboard, 51 stored readings remained,
  confirming SQLite persistence.
- Empty-database behavior is covered by the automated dashboard/API test and
  displays `Waiting for sensor data...`.

## Normal / later Phase 3 run

1. Confirm port 1883 is listening.
2. Run `python -m mqtt.fog_receiver` in the activated project environment.
3. Run `python -m mqtt.edge_publisher` in another activated terminal.
4. Run `python -m dashboard.app` in a fourth activated terminal.
5. Open `http://127.0.0.1:5000`; stop services with `Ctrl+C`.

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
| `No module named flask` | Activate `..\.venv`, then run `python -m pip install -r requirements.txt`. |
| Database file not created | Start Fog or dashboard from the project folder and confirm the `data` folder is writable. Initialization is automatic. |
| `database is locked` | Stop duplicate Fog/dashboard processes, wait a few seconds, then use one instance of each. SQLite already waits briefly for normal concurrent access. |
| Dashboard opens but shows no data | Start Broker, Fog, and Edge in that order; confirm Fog logs `Stored event in SQLite database.` |
| MQTT works but database does not update | Confirm the running Fog is this Phase 3 project and check its terminal for `DATABASE ERROR`. |
| Continuous unavailable / RECONNECTED loop | Close every old Edge/Fog terminal with `Ctrl+C`, confirm no duplicate Python MQTT process remains, then start exactly one Fog and one Edge. Their startup logs must show different client IDs. |
| Browser cannot connect to localhost | Confirm Terminal 4 prints the dashboard URL and open exactly `http://127.0.0.1:5000`. |
| Port 5000 already in use | Stop the other Flask process, or set `$env:MARINE_DASHBOARD_PORT = "5001"` before running the dashboard and open that port. |
| INVALID sensor shows `None` | This is expected only for the numeric risk score; the dashboard shows `BLOCKED` and `INVALID`, not a fabricated risk number. |
| Charts have no data | Generate events through Edge/Fog. Also ensure internet is available for the Chart.js CDN. |
| `/api/decision/latest` returns `null` while sensor history grows | The usual cause is a Fog process started before Phase 4 code was loaded, or Fog/Dashboard using different relative database paths. Stop the old Fog, Edge, and Dashboard terminals with `Ctrl+C`; start the current Fog first, then Edge and Dashboard. Confirm Fog and Dashboard print the same canonical SQLite path. Wait for a new sequence—older Phase 3 rows are retained but are not silently backfilled into decisions. Run `python -m database.diagnostics` to confirm counts. |

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

# Running Phase 4

Phase 4 is still a software-only prototype. Fog converts every validated risk
result into a traceable decision and stores the event, alert, decision, and any
new sample request in one SQLite transaction before acknowledging Edge.

```text
Sensor Event
    ↓
Risk
    ↓
Decision Engine
    ↓
MONITOR / RETEST / SENSOR_MAINTENANCE / COLLECT_SAMPLE
    ↓
Decision Database
    ↓
Sample ID if required
    ↓
MQTT Sampling Command
    ↓
Dashboard
```

| Risk result | Decision | Sample request |
|---|---|---|
| LOW | `MONITOR` | No |
| MEDIUM | `RETEST` | No |
| HIGH | `COLLECT_SAMPLE` (harvest hold recommended) | Yes, subject to cooldown |
| CRITICAL | `COLLECT_SAMPLE` | Yes, subject to cooldown |
| INVALID | `SENSOR_MAINTENANCE` | No |

Repeated HIGH/CRITICAL readings do not create a new sample during the default
15-minute cooldown. A LOW, MEDIUM, or INVALID reading resets the elevated-risk
episode, so a later HIGH/CRITICAL transition can create a new request. Database
uniqueness also prevents duplicate MQTT delivery from creating duplicate
decisions or samples.

Open five PowerShell terminals in the project folder and activate the same
environment in Terminals 2–5.

## Terminal 1 — Mosquitto

If `netstat -ano | findstr :1883` does not show `LISTENING`:

```powershell
& "C:\Program Files\Mosquitto\mosquitto.exe" -v
```

## Terminal 2 — Fog decision receiver

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
python -m mqtt.fog_receiver
```

## Terminal 3 — Edge publisher

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
python -m mqtt.edge_publisher
```

## Terminal 4 — Dashboard

```powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
python -m dashboard.app
```

Open `http://127.0.0.1:5000`. The dashboard shows the latest decision,
decision history, sampling requirement, sample ID, command status, and sample
history in addition to all Phase 3 content.

## Terminal 5 — Simulated sampling receiver

```powershell
python -m mqtt.sampling_receiver
```

For HIGH/CRITICAL transitions, expected flow is:

```text
Edge event -> Fog atomic storage -> decision/sample IDs
           -> marine/<zone>/commands -> simulated receiver
           -> marine/<zone>/command-ack -> sample command status SIMULATED_ACK
```

This receiver only prints and acknowledges the command. It does not control a
pump, collect seawater, detect toxins, or submit a laboratory sample. Sampling
is simulated throughout Phase 4. HIGH/CRITICAL create verification sample
requests only; they do not confirm toxin presence, and accredited laboratory
confirmation is still required.

Manual Phase 4 verification completed with Mosquitto: a controlled HIGH event
created linked decision/sample IDs, Fog published the command, the simulator
returned `SIMULATED_ACK`, and the dashboard plus all three Phase 4 APIs returned
the persisted result successfully.

Phase 4 read-only APIs:

```powershell
$result = Invoke-RestMethod "http://127.0.0.1:5000/api/decision/latest"
$result.decision | Format-List

Invoke-RestMethod "http://127.0.0.1:5000/api/decisions"
Invoke-RestMethod "http://127.0.0.1:5000/api/samples"
```

Database diagnostics:

```powershell
python -m database.diagnostics
```

Optional local configuration:

```powershell
$env:MARINE_SAMPLING_COOLDOWN = "900"
$env:MARINE_SAMPLING_DURATION = "5"
$env:MARINE_SAMPLING_CLIENT_ID = "marine-sampling-simulator-01"
```

Run all automated tests separately:

```powershell
python -m pytest
```

Current verified result: `57 passed` (`11 + 11 + 13 + 22` across Phases 1–4).

## Basic Git commands

```powershell
git status
git add .
git commit -m "Complete Phase 4 decision and automated sampling logic"
git push
```

Never paste a GitHub password, personal access token, or credential into a
tracked project file.

## Risk disclaimer

Limits and risk rules in `config.py` are prototype engineering assumptions.
They require validation with local history and laboratory-confirmed data before
operational or seafood-safety use.
