"""Load public GUJRERA records from downloaded files into a separate database.

    python scripts/import_gujrera_public.py projects.xlsx agents.csv
    python scripts/import_gujrera_public.py --fresh surat_projects.json
    python scripts/import_gujrera_public.py --kind agent agents.xlsx

Files may be CSV, Excel (.xlsx) or JSON, as downloaded (see gujrera/ingest/public_import.py for the
column names and date formats understood). Projects and agents are told apart automatically from
their registration numbers (PR/... or AG/...); use --kind to force one.

The records go into data/gujrera/gujrera_public.sqlite by default, so the demo database is never
touched. Running again adds new records and updates existing ones; --fresh starts the file over.
A few logins are created (password = GUJRERA_DEMO_PASSWORD) so officer reports can be used on the
imported data: officer_state (statewide), officer_<district> for the largest district, citizen_01.

Then start the app on it:

    powershell -ExecutionPolicy Bypass -File scripts\\run_gujrera.ps1 -Db data\\gujrera\\gujrera_public.sqlite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from gujrera.db.models import Agent, Project, Promoter, User  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.enforcement import ensure_tables  # noqa: E402
from gujrera.ingest.public_import import DEFAULT_SOURCE, import_file  # noqa: E402

DEFAULT_DB = ROOT / "data" / "gujrera" / "gujrera_public.sqlite"


def ensure_logins(s, top_districts: int = 3) -> list[str]:
    """Demo logins for the imported data: a statewide officer, a buyer, and an officer for each of the largest
    districts. Only adds the ones missing, so re-running an import keeps existing accounts and passwords."""
    from gujrera.auth import hash_password
    from gujrera.config import get_gujrera_settings

    have = set(s.scalars(select(User.username)))
    tops = [d for d, _ in s.execute(select(Project.district, func.count()).group_by(Project.district)
                                    .order_by(func.count().desc()).limit(top_districts)).all()]
    wanted = [("officer_state", "officer", None, "en", "GUJRERA officer (statewide)"),
              ("citizen_01", "citizen", None, "gu", "Demo buyer 01")]
    wanted += [(f"officer_{d.lower().replace(' ', '_')}", "officer", d, "gu", f"GUJRERA officer ({d})") for d in tops]
    pw = hash_password(get_gujrera_settings().GUJRERA_DEMO_PASSWORD.get_secret_value())
    created = []
    for name, role, scope, lang, display in wanted:
        if name in have:
            continue
        s.add(User(username=name, role=role, district_scope=scope, preferred_lang=lang, display_name=display,
                   password_hash=pw, is_mock=True))
        created.append(name)
    s.commit()
    return created


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="downloaded .csv, .xlsx or .json files")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database file (default {DEFAULT_DB.relative_to(ROOT)})")
    ap.add_argument("--fresh", action="store_true", help="delete the imported records and start over")
    ap.add_argument("--kind", choices=("project", "agent"), help="force the record type (default: detect)")
    ap.add_argument("--source-url", default=DEFAULT_SOURCE,
                    help="page the files came from, cited when a row has no link of its own")
    args = ap.parse_args()

    demo = (ROOT / "data" / "gujrera" / "gujrera.sqlite").resolve()
    if args.db.resolve() == demo:
        print("Refusing to import into the demo database; choose another --db file.")
        return 2
    args.db.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(f"sqlite:///{args.db.resolve().as_posix()}")
    init_db(engine, drop=args.fresh)
    ensure_tables(engine)
    Session = session_factory(engine)
    print(f"Database: {args.db}")

    failed = False
    for path in args.files:
        if not path.exists():
            print(f"{path}: file not found")
            failed = True
            continue
        with Session() as s:
            try:
                reports = import_file(s, path, kind=args.kind, source_url=args.source_url)
            except ValueError as exc:
                print(f"{path}: {exc}")
                failed = True
                continue
        for rep in reports:
            label = f"{path.name} [{rep.sheet}]" if rep.sheet and rep.sheet != path.name else path.name
            print(f"{label}: {rep.rows} {rep.kind or 'unknown'} rows -> {rep.inserted} added, {rep.updated} updated, "
                  f"{len(rep.errors)} with problems")
            if rep.unmatched_columns:
                print(f"  columns not used: {', '.join(rep.unmatched_columns)}")
            for err in rep.errors[:20]:
                print(f"  {err}")
            if rep.no_promoter:
                print(f"  note: {rep.no_promoter} projects have no promoter name in the file; they are listed under "
                      "'Promoter not in imported records' and the ad check does not compare promoter names for them")
            for w in rep.warnings[:5]:
                print(f"  note: {w}")
            if len(rep.warnings) > 5:
                print(f"  note: ... and {len(rep.warnings) - 5} more rows like this")
            if len(rep.errors) > 20:
                print(f"  ... and {len(rep.errors) - 20} more")
            failed |= bool(rep.errors) and not (rep.inserted or rep.updated)

    with Session() as s:
        created = ensure_logins(s)
        n_proj = s.scalar(select(func.count()).select_from(Project))
        n_prom = s.scalar(select(func.count()).select_from(Promoter))
        n_agent = s.scalar(select(func.count()).select_from(Agent))
        districts = s.execute(select(Project.district, func.count()).group_by(Project.district)
                              .order_by(func.count().desc())).all()
    print(f"\nNow in the database: {n_proj} projects, {n_prom} promoters, {n_agent} agents")
    if districts:
        print("By district: " + ", ".join(f"{d} {n}" for d, n in districts[:10]))
    if created:
        print("Logins created (demo password): " + ", ".join(created))
    print(f"\nRun the app on it:\n  powershell -ExecutionPolicy Bypass -File scripts\\run_gujrera.ps1 -Db {args.db}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
