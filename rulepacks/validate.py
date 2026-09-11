#!/usr/bin/env python3
"""Validate a draft rule pack locally -- the exact check
`POST /tenders/{tender_id}/rule-pack` runs, with no server or database.

Usage:
    services/orchestrator/venv/bin/python rulepacks/validate.py path/to/draft.json

Reuses satyapramana.rulepack.validate() and the orchestrator's own
_registry_as_dict() (services/orchestrator/satyapramana_store/rulepacks.py) --
the same registry-shape logic rule 8 is checked against in production, not a
reimplementation that could drift from it. The capability registry is loaded
from schemas/capability_registry.json, the same file the live orchestrator
loads at startup, so "what evidence paths exist" is the real current answer,
not a guess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "core"))
sys.path.insert(0, str(REPO_ROOT / "services" / "orchestrator"))

from satyapramana.rulepack import content_hash, rule_pack_version, validate  # noqa: E402
from satyapramana_store.adapters import Registry  # noqa: E402
from satyapramana_store.rulepacks import _registry_as_dict  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "schemas" / "rule_pack.schema.json"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path-to-draft.json>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        pack = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL  could not read {path}: {exc}")
        return 1

    # Mirrors satyapramana_store/rulepacks.py adopt() exactly: content_hash is
    # computed and injected before validation, never hand-supplied in the
    # draft file, and the schema requires the field to be present.
    body = {k: v for k, v in pack.items() if k != "content_hash"}
    body["content_hash"] = content_hash(body)

    schema = json.loads(SCHEMA_PATH.read_text())
    registry = _registry_as_dict(Registry.from_file())
    violations = validate(body, registry, schema)

    if not violations:
        print(f"PASS  {path}")
        print(f"      would adopt as version: {rule_pack_version(body)}")
        return 0

    print(f"FAIL  {path} -- {len(violations)} violation(s):")
    for v in violations:
        where = f" [{v.requirement_id}]" if v.requirement_id else ""
        print(f"  rule {v.rule}{where}: {v.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
