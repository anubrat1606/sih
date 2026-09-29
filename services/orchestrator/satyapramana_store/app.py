"""FastAPI orchestrator.

Replaces the Express/Mongo layer in /backend. Orchestration only: it calls the
extraction service, drives the adapter layer, folds projections, and serves read
models. It holds no AI logic and no verification logic of its own.

Every state change goes through `append()`. There is no other way to change
compliance state, because there is no code path that writes a verdict directly.
"""
from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any

import httpx
import jwt as _jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from satyapramana.metrics import Constants, RequirementResult, compute
from satyapramana.predicates import EvaluationContext
from satyapramana.risk import ConflictSignals, classify
from satyapramana.rulepack import derived_bindings
from satyapramana.verdicts import Channel, Obligation, Tier, Verdict

from .adapters import Registry, VerificationRequest, failure_to_judgement
from .adapters.base import Basis, Failure, FailureCode, LawfulBasis
from .auth import Role, User, decode_token, issue_token, role_at_least
from .auth import store as auth_store
from .db import close_pool, connect, get_pool, migrate, open_pool
from .decide import fuse_and_evaluate
from .events import Actor, append, export_jsonl, verify_chain
from .evidence import ProjectionResolver, fold_evidence_as_of, rebuild_evidence
from .explain import Unavailable
from .extract import ingest_document, read_pdf
from .extract.ingest import INGEST, read_document, store_document
from .requirement_types import requirement_type_catalog
from .tender_intelligence import Unavailable as DecomposeUnavailable
from .projections import (
    collusion_clusters, collusion_clusters_as_of, fold_verdicts_as_of,
    provenance_trail, rebuild_projections, rebuild_projections_for_bidder,
)
from .reporting.bid_autopsy import autopsy
from .reporting.blocker_summary import blocker_summary
from .reporting.compliance_repair import repair_plan
from .reporting.csv_export import bidders_to_csv
from .reporting.dossier import build_dossier, render_dossier_text
from .reporting.evidence_graph import build_evidence_graph
from .reporting.tender_report import render_tender_report_text, tender_report
from .rulepacks import NotAdoptable, active_pack, active_pack_as_of, adopt, validate_only

@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("SATYAPRAMANA_MIGRATE_ON_START") == "1":
        conn = connect()
        migrate(conn)
        # Deployment-friendly bootstrap: creates the first ADMIN account from
        # env vars if one doesn't exist yet and both are set. A no-op
        # everywhere neither is configured -- see auth/store.py.
        auth_store.bootstrap_admin(conn)
        conn.close()
    open_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    lifespan=lifespan,
    title="SATYAPRAMĀṆA orchestrator",
    description=(
        "Bid compliance verification. Every verdict traces to a page number, an "
        "authority, a rule version and a timestamp. Where an authority cannot be "
        "reached the answer is UNKNOWN with a machine-readable reason -- never a "
        "simulated response."
    ),
    version="0.1.0",
)

# The frontend (Vite dev server, a different origin) calls this API directly
# from the browser -- without this, every request is blocked by the browser's
# CORS policy before it ever reaches a route, which no server-side test using
# a plain HTTP client (curl, node fetch, the FastAPI TestClient) would ever
# catch, since none of them enforce CORS the way a real browser does.
# allow_credentials stays False even now that real auth exists: a session
# token travels in an Authorization header, set explicitly by the frontend's
# own fetch call, never an automatically-sent cookie -- there is nothing here
# for a credentialed CORS policy to protect against.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.environ.get("SATYAPRAMANA_FRONTEND_ORIGIN", "http://localhost:5173"),
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM = Actor("SYSTEM", "orchestrator")
REGISTRY = Registry.from_file()
CONSTANTS = Constants()

# Unset in an unconfigured deployment -- same honesty pattern as every other
# credential in this system (Sandbox.co.in, Gemini): auth endpoints stay up
# and answer 503 rather than the app either refusing to start or, worse,
# signing tokens with a fabricated fallback secret.
JWT_SECRET = os.environ.get("SATYAPRAMANA_JWT_SECRET")

# The whole plug-in point (docs/ADAPTERS.md): a real adapter takes over the
# capabilities its manifest declares, and nothing else changes. With no
# SATYAPRAMANA_SANDBOX_* credentials set this is a no-op and PAN_STATUS /
# GST_STATUS stay on the honest UnconfiguredAdapter.
from .adapters.sandbox_co_in import build_from_env as _build_sandbox_adapters  # noqa: E402
for _adapter in _build_sandbox_adapters():
    REGISTRY.register(_adapter)

# UDYAM_STATUS (round 11): Sandbox.co.in's own catalog doesn't offer it
# (confirmed round 10, still true), but Attestr's does -- a second,
# separate vendor account, same plug-in shape. With no
# SATYAPRAMANA_ATTESTR_AUTH_TOKEN set this is a no-op and UDYAM_STATUS
# stays on the honest NullAdapter declared in capability_registry.json.
from .adapters.attestr import build_from_env as _build_attestr_adapters  # noqa: E402
for _adapter in _build_attestr_adapters():
    REGISTRY.register(_adapter)

# DigiLocker (round 10, PS26100 point 8) doesn't fit the loop-callable
# VerificationAdapter shape the four adapters above use -- it's a real
# bidder-consent redirect flow, not a server-to-server lookup -- so it gets
# its own session object for the dedicated endpoints below, plus a
# placeholder adapter registered purely so DIGILOCKER_DOCUMENT shows up
# honestly in the coverage report, same mechanism as every other
# capability. Same credential gate as every other Sandbox.co.in product:
# unset and this stays AWAITING_CREDENTIALS on the static registry entry.
from .adapters import digilocker as _digilocker  # noqa: E402
DIGILOCKER_SESSION = _digilocker.build_from_env()
if DIGILOCKER_SESSION is not None:
    REGISTRY.register(_digilocker.DigilockerPlaceholderAdapter())

# Same plug-in shape as the verification adapters above: with no
# SATYAPRAMANA_GEMINI_API_KEY set, EXPLAINER stays on the honest
# UnconfiguredExplainer and /bidders/{id}/explain returns Unavailable rather
# than a fabricated narrative.
from .explain import build_from_env as _build_explainer  # noqa: E402
EXPLAINER = _build_explainer()

# Same plug-in shape again: with no SATYAPRAMANA_GEMINI_API_KEY set,
# DECOMPOSER stays on the honest UnconfiguredDecomposer and
# /tenders/{id}/decompose returns Unavailable -- never a fabricated
# requirement list.
from .tender_intelligence import build_from_env as _build_decomposer  # noqa: E402
DECOMPOSER = _build_decomposer()


def db():
    """A connection checked out of the pool for the request's duration, then
    returned (not closed) -- see db.py. Tests bypass this entirely via
    app.dependency_overrides[db], so this change has no effect on them."""
    with get_pool().connection() as conn:
        yield conn


# --- request models -----------------------------------------------------------

class TenderIn(BaseModel):
    tender_id: str
    title: str
    issuing_authority: str
    bid_submission_deadline: date | None = None
    description: str | None = None
    #: Issuing department/organization within the authority (e.g. "Materials
    #: Management"), the tender category (e.g. "Goods", "Works", "Services"),
    #: and the notice's own issue date -- all optional, all additive to the
    #: five fields Tender Management originally shipped with.
    department: str | None = None
    category: str | None = None
    issue_date: date | None = None


class BidderIn(BaseModel):
    bidder_id: str
    director_name: str | None = None
    address: str | None = None
    phone: str | None = None
    bank_account: str | None = None


class RulePackIn(BaseModel):
    pack: dict


class EvaluateIn(BaseModel):
    as_of: date | None = None
    bid_submission_date: date


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(QUALIFY|DISQUALIFY)$")
    note: str | None = None


class OverrideIn(BaseModel):
    requirement_id: str
    verdict_after: str = Field(pattern="^(PASS|FAIL|PARTIAL|UNKNOWN)$")
    justification: str = Field(min_length=1)


class DigilockerSessionIn(BaseModel):
    #: Where DigiLocker sends the bidder's browser back to after they grant
    #: or deny consent. The frontend's own callback route -- this backend
    #: never receives the redirect directly, a human's browser does.
    redirect_url: str = Field(min_length=1)


class DeclarationIn(BaseModel):
    requirement_id: str = Field(min_length=1)
    #: What's actually being attested to -- recorded verbatim, not a
    #: boolean flag. An undertaking is the text itself; a checkbox alone
    #: would assert nothing an auditor could later read back.
    declaration_text: str = Field(min_length=1)


class LoginIn(BaseModel):
    username: str
    password: str


class CreateUserIn(BaseModel):
    username: str
    password: str = Field(min_length=8)
    display_name: str
    role: str = Field(pattern="^(BIDDER|OFFICER|SENIOR_OFFICER|ADMIN)$")
    #: Required for role=BIDDER (the bidder record this account acts as),
    #: refused for every other role -- see create_officer_account below.
    bidder_id: str | None = None


# --- authentication -------------------------------------------------------
#
# A session token is a signed JWT (Authorization: Bearer <token>), never a
# cookie -- see the CORS comment above for why. current_user() is the one
# place a token is verified; every endpoint below that needs a real officer
# identity depends on it (or on require_role(), which depends on it in
# turn), rather than trusting a client-supplied officer_id string the way
# every write endpoint used to.

def current_user(authorization: str | None = Header(default=None),
                 conn=Depends(db)) -> User:
    if not JWT_SECRET:
        raise HTTPException(503, "authentication is not configured on this "
                                  "deployment (SATYAPRAMANA_JWT_SECRET is unset)")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = decode_token(token, JWT_SECRET)
    except _jwt.PyJWTError as exc:
        raise HTTPException(401, f"invalid or expired token: {exc}") from exc
    user = auth_store.get_user_by_username(conn, claims["sub"])
    if not user or user.disabled:
        raise HTTPException(401, "account no longer valid")
    return user


def require_role(minimum: Role):
    """A dependency factory, not a dependency -- `Depends(require_role(Role.SENIOR_OFFICER))`
    reads as what it is: this endpoint requires at least that role."""
    def _dependency(user: User = Depends(current_user)) -> User:
        if not role_at_least(user.role, minimum):
            raise HTTPException(403, f"this action requires {minimum.value} or higher; "
                                      f"you are {user.role.value}")
        return user
    return _dependency


def officer_or_self(bidder_id: str, user: User = Depends(current_user)) -> User:
    """For the one endpoint a bidder legitimately calls on their own behalf
    under the officer-shaped path (uploading their own documents): an
    officer may act on any bidder, same as always; a BIDDER account may
    act only where the path's bidder_id matches their own. FastAPI matches
    this dependency's `bidder_id` parameter to the route's path parameter
    of the same name automatically."""
    if role_at_least(user.role, Role.OFFICER):
        return user
    if user.role == Role.BIDDER and user.bidder_id == bidder_id:
        return user
    raise HTTPException(403, "requires an officer account, or the bidder account for this bidder_id")


def current_bidder(user: User = Depends(current_user)) -> User:
    """Not `require_role(Role.BIDDER)`: role_at_least treats BIDDER as a
    floor everything else clears, so an officer or admin token would
    satisfy it -- exactly backwards for an endpoint that must be acting
    AS a specific bidder, not merely cleared to see bidder-shaped data.
    This requires the literal role, and hands back the bidder_id every
    /me/* endpoint below scopes its query to -- a bidder can never read
    another bidder's data by guessing an id in the URL, because these
    endpoints never take one; they only ever use this one."""
    if user.role != Role.BIDDER or not user.bidder_id:
        raise HTTPException(403, "this action requires a bidder account")
    return user


@app.post("/auth/login")
def login(body: LoginIn, conn=Depends(db)) -> dict[str, Any]:
    if not JWT_SECRET:
        raise HTTPException(503, "authentication is not configured on this deployment")
    user = auth_store.verify_login(conn, body.username, body.password)
    if not user:
        # Deliberately identical for "no such user" and "wrong password" --
        # see auth/store.py's verify_login docstring.
        raise HTTPException(401, "invalid username or password")
    token = issue_token(user, JWT_SECRET)
    return {"token": token, "username": user.username,
            "display_name": user.display_name, "role": user.role.value}


@app.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    out = {"username": user.username, "display_name": user.display_name,
           "role": user.role.value}
    if user.role == Role.BIDDER:
        out["bidder_id"] = user.bidder_id
    return out


@app.post("/auth/users", status_code=201)
def create_officer_account(body: CreateUserIn, conn=Depends(db),
                           admin: User = Depends(require_role(Role.ADMIN))) -> dict[str, Any]:
    """ADMIN-only. There is no self-signup for a closed government system --
    an administrator provisions every account, bidders included: round 6
    gives a bidder company its own login the same way an officer gets one,
    never a public sign-up page."""
    role = Role(body.role)
    if role == Role.BIDDER and not body.bidder_id:
        raise HTTPException(422, "role BIDDER requires bidder_id")
    if role != Role.BIDDER and body.bidder_id:
        raise HTTPException(422, "bidder_id is only accepted for role BIDDER")
    if auth_store.get_user_by_username(conn, body.username):
        raise HTTPException(409, f"username {body.username!r} already exists")
    user = auth_store.create_user(conn, body.username, body.password,
                                  body.display_name, role, bidder_id=body.bidder_id)
    out = {"username": user.username, "display_name": user.display_name,
           "role": user.role.value}
    if user.bidder_id:
        out["bidder_id"] = user.bidder_id
    return out


def _user_out(user: User) -> dict[str, Any]:
    out = {"username": user.username, "display_name": user.display_name,
           "role": user.role.value, "disabled": user.disabled}
    if user.bidder_id:
        out["bidder_id"] = user.bidder_id
    if user.created_at:
        out["created_at"] = user.created_at.isoformat()
    return out


@app.get("/auth/users")
def list_accounts(conn=Depends(db),
                  admin: User = Depends(require_role(Role.ADMIN))) -> dict[str, Any]:
    """ADMIN-only account directory -- every account this deployment has,
    provisioned or bidder, disabled or not. There is no path to this list
    for anyone below ADMIN; even a senior officer manages nobody."""
    return {"users": [_user_out(u) for u in auth_store.list_users(conn)]}


@app.post("/auth/users/{username}/disable", status_code=200)
def disable_account(username: str, conn=Depends(db),
                    admin: User = Depends(require_role(Role.ADMIN))) -> dict[str, Any]:
    """A disabled account's session is already refused at current_user() and
    a fresh login already fails at verify_login() -- both existed before
    this route ever gave an admin a way to flip the bit. An admin disabling
    their own only account would strand this deployment with no way back
    in (no self-signup, no password-recovery email), so that one case is
    refused rather than left as a footgun."""
    if username == admin.username:
        raise HTTPException(422, "you cannot disable your own account")
    user = auth_store.set_disabled(conn, username, True)
    if not user:
        raise HTTPException(404, f"no account {username!r}")
    return _user_out(user)


@app.post("/auth/users/{username}/enable", status_code=200)
def enable_account(username: str, conn=Depends(db),
                   admin: User = Depends(require_role(Role.ADMIN))) -> dict[str, Any]:
    user = auth_store.set_disabled(conn, username, False)
    if not user:
        raise HTTPException(404, f"no account {username!r}")
    return _user_out(user)


@app.post("/auth/users/{username}/reset-password", status_code=200)
def reset_password(username: str, conn=Depends(db),
                   _admin: User = Depends(require_role(Role.ADMIN))) -> dict[str, Any]:
    """No self-service recovery exists (no self-signup -- round 6), so this
    is the only way anyone gets back into a forgotten account. Generated
    server-side, never accepted from the request body -- an admin
    resetting someone else's password shouldn't get to choose what it
    becomes, or see it typed into a browser field twice. Returned exactly
    once, here, in the response body; never stored or logged anywhere in
    the clear -- only set_password's hash survives past this call."""
    new_password = secrets.token_urlsafe(12)
    user = auth_store.set_password(conn, username, new_password)
    if not user:
        raise HTTPException(404, f"no account {username!r}")
    return {**_user_out(user), "new_password": new_password}


# --- health and honest capability reporting -----------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "orchestrator"}


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """What this deployment can and cannot verify, stated plainly.

    At v1 most rows read AWAITING_CREDENTIALS. That is rendered rather than
    hidden: handling it with visible integrity is the point, and Verification
    Coverage is honestly 0% until an aggregator account exists.
    """
    rows = REGISTRY.coverage_report()
    live = [r for r in rows if r.get("status") == "LIVE"]
    return {
        "capabilities": rows,
        "live_count": len(live),
        "note": (
            "No capability is LIVE. Every verification will return UNKNOWN with "
            "a machine-readable reason until credentials are configured. No "
            "simulated authority response exists anywhere in this system."
        ) if not live else None,
    }


@app.get("/tenders")
def list_tenders(conn=Depends(db)) -> dict[str, Any]:
    """Every tender_id known to this system -- either explicitly created
    (POST /tenders, with real metadata) or only inferred from having at
    least one registered bidder, the original path from before Tender
    Management existed. Both stay valid: an officer can still just start
    registering bidders on a tender_id with no ceremony, or set one up with
    a title and deadline first. Either way it shows up here."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT tender_id FROM bidder_in_tender
               UNION SELECT tender_id FROM proj_tenders
               ORDER BY tender_id""")
        return {"tenders": [row[0] for row in cur.fetchall()]}


@app.get("/bidder-ids")
def list_bidder_ids(conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Every bidder_id registered anywhere, with which tender(s) -- for the
    admin's bidder-account form (round 6, A5) to offer a real select
    instead of a free-text field an admin could typo. One query, not
    list_tenders() followed by one list_tender_bidders() call per tender
    from the frontend -- the exact N+1 shape docs/PERFORMANCE_AUDIT.md
    already found and fixed elsewhere, not worth reintroducing here."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bidder_id, array_agg(tender_id ORDER BY tender_id) "
            "FROM bidder_in_tender GROUP BY bidder_id ORDER BY bidder_id")
        return {"bidders": [{"bidder_id": b, "tender_ids": t} for b, t in cur.fetchall()]}


@app.post("/tenders", status_code=201)
def create_tender(body: TenderIn, conn=Depends(db),
                  user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Explicit tender creation with real metadata -- title, issuing
    authority, bid submission deadline, description. Any authenticated
    officer may create one; refuses if the tender_id was already explicitly
    created (never silently overwrites another officer's metadata)."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM proj_tenders WHERE tender_id=%s", (body.tender_id,))
        if cur.fetchone():
            raise HTTPException(409, f"tender {body.tender_id!r} already exists")

    rec = append(
        conn, event_type="TENDER_CREATED", actor=Actor("HUMAN", user.username),
        correlation_id=str(uuid.uuid4()), tender_id=body.tender_id,
        payload={
            "title": body.title, "issuing_authority": body.issuing_authority,
            "bid_submission_deadline": body.bid_submission_deadline.isoformat()
                if body.bid_submission_deadline else None,
            "description": body.description, "created_by": user.username,
            "department": body.department, "category": body.category,
            "issue_date": body.issue_date.isoformat() if body.issue_date else None,
        })
    rebuild_projections(conn)
    return {"tender_id": body.tender_id, "seq": rec["seq"], "hash": rec["hash"]}


@app.get("/tenders/{tender_id}")
def get_tender(tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    """This tender's explicit metadata, if it has any. A tender that only
    exists because a bidder registered on it (no POST /tenders was ever
    made) honestly returns null metadata fields, never a guessed title."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT title, issuing_authority, bid_submission_deadline,
                      description, created_by, department, category, issue_date
               FROM proj_tenders WHERE tender_id=%s""",
            (tender_id,))
        row = cur.fetchone()
    if not row:
        return {"tender_id": tender_id, "title": None, "issuing_authority": None,
                "bid_submission_deadline": None, "description": None, "created_by": None,
                "department": None, "category": None, "issue_date": None}
    title, authority, deadline, description, created_by, department, category, issue_date = row
    return {"tender_id": tender_id, "title": title, "issuing_authority": authority,
            "bid_submission_deadline": deadline.isoformat() if deadline else None,
            "description": description, "created_by": created_by,
            "department": department, "category": category,
            "issue_date": issue_date.isoformat() if issue_date else None}


@app.get("/dashboard")
def dashboard(conn=Depends(db), user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The landing view: how many tenders and bidders exist, the system-wide
    risk distribution, the most recent officer decisions, and the same
    honest capability status /capabilities already reports. Authenticated
    (unlike /capabilities) because this exposes real tender and bidder
    counts, not just deployment config.

    Composes list_tenders/list_tender_bidders/capabilities rather than
    recomputing anything -- every number here traces back to a real read
    model this system already serves elsewhere.

    Projections are rebuilt once, up front, for the whole dashboard --
    `rebuild_projections` folds the entire event log for every tenant in one
    pass, so it was never tender-scoped work; running it again for every
    tender in the system on every dashboard load was pure waste.
    """
    rebuild_projections(conn)
    tenders = list_tenders(conn)["tenders"]
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    bidder_count = 0
    flagged_bidder_count = 0
    for tender_id in tenders:
        for b in _list_tender_bidders(tender_id, conn)["bidders"]:
            bidder_count += 1
            risk_counts[b["risk"]["level"]] += 1
            if b.get("collusion", {}).get("flagged"):
                flagged_bidder_count += 1

    with conn.cursor() as cur:
        cur.execute(
            """SELECT tender_id, bidder_id, occurred_at, payload->>'decision', actor_id
               FROM events WHERE event_type='DECISION_RECORDED'
               ORDER BY seq DESC LIMIT 10""")
        recent_decisions = [
            {"tender_id": t, "bidder_id": b, "occurred_at": at.isoformat(),
             "decision": d, "officer": officer}
            for t, b, at, d, officer in cur.fetchall()
        ]

    return {
        "tender_count": len(tenders),
        "bidder_count": bidder_count,
        "flagged_bidder_count": flagged_bidder_count,
        "risk_distribution": risk_counts,
        "recent_decisions": recent_decisions,
        "capabilities": capabilities(),
    }


# --- ingestion ----------------------------------------------------------------

@app.post("/tenders/{tender_id}/bidders", status_code=201)
def register_bidder(tender_id: str, body: BidderIn, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Register a bidder and record any attribute they share with an existing
    bidder on the same tender.

    Unlike the Express implementation this replaces, registration is NOT
    all-or-nothing: a bidder is linked on whatever subset of attributes is
    present. Requiring all four meant a single missing field silently disabled
    collusion detection for that bidder.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bidder_in_tender VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (tender_id, body.bidder_id))

    correlation = str(uuid.uuid4())
    registered = append(
        conn, event_type="BIDDER_REGISTERED", actor=SYSTEM,
        correlation_id=correlation, tender_id=tender_id, bidder_id=body.bidder_id,
        payload={"bidder_id": body.bidder_id,
                 "attributes_present": sorted(
                     k for k in ("director_name", "address", "phone", "bank_account")
                     if getattr(body, k))})

    links = _link_shared_attributes(conn, tender_id, body, correlation,
                                    registered["event_id"])
    return {"bidder_id": body.bidder_id, "tender_id": tender_id,
            "shared_attribute_links": links}


def _link_shared_attributes(conn, tender_id, body, correlation, causation) -> list[dict]:
    from .normalise import fingerprint

    attributes = {k: getattr(body, k) for k in
                  ("director_name", "address", "phone", "bank_account")
                  if getattr(body, k)}
    if not attributes:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """SELECT bidder_id, payload FROM events
               WHERE event_type='BIDDER_ATTRIBUTES' AND tender_id=%s
                 AND bidder_id <> %s""",
            (tender_id, body.bidder_id))
        others = cur.fetchall()

    prints = {name: fingerprint(name, value) for name, value in attributes.items()}

    links = []
    for other_id, payload in others:
        for name, digest in prints.items():
            if payload.get(name) == digest:
                append(conn, event_type="SHARED_ATTRIBUTE_OBSERVED", actor=SYSTEM,
                       correlation_id=correlation, causation_id=causation,
                       tender_id=tender_id,
                       payload={"bidder_a": body.bidder_id, "bidder_b": other_id,
                                "attribute": name, "value_sha256": digest})
                links.append({"with": other_id, "attribute": name})

    # Only hashes are stored. Two bidders sharing a bank account is the finding;
    # the account number does not need to enter an immutable log to establish
    # it, and events cannot be redacted afterwards.
    append(conn, event_type="BIDDER_ATTRIBUTES", actor=SYSTEM,
           correlation_id=correlation, causation_id=causation,
           tender_id=tender_id, bidder_id=body.bidder_id,
           payload=prints)
    return links


# --- verification -------------------------------------------------------------

@app.post("/bidders/{bidder_id}/verify")
def verify(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Run every registered capability for this bidder.

    With no credentials configured every capability returns a Failure, which
    becomes UNKNOWN with a machine-readable reason. That is the correct and
    honest result, and it is what the officer is shown.
    """
    correlation = str(uuid.uuid4())
    basis = LawfulBasis(Basis.TENDER_EVALUATION, "orchestrator",
                        f"Compliance evaluation for tender {tender_id}")

    # What we actually have on file for this bidder, so a live adapter has an
    # identifier to submit. Only what was genuinely extracted goes in here --
    # a field ProjectionResolver can't resolve is simply absent, never guessed.
    resolver = ProjectionResolver(conn, bidder_id)
    subject = {"bidder_id": bidder_id}
    for key, path in (("pan_number", "bidder.pan.pan_number"),
                       ("gstin", "bidder.gst.gstin"),
                       ("cin", "bidder.entity.cin"),
                       # Extraction landed (Suhani, feat/suhani-pan-holder-fields)
                       # -- PanStatusAdapter reads these two exact subject keys;
                       # PAN_STATUS goes from a standing MALFORMED refusal to a
                       # real live call the moment both resolve for a bidder.
                       ("pan_holder_name", "bidder.pan.holder_name"),
                       ("pan_date_of_birth", "bidder.pan.date_of_birth"),
                       # Round 11: UdyamStatusAdapter reads this exact key --
                       # was missing entirely before, so UDYAM_STATUS could
                       # never have received a real number even when
                       # Attestr credentials were configured.
                       ("udyam_number", "bidder.udyam.udyam_number")):
        resolved = resolver.field(path)
        if resolved.ok:
            subject[key] = resolved.value

    outcomes = []
    for capability_id, (adapter, capability) in sorted(REGISTRY.capabilities().items()):
        requested = append(
            conn, event_type="VERIFICATION_REQUESTED", actor=SYSTEM,
            correlation_id=correlation, tender_id=tender_id, bidder_id=bidder_id,
            payload={"capability_id": capability_id,
                     "lawful_basis": basis.basis.value,
                     "requested_by": basis.requested_by})

        outcome = adapter.verify(
            VerificationRequest(capability_id, subject, basis), conn)

        if hasattr(outcome, "code"):
            judgement = failure_to_judgement(outcome, capability)
            append(conn, event_type="VERIFICATION_FAILED",
                   actor=Actor("ADAPTER", adapter.manifest.adapter_id),
                   correlation_id=correlation, causation_id=requested["event_id"],
                   tender_id=tender_id, bidder_id=bidder_id,
                   payload={"capability_id": capability_id,
                            "failure_code": outcome.code.value,
                            "detail": outcome.detail,
                            "verdict": judgement.verdict.value,
                            "reason_code": judgement.reason.value})
            outcomes.append({"capability_id": capability_id,
                             "verdict": judgement.verdict.value,
                             "reason_code": judgement.reason.value,
                             "detail": outcome.detail})
        else:
            append(conn, event_type="VERIFICATION_OBSERVED",
                   actor=Actor("ADAPTER", adapter.manifest.adapter_id),
                   correlation_id=correlation, causation_id=requested["event_id"],
                   tender_id=tender_id, bidder_id=bidder_id,
                   payload={"capability_id": capability_id,
                            "raw_response_ref": outcome.raw_response_ref,
                            "observed_at": outcome.observed_at.isoformat(),
                            "source_asserted_at": (
                                outcome.source_asserted_at.isoformat()
                                if outcome.source_asserted_at else None),
                            "observations": [
                                {"path": o.path, "value": o.value,
                                 "tier": o.tier.value, "channel": o.channel.value}
                                for o in outcome.observations]})
            outcomes.append({"capability_id": capability_id, "verdict": "OBSERVED"})

    return {"bidder_id": bidder_id, "correlation_id": correlation,
            "outcomes": outcomes}


@app.post("/bidders/{bidder_id}/documents", status_code=201)
def upload_document(bidder_id: str, tender_id: str,
                    declared_type: str | None = None,
                    file: UploadFile = File(...),
                    conn=Depends(db), _user: User = Depends(officer_or_self)) -> dict[str, Any]:
    """Ingest a document and extract what can be read from it deterministically.

    For a PDF with a text layer this needs no model at all: identifiers are
    located by grammar, validated structurally, and recorded with the exact page
    and region their characters occupy. A page with no text layer is recorded as
    EXTRACTION_FAILED with a stated reason -- never a guessed value.

    Declared as a sync `def`, not `async def`: FastAPI runs a sync route in a
    worker thread automatically, which is what actually needs to happen here --
    `ingest_document` below does blocking DB calls and CPU-bound PDF parsing
    (pdfplumber), and running that inside an `async def` would block the whole
    event loop, freezing every other concurrent request for the duration of
    every upload. `file.file.read()` is the sync counterpart to `await
    file.read()` -- same bytes, off the event loop instead of blocking it.
    """
    data = file.file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    result = ingest_document(conn, tender_id=tender_id, bidder_id=bidder_id,
                             filename=file.filename or "upload.pdf", data=data,
                             declared_type=declared_type)
    rebuild_evidence(conn, bidder_id, REGISTRY)
    return result


@app.post("/bidders/{bidder_id}/declarations", status_code=201)
def record_declaration(bidder_id: str, tender_id: str, body: DeclarationIn,
                       conn=Depends(db), user: User = Depends(officer_or_self)) -> dict[str, Any]:
    """Round 9: closes DECLARATION, the one requirement type that was
    never an extraction problem -- an undertaking IS the self-declaration,
    with nothing to independently verify it against, by definition.

    Same gate as a bidder's own document upload (officer_or_self): a
    bidder attests for themselves, or an officer records it on their
    behalf -- either way the real signed-in identity is the actor, never
    a client-supplied name, because who attested is the entire point of
    a declaration.
    """
    event = append(
        conn, event_type="DECLARATION_RECORDED", actor=Actor("HUMAN", user.username),
        correlation_id=str(uuid.uuid4()), tender_id=tender_id, bidder_id=bidder_id,
        payload={"requirement_id": body.requirement_id,
                 "declaration_text": body.declaration_text,
                 "declared_by": user.username})
    rebuild_evidence(conn, bidder_id, REGISTRY)
    return {"bidder_id": bidder_id, "tender_id": tender_id,
            "requirement_id": body.requirement_id, "declared_by": user.username,
            "seq": event["seq"]}


def _digilocker_unavailable() -> HTTPException:
    return HTTPException(503, "DigiLocker is not configured on this deployment "
                              "(SATYAPRAMANA_SANDBOX_API_KEY/_SECRET unset)")


@app.post("/bidders/{bidder_id}/digilocker/session", status_code=201)
def start_digilocker_session(bidder_id: str, tender_id: str, body: DigilockerSessionIn,
                             conn=Depends(db), user: User = Depends(officer_or_self)) -> dict[str, Any]:
    """Round 10, PS26100 point 8. Issues the DigiLocker consent redirect --
    the bidder's browser goes to `authorization_url`, authenticates with
    DigiLocker directly (this backend never sees their DigiLocker
    credentials), and grants or denies consent to share their Aadhaar
    record. Nothing is verified yet at this point -- only requested; see
    GET .../digilocker/status for the outcome once the bidder returns.

    LawfulBasis here is TENDER_EVALUATION, not BIDDER_CONSENT: no consent
    exists yet at the moment of asking for a consent URL. The consent
    artefact (the session_id, once DigiLocker actually grants it) is what
    backs BIDDER_CONSENT on the fetch call below -- see digilocker.py's
    module docstring and adapters/base.py's own note on this distinction.
    """
    if DIGILOCKER_SESSION is None:
        raise _digilocker_unavailable()

    correlation = str(uuid.uuid4())
    basis = LawfulBasis(Basis.TENDER_EVALUATION, user.username,
                        f"DigiLocker consent request for tender {tender_id}")
    requested = append(
        conn, event_type="VERIFICATION_REQUESTED", actor=SYSTEM,
        correlation_id=correlation, tender_id=tender_id, bidder_id=bidder_id,
        payload={"capability_id": "DIGILOCKER_DOCUMENT",
                 "lawful_basis": basis.basis.value, "requested_by": user.username})

    outcome = _digilocker.initiate_session(
        DIGILOCKER_SESSION, redirect_url=body.redirect_url, doc_types=("aadhaar",),
        lawful_basis=basis, conn=conn)

    if isinstance(outcome, Failure):
        judgement = failure_to_judgement(outcome, _digilocker.DIGILOCKER_CAPABILITY)
        append(conn, event_type="VERIFICATION_FAILED",
               actor=Actor("ADAPTER", "digilocker"),
               correlation_id=correlation, causation_id=requested["event_id"],
               tender_id=tender_id, bidder_id=bidder_id,
               payload={"capability_id": "DIGILOCKER_DOCUMENT",
                        "failure_code": outcome.code.value, "detail": outcome.detail,
                        "verdict": judgement.verdict.value,
                        "reason_code": judgement.reason.value})
        raise HTTPException(502, f"DigiLocker session could not be started: {outcome.detail}")

    return {"bidder_id": bidder_id, "tender_id": tender_id,
            "session_id": outcome.session_id, "authorization_url": outcome.authorization_url}


@app.get("/bidders/{bidder_id}/digilocker/status")
def digilocker_session_status(bidder_id: str, tender_id: str, session_id: str,
                              conn=Depends(db), user: User = Depends(officer_or_self)) -> dict[str, Any]:
    """Polled by the frontend after the bidder returns from DigiLocker.
    `created` (still pending) is reported back with no event recorded --
    nothing has actually happened yet. `succeeded` fetches the real
    document and records a real VERIFICATION_OBSERVED; `failed`/`expired`
    record a real VERIFICATION_FAILED. Both terminal outcomes are recorded
    exactly once each poll that first observes them lands here -- a second
    poll after that re-fetches and re-records, same idempotent shape every
    other verification capability already has (append-only: a duplicate
    observation is just another true fact in the log, not a bug)."""
    if DIGILOCKER_SESSION is None:
        raise _digilocker_unavailable()

    correlation = str(uuid.uuid4())
    basis = LawfulBasis(Basis.TENDER_EVALUATION, user.username,
                        f"DigiLocker session status check for tender {tender_id}")
    status_outcome = _digilocker.check_session_status(
        DIGILOCKER_SESSION, session_id, lawful_basis=basis, conn=conn)

    if isinstance(status_outcome, Failure):
        raise HTTPException(502, f"could not check DigiLocker session status: {status_outcome.detail}")

    if status_outcome.status == "created":
        return {"status": "created"}

    requested = append(
        conn, event_type="VERIFICATION_REQUESTED", actor=SYSTEM,
        correlation_id=correlation, tender_id=tender_id, bidder_id=bidder_id,
        payload={"capability_id": "DIGILOCKER_DOCUMENT",
                 "lawful_basis": basis.basis.value, "requested_by": user.username,
                 "digilocker_session_id": session_id})

    if status_outcome.status in ("failed", "expired"):
        outcome = Failure(
            FailureCode.UNAVAILABLE,
            "bidder did not complete DigiLocker consent (session status: "
            f"{status_outcome.status})",
        )
        judgement = failure_to_judgement(outcome, _digilocker.DIGILOCKER_CAPABILITY)
        append(conn, event_type="VERIFICATION_FAILED",
               actor=Actor("ADAPTER", "digilocker"),
               correlation_id=correlation, causation_id=requested["event_id"],
               tender_id=tender_id, bidder_id=bidder_id,
               payload={"capability_id": "DIGILOCKER_DOCUMENT",
                        "failure_code": outcome.code.value, "detail": outcome.detail,
                        "verdict": judgement.verdict.value,
                        "reason_code": judgement.reason.value})
        rebuild_evidence(conn, bidder_id, REGISTRY)
        return {"status": status_outcome.status, "verdict": judgement.verdict.value}

    # status_outcome.status == "succeeded": the consent artefact now exists
    # for real -- this fetch is the one call in this whole flow that
    # actually retrieves the bidder's personal data, so it is the one call
    # lawfully backed by BIDDER_CONSENT, citing the real session_id.
    consent_basis = LawfulBasis(Basis.BIDDER_CONSENT, user.username,
                                f"DigiLocker document retrieval for tender {tender_id}",
                                consent_reference=session_id)
    doc_outcome = _digilocker.fetch_document(
        DIGILOCKER_SESSION, session_id, "aadhaar", lawful_basis=consent_basis, conn=conn)

    if isinstance(doc_outcome, Failure):
        judgement = failure_to_judgement(doc_outcome, _digilocker.DIGILOCKER_CAPABILITY)
        append(conn, event_type="VERIFICATION_FAILED",
               actor=Actor("ADAPTER", "digilocker"),
               correlation_id=correlation, causation_id=requested["event_id"],
               tender_id=tender_id, bidder_id=bidder_id,
               payload={"capability_id": "DIGILOCKER_DOCUMENT",
                        "failure_code": doc_outcome.code.value, "detail": doc_outcome.detail,
                        "verdict": judgement.verdict.value,
                        "reason_code": judgement.reason.value})
        rebuild_evidence(conn, bidder_id, REGISTRY)
        return {"status": "succeeded", "document_fetch": "failed", "verdict": judgement.verdict.value}

    file_meta = doc_outcome.files[0].get("metadata", {})
    observations = [
        {"path": "bidder.digilocker.aadhaar_verified", "value": "VERIFIED",
         "tier": Tier.A.value, "channel": Channel.AGGREGATOR.value},
        {"path": "bidder.digilocker.aadhaar_issuer",
         "value": file_meta.get("issuer", "DigiLocker"),
         "tier": Tier.A.value, "channel": Channel.AGGREGATOR.value},
    ]

    # DigiLocker consent alone proves a real Aadhaar-verified person
    # completed the flow -- it does not, by itself, prove that person is
    # this bidder. Downloading and reading the real signed document closes
    # that gap; failing to (a network blip, an expired pre-signed link) is
    # a real but non-fatal gap in a cross-check, never a reason to discard
    # the "consent was genuinely granted" fact already established above.
    identity_match_note = None
    try:
        doc_url = doc_outcome.files[0].get("url")
        if doc_url:
            identity = _digilocker.parse_aadhaar_xml(_digilocker.download_document_file(doc_url))
            if identity is not None:
                observations.append({"path": "bidder.digilocker.aadhaar_name", "value": identity.name,
                                     "tier": Tier.A.value, "channel": Channel.AGGREGATOR.value})
                if identity.dob_iso:
                    observations.append({"path": "bidder.digilocker.aadhaar_dob", "value": identity.dob_iso,
                                         "tier": Tier.A.value, "channel": Channel.AGGREGATOR.value})
                pan_resolver = ProjectionResolver(conn, bidder_id)
                pan_name = pan_resolver.field("bidder.pan.holder_name")
                if pan_name.ok:
                    match = _digilocker.names_match(identity.name, pan_name.value)
                    observations.append({"path": "bidder.digilocker.pan_identity_match",
                                         "value": "MATCH" if match else "MISMATCH",
                                         "tier": Tier.A.value, "channel": Channel.AGGREGATOR.value})
                    identity_match_note = "MATCH" if match else "MISMATCH"
    except httpx.HTTPError:
        pass  # the core VERIFIED fact below still stands; the cross-check just isn't available this time

    observed_at = datetime.now(timezone.utc)
    append(conn, event_type="VERIFICATION_OBSERVED",
           actor=Actor("ADAPTER", "digilocker"),
           correlation_id=correlation, causation_id=requested["event_id"],
           tender_id=tender_id, bidder_id=bidder_id,
           payload={"capability_id": "DIGILOCKER_DOCUMENT",
                    "raw_response_ref": doc_outcome.raw_response_ref,
                    "observed_at": observed_at.isoformat(), "source_asserted_at": None,
                    "observations": observations})
    rebuild_evidence(conn, bidder_id, REGISTRY)
    return {"status": "succeeded", "document_fetch": "ok",
            "issuer": file_meta.get("issuer"), "description": file_meta.get("description"),
            "pan_identity_match": identity_match_note}


@app.get("/documents/{document_sha256}")
def get_document(document_sha256: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))):
    """Serve a previously-ingested document back, for the evidence viewer --
    click a verdict, see the actual highlighted line of the actual PDF
    (satyapramana.md's own stated demo axiom).

    Looked up by content hash, never by a client-supplied filesystem path --
    the client can never name an arbitrary path on disk, only a hash that has
    to match a real DOCUMENT_INGESTED event's storage_ref.

    Real bug, found live (round 10): the same byte-identical content can be
    ingested more than once -- a genuine re-upload after a lost file, or
    two different bidders' documents that happen to collide on SHA-256 --
    each producing its own DOCUMENT_INGESTED event with its own
    storage_ref. `ORDER BY seq DESC` picks the most recent one, the same
    "later wins" rule every other evidence fold in this system already
    follows; without it, a bare LIMIT 1 could just as easily return a
    storage_ref from years-old, long-since-wiped local disk storage over
    one that's genuinely live right now.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT payload->>'storage_ref' FROM events
               WHERE event_type='DOCUMENT_INGESTED' AND payload->>'document_sha256'=%s
               ORDER BY seq DESC LIMIT 1""",
            (document_sha256,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "no document with that hash was ever ingested")
    data = read_document(row[0])
    if data is None:
        raise HTTPException(404, "the event log references this document, but it is not on disk here")
    return Response(content=data, media_type="application/pdf")


@app.post("/tenders/{tender_id}/documents", status_code=201)
def upload_tender_document(tender_id: str, file: UploadFile = File(...),
                           conn=Depends(db), user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Ingest the tender's own source document -- the original notice/RFP PDF,
    as opposed to a bidder's compliance document (`POST /bidders/{id}/documents`).

    Deliberately does not run identifier extraction (`find_candidates` and
    friends look for a GSTIN/PAN/CIN/Udyam-shaped string, which a tender
    notice has no reason to contain -- running them here would risk a
    coincidental false match). What this stage produces is exactly what
    Tender Intelligence's `POST /tenders/{tender_id}/decompose` and the rule
    pack's `tender_reference.source_document_sha256` both need: a real,
    hash-addressed, retrievable document, recorded as who uploaded it and
    when -- the event log, unchanged.

    `DOCUMENT_INGESTED` is not in `events.HUMAN_EVENT_TYPES` (only
    `TENDER_CREATED`/`RULE_PACK_ADOPTED`/`VERDICT_OVERRIDDEN`/`DECISION_RECORDED`
    may carry a HUMAN actor -- `append()` refuses the rest), the same reason
    `POST /bidders/{id}/documents` records this event under `INGEST`
    (`Actor("SYSTEM", ...)`) rather than the uploading officer directly. This
    endpoint still requires authentication (`current_user` above) and still
    records who triggered it -- just in the payload, the same place
    `TENDER_CREATED` already puts `created_by`, not in the event's actor
    field.

    Declared as a sync `def`, not `async def`, for the same reason as
    `upload_document` above: `store_document` (disk I/O + hashing) and
    `append` (a blocking DB call) both belong off the event loop, in
    FastAPI's automatic worker thread for a sync route.
    """
    data = file.file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    digest, storage_ref = store_document(data, tender_id, file.filename or "tender.pdf")
    rec = append(
        conn, event_type="DOCUMENT_INGESTED", actor=INGEST,
        correlation_id=str(uuid.uuid4()), tender_id=tender_id,
        payload={"document_sha256": digest, "storage_ref": storage_ref,
                 "filename": os.path.basename(file.filename or "tender.pdf"),
                 "declared_type": "TENDER_NOTICE", "bytes": len(data),
                 "uploaded_by": user.username})
    return {"tender_id": tender_id, "document_sha256": digest,
            "seq": rec["seq"], "hash": rec["hash"]}


@app.get("/requirement-types")
def requirement_types(_user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The admin builder's requirement-type catalog (docs/COMPLETION_PLAN.md
    item 2). Computed live against REGISTRY and the deterministic-extraction
    field list -- the same two sources rule 8 validates a submitted pack
    against -- so `evidence_backed` here is never a second, driftable copy
    of that answer."""
    return {"requirement_types": requirement_type_catalog(REGISTRY)}


class RulePackValidateIn(BaseModel):
    pack: dict[str, Any]


@app.post("/tenders/{tender_id}/rule-pack/validate")
def validate_rule_pack(tender_id: str, body: RulePackValidateIn, conn=Depends(db),
                       user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Dry-run validation -- the admin builder's "Validate Rule Pack" step,
    distinct from "Publish Tender" (`POST /tenders/{tender_id}/rule-pack`,
    which adopts). Runs the identical rule-8-through-13 check adoption gates
    on, against the same live registry, but appends no event and writes no
    row -- so an officer can iterate on a draft without every attempt
    becoming a permanent adoption record. Open to any authenticated officer
    (not just SENIOR_OFFICER+): checking a draft commits nothing, so the
    higher bar belongs on adoption alone, where it already is.
    """
    body_hashed, violations = validate_only(body.pack, registry=REGISTRY)
    if violations:
        return {"valid": False,
                "violations": [{"rule": v.rule, "requirement_id": v.requirement_id,
                                "message": v.message} for v in violations]}
    return {"valid": True, "violations": [],
            "content_hash": body_hashed["content_hash"],
            "requirement_count": len(body_hashed["requirements"])}


class DecomposeIn(BaseModel):
    document_sha256: str


@app.post("/tenders/{tender_id}/decompose")
def decompose_tender(tender_id: str, body: DecomposeIn, conn=Depends(db),
                     user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """satyapramana.md section 5's AI/deterministic boundary table, the
    "Decompose tender prose into atomic requirements" row -- explicitly an
    LLM-may capability, and explicitly bounded: this returns candidate
    requirement proposals for an officer to review, never a rule pack.
    Nothing from here reaches POST /tenders/{id}/rule-pack without a human
    manually re-entering it through the rule pack builder -- there is no
    code path that skips that.

    The document must already be an ingested document (any prior upload
    endpoint reaches the same storage) -- this never accepts raw text
    directly, so every decomposition traces back to a real, hash-addressed
    source document, the same evidentiary discipline as everything else in
    this system.
    """
    # ORDER BY seq DESC -- same real bug and same fix as GET /documents/
    # {sha256} above: the same content can be re-ingested more than once,
    # each with its own storage_ref, and a bare LIMIT 1 has no guarantee
    # of picking the current one.
    with conn.cursor() as cur:
        cur.execute(
            """SELECT payload->>'storage_ref' FROM events
               WHERE event_type='DOCUMENT_INGESTED' AND payload->>'document_sha256'=%s
               ORDER BY seq DESC LIMIT 1""",
            (body.document_sha256,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "no document with that hash was ever ingested")
    data = read_document(row[0])
    if data is None:
        raise HTTPException(404, "the event log references this document, but it is not on disk here")

    pages = read_pdf(data)
    document_text = "\n\n".join(
        f"--- PAGE {p.number} ---\n" + " ".join(w.text for w in p.words)
        for p in pages if p.has_text_layer)
    if not document_text.strip():
        return {"tender_id": tender_id, "available": False,
                "reason": "this document has no extractable text layer (a scanned image, not real text)",
                "model": None, "generated_at": None, "proposals": []}

    outcome = DECOMPOSER.decompose(document_text)
    if isinstance(outcome, DecomposeUnavailable):
        return {"tender_id": tender_id, "available": False, "reason": outcome.reason,
                "model": None, "generated_at": None, "proposals": []}
    return {"tender_id": tender_id, "available": True, "reason": None,
            "model": outcome.model, "generated_at": outcome.generated_at.isoformat(),
            "proposals": [
                {"text": p.text, "page": p.page, "obligation_guess": p.obligation_guess,
                 "suggested_field": p.suggested_field, "suggested_check": p.suggested_check,
                 "note": p.note}
                for p in outcome.proposals
            ]}


# --- rule packs and decision --------------------------------------------------

@app.post("/tenders/{tender_id}/rule-pack", status_code=201)
def adopt_rule_pack(tender_id: str, body: RulePackIn, conn=Depends(db),
                    user: User = Depends(require_role(Role.SENIOR_OFFICER))) -> dict[str, Any]:
    """Adoption is a human act, recorded with the officer's identity, the
    content hash and a timestamp. Requires SENIOR_OFFICER or higher -- a
    rule pack governs every bidder's evaluation on a tender, not a single
    bidder's record, so adopting one is deliberately not a base-OFFICER
    action.

    Validation gates it. A pack whose predicates reference evidence paths no
    registered capability can produce is refused here rather than becoming a
    permanent, unexplained UNKNOWN in production -- and a pack carrying an
    unreviewed uncertain requirement cannot be adopted at all.
    """
    try:
        return adopt(conn, body.pack, tender_id=tender_id,
                     officer_id=user.username, registry=REGISTRY)
    except NotAdoptable as exc:
        raise HTTPException(422, {
            "error": "rule pack cannot be adopted",
            "violations": [{"rule": v.rule, "requirement_id": v.requirement_id,
                            "message": v.message} for v in exc.violations],
        }) from exc


@app.post("/bidders/{bidder_id}/evaluate")
def evaluate_bidder_endpoint(bidder_id: str, tender_id: str, body: EvaluateIn,
                             conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Fold the evidence, fuse it, and decide -- deterministically, with no
    model in the path.

    `as_of` and `bid_submission_date` come from the request, never from the
    system clock, which is what makes the result reproducible on replay.
    """
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    version, pack = found

    rebuild_evidence(conn, bidder_id, REGISTRY)
    ctx = EvaluationContext(
        as_of=body.as_of or date.today(),
        bid_submission_date=body.bid_submission_date,
        tender_id=tender_id, bidder_id=bidder_id, rule_pack_version=version)
    result = fuse_and_evaluate(conn, pack=pack, rule_pack_version=version,
                              tender_id=tender_id, bidder_id=bidder_id, ctx=ctx)
    rebuild_projections_for_bidder(conn, bidder_id)
    return {"bidder_id": bidder_id, "rule_pack_version": version, **result}


# --- read models --------------------------------------------------------------

def _fetch_verdict_rows(conn, bidder_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT requirement_id, verdict_system, reason_system,
                      verdict_effective, reason_effective, overridden_by,
                      override_justification, rule_pack_version
               FROM proj_verdicts WHERE bidder_id=%s ORDER BY requirement_id""",
            (bidder_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _list_tender_bidders(tender_id: str, conn) -> dict[str, Any]:
    """The actual bidder-listing query, assuming projections are already
    fresh -- split out so a caller that's about to list bidders across
    several tenders in one request (the dashboard) can rebuild once for the
    whole request instead of once per tender. `rebuild_projections` folds
    the entire event log for every tenant, not just one, so it was never
    actually tender-scoped work to begin with."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bidder_id FROM bidder_in_tender WHERE tender_id=%s ORDER BY bidder_id",
            (tender_id,))
        bidder_ids = [row[0] for row in cur.fetchall()]

    pack = active_pack(conn, tender_id)
    clusters = {c.bidder_id: c for c in collusion_clusters(conn, tender_id)}
    return {"tender_id": tender_id,
            "bidders": [_bidder_snapshot(bidder_id, tender_id, conn, pack=pack, cluster=clusters.get(bidder_id))
                       for bidder_id in bidder_ids]}


@app.get("/tenders/{tender_id}/bidders")
def list_tender_bidders(tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Every bidder registered on this tender, each with the same summary
    `GET /bidders/{id}` returns -- one round trip for a dashboard instead of
    one per card."""
    rebuild_projections(conn)
    return _list_tender_bidders(tender_id, conn)


@app.get("/tenders/{tender_id}/report")
def tender_compliance_report(tender_id: str, as_text: bool = False, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))):
    """Of everyone who bid, where do we stand overall -- the aggregate
    counterpart to a single bidder's Dossier. `?as_text=true` for the
    plain-text rendering."""
    body = list_tender_bidders(tender_id, conn)
    report = tender_report(tender_id, body["bidders"])
    if as_text:
        return PlainTextResponse(render_tender_report_text(report))
    return report


@app.get("/tenders/{tender_id}/report/csv")
def tender_report_csv(tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))):
    """The same bidder list as `GET /tenders/{tender_id}/bidders`, as CSV --
    the artifact an officer actually takes somewhere: a spreadsheet, an
    email, a physical file. See reporting/csv_export.py."""
    body = list_tender_bidders(tender_id, conn)
    return PlainTextResponse(bidders_to_csv(body["bidders"]), media_type="text/csv")


@app.get("/tenders/{tender_id}/blockers")
def tender_blockers(tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Across every bidder on this tender, which requirement is blocking the
    most of them -- aggregating each bidder's own Bid Autopsy. Useful for an
    officer deciding whether a requirement needs relaxing, or which document
    type to chase bidders for. See reporting/blocker_summary.py.

    `list_tender_bidders` below already does one projection rebuild for the
    whole tender; autopsy only needs the pack fetched once more here, not
    once per bidder via the full `bidder_autopsy` route function.
    """
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    _, pack = found
    bidder_ids = list_tender_bidders(tender_id, conn)["bidders"]
    autopsies = [_bidder_autopsy_result(b["bidder_id"], tender_id, conn, pack=pack) for b in bidder_ids]
    return {"tender_id": tender_id, "blockers": blocker_summary(autopsies)}


def _bidder_snapshot(bidder_id: str, tender_id: str, conn, *, pack, cluster,
                     verdicts=None, resolver=None) -> dict[str, Any]:
    """The actual per-bidder computation behind `GET /bidders/{id}`, given the
    tender-scoped inputs (the active rule pack, and this bidder's own
    collusion cluster if any) already fetched by the caller.

    Split out so `list_tender_bidders` can compute the active pack and every
    bidder's cluster ONCE per request and pass them in here per bidder,
    instead of every bidder on the tender separately re-querying the exact
    same pack and re-running collusion_clusters() (whose result is identical
    for all of them -- it's scoped to the tender, not the bidder). For a
    tender with N bidders this was N redundant queries each; now it's one.

    `verdicts`/`resolver` are optional so the Temporal Scrubber's `as-of`
    endpoint can pass a past, purely-computed pair (fold_verdicts_as_of +
    ProjectionResolver.from_records -- neither touches a table) through the
    exact same metrics/risk computation the live path uses below, instead
    of a second, possibly-drifting copy of it. Every existing caller leaves
    both unset and gets today's live-tip behaviour, unchanged.
    """
    if verdicts is None:
        verdicts = _fetch_verdict_rows(conn, bidder_id)
    if resolver is None:
        resolver = ProjectionResolver(conn, bidder_id)

    obligations, bindings = {}, {}
    if pack:
        for req in pack[1]["requirements"]:
            obligations[req["id"]] = Obligation(req["obligation"])
            bindings[req["id"]] = derived_bindings(req)

    results = []
    for v in verdicts:
        rid = v["requirement_id"]
        tiers = resolver.tiers_for(bindings.get(rid, ()))
        # Coverage counts only fresh Tier A evidence. Nothing is Tier A yet,
        # because no capability is configured -- so coverage is honestly 0%.
        covered = any(t is Tier.A for t in tiers)
        results.append(RequirementResult(
            rid, Verdict(v["verdict_effective"]),
            obligations.get(rid, Obligation.MANDATORY),
            covered=covered,
            tier=max(tiers, key=lambda t: {Tier.A: 3, Tier.B: 2, Tier.C: 1}[t])
                 if tiers else None))
    metrics = compute(results, CONSTANTS)
    self_declared = tuple(
        r.requirement_id for r in results
        if r.obligation is Obligation.MANDATORY and r.tier is Tier.C)
    risk = classify(results, metrics, ConflictSignals(
        collusion_edge=bool(cluster and cluster.flagged),
        self_declared_mandatory=self_declared), CONSTANTS)

    return {
        "bidder_id": bidder_id,
        "tender_id": tender_id,
        "verdicts": verdicts,
        # Three figures, never averaged. compliance_score is null -- not zero --
        # when nothing could be determined; renderers must show an em dash.
        "metrics": {
            "compliance_score": metrics.compliance_score,
            "verification_coverage": metrics.verification_coverage,
            "verification_coverage_mandatory": metrics.verification_coverage_mandatory,
            "evidence_confidence": metrics.evidence_confidence,
        },
        "risk": {"level": risk.level.value, "triggers": list(risk.triggers),
                 "function_version": risk.function_version},
        "collusion": None if not cluster else {
            "flagged": cluster.flagged, "cluster_id": cluster.cluster_id,
            "members": list(cluster.members)},
    }


@app.get("/bidders/{bidder_id}")
def get_bidder(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    rebuild_projections_for_bidder(conn, bidder_id)
    pack = active_pack(conn, tender_id)
    clusters = {c.bidder_id: c for c in collusion_clusters(conn, tender_id)}
    return _bidder_snapshot(bidder_id, tender_id, conn, pack=pack, cluster=clusters.get(bidder_id))


#: Event types that mark a real checkpoint in one bidder's own history --
#: the Temporal Scrubber's timeline is exactly this set, nothing invented.
_TIMELINE_EVENT_TYPES = (
    "FIELD_EXTRACTED", "EXTRACTION_FAILED", "VERIFICATION_OBSERVED",
    "VERIFICATION_FAILED", "REQUIREMENT_EVALUATED", "VERDICT_OVERRIDDEN",
    "DECISION_RECORDED",
)


@app.get("/bidders/{bidder_id}/timeline")
def bidder_timeline(bidder_id: str, tender_id: str, conn=Depends(db),
                    _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Every event that changed something about this bidder, in order --
    the real checkpoints `GET /bidders/{id}/as-of/{seq}` can be asked
    about. Not evenly spaced: however sparse or clustered the bidder's
    real history actually is, is what this returns."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT seq, event_type, occurred_at FROM events
               WHERE bidder_id=%s AND tender_id=%s
                 AND event_type = ANY(%s)
               ORDER BY seq""",
            (bidder_id, tender_id, list(_TIMELINE_EVENT_TYPES)))
        rows = cur.fetchall()
    return {"checkpoints": [
        {"seq": seq, "event_type": etype, "occurred_at": occurred_at.isoformat()}
        for seq, etype, occurred_at in rows
    ]}


@app.get("/bidders/{bidder_id}/as-of/{seq}")
def bidder_as_of(bidder_id: str, seq: int, tender_id: str, conn=Depends(db),
                 _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The Temporal Scrubber: the same shape `GET /bidders/{id}` returns,
    computed as of a past event instead of the live tip -- via the pure
    fold functions (fold_verdicts_as_of, fold_evidence_as_of,
    active_pack_as_of, collusion_clusters_as_of), never the tables every
    concurrent `GET /bidders/{id}` reads. See
    projections.fold_verdicts_as_of's docstring for why that distinction
    is load-bearing, not stylistic.

    Round 8 shipped this endpoint with collusion as the one honest
    exception -- collusion_clusters() had no `up_to_seq` of its own, so
    the collusion figure was always today's, never the checkpoint's.
    Round 9 (sql/009_collusion_as_of.sql) closed that: collusion below is
    genuinely folded as of `seq`, the same as everything else here.
    """
    tip = _tip_seq(conn)
    if seq < 0 or seq > tip:
        raise HTTPException(422, f"seq {seq} is outside this log's range (0..{tip})")

    raw_verdicts = fold_verdicts_as_of(conn, seq, bidder_id=bidder_id)
    # Same 8-key shape _fetch_verdict_rows returns for the live endpoint --
    # fold_verdicts_as_of carries extra bookkeeping fields (bidder_id,
    # tender_id, causation_event, built_from_seq) that _rebuild_locked
    # needs for its INSERT and this response does not; trimmed here so
    # both endpoints' "verdicts" field is the same shape for a frontend
    # that renders either one.
    verdicts = [
        {k: v[k] for k in ("requirement_id", "verdict_system", "reason_system",
                           "verdict_effective", "reason_effective", "overridden_by",
                           "override_justification", "rule_pack_version")}
        for v in raw_verdicts.values()
    ]
    evidence_records = fold_evidence_as_of(conn, bidder_id, REGISTRY, seq)
    resolver = ProjectionResolver.from_records(evidence_records)
    pack = active_pack_as_of(conn, tender_id, seq)
    cluster = {c.bidder_id: c for c in collusion_clusters_as_of(conn, tender_id, seq)}.get(bidder_id)

    snapshot = _bidder_snapshot(bidder_id, tender_id, conn, pack=pack, cluster=cluster,
                                verdicts=verdicts, resolver=resolver)
    snapshot["as_of_seq"] = seq
    return snapshot


def _tip_seq(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(seq), 0) FROM events")
        return cur.fetchone()[0]


# --- reporting: Bid Autopsy and Compliance Repair -----------------------------

def _bidder_autopsy_result(bidder_id: str, tender_id: str, conn, *, pack) -> dict[str, Any]:
    """The per-bidder computation behind `GET /bidders/{id}/autopsy`, given
    the tender's active pack already fetched by the caller -- see
    `_bidder_snapshot` above for why this split exists."""
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    return {"bidder_id": bidder_id, "tender_id": tender_id, **autopsy(pack, verdicts)}


@app.get("/bidders/{bidder_id}/autopsy")
def bidder_autopsy(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Why would this bid fail, right now. satyapramana.md section 11:
    deterministic, derived from the event log, never regenerated by a model.
    """
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    _, pack = found
    rebuild_projections_for_bidder(conn, bidder_id)
    return _bidder_autopsy_result(bidder_id, tender_id, conn, pack=pack)


@app.get("/bidders/{bidder_id}/repair-plan")
def bidder_repair_plan(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The forward-looking inverse of the autopsy: one action per curable gap.
    Fatal findings (positive evidence against the bidder) get no action here --
    the autopsy is where those stay visible."""
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    _, pack = found
    rebuild_projections_for_bidder(conn, bidder_id)
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    return {"bidder_id": bidder_id, "tender_id": tender_id,
            **repair_plan(pack, verdicts, REGISTRY)}


@app.get("/bidders/{bidder_id}/dossier")
def bidder_dossier(bidder_id: str, tender_id: str, as_text: bool = False,
                   conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))):
    """The single artifact an officer would print, attach to a decision file,
    or hand to a supervisor -- score, risk, verdicts, the autopsy and the
    repair plan, combined. `?as_text=true` for the plain-text rendering
    instead of JSON. Composes the three real endpoints above rather than
    recomputing anything -- see reporting/dossier.py."""
    bidder = get_bidder(bidder_id, tender_id, conn)
    autopsy_report = bidder_autopsy(bidder_id, tender_id, conn)
    repair_report = bidder_repair_plan(bidder_id, tender_id, conn)
    dossier = build_dossier(bidder, autopsy_report, repair_report)
    if as_text:
        return PlainTextResponse(render_dossier_text(dossier))
    return dossier


@app.get("/bidders/{bidder_id}/explain")
def bidder_explain(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """satyapramana.md section 2.2's EXPLAIN stage: narrate the already-final
    dossier into officer-readable prose. A narrator, not a judge -- the LLM
    receives exactly the plain-text Compliance Dossier an officer could
    already read and may not alter a single fact in it. Never archived to
    the event log (see explain/base.py): this endpoint recomputes the
    dossier and re-narrates it fresh on every call.

    Always 200 -- an unconfigured or failing provider is a normal, honest
    outcome here (`available: false`, with the real reason), never a 5xx,
    because the charter is explicit: "the system still returns complete,
    correct, structured verdicts" with or without this."""
    dossier = bidder_dossier(bidder_id, tender_id, conn=conn)
    dossier_text = render_dossier_text(dossier)
    outcome = EXPLAINER.narrate(dossier_text)
    if isinstance(outcome, Unavailable):
        return {"bidder_id": bidder_id, "tender_id": tender_id,
                "available": False, "narrative": None, "reason": outcome.reason,
                "model": None, "generated_at": None}
    return {"bidder_id": bidder_id, "tender_id": tender_id,
            "available": True, "narrative": outcome.narrative, "reason": None,
            "model": outcome.model, "generated_at": outcome.generated_at.isoformat()}


@app.get("/bidders/{bidder_id}/evidence")
def bidder_evidence(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Every evidence path resolved (or not) for this bidder -- the raw
    material the rule engine reads, before any rule pack judges it.
    Provenance answers "why does this one verdict say what it says"; this
    answers "what does this system actually know about this bidder,
    everything, right now" -- the frontend's ConflictCard needs exactly this
    to show a bidder's own claim beside what an authority verified, since
    nothing else exposes two evidence paths side by side."""
    rebuild_evidence(conn, bidder_id, REGISTRY)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT path, resolved, value, unresolved_reason, tier, channel, capability_id
               FROM proj_evidence WHERE bidder_id=%s ORDER BY path""",
            (bidder_id,))
        rows = cur.fetchall()
    return {"bidder_id": bidder_id, "tender_id": tender_id,
            "evidence": [
                {"path": path, "resolved": resolved, "value": value,
                 "unresolved_reason": reason, "tier": tier, "channel": channel,
                 "capability_id": capability_id}
                for path, resolved, value, reason, tier, channel, capability_id in rows]}


def _evidence_by_path(conn, bidder_id: str) -> dict[str, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT path, resolved, value, unresolved_reason, tier, channel, capability_id
               FROM proj_evidence WHERE bidder_id=%s""",
            (bidder_id,))
        return {
            path: {"resolved": resolved, "value": value, "unresolved_reason": reason,
                   "tier": tier, "channel": channel, "capability_id": capability_id}
            for path, resolved, value, reason, tier, channel, capability_id in cur.fetchall()
        }


@app.get("/bidders/{bidder_id}/evidence-graph")
def bidder_evidence_graph(bidder_id: str, tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """satyapramana.md section 2.3's signature screen, as data: requirements
    on one axis, the evidence each one actually consumes beneath it, and
    which authority (if any) was ever asked about that evidence, beside it.
    See reporting/evidence_graph.py for exactly what a node and an edge mean
    here, and why a composite requirement or a self-declared-only path gets
    no node of a kind it doesn't honestly have."""
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    _, pack = found
    rebuild_projections_for_bidder(conn, bidder_id)
    rebuild_evidence(conn, bidder_id, REGISTRY)
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    evidence_by_path = _evidence_by_path(conn, bidder_id)
    graph = build_evidence_graph(pack, verdicts, evidence_by_path, REGISTRY)
    return {"bidder_id": bidder_id, "tender_id": tender_id, **graph}


@app.get("/bidders/{bidder_id}/requirements/{requirement_id}/provenance")
def provenance(bidder_id: str, requirement_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Why does this say what it says.

    One backward walk along causation_id: verdict -> fused evidence ->
    verification (with its raw response reference) -> extraction (with page and
    region) -> the source document.
    """
    trail = provenance_trail(conn, bidder_id, requirement_id)
    if not trail:
        raise HTTPException(404, f"no verdict recorded for {requirement_id}")
    return {"bidder_id": bidder_id, "requirement_id": requirement_id,
            "trail": [{"depth": t["depth"], "event_type": t["event_type"],
                       "seq": t["seq"], "occurred_at": t["occurred_at"].isoformat(),
                       "payload": t["payload"]} for t in trail]}


@app.get("/tenders/{tender_id}/collusion")
def collusion(tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    clusters = collusion_clusters(conn, tender_id)
    return {"tender_id": tender_id,
            "bidders": [{"bidder_id": c.bidder_id, "flagged": c.flagged,
                         "cluster_id": c.cluster_id, "members": list(c.members)}
                        for c in clusters]}


@app.get("/tenders/{tender_id}/collusion/edges")
def collusion_edges(tender_id: str, conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The pairwise findings behind the clusters above -- which two bidders,
    over which specific attribute. `/collusion` answers "is this bidder
    flagged"; this answers "why", at the same precision the event log
    actually recorded it. Never the raw attribute value, only its hash's
    existence as a match -- the same evidentiary boundary the log itself
    keeps (see _link_shared_attributes)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT payload->>'bidder_a', payload->>'bidder_b', payload->>'attribute'
               FROM events
               WHERE event_type='SHARED_ATTRIBUTE_OBSERVED' AND tender_id=%s
               ORDER BY seq""",
            (tender_id,))
        edges = [{"bidder_a": a, "bidder_b": b, "attribute": attr}
                 for a, b, attr in cur.fetchall()]
    return {"tender_id": tender_id, "edges": edges}


# --- bidder self-service (round 6) ---------------------------------------------
#
# Every endpoint below is scoped to the caller's OWN bidder_id via
# current_bidder -- none of them take a bidder_id from the path or query,
# so there is no id to guess. They return a deliberately narrower shape
# than the officer-facing equivalents: no metrics, no risk, no collusion,
# no rule-pack constants, no officer identity, nothing from /audit. See
# docs/NEXT_TASKS_6_anubrat_rishika_suhani_kevin.md's policy table for
# exactly what a bidder may and may not see -- this is that table, in code.

def _bidder_submission_status(conn, tender_id: str, bidder_id: str) -> str:
    """REGISTERED -> DOCUMENTS_RECEIVED -> UNDER_EVALUATION -> DECIDED,
    derived from events only, never from a stored flag that could drift
    from what actually happened."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM events WHERE event_type='DECISION_RECORDED' "
            "AND tender_id=%s AND bidder_id=%s LIMIT 1", (tender_id, bidder_id))
        if cur.fetchone():
            return "DECIDED"
        cur.execute(
            "SELECT 1 FROM proj_verdicts WHERE bidder_id=%s AND tender_id=%s LIMIT 1",
            (bidder_id, tender_id))
        if cur.fetchone():
            return "UNDER_EVALUATION"
        cur.execute(
            "SELECT 1 FROM events WHERE event_type='DOCUMENT_INGESTED' "
            "AND tender_id=%s AND bidder_id=%s LIMIT 1", (tender_id, bidder_id))
        if cur.fetchone():
            return "DOCUMENTS_RECEIVED"
    return "REGISTERED"


def _evidence_expected(field: str) -> str:
    """A plain-language label for the document a requirement's evidence
    field implies, for the bidder-facing requirements list. Falls back to
    the raw field name rather than guessing for anything not in this list
    -- an honest "we don't have a nicer label" beats a wrong one."""
    labels = {
        "bidder.gst.gstin": "GST registration certificate",
        "bidder.gst.status": "GST registration certificate",
        "bidder.pan.pan_number": "PAN card",
        "bidder.pan.status": "PAN card",
        "bidder.entity.cin": "Certificate of Incorporation",
        "bidder.entity.status": "Certificate of Incorporation",
        "bidder.udyam.udyam_number": "Udyam (MSME) registration certificate",
        "bidder.udyam.status": "Udyam (MSME) registration certificate",
    }
    if field.startswith("bidder.declarations."):
        return "Self-declaration / undertaking"
    if field.startswith("bidder.digilocker."):
        return "Aadhaar via DigiLocker"
    return labels.get(field, field)


@app.get("/me/tenders")
def my_tenders(conn=Depends(db), bidder: User = Depends(current_bidder)) -> dict[str, Any]:
    """Tenders this bidder is registered on, plus every tender with an
    adopted rule pack they're not on yet (so discovery works) -- each
    flagged `registered`. Reuses list_tenders/proj_tenders/active_pack
    rather than re-deriving what a tender is."""
    all_tender_ids = list_tenders(conn)["tenders"]
    with conn.cursor() as cur:
        cur.execute("SELECT tender_id FROM bidder_in_tender WHERE bidder_id=%s",
                    (bidder.bidder_id,))
        registered = {row[0] for row in cur.fetchall()}
    out = []
    for tender_id in all_tender_ids:
        found = active_pack(conn, tender_id)
        is_registered = tender_id in registered
        if not is_registered and not found:
            continue  # not registered, and nothing published yet -- not discoverable
        meta = get_tender(tender_id, conn)
        out.append({**meta, "requirements_published": bool(found), "registered": is_registered,
                    "status": _bidder_submission_status(conn, tender_id, bidder.bidder_id)
                              if is_registered else "NOT_REGISTERED"})
    return {"tenders": out}


@app.get("/me/tenders/{tender_id}/requirements")
def my_tender_requirements(tender_id: str, conn=Depends(db),
                           bidder: User = Depends(current_bidder)) -> dict[str, Any]:
    """The adopted pack's requirements, projected to only what a bidder
    should see -- id, quoted text, obligation, source page, and a
    plain-language evidence label. No constants, no weights, no
    freshness windows, no review notes."""
    found = active_pack(conn, tender_id)
    if not found:
        return {"tender_id": tender_id, "requirements": []}
    _, pack = found

    def _field_of(req: dict) -> str | None:
        pred = req.get("predicate") or {}
        subject = pred.get("subject") or pred.get("left") or {}
        return subject.get("field")

    reqs = [
        {"id": r["id"], "text": r["text"], "obligation": r["obligation"],
         "source_page": r.get("source", {}).get("page"),
         "evidence_expected": _evidence_expected(_field_of(r)) if _field_of(r) else "Supporting document"}
        for r in pack["requirements"]
    ]
    return {"tender_id": tender_id, "requirements": reqs}


@app.get("/me/tenders/{tender_id}/submission")
def my_submission(tender_id: str, conn=Depends(db),
                  bidder: User = Depends(current_bidder)) -> dict[str, Any]:
    """This bidder's own uploaded documents on this tender, with each
    upload's real extraction summary -- the same shape
    POST /bidders/{id}/documents already returned at upload time, read
    back from the event log rather than re-derived. Round 9: their own
    recorded declarations join this same read, same reasoning -- a
    bidder reopening this page needs to see what they've already
    attested to, not re-declare blind."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT payload FROM events
               WHERE event_type='DOCUMENT_INGESTED' AND tender_id=%s AND bidder_id=%s
               ORDER BY seq""",
            (tender_id, bidder.bidder_id))
        documents = [row[0] for row in cur.fetchall()]
        cur.execute(
            """SELECT payload, occurred_at FROM events
               WHERE event_type='DECLARATION_RECORDED' AND tender_id=%s AND bidder_id=%s
               ORDER BY seq""",
            (tender_id, bidder.bidder_id))
        # Later wins, the same fold every other evidence path uses -- keyed
        # by requirement_id so a correction replaces the row instead of
        # appending a second one the bidder would see twice.
        by_requirement: dict[str, dict[str, Any]] = {}
        for payload, occurred_at in cur.fetchall():
            by_requirement[payload["requirement_id"]] = {
                "requirement_id": payload["requirement_id"],
                "declaration_text": payload["declaration_text"],
                "declared_by": payload["declared_by"],
                "declared_at": occurred_at.isoformat()}
        declarations = sorted(by_requirement.values(), key=lambda d: d["requirement_id"])
    status = _bidder_submission_status(conn, tender_id, bidder.bidder_id)
    return {"tender_id": tender_id, "bidder_id": bidder.bidder_id,
            "status": status, "documents": documents, "declarations": declarations}


def _bidder_result_view(conn, tender_id: str, bidder_id: str) -> dict[str, Any]:
    """The bidder-visible result, exactly -- shared by the bidder's own
    GET /me/tenders/{id}/result and the officer's pre-decision preview
    below, so "what the bidder sees" is never a second, hand-maintained
    copy of this projection that could quietly drift from the real one."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT occurred_at, payload->>'decision', payload->>'note'
               FROM events WHERE event_type='DECISION_RECORDED'
                 AND tender_id=%s AND bidder_id=%s
               ORDER BY seq DESC LIMIT 1""",
            (tender_id, bidder_id))
        row = cur.fetchone()
    if not row:
        return {"tender_id": tender_id, "bidder_id": bidder_id, "published": False}
    decided_at, decision, note = row
    rebuild_projections_for_bidder(conn, bidder_id)
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    outcomes = [{"requirement_id": v["requirement_id"], "verdict": v["verdict_effective"]}
                for v in verdicts]
    actions = []
    found = active_pack(conn, tender_id)
    if found:
        _, pack = found
        actions = repair_plan(pack, verdicts, REGISTRY).get("actions", [])
    return {"tender_id": tender_id, "bidder_id": bidder_id, "published": True,
            "decision": decision, "decided_at": decided_at.isoformat(), "note": note,
            "outcomes": outcomes, "repair_actions": actions}


@app.get("/me/tenders/{tender_id}/result")
def my_result(tender_id: str, conn=Depends(db),
              bidder: User = Depends(current_bidder)) -> dict[str, Any]:
    """Honestly empty until a DECISION_RECORDED exists for this bidder --
    no metrics, no risk, no collusion, no officer identity, no override
    justifications. Once decided: the decision, the officer's note (if
    any), per-requirement effective verdicts, and repair actions for
    curable gaps."""
    return _bidder_result_view(conn, tender_id, bidder.bidder_id)


@app.get("/tenders/{tender_id}/bidders/{bidder_id}/result-preview")
def bidder_result_preview(tender_id: str, bidder_id: str, conn=Depends(db),
                          _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The officer's pre-decision check: exactly what GET /me/tenders/{id}/result
    would return to this bidder right now -- same helper, same projection,
    so "what the bidder will see" is never guessed at from a different
    (richer) officer-side view. If no decision exists yet, this honestly
    returns published: false, same as the bidder would see."""
    return _bidder_result_view(conn, tender_id, bidder_id)


# --- officer review desk (round 6) ----------------------------------------------

@app.get("/review-queue")
def review_queue(conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """Every bidder across every tender, with enough to triage who needs a
    human decision next -- built on _list_tender_bidders (one
    rebuild_projections total, not one per bidder or per tender pair; see
    docs/PERFORMANCE_AUDIT.md) rather than re-walking bidders one at a time."""
    rebuild_projections(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT tender_id, bidder_id FROM events "
                    "WHERE event_type='DECISION_RECORDED'")
        decided = set(cur.fetchall())

    rows = []
    for tender_id in list_tenders(conn)["tenders"]:
        found = active_pack(conn, tender_id)
        obligations = {r["id"]: r["obligation"] for r in found[1]["requirements"]} if found else {}
        for b in _list_tender_bidders(tender_id, conn)["bidders"]:
            bidder_id = b["bidder_id"]
            mandatory_bad = sum(
                1 for v in b["verdicts"]
                if obligations.get(v["requirement_id"]) == "mandatory"
                and v["verdict_effective"] in ("FAIL", "UNKNOWN"))
            rows.append({
                "tender_id": tender_id, "bidder_id": bidder_id,
                "status": _bidder_submission_status(conn, tender_id, bidder_id),
                "risk": b["risk"], "collusion": b["collusion"],
                "mandatory_fail_or_unknown_count": mandatory_bad,
                "needs_decision": (tender_id, bidder_id) not in decided,
            })
    return {"bidders": rows}


# --- officer actions ----------------------------------------------------------

@app.post("/bidders/{bidder_id}/decision", status_code=201)
def record_decision(bidder_id: str, tender_id: str, body: DecisionIn, conn=Depends(db),
                    user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    """The officer decides. The system never disqualifies anyone -- it hands
    over a defensible dossier and records what the human did with it. Any
    authenticated officer may record a decision -- unlike overriding a
    verdict or adopting a rule pack, this isn't gated to SENIOR_OFFICER."""
    snapshot = get_bidder(bidder_id, tender_id, conn)
    rec = append(conn, event_type="DECISION_RECORDED",
                 actor=Actor("HUMAN", user.username), correlation_id=str(uuid.uuid4()),
                 tender_id=tender_id, bidder_id=bidder_id,
                 payload={"decision": body.decision, "officer_id": user.username,
                          "note": body.note, "metrics": snapshot["metrics"],
                          "risk": snapshot["risk"]})
    return {"seq": rec["seq"], "hash": rec["hash"], "decision": body.decision}


@app.post("/bidders/{bidder_id}/override", status_code=201)
def override(bidder_id: str, tender_id: str, body: OverrideIn, conn=Depends(db),
            user: User = Depends(require_role(Role.SENIOR_OFFICER))) -> dict[str, Any]:
    """An officer may overrule the system. The system remembers that they did,
    and keeps its own conclusion alongside theirs. Requires SENIOR_OFFICER or
    higher -- overruling the deterministic core is deliberately not a base-
    OFFICER action."""
    rec = append(conn, event_type="VERDICT_OVERRIDDEN",
                 actor=Actor("HUMAN", user.username), correlation_id=str(uuid.uuid4()),
                 tender_id=tender_id, bidder_id=bidder_id,
                 payload={"requirement_id": body.requirement_id,
                          "verdict_after": body.verdict_after,
                          "officer_id": user.username,
                          "justification": body.justification})
    rebuild_projections_for_bidder(conn, bidder_id)
    return {"seq": rec["seq"], "hash": rec["hash"]}


# --- audit --------------------------------------------------------------------

@app.get("/audit/export", response_class=PlainTextResponse)
def audit_export(conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> str:
    """JSON Lines, one event per line in seq order. This is the artefact a third
    party verifies without any access to the database or to us."""
    return "\n".join(export_jsonl(conn))


@app.get("/audit/verify")
def audit_verify(conn=Depends(db), _user: User = Depends(require_role(Role.OFFICER))) -> dict[str, Any]:
    report = verify_chain(list(export_jsonl(conn)))
    return {"intact": report.intact, "events": report.events,
            "linked": report.linked, "rehashed": report.rehashed,
            "breaks": [{"seq": s, "detail": d} for s, d in report.breaks]}
