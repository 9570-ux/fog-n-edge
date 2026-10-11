"""Read-only SQLite diagnostics; never initializes schemas or modifies records."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any

from config import DATABASE_PATH
from decision.adaptive_sampling import ACTIVE_STATUSES, TERMINAL_SAMPLE_STATUSES


def inspect_database(path: str | Path = DATABASE_PATH) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    # mode=ro fails for missing databases rather than creating one.
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(row) for row in connection.execute(sql)]
        counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("sensor_events", "decisions", "samples")}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        sample_groups = rows("""SELECT zone_id, status, command_status, collection_status,
                               laboratory_status, COUNT(*) AS count FROM samples
                               GROUP BY zone_id, status, command_status, collection_status, laboratory_status
                               ORDER BY zone_id, status, command_status""")
        command_counts = rows("SELECT command_status, COUNT(*) AS count FROM samples GROUP BY command_status ORDER BY command_status")
        outstanding = [row for row in sample_groups if row["status"] not in TERMINAL_SAMPLE_STATUSES]
        observed = {row[0] for row in connection.execute("SELECT DISTINCT zone_id FROM sensor_events")}
        virtual_groups = rows("SELECT zone_id, status, COUNT(*) AS count FROM sampling_plan_zones GROUP BY zone_id, status ORDER BY zone_id, status") if 'sampling_plan_zones' in tables else []
        virtual_statuses = rows("SELECT status, COUNT(*) AS count FROM sampling_plan_zones GROUP BY status ORDER BY status") if 'sampling_plan_zones' in tables else []
        blocking = []
        for zone in sorted(observed):
            legacy_count = sum(row['count'] for row in outstanding if row['zone_id'] == zone)
            virtual_count = sum(row['count'] for row in virtual_groups if row['zone_id'] == zone and row['status'] in ACTIVE_STATUSES)
            if legacy_count or virtual_count:
                blocking.append({"zone_id": zone, "outstanding_phase4_requests": legacy_count,
                                 "active_virtual_reservations": virtual_count})
        blocked = [row['zone_id'] for row in blocking]
        eligibility_reason = "NO_OBSERVED_ZONES" if not observed else "ALL_OBSERVED_ZONES_BLOCKED" if len(blocked) == len(observed) else "ELIGIBLE_ZONES_AVAILABLE"
        plans = []
        if 'sampling_plans' in tables:
            for row in rows("SELECT plan_id, request_id, created_at, budget, snapshot_json FROM sampling_plans ORDER BY created_at, plan_id"):
                snapshot = json.loads(row.pop('snapshot_json'))
                candidates = snapshot.get('candidates', [])
                snapshot_blocked = snapshot.get('blocked_zones', [])
                selected = connection.execute("SELECT COUNT(*) FROM sampling_plan_zones WHERE plan_id = ?", (row['plan_id'],)).fetchone()[0] if 'sampling_plan_zones' in tables else 0
                row.update(candidate_count=len(candidates), selected_count=selected, blocked_zones=snapshot_blocked,
                           no_candidates_reason=("STORED_SNAPSHOT_HAS_ONLY_BLOCKED_ZONES" if snapshot_blocked else "STORED_SNAPSHOT_HAS_NO_OBSERVED_ZONES") if not candidates else None,
                           empty_selection_reason="NO_CANDIDATES" if not candidates else "ZERO_BUDGET" if row['budget'] == 0 else None,
                           retry_behavior="Same request ID returns this stored snapshot; it does not recompute eligibility.")
                plans.append(row)
        lifecycle_counts = rows("SELECT collection_status, COUNT(*) AS count FROM samples GROUP BY collection_status ORDER BY collection_status")
        legacy_unknown = connection.execute("SELECT COUNT(*) FROM samples WHERE collection_status = 'SIMULATED'").fetchone()[0]
        evidence_counts = rows("SELECT event_type, COUNT(*) AS count FROM simulation_events GROUP BY event_type ORDER BY event_type") if 'simulation_events' in tables else []
        evidenced_completions = connection.execute("""SELECT COUNT(*) FROM samples s
            JOIN simulation_events e ON s.sample_id = e.sample_id
            WHERE e.event_type = 'SIMULATION_COMPLETED' AND e.is_simulation = 1
              AND s.status = 'COMPLETED' AND s.collection_status = 'SIMULATED_COMPLETED'""").fetchone()[0] if 'simulation_events' in tables else 0
        latest = rows("SELECT * FROM decisions ORDER BY id DESC LIMIT 1")
        return {"database_path": str(path), "counts": counts,
                "sample_status_counts": sample_groups, "command_status_counts": command_counts,
                "simulated_lifecycle_counts": lifecycle_counts,
                "legacy_simulation_completion_unknown": legacy_unknown,
                "simulation_evidence_schema_available": 'simulation_events' in tables,
                "simulation_evidence_counts": evidence_counts,
                "evidenced_virtual_completions": evidenced_completions,
                "outstanding_sample_requests": sum(row['count'] for row in outstanding),
                "outstanding_request_groups": outstanding, "observed_zones": sorted(observed),
                "blocked_zones": blocked, "blocking_details": blocking,
                "eligible_zones": sorted(observed - set(blocked)), "current_eligibility_reason": eligibility_reason,
                "virtual_plans": len(plans), "virtual_statuses": virtual_statuses,
                "virtual_statuses_explanation": "No selected virtual zone rows exist; plan headers alone have no zone lifecycle status." if not virtual_groups else None,
                "plans": plans, "phase5_schema_available": {'sampling_plans', 'sampling_plan_zones'} <= tables,
                "latest_decision": latest[0] if latest else None,
                "integrity": connection.execute('PRAGMA integrity_check').fetchone()[0],
                "foreign_key_errors": len(connection.execute('PRAGMA foreign_key_check').fetchall())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=str(DATABASE_PATH))
    parser.add_argument('--json', action='store_true', help='Print the complete machine-readable report')
    args = parser.parse_args()
    try:
        report = inspect_database(args.database)
    except (sqlite3.Error, OSError, ValueError) as exc:
        parser.exit(1, f'Database diagnostics failed: {exc}\n')
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"Active SQLite path : {report['database_path']}")
    print(f"Sensor events      : {report['counts']['sensor_events']}")
    print(f"Decisions          : {report['counts']['decisions']}")
    print(f"Samples            : {report['counts']['samples']}")
    print(f"Outstanding requests: {report['outstanding_sample_requests']}")
    print(f"Sample status counts: {report['sample_status_counts']}")
    print(f"Command statuses   : {report['command_status_counts']}")
    print(f"Simulation states  : {report['simulated_lifecycle_counts']}")
    print(f"Legacy completion unknown: {report['legacy_simulation_completion_unknown']}")
    print(f"Simulation evidence: {report['simulation_evidence_counts']}")
    print(f"Evidenced virtual completions: {report['evidenced_virtual_completions']}")
    if not report['simulation_evidence_schema_available']:
        print('Simulation evidence schema is absent; read-only diagnostics did not migrate it.')
    print(f"Blocked zones      : {report['blocking_details']}")
    print(f"Current eligibility: {report['current_eligibility_reason']}")
    print(f"Virtual plans      : {report['virtual_plans']}")
    print(f"Virtual statuses   : {report['virtual_statuses']}")
    if report['virtual_statuses_explanation']:
        print(f"Explanation        : {report['virtual_statuses_explanation']}")
    if not report['phase5_schema_available']:
        print('Phase 5 schema is absent; diagnostics did not create or migrate it.')
    for plan in report['plans']:
        print(f"Plan diagnostic    : {plan}")
    print(f"SQLite integrity   : {report['integrity']}")
    print(f"Foreign key errors : {report['foreign_key_errors']}")
    print(f"Latest decision    : {report['latest_decision']}")


if __name__ == '__main__':
    main()
