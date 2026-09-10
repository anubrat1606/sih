"""Loading the capability registry and resolving capabilities to adapters.

The rule engine does not reference adapters. It references *capabilities*. An
adapter is merely something that currently provides some, which is what makes
moving GST from an aggregator to a direct GSTN connection a one-field manifest
change.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from satyapramana.verdicts import Channel, Tier

from .base import (
    Basis, Capability, CapabilityManifest, Failure, FailureCode,
    VerificationAdapter, VerificationRequest,
)

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[4] / "schemas" / "capability_registry.json"
)


def load_manifest(data: Mapping) -> CapabilityManifest:
    return CapabilityManifest(
        adapter_id=data["adapter_id"],
        adapter_version=data["adapter_version"],
        authority=data.get("authority"),
        intermediary=data.get("intermediary"),
        identifier_queryable=data.get("identifier_queryable", True),
        capabilities=tuple(
            Capability(
                capability_id=c["capability_id"],
                provides=tuple(c["provides"]),
                tier=Tier(c["tier"]),
                channel=Channel(c["channel"]),
                as_of_supported=c["as_of_supported"],
                freshness_days=c["freshness_days"],
                not_found_is_negative=c.get("not_found_is_negative", False),
                not_found_justification=c.get("not_found_justification"),
                lawful_bases=tuple(Basis(b) for b in c.get("lawful_bases", [])),
                status=c.get("status", "AWAITING_CREDENTIALS"),
                unavailable_reason=c.get("unavailable_reason"),
            )
            for c in data.get("capabilities", [])
        ),
    )


class NullAdapter:
    """A missing integration, stated out loud.

    Not a mock and not an omission: a registered adapter with an empty
    capability list that honestly returns NOT_CAPABLE. Being explicit buys real
    things -- the UI can say "EPFO establishment verification: no lawful
    programmatic source available" rather than silently having no row, and
    Coverage still counts the requirement in its denominator, so the unverified
    remainder stays visible.
    """

    def __init__(self, manifest: CapabilityManifest, reason: str | None = None):
        self.manifest = manifest
        self.reason = reason or (
            f"{manifest.authority or manifest.adapter_id}: no lawful "
            "programmatic source available"
        )

    def verify(self, request: VerificationRequest) -> Failure:
        return Failure(FailureCode.NOT_CAPABLE, self.reason)


class UnconfiguredAdapter:
    """A capability that exists but has no credentials yet.

    Distinct from NullAdapter on purpose: "we have not bought an account" and
    "no lawful source exists" are different facts, and an officer deserves to
    be told which. Both resolve to UNKNOWN.
    """

    def __init__(self, manifest: CapabilityManifest):
        self.manifest = manifest

    def verify(self, request: VerificationRequest) -> Failure:
        return Failure(
            FailureCode.UNAUTHORIZED,
            f"{self.manifest.adapter_id}: awaiting credentials for "
            f"{request.capability_id}; no verification was attempted",
        )


class Registry:
    def __init__(self, adapters: Iterable[VerificationAdapter] = ()):
        self._adapters: list[VerificationAdapter] = list(adapters)

    @classmethod
    def from_file(cls, path: Path | str | None = None) -> "Registry":
        data = json.loads(Path(path or DEFAULT_REGISTRY).read_text())
        adapters: list[VerificationAdapter] = []
        for entry in data["adapters"]:
            manifest = load_manifest(entry)
            if manifest.is_null:
                adapters.append(NullAdapter(manifest))
            else:
                adapters.append(UnconfiguredAdapter(manifest))
        return cls(adapters)

    def register(self, adapter: VerificationAdapter) -> None:
        """Replace the placeholder for the same adapter_id, if any. This is the
        whole plug-in point: configure a real aggregator and it takes over the
        capabilities its manifest declares, touching nothing else."""
        self._adapters = [
            a for a in self._adapters
            if a.manifest.adapter_id != adapter.manifest.adapter_id
        ]
        self._adapters.append(adapter)

    @property
    def adapters(self) -> tuple[VerificationAdapter, ...]:
        return tuple(self._adapters)

    def capabilities(self) -> dict[str, tuple[VerificationAdapter, Capability]]:
        out: dict[str, tuple[VerificationAdapter, Capability]] = {}
        for adapter in self._adapters:
            for cap in adapter.manifest.capabilities:
                out[cap.capability_id] = (adapter, cap)
        return out

    def for_capability(self, capability_id: str):
        return self.capabilities().get(capability_id)

    def for_path(self, evidence_path: str):
        """Which capability produces this evidence path? This is what rule pack
        validation rule 8 resolves against."""
        for adapter in self._adapters:
            for cap in adapter.manifest.capabilities:
                if evidence_path in cap.provides:
                    return adapter, cap
        return None

    def provided_paths(self) -> set[str]:
        return {
            path
            for a in self._adapters
            for c in a.manifest.capabilities
            for path in c.provides
        }

    def coverage_report(self) -> list[dict]:
        """What an officer is shown about the state of verification itself.

        At v1 most rows say AWAITING_CREDENTIALS, and rendering that honestly is
        more impressive than faking coverage.
        """
        rows = []
        for adapter in self._adapters:
            if adapter.manifest.is_null:
                rows.append({
                    "adapter_id": adapter.manifest.adapter_id,
                    "authority": adapter.manifest.authority,
                    "capability_id": None,
                    "status": "UNAVAILABLE",
                    "detail": getattr(adapter, "reason", "no capabilities declared"),
                })
                continue
            for cap in adapter.manifest.capabilities:
                rows.append({
                    "adapter_id": adapter.manifest.adapter_id,
                    "authority": adapter.manifest.authority,
                    "capability_id": cap.capability_id,
                    "status": cap.status,
                    "tier": cap.tier.value,
                    "channel": cap.channel.value,
                    "as_of_supported": cap.as_of_supported,
                    "detail": cap.unavailable_reason,
                })
        return rows
