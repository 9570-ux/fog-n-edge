"""Print the active Phase 4 SQLite location and record counts."""

from database import MarineDatabase


def main() -> None:
    database = MarineDatabase()
    print(f"Active SQLite path : {database.path}")
    print(f"Sensor events      : {database.event_count()}")
    print(f"Decisions          : {database.decision_count()}")
    print(f"Samples            : {database.sample_count()}")
    print(f"Latest decision    : {database.latest_decision()}")


if __name__ == "__main__":
    main()
