"""The role scale. Three tiers, ordered: OFFICER < SENIOR_OFFICER < ADMIN.
Every higher tier can do everything a lower tier can -- there is no
orthogonal permission axis yet, on purpose, until a real deployment surfaces
a need for one that a total order can't express.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    OFFICER = "OFFICER"
    SENIOR_OFFICER = "SENIOR_OFFICER"
    ADMIN = "ADMIN"


_ORDER = {Role.OFFICER: 0, Role.SENIOR_OFFICER: 1, Role.ADMIN: 2}


def role_at_least(role: Role, minimum: Role) -> bool:
    return _ORDER[role] >= _ORDER[minimum]


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: Role
    disabled: bool
