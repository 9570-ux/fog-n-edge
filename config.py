"""Configuration for the Phase 1 marine Edge simulation prototype."""

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

