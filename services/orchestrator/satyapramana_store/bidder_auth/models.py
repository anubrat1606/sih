"""The bidder account record. Deliberately its own dataclass, not a reuse of
auth.models.User -- a bidder is a different kind of identity (no role, no
username, a verified-contact-channel pair instead), and keeping the two
types distinct is what makes it a type error, not just a convention, to pass
a bidder where officer code expects a User.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BidderAccount:
    id: int
    email: str
    full_name: str
    mobile: str | None
    company_name: str | None
    gstin: str | None
    email_verified: bool
    mobile_verified: bool
    disabled: bool
    google_linked: bool
    created_at: datetime
