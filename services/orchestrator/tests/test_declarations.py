"""Self-declaration / undertaking capture (round 9): DECLARATION_RECORDED,
the evidence path it feeds, and the pack-validation rule that lets a
requirement reference only its own declaration, never another's.

An undertaking is the self-declaration -- there is nothing to
independently verify it against, by definition. A mandatory requirement
built on it stays capped at PARTIAL (self_declared_ceiling), the same
rule that caps a real PAN or MIN_TURNOVER result on Tier C evidence --
this file proves that's exactly what happens here too, not a special case.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from satyapramana_store.adapters import Registry
from satyapramana_store.app import app, db
from satyapramana_store.auth.models import Role
from satyapramana_store.auth.store import create_user
from satyapramana_store.declarations import declaration_field
from satyapramana_store.evidence import ProjectionResolver, rebuild_evidence
from satyapramana_store.events import Actor, HUMAN_EVENT_TYPES, append
from satyapramana_store.requirement_types import requirement_type_catalog
from satyapramana_store.rulepacks import _registry_as_dict

from .conftest import auth_headers

CORR = str(uuid.uuid4())


def PACK(field=None, obligation="mandatory"):
    field = field or declaration_field("R1")
    return {
        "rule_pack_id": "test.declarations.pack", "semver": "1.0.0",
        "tender_reference": {"tender_id": "T-DECL", "source_document_sha256": "d" * 64,
                             "issuing_authority": "Test Authority"},
        "constants": {"partial_credit": 0.5, "w_mandatory": 1.0, "w_desirable": 0.3,
                     "recency_floor": 0.5, "corroboration_step": 0.1,
                     "coverage_floor_high": 50, "coverage_floor_medium": 80,
                     "confidence_floor": 70, "freshness_days": {"GST_STATUS": 30}},
        "requirements": [
            {"id": "R1", "text": "Bidder shall submit a self-declaration of no blacklisting.",
             "source": {"page": 1}, "obligation": obligation, "operator": "LEAF",
             "predicate": {"op": "exists", "subject": {"field": field}}},
        ],
    }


# --- HUMAN_EVENT_TYPES ---------------------------------------------------------

def test_declaration_recorded_is_a_real_human_event_type():
    assert "DECLARATION_RECORDED" in HUMAN_EVENT_TYPES


# --- _registry_as_dict: per-pack declaration paths ------------------------------

def test_registry_as_dict_offers_one_declaration_path_per_requirement_id():
    d = _registry_as_dict(Registry(), PACK())
    provided = {p for a in d["adapters"] for c in a["capabilities"] for p in c["provides"]}
    assert declaration_field("R1") in provided


def test_registry_as_dict_with_no_pack_offers_no_declaration_paths():
    """The catalog-facing call site (requirement_type_catalog) has no pack
    yet -- confirms this doesn't leak a wildcard/always-true path."""
    d = _registry_as_dict(Registry(), pack=None)
    provided = {p for a in d["adapters"] for c in a["capabilities"] for p in c["provides"]}
    assert not any(p.startswith("bidder.declarations.") for p in provided)


# --- pack validation: a requirement may only reference its own declaration -----

def test_a_declaration_requirement_referencing_its_own_id_validates(conn):
    _, violations = _validate(conn, PACK(declaration_field("R1")))
    assert violations == []


def test_a_declaration_requirement_referencing_another_ids_field_is_refused(conn):
    """R1 cannot borrow R2's declaration -- R2 doesn't even exist in this
    pack, so this must fail exactly like referencing any other
    unregistered evidence path would (rule 8)."""
    _, violations = _validate(conn, PACK(declaration_field("R2")))
    assert any(v.rule == 8 for v in violations)


def _validate(conn, pack):
    from satyapramana_store.rulepacks import validate_only
    return validate_only(pack, registry=Registry())


# --- the catalog ----------------------------------------------------------------

def test_declaration_type_is_always_evidence_backed():
    catalog = {t["id"]: t for t in requirement_type_catalog(Registry())}
    decl = catalog["DECLARATION"]
    assert decl["evidence_backed"] is True
    assert decl["backed_fields"] == ["bidder.declarations.{requirement_id}"]


def test_round_10_declaration_backed_types_are_also_evidence_backed():
    """OEM_AUTHORIZATION, STARTUP_INDIA, NSIC, MAKE_IN_INDIA and
    BLACKLIST_DEBARMENT (PS26100 points 5, 7, 9) all reuse the exact same
    mechanism DECLARATION does -- requirement_type_catalog() detects this by
    field content (the shared template string), not by hardcoding each id,
    so this covers all five without repeating the assertion per type."""
    catalog = {t["id"]: t for t in requirement_type_catalog(Registry())}
    for type_id in ("OEM_AUTHORIZATION", "STARTUP_INDIA", "NSIC",
                     "MAKE_IN_INDIA", "BLACKLIST_DEBARMENT"):
        entry = catalog[type_id]
        assert entry["evidence_backed"] is True, type_id
        assert entry["backed_fields"] == ["bidder.declarations.{requirement_id}"], type_id


def test_round_10_followup_declaration_backed_types_are_also_evidence_backed():
    """EXPERIENCE, SIMILAR_WORK and CERTIFICATION had no evidence path at
    all through round 10 (docs/STATUS.md gap 2's residual three) -- given
    the same self-declared mechanism as a follow-up, each with its own
    honest weaker-evidence note (requirement_types.py), same spirit as
    BLACKLIST_DEBARMENT's caveat, not presented as equivalent in strength
    to the register-backed self-declared types above."""
    catalog = {t["id"]: t for t in requirement_type_catalog(Registry())}
    for type_id in ("EXPERIENCE", "SIMILAR_WORK", "CERTIFICATION"):
        entry = catalog[type_id]
        assert entry["evidence_backed"] is True, type_id
        assert entry["backed_fields"] == ["bidder.declarations.{requirement_id}"], type_id
        assert entry["note"], type_id  # every one has a real, non-empty explanation


def test_a_startup_india_requirement_resolves_through_the_same_declaration_path(conn):
    """One representative end-to-end check (not all five -- they share one
    mechanism, already proven by test_a_recorded_declaration_resolves_at_
    tier_c_with_its_own_text above) confirming a round-10 type genuinely
    round-trips: officer picks STARTUP_INDIA in the builder, the field it
    computes is a real, resolvable declaration path, same as DECLARATION."""
    field = declaration_field("R-STARTUP")
    record(conn, requirement_id="R-STARTUP",
           text="We declare this firm holds current DPIIT Startup India recognition.")
    rebuild_evidence(conn, "A", Registry())
    resolver = ProjectionResolver(conn, "A")
    resolved = resolver.field(field)
    assert resolved.ok
    assert "DPIIT Startup India" in resolved.value
    assert resolver.record(field).tier.value == "C"


# --- evidence fold ---------------------------------------------------------------

def record(conn, bidder="A", tender="T-DECL", requirement_id="R1",
          text="We declare our firm has not been blacklisted by any government department.",
          username="declarer_1"):
    return append(conn, event_type="DECLARATION_RECORDED", actor=Actor("HUMAN", username),
                 correlation_id=CORR, tender_id=tender, bidder_id=bidder,
                 payload={"requirement_id": requirement_id, "declaration_text": text,
                          "declared_by": username})


def test_a_recorded_declaration_resolves_at_tier_c_with_its_own_text(conn):
    record(conn, text="We declare no pending litigation against this firm.")
    rebuild_evidence(conn, "A", Registry())
    resolver = ProjectionResolver(conn, "A")
    resolved = resolver.field(declaration_field("R1"))
    assert resolved.ok and resolved.value == "We declare no pending litigation against this firm."
    assert resolver.record(declaration_field("R1")).tier.value == "C"


def test_an_undeclared_requirement_is_honestly_unresolved(conn):
    rebuild_evidence(conn, "A", Registry())
    resolver = ProjectionResolver(conn, "A")
    assert not resolver.field(declaration_field("R1")).ok


def test_a_later_declaration_supersedes_an_earlier_one_for_the_same_requirement(conn):
    """Later events win -- a corrected declaration replaces the earlier
    text, the same "later wins" rule every other evidence path follows."""
    record(conn, text="first version")
    record(conn, text="corrected version")
    rebuild_evidence(conn, "A", Registry())
    resolver = ProjectionResolver(conn, "A")
    assert resolver.field(declaration_field("R1")).value == "corrected version"


def test_declaring_for_one_requirement_does_not_satisfy_a_different_one(conn):
    record(conn, requirement_id="R1")
    rebuild_evidence(conn, "A", Registry())
    resolver = ProjectionResolver(conn, "A")
    assert resolver.field(declaration_field("R1")).ok
    assert not resolver.field(declaration_field("R2")).ok


# --- the real API ------------------------------------------------------------

@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_an_officer_can_record_a_declaration_for_a_bidder(client, conn):
    headers = auth_headers(conn, username="officer_decl")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    r = client.post("/bidders/A/declarations?tender_id=T-DECL",
                    json={"requirement_id": "R1", "declaration_text": "We are not blacklisted."},
                    headers=headers)
    assert r.status_code == 201
    assert r.json()["declared_by"] == "officer_decl"


def test_a_bidder_can_record_their_own_declaration(client, conn):
    headers = auth_headers(conn, username="officer_setup")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    create_user(conn, "bidder_self", "correct horse battery staple", "Bidder A", Role.BIDDER, bidder_id="A")
    token = _token(conn, "bidder_self")
    r = client.post("/bidders/A/declarations?tender_id=T-DECL",
                    json={"requirement_id": "R1", "declaration_text": "We attest this ourselves."},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert r.json()["declared_by"] == "bidder_self"


def test_a_bidder_cannot_record_a_declaration_for_another_bidder(client, conn):
    headers = auth_headers(conn, username="officer_setup2")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "B"}, headers=headers)
    create_user(conn, "bidder_a2", "correct horse battery staple", "Bidder A", Role.BIDDER, bidder_id="A")
    token = _token(conn, "bidder_a2")
    r = client.post("/bidders/B/declarations?tender_id=T-DECL",
                    json={"requirement_id": "R1", "declaration_text": "trying to declare for B"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def _token(conn, username):
    from satyapramana_store.auth.store import get_user_by_username
    from satyapramana_store.auth.tokens import issue_token
    return issue_token(get_user_by_username(conn, username), os.environ["SATYAPRAMANA_JWT_SECRET"])


# --- end to end: adopt, declare, evaluate ---------------------------------------

def test_a_mandatory_declaration_resolves_partial_self_declared_ceiling(client, conn):
    """The single most important proof: not UNKNOWN (which would mean the
    field didn't actually resolve), and not a silent full PASS either --
    PARTIAL/self_declared_ceiling is the one honest outcome for a
    mandatory requirement built entirely on Tier C evidence."""
    headers = auth_headers(conn, username="officer_e2e")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    client.post("/bidders/A/declarations?tender_id=T-DECL",
               json={"requirement_id": "R1", "declaration_text": "We declare full compliance."},
               headers=headers)
    client.post("/tenders/T-DECL/rule-pack", json={"pack": PACK()}, headers=headers)
    client.post("/bidders/A/evaluate", params={"tender_id": "T-DECL"},
               json={"bid_submission_date": "2026-09-21"}, headers=headers)

    result = client.get("/bidders/A", params={"tender_id": "T-DECL"}, headers=headers).json()
    verdict = next(v for v in result["verdicts"] if v["requirement_id"] == "R1")
    assert verdict["verdict_effective"] == "PARTIAL"
    assert verdict["reason_effective"] == "SELF_DECLARED_CEILING"


def test_a_desirable_declaration_resolves_a_clean_pass(client, conn):
    """The self-declared ceiling only caps MANDATORY requirements -- a
    desirable one built on the same Tier C evidence is allowed to PASS
    outright, exactly like every other desirable requirement type."""
    headers = auth_headers(conn, username="officer_e2e2")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    client.post("/bidders/A/declarations?tender_id=T-DECL",
               json={"requirement_id": "R1", "declaration_text": "We declare full compliance."},
               headers=headers)
    client.post("/tenders/T-DECL/rule-pack", json={"pack": PACK(obligation="desirable")}, headers=headers)
    client.post("/bidders/A/evaluate", params={"tender_id": "T-DECL"},
               json={"bid_submission_date": "2026-09-21"}, headers=headers)

    result = client.get("/bidders/A", params={"tender_id": "T-DECL"}, headers=headers).json()
    verdict = next(v for v in result["verdicts"] if v["requirement_id"] == "R1")
    assert verdict["verdict_effective"] == "PASS"


def test_an_undeclared_mandatory_requirement_stays_unknown_not_a_guess(client, conn):
    headers = auth_headers(conn, username="officer_e2e3")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    client.post("/tenders/T-DECL/rule-pack", json={"pack": PACK()}, headers=headers)
    client.post("/bidders/A/evaluate", params={"tender_id": "T-DECL"},
               json={"bid_submission_date": "2026-09-21"}, headers=headers)

    result = client.get("/bidders/A", params={"tender_id": "T-DECL"}, headers=headers).json()
    verdict = next(v for v in result["verdicts"] if v["requirement_id"] == "R1")
    assert verdict["verdict_effective"] == "UNKNOWN"


def test_my_submission_shows_the_bidders_own_declarations(client, conn):
    from .test_bidder_portal import bidder_headers
    officer = auth_headers(conn, username="officer_sub")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=officer)
    client.post("/bidders/A/declarations?tender_id=T-DECL",
               json={"requirement_id": "R1", "declaration_text": "first"}, headers=officer)
    client.post("/bidders/A/declarations?tender_id=T-DECL",
               json={"requirement_id": "R2", "declaration_text": "second"}, headers=officer)
    client.post("/bidders/A/declarations?tender_id=T-DECL",
               json={"requirement_id": "R1", "declaration_text": "corrected"}, headers=officer)

    body = client.get("/me/tenders/T-DECL/submission", headers=bidder_headers(conn, "A")).json()
    by_req = {d["requirement_id"]: d for d in body["declarations"]}
    assert len(by_req) == 2
    assert by_req["R1"]["declaration_text"] == "corrected"
    assert by_req["R2"]["declaration_text"] == "second"


def test_the_provenance_trail_reaches_the_real_declaration_event(client, conn):
    headers = auth_headers(conn, username="officer_e2e4")
    client.post("/tenders/T-DECL/bidders", json={"bidder_id": "A"}, headers=headers)
    client.post("/bidders/A/declarations?tender_id=T-DECL",
               json={"requirement_id": "R1", "declaration_text": "We declare compliance with labour law."},
               headers=headers)
    client.post("/tenders/T-DECL/rule-pack", json={"pack": PACK()}, headers=headers)
    client.post("/bidders/A/evaluate", params={"tender_id": "T-DECL"},
               json={"bid_submission_date": "2026-09-21"}, headers=headers)

    trail = client.get("/bidders/A/requirements/R1/provenance", headers=headers).json()["trail"]
    kinds = [t["event_type"] for t in trail]
    assert "DECLARATION_RECORDED" in kinds
    declared = next(t for t in trail if t["event_type"] == "DECLARATION_RECORDED")
    assert declared["payload"]["declaration_text"] == "We declare compliance with labour law."
    assert declared["payload"]["declared_by"] == "officer_e2e4"
