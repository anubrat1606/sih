"""The verification adapter interface. docs/ADAPTERS.md.

The one rule that shapes everything here:

    An adapter never emits a verdict. It emits observations.

An adapter has no access to the rule pack and no knowledge of thresholds. It
cannot know whether 2.4 crore of turnover passes, because that fact lives in
versioned data it never sees. That is what makes swapping an authority a
manifest change rather than a code change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from satyapramana.verdicts import ADAPTER_FAILURE_REASON, Channel, Reason, Tier


class FailureCode(str, Enum):
    """docs/ADAPTERS.md section 5. Total, and one-way: no code maps to PASS.

    None maps to FAIL either -- the sole exception is a capability that declares
    not_found_is_negative with a written justification, handled in outcomes.py.
    A source being down is not evidence against a bidder.
    """
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    MALFORMED = "MALFORMED"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_CAPABLE = "NOT_CAPABLE"
    AS_OF_UNSUPPORTED = "AS_OF_UNSUPPORTED"

    @property
    def reason(self) -> Reason:
        return ADAPTER_FAILURE_REASON[self.value]


class Basis(str, Enum):
    TENDER_EVALUATION = "TENDER_EVALUATION"
    BIDDER_CONSENT = "BIDDER_CONSENT"
    PUBLIC_REGISTER = "PUBLIC_REGISTER"


@dataclass(frozen=True)
class LawfulBasis:
    """Recorded on the verification event, never inferred."""
    basis: Basis
    requested_by: str
    purpose: str
    consent_reference: str | None = None

    def __post_init__(self) -> None:
        # Concretely this matters for the API Setu / DigiLocker route, which is
        # consent-based by design: those calls are only lawful with a consent
        # artefact, and the artefact must be citable later.
        if self.basis is Basis.BIDDER_CONSENT and not self.consent_reference:
            raise ValueError(
                "BIDDER_CONSENT requires a consent_reference -- this is a "
                "validation error, not a warning"
            )


@dataclass(frozen=True)
class Observation:
    """A fact an authority reported. Not a verdict."""
    path: str
    value: Any
    tier: Tier
    channel: Channel
    #: 1.0 for an exact statutory-identifier match; 0.0 when nothing matched.
    #: Values between are reserved for name-only sources, which must declare
    #: identifier_queryable: false and may never alone establish a Tier A fact.
    subject_match_confidence: float = 1.0


@dataclass(frozen=True)
class VerificationRequest:
    capability_id: str
    subject: Mapping[str, str]
    lawful_basis: LawfulBasis
    as_of: date | None = None


@dataclass(frozen=True)
class Success:
    observations: tuple[Observation, ...]
    raw_response_ref: str
    #: When WE asked.
    observed_at: datetime
    #: The date the AUTHORITY says its answer is as of. A different fact from
    #: observed_at, and conflating them is a real evidentiary error: freshness
    #: is computed from this one.
    source_asserted_at: date | None = None


@dataclass(frozen=True)
class Failure:
    code: FailureCode
    #: The real error, never a paraphrase.
    detail: str
    raw_response_ref: str | None = None
    retry_after: datetime | None = None

    @property
    def reason(self) -> Reason:
        return self.code.reason


VerificationOutcome = Success | Failure


@dataclass(frozen=True)
class Capability:
    capability_id: str
    provides: tuple[str, ...]
    tier: Tier
    channel: Channel
    as_of_supported: bool
    freshness_days: int
    not_found_is_negative: bool = False
    not_found_justification: str | None = None
    lawful_bases: tuple[Basis, ...] = ()
    status: str = "AWAITING_CREDENTIALS"
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.not_found_is_negative and not self.not_found_justification:
            raise ValueError(
                f"{self.capability_id}: not_found_is_negative requires a written "
                "justification naming the register and why its coverage is "
                "complete -- it is never inferred"
            )

    @property
    def live(self) -> bool:
        return self.status == "LIVE"


@dataclass(frozen=True)
class CapabilityManifest:
    adapter_id: str
    adapter_version: str
    capabilities: tuple[Capability, ...] = ()
    authority: str | None = None
    intermediary: str | None = None
    identifier_queryable: bool = True

    def __post_init__(self) -> None:
        if any(c.channel is Channel.AGGREGATOR for c in self.capabilities):
            if not self.intermediary:
                raise ValueError(
                    f"{self.adapter_id}: a capability declares channel "
                    "AGGREGATOR but the manifest names no intermediary"
                )

    @property
    def is_null(self) -> bool:
        """A missing integration is a registered adapter with an empty
        capability list -- not an omission, and not a mock."""
        return not self.capabilities


class VerificationAdapter(Protocol):
    manifest: CapabilityManifest

    def verify(self, request: VerificationRequest) -> VerificationOutcome: ...
