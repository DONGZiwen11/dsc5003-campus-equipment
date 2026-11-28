import argparse
import sqlite3
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import db
import queries


def options(rows, selected=""):
    return "".join(
        '<option value="{}"{}>{}</option>'.format(
            escape(str(key)), " selected" if key == selected else "", escape(label)
        )
        for key, label in rows
    )



def report_table(title, headers, rows):
    headings = "".join(f"<th scope='col'>{escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(value)) if value is not None else '—'}</td>" for value in row) + "</tr>"
        for row in rows
    )
    if not body:
        body = f"<tr><td colspan='{len(headers)}'>No records</td></tr>"
    return f"<section><h2>{title}</h2><div class='table-wrap'><table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div></section>"


def operations(connection, equipment):
    device_options = options([(r["id"], f'{r["name"]} · {r["id"]}') for r in equipment])
    disabled = "" if equipment else " disabled"
    active = "".join(
        f'<li><div><strong>{escape(row["equipment_id"])}</strong> · {escape(row["reason"])}</div>'
        f'<form method="post" action="/maintenance/close"><input type="hidden" name="maintenance" value="{row["id"]}">'
        '<button class="secondary">Close</button></form></li>'
        for row in connection.execute(queries.OPEN_MAINTENANCE)
    ) or "<li>No active maintenance records.</li>"
    maintenance = f"""<section id="maintenance"><h2>Equipment maintenance</h2>
<form method="post" action="/maintenance/open" class="stack">
<label>Equipment <select name="equipment" required{disabled}>{device_options}</select></label>
<label>Reason <input name="reason" maxlength="240" required></label>
<button{disabled}>Open maintenance</button>
</form><ul>{active}</ul></section>"""
    reports = (
        ("Capacity by category", ("Category", "Items", "On loan", "Maintenance", "On loan (%)"), queries.CATEGORY_UTILIZATION),
        ("Most borrowed models in the last 30 days", ("Category", "Model", "Loans", "Rank"), queries.POPULAR_MODELS),
        ("Borrowers with repeat overdue loans", ("ID", "Borrower", "Late loans"), queries.REPEAT_OVERDUE),
        ("Recent audit events", ("Time (UTC)", "Action", "Equipment"), queries.RECENT_AUDIT),
    )
    return maintenance + '<div class="grid">' + "".join(
        report_table(title, headers, connection.execute(query)) for title, headers, query in reports
    ) + "</div>"



def render(category, notice, tab):
    overdue_filter = "WHERE l.returned_at IS NULL AND l.due_at < datetime('now')" if tab == "overdue" else ""
    with db.connect() as connection:
        categories = connection.execute("SELECT name FROM category ORDER BY name").fetchall()
        equipment = connection.execute(db.AVAILABLE, (category, category)).fetchall()
        students = connection.execute("SELECT id, name FROM student ORDER BY id").fetchall()
        loans = connection.execute(
            queries.LOAN_DETAILS + overdue_filter +
            " ORDER BY l.returned_at IS NOT NULL, l.due_at, l.id LIMIT 100"
        ).fetchall()
        operations_html = operations(connection, connection.execute(queries.AVAILABLE, ("", "")).fetchall())
    category_options = options([("", "All categories")] + [(r[0], r[0]) for r in categories], category)
    student_options = options([(r["id"], f'{r["name"]} · {r["id"]}') for r in students])
    device_options = options([(r["id"], f'{r["name"]} · {r["id"]}') for r in equipment])
    devices = "".join(
        f'<li><strong>{escape(r["name"])}</strong><span>{escape(r["id"])}</span></li>'
        for r in equipment
    ) or '<li>No equipment is available in this category.</li>'
    loan_rows = []
    for row in loans:
        status = "Returned" if row["returned_at"] else "Overdue" if row["overdue"] else "On loan"
        action = ""
        if row["returned_at"] is None:
            action = (
                '<form method="post" action="/return">'
                f'<input type="hidden" name="loan" value="{row["id"]}">'
                '<button class="secondary">Check in</button></form>'
            )
        loan_rows.append(
            f'<tr><td>{escape(row["model"])}<small>{escape(row["equipment_id"])}</small></td>'
            f'<td>{escape(row["student"])}</td><td>{escape(row["due_at"])}</td>'
            f'<td><span class="status {"late" if row["overdue"] else ""}">{status}</span></td>'
            f'<td>{action}</td></tr>'
        )
    table_rows = "".join(loan_rows) or '<tr><td colspan="5">No loans match this view.</td></tr>'
    message = f'<p class="notice" role="status">{escape(notice)}</p>' if notice else ""
    disabled = "" if equipment else " disabled"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Equipment Loans</title>
<link rel="stylesheet" href="/style.css">
</head>
<body><header><div class="masthead">Laboratory Equipment Service</div><div class="hero"><h1>Campus Equipment Loans</h1><p>Browse equipment, issue loans and check in returns.</p></div></header>
<main>
{message}
<div class="grid">
<section><h2>Available equipment</h2>
<form method="get" action="/" class="filter">
<label>Category <select name="category">{category_options}</select></label>
<button class="secondary">Apply filter</button>
</form><ul>{devices}</ul></section>
<section><h2>New loan</h2>
<form method="post" action="/borrow" class="stack">
<label>Borrower <select name="student" required>{student_options}</select></label>
<label>Equipment <select name="equipment" required{disabled}>{device_options}</select></label>
<label>Loan duration (days) <input type="number" name="days" min="1" max="30" value="7" required></label>
<button{disabled}>Check out equipment</button>
</form></section>
</div>
<section><div class="section-title"><h2>Loan records</h2>
<nav aria-label="Filter loan records">
<a href="/#loans" {"aria-current='page'" if tab != "overdue" else ""}>All loans</a>
<a href="/?tab=overdue#loans" {"aria-current='page'" if tab == "overdue" else ""}>Overdue only</a>
</nav></div>
<p>Showing up to 100 records, with open loans first.</p>
<div class="table-wrap" id="loans"><table>
<thead><tr><th>Equipment</th><th>Borrower</th><th>Due date (UTC)</th><th>Status</th><th>Action</th></tr></thead>
<tbody>{table_rows}</tbody></table></div>
</section>
{operations_html}
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send_content(self, content, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/style.css":
            self.send_content((db.ROOT / "style.css").read_bytes(), "text/css; charset=utf-8")
        elif url.path == "/":
            query = parse_qs(url.query)
            page = render(*(query.get(key, [""])[0] for key in ("category", "notice", "tab")))
            self.send_content(page.encode(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/borrow", "/return", "/maintenance/open", "/maintenance/close"):
            self.send_error(404)
            return
        port = self.server.server_port
        if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError
            form = parse_qs(self.rfile.read(size).decode("utf-8"), max_num_fields=8)
            if self.path == "/borrow":
                student, equipment = (form[key][0] for key in ("student", "equipment"))
                number = int(form["days"][0])
            elif self.path == "/return":
                number = int(form["loan"][0])
            elif self.path == "/maintenance/open":
                equipment, reason = (form[key][0] for key in ("equipment", "reason"))
            else:
                number = int(form["maintenance"][0])
        except (ValueError, KeyError):
            self.send_error(400, "Invalid form")
            return
        try:
            with db.connect() as connection:
                if self.path == "/borrow":
                    db.borrow(connection, student, equipment, number)
                    notice = "Equipment checked out."
                elif self.path == "/return":
                    db.return_equipment(connection, number)
                    notice = "Equipment checked in."
                elif self.path == "/maintenance/open":
                    db.open_maintenance(connection, equipment, reason)
                    notice = "Maintenance opened."
                else:
                    db.close_maintenance(connection, number)
                    notice = "Maintenance closed."
        except (ValueError, OverflowError) as exc:
            notice = str(exc)
        except sqlite3.OperationalError as exc:
            if getattr(exc, "sqlite_errorname", "") not in ("SQLITE_BUSY", "SQLITE_LOCKED"):
                raise
            notice = "The database is busy. Please try again."
        self.send_response(303)
        self.send_header("Location", "/?" + urlencode({"notice": notice}))
        self.end_headers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the campus equipment server locally.")
    parser.add_argument("--port", type=int, default=8000, help="Local HTTP port (default: 8000)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    db.initialize()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Campus Equipment: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
