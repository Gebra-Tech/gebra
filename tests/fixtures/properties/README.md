# Property Fixture Corpus

> [!NOTE]
> **Corpus populated 2026-07-17 — migrated to ir 1.0 on 2026-07-18.**
> 60 fixtures across the nine allocated properties + `mixed/` — every counts-table target met. **R-05 lead sampling review complete 2026-07-17** (guided walkthrough, 100% of `mixed/` + ~30% per-property; eight decisions recorded in DEC-05 and applied). **ir 1.0 migration complete (2026-07-18, DEC-09)**: every fixture's `ir_version` is `"1.0"` (evolution pairs: both snapshots), and [schema.yaml](schema.yaml) carries the **v2.2 addendum** — the ir 1.0 optional slots (`args_schema`, `retry_policy`, `variant`, `compensation`, `prompt_digest`/`config_digest`, top-level `runtime`) plus shape pins. **Wedge-five witness shapes (P-01, P-02, P-04, P-06, P-08) are PINNED and normalized** (walkthrough #2, 2026-07-18, DEC-11) **and reconciled to the §P-nn.3 record contracts** (the DEC-11-mandated single corpus pass — 22 items across 12 fixtures: location discriminators, §0.4 grades, canonical cycle rotations, the `positive-01` region normalization, §B.3 remediation texts; DEC-17, 2026-07-31); the standing witness-shape-reconciliation item now applies **only to the 8 non-wedge properties**, whose shapes stay marked provisional in each fixture's `notes:` pending their PROPERTY-CATALOG-SPEC sections. The authoring-surfaced spec gaps (no `recursion_limit` IR slot, no `args_schema` annotation field, no `retry_policy` serialization, no compensation-hook annotation) are closed by the ir 1.0 freeze — the `args_schema` fixture (`signature-soundness/negative-03`) is un-skipped, its verdict now reproducible from the `ir` block; the missing temperature slot in `@deterministic` was closed earlier by the schema v2.1 addendum (DEC-05).

The reference fixture corpus produced by R-05 and consumed by D-10 to build golden tests for the D-09 property validators. Schema spec: [schema.yaml](schema.yaml) (`$id: gebra-property-fixture-v2`). Decision driver: DEC-03-fixture-format (v2 addendum). Property catalog authority: Verification-Properties.

Fixtures carry **serialized Gebra IR**, never live LangGraph Python: stable across LangChain/LangGraph API churn, hermetic for validator testing, lintable without executing anything. Extractor correctness is tested separately against pinned versions in the package repo (D-08-Python-Package-and-IR-Extractor).

## Layout

```
fixtures/properties/
├── README.md                 # this file
├── schema.yaml               # fixture format spec (gebra-property-fixture-v2)
├── graph-well-formed/        # P-01 — ≥3 positive + ≥3 negative
├── termination-witness/      # P-02 — ≥4 positive + ≥4 negative (flagship)
├── signature-soundness/      # P-03 — ≥3 positive + ≥3 negative
├── dataflow-completeness/    # P-04 — ≥3 positive + ≥3 negative
├── effect-safety/            # P-06 — ≥3 positive + ≥3 negative
├── retry-coherence/          # P-07 — ≥2 positive + ≥2 negative
├── determinism-replay/       # P-08 — ≥2 positive + ≥2 negative
├── parallel-safety/          # P-09 — ≥2 positive + ≥2 negative
├── evolution-safety/         # P-12 — ≥3 positive + ≥3 negative (ir_before/ir_after pairs)
└── mixed/                    # ≥10 cross-property fixtures
```

Directories for P-05 `guard-exhaustiveness`, P-10 `subgraph-consistency`, P-11 `join-key-soundness`, and P-13 `interrupt-gate-coverage` are allocated when their validators are scheduled (Phase-0-Plan catalog scope); the schema's `property` enum already admits all 13 slugs.

## Naming convention

`<polarity>-<NN>-<slug>.yaml` — examples:

- `termination-witness/positive-01-counter-guarded-retry-loop.yaml`
- `termination-witness/negative-01-unwitnessed-reflection-loop.yaml`
- `effect-safety/negative-01-billable-in-unguarded-retry.yaml`
- `mixed/01-witnessed-cycle-with-unkeyed-billable-node.yaml`

`NN` is a zero-padded two-digit serial number, allocated in order. New fixtures take the next-available number; never overwrite.

## Counts (target end of quarter)

| Property | Positive | Negative | Subtotal |
|---|---|---|---|
| P-01 `graph-well-formed` | 3+ | 3+ | 6+ |
| P-02 `termination-witness` (flagship) | 4+ | 4+ | 8+ |
| P-03 `signature-soundness` | 3+ | 3+ | 6+ |
| P-04 `dataflow-completeness` | 3+ | 3+ | 6+ |
| P-06 `effect-safety` | 3+ | 3+ | 6+ |
| P-07 `retry-coherence` | 2+ | 2+ | 4+ |
| P-08 `determinism-replay` | 2+ | 2+ | 4+ |
| P-09 `parallel-safety` | 2+ | 2+ | 4+ |
| P-12 `evolution-safety` | 3+ | 3+ | 6+ |
| Mixed (cross-property) | varies | varies | 10+ |
| **Grand total** |   |   | **60+** |

> [!NOTE]
> The "50+ fixtures" target cited in D-10-Test-Engine-and-Pytest-Plugin and Status-Report-2026-07-09 is the single-property floor (subtotals above excluding `mixed/`); including the cross-property `mixed/` corpus the floor is 60+.

P-02 is the flagship: termination-witness is the biggest formal-model change of the reframe (D-016 — cycles admitted with witnesses) and the property most in need of edge-case coverage (counter guards, `recursion_limit`, loop bounds, nested cycles, witness removed by evolution).

**Evolution-safety fixtures use `ir_before` + `ir_after` snapshot pairs** instead of a single `ir` — P-12 classifies the diff, so one IR is never enough. All other directories use the single-`ir` form.

**Corpus discipline:** a single-property fixture should fail only its named property — all other catalog properties must hold, so the fixture isolates the validator under test. Where the catalog couples properties by design (e.g. an unprotected effect in a retry cycle fails both P-06 and P-07), record the known co-failure in `notes:`; deliberate multi-property interactions belong in `mixed/`.

## Validation

The corpus lints as a whole. The lint enforces:
- Every YAML file conforms to [schema.yaml](schema.yaml)
- Exactly one IR shape per fixture (`ir`, or `ir_before`+`ir_after` for evolution-safety only)
- Per-directory positive/negative minimums per the counts table
- No serial-number collisions
- `expected.witness` present for `result: pass`; `expected.failure.property_condition` present for `result: fail`

## Fixture authoring

- Fixtures are authored by hand against [schema.yaml](schema.yaml) and always reviewed by
  the R-05 lead before commit (sampling allowed: 100% of mixed, 30% of per-property)

## Consumer (D-10)

The D-10-Test-Engine-and-Pytest-Plugin golden harness reads each fixture with `yaml.safe_load`, validates the IR into the pydantic model from D-08-Python-Package-and-IR-Extractor, and asserts the validator verdict:

```python
# Conceptual; actual implementation in the gebra package repo (D-10).
import yaml
from gebra.ir import WorkflowIR
from gebra.verify import run_property

def run_fixture(fixture_path):
    fixture = yaml.safe_load(fixture_path.read_text())
    if "ir" in fixture:
        report = run_property(fixture["property"], WorkflowIR.model_validate(fixture["ir"]))
    else:  # evolution-safety pair
        report = run_property(
            fixture["property"],
            WorkflowIR.model_validate(fixture["ir_before"]),
            WorkflowIR.model_validate(fixture["ir_after"]),
        )
    assert report.result == fixture["expected"]["result"]
    if report.result == "pass":
        assert report.witness == fixture["expected"]["witness"]
```

`source_snippet` is documentation for human readers only — the harness never imports or executes it (Gebra never executes workflows; D-018).

---

**See also:** R-05-Verification-Property-Formalization, D-09-IR-Property-Validators, D-10-Test-Engine-and-Pytest-Plugin, DEC-03-fixture-format, Verification-Properties.
