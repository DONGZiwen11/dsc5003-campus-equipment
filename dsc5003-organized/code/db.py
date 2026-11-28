import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from queries import AVAILABLE, OVERDUE, OVERLAP

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "equipment.sqlite3"


@contextmanager
def connect(path=DATABASE):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def apply_sql(connection, filename):
    statement = ""
    for line in (ROOT / filename).read_text(encoding="utf-8").splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""


def initialize(path=DATABASE):
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 4:
            return
        if version == 3:
            if connection.execute("SELECT 1 FROM loan l JOIN maintenance_log m ON l.equipment_id=m.equipment_id WHERE l.returned_at IS NULL AND m.closed_at IS NULL").fetchone():
                raise ValueError("Resolve conflicting open loan and maintenance records before upgrading.")
            apply_sql(connection, "schema.sql")
            connection.execute("PRAGMA user_version = 4")
            return
        if version not in (0, 1, 2):
            raise ValueError(f"Unsupported database version: {version}")
        if version in (1, 2):
            if version == 1:
                apply_sql(connection, "translate_seed.sql")
            for table in ("loan", "equipment", "model", "student"):
                connection.execute(f"ALTER TABLE {table} RENAME TO legacy_{table}")
        apply_sql(connection, "schema.sql")
        if version == 0:
            apply_sql(connection, "seed.sql")
        else:
            connection.execute("INSERT INTO category SELECT DISTINCT category FROM legacy_model")
            for table in ("student", "model", "equipment", "loan"):
                connection.execute(f"INSERT INTO {table} SELECT * FROM legacy_{table}")
            for table in ("loan", "equipment", "model", "student"):
                connection.execute(f"DROP TABLE legacy_{table}")
            # Legacy indexes kept their names until the old tables were dropped.
            apply_sql(connection, "schema.sql")
        connection.execute("PRAGMA user_version = 4")


def timestamp(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def borrow(db, student, equipment, days):
    if not 1 <= days <= 30:
        raise ValueError("Enter a loan duration between 1 and 30 days.")
    db.execute("BEGIN IMMEDIATE")
    now = datetime.now(timezone.utc)
    start = timestamp(now)
    due = timestamp(now + timedelta(days=days))
    if db.execute(
        "SELECT 1 FROM maintenance_log WHERE equipment_id = ? AND closed_at IS NULL", (equipment,)
    ).fetchone():
        raise ValueError("This equipment is under maintenance.")
    if db.execute(OVERLAP, (equipment, due, start)).fetchone():
        raise ValueError("This equipment already has an overlapping loan.")
    try:
        loan = db.execute(
            "INSERT INTO loan (student_id, equipment_id, borrowed_at, due_at) VALUES (?, ?, ?, ?)",
            (student, equipment, start, due),
        )
    except sqlite3.IntegrityError as exc:
        messages = {
            "SQLITE_CONSTRAINT_UNIQUE": "This equipment is already on loan. Refresh and select another item.",
            "SQLITE_CONSTRAINT_FOREIGNKEY": "The borrower or equipment could not be found.",
        }
        if exc.sqlite_errorname in messages:
            raise ValueError(messages[exc.sqlite_errorname]) from exc
        raise

    db.execute("INSERT INTO audit_log (loan_id, action) VALUES (?, 'checkout')", (loan.lastrowid,))


def return_equipment(db, loan_id):
    db.execute("BEGIN IMMEDIATE")
    result = db.execute(
        "UPDATE loan SET returned_at = datetime('now') WHERE id = ? AND returned_at IS NULL",
        (loan_id,),
    )
    if result.rowcount == 0:
        raise ValueError("This loan could not be found or has already been returned.")
    db.execute("INSERT INTO audit_log (loan_id, action) VALUES (?, 'checkin')", (loan_id,))


def open_maintenance(connection, equipment_id, reason):
    reason = reason.strip()
    if not 1 <= len(reason) <= 240:
        raise ValueError("Enter a maintenance reason of 1–240 characters.")
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute(
        "SELECT id FROM loan WHERE equipment_id = ? AND returned_at IS NULL", (equipment_id,)
    ).fetchone():
        raise ValueError("Check the item in before opening maintenance.")
    if not connection.execute("SELECT id FROM equipment WHERE id = ?", (equipment_id,)).fetchone():
        raise ValueError("Equipment could not be found.")
    if connection.execute(
        "SELECT id FROM maintenance_log WHERE equipment_id = ? AND closed_at IS NULL", (equipment_id,)
    ).fetchone():
        raise ValueError("Maintenance is already open for this item.")
    maintenance = connection.execute(
        "INSERT INTO maintenance_log (equipment_id, reason, opened_at) VALUES (?, ?, datetime('now'))",
        (equipment_id, reason),
    )
    connection.execute(
        "INSERT INTO audit_log (maintenance_id, action) VALUES (?, 'maintenance_open')",
        (maintenance.lastrowid,),
    )


def close_maintenance(connection, maintenance_id):
    connection.execute("BEGIN IMMEDIATE")
    result = connection.execute(
        "UPDATE maintenance_log SET closed_at = datetime('now') WHERE id = ? AND closed_at IS NULL",
        (maintenance_id,),
    )
    if result.rowcount != 1:
        raise ValueError("This maintenance record is already closed or does not exist.")
    connection.execute(
        "INSERT INTO audit_log (maintenance_id, action) VALUES (?, 'maintenance_close')",
        (maintenance_id,),
    )
