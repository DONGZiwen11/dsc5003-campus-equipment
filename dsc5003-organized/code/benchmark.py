"""Reproduce the report's file-backed SQLite experiments."""
import csv
import json
import platform
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median, quantiles
from tempfile import TemporaryDirectory
from threading import Barrier
from time import perf_counter_ns

import db
from generate_data import populate

OUT = db.ROOT.parent / "evaluation"
SIZES = (1000, 10000, 50000, 100000)
CASES = (
    ("Overdue loans", db.OVERDUE, ("2026-02-01 00:00:00",), "open_loan_due",
     "CREATE INDEX open_loan_due ON loan(due_at) WHERE returned_at IS NULL"),
    ("Borrower history", """SELECT l.id, l.borrowed_at, l.due_at, l.returned_at, e.id, m.name
     FROM loan l JOIN equipment e ON e.id=l.equipment_id JOIN model m ON m.id=e.model_id
     WHERE l.student_id=? ORDER BY l.borrowed_at DESC, l.id DESC LIMIT 20""",
     ("SYN-0001",), "loan_student_history",
     "CREATE INDEX loan_student_history ON loan(student_id, borrowed_at)"),
)


def record(samples, size, workload, configuration, result_rows):
    quartiles = quantiles(samples, n=4, method="inclusive")
    return dict(loans=size, workload=workload, configuration=configuration,
                result_rows=result_rows, samples=len(samples), median_ms=median(samples),
                q1_ms=quartiles[0], q3_ms=quartiles[2],
                p95_ms=quantiles(samples, n=100, method="inclusive")[94])


def query_test(conn, case, size):
    label, sql, args, index, create = case
    summaries, plans = [], []
    reference = None
    for enabled in (False, True):
        conn.execute(create if enabled else "DROP INDEX " + index)
        conn.execute("ANALYZE")
        conn.commit()
        plan = [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args)]
        durations = []
        for iteration in range(110):
            start = perf_counter_ns()
            rows = conn.execute(sql, args).fetchall()
            elapsed = (perf_counter_ns() - start) / 1e6
            if iteration >= 10:
                durations.append(elapsed)
        identity = sorted(tuple(row) for row in rows)
        if reference is not None and reference != identity:
            raise AssertionError("Index changed query results")
        reference = identity
        config = "With index" if enabled else "Without index"
        summaries.append(record(durations, size, label, config, len(rows)))
        plans.append(dict(loans=size, workload=label, configuration=config, details=plan))
    return summaries, plans


def transaction_test(path, size, workers):
    durations = []
    def checkout(worker, gate):
        with db.connect(path) as connection:
            gate.wait(timeout=15)
            start = perf_counter_ns()
            db.borrow(connection, "SYN-0001", f"BENCH-{worker}", 7)
            connection.commit()
            return (perf_counter_ns() - start) / 1e6

    with ThreadPoolExecutor(workers) as pool, db.connect(path) as cleanup:
        for iteration in range(110 if workers == 1 else 28):
            gate = Barrier(workers)
            jobs = [pool.submit(checkout, i, gate) for i in range(workers)]
            timings = [job.result() for job in jobs]
            count = cleanup.execute("""
                SELECT count(*) FROM audit_log a JOIN loan l ON l.id=a.loan_id
                WHERE l.equipment_id LIKE 'BENCH-%' AND a.action='checkout'
            """).fetchone()[0]
            assert count == workers
            if iteration >= (10 if workers == 1 else 3):
                durations.extend(timings)
            cleanup.execute("DELETE FROM audit_log WHERE loan_id IN (SELECT id FROM loan WHERE equipment_id LIKE 'BENCH-%')")
            cleanup.execute("DELETE FROM loan WHERE equipment_id LIKE 'BENCH-%'")
            cleanup.commit()
    return record(durations, size, "Committed checkout", f"{workers} writer(s)", 1)


def main():
    summaries, plans = [], []
    for size in SIZES:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bench.sqlite3"
            with db.connect(path) as conn:
                db.apply_sql(conn, "schema.sql")
                populate(conn, size - 100)
                conn.execute("DELETE FROM loan WHERE returned_at IS NULL AND CAST(substr(equipment_id,5) AS INTEGER)%10 != 0")
                conn.executemany("INSERT INTO equipment VALUES (?, 1)", [(f"BENCH-{i}",) for i in range(4)])
                assert conn.execute("SELECT count(*) FROM loan").fetchone()[0] == size
                conn.commit()
                journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
                sync = conn.execute("PRAGMA synchronous").fetchone()[0]
                for case in CASES:
                    stats, details = query_test(conn, case, size)
                    summaries.extend(stats)
                    plans.extend(details)
            for workers in (1, 4):
                summaries.append(transaction_test(path, size, workers))
    OUT.mkdir(exist_ok=True)
    with (OUT / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summaries[0].keys())
        writer.writeheader()
        writer.writerows(summaries)
    (OUT / "plans.json").write_text(json.dumps(plans, indent=2), encoding="utf-8")
    (OUT / "environment.json").write_text(json.dumps(dict(platform=platform.platform(),
        processor=platform.processor(), python=platform.python_version(), sqlite=sqlite3.sqlite_version,
        journal_mode=journal, synchronous=sync), indent=2), encoding="utf-8")
    print(f"Saved {len(summaries)} measurements and {len(plans)} plans in {OUT}")


if __name__ == "__main__":
    main()
