import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from tempfile import TemporaryDirectory
from pathlib import Path
import db

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        db.initialize(self.path)

    def run_op(self, fn, *args):
        with db.connect(self.path) as c:
            return fn(c, *args)

    def test_checkout_audit(self):
        self.run_op(db.borrow, 'S001', 'CAM-02', 7)
        with db.connect(self.path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM audit_log a JOIN loan l ON a.loan_id=l.id WHERE l.equipment_id='CAM-02' AND a.action='checkout'").fetchone()[0], 1)

    def test_duplicate_checkout(self):
        with self.assertRaises(ValueError): self.run_op(db.borrow, 'S001', 'CAM-01', 7)

    def test_direct_duplicate(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(self.path) as c:
                c.execute("INSERT INTO loan(student_id,equipment_id,borrowed_at,due_at) VALUES ('S001','CAM-01','2026-01-01','2026-01-02')")

    def test_concurrent_same_item(self):
        gate = Barrier(2)
        def attempt(student):
            gate.wait(timeout=5)
            try:
                self.run_op(db.borrow, student, 'CAM-02', 7)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(attempt, ['S001','S002'])), 1)

    def test_checkout_during_maintenance(self):
        self.run_op(db.open_maintenance, 'CAM-02', 'Repair')
        with self.assertRaises(ValueError): self.run_op(db.borrow, 'S001','CAM-02',7)
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(self.path) as c:
                c.execute("INSERT INTO loan(student_id,equipment_id,borrowed_at,due_at) VALUES ('S001','CAM-02','2026-01-01','2026-01-02')")

    def test_maintenance_during_loan(self):
        with self.assertRaises(ValueError): self.run_op(db.open_maintenance,'CAM-01','Repair')
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(self.path) as c:
                c.execute("INSERT INTO maintenance_log(equipment_id,reason,opened_at) VALUES ('CAM-01','Repair','2026-01-01')")

    def test_direct_updates(self):
        self.run_op(db.open_maintenance,'CAM-02','Repair')
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(self.path) as c: c.execute("UPDATE loan SET equipment_id='CAM-02' WHERE equipment_id='CAM-01'")
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(self.path) as c: c.execute("UPDATE maintenance_log SET equipment_id='CAM-01' WHERE equipment_id='CAM-02'")

    def test_invalid_student(self):
        with self.assertRaises(ValueError): self.run_op(db.borrow,'INVALID','CAM-02',7)

    def test_invalid_duration(self):
        with self.assertRaises(ValueError): self.run_op(db.borrow,'S001','CAM-02',31)

    def test_duplicate_return(self):
        self.run_op(db.return_equipment,1)
        with self.assertRaises(ValueError): self.run_op(db.return_equipment,1)

    def test_audit_failure_rolls_back(self):
        with db.connect(self.path) as c:
            c.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.run_op(db.borrow,'S001','CAM-02',7)
        with db.connect(self.path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM loan WHERE equipment_id='CAM-02'").fetchone()[0],0)

    def test_v3_migration(self):
        with db.connect(self.path) as c:
            before = [tuple(r) for r in c.execute('SELECT * FROM loan ORDER BY id')]
            for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall(): c.execute('DROP TRIGGER '+r[0])
            c.execute('PRAGMA user_version=3')
        db.initialize(self.path)
        with db.connect(self.path) as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM loan ORDER BY id')],before)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertEqual(c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],4)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

if __name__ == '__main__': unittest.main(verbosity=2)
