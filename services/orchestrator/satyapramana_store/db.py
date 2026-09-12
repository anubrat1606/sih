"""Connection helper. No ORM: the schema is small, the SQL is the specification,
and an ORM here would put a layer between the audit claim and what runs."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _dsn(dsn: str | None = None) -> str:
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set. This service refuses to start against an "
            "implicit default -- see services/orchestrator/README.md"
        )
    return dsn


def connect(dsn: str | None = None):
    """One raw connection, unpooled -- for one-off work outside a request
    (startup migration/bootstrap, the test suite's own fixtures). Request
    handling goes through the pool below instead; see `db()` in app.py."""
    return psycopg.connect(_dsn(dsn), autocommit=True)


# A pooled connection is checked out and returned per request instead of a
# fresh psycopg.connect() every time -- opening a connection is a real,
# measurable cost (TCP + TLS + Postgres auth), and every one of this app's
# routes hit the database at least once, over a network to a remote Postgres.
# Built lazily/without opening (open=False) rather than in this module's
# import: opening at import time can start the pool's background thread
# before the ASGI server is actually ready, which psycopg_pool itself warns
# against. app.py's lifespan calls open_pool()/close_pool() around the
# app's actual up-time.
_pool: ConnectionPool | None = None


def open_pool(dsn: str | None = None) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            _dsn(dsn), open=False, min_size=1, max_size=10,
            kwargs={"autocommit": True},
        )
        _pool.open()
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Connection pool not open -- open_pool() must run "
                           "at app startup (see app.py's lifespan)")
    return _pool


def migrate(conn) -> list[str]:
    """Apply sql/*.sql in filename order. Idempotent."""
    applied = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text())
        applied.append(path.name)
    return applied
