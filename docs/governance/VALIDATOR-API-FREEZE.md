# Validator-result API freeze (F3 — VAL-12)

> **What this is.** The freeze record for card VAL-12 (tracked in the maintainers' development-process repository).
> Master plan §3 names freeze event **F3**: "IR-models + validator-result API freezes
> (IR-06, VAL-12, at G5) — jointly the D-12 promotion trigger (CLI-08)." F3 has two
> halves owned by two different tracks. This document is the VAL half — the
> validator-result API (the `gebra.verify` public surface). The IR-models half is IR-06's
> to record, in its own note, once that card lands; this document does not speak for it
> and is not amended when it does.

**Status: FROZEN**, recorded 2026-08-08.

## 1. What is frozen

The public surface of `src/gebra/verify` as landed by VAL-01 through VAL-11 (162 flat
exports re-exported from `gebra.verify.__init__`), specifically:

- **The result envelope** (PROPERTY-CATALOG-SPEC §0.3) — `PropertyReport`, `Failure`,
  `CoFailure`, `Advisory`, the five wedge witness models, the six structural `Location`
  subtypes, and the PC-4 serialization profile (`to_data`, `to_json`, `to_display`,
  `json_text`, `models_equivalent`).
- **The condition-ID / property registry** (§0.4) — `ConditionId`, `Severity`,
  `ClaimClass`, `PropertySlug`, `emittable_condition`, `is_emittable`,
  `property_for_condition`, `condition`, and the thirteen-slug property table
  (`register_validator`, `unregister_validator`, `run_property`, `validator_for`,
  `is_registered`, `is_implemented`, `not_implemented`).
- **The emission constructors** — `emit_failure`, `emit_co_failure`, `emit_advisory`.
- **The five wedge validator entry points** — `check_graph_well_formed`,
  `check_termination_witness`, `check_dataflow_completeness`, `check_effect_safety`,
  `check_determinism_replay`, each `validate(ir) -> PropertyReport`, plus P-02's strict
  surface `strict_promotions`.
- **The run-level aggregation** (REPORT-FORMAT-SPEC §1.2, built by VAL-11) —
  `verify(ir, policy=None) -> RunReport`, `RunPolicy`, `SubjectRef`, `anchor_location`,
  and the `RunReport` model family: `RunReport`, `Tool`, `Subject`, `StrictPolicy`,
  `Promotion`, `SeverityCounts`, `ToolError`, `GateOutcome`, `PropertyOutcome`.

This is the **Python callable/model surface** — signatures, field sets, and the registry
contract ("slug → callable → claim class → severity" per brief D-09's Deliverable 2) —
not the wire-format document version. `report_format` (currently `1.1`, REPORT-FORMAT-SPEC
§1.6) is that document's own governance and is explicit that it is "stamped final at the
D-12 promotion" (REPORT-FORMAT-SPEC front matter, Appendix B OI-4) — that stamping is
CLI-08's event, not this one. Freezing the validator-result API here does not itself
stamp `report_format` final; it fixes the code surface that document describes.

The eight non-wedge properties (P-03, P-05, P-07, P-09…P-13) are out of the Phase-0 wedge
(SOW §8) and answer through the same registry with a structured `DeferredToPhase1`
not-implemented marker — that dispatch contract is part of the frozen surface; the
properties themselves are not built and this freeze makes no claim about their shape.

## 2. Harness-consumer sign-off

Brief D-09's Definition of Done names this exact sign-off: "D-10 sign-off: 'Validators
are callable and produce structured outputs our golden harness can assert on.'" VAL-12's
own objective condenses it to **"callable, structured, assertable."** That sign-off is
recorded here as met, on the evidence the TE track's own cards produced against the
surface in §1 rather than as an unevidenced opinion:

- **Callable** — TE-02/TE-03 wired the fixture-loader and golden harness against
  `run_property`/`validate(ir)` from card VAL-04 onward, and every wedge validator has
  run under it since VAL-06 through VAL-10 landed.
- **Structured** — the harness compares validator output and fixture `expected:` blocks
  as the *same* pydantic models (`models_equivalent`, never string or raw-dict
  equality) — PROPERTY-CATALOG-SPEC §0.3's "one model, two duties" (PC-6), exercised on
  every fixture the corpus carries.
- **Assertable** — card **TE-04** ("Golden corpus green", `done`, 2026-08-06) is the
  observable proof: `python tools/golden_harness.py` and `python tools/corpus_green.py`
  run the full envelope + registry + `verify()` aggregation over the 60-fixture corpus
  and assert structurally on the result, with `pytest -q` green (6581 passed, 36 skipped
  on TE-04's final tree) exercising the same surface unit-test-side. TE-04's residual
  gap (`FM-009`, routed to `MANUAL-STEPS` M13 per WA-04 — a vendored-fixture question)
  is a corpus-completeness matter, not a surface-shape one: it does not touch whether the
  validators are callable, structured, or assertable, and this freeze note makes no claim
  about it either way.

No separate live meeting produced this sign-off; TE-04 already exercised the surface
end-to-end, and this record is that evidence read against D-09's sign-off wording.

## 3. CLI render sign-off — deliberately deferred

D-09's DoD also names "D-12 sign-off: 'Every witness/failure variant renders cleanly.'"
Per VAL-12's own objective, that sign-off is **not** captured here. It is CLI-07's
("CLI integration test suite") to record — CLI-07's objective already names the
obligation: "records the 'every variant renders cleanly' sign-off owed to the VAL track
(referenced by VAL-12's freeze note)." This is that reference. CLI-07 is `status: todo`
as of this record.

## 4. Post-freeze change policy

As of this freeze, the surface in §1 is no longer ordinary repo-authored iteration. Any
future change to its shape — a field added, removed, or retyped on an envelope or
run-level model; a condition ID added, renamed, or reclassified; a registered validator's
signature changed; a property moved off `DeferredToPhase1` — requires an
**R-05-routed decision**: a proposal, an R-05 vault sign-off recorded as a DEC or addendum,
then a re-vendored commit citing the new vault hash, mirroring the WA-03/WA-04 discipline that
already governs the frozen specs (PROPERTY-CATALOG-SPEC, TERMINATION-WITNESS-SPEC) this
surface implements — never a quiet local edit, even though the Python code itself is
repo-authored rather than vendored. R-05 is the ratified authority for this domain per
master plan §2: "Property semantics, witness/failure shapes, claim classes |
PROPERTY-CATALOG-SPEC + TERMINATION-WITNESS-SPEC (R-05 lineage; DEC-05/DEC-11)."

Additive, non-shape-changing work is unaffected by this freeze — e.g., a new wedge
validator is not in scope (all five already landed), and internal refactors that do not
move the surface in §1 need no R-05 routing, exactly as before.

## 5. D-12 promotion eligibility

F3 is a joint trigger: master plan §3 names it "IR-models + validator-result API
freezes (**IR-06, VAL-12**, at G5) — jointly the D-12 promotion trigger (CLI-08)," and
CLI-08's own `prereqs` list both `IR-06` and `VAL-12` by name (plus `CLI-02`). This
record discharges **VAL-12's half only**. As of this writing, **IR-06 ("IR freeze +
consumer sign-offs") is `status: todo`, unclaimed** on `boards/ir-core.md` — its half of
F3 has not landed. D-12 promotion (CLI-08) is therefore not yet fully eligible: it
becomes READY the moment IR-06 also reaches `done`, by the board's own derived-readiness
rule (§6: "a freeze event lands or slips (F3 → CLI promotion becomes READY...)") — no
board edit is needed to arm it, since CLI-08's `prereqs` already name both cards. This
note is what the VAL side of that trigger points at.

## 6. What this freeze does not claim

This record states witness/structure presence and API stability only. It does not claim
that the frozen surface is complete for Phase-1 scope (the eight non-wedge properties
remain stubs), that `report_format` is stamped final (CLI-08's event), or that G5 is
signed (G5's status line requires every G5 exit card `done`, not only this one).
