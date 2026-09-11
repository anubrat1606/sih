"""Tests run against a real PostgreSQL. They are skipped, never faked, when one
is unavailable -- a passing test suite that silently ran against a stub would be
exactly the kind of comfortable fiction this project refuses everywhere else.

    export DATABASE_URL=postgresql://localhost/satyapramana_test
"""
import os

import pytest

psycopg = pytest.importorskip("psycopg")

from satyapramana_store import connect, migrate  # noqa: E402
from satyapramana_store.auth.models import Role  # noqa: E402
from satyapramana_store.auth.store import create_user  # noqa: E402
from satyapramana_store.auth.tokens import issue_token  # noqa: E402

# Ephemeral, test-only, clearly not a production secret -- only needs to be
# stable within one test process so tokens issued and verified in the same
# run agree. Set via setdefault so a real value in the environment (e.g. a
# developer testing against a deployed JWT_SECRET) still wins.
os.environ.setdefault("SATYAPRAMANA_JWT_SECRET", "test-secret-not-for-production-32chars+")


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
        for t in ("rule_packs", "raw_responses"):
            cur.execute(f"DROP TRIGGER IF EXISTS {t}_no_mutate ON {t}")
            cur.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
        cur.execute("DROP TABLE IF EXISTS proj_verdicts, proj_collusion, "
                    "proj_evidence, bidder_in_tender, raw_responses, "
                    "rule_packs, users CASCADE")
        cur.execute("DROP TRIGGER IF EXISTS events_no_mutate ON events")
        cur.execute("DROP TRIGGER IF EXISTS events_no_truncate ON events")
        cur.execute("DROP TABLE IF EXISTS events CASCADE")
    migrate(c)
    yield c
    c.close()


def auth_headers(conn, username: str = "officer_1", role: Role = Role.SENIOR_OFFICER) -> dict[str, str]:
    """Creates a real user (or reuses one already created with this username
    in this test's conn) and returns a real, verifiable Authorization header
    -- the same shape any real client sends. Tests exercising role-gated
    endpoints pass role=Role.OFFICER explicitly to prove the gate actually
    refuses a too-low role; everything else defaults to SENIOR_OFFICER so
    existing call sites that don't care about roles don't all need updating
    to think about them.
    """
    from satyapramana_store.auth.store import get_user_by_username
    user = get_user_by_username(conn, username)
    if user is None:
        user = create_user(conn, username, "correct horse battery staple",
                           display_name=username, role=role)
    token = issue_token(user, os.environ["SATYAPRAMANA_JWT_SECRET"])
    return {"Authorization": f"Bearer {token}"}
