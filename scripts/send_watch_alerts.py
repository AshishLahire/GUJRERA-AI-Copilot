"""Show the alerts each buyer would receive for the projects they watch (SMS/WhatsApp hand-off).

    python scripts/send_watch_alerts.py --since 2026-10-01

Nothing is sent: the prototype stores no phone numbers. In the PoC, GUJRERA's SMS or WhatsApp gateway
implements gujrera.watch.Notifier and this runs on a schedule (e.g. daily).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from gujrera.db.session import make_engine, session_factory  # noqa: E402
from gujrera.enforcement import ensure_tables  # noqa: E402
from gujrera.watch import MockNotifier, digest  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, default=date.today() - timedelta(days=7))
    args = ap.parse_args()
    engine = make_engine()
    ensure_tables(engine)
    notifier = MockNotifier()
    with session_factory(engine)() as s:
        n = digest(s, notifier, since=args.since)
    print(f"{n} buyer(s) would be notified of alerts since {args.since}:")
    for user, lines in notifier.sent:
        print(f"\n{user}:")
        for line in lines:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
