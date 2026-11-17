"""Attack queries the SQL guard must refuse, and officer questions with their expected report.

Shared by the tests and scripts/eval_gujrera_analytics.py.
"""

from __future__ import annotations

ATTACKS: list[tuple[str, str]] = [
    ("write", "DELETE FROM projects"),
    ("write", "UPDATE projects SET status = 'completed'"),
    ("write", "INSERT INTO audit_log (at, role, action) VALUES ('2026-01-01', 'x', 'y')"),
    ("write", "REPLACE INTO users (id, username, role) VALUES (1, 'x', 'officer')"),
    ("schema", "DROP TABLE complaints"),
    ("schema", "CREATE TABLE stolen AS SELECT * FROM users"),
    ("schema", "ALTER TABLE users ADD COLUMN pwned TEXT"),
    ("stacked", "SELECT * FROM v_project_delays; DELETE FROM projects"),
    ("stacked", "SELECT 1 FROM v_project_delays; DROP TABLE users;"),
    ("private table", "SELECT * FROM users"),
    ("private table", "SELECT password_hash FROM users"),
    ("private table", "SELECT * FROM mock_portal_submissions"),
    ("private table", "SELECT complainant_hash, complainant_user_id FROM complaints"),
    ("private table", "SELECT * FROM dues_notices"),
    ("private table", "SELECT * FROM audit_log"),
    ("private table", "SELECT * FROM sqlite_master"),
    ("subquery", "SELECT * FROM v_project_delays WHERE promoter_id IN (SELECT promoter_id FROM users)"),
    ("subquery", "SELECT (SELECT password_hash FROM users LIMIT 1) AS x FROM v_project_delays"),
    ("union", "SELECT project_name FROM v_project_delays UNION SELECT username FROM users"),
    ("cte", "WITH u AS (SELECT * FROM users) SELECT * FROM u"),
    ("qualified", "SELECT * FROM main.v_project_delays"),
    ("qualified", "SELECT * FROM temp.v_project_delays"),
    ("pragma", "PRAGMA table_info(users)"),
    ("attach", "ATTACH DATABASE 'x.db' AS x"),
    ("function", "SELECT load_extension('evil') FROM v_project_delays"),
    ("function", "SELECT readfile('C:/Windows/win.ini') FROM v_project_delays"),
    ("function", "SELECT writefile('x.txt', 'y') FROM v_project_delays"),
    ("function", "SELECT sqlite_version() FROM v_project_delays"),
    ("transaction", "BEGIN; DELETE FROM projects; COMMIT"),
    ("empty", ""),
]

# (question, expected report key or None for "no standard report")
QUESTIONS: list[tuple[str, str | None]] = [
    ("Which promoters in Surat have the most delayed projects?", "delayed_by_promoter"),
    ("top 5 builders with delayed projects", "delayed_by_promoter"),
    ("સુરતમાં સૌથી વધુ વિલંબિત પ્રોજેક્ટ ધરાવતા બિલ્ડર કયા છે?", "delayed_by_promoter"),
    ("अहमदाबाद में सबसे ज्यादा देरी वाले बिल्डर कौन से हैं?", "delayed_by_promoter"),
    ("Most delayed projects in Rajkot", "delayed_projects"),
    ("વિલંબિત પ્રોજેક્ટની યાદી", "delayed_projects"),
    ("Complaints by category", "complaints_by_category"),
    ("કેટલી ફરિયાદો ખુલ્લી છે પ્રકાર મુજબ?", "complaints_by_category"),
    ("शिकायतें श्रेणी अनुसार", "complaints_by_category"),
    ("Oldest open complaints in Vadodara", "complaint_ageing"),
    ("सबसे पुरानी लंबित शिकायतें", "complaint_ageing"),
    ("Complaints by district", "complaints_by_district"),
    ("Promoters with the most complaints", "promoters_by_complaints"),
    ("કયા બિલ્ડર સામે સૌથી વધુ ફરિયાદો છે?", "promoters_by_complaints"),
    ("Lapsed or soon-ending registrations", "registrations_ending"),
    ("જેની નોંધણીની મુદત સમાપ્ત થઈ છે તે પ્રોજેક્ટ", "registrations_ending"),
    ("Agents with expired registration", "agents_expired"),
    ("District-wise projects and delays", "projects_by_district"),
    ("how many projects in Gandhinagar", "projects_by_district"),
    ("Promoters with penalty or show-cause orders", "adverse_orders"),
    ("दंड आदेश वाले प्रमोटर", "adverse_orders"),
    # not covered by a standard report: must go to the LLM path, never to a wrong report
    ("average delay by project type", None),
    ("how many complaints were filed each year", None),
    ("monthly trend of complaints", None),
    ("compare delays between Surat and Ahmedabad", None),
    ("સરેરાશ વિલંબ કેટલો છે?", None),
    ("प्रतिशत परियोजनाएँ जिनमें देरी है", None),
]
