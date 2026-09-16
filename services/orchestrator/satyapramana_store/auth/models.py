"""The role scale: BIDDER < OFFICER < SENIOR_OFFICER < ADMIN. Every higher
tier can do everything a lower tier can -- there is no orthogonal
permission axis yet, on purpose, until a real deployment surfaces a need
for one that a total order can't express.

BIDDER sits below OFFICER specifically so every existing
`require_role(Role.OFFICER)` gate keeps excluding bidders with no other
change -- adding a role beneath the floor, not beside it. A bidder is a
real user of this same system (round 6), not a second auth system: same
`users` table, same login, same token shape, one extra nullable
`bidder_id` column linking the account to the bidder record it may act as.
role_at_least() alone is deliberately NOT how bidder-scoped endpoints gate
themselves, though -- "at least BIDDER" is satisfied by every role, which
is backwards for "must literally be a bidder acting as themselves." See
`current_bidder` in app.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    BIDDER = "BIDDER"
    OFFICER = "OFFICER"
    SENIOR_OFFICER = "SENIOR_OFFICER"
    ADMIN = "ADMIN"


_ORDER = {Role.BIDDER: 0, Role.OFFICER: 1, Role.SENIOR_OFFICER: 2, Role.ADMIN: 3}


def role_at_least(role: Role, minimum: Role) -> bool:
    return _ORDER[role] >= _ORDER[minimum]


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: Role
    disabled: bool
    #: Set only for role == BIDDER -- which bidder record this account acts
    #: as. None for every other role, always, even if somehow set in the
    #: database; app.py's current_bidder is the only place this is trusted.
    bidder_id: str | None = None
    #: Only populated by list_users() -- every other constructor (login,
    #: token lookup, create) has no use for it and leaves it None, since
    #: nothing about "when was this account created" belongs in a session.
    created_at: datetime | None = None
