"""Engine and session helpers.

``make_readonly_engine`` gives the analytics layer a connection that cannot
write, independent of any SQL checks done above it:
- SQLite: the file is opened with ``mode=ro``.
- PostgreSQL: every transaction is set READ ONLY; production should also use a
  database role that only has SELECT on the analytics views.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from gujrera.config import get_gujrera_settings
from gujrera.db.models import Base
from gujrera.db.views import ANALYTICS_VIEWS, create_views


def make_engine(url: str | None = None) -> Engine:
    url = url or get_gujrera_settings().GUJRERA_DB_URL
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    file_sqlite = parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:")
    # Wait up to 30 s for another writer instead of failing after 5 s (many users at once).
    # SQLite connections are cheap; a request waiting on the LLM keeps its connection, so allow many.
    engine = (create_engine(url, connect_args={"timeout": 30}, pool_size=20, max_overflow=200, pool_timeout=60)
              if file_sqlite else create_engine(url))
    if parsed.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys = ON")
            if file_sqlite:
                # WAL: readers never block the writer and the writer never blocks readers.
                dbapi_conn.execute("PRAGMA journal_mode = WAL")
                dbapi_conn.execute("PRAGMA synchronous = NORMAL")
    return engine


def make_readonly_engine(url: str | None = None) -> Engine:
    url = url or get_gujrera_settings().GUJRERA_DB_URL
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        if parsed.database in (None, "", ":memory:"):
            raise ValueError("A read-only engine needs a file-backed SQLite database")
        path = Path(parsed.database).resolve().as_posix()
        return create_engine(f"sqlite:///file:{path}?mode=ro&uri=true")

    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _read_only(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        cur.close()

    return engine


def init_db(engine: Engine, *, drop: bool = False) -> None:
    """Create tables and reporting views."""
    with engine.begin() as conn:
        if drop:
            for name in reversed(ANALYTICS_VIEWS):
                conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
            Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        create_views(conn)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
