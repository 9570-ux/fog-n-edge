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
| Phase 5 | Adaptive Virtual Sampling | **Completed (software-only)** |
| Phase 6 | AI Prediction, Uncertainty and Explainability | **Pending** |
| Phase 7 | Adaptive Edge–Fog Task Allocation | **Pending** |
| Phase 8 | Role-Based Dashboard, Evaluation and Final Testing | **Pending** |

Phases 1–4 form the completed runtime guide below. Phase 5 is completed for its software-only adaptive virtual sampling scope, documented in the Phase 5 section. Phases 6–8 remain Pending.

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


## Phase 5 — Adaptive, explainable virtual sampling

**Completed (software-only).** Verified adaptive scoring, per-cycle budget limits,
eligibility protection, persisted plans, idempotent retries, validated virtual
lifecycle evidence, and isolated end-to-end simulation. Production planning
remains blocked because 388 legacy sampling requests are unresolved. Live MQTT
delivery, physical water collection, laboratory results, actual HAB detection,
and production readiness are not verified by Phase 5 tests or the isolated demo.
Phases 6, 7, and 8 remain Pending.

The planner in `decision/adaptive_sampling.py` reads the same SQLite sensor
observations, Fog decisions and Phase 4 samples as the existing application.
It ranks zones, reserves up to a per-cycle budget, and persists explanations.
Phase 4 automatic high-risk commands continue to operate independently; this
budget limits Phase 5 plans, not Phase 4 commands or total system sampling.
No new dependencies or hardware commands are introduced.

### Scoring and eligibility

Every zone with at least one stored event is considered. Unknown zones without
observations cannot be discovered. Latest observations use event time in UTC,
with event ID as a timestamp tie-breaker. Future or malformed timestamps are
excluded from current risk and trend; a zone with no usable timestamps remains
eligible for verification. Zones with active Phase 4 requests or virtual
`PLANNED`/`IN_PROGRESS` reservations are excluded. No override is provided.
Legacy samples remain active until explicitly terminal (`COMPLETED`, `CANCELLED`,
or `FAILED`); `SIMULATED_ACK` alone never clears that protection.

All components use 0–100:

- **R (risk):** current validated Edge score, clamped to 0–100. Missing or
  invalid risk contributes zero, with stored `risk_score: null` and level
  `UNKNOWN`; this zero is a scoring convention, not an estimated low risk.
- **T (trend):** positive change from the previous valid, distinct-time
  observation from the same device, clamped to 0–100. Invalid observations
  break the comparison. Insufficient history contributes zero.
- **O (overdue):** `min(100, 100 * elapsed / overdue_seconds)` since the last
  explicitly completed virtual sample. No timestamped completion contributes
  100. Legacy request time and simulated ACK do not count as collection.
- **Q (data-quality uncertainty proxy):** maximum of sensor-invalid/risk-missing
  penalty (100), invalid/missing field fraction * 100, `100 * (1-validity_score)`,
  and `min(100, 100 * observation_age / stale_seconds)`. Invalid timestamps
  contribute 100. Numeric scores and validity are checked for finiteness.

`priority = (wR*R + wT*T + wO*O + wQ*Q) / (wR+wT+wO+wQ)`.
Default weights are 0.50, 0.15, 0.20, 0.15. Q is a data-quality proxy, **not a
HAB probability, predictive confidence interval, or calibrated uncertainty**.
The formula may trade high-risk coverage for verification of unreliable data.
Stale risk remains a historical risk signal alongside an explicit stale-data
reason; it is not a fresh measurement. Trend measures score change, not a
rate or forecast. Weights are engineering choices, not fitted scientific values.

Priority is rounded to six decimals; descending priority then ascending exact
zone ID provides deterministic selection for the same inputs and planning time.
Plan IDs are unique UUIDs, so reproducibility applies to selection and scores,
not newly generated IDs. UTC timestamps include an offset. Legacy naive times
are interpreted as UTC; actual legacy local timezone cannot be inferred.

### Configuration

Set environment variables before starting Python, or pass validated settings
when constructing `AdaptiveSamplingPlanner`:

| Environment variable | Default | Meaning |
|---|---:|---|
| `MARINE_PLAN_BUDGET` | 2 | Maximum zones per cycle; integer >= 0 |
| `MARINE_PLAN_STALE_SECONDS` | 900 | Age at which Q's age component reaches 100 |
| `MARINE_PLAN_OVERDUE_SECONDS` | 3600 | Completed-sample age at which O reaches 100 |
| `MARINE_PLAN_WEIGHT_RISK` | 0.50 | R weight |
| `MARINE_PLAN_WEIGHT_TREND` | 0.15 | T weight |
| `MARINE_PLAN_WEIGHT_OVERDUE` | 0.20 | O weight |
| `MARINE_PLAN_WEIGHT_QUALITY` | 0.15 | Q weight |

Weights must be finite and nonnegative with a positive sum; intervals must be
finite and positive. `MARINE_DATABASE_PATH` retains its existing semantics.
Zero budget and no eligible zones both persist an empty plan. A larger budget
selects only the available eligible zones.

### Planner CLI

Run from the repository directory with its activated environment. The commands
also work with `.\.venv\Scripts\python.exe` in place of `python` on Windows.

```powershell
python -m decision.adaptive_sampling plan --budget 2 --request-id example-new-cycle
python -m decision.adaptive_sampling inspect
python -m decision.adaptive_sampling inspect --plan-id PLAN-<returned-uuid>
python -m decision.adaptive_sampling status PLAN-<returned-uuid> zone-a IN_PROGRESS
python -m decision.adaptive_sampling status PLAN-<returned-uuid> zone-a COMPLETED
python -m decision.adaptive_sampling feedback PLAN-<returned-uuid>
```

To use a separate database, place the global option before the subcommand:
`python -m decision.adaptive_sampling --database data/example.db plan --budget 1`.
Invalid CLI values fail with an error and nonzero exit code. Use the same request
ID to retry: it returns the stored plan and current statuses without reserving
again. Reusing that ID with a different budget/settings/version fails. New
request IDs create new cycles; active reservations still prevent duplication.

Illustrative **synthetic** selected item (risk 60, no prior completion, fresh
valid observation, no trend):

```json
{
  "zone_id": "zone-a",
  "risk_score": 60,
  "risk_level": "HIGH",
  "components": {"risk": 60, "trend": 0, "overdue": 100, "quality_proxy": 0},
  "priority_score": 50,
  "rank": 1,
  "status": "PLANNED",
  "sample_id": null,
  "explanation": "High current environmental risk score. No timestamped completed virtual sample is recorded."
}
```

Actual output also contains plan ID, UTC creation time, budget, algorithm
version, settings, candidate snapshot, supporting evidence, Fog decision when
available, and machine-readable reason codes. `inspect` shows pending and
completed states. `status` explicitly starts/completes/cancels a **virtual**
workflow; completion assigns a `VIRTUAL-` sample identifier and timestamp.
It does not assert physical collection, laboratory verification or seafood
safety. Terminal states cannot be reopened. Repeating the same transition is
idempotent. Cancellation releases the reservation without a valid sample.

### Database migration and MQTT boundary

`MarineDatabase.initialize()` adds only `sampling_plans` and
`sampling_plan_zones`, plus a partial unique index on active virtual zone
reservations. Existing tables/records are preserved; no data reset or historical
backfill occurs. Plan headers store request identity and reproducibility settings;
zone rows store frozen recommendations, rank, lifecycle, and optional virtual
sample ID/completion time. `BEGIN IMMEDIATE` serializes concurrent plan writers.
The original `samples` table requires a unique Phase 4 decision/event, so virtual
plan lifecycle is stored separately rather than manufacturing a Phase 4 decision.

Existing `marine/<zone>/commands`, command format, sampling receiver and
`SIMULATED_ACK` behavior remain unchanged and covered by regression tests.
Phase 5 planning does not publish MQTT commands: a recommendation alone is
not a collection request. The local CLI provides the explicit virtual execution
boundary. Phase 4 activity can arise after a plan; its independent cooldown rules
are preserved. A combined global budget or arbitration across both phases would
require a separately validated change to the Phase 4 workflow.

Feedback returns the first stored observation after plan creation per selected
zone and the observed score change when both risk scores are available. No lab outcome fields or labelled HAB dataset currently exist, so
`laboratory_outcome` is null. This interface supports later evaluation without
inventing labels or implementing automatic retraining. Historical completed
physical samples without a collection timestamp cannot inform elapsed time.

### Tests, diagnostics, and research evaluation

```powershell
python -m pytest -q
python -m database.diagnostics
python -m decision.sampling_evaluation --seed 42 --budget 2 --cycles 12 --output data/phase5_evaluation.json
```

If the Windows system pytest temporary folder is inaccessible, use a **new**
workspace directory: `python -m pytest -q --basetemp=data/phase5-test-run-unique`.
Pytest owns that temporary directory; never point `--basetemp` at `data` itself
or any directory containing records you need. Phase 5 tests use isolated
fixtures; the production database is never used as a test fixture.
Diagnostics includes virtual plan/status counts and SQLite integrity checks.

The evaluation uses eight seeded synthetic zones, twelve cycles ten minutes
apart, separate temporary databases per policy, and the same budget per cycle.
It compares rotating round-robin, risk-only (score then zone ID), and adaptive
ranking. Each policy records explicit synthetic completion history. Cycles
alternate complete, missing and stale observations. Output reports observed
high-risk coverage, number selected, utilization, consecutive-cycle repeats,
pending-zone redundancy, degraded-zone selection/coverage and measured latency.
Undefined coverage is null. Repeats can be justified by persistent risk; they
are not automatically waste. This simulation completes samples immediately,
so pending redundancy is zero by construction; pending safety is tested separately.
Latency includes common candidate scoring/SQLite reads and ranking, excludes
persistence/completion, and is not a production throughput benchmark.

Measured seed-42 run (budget 2, 12 cycles):

| Policy | Observed high-risk coverage | Selected | Budget utilization | Consecutive repeats |
|---|---:|---:|---:|---:|
| Round-robin | 28.6% | 24 | 100% | 0 |
| Risk-only | 67.9% | 24 | 100% | 5 |
| Adaptive | 67.9% | 24 | 100% | 2 |

All policies made zero pending-zone redundant selections in this simulation.
Mean measured selection latency was approximately 6–7 ms on this run; timings
vary by machine. Across the four missing-data cycles, round-robin selected three
degraded zones and both risk-based policies selected zero. Across four stale-data
cycles, the corresponding counts were three, two and three. Quality weighting
therefore does not guarantee selection of missing-data zones under a small budget.
These are reproducible synthetic policy metrics, **not real HAB detection
performance or evidence of scientific superiority**. Change seeds, weights and
budgets to investigate sensitivity before drawing broader conclusions.

Current verification: 151 tests passed (148 existing cases plus three isolated
end-to-end regression cases). Full-history scoring currently loads stored records into
memory; a large deployment would need bounded/indexed history queries and
validated retention rules. No laboratory confirmation, learned uncertainty,
automatic retraining, external devices or physical sample collection is added.

### Troubleshooting: blocked zone with no candidates

An empty plan is expected when every observed zone has an outstanding sample.
The inspected production database contained only `zone-b` (6,708 observations)
and 388 Phase 4 samples for that zone, all `REQUESTED` with `command_status`
`PUBLISHED`, collection `SIMULATED`, and laboratory `NOT_SUBMITTED`. The planner
checks sample **status**, not command acknowledgement or cooldown age. MQTT
acknowledgements update `command_status` only, so old requests still block the
zone. No physical completion or lab outcome can be inferred from them.

Additionally, `cycle-001` is an idempotency key: its stored empty snapshot is
returned on retries. A new request ID recomputes eligibility, but cannot make
an outstanding zone eligible. No eligibility rule or historical request needs
to be changed to test the planner.

Run the safe selection demonstration from the repository:

```powershell
.\.venv\Scripts\python.exe -m decision.sampling_demo
```

This opens only a disposable temporary database populated with explicitly
synthetic events through the existing simulator, validator, risk engine and
Fog decision transaction. Synthetic `zone-b` has a pending Phase 4 request;
synthetic `zone-a` (medium risk) and `zone-c` (low risk) are eligible. Budget 2
selects both, in priority order. Output includes `SYNTHETIC_TEST_FIXTURE`,
`blocked_zones: ["zone-b"]`, two candidates, two selected zones and
`inspection_matches: true`. Selected items stay `PLANNED` with no sample ID or
completion timestamp. The database is discarded when the demo finishes; it is
not available to a later `inspect` command. No production database is opened,
MQTT command is published, collection is asserted, or laboratory result is
created. The regression suite also checks that Phase 4 transport statuses do
not close requests, blocking is zone-specific, and retries of an empty plan
remain stable after new eligible observations arrive.


### ACK identity and read-only integration diagnostics

Phase 4 command states advance monotonically:
`PENDING -> PUBLISHED -> SIMULATED_ACK`. An ACK may arrive before the local
publication update; a later `PUBLISHED` write cannot overwrite it. Repeated
valid ACKs are accepted without rewriting the row. These transport states do
not change sample `status`, `collection_status`, or `laboratory_status`.
`PUBLISHED` means Paho accepted the publish operation, not that the sampling
receiver acknowledged it. `SIMULATED_ACK` confirms only the software response.

The existing MQTT ACK schema remains unchanged. Sample ID uniquely identifies
its command; Fog additionally checks the ACK device ID and incoming
`marine/<zone>/command-ack` topic against the stored sample. Unknown samples,
mismatched devices/topics, unsupported states, empty or non-string identity
fields, and malformed or timezone-less timestamps are rejected. Persistence
failures are logged as failures. The two-argument
`update_sample_command_ack(sample_id, status)` API remains available to trusted
local callers; MQTT handling supplies both device and topic identity.
No new tables or migrations are required for these changes.

```powershell
python -m database.diagnostics
python -m database.diagnostics --json
python -m database.diagnostics --database data/example.db --json
```

Diagnostics now opens SQLite with `mode=ro` and `query_only`, and never
initializes a database or migrates its schema. Missing databases fail without
creating files; databases without Phase 5 tables are reported without adding
them. The report includes sample-status groups, command-status counts,
outstanding requests, per-zone Phase 4 and virtual blockers, currently eligible
zones, and stored plan candidate/selection counts. It distinguishes a zero-budget
selection from an empty candidate snapshot and explains why plan headers with
no zone rows have empty virtual statuses. Current eligibility is evaluated
separately from the frozen snapshot returned for an existing request ID.

These improvements do not close or backfill the 388 existing requests. ACKs
remain transport acknowledgements, and planner eligibility is unchanged.
Isolated integration tests cover duplicates, ACK/publication ordering, concurrent
updates, invalid identities, lifecycle preservation, and diagnostics that leave
database bytes unchanged. They do not use production records or a real broker.


### Evidenced simulated-request lifecycle

New Phase 4 requests now explicitly set `collection_status=SIMULATED_PENDING`.
The original schema default `SIMULATED` is retained for backward compatibility;
existing rows are not rewritten. Legacy `SIMULATED` means **virtual mode with
completion unknown**, not completed collection. The new lifecycle API refuses
start events for those legacy rows, preventing retrospective completion or
backfill of the 388 historical requests.

| Dimension | States | Evidence |
|---|---|---|
| Command transport | PENDING, PUBLISHED, SIMULATED_ACK | Publication/receiver ACK only |
| Virtual collection | SIMULATED_PENDING, SIMULATED_IN_PROGRESS, SIMULATED_COMPLETED | Separate validated simulation events |
| Request | REQUESTED, then COMPLETED | COMPLETED means the virtual task finished |
| Laboratory | NOT_SUBMITTED | Simulation never submits specimens or creates lab results |

A new additive `simulation_events` table stores unique event IDs, sample/device/
zone identity, simulator run ID, event type, UTC start/completion times, an
explicit `is_simulation=true` marker, local recording time, and canonical JSON.
There is one start and one completion per sample. This table is created by the
normal `MarineDatabase.initialize()` path; its migration contains no updates or
backfill. During implementation it was applied **only to disposable test
DBs**, not `data/marine_monitoring.db`. Starting a database-backed application
later would initialize the new table; no such production startup was performed
for this verification.

`record_simulation_event()` is the only new lifecycle transition API. It validates
identity, simulation marker, timezone-aware timestamps, request/start ordering,
and non-future evidence. Completion must match a recorded start's run ID and
start time. Valid events atomically persist evidence and advance collection
state. On completion the request becomes `COMPLETED` and collection becomes
`SIMULATED_COMPLETED`; command and laboratory states are unchanged. Identical
canonical evidence with the same event ID is an idempotent no-op, including a
start retried after completion. Reused IDs with different evidence, a different
ID for an already recorded stage, mismatched identities/runs, missing start,
or incompatible lifecycle states are rejected without partial writes.

The separate MQTT channel is `marine/<zone>/simulation-events`. Existing command
and ACK topics and required schema fields remain unchanged. New commands include
an optional `simulation_lifecycle=true` flag; legacy commands without it are
ACK-only. For opt-in commands, the sampling receiver emits a start event and
runs a timed, interruptible **software task** using `duration_seconds`. Only
when that task finishes does it emit a separate completion event. A shutdown
interrupts the task without asserting completion. Fog validates incoming topic
identity and records events through the database API; the handler publishes no
collection commands. Command ACKs never invoke completion logic.

Duplicate commands in the same receiver process reuse the original run/event
IDs and replay cached evidence without starting another task. Receiver caching
is in memory: a restart cannot resume an interrupted run or recreate its original
evidence IDs. Conflicting replacement evidence is rejected by Fog. There is
no durable receiver outbox, simulation-event application ACK, or automatic
recovery for lost/out-of-order evidence; QoS 1 alone is not a completion guarantee.
Those features would require a separately tested extension. Timestamp validation
assumes synchronized clocks. These events establish virtual execution only,
not physical collection, specimen quality, or independently attested measurements.

Phase 5 eligibility and terminal statuses are unchanged. An evidenced completed
request ceases to block its zone, but another outstanding Phase 4 request or
active virtual reservation still blocks it. The planner's existing completed-
sample age calculation does not yet consume Phase 4 simulation-event timestamps;
releasing a request therefore does not imply a new physical or laboratory sample
nor automatically reset that scoring component.

Read-only diagnostics reports collection-state counts, the number of legacy
unknown-completion rows, recorded evidence counts, and evidenced virtual
completions. It reports an absent evidence table without creating it. The
production database therefore continues to show 388 legacy unknown requests
until a separately authorized historical-resolution policy exists.

The disposable integration tests demonstrate blocking before completion,
ACK/time/new readings not resolving requests, valid completion, another request
keeping the zone blocked, duplicates, identity/run contradictions, missing
start, invalid timestamps/markers, atomic rollback, unchanged legacy rows during
migration, fake-client receiver behavior, shutdown interruption, and a fresh
Phase 5 plan. No real broker or production DB writes are used.

```powershell
python -m pytest -q
python -m database.diagnostics --json
```

Reusing `cycle-001` continues to return the stored empty snapshot. After valid
resolution **in a temporary fixture**, create a fresh plan with a new request ID:

```powershell
python -m decision.adaptive_sampling --database data/lifecycle_test.db plan --budget 2 --request-id lifecycle-test-002
```

The file must already contain the synthetic fixture; creating a new empty DB
alone gives no observed zones. A new request ID does not bypass legacy blocks.
No requests or virtual samples are marked physically collected by this workflow.


### Isolated Phase 5 end-to-end verification

Run from `fog-n-edge`:

```powershell
.\.venv\Scripts\python.exe -m decision.sampling_demo --end-to-end
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase5_end_to_end.py --basetemp=.pytest-e2e-tmp
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
```

The default demo above verifies selection only. The `--end-to-end` mode also
executes two local virtual timer tasks through `IN_PROGRESS` to `COMPLETED`,
inspects their persisted virtual IDs and timestamps, and creates a fresh plan.
It additionally routes JSON commands, ACKs and simulation events through the
actual Fog and sampling receiver callbacks using an in-process queue. There is
no external broker connection. The Phase 5 local task lifecycle and Phase 4
MQTT sample lifecycle have separate identities and tables; this harness tests
both without pretending a virtual plan ID is a Phase 4 command identity.

A new synthetic Phase 4 request stays outstanding after ACK. Its recorded
simulation start and completion events have unique event IDs and matching
sample/device/zone/run identities. Only validated completion releases that
zone. An explicitly labelled legacy fixture remains unchanged and blocked.
The stored empty `synthetic-e2e-empty` plan stays empty on retry; a different
request ID produces the fresh eligible plan. The production `cycle-001`
snapshot is never opened or reused. Fresh production planning requires a new
request ID and legitimate reconciliation of outstanding requests; changing
only the ID does not unblock `zone-b`.

Output is JSON labelled `SYNTHETIC_END_TO_END_SIMULATION`, with `result: PASS`,
individual checks, persisted evidence, lifecycle snapshots and limitations.
Failure raises an error instead of reporting success. The temporary database
is removed on success or failure. The runner accepts no database path and
ignores the configured production database. Seeded selection is reproducible;
UUIDs, timestamps and measured timer durations vary. The next plan is left
`PLANNED` as a distinct future cycle in the disposable database.

This verifies software integration, not real collection, laboratory results,
HAB detection accuracy or a live Mosquitto deployment. Laboratory status stays
`NOT_SUBMITTED`. Production and backup records are untouched, and the 388
legacy requests still require evidence-based reconciliation outside this demo.

**Repository:** [9570-ux/fog-n-edge](https://github.com/9570-ux/fog-n-edge)
**Completed scope:** Phases 1–5, software only
**Next planned phase:** Phase 6 (Pending)
