# /rulepacks

This folder intentionally starts empty, the same way `/data` does, and for the
same reason: a rule pack encodes what a **real** tender actually requires, and
there is no real tender here yet to encode. Nothing in this repository
fabricates tender clauses, requirement text, or thresholds — see
`CLAUDE.md`'s non-negotiable principle and `docs/RULE_PACKS.md` for the format
this folder holds once there is something real to put in it.

## What belongs here

One JSON file per adopted rule pack version, matching
[`/schemas/rule_pack.schema.json`](../schemas/rule_pack.schema.json) — the
same file a `POST /tenders/{tender_id}/rule-pack` call sends as `pack` in its
body. Content-addressed, versioned, declarative: see `docs/RULE_PACKS.md`
section 1 for the full grammar (`ALL_OF` / `ANY_OF` / `K_OF_N` / `NOT` /
`LEAF`, the predicate language, `source.page` / `source.region` tying every
requirement back to the exact clause it came from).

## The actual workflow, once a real tender PDF exists

1. Read the tender document. For each atomic requirement, note its exact page
   and bounding region (`source`), its obligation (`mandatory` / `desirable`),
   and which evidence field(s) it depends on.
2. Encode it as a predicate over an evidence path already produced by a
   registered capability or the extraction stage — `GET /capabilities` lists
   what's live; `rulepack.capability_paths()` / rule 8 in `docs/RULE_PACKS.md`
   is what the adoption endpoint checks this against. A requirement that
   references a path nothing can produce is refused at adoption, not silently
   left to become a permanent `UNKNOWN` in production.
3. Validate locally before ever calling the API — `validate.py` in this folder
   runs the exact same check `POST /tenders/{id}/rule-pack` does, against the
   real schema and the real live capability registry, with no server or
   database required:

   ```bash
   services/orchestrator/venv/bin/python rulepacks/validate.py path/to/draft.json
   ```

4. Once it validates, `POST` it (via the officer UI's rule-pack adoption form,
   or directly) with a real `officer_id`. Adoption is a recorded human act —
   content hash, officer identity, timestamp — never an anonymous file drop.

## Why this can't be started further than this

Decomposing tender prose into atomic requirements is deliberately a job for a
human plus, per `docs/satyapramana.md` section 5, an LLM that only *proposes*
— deterministic code confirms. Writing a plausible-looking rule pack without a
real tender behind it would be inventing the exact kind of fabricated
authority content this whole project exists to refuse. When there's a real
GeM/CPCL tender PDF to work from, that's the next step here.
