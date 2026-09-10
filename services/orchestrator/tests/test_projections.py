"""Projections: collusion clusters, provenance, and rebuild determinism."""
import uuid

import pytest

from satyapramana_store import (
    Actor, append, collusion_clusters, provenance_trail, rebuild_projections,
)

SYS = Actor("SYSTEM", "test")
CORR = str(uuid.uuid4())
RPV = "cpcl.tender.2026.gem-x@1.0.0+abc123def456"


def register(conn, tender, bidders):
    with conn.cursor() as cur:
        for b in bidders:
            cur.execute("INSERT INTO bidder_in_tender VALUES (%s,%s)", (tender, b))


def link(conn, tender, a, b, attribute):
    """Record that two bidders share an attribute. The VALUE is not stored --
    only a hash of it. Two bidders sharing a bank account is the finding; the
    account number does not need to enter an immutable log to establish it."""
    return append(conn, event_type="SHARED_ATTRIBUTE_OBSERVED", actor=SYS,
                  correlation_id=CORR, tender_id=tender,
                  payload={"bidder_a": a, "bidder_b": b, "attribute": attribute,
                           "value_sha256": "f" * 64})


def evaluate(conn, tender, bidder, requirement, verdict, reason, causation=None):
    return append(conn, event_type="REQUIREMENT_EVALUATED", actor=SYS,
                  correlation_id=CORR, tender_id=tender, bidder_id=bidder,
                  causation_id=causation,
                  payload={"requirement_id": requirement, "verdict": verdict,
                           "reason_code": reason, "rule_pack_version": RPV})


# --- collusion ----------------------------------------------------------------

def test_a_ring_terminates_and_clusters_correctly(conn):
    """A collusion ring is a cycle. UNION (not UNION ALL) in `reach` is what
    makes the recursion terminate on one."""
    register(conn, "T1", ["A", "B", "C", "D", "E", "F"])
    link(conn, "T1", "A", "B", "phone")
    link(conn, "T1", "B", "C", "address")
    link(conn, "T1", "C", "A", "bank_account")
    link(conn, "T1", "D", "E", "director_name")

    by_id = {c.bidder_id: c for c in collusion_clusters(conn, "T1")}
    assert by_id["A"].cluster_id == by_id["B"].cluster_id == by_id["C"].cluster_id
    assert by_id["A"].cluster_id == "cluster_A_B_C"
    assert by_id["D"].cluster_id == "cluster_D_E"
    assert by_id["F"].flagged is False
    assert all(by_id[x].flagged for x in "ABCDE")


def test_a_transitive_link_is_found(conn):
    """A and C never share an attribute directly, but both share with B."""
    register(conn, "T1", ["A", "B", "C"])
    link(conn, "T1", "A", "B", "phone")
    link(conn, "T1", "B", "C", "address")
    by_id = {c.bidder_id: c for c in collusion_clusters(conn, "T1")}
    assert by_id["A"].members == ("A", "B", "C")


def test_cluster_id_does_not_depend_on_registration_order(conn):
    register(conn, "T1", ["C", "A", "B"])
    link(conn, "T1", "B", "A", "phone")
    link(conn, "T1", "C", "B", "address")
    ids = {c.cluster_id for c in collusion_clusters(conn, "T1")}
    assert ids == {"cluster_A_B_C"}


def test_tenders_are_isolated(conn):
    register(conn, "T1", ["A", "B"])
    register(conn, "T2", ["A", "B"])
    link(conn, "T1", "A", "B", "phone")
    assert all(c.flagged for c in collusion_clusters(conn, "T1"))
    assert not any(c.flagged for c in collusion_clusters(conn, "T2"))


def test_the_shared_value_never_enters_the_log(conn):
    register(conn, "T1", ["A", "B"])
    link(conn, "T1", "A", "B", "bank_account")
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM events "
                    "WHERE event_type='SHARED_ATTRIBUTE_OBSERVED'")
        payload = cur.fetchone()[0]
    assert "value_sha256" in payload and "value" not in payload


def test_a_flag_survives_a_reconnect(conn):
    """The whole point of moving off an in-memory networkx graph."""
    register(conn, "T1", ["A", "B"])
    link(conn, "T1", "A", "B", "phone")
    rebuild_projections(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT flagged, cluster_id FROM proj_collusion "
                    "WHERE bidder_id='A'")
        assert cur.fetchone() == (True, "cluster_A_B")


# --- provenance ---------------------------------------------------------------

def test_the_full_causation_chain_is_walkable(conn):
    doc = append(conn, event_type="DOCUMENT_INGESTED", actor=SYS, correlation_id=CORR,
                 tender_id="T1", bidder_id="A",
                 payload={"storage_ref": "docs/A/gst.pdf", "document_sha256": "9" * 64})
    ext = append(conn, event_type="FIELD_EXTRACTED", actor=Actor("AGENT", "extract@2.1"),
                 correlation_id=CORR, causation_id=doc["event_id"],
                 tender_id="T1", bidder_id="A",
                 payload={"path": "bidder.gst.gstin", "value": "33AAAAA0000A1Z5",
                          "page": 1, "region": [120, 340, 410, 362], "confidence": 0.94})
    ver = append(conn, event_type="VERIFICATION_OBSERVED", actor=Actor("ADAPTER", "gst_status"),
                 correlation_id=CORR, causation_id=ext["event_id"],
                 tender_id="T1", bidder_id="A",
                 payload={"capability_id": "GST_STATUS", "raw_response_ref": "sha256:aa11"})
    fus = append(conn, event_type="EVIDENCE_FUSED", actor=SYS, correlation_id=CORR,
                 causation_id=ver["event_id"], tender_id="T1", bidder_id="A",
                 payload={"path": "bidder.gst.status", "outcome": "AGREEMENT"})
    evaluate(conn, "T1", "A", "R4.1", "PASS", "AUTHORITY_CONFIRMED", fus["event_id"])

    trail = provenance_trail(conn, "A", "R4.1")
    assert [t["event_type"] for t in trail] == [
        "REQUIREMENT_EVALUATED", "EVIDENCE_FUSED", "VERIFICATION_OBSERVED",
        "FIELD_EXTRACTED", "DOCUMENT_INGESTED",
    ]
    # Page and region survive unbroken from ingestion to the rendered chip.
    extraction = trail[3]["payload"]
    assert extraction["page"] == 1 and extraction["region"] == [120, 340, 410, 362]
    assert trail[2]["payload"]["raw_response_ref"] == "sha256:aa11"
    assert trail[4]["payload"]["storage_ref"] == "docs/A/gst.pdf"


def test_every_verdict_records_the_rule_pack_that_produced_it(conn):
    evaluate(conn, "T1", "A", "R4.1", "PASS", "AUTHORITY_CONFIRMED")
    assert provenance_trail(conn, "A", "R4.1")[0]["payload"]["rule_pack_version"] == RPV


# --- overrides ----------------------------------------------------------------

def test_an_override_never_erases_what_the_system_concluded(conn):
    register(conn, "T1", ["A"])
    evaluate(conn, "T1", "A", "R4.1", "FAIL", "AUTHORITY_CONTRADICTED")
    append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
           correlation_id=CORR, tender_id="T1", bidder_id="A",
           payload={"requirement_id": "R4.1", "verdict_after": "PASS",
                    "reason_after": "AUTHORITY_CONFIRMED", "officer_id": "officer_1",
                    "justification": "Original certificate produced in person."})
    rebuild_projections(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT verdict_system, verdict_effective, overridden_by, "
                    "override_justification FROM proj_verdicts WHERE bidder_id='A'")
        system, effective, officer, why = cur.fetchone()
    assert system == "FAIL", "the system's own conclusion is preserved"
    assert effective == "PASS"
    assert officer == "officer_1" and "in person" in why


# --- rebuild determinism ------------------------------------------------------

def test_a_rebuild_from_genesis_reproduces_the_projection(conn):
    """Charter section 3.9, enforced rather than asserted."""
    register(conn, "T1", ["A", "B"])
    link(conn, "T1", "A", "B", "phone")
    for i in range(10):
        evaluate(conn, "T1", "A", f"R{i}", "PASS", "AUTHORITY_CONFIRMED")

    def snapshot():
        with conn.cursor() as cur:
            cur.execute("SELECT bidder_id,requirement_id,verdict_system,"
                        "verdict_effective,rule_pack_version FROM proj_verdicts "
                        "ORDER BY bidder_id,requirement_id")
            verdicts = cur.fetchall()
            cur.execute("SELECT tender_id,bidder_id,flagged,cluster_id "
                        "FROM proj_collusion ORDER BY tender_id,bidder_id")
            return verdicts, cur.fetchall()

    rebuild_projections(conn)
    first = snapshot()
    for _ in range(5):
        rebuild_projections(conn)
        assert snapshot() == first


def test_rebuilding_to_an_earlier_sequence_gives_the_state_at_that_moment(conn):
    """Time travel falls out of the log for free."""
    register(conn, "T1", ["A"])
    early = evaluate(conn, "T1", "A", "R1", "PASS", "AUTHORITY_CONFIRMED")
    evaluate(conn, "T1", "A", "R2", "FAIL", "THRESHOLD_NOT_MET")

    rebuild_projections(conn, up_to_seq=early["seq"])
    with conn.cursor() as cur:
        cur.execute("SELECT requirement_id FROM proj_verdicts ORDER BY requirement_id")
        assert cur.fetchall() == [("R1",)]

    rebuild_projections(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT requirement_id FROM proj_verdicts ORDER BY requirement_id")
        assert cur.fetchall() == [("R1",), ("R2",)]
