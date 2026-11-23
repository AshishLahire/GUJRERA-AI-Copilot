"""Derived reporting views.

These views are the ONLY relations the officer analytics (text-to-SQL) layer
may read; see ``ANALYTICS_VIEWS``. They expose no complainant identifiers.

Date arithmetic differs between SQLite and PostgreSQL, so the SQL is rendered
per dialect.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

ANALYTICS_VIEWS = (
    "v_project_delays",
    "v_promoter_scorecard",
    "v_complaint_stats",
    "v_agent_status",
    # Authority records (officers only); each carries `district` so officer scope applies.
    "v_scrutiny",
    "v_notices",
    "v_defaults",
    "v_orders",
)


def _days(later: str, earlier: str, dialect: str) -> str:
    if dialect == "sqlite":
        return f"CAST(julianday({later}) - julianday({earlier}) AS INTEGER)"
    return f"({later} - {earlier})"


def _greatest(a: str, b: str, dialect: str) -> str:
    return f"MAX({a}, {b})" if dialect == "sqlite" else f"GREATEST({a}, {b})"


def _today(dialect: str) -> str:
    return "date('now')" if dialect == "sqlite" else "CURRENT_DATE"


def view_sql(dialect: str) -> dict[str, str]:
    today = _today(dialect)
    # Delay is measured against the ORIGINAL proposed completion date: for completed
    # projects up to actual completion, otherwise up to today.
    end = f"COALESCE(p.actual_completion, {today})"
    delay = _greatest(_days(end, "p.proposed_completion", dialect), "0", dialect)
    # No delay is claimed when the source does not say whether the project was completed.
    delay = f"(CASE WHEN p.status = 'unverified' THEN 0 ELSE {delay} END)"
    open_statuses = "('filed','under_scrutiny','hearing_scheduled','order_reserved')"
    return {
        "v_project_delays": f"""
            CREATE VIEW v_project_delays AS
            SELECT p.id AS project_id, p.rera_no, p.name AS project_name, p.district, p.taluka, p.locality,
                   p.project_type, p.status, p.units, p.promoter_id, pr.name AS promoter_name,
                   p.reg_date, p.proposed_completion, p.revised_completion, p.actual_completion,
                   p.reg_valid_until,
                   {delay} AS delay_days,
                   CASE WHEN {delay} > 0 THEN 1 ELSE 0 END AS is_delayed,
                   p.is_mock
            FROM projects p JOIN promoters pr ON pr.id = p.promoter_id
        """,
        "v_promoter_scorecard": f"""
            CREATE VIEW v_promoter_scorecard AS
            SELECT pr.id AS promoter_id, pr.name AS promoter_name, pr.district,
                   COUNT(DISTINCT d.project_id) AS projects,
                   COALESCE(SUM(d.is_delayed), 0) AS delayed_projects,
                   COALESCE(MAX(d.delay_days), 0) AS max_delay_days,
                   (SELECT COUNT(*) FROM complaints c WHERE c.promoter_id = pr.id) AS complaints_total,
                   (SELECT COUNT(*) FROM complaints c WHERE c.promoter_id = pr.id
                        AND c.status IN {open_statuses}) AS complaints_open,
                   (SELECT COUNT(*) FROM orders o WHERE o.promoter_id = pr.id
                        AND o.order_type IN ('penalty_order','revocation_order','show_cause')) AS adverse_orders,
                   pr.is_mock
            FROM promoters pr LEFT JOIN v_project_delays d ON d.promoter_id = pr.id
            GROUP BY pr.id, pr.name, pr.district, pr.is_mock
        """,
        "v_complaint_stats": f"""
            CREATE VIEW v_complaint_stats AS
            SELECT c.id AS complaint_id, c.ref_no, c.district, c.form, c.category, c.status,
                   c.outcome, c.filed_on, c.closed_on,
                   CASE WHEN c.status IN {open_statuses} THEN 1 ELSE 0 END AS is_open,
                   {_days(f"COALESCE(c.closed_on, {today})", "c.filed_on", dialect)} AS age_days,
                   c.project_id, p.name AS project_name, c.promoter_id, pr.name AS promoter_name,
                   c.is_mock
            FROM complaints c
            LEFT JOIN projects p ON p.id = c.project_id
            LEFT JOIN promoters pr ON pr.id = c.promoter_id
        """,
        "v_agent_status": f"""
            CREATE VIEW v_agent_status AS
            SELECT a.id AS agent_id, a.reg_no, a.name AS agent_name, a.district, a.status,
                   a.reg_date, a.valid_until,
                   CASE WHEN a.valid_until < {today} THEN 1 ELSE 0 END AS is_expired,
                   (SELECT COUNT(*) FROM complaints c WHERE c.agent_id = a.id) AS complaints_total,
                   a.is_mock
            FROM agents a
        """,
        "v_scrutiny": """
            CREATE VIEW v_scrutiny AS
            SELECT s.id AS scrutiny_id, p.id AS project_id, p.rera_no, p.name AS project_name, p.district, p.taluka,
                   p.locality, pr.name AS promoter_name, s.subject, s.stage,
                   CASE WHEN s.stage IN ('under_scrutiny', 'query_raised') THEN 1 ELSE 0 END AS is_open,
                   s.opened_on, s.closed_on, s.is_mock
            FROM project_scrutiny s JOIN projects p ON p.id = s.project_id JOIN promoters pr ON pr.id = p.promoter_id
        """,
        "v_notices": """
            CREATE VIEW v_notices AS
            SELECT n.id AS notice_id, n.ref_no, n.notice_type, n.issued_on, n.status,
                   pr.id AS promoter_id, pr.name AS promoter_name, p.name AS project_name, p.rera_no,
                   COALESCE(p.district, pr.district) AS district, n.is_mock
            FROM authority_notices n JOIN promoters pr ON pr.id = n.promoter_id
            LEFT JOIN projects p ON p.id = n.project_id
        """,
        "v_defaults": """
            CREATE VIEW v_defaults AS
            SELECT e.id AS event_id, e.event_type, e.period, e.event_date, e.resolved_on,
                   CASE WHEN e.resolved_on IS NULL THEN 1 ELSE 0 END AS is_unresolved,
                   pr.id AS promoter_id, pr.name AS promoter_name, p.name AS project_name, p.rera_no,
                   p.district, e.is_mock
            FROM compliance_events e JOIN promoters pr ON pr.id = e.promoter_id JOIN projects p ON p.id = e.project_id
        """,
        "v_orders": """
            CREATE VIEW v_orders AS
            SELECT o.id AS order_id, o.order_no, o.order_type, o.issued_on, op.amount AS penalty_amount,
                   op.paid AS penalty_paid, pr.name AS promoter_name, p.name AS project_name, p.rera_no,
                   COALESCE(p.district, pr.district) AS district, o.is_mock
            FROM orders o LEFT JOIN order_penalties op ON op.order_id = o.id
            LEFT JOIN projects p ON p.id = o.project_id LEFT JOIN promoters pr ON pr.id = COALESCE(o.promoter_id, p.promoter_id)
        """,
    }


def create_views(conn: Connection) -> None:
    dialect = conn.dialect.name
    for name in reversed(ANALYTICS_VIEWS):  # drop dependants first
        conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
    statements = view_sql(dialect)
    for name in ANALYTICS_VIEWS:  # v_project_delays before v_promoter_scorecard
        conn.execute(text(statements[name]))
