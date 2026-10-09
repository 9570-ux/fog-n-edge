# AI-Enabled Edge–Fog Early-Warning System for Marine Algal Toxin Risk

Software-only final-year B.Tech project for simulated marine monitoring, Edge validation and risk scoring, MQTT communication, Fog processing, SQLite storage, a Flask dashboard, decision support, and virtual sampling.

> **Scientific limitation:** This software prototype predicts environmental HAB/toxin risk from simulated or dataset-based marine conditions. It does not directly detect marine toxins or certify seafood safety. High-risk results require accredited laboratory confirmation.

No physical sensor, ESP32, probe, pump, relay, camera, or other hardware is required for the completed Phase 1–4 demonstration.

## Contents

- [Problem and objectives](#problem-and-objectives)
- [Project status](#project-status)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Windows installation](#windows-installation)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Phase 1](#phase-1--simulation-validation-and-edge-risk)
- [Phase 2](#phase-2--mqtt-edgefog-communication)
- [Phase 3](#phase-3--database-and-dashboard)
- [Phase 4](#phase-4--decision-and-virtual-sampling)
- [Complete demonstration](#complete-end-to-end-demonstration)
- [API reference](#api-reference)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Research novelty](#research-novelty)

## Problem and objectives

Harmful algal blooms (HABs) can produce toxins that accumulate in seafood. Laboratory testing remains essential, but is not continuous. This project demonstrates an early-warning pipeline that:

- simulates marine environmental readings;
- detects missing, impossible, stuck, and suddenly changing values;
- estimates risk locally at an Edge node;
- transfers events reliably through MQTT;
- queues events during a broker outage and replays them;
- stores readings, alerts, decisions, and virtual samples;
- provides current and historical information through a dashboard;
- recommends monitoring, retesting, maintenance, or sample collection.

## Project status

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Simulation, validation, and Edge risk | **Completed** |
| Phase 2 | MQTT Edge publisher, Fog receiver, ACK, and offline queue | **Completed** |
| Phase 3 | SQLite, alerts, Flask dashboard, APIs, and graphs | **Completed** |
| Phase 4 | Decision engine, cooldown, and virtual sampling | **Completed** |
| Phase 5 | Multi-Zone Digital Twin Simulation | **Pending — Next** |
| Phase 6 | AI Prediction, Uncertainty and Explainability | **Pending** |
| Phase 7 | Adaptive Edge–Fog Task Allocation | **Pending** |
| Phase 8 | Role-Based Dashboard, Evaluation and Final Testing | **Pending** |

Only Phases 1–4 form the completed runtime documented here. Phases 5–8 are future work.

Planned work will add multiple coastal zones, explainable and uncertainty-aware AI, adaptive Edge/Fog/Cloud placement, species-wise recommendations, role-based views, and final evaluation. These are proposals, not current features.

## Architecture

~~~mermaid
flowchart LR
    A[Marine Simulator] --> B[Validation Engine]
    B --> C[Edge Risk Engine]
    C --> D[Edge MQTT Publisher]
    D -->|Sensor event, QoS 1| E[Mosquitto]
    E --> F[Fog Receiver]
    F --> G[(SQLite)]
    F --> H[Decision Engine]
    H --> G
    H --> I[Sampling Manager]
    I -->|Virtual command| E
    E --> J[Software Sampling Receiver]
    J -->|Command ACK| E
    F -->|Event ACK| E
    G --> K[Flask Dashboard and APIs]
    D -. Broker offline .-> L[JSONL Offline Queue]
    L -. Replay .-> D
~~~

The Edge, Fog, dashboard, and sampling receiver are separate software processes. The dashboard reads the same canonical SQLite database written by Fog.

## Prerequisites

Install:

1. [Python for Windows](https://www.python.org/downloads/windows/) — Python 3.10+
2. [Git for Windows](https://git-scm.com/download/win)
3. [Eclipse Mosquitto](https://mosquitto.org/download/) — broker and command-line tools
4. Optional: [Visual Studio Code](https://code.visualstudio.com/download)

### Installation verification

Use the official Windows installers. During Python installation select **Add python.exe to PATH**. Git can use its recommended defaults. Mosquitto may be installed as a Windows service. VS Code is optional; its Microsoft Python extension can select the project virtual environment.

~~~powershell
python --version
python -m pip --version
git --version
& "C:\Program Files\mosquitto\mosquitto.exe" -h
Get-Service mosquitto -ErrorAction SilentlyContinue
netstat -ano | findstr :1883
code --version
~~~

Success means Python 3.10+, pip, and Git print versions; Mosquitto prints help; and a running broker listens on port 1883. If a command is not recognized, reopen PowerShell after installation or add its installation folder to PATH. VS Code and its command are optional.

SQLite needs no separate installation because Python includes it:

~~~powershell
python -c "import sqlite3; print(sqlite3.sqlite_version)"
~~~

Minimal Python packages:

| Package | Purpose |
|---|---|
| paho-mqtt | MQTT communication |
| Flask | Dashboard and REST APIs |
| pytest | Automated tests |

## Windows installation

Clone the repository in PowerShell:

~~~powershell
cd "$HOME\Desktop"
git clone https://github.com/9570-ux/fog-n-edge.git
cd fog-n-edge
~~~

For this existing workspace, the real folder is:

~~~powershell
cd "C:\Users\Manya Kothari\Desktop\fog and edge computin\marine-edge-fog"
~~~

Do not use an invented path such as Manya Kothari remindersbies. PowerShell reports “Cannot find path” if the folder does not exist.

Create the environment and install dependencies:

~~~powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip list
python -m pytest
~~~

If the environment already exists in the parent folder, activate it with:

~~~powershell
..\.venv\Scripts\Activate.ps1
~~~

## Configuration

The defaults support a local demonstration:

| Setting | Default |
|---|---|
| MQTT broker | localhost:1883 |
| MQTT QoS | 1 |
| Edge client ID | marine-edge-coastal-node-01 |
| Fog client ID | marine-fog-node-01 |
| Sampling client ID | marine-sampling-simulator-01 |
| Device / zone | coastal-node-01 / zone-b |
| Publish interval | 3 seconds |
| Database | data/marine_monitoring.db |
| Offline queue | data/offline_queue.jsonl |
| Sampling cooldown | 900 seconds |
| Dashboard | http://127.0.0.1:5000 |

Example session overrides:

~~~powershell
$env:MARINE_MQTT_HOST = "localhost"
$env:MARINE_MQTT_PORT = "1883"
$env:MARINE_DEVICE_ID = "coastal-node-01"
$env:MARINE_ZONE_ID = "zone-b"
~~~

All components must use compatible broker/topic settings. Client IDs must remain unique; duplicate IDs cause Mosquitto to disconnect the older client.

## Project structure

~~~text
marine-edge-fog/
├── app.py                  Interactive Phase 1 demonstration
├── config.py               Shared settings and paths
├── simulator/              Marine data simulation
├── validation/             Data quality checks
├── risk/                   Edge risk calculation
├── edge/publisher.py       MQTT publisher and offline queue
├── fog/receiver.py         Persistence, decisions, commands, ACKs
├── messaging/              Topics and JSON message helpers
├── storage/                SQLite repository and diagnostics
├── decision/               Phase 4 rules
├── sampling/               Manager and software receiver
├── dashboard/              Flask app, templates, and assets
├── tests/                  Automated test suite
└── data/                   Git-ignored runtime database and queue
~~~

Experimental future-phase files, if present in a development checkout, are not required by the completed Phase 1–4 software demonstration.

## Phase 1 — Simulation, validation and Edge risk

Run:

~~~powershell
python app.py
~~~

Choose from the actual interactive menu:

| Choice | Scenario | Expected behavior |
|---:|---|---|
| 1 | Normal | Valid, normally LOW |
| 2 | Medium Risk | MEDIUM |
| 3 | High Risk | HIGH or CRITICAL |
| 4 | Invalid pH | INVALID; prediction blocked |
| 5 | Low Dissolved Oxygen | Increased risk |
| 6 | High Turbidity | Increased risk |
| 7 | Missing Sensor | INVALID; prediction blocked |
| 8 | Stuck Sensor | Fourth repeated reading becomes invalid |
| 9 | Sudden Sensor Change | Excessive change becomes invalid |
| 10 | Automatic Random Simulation | Runs until Ctrl+C |
| 0 | Exit | Stops the program |

Validation checks required fields, numeric types, ranges, rate of change, and stuck values. Errors and significant warnings block prediction.

Risk bands:

- LOW: 0–24
- MEDIUM: 25–49
- HIGH: 50–79
- CRITICAL: 80–100
- INVALID: input quality failed

Important: app.py is a local menu demonstration. It does not send its selected scenario to MQTT. Use the Edge Publisher for the live pipeline.

## Phase 2 — MQTT Edge–Fog communication

### Topics

| Purpose | Topic |
|---|---|
| Sensor event | marine/device-id/sensors |
| Edge risk | marine/device-id/edge-risk |
| Device status/LWT | marine/device-id/status |
| Fog command | marine/device-id/commands |
| Fog event ACK | marine/device-id/ack |
| Sampling command ACK | marine/device-id/command-ack |

Messages use JSON and carry the schema version, device, zone, sequence, readings, validation, and risk data. Sensor publication uses QoS 1.

### Start Mosquitto

If installed as a service:

~~~powershell
Get-Service mosquitto
Start-Service mosquitto
netstat -ano | findstr :1883
~~~

Otherwise run it in its own terminal:

~~~powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -v
~~~

Keep a manually started broker terminal open and stop it with Ctrl+C. Stop the service from an Administrator PowerShell with Stop-Service mosquitto.

### Start Fog and Edge

Fog terminal:

~~~powershell
python -m fog.receiver
~~~

Edge terminal:

~~~powershell
python -m edge.publisher
~~~

Healthy Edge output should remain stable:

~~~text
Connected to MQTT broker (ONLINE)
Published sequence ...
Fog acknowledged sequence ...
Published sequence ...
Fog acknowledged sequence ...
~~~

It should not continuously alternate between broker unavailable and RECONNECTED while Mosquitto is healthy.

### Offline queue

The Edge records outgoing events in data/offline_queue.jsonl. A Fog ACK removes the acknowledged item. During an outage, items remain queued; after reconnection, they replay in sequence. Database uniqueness on device ID and sequence number prevents duplicate records, decisions, and samples.

## Phase 3 — Database and dashboard

The canonical database is data/marine_monitoring.db and is created automatically. Main tables:

| Table | Purpose |
|---|---|
| sensor_events | Readings, validation, risk, timestamps |
| alerts | Medium, high, critical, and invalid alerts |
| decisions | One Phase 4 action per accepted event |
| samples | Traceable virtual samples |

Start the dashboard:

~~~powershell
python -m dashboard.app
~~~

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

It shows current readings and risk, status, latest decision, history, charts, alerts, and samples with automatic refresh. Chart.js is loaded from a CDN; the APIs and numeric dashboard data can still work if that chart resource is unavailable.

Inspect storage:

~~~powershell
python -m storage.diagnostics
~~~

## Phase 4 — Decision and virtual sampling

Fog passes every new non-duplicate stored sensor event to the Decision Engine:

| Event/risk | Action | Sampling |
|---|---|---|
| LOW | MONITOR | No |
| MEDIUM | RETEST | No |
| HIGH | COLLECT_SAMPLE | Yes, subject to cooldown |
| CRITICAL | COLLECT_SAMPLE | Yes, subject to cooldown |
| Invalid | SENSOR_MAINTENANCE | No |

For HIGH or CRITICAL, the Sampling Manager creates a SAMPLE-... record and publishes a command. The receiver below is only a software simulator and controls no physical equipment:

~~~powershell
python -m sampling.receiver
~~~

The cooldown suppresses redundant samples during one continuing hazard. LOW, MEDIUM, or invalid input resets that hazard state. Duplicate MQTT events create no duplicate decision or sample.

## Complete end-to-end demonstration

Activate the virtual environment and enter the repository folder in every terminal.

### Terminal 1 — Mosquitto

~~~powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -v
~~~

If the Mosquitto service is already running, do not start a second broker on port 1883.

### Terminal 2 — Fog Receiver

~~~powershell
python -m fog.receiver
~~~

### Terminal 3 — Edge Publisher

~~~powershell
python -m edge.publisher
~~~

### Terminal 4 — Dashboard

~~~powershell
python -m dashboard.app
~~~

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

### Terminal 5 — Software Sampling Receiver

~~~powershell
python -m sampling.receiver
~~~

### Terminal 6 — Tests and API checks

~~~powershell
python -m pytest
Invoke-RestMethod http://127.0.0.1:5000/api/status
Invoke-RestMethod http://127.0.0.1:5000/api/latest
Invoke-RestMethod http://127.0.0.1:5000/api/decision/latest
~~~

The live Edge Publisher uses weighted random simulation, so its next risk level is not deterministic. Automated tests verify every exact decision mapping.

## API reference

| Method | Endpoint | Result |
|---|---|---|
| GET | /api/status | Database/Fog status and counts |
| GET | /api/latest | Latest sensor event |
| GET | /api/history?limit=20 | History; supported limits: 20, 50, 100 |
| GET | /api/alerts | Alert history |
| GET | /api/alerts?level=HIGH | Alerts filtered by level |
| GET | /api/decision/latest | Latest persisted decision |
| GET | /api/decisions?limit=50 | Decision history |
| GET | /api/samples?limit=100 | Virtual sample history |

Examples:

~~~powershell
Invoke-RestMethod http://127.0.0.1:5000/api/history?limit=20
Invoke-RestMethod http://127.0.0.1:5000/api/alerts
Invoke-RestMethod http://127.0.0.1:5000/api/decisions?limit=50
Invoke-RestMethod http://127.0.0.1:5000/api/samples?limit=100
~~~

If the latest-decision API has no record, ensure Fog has received at least one new, non-duplicate event.

## Testing

Run everything:

~~~powershell
python -m pytest
~~~

Phase 1–4 tests cover scenarios, validation, risk, message schema, client IDs, topics, ACKs, queue replay, SQLite persistence, duplicates, alerts, dashboard APIs, Fog-to-decision integration, action mapping, cooldown, commands, and sample APIs.

Run individual groups:

~~~powershell
python -m pytest tests/test_scenarios.py
python -m pytest tests/test_phase2_mqtt.py
python -m pytest tests/test_phase3_database_dashboard.py
python -m pytest tests/test_phase4_decision_sampling.py
python -m pytest -v
~~~

The exact total can increase as regression tests are added. The authoritative result is the count printed by the current checkout, and completion requires zero failures.

A pass appears as a dot or PASSED. A failure appears as FAILED with a traceback. The suite uses controlled MQTT test doubles and temporary data, so it does not require a live broker and does not reset the historical runtime database.

## Troubleshooting

### Cannot find the project path

~~~powershell
Get-ChildItem "$HOME\Desktop"
Get-ChildItem "C:\Users\Manya Kothari\Desktop\fog and edge computin"
~~~

Copy the exact path and quote it because it contains spaces.

### Script execution is disabled

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
~~~

This changes policy only for the current PowerShell process.

### No module named ...

~~~powershell
python -m pip install -r requirements.txt
Get-Command python
~~~

### MQTT connection refused

- Confirm Mosquitto is running.
- Confirm all processes use localhost:1883.
- Do not start two brokers on port 1883.
- Check Get-Service mosquitto.

### Repeated MQTT reconnects

Edge, Fog, and sampling client IDs must be different. Do not run two copies of the same component with the same client ID.

### No decisions

- Start Fog before Edge.
- Wait for a new sequence; duplicates intentionally create no decision.
- Run python -m storage.diagnostics.
- Confirm Fog and dashboard use the same database.

### Empty dashboard

The dashboard does not generate readings. Start Mosquitto, Fog, and Edge, wait for an ACK, and refresh.

### Port 5000 is busy

Stop the older dashboard with Ctrl+C or inspect it:

~~~powershell
Get-NetTCPConnection -LocalPort 5000
~~~

### Database locked during tests

Stop live Fog/dashboard processes and rerun the tests. Tests should not require the live broker.

## Research novelty

The novelty is the integrated software architecture, not direct toxin identification:

- validation-aware local Edge risk;
- reliable MQTT delivery with ACK, offline queue, and replay;
- duplicate-safe Fog persistence and immediate decisions;
- traceable decision-to-virtual-sample records;
- cooldown-aware sampling to avoid redundant actions;
- transparent recommendations for monitoring, retesting, maintenance, or sampling;
- one historical dashboard for operational review;
- a reproducible software-only prototype without costly marine hardware.

Planned novelty includes multi-zone digital twins, explainable AI, uncertainty-aware decisions, adaptive Edge/Fog/Cloud allocation, species-wise recommendations, and role-based views. These belong to pending phases.

A real deployment would additionally require calibrated instruments, validated toxin-specific models, secure communication, field trials, and accredited laboratory confirmation. This repository does not claim direct toxin detection, certified seafood safety, verified AI accuracy, or patent approval.

## Safe shutdown and local data

Stop long-running processes with Ctrl+C. Suggested order:

1. Edge Publisher
2. Sampling Receiver
3. Fog Receiver
4. Dashboard
5. Mosquitto, only if started manually

Do not delete the data directory if local history or queued events must be preserved. Runtime databases, queues, caches, environments, temporary files, and secrets are excluded by .gitignore and must not be committed.

---

**Repository:** [9570-ux/fog-n-edge](https://github.com/9570-ux/fog-n-edge)
**Completed scope:** Phase 1–4, software only
**Next planned phase:** Phase 5
