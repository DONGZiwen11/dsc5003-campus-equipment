"""Create a reproducible synthetic SQLite workload in a new file."""

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import db


def populate(connection, history, seed=5003):
    rng = random.Random(seed)
    devices = [f"SIM-{i:04d}" for i in range(1000)]
    students = [f"SYN-{i:04d}" for i in range(500)]
    connection.execute("INSERT INTO category VALUES ('Synthetic')")
    connection.execute("INSERT INTO model VALUES (1, 'Synthetic', 'Training Device')")
    connection.executemany("INSERT INTO equipment VALUES (?, 1)", ((item,) for item in devices))
    connection.executemany("INSERT INTO student VALUES (?, ?)", ((key, f"Student {key}") for key in students))
    start = datetime(2025, 1, 1)

    def closed_loans():
        for i in range(history):
            borrowed = start + timedelta(days=3 * (i // len(devices)))
            yield (rng.choice(students), devices[i % len(devices)], db.timestamp(borrowed),
                   db.timestamp(borrowed + timedelta(days=2)),
                   db.timestamp(borrowed + timedelta(days=1)))

    connection.executemany("""
        INSERT INTO loan (student_id,equipment_id,borrowed_at,due_at,returned_at) VALUES (?,?,?,?,?)
    """, closed_loans())
    connection.executemany("""
        INSERT INTO loan (student_id,equipment_id,borrowed_at,due_at) VALUES (?,?,'2026-01-01 00:00:00',?)
    """, ((rng.choice(students), item, "2026-01-10 00:00:00" if i < 100 else "2026-02-10 00:00:00")
          for i, item in enumerate(devices)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("synthetic.sqlite3"))
    parser.add_argument("--loans", type=int, choices=range(10_000, 100_001),
                        metavar="10000..100000", default=100_000, help="Total number of loans")
    parser.add_argument("--seed", type=int, default=5003)
    args = parser.parse_args()
    try:
        args.output.touch(exist_ok=False)
    except FileExistsError:
        parser.error("Output already exists. Choose a new file.")
    with db.connect(args.output) as connection:
        db.apply_sql(connection, "schema.sql")
        populate(connection, args.loans - 1000, args.seed)
        connection.execute("PRAGMA user_version = 4")
    print(f"Created {args.output}: {args.loans:,} loans, 1,000 equipment items, 500 students")


if __name__ == "__main__":
    main()
