"""Central configuration for the marine Edge-Fog prototype."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def project_path(environment_name: str, default: str) -> Path:
    """Return one canonical path, independent of the process working directory."""
    configured = Path(os.getenv(environment_name, default)).expanduser()
    if not configured.is_absolute():
        configured = PROJECT_ROOT / configured
    return configured.resolve()

DEVICE_ID = "coastal-node-01"
ZONE_ID = "zone-b"

SENSOR_FIELDS = {
    "temperature_c": "Water temperature",
    "ph": "pH",
    "salinity_psu": "Salinity",
    "turbidity_ntu": "Turbidity",
    "dissolved_oxygen_mg_l": "Dissolved oxygen",
}

# Broad physical/measurement limits used to reject impossible prototype input.
# These are configurable engineering limits, not regulatory seafood limits.
SENSOR_LIMITS = {
    "temperature_c": {"min": -2.0, "max": 40.0},
    "ph": {"min": 0.0, "max": 14.0},
    "salinity_psu": {"min": 0.0, "max": 50.0},
    "turbidity_ntu": {"min": 0.0, "max": 1000.0},
    "dissolved_oxygen_mg_l": {"min": 0.0, "max": 20.0},
}

# Maximum change allowed between consecutive readings from one device.
MAX_RATE_OF_CHANGE = {
    "temperature_c": 6.0,
    "ph": 1.5,
    "salinity_psu": 8.0,
    "turbidity_ntu": 150.0,
    "dissolved_oxygen_mg_l": 5.0,
}

# A sensor is considered stuck after this many identical consecutive readings.
STUCK_READING_COUNT = 4
FLOAT_EQUALITY_TOLERANCE = 1e-9

# Prototype risk thresholds. These must be reviewed against local historical
# and laboratory-confirmed data before any field or safety use.
RISK_RULES = {
    "temperature": {
        "medium": 29.0,
        "high": 31.0,
        "critical": 34.0,
        "points": (12, 22, 30),
    },
    "ph": {
        "low": 7.7,
        "high": 8.4,
        "severe_low": 7.2,
        "severe_high": 8.8,
        "points": (10, 20),
    },
    "salinity": {
        "low": 30.0,
        "high": 36.0,
        "severe_low": 25.0,
        "severe_high": 40.0,
        "points": (8, 16),
    },
    "turbidity": {
        "medium": 25.0,
        "high": 45.0,
        "critical": 80.0,
        "points": (12, 22, 30),
    },
    "dissolved_oxygen": {
        "medium": 5.0,
        "high": 4.0,
        "critical": 2.5,
        "points": (15, 28, 40),
    },
}

RISK_LEVEL_THRESHOLDS = {
    "LOW": 0,
    "MEDIUM": 25,
    "HIGH": 50,
    "CRITICAL": 80,
}

AUTOMATIC_INTERVAL_SECONDS = 3

# Phase 2 MQTT settings. Environment variables allow local overrides without
# putting credentials or machine-specific settings in Git.
MQTT_BROKER_HOST = os.getenv("MARINE_MQTT_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MARINE_MQTT_PORT", "1883"))
MQTT_KEEPALIVE_SECONDS = int(os.getenv("MARINE_MQTT_KEEPALIVE", "60"))
MQTT_QOS = 1
MQTT_SCHEMA_VERSION = "1.0"
MQTT_TOPIC_ROOT = os.getenv("MARINE_MQTT_TOPIC_ROOT", "marine")
MQTT_RECONNECT_MIN_SECONDS = 1
MQTT_RECONNECT_MAX_SECONDS = 30
EDGE_MQTT_CLIENT_ID = os.getenv(
    "MARINE_EDGE_CLIENT_ID", f"marine-edge-{DEVICE_ID}"
)
FOG_MQTT_CLIENT_ID = os.getenv("MARINE_FOG_CLIENT_ID", "marine-fog-node-01")
EDGE_PUBLISH_INTERVAL_SECONDS = float(os.getenv("MARINE_EDGE_INTERVAL", "3"))
OFFLINE_QUEUE_PATH = Path(
    os.getenv("MARINE_OFFLINE_QUEUE", "data/offline_queue.jsonl")
)

# Phase 3 local persistence and dashboard settings.
DATABASE_PATH = project_path("MARINE_DATABASE_PATH", "data/marine_monitoring.db")
DASHBOARD_HOST = os.getenv("MARINE_DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("MARINE_DASHBOARD_PORT", "5000"))

# Phase 4 simulated decision and sampling settings (no physical actuator).
SAMPLING_COOLDOWN_SECONDS = int(os.getenv("MARINE_SAMPLING_COOLDOWN", "900"))
SAMPLING_COMMAND_DURATION_SECONDS = int(
    os.getenv("MARINE_SAMPLING_DURATION", "5")
)
SAMPLING_RECEIVER_MQTT_CLIENT_ID = os.getenv(
    "MARINE_SAMPLING_CLIENT_ID", "marine-sampling-simulator-01"
)

# Phase 5 virtual planning. Weights are relative and normalized by their sum.
SAMPLING_PLAN_BUDGET = int(os.getenv("MARINE_PLAN_BUDGET", "2"))
SAMPLING_PLAN_STALE_SECONDS = float(os.getenv("MARINE_PLAN_STALE_SECONDS", "900"))
SAMPLING_PLAN_OVERDUE_SECONDS = float(os.getenv("MARINE_PLAN_OVERDUE_SECONDS", "3600"))
SAMPLING_PLAN_WEIGHTS = {
    "risk": float(os.getenv("MARINE_PLAN_WEIGHT_RISK", "0.5")),
    "trend": float(os.getenv("MARINE_PLAN_WEIGHT_TREND", "0.15")),
    "overdue": float(os.getenv("MARINE_PLAN_WEIGHT_OVERDUE", "0.2")),
    "quality_proxy": float(os.getenv("MARINE_PLAN_WEIGHT_QUALITY", "0.15")),
}
