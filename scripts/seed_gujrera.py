"""Build the GUJRERA prototype database.

    python scripts/seed_gujrera.py                      # fresh DB with mock data
    python scripts/seed_gujrera.py --csv public.csv     # also import public project records
    python scripts/seed_gujrera.py --no-mock --csv public.csv
    python scripts/seed_gujrera.py --add-ad-reports     # only add the starting set of reported ads

The database location comes from GUJRERA_DB_URL (default
data/gujrera/gujrera.sqlite). The existing database is dropped and rebuilt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gujrera.config import get_gujrera_settings  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.csv_import import import_projects_csv  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from gujrera.db.models import AdReport  # noqa: E402
from gujrera.db.session import session_factory as Session_  # noqa: E402
from gujrera.enforcement import ensure_tables, seed_reports  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-url", default=None, help="override GUJRERA_DB_URL")
    ap.add_argument("--seed", type=int, default=None, help="mock data seed (default GUJRERA_MOCK_SEED)")
    ap.add_argument("--no-mock", action="store_true", help="skip mock data")
    ap.add_argument("--csv", type=Path, action="append", default=[], help="public projects CSV to import")
    ap.add_argument("--add-ad-reports", action="store_true",
                    help="keep the database; only add the starting set of reported ads (enforcement cases)")
    args = ap.parse_args()

    settings = get_gujrera_settings()
    engine = make_engine(args.db_url)
    if args.add_ad_reports:
        ensure_tables(engine)
        with Session_(engine)() as s:
            if s.scalar(select(func.count()).select_from(AdReport)):
                print("Reported ads already present; nothing added.")
                return 0
            print(seed_reports(s))
        return 0
    init_db(engine, drop=True)
    Session = session_factory(engine)
    print(f"Database: {engine.url}")

    if not args.no_mock:
        with Session() as s:
            counts = generate(s, MockConfig(seed=args.seed if args.seed is not None else settings.GUJRERA_MOCK_SEED))
        print("Mock data (is_mock=1):")
        for table, n in counts.items():
            print(f"  {table:<18}{n:>6}")
        with Session() as s:
            for table, n in seed_reports(s).items():
                print(f"  {table:<18}{n:>6}")

    failed = False
    for path in args.csv:
        with Session() as s:
            rep = import_projects_csv(s, path)
        print(f"{path}: {rep.inserted} inserted, {rep.updated} updated, {len(rep.errors)} errors")
        for err in rep.errors:
            print(f"  {err}")
        failed |= bool(rep.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
