"""Parameterized SQLite storage and queries for marine monitoring events."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from config import DATABASE_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    temperature_c REAL,
    ph REAL,
    salinity_psu REAL,
    turbidity_ntu REAL,
    dissolved_oxygen_mg_l REAL,
    sensor_valid INTEGER NOT NULL CHECK (sensor_valid IN (0, 1)),
    validity_score REAL NOT NULL,
    edge_risk_score INTEGER,
    edge_risk_level TEXT NOT NULL,
    received_timestamp TEXT NOT NULL,
    UNIQUE (device_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS idx_sensor_events_received
ON sensor_events(received_timestamp DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_event_id INTEGER NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    FOREIGN KEY (sensor_event_id) REFERENCES sensor_events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alerts_created
ON alerts(created_timestamp DESC);
"""


class MarineDatabase:
    """Small connection-per-operation database layer safe for Flask threads."""

    def __init__(self, path: str | Path = DATABASE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)

    def insert_event(self, message: dict[str, Any]) -> tuple[bool, int | None]:
        """Insert event and its alert atomically; return false for a duplicate."""
        received = datetime.now(timezone.utc).isoformat(timespec="seconds")
        values = (
            message["device_id"], message["zone_id"], message["timestamp"],
            message["sequence_number"], message["temperature_c"], message["ph"],
            message["salinity_psu"], message["turbidity_ntu"],
            message["dissolved_oxygen_mg_l"], int(message["sensor_valid"]),
            message["validity_score"], message["edge_risk_score"],
            message["edge_risk_level"], received,
        )
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO sensor_events (
                    device_id, zone_id, event_timestamp, sequence_number,
                    temperature_c, ph, salinity_psu, turbidity_ntu,
                    dissolved_oxygen_mg_l, sensor_valid, validity_score,
                    edge_risk_score, edge_risk_level, received_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                return False, None
            event_id = int(cursor.lastrowid)
            alert = self._alert_for(message)
            if alert:
                level, text = alert
                connection.execute(
                    """INSERT INTO alerts (
                        sensor_event_id, device_id, zone_id, alert_level,
                        message, created_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (event_id, message["device_id"], message["zone_id"],
                     level, text, received),
                )
            return True, event_id

    @staticmethod
    def _alert_for(message: dict[str, Any]) -> tuple[str, str] | None:
        level = message["edge_risk_level"]
        descriptions = {
            "MEDIUM": "Environmental indicators require increased monitoring.",
            "HIGH": "High environmental risk; sampling verification is required.",
            "CRITICAL": "Critical environmental risk; urgent verification is required.",
            "INVALID": "Sensor validation failed; inspect or recalibrate the sensor.",
        }
        if not message["sensor_valid"]:
            return "INVALID SENSOR", descriptions["INVALID"]
        if level in descriptions:
            return level, descriptions[level]
        return None

    def latest_event(self) -> dict[str, Any] | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM sensor_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._event_dict(row) if row else None

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT * FROM sensor_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._event_dict(row) for row in rows]

    def alerts(self, level: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alerts"
        parameters: list[Any] = []
        if level:
            sql += " WHERE alert_level = ?"
            parameters.append(level)
        sql += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def event_count(self) -> int:
        with closing(self._connect()) as connection, connection:
            return int(connection.execute("SELECT COUNT(*) FROM sensor_events").fetchone()[0])

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["sensor_valid"] = bool(item["sensor_valid"])
        return item
