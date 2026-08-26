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

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT UNIQUE,
    sensor_event_id INTEGER NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    decision_timestamp TEXT NOT NULL,
    risk_score INTEGER,
    risk_level TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    sampling_required INTEGER NOT NULL CHECK (sampling_required IN (0, 1)),
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (sensor_event_id) REFERENCES sensor_events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_decisions_timestamp
ON decisions(decision_timestamp DESC);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id TEXT UNIQUE,
    decision_id TEXT NOT NULL UNIQUE,
    sensor_event_id INTEGER NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    trigger_reason TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    risk_score INTEGER,
    status TEXT NOT NULL DEFAULT 'REQUESTED',
    command_status TEXT NOT NULL DEFAULT 'PENDING',
    collection_status TEXT NOT NULL DEFAULT 'SIMULATED',
    laboratory_status TEXT NOT NULL DEFAULT 'NOT_SUBMITTED',
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id),
    FOREIGN KEY (sensor_event_id) REFERENCES sensor_events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_samples_requested
ON samples(requested_at DESC);
"""


class MarineDatabase:
    """Small connection-per-operation database layer safe for Flask threads."""

    def __init__(self, path: str | Path = DATABASE_PATH) -> None:
        self.path = Path(path).expanduser().resolve()
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
        with closing(self._connect()) as connection, connection:
            event_id = self._insert_event_row(connection, message, received)
            if event_id is None:
                return False, None
            self._insert_alert(connection, event_id, message, received)
            return True, event_id

    def process_event(self, message: dict[str, Any], decision_engine: Any,
                      sampling_manager: Any) -> dict[str, Any]:
        """Atomically persist a new event, decision, and optional sample."""
        now = datetime.now(timezone.utc)
        created = now.isoformat(timespec="seconds")
        draft = decision_engine.decide(message)
        with closing(self._connect()) as connection, connection:
            previous = connection.execute(
                """SELECT risk_level FROM decisions
                   WHERE device_id = ? AND zone_id = ? ORDER BY id DESC LIMIT 1""",
                (message["device_id"], message["zone_id"]),
            ).fetchone()
            event_id = self._insert_event_row(connection, message, created)
            if event_id is None:
                existing = self._existing_processing_result(connection, message)
                return {"inserted": False, **existing}
            self._insert_alert(connection, event_id, message, created)

            cursor = connection.execute(
                """INSERT INTO decisions (
                    sensor_event_id, device_id, zone_id, decision_timestamp,
                    risk_score, risk_level, action, reason, sampling_required,
                    priority, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, draft["device_id"], draft["zone_id"], created,
                 draft["risk_score"], draft["risk_level"], draft["action"],
                 draft["reason"], int(draft["sampling_required"]),
                 draft["priority"], draft["status"]),
            )
            decision_row_id = int(cursor.lastrowid)
            decision_id = f"DEC-{now.year}-{decision_row_id:06d}"
            connection.execute(
                "UPDATE decisions SET decision_id = ? WHERE id = ?",
                (decision_id, decision_row_id),
            )
            decision = {**draft, "decision_id": decision_id,
                        "sensor_event_id": event_id, "decision_timestamp": created}

            sample = None
            command = None
            if draft["sampling_required"]:
                last_sample = connection.execute(
                    """SELECT requested_at FROM samples
                       WHERE device_id = ? AND zone_id = ?
                       ORDER BY id DESC LIMIT 1""",
                    (message["device_id"], message["zone_id"]),
                ).fetchone()
                allowed, trigger = sampling_manager.should_request(
                    draft["risk_level"], previous["risk_level"] if previous else None,
                    last_sample["requested_at"] if last_sample else None, now,
                )
                if allowed:
                    sample_cursor = connection.execute(
                        """INSERT INTO samples (
                            decision_id, sensor_event_id, device_id, zone_id,
                            requested_at, trigger_reason, risk_level, risk_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (decision_id, event_id, message["device_id"], message["zone_id"],
                         created, trigger, draft["risk_level"], draft["risk_score"]),
                    )
                    sample_row_id = int(sample_cursor.lastrowid)
                    sample_id = f"SAMPLE-{now.year}-{sample_row_id:06d}"
                    connection.execute(
                        "UPDATE samples SET sample_id = ? WHERE id = ?",
                        (sample_id, sample_row_id),
                    )
                    sample = self._sample_by_id(connection, sample_id)
                    command = sampling_manager.build_command(sample)
                    connection.execute(
                        "UPDATE decisions SET status = 'SAMPLE_REQUESTED' WHERE id = ?",
                        (decision_row_id,),
                    )
                    decision["status"] = "SAMPLE_REQUESTED"
                else:
                    connection.execute(
                        "UPDATE decisions SET status = ? WHERE id = ?",
                        (f"SAMPLE_SUPPRESSED_{trigger}", decision_row_id),
                    )
                    decision["status"] = f"SAMPLE_SUPPRESSED_{trigger}"
            return {"inserted": True, "event_id": event_id,
                    "decision": decision, "sample": sample, "command": command}

    @staticmethod
    def _insert_event_row(connection: sqlite3.Connection, message: dict[str, Any],
                          received: str) -> int | None:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO sensor_events (
                device_id, zone_id, event_timestamp, sequence_number,
                temperature_c, ph, salinity_psu, turbidity_ntu,
                dissolved_oxygen_mg_l, sensor_valid, validity_score,
                edge_risk_score, edge_risk_level, received_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (message["device_id"], message["zone_id"], message["timestamp"],
             message["sequence_number"], message["temperature_c"], message["ph"],
             message["salinity_psu"], message["turbidity_ntu"],
             message["dissolved_oxygen_mg_l"], int(message["sensor_valid"]),
             message["validity_score"], message["edge_risk_score"],
             message["edge_risk_level"], received),
        )
        return int(cursor.lastrowid) if cursor.rowcount else None

    def _insert_alert(self, connection: sqlite3.Connection, event_id: int,
                      message: dict[str, Any], created: str) -> None:
        alert = self._alert_for(message)
        if alert:
            connection.execute(
                """INSERT OR IGNORE INTO alerts (
                    sensor_event_id, device_id, zone_id, alert_level,
                    message, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (event_id, message["device_id"], message["zone_id"],
                 alert[0], alert[1], created),
            )

    def _existing_processing_result(self, connection: sqlite3.Connection,
                                    message: dict[str, Any]) -> dict[str, Any]:
        row = connection.execute(
            """SELECT id FROM sensor_events
               WHERE device_id = ? AND sequence_number = ?""",
            (message["device_id"], message["sequence_number"]),
        ).fetchone()
        if not row:
            return {"event_id": None, "decision": None, "sample": None, "command": None}
        decision_row = connection.execute(
            "SELECT * FROM decisions WHERE sensor_event_id = ?", (row["id"],)
        ).fetchone()
        sample_row = connection.execute(
            "SELECT * FROM samples WHERE sensor_event_id = ?", (row["id"],)
        ).fetchone()
        return {"event_id": row["id"],
                "decision": self._decision_dict(decision_row) if decision_row else None,
                "sample": dict(sample_row) if sample_row else None, "command": None}

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

    def decision_count(self) -> int:
        with closing(self._connect()) as connection, connection:
            return int(connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])

    def sample_count(self) -> int:
        with closing(self._connect()) as connection, connection:
            return int(connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0])

    def latest_decision(self) -> dict[str, Any] | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """SELECT d.*, s.sample_id, s.command_status,
                          s.collection_status, s.laboratory_status
                   FROM decisions d
                   LEFT JOIN samples s ON s.decision_id = d.decision_id
                   ORDER BY d.id DESC LIMIT 1"""
            ).fetchone()
        return self._decision_dict(row) if row else None

    def decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """SELECT d.*, s.sample_id, s.command_status
                   FROM decisions d
                   LEFT JOIN samples s ON s.decision_id = d.decision_id
                   ORDER BY d.id DESC LIMIT ?""", (limit,),
            ).fetchall()
        return [self._decision_dict(row) for row in rows]

    def samples(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT * FROM samples ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_sample_command_ack(self, sample_id: str, status: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "UPDATE samples SET command_status = ? WHERE sample_id = ?",
                (status, sample_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _sample_by_id(connection: sqlite3.Connection,
                      sample_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM samples WHERE sample_id = ?", (sample_id,)
        ).fetchone()
        return dict(row)

    @staticmethod
    def _decision_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["sampling_required"] = bool(item["sampling_required"])
        return item

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["sensor_valid"] = bool(item["sensor_valid"])
        return item
