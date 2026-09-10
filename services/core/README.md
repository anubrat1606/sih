# services/core — SATYAPRAMĀṆA domain logic

Pure, deterministic, framework-free. No I/O, no database, no HTTP, no model
calls. Everything here is exhaustively testable and is tested that way.

This is the layer charter §5's "tell-tale test" is about: **if you removed every
model from the system, this package still produces correct verdicts on
already-extracted evidence.** Models make the system usable at scale; they do
not make it correct.

| Module | Implements |
|---|---|
| `verdicts.py` | `docs/VERDICT_ALGEBRA.md` §§1–4 — four states, one composition function, the Tier C ceiling, reason codes |
| `metrics.py` | §5 — the three orthogonal metrics |
| `risk.py` | §6 — deterministic risk classification |
| `predicates.py` | `docs/RULE_PACKS.md` §4 — the closed predicate language, three-valued |
| `rulepack.py` | §7 — content addressing and the 13 validation rules |

## Run the tests

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m pytest tests/ -q
```

`tests/test_rulepack.py` reads the real `/schemas/rule_pack.schema.json` and
`/schemas/capability_registry.json`, so the package, the schemas and the adapter
registry are checked against each other rather than in isolation.

## Note on test fixtures

There is no mock, sample or simulated government data here, and none is
permitted. The fixtures are abstract verdict states and locally-constructed
evidence records exercising the evaluator's own logic — never a stand-in for an
authority's response. Charter §3.1 forbids the latter anywhere in this
repository, including in tests that double as demos.

## Invariants worth not breaking

- **Compliance Score is `None`, never `0.0`,** when nothing is determinate.
  A zero reads as "totally non-compliant"; the truth is "nothing could be
  checked". Renderers must show an em dash.
- **Predicates never return `PARTIAL`.** It enters only via the Tier C clamp and
  composition, so every `PARTIAL` on screen has one of two traceable causes.
- **A missing field is `UNKNOWN`, never `False`.** The reason comes from the
  evidence record itself, never guessed by the evaluator.
- **No predicate reads the system clock.** Temporal values come only from
  `EvaluationContext`, which is what makes replay determinism testable.
- **`Metrics` exposes no blended figure**, and a test enforces the absence.
