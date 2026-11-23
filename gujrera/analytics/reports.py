"""Canned officer reports matched from plain-language questions (Gujarati, Hindi, English).

These cover the routine questions exactly and instantly. Anything they do not
match goes to the LLM text-to-SQL path. District names are inserted only from
the fixed list below, never from user text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gujrera.analytics.periods import Period, parse_period, without_period

DISTRICT_WORDS = {
    "ahmedabad": "Ahmedabad", "અમદાવાદ": "Ahmedabad", "अहमदाबाद": "Ahmedabad",
    "surat": "Surat", "સુરત": "Surat", "सूरत": "Surat",
    "vadodara": "Vadodara", "baroda": "Vadodara", "વડોદરા": "Vadodara", "वडोदरा": "Vadodara",
    "rajkot": "Rajkot", "રાજકોટ": "Rajkot", "राजकोट": "Rajkot",
    "gandhinagar": "Gandhinagar", "ગાંધીનગર": "Gandhinagar", "गांधीनगर": "Gandhinagar",
    "bhavnagar": "Bhavnagar", "ભાવનગર": "Bhavnagar", "भावनगर": "Bhavnagar",
}

W = {
    "delay": ("delay", "delayed", "late", "behind schedule", "વિલંબ", "મોડા", "મોડું", "देरी", "विलंब", "लेट"),
    "promoter": ("promoter", "promoters", "builder", "builders", "developer", "developers",
                 "પ્રમોટર", "બિલ્ડર", "ડેવલપર", "प्रमोटर", "बिल्डर", "डेवलपर"),
    "project": ("project", "projects", "પ્રોજેક્ટ", "प्रोजेक्ट"),
    "complaint": ("complaint", "complaints", "grievance", "ફરિયાદ", "शिकायत"),
    "category": ("category", "categories", "type", "types", "kind", "પ્રકાર", "प्रकार", "श्रेणी"),
    "open": ("open", "pending", "unresolved", "ખુલ્લી", "બાકી", "लंबित", "खुली"),
    "age": ("oldest", "longest", "ageing", "aging", "age", "days old", "સૌથી જૂની", "सबसे पुरानी"),
    "district": ("district", "districts", "district-wise", "districtwise", "જિલ્લા", "जिला", "जिले"),
    "expiry": ("lapsed", "expired", "expiring", "expire", "registration ending", "validity",
               "મુદત", "સમાપ્ત", "समाप्त", "अवधि"),
    "agent": ("agent", "agents", "broker", "એજન્ટ", "एजेंट"),
    "orders": ("penalty", "penalties", "show cause", "show-cause", "revocation", "adverse",
               "દંડ", "કારણદર્શક", "दंड", "जुर्माना"),
    "count": ("how many", "number of", "count", "કેટલા", "કેટલી", "कितने", "कितनी"),
    # authority records (POC sample questions)
    "scrutiny": ("scrutiny", "under review", "under examination", "pending approval", "સ્ક્રુટિની", "સ્ક્રૂટિની",
                 "ચકાસણી હેઠળ", "તપાસ હેઠળ", "स्क्रूटिनी", "स्क्रुटिनी", "जांच के अधीन", "जाँच के अधीन", "समीक्षाधीन"),
    "notice": ("notice", "notices", "નોટિસ", "नोटिस"),
    "default": ("default", "defaults", "defaulted", "defaulting", "defaulter", "defaulters", "non-compliance",
                "non compliance", "ડિફોલ્ટ", "ડિફૉલ્ટ", "ડિફોલ્ટર", "નિયમભંગ", "डिफ़ॉल्ट", "डिफॉल्ट", "चूक",
                "अनुपालन नहीं"),
    "past_completion": ("past their completion", "past completion", "past the completion",
                        "completion date has passed", "completion date passed", "overdue",
                        "પૂર્ણ થવાની તારીખ વીતી", "તારીખ વીતી", "સમયમર્યાદા વીતી",
                        "समापन तिथि बीत", "तारीख बीत", "तिथि बीत", "तिथि निकल"),
    "rank": ("top", "most", "highest", "સૌથી", "सबसे"),
    "penalty": ("penalty", "penalties", "fine", "fines", "દંડ", "दंड", "जुर्माना"),
}
ANALYTICS_CUES = ("which", "how many", "top", "list", "show", "count", "average", "most", "highest", "compare",
                  "report", "by district", "district-wise", "breakdown", "trend",
                  "કયા", "કયો", "કેટલા", "કેટલી", "સૌથી", "યાદી", "बताओ", "कौन से", "कितने", "कितनी", "सबसे", "सूची")

TITLES = {
    "delayed_by_promoter": {"en": "Promoters with the most delayed projects", "gu": "સૌથી વધુ વિલંબિત પ્રોજેક્ટ ધરાવતા પ્રમોટર",
                            "hi": "सबसे अधिक देरी वाले प्रोजेक्ट्स के प्रमोटर"},
    "delayed_projects": {"en": "Most delayed ongoing projects", "gu": "સૌથી વધુ વિલંબિત ચાલુ પ્રોજેક્ટ",
                         "hi": "सबसे अधिक देरी वाले चालू प्रोजेक्ट"},
    "complaints_by_category": {"en": "Complaints by category", "gu": "પ્રકાર મુજબ ફરિયાદો", "hi": "श्रेणी अनुसार शिकायतें"},
    "complaint_ageing": {"en": "Oldest open complaints", "gu": "સૌથી જૂની ખુલ્લી ફરિયાદો", "hi": "सबसे पुरानी लंबित शिकायतें"},
    "complaints_by_district": {"en": "Complaints by district", "gu": "જિલ્લા મુજબ ફરિયાદો", "hi": "जिलेवार शिकायतें"},
    "promoters_by_complaints": {"en": "Promoters with the most open complaints", "gu": "સૌથી વધુ ખુલ્લી ફરિયાદો ધરાવતા પ્રમોટર",
                                "hi": "सबसे अधिक लंबित शिकायतों वाले प्रमोटर"},
    "registrations_ending": {"en": "Lapsed or soon-ending registrations", "gu": "સમાપ્ત અથવા જલ્દી સમાપ્ત થતી નોંધણીઓ",
                             "hi": "समाप्त या जल्द समाप्त होने वाले पंजीकरण"},
    "agents_expired": {"en": "Agents with expired or ending registrations", "gu": "મુદત પૂરી અથવા પૂરી થતી નોંધણીવાળા એજન્ટ",
                       "hi": "समाप्त या समाप्त होने वाले पंजीकरण वाले एजेंट"},
    "projects_by_district": {"en": "Projects and delays by district", "gu": "જિલ્લા મુજબ પ્રોજેક્ટ અને વિલંબ",
                             "hi": "जिलेवार प्रोजेक्ट और देरी"},
    "projects_under_scrutiny": {"en": "Projects under scrutiny", "gu": "સ્ક્રુટિની હેઠળના પ્રોજેક્ટ",
                                "hi": "स्क्रूटिनी के अधीन प्रोजेक्ट"},
    "notices_issued": {"en": "Notices issued to developers", "gu": "ડેવલપર્સને આપેલી નોટિસ",
                       "hi": "डेवलपर्स को जारी नोटिस"},
    "promoters_by_notices": {"en": "Promoters with the most notices", "gu": "સૌથી વધુ નોટિસ મેળવનાર પ્રમોટર",
                             "hi": "सबसे अधिक नोटिस वाले प्रमोटर"},
    "defaulting_promoters": {"en": "Defaulting developers", "gu": "ડિફોલ્ટ કરનાર ડેવલપર્સ",
                             "hi": "डिफ़ॉल्ट करने वाले डेवलपर्स"},
    "past_completion": {"en": "Ongoing projects past their completion date",
                        "gu": "પૂર્ણ થવાની તારીખ વીતી ગઈ હોય તેવા ચાલુ પ્રોજેક્ટ",
                        "hi": "समापन तिथि बीत चुके चालू प्रोजेक्ट"},
    "penalty_orders": {"en": "Orders with penalties", "gu": "દંડ સાથેના આદેશો", "hi": "दंड वाले आदेश"},
    "adverse_orders": {"en": "Promoters with show-cause, penalty or revocation orders",
                       "gu": "કારણદર્શક, દંડ અથવા રદ કરવાના આદેશ ધરાવતા પ્રમોટર",
                       "hi": "कारण बताओ, दंड या रद्द करने के आदेश वाले प्रमोटर"},
}


ONGOING = "status = 'ongoing'"
AGENT_EXPIRING = "(is_expired = 1 OR status <> 'active' OR valid_until < date('now', '+90 day'))"
REG_ENDING = "(status = 'lapsed' OR (status = 'ongoing' AND reg_valid_until < date('now', '+90 day')))"


# Reports over the authority records (the department's POC sample questions). In chat these take
# precedence over older officer features that share words such as "order".
AUTHORITY_REPORTS = frozenset({"projects_under_scrutiny", "notices_issued", "promoters_by_notices",
                               "defaulting_promoters", "past_completion", "penalty_orders"})


@dataclass
class Report:
    key: str
    sql: str
    district: str | None
    period: Period | None = None
    note: str | None = None  # key of an explanatory sentence (e.g. how "default" is defined)
    locality: str | None = None


def _has(text_lc: str, group: str) -> bool:
    for w in W[group]:
        if re.fullmatch(r"[a-z \-]+", w):
            if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text_lc):
                return True
        elif w in text_lc:
            return True
    return False


def find_district(text_lc: str) -> str | None:
    for word, district in DISTRICT_WORDS.items():
        if (re.search(rf"(?<![a-z]){word}(?![a-z])", text_lc) if word.isascii() else word in text_lc):
            return district
    return None


def looks_like_analytics(text_lc: str) -> bool:
    return any(c in text_lc for c in ANALYTICS_CUES) or match_report(text_lc) is not None


def _top_n(text_lc: str, default: int = 10) -> int:
    m = re.search(r"\btop\s+(\d{1,3})\b", text_lc)
    if not m and _has(text_lc, "rank"):  # "સૌથી વધુ નોટિસ મેળવનાર 10 પ્રમોટર"
        m = re.search(r"(?<![\d/.-])(\d{1,3})(?![\d/.-])", text_lc)
    return max(1, min(int(m.group(1)), 100)) if m else default


def find_locality(text_lc: str) -> str | None:
    """A locality named in the question, from the fixed list (never copied from user text)."""
    from gujrera.authority_seed import locality_names

    best = None
    for spelling, name in locality_names().items():
        hit = (re.search(rf"(?<![a-z]){re.escape(spelling)}(?![a-z])", text_lc) if spelling.isascii()
               else spelling in text_lc)
        if hit and (best is None or len(spelling) > len(best[0])):
            best = (spelling, name)  # longest wins: "south bopal" over "bopal"
    return best[1] if best else None


# Dimensions or measures no standard report provides. A question asking for one of these goes to the
# LLM path instead, so a report never answers a different question than the one asked.
UNCOVERED = ("average", "avg", "mean", "median", "year", "yearly", "annual", "month", "monthly", "quarter",
             "trend", "ratio", "percent", "%", "compare", "comparison", "between", "project type", "by type",
             "status-wise", "by status", "per ", "each ", "over time",
             "સરેરાશ", "વર્ષ", "મહિન", "ટકા", "સરખામણી", "औसत", "वर्ष", "साल", "महीन", "प्रतिशत", "तुलना")


def _uncovered(text_lc: str) -> bool:
    for w in UNCOVERED:
        if w.strip().isascii() and w.strip().isalpha():
            if re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", text_lc):
                return True
        elif w in text_lc:
            return True
    return False


def match_report(text_lc: str) -> Report | None:
    period = parse_period(text_lc)
    text_lc = without_period(text_lc, period)  # "last six months" must not send the question to the LLM path
    if _uncovered(text_lc):
        return None
    d = find_district(text_lc)
    where_d = f"district = '{d}'" if d else None  # d comes only from DISTRICT_WORDS
    loc = find_locality(text_lc)
    where_l = f"locality = '{loc}'" if loc else None  # loc comes only from the fixed locality list

    def w(*conds: str | None) -> str:
        parts = [c for c in conds if c]
        return (" WHERE " + " AND ".join(parts)) if parts else ""

    def when(column: str) -> str | None:
        return period.sql(column) if period else None

    n = _top_n(text_lc)

    # Authority records (POC sample questions) first: their questions also contain words older reports match.
    if _has(text_lc, "scrutiny") and not _has(text_lc, "complaint"):
        return Report("projects_under_scrutiny",
                      "SELECT project_name, promoter_name, district, locality, subject, stage, opened_on "
                      f"FROM v_scrutiny{w('is_open = 1', where_d, where_l, when('opened_on'))} ORDER BY opened_on",
                      d, period, locality=loc)
    if _has(text_lc, "default"):
        limit = n if _has(text_lc, "rank") else 100
        return Report("defaulting_promoters",
                      "SELECT promoter_name, district, COUNT(*) AS defaults, SUM(is_unresolved) AS unresolved, "
                      f"MAX(event_date) AS latest_default FROM v_defaults{w(where_d, when('event_date'))} "
                      f"GROUP BY promoter_name, district ORDER BY unresolved DESC, defaults DESC LIMIT {limit}",
                      d, period, note="default_definition")
    if _has(text_lc, "notice"):
        if _has(text_lc, "rank"):
            return Report("promoters_by_notices",
                          "SELECT promoter_name, district, COUNT(*) AS notices, MAX(issued_on) AS latest_notice "
                          f"FROM v_notices{w(where_d, when('issued_on'))} GROUP BY promoter_name, district "
                          f"ORDER BY notices DESC, latest_notice DESC LIMIT {n}", d, period)
        return Report("notices_issued",
                      "SELECT promoter_name, project_name, district, notice_type, issued_on, status "
                      f"FROM v_notices{w(where_d, when('issued_on'))} ORDER BY issued_on DESC", d, period)
    if _has(text_lc, "past_completion") and not _has(text_lc, "complaint"):  # "overdue complaints" = triage
        overdue = "proposed_completion < date('now')"  # the completion date declared at registration
        return Report("past_completion",
                      "SELECT project_name, promoter_name, district, locality, proposed_completion, "
                      "revised_completion, delay_days "
                      f"FROM v_project_delays{w(ONGOING, overdue, where_d, where_l)} ORDER BY proposed_completion",
                      d, locality=loc)
    if _has(text_lc, "penalty") and not _has(text_lc, "promoter"):
        penalty = "order_type = 'penalty_order'"
        return Report("penalty_orders",
                      "SELECT order_no, promoter_name, project_name, district, issued_on, penalty_amount, penalty_paid "
                      f"FROM v_orders{w(penalty, where_d, when('issued_on'))} "
                      "ORDER BY issued_on DESC", d, period)
    if _has(text_lc, "delay") and _has(text_lc, "promoter"):
        return Report("delayed_by_promoter",
                      "SELECT promoter_name, COUNT(*) AS delayed_projects, MAX(delay_days) AS max_delay_days "
                      f"FROM v_project_delays{w('is_delayed = 1', where_d)} GROUP BY promoter_name "
                      f"ORDER BY delayed_projects DESC, max_delay_days DESC LIMIT {n}", d)
    if _has(text_lc, "delay") and not _has(text_lc, "complaint"):
        return Report("delayed_projects",
                      "SELECT project_name, promoter_name, district, delay_days, proposed_completion, reg_valid_until "
                      f"FROM v_project_delays{w('is_delayed = 1', ONGOING, where_d)} "
                      f"ORDER BY delay_days DESC LIMIT {n}", d)
    if _has(text_lc, "orders"):
        return Report("adverse_orders",
                      "SELECT promoter_name, district, adverse_orders, complaints_open FROM v_promoter_scorecard"
                      f"{w('adverse_orders > 0', where_d)} ORDER BY adverse_orders DESC, complaints_open DESC LIMIT {n}", d)
    if _has(text_lc, "agent") and (_has(text_lc, "expiry") or "valid" in text_lc):
        return Report("agents_expired",
                      "SELECT agent_name, reg_no, district, status, valid_until FROM v_agent_status"
                      f"{w(AGENT_EXPIRING, where_d)} "
                      "ORDER BY valid_until", d)
    if _has(text_lc, "expiry"):
        return Report("registrations_ending",
                      "SELECT project_name, promoter_name, district, status, reg_valid_until FROM v_project_delays"
                      f"{w(REG_ENDING, where_d)} "
                      "ORDER BY reg_valid_until", d)
    if _has(text_lc, "complaint"):
        if _has(text_lc, "promoter"):
            return Report("promoters_by_complaints",
                          "SELECT promoter_name, district, complaints_open, complaints_total FROM v_promoter_scorecard"
                          f"{w(where_d)} ORDER BY complaints_open DESC, complaints_total DESC LIMIT {n}", d)
        if _has(text_lc, "age"):
            return Report("complaint_ageing",
                          "SELECT ref_no, category, promoter_name, project_name, status, age_days FROM v_complaint_stats"
                          f"{w('is_open = 1', where_d)} ORDER BY age_days DESC LIMIT {n}", d)
        if _has(text_lc, "district") and not d:
            return Report("complaints_by_district",
                          "SELECT district, COUNT(*) AS complaints, SUM(is_open) AS open_complaints "
                          "FROM v_complaint_stats GROUP BY district ORDER BY complaints DESC", d)
        if _has(text_lc, "category") or _has(text_lc, "count") or _has(text_lc, "open"):
            return Report("complaints_by_category",
                          "SELECT category, COUNT(*) AS complaints, SUM(is_open) AS open_complaints "
                          f"FROM v_complaint_stats{w(where_d)} GROUP BY category ORDER BY complaints DESC", d)
    if (_has(text_lc, "project") and (_has(text_lc, "district") or _has(text_lc, "count"))):
        return Report("projects_by_district",
                      "SELECT district, COUNT(*) AS projects, SUM(is_delayed) AS delayed_projects, "
                      "ROUND(AVG(CASE WHEN is_delayed = 1 THEN delay_days END), 0) AS avg_delay_days "
                      f"FROM v_project_delays{w(where_d)} GROUP BY district ORDER BY projects DESC", d)
    return None
