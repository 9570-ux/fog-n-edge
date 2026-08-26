"""Read-only local dashboard and JSON API backed by SQLite."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from config import DASHBOARD_HOST, DASHBOARD_PORT, DATABASE_PATH
from database import MarineDatabase

VALID_LIMITS = {20, 50, 100}
VALID_ALERT_LEVELS = {"MEDIUM", "HIGH", "CRITICAL", "INVALID SENSOR"}


def create_app(database_path: str | Path = DATABASE_PATH) -> Flask:
    app = Flask(__name__)
    database = MarineDatabase(database_path)
    app.config["MARINE_DATABASE"] = database

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/latest")
    def api_latest():
        return jsonify({"event": database.latest_event()})

    @app.get("/api/history")
    def api_history():
        limit = request.args.get("limit", default=20, type=int)
        if limit not in VALID_LIMITS:
            limit = 20
        return jsonify({"events": database.history(limit), "limit": limit})

    @app.get("/api/alerts")
    def api_alerts():
        level = request.args.get("level", default="", type=str).upper()
        if level not in VALID_ALERT_LEVELS:
            level = ""
        return jsonify({"alerts": database.alerts(level or None), "level": level or "ALL"})

    @app.get("/api/status")
    def api_status():
        latest = database.latest_event()
        return jsonify({
            "database": "CONNECTED",
            "fog_data_status": "DATA AVAILABLE" if latest else "WAITING",
            "latest_data_timestamp": latest["event_timestamp"] if latest else None,
            "device_id": latest["device_id"] if latest else None,
            "zone_id": latest["zone_id"] if latest else None,
            "total_readings": database.event_count(),
        })

    @app.get("/api/decision/latest")
    def api_latest_decision():
        return jsonify({"decision": database.latest_decision()})

    @app.get("/api/decisions")
    def api_decisions():
        limit = request.args.get("limit", default=50, type=int)
        if limit not in VALID_LIMITS:
            limit = 50
        return jsonify({"decisions": database.decisions(limit), "limit": limit})

    @app.get("/api/samples")
    def api_samples():
        limit = request.args.get("limit", default=100, type=int)
        if limit not in VALID_LIMITS:
            limit = 100
        return jsonify({"samples": database.samples(limit), "limit": limit})

    return app


def main() -> None:
    app = create_app()
    print(f"Dashboard running at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
