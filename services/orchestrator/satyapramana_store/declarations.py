"""The one piece shared between rulepacks.py (which needs to say what
evidence path a DECLARATION requirement produces) and evidence.py (which
needs to fold a real DECLARATION_RECORDED event into that same path):
turning a requirement's own id into a schema-legal field name.

Field-path grammar (schemas/rule_pack.schema.json's `operand.field`
pattern) only allows lowercase alphanumeric/underscore segments starting
with a letter. This project's own requirement-id convention used
everywhere else -- "R1", "R4.1" -- is neither: uppercase, and a dotted id
like "R4.1" would split into a segment ("1") that starts with a digit.
Embedding a requirement's real id directly in a field path is otherwise
exactly right (round 9's design: a requirement can only ever satisfy its
own declaration, never another's) -- it just needs a schema-legal name,
not a literal substitution.

frontend/src/features/RequirementBuilder.jsx mirrors this transform in
JS (the same "ported byte-for-byte" convention validation.js already
uses for gstin_check_digit) so what an officer sees in the builder
matches what the backend actually validates against.
"""
from __future__ import annotations

import re

_NOT_SAFE = re.compile(r"[^a-z0-9]+")


def declaration_field(requirement_id: str) -> str:
    """bidder.declarations.req_<slug>, where <slug> is `requirement_id`
    lowercased with every run of non-alphanumeric characters (including
    the dot in "R4.1") collapsed to one underscore. The "req_" prefix
    guarantees the segment starts with a letter even when the id itself
    starts with a digit; a requirement id with no alphanumeric characters
    at all falls back to "x" rather than producing a degenerate
    "bidder.declarations.req_" nothing could ever match."""
    slug = _NOT_SAFE.sub("_", requirement_id.strip().lower()).strip("_") or "x"
    return f"bidder.declarations.req_{slug}"
