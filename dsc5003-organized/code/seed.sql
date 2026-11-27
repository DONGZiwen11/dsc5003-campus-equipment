INSERT INTO category VALUES ('Photography'), ('Computing'), ('Presentation');
INSERT INTO student VALUES ('S001', 'Alex Chen'), ('S002', 'Jamie Lin'), ('S003', 'Morgan Chow');
INSERT INTO model VALUES
    (1, 'Photography', 'Portable Camera'), (2, 'Photography', 'Tripod'),
    (3, 'Computing', 'Lab Laptop'), (4, 'Presentation', 'Portable Projector');
INSERT INTO equipment VALUES
    ('CAM-01', 1), ('CAM-02', 1), ('TRI-01', 2),
    ('LAP-01', 3), ('LAP-02', 3), ('PRO-01', 4);
INSERT INTO loan (student_id, equipment_id, borrowed_at, due_at, returned_at) VALUES
    ('S001', 'CAM-01', datetime('now', '-7 days'), datetime('now', '-2 days'), NULL),
    ('S002', 'LAP-01', datetime('now', '-1 day'), datetime('now', '+3 days'), NULL),
    ('S003', 'TRI-01', datetime('now', '-9 days'), datetime('now', '-6 days'), datetime('now', '-7 days'));
