"""Read models shared by the portal and the performance benchmark."""

AVAILABLE = """
SELECT e.id, m.name, m.category
FROM equipment e JOIN model m ON m.id = e.model_id
WHERE (? = '' OR m.category = ?)
  AND NOT EXISTS (SELECT 1 FROM loan l WHERE l.equipment_id = e.id AND l.returned_at IS NULL)
  AND NOT EXISTS (SELECT 1 FROM maintenance_log ml WHERE ml.equipment_id = e.id AND ml.closed_at IS NULL)
ORDER BY m.category, m.name, e.id
"""

OVERDUE = "SELECT id FROM loan WHERE returned_at IS NULL AND due_at < ? ORDER BY due_at"

LOAN_DETAILS = """
SELECT l.id, l.equipment_id, m.name AS model, s.name AS student,
       l.due_at, l.returned_at,
       l.returned_at IS NULL AND l.due_at < datetime('now') AS overdue
FROM loan l
JOIN student s ON s.id = l.student_id
JOIN equipment e ON e.id = l.equipment_id
JOIN model m ON m.id = e.model_id
"""

CATEGORY_UTILIZATION = """
SELECT c.name, COUNT(e.id) AS items, COUNT(l.id) AS on_loan, COUNT(ml.id) AS under_maintenance,
       ROUND(100.0 * COUNT(l.id) / NULLIF(COUNT(e.id), 0), 1) AS utilization
FROM category c
LEFT JOIN model m ON m.category = c.name
LEFT JOIN equipment e ON e.model_id = m.id
LEFT JOIN loan l ON l.equipment_id = e.id AND l.returned_at IS NULL
LEFT JOIN maintenance_log ml ON ml.equipment_id = e.id AND ml.closed_at IS NULL
GROUP BY c.name
ORDER BY c.name
"""

POPULAR_MODELS = """
WITH totals AS (
    SELECT m.category, m.name, COUNT(l.id) AS checkouts
    FROM model m JOIN equipment e ON e.model_id = m.id JOIN loan l ON l.equipment_id = e.id
    WHERE l.borrowed_at >= datetime('now', '-30 days')
    GROUP BY m.id
), ranked AS (
    SELECT *, DENSE_RANK() OVER (PARTITION BY category ORDER BY checkouts DESC) AS popularity
    FROM totals
)
SELECT category, name, checkouts, popularity
FROM ranked WHERE popularity <= 3 ORDER BY category, popularity, name
"""

REPEAT_OVERDUE = """
SELECT s.id, s.name, COUNT(*) AS late_loans
FROM student s JOIN loan l ON l.student_id = s.id
WHERE l.due_at < COALESCE(l.returned_at, datetime('now'))
GROUP BY s.id HAVING COUNT(*) >= 2
ORDER BY late_loans DESC, s.id LIMIT 20
"""

OVERLAP = """
SELECT id FROM loan
WHERE equipment_id = ? AND borrowed_at < ?
  AND (returned_at IS NULL OR returned_at > ?)
LIMIT 1
"""

OPEN_MAINTENANCE = """
SELECT ml.id, ml.equipment_id, m.name, ml.reason, ml.opened_at
FROM maintenance_log ml JOIN equipment e ON e.id = ml.equipment_id
JOIN model m ON m.id = e.model_id WHERE ml.closed_at IS NULL
ORDER BY ml.opened_at, ml.id
"""

RECENT_AUDIT = """
SELECT a.occurred_at, a.action, COALESCE(l.equipment_id, ml.equipment_id) AS equipment_id
FROM audit_log a LEFT JOIN loan l ON l.id = a.loan_id
LEFT JOIN maintenance_log ml ON ml.id = a.maintenance_id
ORDER BY a.id DESC LIMIT 20
"""
