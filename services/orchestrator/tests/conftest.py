"""Tests run against a real PostgreSQL. They are skipped, never faked, when one
is unavailable -- a passing test suite that silently ran against a stub would be
exactly the kind of comfortable fiction this project refuses everywhere else.

    export DATABASE_URL=postgresql://localhost/satyapramana_test
"""
import os

import pytest

psycopg = pytest.importorskip("psycopg")

from satyapramana_store import connect, migrate  # noqa: E402


@pytest.fixture(scope="session")
def dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set; these tests require a real PostgreSQL")
    return url


@pytest.fixture()
def conn(dsn):
    c = connect(dsn)
    with c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS proj_verdicts, proj_collusion, "
                    "bidder_in_tender CASCADE")
        cur.execute("DROP TRIGGER IF EXISTS events_no_mutate ON events")
        cur.execute("DROP TRIGGER IF EXISTS events_no_truncate ON events")
        cur.execute("DROP TABLE IF EXISTS events CASCADE")
    migrate(c)
    yield c
    c.close()
