"""Sends the mobile-OTP SMS. Same honest plug-in shape as email_sender.py
and explain/gemini.py -- but unlike email (plain SMTP, a real protocol
every deployment can just configure), SMS delivery only exists through a
paid, provider-specific HTTP API (Twilio, MSG91, etc.), and there is no
provider account or credential available to build and verify a real
integration against here.

Rather than guess at one provider's request/response contract from memory
and risk shipping an integration that looks real but has never actually
been exercised against that provider, this stays honestly unconfigured --
exactly the same choice this project already made for EPFO/ESIC/UDYAM
verification (see adapters/), and for the same reason: "not implemented" is
a different, more trustworthy fact than "implemented, probably correctly".

The OTP itself is fully real: bidder_auth/store.py generates it with
`secrets`, hashes it, rate-limits attempts, and expires it exactly as if
delivery worked. Only the "hand it to a phone" leg is missing. Wiring a real
provider in is one file that implements `.send()`, dropped in the same way
adapters/sandbox_co_in.py plugs into the verification registry -- a
SATYAPRAMANA_SMS_* set of environment variables and an HTTP call, nothing
about the rest of this module needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SmsSendOutcome:
    delivered: bool
    detail: str


class UnconfiguredSmsSender:
    def send(self, *, to_mobile: str, message: str) -> SmsSendOutcome:
        return SmsSendOutcome(
            delivered=False,
            detail="No SMS provider is configured on this deployment -- mobile OTP "
                   "delivery is unavailable. The OTP was still generated and stored "
                   "for real; it cannot reach a phone until an operator configures "
                   "a provider (see bidder_auth/sms_sender.py).",
        )


def build_from_env():
    # No SATYAPRAMANA_SMS_* variables are read anywhere yet -- there is
    # nothing to configure this against today. See the module docstring.
    return UnconfiguredSmsSender()
