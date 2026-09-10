"""Connection helper. No ORM: the schema is small, the SQL is the specification,
and an ORM here would put a layer between the audit claim and what runs."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def connect(dsn: str | None = None):
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set. This service refuses to start against an "
            "implicit default -- see services/orchestrator/README.md"
        )
    return psycopg.connect(dsn, autocommit=True)


def migrate(conn) -> list[str]:
    """Apply sql/*.sql in filename order. Idempotent."""
    applied = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text())
        applied.append(path.name)
    return applied
