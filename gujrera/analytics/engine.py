"""Answer an officer's plain-language question with a table, a chart and the SQL used.

Path: canned report (exact, instant) → otherwise the self-hosted LLM writes SQL
from the view schema → ``guard_sql`` → read-only execution with a time limit →
audit log. The SQL is always shown, and LLM-written queries are labelled.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx
from sqlalchemy import Engine, inspect

from gujrera.analytics.reports import TITLES, find_district, match_report
from gujrera.analytics.sql_guard import UnsafeSQL, execute_readonly, guard_sql
from gujrera.complaints.strings import label
from gujrera.config import get_gujrera_settings
from gujrera.db.repository import Repository
from gujrera.db.session import make_readonly_engine
from gujrera.db.views import ANALYTICS_VIEWS
from gujrera.i18n import word
from gujrera.profile.summarise import Sentence

S = {
    "capped": {
        "en": "Only the first {n} rows are shown; there are more. Ask for one district or a shorter period to narrow it.",
        "gu": "ફક્ત પ્રથમ {n} પંક્તિઓ બતાવી છે; વધુ છે. ઓછી કરવા એક જિલ્લો કે ટૂંકો સમયગાળો પૂછો.",
        "hi": "केवल पहली {n} पंक्तियाँ दिखाई हैं; और भी हैं। कम करने के लिए एक जिला या छोटी अवधि पूछें।",
    },
    "result": {
        "en": "{title}: {n} {rows}.{scope}",
        "gu": "{title}: {n} પંક્તિઓ.{scope}",
        "hi": "{title}: {n} पंक्तियाँ।{scope}",
    },
    "top": {
        "en": "Top: {label} ({metric}: {value}).",
        "gu": "સૌથી ઉપર: {label} ({metric}: {value}).",
        "hi": "सबसे ऊपर: {label} ({metric}: {value})।",
    },
    "empty": {
        "en": "The query ran but returned no rows.",
        "gu": "ક્વેરી ચાલી પણ કોઈ પરિણામ મળ્યું નથી.",
        "hi": "क्वेरी चली लेकिन कोई परिणाम नहीं मिला।",
    },
    "scope": {"en": " Limited to {d} district.", "gu": " ફક્ત {d} જિલ્લા માટે.", "hi": " केवल {d} जिले के लिए।"},
    "llm_title": {"en": "Custom query", "gu": "કસ્ટમ ક્વેરી", "hi": "कस्टम क्वेरी"},
    "llm_note": {
        "en": "This query was written by the AI model from your question; check the SQL before relying on it.",
        "gu": "આ ક્વેરી AI મોડેલે તમારા પ્રશ્ન પરથી લખી છે; તેના પર આધાર રાખતા પહેલાં SQL તપાસો.",
        "hi": "यह क्वेरी AI मॉडल ने आपके सवाल से लिखी है; भरोसा करने से पहले SQL जाँच लें।",
    },
    "cannot": {
        "en": "I couldn't turn that into a safe query. Try one of the standard reports below.",
        "gu": "હું તેને સુરક્ષિત ક્વેરીમાં ફેરવી શક્યો નહીં. નીચેના પ્રમાણભૂત રિપોર્ટમાંથી એક અજમાવો.",
        "hi": "मैं इसे सुरक्षित क्वेरी में नहीं बदल सका। नीचे दी गई मानक रिपोर्ट में से एक आज़माएँ।",
    },
    "officer_only": {
        "en": "This report is available to GUJRERA officers. Please log in as an officer.",
        "gu": "આ રિપોર્ટ GUJRERA અધિકારીઓ માટે છે. કૃપા કરીને અધિકારી તરીકે લોગિન કરો.",
        "hi": "यह रिपोर्ट GUJRERA अधिकारियों के लिए है। कृपया अधिकारी के रूप में लॉगिन करें।",
    },
    "period": {"en": "Period used: {p}.", "gu": "ગણતરીનો સમયગાળો: {p}.", "hi": "अवधि: {p}।"},
    "default_definition": {
        "en": "\"Default\" here means a recorded non-compliance: a quarterly progress report, quarter-end return or "
              "Form 5 annual report not filed on time, or a fee not paid. \"Unresolved\" means not yet made good.",
        "gu": "અહીં \"ડિફોલ્ટ\" એટલે નોંધાયેલ નિયમભંગ: ત્રિમાસિક પ્રગતિ અહેવાલ, ત્રિમાસિક અંતનું રિટર્ન અથવા ફોર્મ 5 "
              "વાર્ષિક અહેવાલ સમયસર ન ભરવો, અથવા ફી ન ભરવી. \"બાકી\" એટલે હજી સુધી પૂર્ણ ન કરેલ.",
        "hi": "यहाँ \"डिफ़ॉल्ट\" का अर्थ है दर्ज अनुपालन चूक: तिमाही प्रगति रिपोर्ट, तिमाही-अंत रिटर्न या फ़ॉर्म 5 वार्षिक "
              "रिपोर्ट समय पर न भरना, या शुल्क न भरना। \"लंबित\" यानी अभी तक पूरा नहीं किया गया।",
    },
    "out_of_scope": {
        "en": "Your access covers {scope} district only, so records from {asked} are not shown. This request has been logged.",
        "gu": "તમારી પહોંચ ફક્ત {scope} જિલ્લા સુધી છે, તેથી {asked} ના રેકોર્ડ બતાવાયા નથી. આ વિનંતી નોંધવામાં આવી છે.",
        "hi": "आपकी पहुँच केवल {scope} जिले तक है, इसलिए {asked} के रिकॉर्ड नहीं दिखाए गए। यह अनुरोध दर्ज किया गया है।",
    },
    "read_only": {
        "en": "I can only read records. Changing or deleting data is not possible from here. This request has been logged.",
        "gu": "હું ફક્ત રેકોર્ડ વાંચી શકું છું. અહીંથી ડેટા બદલવો કે કાઢી નાખવો શક્ય નથી. આ વિનંતી નોંધવામાં આવી છે.",
        "hi": "मैं केवल रिकॉर्ड पढ़ सकता हूँ। यहाँ से डेटा बदलना या हटाना संभव नहीं है। यह अनुरोध दर्ज किया गया है।",
    },
    "refused": {
        "en": "That query was refused: {reason}",
        "gu": "તે ક્વેરી નકારવામાં આવી: {reason}",
        "hi": "वह क्वेरी अस्वीकार की गई: {reason}",
    },
}
SUGGESTED = [
    "Which projects are under scrutiny in Ahmedabad?",
    "Which developers were issued notices in the last six months?",
    "Which developers in Ahmedabad defaulted in the last six months?",
    "Which promoters in Surat have the most delayed projects?",
    "Complaints by category",
    "Oldest open complaints",
    "Lapsed or soon-ending registrations",
    "District-wise projects and delays",
    "Promoters with penalty or show-cause orders",
]

FEW_SHOT = """Q: which promoters in Surat have the most delayed projects
SQL: SELECT promoter_name, COUNT(*) AS delayed_projects FROM v_project_delays WHERE district = 'Surat' AND is_delayed = 1 GROUP BY promoter_name ORDER BY delayed_projects DESC LIMIT 10
Q: average delay of delayed projects by project type
SQL: SELECT project_type, ROUND(AVG(delay_days), 0) AS avg_delay_days, COUNT(*) AS projects FROM v_project_delays WHERE is_delayed = 1 GROUP BY project_type ORDER BY avg_delay_days DESC
Q: how many complaints were filed each year
SQL: SELECT strftime('%Y', filed_on) AS year, COUNT(*) AS complaints FROM v_complaint_stats GROUP BY year ORDER BY year"""


# Requests to change data. Refused before any SQL is written: the officer assistant only reads.
WRITE_INTENT = re.compile(
    r"\b(delete|drop|truncate|update|insert|modify|alter|remove|erase|wipe)\b.*\b(table|tables|record|records|row|rows|"
    r"data|database|project|projects|entry|entries|notice|notices|order|orders|complaint|complaints|promoter|promoters|"
    r"agent|agents|status|statuses|user|users|log|logs)\b|"
    r"(ડિલીટ|કાઢી નાખ|ભૂંસી|હટાવ|બદલી નાખ)|(डिलीट|हटा दो|हटाओ|मिटा|बदल दो)", re.IGNORECASE)


def s(key: str, lang: str, **values: Any) -> str:
    entry = S[key]
    return entry.get(lang, entry["en"]).format(**values)


@dataclass
class AnalyticsAnswer:
    intent: str
    sentences: list[Sentence]
    card: dict[str, Any] | None = None
    suggestions: list[str] = field(default_factory=list)


@lru_cache(maxsize=8)
def _readonly_engine(url: str) -> Engine:
    return make_readonly_engine(url)


def schema_text(engine: Engine) -> str:
    insp = inspect(engine)
    lines = []
    for view in ANALYTICS_VIEWS:
        cols = ", ".join(f"{c['name']}" for c in insp.get_columns(view))
        lines.append(f"{view}({cols})")
    return "\n".join(lines)


def ollama_sql(prompt: str) -> str:
    """Ask the self-hosted SQL model. Thinking-only models leave ``content`` empty and put the
    answer at the end of their reasoning, so that is used as a fallback (the guard still applies)."""
    cfg = get_gujrera_settings()
    res = httpx.post(
        f"{cfg.GUJRERA_LLM_BASE_URL.rstrip('/')}/api/chat",
        json={"model": cfg.GUJRERA_SQL_MODEL, "stream": False, "think": False, "keep_alive": cfg.GUJRERA_LLM_KEEP_ALIVE, "options": {"temperature": 0},
              "messages": [{"role": "user", "content": "/no_think\n" + prompt}]},
        timeout=cfg.GUJRERA_ANALYTICS_LLM_TIMEOUT_SECONDS,
    )
    res.raise_for_status()
    message = res.json().get("message", {})
    return message.get("content") or message.get("thinking") or ""


_SQL_LINE = re.compile(r"(?im)^[ \t]*(?:sql:[ \t]*)?((?:with|select)\b.*)$")


def _extract_sql(text: str) -> str:
    """The last SQL statement in the model output: a code block, or a line starting with SELECT/WITH."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    blocks = re.findall(r"```(?:sql)?\s*(.+?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip().rstrip(";")
    lines = list(_SQL_LINE.finditer(text))
    if not lines:
        return ""
    tail = text[lines[-1].start(1):]
    return re.split(r"\n\s*\n", tail, maxsplit=1)[0].strip().rstrip(";")


def llm_sql(question: str, engine: Engine, generate: Callable[[str], str]) -> str:
    prompt = (
        "You write one SQLite SELECT query for a GUJRERA officer. Use only these views and columns:\n"
        f"{schema_text(engine)}\n"
        "Dates are ISO strings; is_delayed and is_open are 0/1; district names are capitalised (e.g. 'Surat').\n"
        "Return only the SQL, nothing else.\n\n"
        f"{FEW_SHOT}\nQ: {question}\nSQL:"
    )
    return _extract_sql(generate(prompt))


def _chart(columns: list[str], rows: list[list[Any]]) -> dict[str, str] | None:
    if len(columns) < 2 or not rows or len(rows) > 30:
        return None
    label = columns[0]
    numeric = [c for i, c in enumerate(columns[1:], 1)
               if all(isinstance(r[i], (int, float)) or r[i] is None for r in rows)]
    if isinstance(rows[0][0], (int, float)) or not numeric:
        return None
    return {"x": label, "y": numeric[0]}


def answer(question: str, repo: Repository, lang: str, *,
           generate: Callable[[str], str] | None = None) -> AnalyticsAnswer:
    """Officer analytics. Callers must have checked repo.p.role == "officer"."""
    settings = get_gujrera_settings()
    scope = repo.p.district_scope
    text_lc = (question or "").lower()
    if WRITE_INTENT.search(text_lc):
        repo._audit("analytics_write_refused", {"question": question})
        return AnalyticsAnswer("analytics_refused", [Sentence(s("read_only", lang), [], "an_read_only")],
                               suggestions=SUGGESTED)
    asked = find_district(text_lc)
    if scope and asked and asked != scope:
        repo._audit("analytics_out_of_scope", {"question": question, "asked": asked, "scope": scope})
        return AnalyticsAnswer("analytics_out_of_scope",
                               [Sentence(s("out_of_scope", lang, scope=word(scope, lang), asked=word(asked, lang)),
                                         [], "an_out_of_scope")], suggestions=SUGGESTED)
    report = match_report(text_lc)
    source = "report"
    if report:
        sql, title = report.sql, TITLES[report.key][lang]
    else:
        if generate is None and not settings.GUJRERA_ANALYTICS_LLM:
            return AnalyticsAnswer("analytics_unmatched", [Sentence(s("cannot", lang), [], "an_cannot")],
                                   suggestions=SUGGESTED)
        try:
            sql = llm_sql(question, repo.s.get_bind(), generate or ollama_sql)
        except Exception:  # noqa: BLE001 - model unavailable or timed out
            sql = ""
        if not sql:
            return AnalyticsAnswer("analytics_unmatched", [Sentence(s("cannot", lang), [], "an_cannot")],
                                   suggestions=SUGGESTED)
        source, title = "llm", s("llm_title", lang)

    try:
        guarded = guard_sql(sql, district_scope=scope, max_rows=settings.GUJRERA_MAX_ROWS)
    except UnsafeSQL as exc:
        repo._audit("analytics_refused", {"question": question, "sql": sql, "reason": str(exc)})
        return AnalyticsAnswer("analytics_refused", [Sentence(s("refused", lang, reason=str(exc)), [], "an_refused")],
                               card={"type": "analytics", "title": title, "sql": sql, "source": source,
                                     "refused": str(exc), "columns": [], "rows": []},
                               suggestions=SUGGESTED)

    url = repo.s.get_bind().url.render_as_string(hide_password=False)
    try:
        result = execute_readonly(_readonly_engine(url), guarded, timeout_s=settings.GUJRERA_SQL_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - SQL error or timeout: report, do not crash
        repo._audit("analytics_failed", {"question": question, "sql": guarded.sql, "error": str(exc)[:300]})
        return AnalyticsAnswer("analytics_refused",
                               [Sentence(s("refused", lang, reason=str(exc).splitlines()[0][:200]), [], "an_refused")],
                               suggestions=SUGGESTED)
    repo._audit("analytics_query", {"question": question, "source": source, "sql": guarded.sql,
                                    "rows": len(result.rows)})

    citations = [{"type": "view", "id": v, "is_mock": True} for v in guarded.views]
    scope_txt = s("scope", lang, d=word(scope, lang)) if scope else ""
    sentences = [Sentence(s("result", lang, title=title, n=len(result.rows), rows="row" if len(result.rows) == 1 else "rows",
                            scope=scope_txt), citations, "an_result")]
    chart = _chart(result.columns, result.rows)
    if result.rows and chart and "order by" in sql.lower():  # "top" only makes sense for a sorted result
        top = result.rows[0]
        y_idx = result.columns.index(chart["y"])
        sentences.append(Sentence(s("top", lang, label=label(str(top[0]), lang), metric=chart["y"].replace("_", " "),
                                    value=top[y_idx]), citations, "an_top"))
    elif not result.rows:
        sentences.append(Sentence(s("empty", lang), [], "an_empty"))
    cap = int(guarded.sql.rsplit("LIMIT", 1)[1])
    if result.rows and len(result.rows) >= cap:
        sentences.append(Sentence(s("capped", lang, n=cap), [], "an_capped"))
    if report and report.period:
        sentences.append(Sentence(s("period", lang, p=report.period.describe(lang)), [], "an_period"))
    if report and report.note:
        sentences.append(Sentence(s(report.note, lang), [], "an_note"))
    if source == "llm":
        sentences.append(Sentence(s("llm_note", lang), [], "an_llm_note"))
    card = {
        "type": "analytics", "title": title, "columns": result.columns, "rows": result.rows,
        "sql": guarded.sql, "source": source, "scoped_to": scope, "truncated": result.truncated,
        "chart": chart, "elapsed_ms": result.elapsed_ms, "district_asked": find_district(text_lc),
        "is_mock": True,
    }
    return AnalyticsAnswer("analytics", sentences, card=card)
