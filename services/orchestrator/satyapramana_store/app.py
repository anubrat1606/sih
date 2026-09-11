"""FastAPI orchestrator.

Replaces the Express/Mongo layer in /backend. Orchestration only: it calls the
extraction service, drives the adapter layer, folds projections, and serves read
models. It holds no AI logic and no verification logic of its own.

Every state change goes through `append()`. There is no other way to change
compliance state, because there is no code path that writes a verdict directly.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from satyapramana.metrics import Constants, RequirementResult, compute
from satyapramana.predicates import EvaluationContext
from satyapramana.risk import ConflictSignals, classify
from satyapramana.rulepack import derived_bindings
from satyapramana.verdicts import Obligation, Tier, Verdict

from .adapters import Registry, VerificationRequest, failure_to_judgement
from .adapters.base import Basis, LawfulBasis
from .db import connect, migrate
from .decide import fuse_and_evaluate
from .events import Actor, append, export_jsonl, verify_chain
from .evidence import ProjectionResolver, rebuild_evidence
from .explain import Unavailable
from .extract import ingest_document
from .projections import collusion_clusters, provenance_trail, rebuild_projections
from .reporting.bid_autopsy import autopsy
from .reporting.blocker_summary import blocker_summary
from .reporting.compliance_repair import repair_plan
from .reporting.csv_export import bidders_to_csv
from .reporting.dossier import build_dossier, render_dossier_text
from .reporting.evidence_graph import build_evidence_graph
from .reporting.tender_report import render_tender_report_text, tender_report
from .rulepacks import NotAdoptable, active_pack, adopt

@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("SATYAPRAMANA_MIGRATE_ON_START") == "1":
        conn = connect()
        migrate(conn)
        conn.close()
    yield


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
# catch, since none of them enforce CORS the way a real browser does. No auth
# exists in this prototype (out of scope, CLAUDE.md), so a permissive origin
# list costs nothing beyond what already holds; allow_credentials stays False
# since there are no cookies or sessions to protect.
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

# The whole plug-in point (docs/ADAPTERS.md): a real adapter takes over the
# capabilities its manifest declares, and nothing else changes. With no
# SATYAPRAMANA_SANDBOX_* credentials set this is a no-op and PAN_STATUS /
# GST_STATUS stay on the honest UnconfiguredAdapter.
from .adapters.sandbox_co_in import build_from_env as _build_sandbox_adapters  # noqa: E402
for _adapter in _build_sandbox_adapters():
    REGISTRY.register(_adapter)

# Same plug-in shape as the verification adapters above: with no
# SATYAPRAMANA_GEMINI_API_KEY set, EXPLAINER stays on the honest
# UnconfiguredExplainer and /bidders/{id}/explain returns Unavailable rather
# than a fabricated narrative.
from .explain import build_from_env as _build_explainer  # noqa: E402
EXPLAINER = _build_explainer()


def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# --- request models -----------------------------------------------------------

class BidderIn(BaseModel):
    bidder_id: str
    director_name: str | None = None
    address: str | None = None
    phone: str | None = None
    bank_account: str | None = None


class RulePackIn(BaseModel):
    officer_id: str
    pack: dict


class EvaluateIn(BaseModel):
    as_of: date | None = None
    bid_submission_date: date


class DecisionIn(BaseModel):
    officer_id: str
    decision: str = Field(pattern="^(QUALIFY|DISQUALIFY)$")
    note: str | None = None


class OverrideIn(BaseModel):
    officer_id: str
    requirement_id: str
    verdict_after: str = Field(pattern="^(PASS|FAIL|PARTIAL|UNKNOWN)$")
    justification: str = Field(min_length=1)


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
    """Every tender_id that has at least one registered bidder.

    Tenders aren't a first-class entity anywhere in this system (no Tender
    Management module -- see docs/STATUS.md's "declined infrastructure cost").
    A tender_id is just a string threaded through bidder_in_tender, rule_packs
    and the event log. This is a projection over the one table that captures
    every tender's existence, not a new source of truth.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT tender_id FROM bidder_in_tender ORDER BY tender_id")
        return {"tenders": [row[0] for row in cur.fetchall()]}


# --- ingestion ----------------------------------------------------------------

@app.post("/tenders/{tender_id}/bidders", status_code=201)
def register_bidder(tender_id: str, body: BidderIn, conn=Depends(db)) -> dict[str, Any]:
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
def verify(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
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
                       ("pan_date_of_birth", "bidder.pan.date_of_birth")):
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
async def upload_document(bidder_id: str, tender_id: str,
                          declared_type: str | None = None,
                          file: UploadFile = File(...),
                          conn=Depends(db)) -> dict[str, Any]:
    """Ingest a document and extract what can be read from it deterministically.

    For a PDF with a text layer this needs no model at all: identifiers are
    located by grammar, validated structurally, and recorded with the exact page
    and region their characters occupy. A page with no text layer is recorded as
    EXTRACTION_FAILED with a stated reason -- never a guessed value.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    result = ingest_document(conn, tender_id=tender_id, bidder_id=bidder_id,
                             filename=file.filename or "upload.pdf", data=data,
                             declared_type=declared_type)
    rebuild_evidence(conn, bidder_id, REGISTRY)
    return result


@app.get("/documents/{document_sha256}")
def get_document(document_sha256: str, conn=Depends(db)):
    """Serve a previously-ingested document back, for the evidence viewer --
    click a verdict, see the actual highlighted line of the actual PDF
    (satyapramana.md's own stated demo axiom).

    Looked up by content hash, never by a client-supplied filesystem path --
    the client can never name an arbitrary path on disk, only a hash that has
    to match a real DOCUMENT_INGESTED event's storage_ref.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT payload->>'storage_ref' FROM events
               WHERE event_type='DOCUMENT_INGESTED' AND payload->>'document_sha256'=%s
               LIMIT 1""",
            (document_sha256,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "no document with that hash was ever ingested")
    path = row[0]
    if not os.path.isfile(path):
        raise HTTPException(404, "the event log references this document, but it is not on disk here")
    return FileResponse(path, media_type="application/pdf")


# --- rule packs and decision --------------------------------------------------

@app.post("/tenders/{tender_id}/rule-pack", status_code=201)
def adopt_rule_pack(tender_id: str, body: RulePackIn, conn=Depends(db)) -> dict[str, Any]:
    """Adoption is a human act, recorded with the officer's identity, the
    content hash and a timestamp.

    Validation gates it. A pack whose predicates reference evidence paths no
    registered capability can produce is refused here rather than becoming a
    permanent, unexplained UNKNOWN in production -- and a pack carrying an
    unreviewed uncertain requirement cannot be adopted at all.
    """
    try:
        return adopt(conn, body.pack, tender_id=tender_id,
                     officer_id=body.officer_id, registry=REGISTRY)
    except NotAdoptable as exc:
        raise HTTPException(422, {
            "error": "rule pack cannot be adopted",
            "violations": [{"rule": v.rule, "requirement_id": v.requirement_id,
                            "message": v.message} for v in exc.violations],
        }) from exc


@app.post("/bidders/{bidder_id}/evaluate")
def evaluate_bidder_endpoint(bidder_id: str, tender_id: str, body: EvaluateIn,
                             conn=Depends(db)) -> dict[str, Any]:
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
    rebuild_projections(conn)
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


@app.get("/tenders/{tender_id}/bidders")
def list_tender_bidders(tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    """Every bidder registered on this tender, each with the same summary
    `GET /bidders/{id}` returns -- one round trip for a dashboard instead of
    one per card."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bidder_id FROM bidder_in_tender WHERE tender_id=%s ORDER BY bidder_id",
            (tender_id,))
        bidder_ids = [row[0] for row in cur.fetchall()]
    return {"tender_id": tender_id,
            "bidders": [get_bidder(bidder_id, tender_id, conn) for bidder_id in bidder_ids]}


@app.get("/tenders/{tender_id}/report")
def tender_compliance_report(tender_id: str, as_text: bool = False, conn=Depends(db)):
    """Of everyone who bid, where do we stand overall -- the aggregate
    counterpart to a single bidder's Dossier. `?as_text=true` for the
    plain-text rendering."""
    body = list_tender_bidders(tender_id, conn)
    report = tender_report(tender_id, body["bidders"])
    if as_text:
        return PlainTextResponse(render_tender_report_text(report))
    return report


@app.get("/tenders/{tender_id}/report/csv")
def tender_report_csv(tender_id: str, conn=Depends(db)):
    """The same bidder list as `GET /tenders/{tender_id}/bidders`, as CSV --
    the artifact an officer actually takes somewhere: a spreadsheet, an
    email, a physical file. See reporting/csv_export.py."""
    body = list_tender_bidders(tender_id, conn)
    return PlainTextResponse(bidders_to_csv(body["bidders"]), media_type="text/csv")


@app.get("/tenders/{tender_id}/blockers")
def tender_blockers(tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    """Across every bidder on this tender, which requirement is blocking the
    most of them -- aggregating each bidder's own Bid Autopsy. Useful for an
    officer deciding whether a requirement needs relaxing, or which document
    type to chase bidders for. See reporting/blocker_summary.py."""
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    bidder_ids = list_tender_bidders(tender_id, conn)["bidders"]
    autopsies = [bidder_autopsy(b["bidder_id"], tender_id, conn) for b in bidder_ids]
    return {"tender_id": tender_id, "blockers": blocker_summary(autopsies)}


@app.get("/bidders/{bidder_id}")
def get_bidder(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    rebuild_projections(conn)
    verdicts = _fetch_verdict_rows(conn, bidder_id)

    resolver = ProjectionResolver(conn, bidder_id)
    found = active_pack(conn, tender_id)
    obligations, bindings = {}, {}
    if found:
        for req in found[1]["requirements"]:
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
    clusters = {c.bidder_id: c for c in collusion_clusters(conn, tender_id)}
    cluster = clusters.get(bidder_id)
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


# --- reporting: Bid Autopsy and Compliance Repair -----------------------------

@app.get("/bidders/{bidder_id}/autopsy")
def bidder_autopsy(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    """Why would this bid fail, right now. satyapramana.md section 11:
    deterministic, derived from the event log, never regenerated by a model.
    """
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    _, pack = found
    rebuild_projections(conn)
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    return {"bidder_id": bidder_id, "tender_id": tender_id, **autopsy(pack, verdicts)}


@app.get("/bidders/{bidder_id}/repair-plan")
def bidder_repair_plan(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    """The forward-looking inverse of the autopsy: one action per curable gap.
    Fatal findings (positive evidence against the bidder) get no action here --
    the autopsy is where those stay visible."""
    found = active_pack(conn, tender_id)
    if not found:
        raise HTTPException(409, f"no rule pack adopted for tender {tender_id}")
    _, pack = found
    rebuild_projections(conn)
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    return {"bidder_id": bidder_id, "tender_id": tender_id,
            **repair_plan(pack, verdicts, REGISTRY)}


@app.get("/bidders/{bidder_id}/dossier")
def bidder_dossier(bidder_id: str, tender_id: str, as_text: bool = False,
                   conn=Depends(db)):
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
def bidder_explain(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
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
def bidder_evidence(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
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
def bidder_evidence_graph(bidder_id: str, tender_id: str, conn=Depends(db)) -> dict[str, Any]:
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
    rebuild_projections(conn)
    rebuild_evidence(conn, bidder_id, REGISTRY)
    verdicts = _fetch_verdict_rows(conn, bidder_id)
    evidence_by_path = _evidence_by_path(conn, bidder_id)
    graph = build_evidence_graph(pack, verdicts, evidence_by_path, REGISTRY)
    return {"bidder_id": bidder_id, "tender_id": tender_id, **graph}


@app.get("/bidders/{bidder_id}/requirements/{requirement_id}/provenance")
def provenance(bidder_id: str, requirement_id: str, conn=Depends(db)) -> dict[str, Any]:
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
def collusion(tender_id: str, conn=Depends(db)) -> dict[str, Any]:
    clusters = collusion_clusters(conn, tender_id)
    return {"tender_id": tender_id,
            "bidders": [{"bidder_id": c.bidder_id, "flagged": c.flagged,
                         "cluster_id": c.cluster_id, "members": list(c.members)}
                        for c in clusters]}


@app.get("/tenders/{tender_id}/collusion/edges")
def collusion_edges(tender_id: str, conn=Depends(db)) -> dict[str, Any]:
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


# --- officer actions ----------------------------------------------------------

@app.post("/bidders/{bidder_id}/decision", status_code=201)
def record_decision(bidder_id: str, tender_id: str, body: DecisionIn,
                    conn=Depends(db)) -> dict[str, Any]:
    """The officer decides. The system never disqualifies anyone -- it hands
    over a defensible dossier and records what the human did with it."""
    snapshot = get_bidder(bidder_id, tender_id, conn)
    rec = append(conn, event_type="DECISION_RECORDED",
                 actor=Actor("HUMAN", body.officer_id), correlation_id=str(uuid.uuid4()),
                 tender_id=tender_id, bidder_id=bidder_id,
                 payload={"decision": body.decision, "officer_id": body.officer_id,
                          "note": body.note, "metrics": snapshot["metrics"],
                          "risk": snapshot["risk"]})
    return {"seq": rec["seq"], "hash": rec["hash"], "decision": body.decision}


@app.post("/bidders/{bidder_id}/override", status_code=201)
def override(bidder_id: str, tender_id: str, body: OverrideIn,
             conn=Depends(db)) -> dict[str, Any]:
    """An officer may overrule the system. The system remembers that they did,
    and keeps its own conclusion alongside theirs."""
    rec = append(conn, event_type="VERDICT_OVERRIDDEN",
                 actor=Actor("HUMAN", body.officer_id), correlation_id=str(uuid.uuid4()),
                 tender_id=tender_id, bidder_id=bidder_id,
                 payload={"requirement_id": body.requirement_id,
                          "verdict_after": body.verdict_after,
                          "officer_id": body.officer_id,
                          "justification": body.justification})
    rebuild_projections(conn)
    return {"seq": rec["seq"], "hash": rec["hash"]}


# --- audit --------------------------------------------------------------------

@app.get("/audit/export", response_class=PlainTextResponse)
def audit_export(conn=Depends(db)) -> str:
    """JSON Lines, one event per line in seq order. This is the artefact a third
    party verifies without any access to the database or to us."""
    return "\n".join(export_jsonl(conn))


@app.get("/audit/verify")
def audit_verify(conn=Depends(db)) -> dict[str, Any]:
    report = verify_chain(list(export_jsonl(conn)))
    return {"intact": report.intact, "events": report.events,
            "linked": report.linked, "rehashed": report.rehashed,
            "breaks": [{"seq": s, "detail": d} for s, d in report.breaks]}
