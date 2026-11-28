CREATE TABLE IF NOT EXISTS category (
    name TEXT PRIMARY KEY NOT NULL CHECK (length(trim(name)) > 0)
);
CREATE TABLE IF NOT EXISTS student (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0)
);
CREATE TABLE IF NOT EXISTS model (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL REFERENCES category(name) ON UPDATE CASCADE ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    UNIQUE (category, name)
);
CREATE TABLE IF NOT EXISTS equipment (
    id TEXT PRIMARY KEY NOT NULL,
    model_id INTEGER NOT NULL REFERENCES model(id) ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS loan (
    id INTEGER PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES student(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    equipment_id TEXT NOT NULL REFERENCES equipment(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    borrowed_at TEXT NOT NULL,
    due_at TEXT NOT NULL CHECK (due_at > borrowed_at),
    returned_at TEXT CHECK (returned_at >= borrowed_at)
);
CREATE TABLE IF NOT EXISTS maintenance_log (
    id INTEGER PRIMARY KEY,
    equipment_id TEXT NOT NULL REFERENCES equipment(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 240),
    opened_at TEXT NOT NULL,
    closed_at TEXT CHECK (closed_at >= opened_at)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    loan_id INTEGER REFERENCES loan(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    maintenance_id INTEGER REFERENCES maintenance_log(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    action TEXT NOT NULL,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (loan_id IS NOT NULL AND maintenance_id IS NULL AND action IN ('checkout','checkin'))
        OR (loan_id IS NULL AND maintenance_id IS NOT NULL AND action IN ('maintenance_open','maintenance_close'))
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_loan ON loan(equipment_id) WHERE returned_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS one_open_maintenance ON maintenance_log(equipment_id) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS open_loan_due ON loan(due_at) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS loan_equipment_history ON loan(equipment_id, borrowed_at);
CREATE INDEX IF NOT EXISTS loan_student_history ON loan(student_id, borrowed_at);
CREATE INDEX IF NOT EXISTS equipment_by_model ON equipment(model_id, id);

-- Open loans and open maintenance must be mutually exclusive, even for direct SQL.
CREATE TRIGGER IF NOT EXISTS loan_no_maintenance_insert BEFORE INSERT ON loan
WHEN NEW.returned_at IS NULL AND EXISTS (SELECT 1 FROM maintenance_log WHERE equipment_id=NEW.equipment_id AND closed_at IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'Equipment is under maintenance');
END;
CREATE TRIGGER IF NOT EXISTS loan_no_maintenance_update BEFORE UPDATE OF equipment_id, returned_at ON loan
WHEN NEW.returned_at IS NULL AND EXISTS (SELECT 1 FROM maintenance_log WHERE equipment_id=NEW.equipment_id AND closed_at IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'Equipment is under maintenance');
END;
CREATE TRIGGER IF NOT EXISTS maintenance_no_loan_insert BEFORE INSERT ON maintenance_log
WHEN NEW.closed_at IS NULL AND EXISTS (SELECT 1 FROM loan WHERE equipment_id=NEW.equipment_id AND returned_at IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'Equipment is on loan');
END;
CREATE TRIGGER IF NOT EXISTS maintenance_no_loan_update BEFORE UPDATE OF equipment_id, closed_at ON maintenance_log
WHEN NEW.closed_at IS NULL AND EXISTS (SELECT 1 FROM loan WHERE equipment_id=NEW.equipment_id AND returned_at IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'Equipment is on loan');
END;
