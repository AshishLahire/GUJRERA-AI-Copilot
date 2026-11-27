"""Administration for the POC: user accounts and roles, and the audit log viewer.

State-level officers are the administrators of the POC (the department will name its own admins). They:

* create test accounts for officers (with a district, or statewide) and citizens; a one-time password is
  shown once to the admin, who hands it over; it is never stored or logged in clear;
* change an officer's district, disable or enable an account, and reset a password. Disabling an account
  or resetting its password ends every session it has open;
* read the audit log: who did what and when, every refusal (outside the district, attempts to change data,
  unsafe queries, failed logins, pages a role may not open), data loads and exports, with filters and a
  CSV download.

Guards: an admin cannot disable or narrow their own account, and the last active statewide officer cannot be
disabled or given a district, so the system can always be administered. Promoter and agent accounts are
linked to registry records and are not created here.
"""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from gujrera.auth import hash_password
from gujrera.db.models import Agent, AuditLog, Project, Promoter, User
from gujrera.db.repository import AccessDenied, Repository

CREATABLE_ROLES = ("officer", "citizen")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,39}$")
ROLE_LABELS = {"officer": "GUJRERA officer", "citizen": "Home buyer", "developer": "Promoter", "agent": "Agent"}

# What each audit action means, and its category, for the viewer.
ACTIONS: dict[str, tuple[str, str]] = {
    "login": ("login", "Logged in"),
    "login_failed": ("refusal", "Wrong username or password"),
    "login_locked": ("refusal", "Login locked after repeated failures"),
    "login_disabled": ("refusal", "Login to a disabled account"),
    "access_denied": ("refusal", "Opened something this role may not use"),
    "analytics_out_of_scope": ("refusal", "Asked about another district"),
    "analytics_write_refused": ("refusal", "Asked to change data (reports are read-only)"),
    "analytics_refused": ("refusal", "Unsafe query blocked"),
    "analytics_failed": ("report", "Report query failed"),
    "complaint_status_denied": ("refusal", "Complaint status change refused"),
    "dues_denied": ("refusal", "Dues of another promoter refused"),
    "qpr_denied": ("refusal", "Quarterly report of another promoter refused"),
    "analytics_query": ("report", "Ran a report"),
    "analytics_export": ("report", "Exported a report"),
    "report_saved": ("report", "Saved a report"),
    "data_upload": ("data", "Uploaded a data file"),
    "data_check": ("data", "Checked a data file"),
    "data_load": ("data", "Loaded a data file"),
    "user_created": ("admin", "Created an account"),
    "user_updated": ("admin", "Changed an account"),
    "password_reset": ("admin", "Reset a password"),
    "officer_dashboard": ("work", "Opened the work queue"),
    "officer_review": ("work", "Marked a work-queue item"),
    "complaint_triage": ("work", "Opened the complaint desk"),
    "complaint_brief": ("work", "Opened a hearing brief"),
    "complaint_status_changed": ("work", "Changed a complaint's status"),
    "enforcement_list": ("work", "Opened ad enforcement"),
    "enforcement_case_viewed": ("work", "Opened an ad case"),
    "enforcement_case_updated": ("work", "Updated an ad case"),
    "order_compliance_updated": ("work", "Updated an order's compliance"),
    "risk_watchlist": ("work", "Opened the risk watch"),
    "complaint_document_opened": ("work", "Opened a complaint document"),
    "dues_notices": ("work", "Opened dues and notices"),
    "qpr_overview": ("work", "Opened quarterly reports"),
    "qpr_filed": ("work", "Filed a quarterly report"),
    "orders_to_enforce": ("work", "Opened orders to enforce"),
    "complaint_access_denied": ("refusal", "Complaint access refused"),
    "audit_exported": ("admin", "Downloaded the audit log"),
    "poc_setting_changed": ("admin", "Changed a POC setting"),
    "test_cases_generated": ("admin", "Generated test questions"),
    "test_cases_imported": ("admin", "Imported test questions"),
    "test_case_added": ("admin", "Added a test question"),
    "test_case_from_feedback": ("admin", "Turned feedback into a test question"),
    "test_run_started": ("admin", "Ran the test set"),
    "circular_uploaded": ("data", "Uploaded a circular"),
    "circular_updated": ("data", "Changed a circular"),
    "circular_deleted": ("data", "Deleted a circular"),
    "chat_reply": ("public", "Answered a chat question"),
    "district_list": ("public", "Listed a district's projects"),
    "locality_list": ("public", "Listed a locality's projects"),
    "project_report": ("public", "Opened a project report"),
    "agent_list": ("public", "Listed agents"),
    "agreement_checked": ("public", "Checked an agreement"),
    "ad_reported": ("public", "Reported an ad"),
    "circular_answer": ("public", "Answered from a circular"),
    "order_lookup": ("public", "Looked up an order"),
    "complaint_status": ("public", "Looked up a complaint"),
    "list_complaints": ("public", "Listed complaints"),
    "complaint_document_added": ("public", "Added a complaint document"),
    "watch_added": ("public", "Started watching a project"),
    "watch_removed": ("public", "Stopped watching a project"),
}

# The same labels in Gujarati and Hindi (English above). Native-speaker review pending.
ACTION_I18N: dict[str, tuple[str, str]] = {
    "login": ("લૉગિન કર્યું", "लॉगिन किया"),
    "login_failed": ("ખોટું યુઝરનેમ કે પાસવર્ડ", "गलत यूज़रनेम या पासवर्ड"),
    "login_locked": ("વારંવાર નિષ્ફળતા પછી લૉગિન બંધ", "बार-बार विफलता के बाद लॉगिन बंद"),
    "login_disabled": ("નિષ્ક્રિય ખાતામાં લૉગિનનો પ્રયાસ", "निष्क्रिय खाते में लॉगिन का प्रयास"),
    "access_denied": ("આ ભૂમિકા માટે નહીં તેવું કંઈક ખોલ્યું", "इस भूमिका के लिए नहीं, ऐसा कुछ खोला"),
    "analytics_out_of_scope": ("બીજા જિલ્લા વિશે પૂછ્યું", "दूसरे जिले के बारे में पूछा"),
    "analytics_write_refused": ("ડેટા બદલવા કહ્યું (રિપોર્ટ ફક્ત વાંચવા માટે છે)", "डेटा बदलने को कहा (रिपोर्ट केवल पढ़ने के लिए हैं)"),
    "analytics_refused": ("અસુરક્ષિત ક્વેરી રોકી", "असुरक्षित क्वेरी रोकी"),
    "analytics_failed": ("રિપોર્ટ ક્વેરી નિષ્ફળ", "रिपोर्ट क्वेरी विफल"),
    "complaint_status_denied": ("ફરિયાદની સ્થિતિ બદલવાનો ઇનકાર", "शिकायत की स्थिति बदलने से इनकार"),
    "dues_denied": ("બીજા પ્રમોટરનાં લેણાં જોવાનો ઇનકાર", "दूसरे प्रमोटर के बकाया देखने से इनकार"),
    "qpr_denied": ("બીજા પ્રમોટરના ત્રિમાસિક અહેવાલનો ઇનકાર", "दूसरे प्रमोटर की तिमाही रिपोर्ट से इनकार"),
    "analytics_query": ("રિપોર્ટ ચલાવ્યો", "रिपोर्ट चलाई"),
    "analytics_export": ("રિપોર્ટ ડાઉનલોડ કર્યો", "रिपोर्ट डाउनलोड की"),
    "report_saved": ("રિપોર્ટ સાચવ્યો", "रिपोर्ट सहेजी"),
    "data_upload": ("ડેટા ફાઇલ અપલોડ કરી", "डेटा फ़ाइल अपलोड की"),
    "data_check": ("ડેટા ફાઇલ તપાસી", "डेटा फ़ाइल जाँची"),
    "data_load": ("ડેટા ફાઇલ લોડ કરી", "डेटा फ़ाइल लोड की"),
    "user_created": ("ખાતું બનાવ્યું", "खाता बनाया"),
    "user_updated": ("ખાતું બદલ્યું", "खाता बदला"),
    "password_reset": ("પાસવર્ડ ફરી સેટ કર્યો", "पासवर्ड रीसेट किया"),
    "officer_dashboard": ("કાર્યસૂચિ ખોલી", "कार्यसूची खोली"),
    "officer_review": ("કાર્યસૂચિની બાબત ચિહ્નિત કરી", "कार्यसूची का मद चिह्नित किया"),
    "complaint_triage": ("ફરિયાદ ડેસ્ક ખોલ્યું", "शिकायत डेस्क खोली"),
    "complaint_brief": ("સુનાવણીનો સાર ખોલ્યો", "सुनवाई का सार खोला"),
    "complaint_status_changed": ("ફરિયાદની સ્થિતિ બદલી", "शिकायत की स्थिति बदली"),
    "enforcement_list": ("જાહેરાત અમલીકરણ ખોલ્યું", "विज्ञापन प्रवर्तन खोला"),
    "enforcement_case_viewed": ("જાહેરાતનો કેસ ખોલ્યો", "विज्ञापन का मामला खोला"),
    "enforcement_case_updated": ("જાહેરાતનો કેસ અપડેટ કર્યો", "विज्ञापन का मामला अपडेट किया"),
    "order_compliance_updated": ("આદેશનું પાલન અપડેટ કર્યું", "आदेश का अनुपालन अपडेट किया"),
    "risk_watchlist": ("જોખમ સૂચિ ખોલી", "जोखिम सूची खोली"),
    "complaint_document_opened": ("ફરિયાદનો દસ્તાવેજ ખોલ્યો", "शिकायत का दस्तावेज़ खोला"),
    "dues_notices": ("લેણાં અને નોટિસ ખોલ્યાં", "बकाया और नोटिस खोले"),
    "qpr_overview": ("ત્રિમાસિક અહેવાલ ખોલ્યા", "तिमाही रिपोर्ट खोलीं"),
    "qpr_filed": ("ત્રિમાસિક અહેવાલ ભર્યો", "तिमाही रिपोर्ट दाखिल की"),
    "orders_to_enforce": ("અમલ કરવાના આદેશો ખોલ્યા", "लागू करने वाले आदेश खोले"),
    "complaint_access_denied": ("ફરિયાદ જોવાનો ઇનકાર", "शिकायत देखने से इनकार"),
    "audit_exported": ("ઓડિટ લોગ ડાઉનલોડ કર્યો", "ऑडिट लॉग डाउनलोड किया"),
    "poc_setting_changed": ("POC સેટિંગ બદલ્યું", "POC सेटिंग बदली"),
    "test_cases_generated": ("ટેસ્ટ પ્રશ્નો બનાવ્યા", "टेस्ट प्रश्न बनाए"),
    "test_cases_imported": ("ટેસ્ટ પ્રશ્નો આયાત કર્યા", "टेस्ट प्रश्न आयात किए"),
    "test_case_added": ("ટેસ્ટ પ્રશ્ન ઉમેર્યો", "टेस्ट प्रश्न जोड़ा"),
    "test_case_from_feedback": ("પ્રતિસાદને ટેસ્ટ પ્રશ્ન બનાવ્યો", "प्रतिक्रिया को टेस्ट प्रश्न बनाया"),
    "test_run_started": ("ટેસ્ટ સેટ ચલાવ્યો", "टेस्ट सेट चलाया"),
    "circular_uploaded": ("પરિપત્ર અપલોડ કર્યો", "परिपत्र अपलोड किया"),
    "circular_updated": ("પરિપત્ર બદલ્યો", "परिपत्र बदला"),
    "circular_deleted": ("પરિપત્ર કાઢી નાખ્યો", "परिपत्र हटाया"),
    "chat_reply": ("ચેટમાં પ્રશ્નનો જવાબ આપ્યો", "चैट में प्रश्न का जवाब दिया"),
    "district_list": ("જિલ્લાના પ્રોજેક્ટની યાદી", "जिले के प्रोजेक्ट की सूची"),
    "locality_list": ("વિસ્તારના પ્રોજેક્ટની યાદી", "इलाके के प्रोजेक्ट की सूची"),
    "project_report": ("પ્રોજેક્ટ રિપોર્ટ ખોલ્યો", "प्रोजेक्ट रिपोर्ट खोली"),
    "agent_list": ("એજન્ટોની યાદી", "एजेंटों की सूची"),
    "agreement_checked": ("કરાર તપાસ્યો", "अनुबंध जाँचा"),
    "ad_reported": ("જાહેરાતની જાણ કરી", "विज्ञापन की सूचना दी"),
    "circular_answer": ("પરિપત્રમાંથી જવાબ આપ્યો", "परिपत्र से जवाब दिया"),
    "order_lookup": ("આદેશ શોધ્યો", "आदेश खोजा"),
    "complaint_status": ("ફરિયાદ શોધી", "शिकायत खोजी"),
    "list_complaints": ("ફરિયાદોની યાદી", "शिकायतों की सूची"),
    "complaint_document_added": ("ફરિયાદમાં દસ્તાવેજ ઉમેર્યો", "शिकायत में दस्तावेज़ जोड़ा"),
    "watch_added": ("પ્રોજેક્ટ પર નજર શરૂ કરી", "प्रोजेक्ट की निगरानी शुरू की"),
    "watch_removed": ("પ્રોજેક્ટ પર નજર બંધ કરી", "प्रोजेक्ट की निगरानी बंद की"),
}
ROLE_I18N = {"officer": ("GUJRERA અધિકારી", "GUJRERA अधिकारी"), "citizen": ("ઘર ખરીદનાર", "घर खरीदार"),
             "developer": ("પ્રમોટર", "प्रमोटर"), "agent": ("એજન્ટ", "एजेंट"),
             "not logged in": ("લૉગિન વગર", "बिना लॉगिन")}


def _i18n(en: str, pair: tuple[str, str] | None) -> dict[str, str]:
    return {"en": en, "gu": pair[0], "hi": pair[1]} if pair else {"en": en, "gu": en, "hi": en}
CATEGORIES = {
    "refusal": "Refusals", "report": "Reports", "data": "Data loads", "admin": "Account changes",
    "login": "Logins", "work": "Officer work", "public": "Citizen and public use",
}


def _category(action: str) -> str:
    return ACTIONS.get(action, ("public", ""))[0]


def _label(action: str) -> str:
    return ACTIONS.get(action, ("", action.replace("_", " ").capitalize()))[1] or action.replace("_", " ").capitalize()


def require_admin(repo: Repository) -> None:
    if repo.p.role != "officer" or repo.p.district_scope:
        raise AccessDenied("Administration is for state-level GUJRERA officers.")


def _me(repo: Repository) -> User | None:
    return repo.s.get(User, repo.p.user_id) if repo.p.user_id else None


def _districts(repo: Repository) -> list[str]:
    from gujrera.analytics.reports import DISTRICT_WORDS

    known = set(DISTRICT_WORDS.values()) | {d for (d,) in repo.s.execute(select(Project.district).distinct()) if d}
    return sorted(known)


def _user_dict(repo: Repository, u: User) -> dict[str, Any]:
    org = None
    if u.promoter_id:
        p = repo.s.get(Promoter, u.promoter_id)
        org = p.name if p else None
    elif u.agent_id:
        a = repo.s.get(Agent, u.agent_id)
        org = a.reg_no if a else None
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role),
            "role_label_i18n": _i18n(ROLE_LABELS.get(u.role, u.role), ROLE_I18N.get(u.role)), "district_scope": u.district_scope, "organisation": org,
            "is_active": u.is_active is not False, "is_demo": bool(u.is_mock),
            "created_at": u.created_at.isoformat(timespec="minutes") if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat(timespec="minutes") if u.last_login_at else None}


# ------------------------------------------------------------------ users
def list_users(repo: Repository, role: str | None = None, q: str | None = None) -> dict[str, Any]:
    require_admin(repo)
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(like), func.lower(User.display_name).like(like)))
    users = repo.s.scalars(stmt.order_by(User.role, User.district_scope, User.username)).all()
    counts = dict(repo.s.execute(select(User.role, func.count()).group_by(User.role)).all())
    return {"users": [_user_dict(repo, u) for u in users], "counts": counts, "districts": _districts(repo),
            "creatable_roles": list(CREATABLE_ROLES)}


def _temp_password() -> str:
    return secrets.token_urlsafe(9)  # 12 characters, shown once


def create_user(repo: Repository, username: str, display_name: str, role: str,
                district_scope: str | None) -> dict[str, Any]:
    require_admin(repo)
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError("Username: 3–40 characters, lower-case letters, digits, '.', '_' or '-'.")
    if role not in CREATABLE_ROLES:
        raise ValueError("Create officer or citizen accounts here; promoter and agent accounts are linked to "
                         "registry records.")
    if repo.s.scalar(select(User).where(User.username == username)):
        raise ValueError(f"The username {username} is taken.")
    scope = (district_scope or "").strip() or None
    if role != "officer":
        scope = None
    elif scope and scope not in _districts(repo):
        raise ValueError(f"Unknown district {scope!r}.")
    password = _temp_password()
    user = User(username=username, display_name=(display_name or "").strip()[:200] or username, role=role,
                district_scope=scope, password_hash=hash_password(password), is_mock=False, is_active=True,
                token_version=0, created_at=datetime.now(), preferred_lang="gu")
    repo.s.add(user)
    repo.s.flush()
    repo._audit("user_created", {"username": username, "role": role, "district_scope": scope or "statewide"})
    return {"user": _user_dict(repo, user), "temporary_password": password}


def _statewide_admins(repo: Repository) -> int:
    return repo.s.scalar(select(func.count()).select_from(User).where(
        User.role == "officer", User.district_scope.is_(None), User.is_active.is_not(False))) or 0


def update_user(repo: Repository, user_id: int, *, display_name: str | None = None,
                district_scope: str | None = None, set_scope: bool = False,
                is_active: bool | None = None) -> dict[str, Any]:
    require_admin(repo)
    user = repo.s.get(User, user_id)
    if user is None:
        raise ValueError("No such account.")
    me = _me(repo)
    changes: dict[str, Any] = {}
    if display_name is not None and display_name.strip() and display_name.strip() != user.display_name:
        user.display_name = display_name.strip()[:200]
        changes["display_name"] = user.display_name
    if set_scope:
        if user.role != "officer":
            raise ValueError("Only officer accounts have a district.")
        scope = (district_scope or "").strip() or None
        if scope and scope not in _districts(repo):
            raise ValueError(f"Unknown district {scope!r}.")
        if scope and user.district_scope is None:
            if me and me.id == user.id:
                raise ValueError("You cannot give your own account a district: ask another state admin.")
            if _statewide_admins(repo) <= 1:
                raise ValueError("This is the last statewide officer; it cannot be given a district.")
        if scope != user.district_scope:
            user.district_scope = scope
            user.token_version = (user.token_version or 0) + 1  # the new scope applies from the next login
            changes["district_scope"] = scope or "statewide"
    if is_active is not None and is_active != (user.is_active is not False):
        if not is_active:
            if me and me.id == user.id:
                raise ValueError("You cannot disable your own account.")
            if user.role == "officer" and user.district_scope is None and _statewide_admins(repo) <= 1:
                raise ValueError("This is the last active statewide officer; it cannot be disabled.")
            user.token_version = (user.token_version or 0) + 1  # end its sessions now
        user.is_active = is_active
        changes["is_active"] = is_active
    repo.s.flush()
    if changes:
        repo._audit("user_updated", {"username": user.username, **changes})
    return {"user": _user_dict(repo, user)}


def reset_password(repo: Repository, user_id: int) -> dict[str, Any]:
    require_admin(repo)
    user = repo.s.get(User, user_id)
    if user is None:
        raise ValueError("No such account.")
    password = _temp_password()
    user.password_hash = hash_password(password)
    user.token_version = (user.token_version or 0) + 1
    repo.s.flush()
    repo._audit("password_reset", {"username": user.username})
    return {"user": _user_dict(repo, user), "temporary_password": password}


# ------------------------------------------------------------------ audit log
def _utc_start(d: date) -> datetime:
    """Local midnight of a day, as the naive UTC time the audit log stores."""
    local = datetime.combine(d, datetime.min.time()).astimezone()
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _local(at: datetime) -> str:
    return at.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def _filtered(repo: Repository, *, username: str | None, role: str | None, category: str | None,
              action: str | None, since: date | None, until: date | None, q: str | None):
    stmt = select(AuditLog, User.username).outerjoin(User, User.id == AuditLog.user_id)
    if username:
        stmt = stmt.where(or_(User.username == username.strip().lower(),
                              AuditLog.detail.like(f'%"username": "{username.strip().lower()}"%')))
    if role:
        stmt = stmt.where(AuditLog.role == role)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if category:
        names = [a for a, (c, _l) in ACTIONS.items() if c == category]
        stmt = stmt.where(AuditLog.action.in_(names)) if category != "public" else stmt.where(
            AuditLog.action.in_(names) | AuditLog.action.not_in(list(ACTIONS)))  # labelled public, or unlabelled
    if since:
        stmt = stmt.where(AuditLog.at >= _utc_start(since))
    if until:
        stmt = stmt.where(AuditLog.at < _utc_start(until + timedelta(days=1)))
    if q:
        stmt = stmt.where(AuditLog.detail.like(f"%{q.strip()[:100]}%"))
    return stmt


def _entry(row: AuditLog, username: str | None) -> dict[str, Any]:
    try:
        detail = json.loads(row.detail) if row.detail else {}
    except json.JSONDecodeError:
        detail = {"text": row.detail}
    who = username or (detail.get("username") if row.action.startswith("login") else None)
    signed_in = row.user_id is not None
    return {"id": row.id, "at": _local(row.at), "user": who or (None if signed_in else "visitor"),
            "role": row.role if signed_in else "not logged in", "action": row.action, "label": _label(row.action),
            "label_i18n": _i18n(_label(row.action), ACTION_I18N.get(row.action)),
            "role_i18n": _i18n(row.role if signed_in else "not logged in",
                               ROLE_I18N.get(row.role if signed_in else "not logged in")),
            "category": _category(row.action), "detail": detail}


def audit_log(repo: Repository, *, username: str | None = None, role: str | None = None, category: str | None = None,
              action: str | None = None, since: date | None = None, until: date | None = None, q: str | None = None,
              limit: int = 100, offset: int = 0) -> dict[str, Any]:
    require_admin(repo)
    since = since or (date.today() - timedelta(days=7))
    stmt = _filtered(repo, username=username, role=role, category=category, action=action, since=since,
                     until=until, q=q)
    total = repo.s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = repo.s.execute(stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc())
                          .limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    # summary of the same window, all categories
    window = _filtered(repo, username=username, role=role, category=None, action=None, since=since, until=until, q=q)
    sub = window.subquery()
    by_action = dict(repo.s.execute(select(sub.c.action, func.count()).group_by(sub.c.action)).all())
    by_category: dict[str, int] = {}
    for a, n in by_action.items():
        by_category[_category(a)] = by_category.get(_category(a), 0) + n
    users = repo.s.scalar(select(func.count(func.distinct(sub.c.user_id))))
    return {
        "since": since.isoformat(), "until": until.isoformat() if until else None, "total": total,
        "entries": [_entry(r, u) for r, u in rows],
        "summary": {"by_category": by_category, "distinct_users": users,
                    "failed_logins": by_action.get("login_failed", 0) + by_action.get("login_locked", 0)
                    + by_action.get("login_disabled", 0),
                    "out_of_scope": by_action.get("analytics_out_of_scope", 0),
                    "write_attempts": by_action.get("analytics_write_refused", 0),
                    "blocked_queries": by_action.get("analytics_refused", 0),
                    "access_denied": by_action.get("access_denied", 0)},
        "categories": CATEGORIES,
        "actions": sorted({*by_action, *ACTIONS}),
    }


def audit_csv(repo: Repository, **filters: Any) -> str:
    require_admin(repo)
    data = audit_log(repo, **filters, limit=500)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["time", "user", "role", "category", "action", "what happened", "detail"])
    for e in data["entries"]:
        w.writerow([e["at"], e["user"] or "", e["role"], e["category"], e["action"], e["label"],
                    json.dumps(e["detail"], ensure_ascii=False)])
    repo._audit("audit_exported", {"rows": len(data["entries"])})
    return out.getvalue()
