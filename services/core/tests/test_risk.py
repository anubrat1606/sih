"""Risk classification is deterministic and never a model's opinion."""
from satyapramana.metrics import Constants, RequirementResult, compute
from satyapramana.risk import ConflictSignals, RiskLevel, classify
from satyapramana.verdicts import Channel, Obligation, Tier, Verdict

C = Constants()
M, D = Obligation.MANDATORY, Obligation.DESIRABLE


def r(verdict, obligation=M, **kw):
    kw.setdefault("covered", True)
    kw.setdefault("tier", Tier.A)
    kw.setdefault("channel", Channel.DIRECT)
    return RequirementResult("R", verdict, obligation, **kw)


def assess(results, signals=ConflictSignals()):
    return classify(results, compute(results, C), signals, C)


def test_a_clean_bid_is_low_risk():
    assert assess([r(Verdict.PASS), r(Verdict.PASS)]).level is RiskLevel.LOW


def test_a_failed_mandatory_requirement_is_high():
    assert assess([r(Verdict.PASS), r(Verdict.FAIL)]).level is RiskLevel.HIGH


def test_an_unverified_mandatory_requirement_is_also_high():
    """'We could not verify a mandatory requirement' is a serious procurement
    risk even though it is not a compliance failure. This is where UNKNOWN is
    kept distinct from FAIL while still being taken seriously."""
    a = assess([r(Verdict.PASS), r(Verdict.UNKNOWN, covered=False)])
    assert a.level is RiskLevel.HIGH
    assert "unverified" in " ".join(a.triggers)


def test_unknown_is_not_reported_as_a_failure():
    a = assess([r(Verdict.UNKNOWN, covered=False)])
    assert "failed" not in " ".join(a.triggers)


def test_a_collusion_link_is_high():
    a = assess([r(Verdict.PASS)], ConflictSignals(collusion_edge=True))
    assert a.level is RiskLevel.HIGH
    assert any("collusion" in t for t in a.triggers)


def test_an_identifier_conflict_is_high():
    assert assess([r(Verdict.PASS)],
                  ConflictSignals(identifier_conflict=True)).level is RiskLevel.HIGH


def test_a_partial_mandatory_requirement_is_medium():
    assert assess([r(Verdict.PASS), r(Verdict.PARTIAL)]).level is RiskLevel.MEDIUM


def test_sole_self_declaration_on_a_mandatory_requirement_is_medium():
    a = assess([r(Verdict.PASS)],
               ConflictSignals(self_declared_mandatory=("R4.3",)))
    assert a.level is RiskLevel.MEDIUM
    assert any("R4.3" in t for t in a.triggers)


def test_low_mandatory_coverage_is_high():
    results = [r(Verdict.PASS, covered=True), r(Verdict.PASS, covered=False),
               r(Verdict.PASS, covered=False)]
    a = assess(results)
    assert a.level is RiskLevel.HIGH


def test_a_failed_desirable_requirement_is_only_medium():
    assert assess([r(Verdict.PASS), r(Verdict.FAIL, D)]).level is RiskLevel.MEDIUM


def test_all_triggers_are_reported_not_just_the_first():
    a = assess([r(Verdict.FAIL), r(Verdict.UNKNOWN, covered=False)],
               ConflictSignals(collusion_edge=True))
    assert len(a.triggers) >= 3


def test_classification_is_deterministic():
    results = [r(Verdict.PASS), r(Verdict.PARTIAL)]
    signals = ConflictSignals(stale_verification=True)
    first = assess(results, signals)
    for _ in range(50):
        assert assess(results, signals) == first


def test_the_risk_function_is_versioned():
    assert assess([r(Verdict.PASS)]).function_version
