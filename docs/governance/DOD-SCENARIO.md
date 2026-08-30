# The Phase-0 DoD scenario

This page describes the repository's dedicated Definition-of-Done CI job — the `dod` job in
`.github/workflows/ci.yml` — which runs SOW §2 criterion 1's end-to-end scenario on every
push: **extract → verify → snapshot → evolve → diff → report** over the travel-booking
tutorial agent, with the five seeded-defect variants and the eight-version evolution
sequence. The acceptance interpretation it is judged against is owner-signed
(PD-006 / PHASE-0-DOD-CHECKLIST, in the delivery repository); this page states what the job
does and what artifacts a scenario run leaves behind.

## What the job runs

One pytest invocation — `python -m pytest tests/dod tests/evolution -q`, issued through
the repository's own reusable CI-gate action (`.github/actions/gebra-gate`, default
`gate` mode; this job is the action's executed reference consumer — see
[docs/ci/github-action.md](../ci/github-action.md)) — on a standard GitHub-hosted
`ubuntu-latest` runner, on the designated blocking matrix cell **py3.13 / cell 3** (Python
3.13 with the `compat-cell-3` frozen substrate pins). The scenario's six legs, in order:

| Leg | What happens | Where |
|---|---|---|
| extract | one `gebra.extract()` per subject: the healthy v1 agent, the five defect variants, the eight evolution stages | `tests/dod/conftest.py` |
| verify | `gebra.verify.verify()` over every subject; the defect-3 leg again under the `determinism-replay` per-property strict promotion | `tests/dod/conftest.py` |
| snapshot | v1 recorded through the eligibility gate — the report handed to `gebra.snapshot.record()`, so the digest the gate saw is the digest stored | `tests/dod/conftest.py` |
| evolve | v2–v8 recorded in sequence; the two FATAL-bearing stages are refused when offered with their reports and land only through the recorder's documented handed-none posture | `tests/dod/conftest.py` |
| diff | every consecutive version pair re-derived from the store's own files via `gebra.lineage.compare()`, held to the recorded S/F/E classes | `tests/dod/test_dod_scenario.py` |
| report | `gebra.audit.export_store()` writes one audit report per stored version; the lineage document is written beside them; `gebra.audit.freshness()` is checked green at the final version | `tests/dod/conftest.py` |

The five seeded defects and the condition each is caught under (the owner-ratified table;
`tests/dod/test_dod_defects.py` asserts property, condition ID, locus and gate per defect,
and is negative-tested — a report in which a defect is absent is refused by the same
checker):

| # | Seeded defect | Property | Condition ID | Gate |
|---|---|---|---|---|
| 1 | cycle without a termination witness | P-02 `termination-witness` | `cycle-without-termination-witness` | exit 1 (fatal) |
| 2 | unprotected retry around `book_flight` | P-06 `effect-safety` | `unprotected-effect-in-retry-region` | exit 1 (error) |
| 3 | incoherent determinism claim on an LLM-backed node | P-08 `determinism-replay` | `deterministic-llm-temperature-unpinned` | exit 1 under `--gebra-strict=determinism-replay`; the record stays warning/heuristic |
| 4 | a node reads state no upstream node supplies | P-04 `dataflow-completeness` | `read-key-never-written-on-path` | exit 1 (fatal) |
| 5 | parallel `Send` fan-out with an unprotected billable worker | P-06 `effect-safety` | `unprotected-effect-in-retry-region`, with `fanout: send` evidence | exit 1 (error) |

P-02 findings and witnesses concern witness *presence* only — a recorded declaration that a
bound exists, never a statement about whether a run halts. Diff output carries structural
S/F/E classes and the deferred-P-12 marker; no safe/breaking classification is emitted
anywhere (SOW §8).

## The time budget

The job declares `timeout-minutes: 5`, so it cannot finish green over the five-minute
budget — "job green" and "under 5:00 total wall-clock" are one observation. Beside the
job's own clock, the suite's terminal summary reports the non-gating **"gebra-work
seconds"** sub-metric — the summed wall-time of the scenario's six legs — and appends it to
the job's step summary, so environment setup and scenario work are attributable separately.
The budget is this demo job's acceptance clock, not a product latency target.

## The audit trail a scenario run leaves

After the report leg, the scenario's `.gebra/` store contains, beside `meta.yaml` and the
eight snapshots:

- `reports/<version>.report.json` — one audit report per stored version, each the
  REPORT-FORMAT-SPEC §6 snapshot profile: all thirteen catalog properties listed, the eight
  non-wedge slugs as structured not-implemented markers, byte-identical on re-export.
- `reports/lineage.json` — the version-history document, in `gebra.lineage`'s own
  version-locked vocabulary (`lineage_version` 1.0): every version with its digest,
  timestamp, and the per-step bump classes. The scenario's report leg writes it with:

```python
from gebra.lineage import dump_lineage, lineage

(store.report_path(version).parent / "lineage.json").write_text(
    dump_lineage(lineage(store)), encoding="utf-8"
)
```

Together the two answer an auditor's "what did each version verify as, and what changed
between versions" from the store's files alone, without a `gebra` installation. The
per-version report names cannot collide with the lineage document — they always end
`.report.json`.
