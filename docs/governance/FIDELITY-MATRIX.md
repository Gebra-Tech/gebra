# Fidelity matrix — validator output ↔ fixture expectation

The golden harness runs every fixture of the vendored corpus at `tests/fixtures/properties/`
against the validators and compares the two **as models** — PROPERTY-CATALOG-SPEC §0.3
model equality, set-comparison on the fields the specs mark order-free, never string or
raw-dict equality. This file is the decision log for every place the two sides do not agree.

**A deviation is a decision, never a quiet edit.** The corpus is a read-only vendored
contract surface: a mismatch is resolved either by *fixing the validator* or by *requesting a
fixture revision*, and a fixture revision routes proposal → R-05 sign-off recorded vault-first
as a DEC or addendum → re-vendor commit citing the new vault hash → corpus lint green
(WA-04; the mechanics are in [re-vendoring.md](re-vendoring.md)). Nothing here authorises an
edit under `tests/fixtures/properties/`.

**This file is machine-checked.** `python tools/golden_harness.py` runs the harness and
cross-checks §2, §3, §4 and §5 against what it observed, in both directions: a deviation with
no open entry fails, and an open entry that no longer reproduces fails. So the matrix cannot
drift from the corpus, and a resolved deviation cannot linger as an open row. The
cross-check is the command's only job — there is no flag to skip it — and it runs as its own
CI job. `--report` adds the per-obligation listing; `--deviations` adds the detail a new row
is written from.

Related: the harness itself is `gebra.testing.harness`; the schema-and-counts gate over the
same corpus is `python tools/corpus_lint.py`; and `python tools/corpus_green.py` is the one
that puts this file's answer beside the other three layers of SOW §2 criterion 2 (PD-006 R3)
and states whether the criterion is met.

## 1. How the harness reads a fixture

A fixture states what one validator should say about one workflow definition. The harness
turns that into **obligations** — the smallest unit a run passes, defers or fails on, each
naming exactly one property, identified as `<directory>/<stem>::<property-slug>`.

A single-property fixture carries one obligation: its whole `expected:` block *is* that
property's report (§0.3). A `mixed/` fixture carries one per property it exercises, because
a cross-property `expected:` block is a **run-level** composition that no single validator
produces whole — `mixed/04`'s block, for instance, carries a `dataflow-completeness`
co-failure on a `graph-well-formed` primary, which `emit_co_failure`'s ownership check
forbids a P-01 validator from emitting. The rules for reading one property's share out of
such a block are §2, which PD-006 R3.2 requires be logged here.

Five outcomes, of which none is silently a pass:

| Status | Meaning | Deviation? |
|---|---|---|
| `matched` | The validator reproduced the expectation, by §0.3 model equality. | no |
| `pending-validator` | A wedge property whose validator card has not landed. The expectation is modelled and the obligation goes live the moment one registers. | no |
| `deferred-to-phase-1` | A non-wedge property: SOW §8 puts it outside Phase 0. Named, counted, surfaced — never rendered as a pass (PD-006 R3.3). | no |
| `unmodelled` | The fixture's expectation has no §0.3 shape for this property, so there is nothing to compare. | **yes** |
| `mismatched` | Both sides are modelled and they disagree. | **yes** |

The acceptance reading this implements is PD-006 R3 (the SD-D1 ruling). Its four clauses, as
written: **R3.1** all 60 fixtures load hermetically, lint green against schema v2.2, their IR
payloads `model_validate`, *and their `expected:` blocks compose into envelope models*;
**R3.2** every wedge assertion obligation green by structural model equality, mixed fixtures
per their projection rules, each rule logged here; **R3.3** every non-wedge component an
explicit structured skip naming the property and citing SOW §8, counted and surfaced, never
rendered as a pass; **R3.4** run-level reports list all thirteen properties with the eight
non-wedge not-implemented markers — which is `verify()`'s obligation (VAL-11), not this
harness's. **VAL-11 landed (2026-08-06)** and `gebra.verify.verify(ir)` meets R3.4 directly:
all thirteen outcomes in catalog order, the eight non-wedge slugs answering with
`deferred-to-phase-1` markers. It changes nothing here — the harness compares one property's
report against one fixture's `expected:` block, and a run report is not a fixture block
(REPORT-FORMAT-SPEC §3.4). Every count in this file is the same before and after it.

**One open question under R3.1, recorded rather than smoothed over — and now ruled.** Its
last clause asked that all 60 `expected:` blocks compose into envelope models. Today 33 do
(`python tools/corpus_lint.py`), and the 27 that do not are shapes PD-016 deliberately left
alone: normalizing the eight non-wedge properties' witness and location shapes "would mean
inventing the contract this pass normalizes *to*". So R3.1's compose clause and PD-016's
scope were in tension, and it was a live question for TE-04's corpus-green box rather than a
harness defect — the harness reports the state per fixture and does not paper over it. It was
never an `FM-` entry, because it is not a validator/fixture disagreement: it is a question
about what criterion 2's first layer requires, which the owner rules on, not this file.
**TE-04 put a mechanical answer under it and filed the ruling as PD-039 Q1, ratified
2026-08-08:** every non-composing block is attributed by `python tools/corpus_green.py` to a
named non-wedge cause, verified rather than labelled, and a block that does not compose *and*
has no such cause is a violation. The owner re-signed `PHASE-0-DOD-CHECKLIST` C2 clause (1)
around exactly that, with one strengthening: **the four causes are a closed set, and admitting
a fifth is a PD event rather than a code edit.** So "the 27 are non-wedge shapes" is a checked
fact rather than a paragraph, and the taxonomy that checks it cannot widen quietly.

## 2. Projection rules

How one property's obligation is read out of a `mixed/` fixture. Each rule is data in
`gebra.testing.harness.PROJECTION_RULES`; the gate asserts this table and that tuple name
the same set of ids and kinds.

| Rule | Obligation kind | Statement | Authority |
|---|---|---|---|
| `PR-1` | `primary-projection` | The owning property's obligation is the expected block with `co_failures` restricted to entries that property holds and `advisories` dropped; where the source list is **merged** — it carries a record another property holds — the restricted co-failures are compared as a multiset, everything else in the report exactly. | Co-failures: §0.3 makes `co_failures` same-property carriage, and `emit_co_failure`'s ownership check refuses a name another property holds. Advisories: §0.3's scope boundary hands the run-level wrapper to REPORT-FORMAT-SPEC, so cross-property carriage is assembled above a single validator, which has no other property's findings in hand. §0.3 licenses an advisory *on* a report and `_check_advisory_carriage` refuses only the self-referential kind, so neither says a lone validator emits one — dropping them is PD-006 R3.2's projection latitude, logged here. The merged-list clause is REPORT-FORMAT-SPEC §3.3: above one property "order carries no meaning" and records are identified by `(property, property_condition, location)`, never by position — so the order a restriction inherits from a merged list states nothing, and comparing it positionally would test a normative order against a non-normative one. Amended at TE-04 (the rule pre-existed; the merged-list clause is what is new), closing `FM-007`. |
| `PR-2` | `cross-property-co-failure` | A wedge property named in another property's `co_failures` gets its own obligation, compared as the multiset of (condition ID, location) against that property's own report records; an expected entry the fixture itself marks `subsumed_by` is excluded, on that fixture's own recorded reading. | §0.3: cross-property carriage is run-level, so only the records are comparable. The exclusion is read off the fixture rather than asserted as a general rule about `subsumed_by`: DEC-05 D2 is scoped to P-01/P-04, and `mixed/04`'s own note states the consequence for that record — "the unreachable reader generates no P-04 obligation". §0.3 also puts `subsumed_by` on a primary `Failure`, so a validator that emits such a record is not thereby wrong; the exclusion is deliberately **not** mirrored on the produced side, so that case lands as a matrix entry — the question routed, rather than silently absorbed. |
| `PR-3` | `cross-property-advisory` | A wedge property riding another property's report as `advisories` gets the same multiset obligation as `PR-2`, with both sides' locations reduced to their §0.3 anchor first. | §0.3: advisories carry cross-property WARNING-class side findings (the `mixed/03` precedent). The property's own report packages the same findings as failure + `co_failures`, so only the records are comparable. The anchor reduction is REPORT-FORMAT-SPEC §3.2 rule 3 — a finding projected onto another property's report keeps its anchor and drops the concrete subtype's evidence members, which is what an advisory record *is*. The fixture side is already in that form; `gebra.verify.anchor_location` is the rule as a function, applied to both sides and idempotent on an anchor. Amended at TE-04 (the rule pre-existed; the anchor clause is what is new), closing `FM-004`. |
| `PR-4` | `multi-property-witness` | A passing mixed fixture's `kind: multi-property` witness projects each entry of `properties` to `PropertyReport(property=<slug>, result="pass", witness=<entry>)`. | §0.3's scope boundary hands the multi-property wrapper to REPORT-FORMAT-SPEC, while each entry under it is one property's §P-nn.3 witness; PD-006 R3.2 names `mixed/10`'s wedge witness entries as an assertion obligation. |

Why the multiset, and not model equality, in `PR-2`/`PR-3`: the two sides package the same
findings differently. An advisory list drops the `remediation` and the failure/co-failure
nesting a property's own report carries, and each side has its own ordering rule. The
records — condition ID and location — are what both sides genuinely state, so those are what
is compared. A property's *own* report is always compared exactly (`PR-1` and whole-report
obligations), including every ordering rule its catalog section fixes.

**What the record tuple deliberately leaves out.** `severity` and `claim_class` are on both
sides (§0.1 makes them a per-record guarantee) and are not compared here. They are pinned
somewhere stronger: `emit_failure`, `emit_co_failure` and `emit_advisory` read both off the
§0.4 registry rather than accepting them as arguments, so a validator built through the
constructors cannot state a grade the catalog disagrees with, and `tests/verify` pins that
per condition ID. Comparing them here would restate a check §0.4 already owns.

**Obligations on P-01-dirty topology are best-effort, and one of them is live.** §0.3 defines
P-02/P-04/P-06 results **only over P-01-clean topology**; where P-01 fails, another
property's report is "best-effort diagnostics, not contract-bearing verdicts", and a
single-property-scoped run there is "outside the defined result surface". The corpus has
exactly one such obligation — `mixed/04`'s P-04 share (`PR-2`), on topology carrying both a
dangling `path_map` target and an unreachable node — and the harness compares it like any
other. Recorded here so VAL-09 meets the caveat rather than inheriting an unstated pin: a
disagreement there is a question about the degradation convention, not automatically a
validator defect. Note also that PD-006 R3.2 names wedge *same-property* co-failures, and
this record is cross-property, so the obligation goes beyond what R3.2 required. VAL-09
landed and it does disagree; the caveat is discharged as `FM-008`.

**Ordering.** Comparison is `gebra.verify.models_equivalent`: exact, field by field, except
where a field carries the `SetCompared` mark, which is compared as a multiset. The marks are
the spec's, carried on the models with their citation (`DataflowWitness.coverage` per §4.3,
`P06EffectRecord.effect` per §6.3) — the harness chooses nothing about ordering, it asks the
envelope. `TerminationWitness.certificate` is the sharpest case of why exact is the default:
a permutation of a topological order is not a topological order.

`PR-1`'s merged-list clause is deliberately **not** such a mark, and the distinction is the
whole of why `FM-007` closed the way it did. Marking `Failure.co_failures` `SetCompared`
would be a statement that no §P-nn section fixes an order for a property's own co-failure
list, which §1.4 Step 5 falsifies. The clause says something narrower and checkable: the
list `PR-1` restricts was never one property's own list — `_merged_source` reads the *raw*
`expected:` block and fires only where it carries records of more than one property, which
in this corpus is exactly `mixed/04` and `mixed/05` — and REPORT-FORMAT-SPEC §3.3 rules
that such a list has no normative order to inherit. Everything else in the projected report,
including every field of every co-failure record, stays exactly compared, and P-01's own
§1.4 Step 5 order stays pinned where it belongs, in `tests/verify/test_graph_well_formed.py`.

**A P-02 obligation on `mixed/10` was predicted to deviate here; DEC-23 resolved it before
it could become a §3 row, and VAL-07 confirmed the resolution by observation.** Its router
guard was `'retry' if publish_status == 'failed' and attempts < 3 else 'done'`, which
TERMINATION-WITNESS-SPEC §3 makes **opaque** — `plain-char` excludes `'` and `"`, so a quoted
string literal in an opaque conjunct derives no `plain-token`, and L0's third clause rejects
the same shape earlier — while the fixture's `expected:` block carries a form-(a) inventory
entry (`counter_key: attempts`, `bound: 3`) as its *only* P-02 witness: a §3-conformant P-02
would have found `S_a ∪ S_c = ∅` and **flipped the verdict** on the corpus's one
all-properties-pass fixture. Filed for owner ruling as **VAL-D5**, ruled at **PD-037 Q3 and
filed as DEC-23 (2026-08-04), on the WA-04 route**: the guard was reworded to the corpus's
prose-conjunct style (`'retry' if publish failed and attempts < 3 else 'done'`), putting the
declared bound inside the grammar with the witness unchanged. Machine-checked at
`tests/verify/test_guards.py::test_the_quoted_string_literal_router_idiom_puts_declared_bounds_out_of_reach`,
which now pins the *post*-revision state: **fourteen** corpus routers still declare a bound
the grammar cannot reach for the same quoted-comparison reason, none of them claiming a P-02
witness, so the residual gap costs no fixture its verdict; the idiom's prevalence is
registered in the supplementary repo's PHASE-1-NOTES as a candidate Phase-1 grammar
widening, never a Phase-0 change. **Closed at VAL-07 (2026-08-05) with no §3 row ever
filed:** the registered validator derives the fixture's form-(a) witness from the revised
guard and the obligation is `matched` — the caveat's predicted deviation never became
observable, which is the WA-04 loop closing on the cheap side. (The fourteen residual
routers surface only as fail verdicts on snapshots no fixture states a P-02 expectation
for — 22 of the 67 corpus snapshots fail P-02, and every fixture-stated P-02 obligation is
green.)

**No cyclic-order comparison mode exists, and none is needed.** §6.3's shape-normalization
callout 2 offered "until then, comparison is cyclic-order equality" as a transitional
relaxation. The corpus reconciliation pass (DEC-17) landed the canonical rotations, so the
relaxation has no subject; exact-tuple equality is correct against the reconciled corpus. A
reader taking §6.3 item 2 at face value would implement the wrong comparison — the passage is
stale rather than live (recorded as MANUAL-STEPS M12). Confirmed by observation at VAL-10: P-06
is the property those four callouts are about, and all ten of its obligations match under
exact-tuple comparison, including every `cycle`/`cycles` list on both polarities.

## 3. Open deviations

One row per live deviation. `Obligation` is the harness id; `Status` is the observed status;
`Route` is which side of the WA-04 loop resolves it. The gate fails if a live deviation has
no row here, or if a row here no longer reproduces.

| Entry | Obligation | Status | Route | Disposition |
|---|---|---|---|---|
| `FM-005` | `mixed/05-evolution-drops-witness-and-state-field::termination-witness` | `unmodelled` | no change (recorded) | The P-02 co-failure's location carries `snapshot: ir_after`, which no §0.3 location models (`extra="forbid"`). Ruled **keep** at DEC-17 (PD-016 Q-03): it is P-12's pair-scoping convention — §4.6 describes this very record as "P-04 co-failure scoped `snapshot: ir_after`" — and removing it would delete evidence on a non-wedge authority's shape. The obligation stays unmodelled until P-12's section fixes how a pair-scoped record is carried; nothing in the wedge is blocked by it. |
| `FM-006` | `mixed/05-evolution-drops-witness-and-state-field::dataflow-completeness` | `unmodelled` | no change (recorded) | The same record shape as `FM-005`, on the P-04 co-failure (`snapshot: ir_after` on a `state-key` location). Same DEC-17 ruling, same route. Kept as its own entry rather than folded into `FM-005` because the two are separate obligations and either could be resolved without the other. |
| `FM-008` | `mixed/04-dangling-path-map-target-orphans-downstream-reader::dataflow-completeness` | `mismatched` | no change (recorded) | **P-01-dirty topology, where §0.3 defines no P-04 result** — the caveat §2 records above, now live. §0.3 gives P-04 the degradation convention "carries the phantom vertex with an empty contract" and §4.4 Step 0 applies `resolve` to targets only, so `G.add_edge(e.from, …)` materializes the phantom on *both* sides of an edge. `mixed/04` carries two dangling references to the same missing node — one as a `path_map` target, one as an edge **source** — so carrying it re-wires `compliance_log` into the START closure and its read of `legal_hold_ref` becomes a live obligation. P-04 emits `read-key-never-written-on-path` there; the fixture records the same finding as a `subsumed_by: P-01` co-failure, which `PR-2` reads as *no* P-04 obligation. Route is `no change (recorded)` on §6.2's terms, naming §0.3's P-01-clean precondition: these conventions "are deliberately local, cross-validator agreement on ill-formed input is NOT promised", and a single-property-scoped run there is "outside the defined result surface". **Not resolvable by a validator change.** DEC-05 D2's predicate is *unreachability*, and under P-04's own ratified convention the reader is reachable — so dropping edges out of an unresolved `from` would be adopting **P-01's** convention inside P-04, card-scoped, to turn one obligation green on topology the spec excludes (WA-03). DEC-12's "no phantom auto-vivification" rule is the one text that says otherwise and it amends **§1.4 only** — P-01's pseudocode, for a stated P-01-witness-leak motive — and it was ruled with this fixture's dangling source in hand, so its scope is deliberate. `the property-spec pre-review` ruled all of this at VAL-09 pre-review. **One fork for the owner, recorded rather than decided here:** the carried phantom now appears inside `DataflowLocation.path`, which is the same phantom-leak *class* DEC-12 closed for `terminal_nodes` — the boundary `DataflowLocation`'s own docstring already names. Closing it for P-04 is a §0.3/§4.4 addendum routed per WA-03, never a code change. **The fork is closed (DEC-26, 2026-08-09, vault `d6f34b4`):** §0.3's phantom-leak rule makes the carried phantom walk-internal — the emitted path now elides `legal_hold_review` (pinned in both directions at `tests/verify/test_dataflow_completeness.py::test_mixed_04_is_the_degradation_convention_residue_fm_008`) — while this row's core observation stays exactly the ruled `no change (recorded)` state: P-04 still emits the live obligation on P-01-dirty topology and the fixture still records it `subsumed_by: P-01`; nothing about the residue itself moved. |

**Three open.** Two trace to a ratified R-05 call — DEC-17 Q-03, which names two separate
records (`FM-005`/`FM-006`); `FM-008` was raised by a validator card. The harness
rediscovers exactly this set from the corpus: nothing outside it, and none of it missing.
(`FM-009`, the fourth at TE-04's landing and the only open row inside R3.2's enumeration,
closed at DEC-24 — the M13 owner action executed 2026-08-08 — and moved to §4; with it,
R3.2 reached 41/41 and the corpus-green gate took `--strict`.)

All three remaining rows are **`PR-2` obligations — cross-property co-failures — and PD-006
R3.2's enumeration does not reach them.** R3.2 names wedge primaries, wedge *same-property*
co-failures, wedge cross-property *advisories*, and `mixed/10`'s witness entries; the
harness compares cross-property co-failures too, which is more than criterion 2 asks for.
All three are ruled (DEC-17 Q-03 twice; §0.3's P-01-clean precondition once) and none is
waiting on a *validator* fix, and nothing here is waiting on this repository.

## 4. Closed deviations

Resolved deviations, kept for the record. The gate fails if a closed entry starts
reproducing again — a regression here is a new row in §3, never a quiet reopen.

| Entry | Obligation | Was | Resolved by |
|---|---|---|---|
| `FM-001` | `determinism-replay/negative-01-seedless-deterministic-llm-classifier::determinism-replay` | `mismatched` | The §8.3 walkthrough-#2 markers (a) and (d) — the negative's missing `kind: "node"` location discriminator and its `remediation` string being a condensed action clause rather than Appendix B §B.3's closing paragraph. Both landed in the corpus reconciliation pass (TE-03, ruled at DEC-17, re-vendored from vault `b2056e9`), which retired the two-entry deviation ledger `tests/verify/test_determinism_replay.py` had carried. Recorded here because it is the loop's first completed circuit: a fixture-side revision, routed through R-05, closing a validator/fixture disagreement. |
| `FM-002` | `determinism-replay/negative-02-seeded-llm-extractor-hot-temperature::determinism-replay` | `mismatched` | The same two markers on the second P-08 negative, resolved by the same DEC-17 re-vendor. Its own row because it is its own obligation: the harness compares each fixture independently, and the ledger it replaced carried two entries for the same reason. |
| `FM-003` | `mixed/10-all-properties-pass-healthy-research-pipeline::dataflow-completeness` | `unmodelled` | The DEC-23 corpus revision (2026-08-04, PD-037 Q3 bundle — the "second, narrower corpus revision" DEC-17/PD-016 Q-01 ratified in advance). Executing the plan of record surfaced a material fact: the shipped VAL-09, run on the fixture's then-current IR, produced **fail** (`read-key-never-written-on-path` for `news_data`/`price_data` at `compose_digest` — the parallel fan-in reads, faithful to §4's every-`START`-path/∩-meet statement), which `unmodelled` had kept invisible because the harness stops before any validator runs. The revision therefore (a) declared `price_data`/`news_data` `optional: true` — the fixture header's own "or is an optional graph input" mechanism, already used by `ticker`/`sources` — preserving the fixture's positive polarity with its cycle, fan-out, billable effect and determinism claim untouched, and (b) replaced the pre-contract aggregate `{unwritten_reads: []}` with the §4.3 `DataflowWitness` derived by the shipped validator on the revised IR, verified equal to the validator's live output. The obligation is `matched` since. |
| `FM-004` | `mixed/03-parallel-reducerless-key-with-unpinned-llm-writers::determinism-replay` | `mismatched` | **The `PR-3` anchor reduction (TE-04, 2026-08-06) — a harness fix, with no corpus byte and no validator change.** The two P-08 advisories carry a bare `NodeLocation`; P-08's own report anchors on §8.3's `DeterminismNodeLocation`, which requires `annotation` and carries the `form`/`effects` evidence. Condition IDs and anchor nodes agreed exactly on both sides — the whole difference was the location shape, and DEC-17 (PD-016 Q-02) ruled it a **deferral rather than a conformance finding**, to be met by "whichever of the §P-09 merge or REPORT-FORMAT-SPEC lands first". REPORT-FORMAT-SPEC landed first, and §3.2 rule 3 is the answer: a finding projected onto another property's report keeps its §0.3 anchor and drops the subtype's evidence — exactly the bare `NodeLocation` this fixture carries. What kept the row open afterwards was a misreading of where the projection had to happen, recorded here because it cost a cycle: §3.2's note and Appendix B OI-3 both concluded that since `verify()` assembles no advisories, the harness could observe no projected shape. But `PR-3` never compared against `verify()`'s output — it compares the fixture's advisory records against **P-08's own report**, which is to say it was already comparing a projected form against an un-projected one. Applying `gebra.verify.anchor_location` — rule 3 as a function, idempotent on an anchor — to both sides closed it. The question §P-09 still owns is untouched and is *not* what this row was: which host report a WARNING-grade finding rides. |
| `FM-007` | `mixed/04-dangling-path-map-target-orphans-downstream-reader::graph-well-formed` | `mismatched` | **The `PR-1` merged-list clause (TE-04, 2026-08-06) — the "`PR-1` amendment" this row named as one of its own two resolutions.** The two same-property co-failures were in a different order and nothing else differed: primary, all three records' condition IDs, locations, severities and claim classes identical on both sides. §1.4 Step 5 fixes P-01's own order as `F_iv ++ F_iii ++ F_i ++ F_ii`; the fixture lists them the other way because DEC-12 ratified the new record as *appended* to the block's **merged cross-property** list. The row's blocker was that "which ordering rule governs a merged list is not fixed by any frozen spec" — §0.3 hands the run-level wrapper to REPORT-FORMAT-SPEC, which was then undrafted. **It is drafted, and §3.3 fixes the rule: above one property "order carries no meaning", and records are identified by `(property, property_condition, location)`, never by position.** So the order `PR-1`'s restriction inherited from that merged list asserted nothing, and comparing it positionally tested a normative order against a non-normative one. `PR-1` now compares the restricted co-failures of a *merged* source as a multiset and everything else exactly. The two things the row forbade are both untaken: no P-01 change (emitting F_i before F_iv would contradict frozen §1.4 Step 5 — the validator still emits §1.4 order, pinned at `tests/verify/test_graph_well_formed.py`), and no `SetCompared` mark on `co_failures` (which would be a false statement about §1.4). **The DEC-12-reading fork this row recorded is settled, and the amendment is not reading-neutral (recorded at PD-039 ratification, 2026-08-08, correcting this row's earlier framing):** comparing the merged list as a multiset presupposes that DEC-12's closing sentence speaks about the *merged fixture list* — under the second reading (normative for P-01's *own* `co_failures`) the fixture's restriction would carry a normative order and relaxing it would be wrong, so ratifying PD-039 Q3 ratifies the merged-list reading. Per that ratification the fork also closes in frozen text: a clarifying addendum to DEC-12 is filed vault-first (riding the M13 vault commit) and re-vendored, so this row's basis is the vault record, not a repo-side reading; a WA-03 filing was the stated alternative and was declined in favour of the addendum. |
| `FM-009` | `mixed/08-express-path-skips-gate-writer-and-witnessed-exit::dataflow-completeness` | `mismatched` | The DEC-24 corpus revision (2026-08-08) — `MANUAL-STEPS` M13, the one-key WA-04 revision this row carried as its route since VAL-09 filed it (2026-07-31). `writers_on_other_paths: [compliance_gate]` was added to the fixture's P-04 failure record in the vault master (`Gebra-Tech/initial-documents@7be81a9`) and re-vendored; the revised block was verified equal to the shipped validator's live output before filing. Basis unchanged from the open row: §4.4 Step 4's emit-iff-non-empty plus DEC-11 decision 3, with the corpus's own four-fixture consistency making any validator-side suppression contradictory. Result, condition, location, severity, claim class and both co-failures untouched. The obligation is `matched` since; with it R3.2 reached 41/41 and the corpus-green CI job flipped to `--strict`. |

## 5. Per-property fidelity status

One row per catalog property, per D-10 deliverable 4 ("complete for every property with at
least one fixture"). The gate asserts the property set and the obligation counts; statuses
are not restated here because they move as validator cards land —
`python tools/golden_harness.py --report` is the live view.

| Property | Slug | Phase 0 | Obligations | Fixtures | Harness treatment |
|---|---|---|---|---|---|
| P-01 | `graph-well-formed` | wedge | 8 | 8 | Assert model equality. Validator: VAL-05 — landed; **all eight** obligations match since TE-04 — the six `graph-well-formed/` fixtures, `mixed/10`'s witness entry, and `mixed/04`'s `PR-1` projection, whose co-failure list-ordering residue closed as `FM-004`'s sibling `FM-007` when `PR-1` gained its merged-list clause. Nothing about P-01 changed: the validator still emits §1.4 Step 5's `F_iv ++ F_iii ++ F_i ++ F_ii`, and `tests/verify/test_graph_well_formed.py` still pins both that order and the vendored merged order it differs from, in both directions. |
| P-02 | `termination-witness` | wedge | 12 | 12 | Assert model equality. Validator: VAL-06 (guard recognizer) + VAL-07 (witness assembly + verification) — landed; **eleven of its twelve obligations match, every one on the first harness run**: the flagship 4+4 under `termination-witness/`, `mixed/02` as a `PR-1` primary, `mixed/08` as a `PR-2` record multiset (P-02 riding P-04's report), and `mixed/10`'s `PR-4` witness entry (green under the DEC-23 guard reword). The twelfth is the pre-existing ruled deferral `FM-005` (`mixed/05`'s `snapshot: ir_after` key), which `unmodelled` decides before any validator runs — P-02 registering moved nothing there. **Four repo-authored spellings ride here, recorded with their routes.** (1) The census list order: no spec fixes one, `positive-04` pins shortest-first (its 2-cycle precedes its 4-cycle, against lexicographic order), so the census sorts by (length, ledger-§6 key); a future fixture ordering differently is a matrix question, never an edit. (2) The blanket note's granularity: T-W-SPEC §2.4's prose reads as one warning "listing every residual non-trivial SCC" while catalog §2.4's pseudocode appends one note per SCC; the catalog owns the contract where both speak (T-W-SPEC's own boundary banner), so VAL-07 emits **one note per residual SCC** in sorted-tuple order, each carrying its own `P02SccLocation` — also the shape VAL-08's strict promotion can map 1:1 onto per-SCC findings. No fixture states a blanket note (§2.7 records the gap; DEC-16/TE-14 own the gap fixtures), so a future fixture disagreeing is a matrix row. (3) The D4 anchor's `guard_edge.labels` ride in authored `path_map` order (`negative-03` pins `[immediate, delayed]`, which the ledger comparator would reverse). (4) **The blanket-only pass certificate** (`the property-spec pre-review` N1 at VAL-07 pre-review): catalog §2.4 Step 6's literal `topological_sort(R)` is undefined on the one reachable pass whose *element* residual is cyclic — a justified (b) covering cycles no element witness reaches — and the validator emits the element residual's condensation order (`worklist_order`) there. That satisfies T-W-SPEC §6.2, the semantics owner, on its own terms: §6.2's certificate is over `G \ S`, and on this path the default-profile `S` includes `S_b = E`, so `G \ S` is edgeless and *any* vertex order is a topological order of it — the spelling is a valid certificate, not an approximation of one. **VAL-08 has now met that corner** (recorded here as prediction, kept as observation): every blanket-only run is a pass, so it emits `worklist_order` over a cyclic element residual on the baseline half of every strict test. The corner is doubly load-bearing from here, because the blanket-only path is the only one that both emits that certificate and produces a strict promotion — DEC-16 item 7's `positive-05-recursion-limit-only-scc-note` (TE-14's to author, positive polarity) will pin both at once. If a fixture ever pins a different blanket-path certificate, that is a matrix row (or a WA-03 observation against §2.4 Step 6's expression), never an edit. The optional census is emitted unconditionally on the pass path per PD-011 (B = 16; on-by-default), with `cycle-census-capped` on abort. **VAL-08 closed the two items VAL-07 left it, and neither added a fifth spelling.** The cap is exercised at its boundary rather than at the constant: B and B+1 through the public path, the §6.3 counting caveats deciding the boundary (eight two-label petals are eight vertex circuits and sixteen edge-simple cycles — exactly B; one self-loop more overflows), the abort proven to be *during* enumeration by instrumenting the blocked search on K₁₂ (119,481,284 simple cycles, exactly B+1 circuits handed back), and T-W-SPEC §6.3's own constraint — B ≥ max c(G) over the corpus — re-derived independently of PD-011's networkx sweep, reproducing max c(G) = 3 at `mixed/08`. **One VAL-07 divergence was corrected rather than recorded:** §6.1 builds one payload for all three profile rows and fills `blanket_only` from `<justified (b) present?>`, so its second row carries `blanket_only: true` on the *note* as much as its third does on the strict item; VAL-07 emitted the note without it, while DEC-11's own pin-6 example (`tests/verify/test_dec11_examples.py`) spells it with it. VAL-08 emits it, which removes a divergence instead of adding one — `false` is still never put on the wire, per the `P02SccLocation` ruling, now proven by a wire scan over the corpus plus every hand-built blanket shape rather than argued. **The delegation runs both ways, and spelling (2) above should be read with this**: T-W-SPEC §6 defers **wire shape** to the catalog ("wire shapes are the catalog's — §P-02 I/O contract"), while catalog §2.3 delegates **note content** back to T-W-SPEC ("`WitnessNote` … imported from TERMINATION-WITNESS-SPEC … this section never restates their semantics"). So granularity — one note per SCC versus one note listing all — is packaging and the catalog's to fix, while whether the payload carries `blanket_only` is content and T-W-SPEC's; spelling (2) and this correction follow one rule, not two conflicting ones. Nothing here routes to WA-04: no fixture states a blanket note, so the corpus is untouched. **The strict row is a promotion, not a second record**, and the two frozen texts are layered rather than colliding: §0.2 names this note as promotable "with the report, witness, and note records unchanged", §2.4's pseudocode takes no strict parameter, and DEC-11 item 6 ratifies it in those words ("the gate changes, never the record"), while T-W-SPEC §6.1 — whose own heading is *profile gate*, and which §2.4 says "encodes the full gate" — fixes what the promoted item is called. So `strict_promotions()` reads the record and returns `StrictPromotion` values (note kind + §6.1's reused condition ID + the `blanket_only`-bearing SCC location), never a second `PropertyReport`; the ID is resolved back through the §0.4 emission gate, and the promotion carries no severity, so nothing on the strict path can enter a run's FATAL count and suppress `gate.snapshot_eligible` (REPORT-FORMAT-SPEC §2.5: "promotion moves the gate, not the ladder"). **Two run-report gaps surfaced with it, and they were split.** REPORT-FORMAT-SPEC §2.1 defined a note as one "riding a passing report's witness", which VAL-08's own merged behaviour falsifies — fail-path notes are promotable and are selected — so its prose was corrected here to match §2.3's reach table, which was already right; no model changed, so `report_format` stays `1.0`, and the precedent for a VAL card amending that repo-authored file in the same change is VAL-07's own §4.3 row. The other is **VAL-11's**: §2.3's `Promotion.property_condition` is "absent iff `origin == "witness-note"`", so §6.1's identity rule and the `blanket_only` location have nowhere to land in a run report, and §5's render table closes the SARIF route too. That is a §1.2 run-level model change under §1.6's bump rule with a design question attached, so it is written into VAL-11's `decisions_to_implementer` rather than decided here. Neither changes an exit code. **VAL-11 decided it (2026-08-06): carry it.** `Promotion.property_condition` is now populated on a `witness-note` promotion where the owning property's spec fixes an identity for the promoted kind, which for P-02 is §6.1's `cycle-without-termination-witness`; `report_format` went to `1.1` on §1.6's MINOR row, and §2.3/§4.6 gained the rule that the id names the promoted *item* and is never rendered as a grade — the record keeps its WARNING severity and the id never enters `gate.counts`. The argument for carrying it over dropping it is that §6.1 is frozen and `gate.promotions` is the only artifact a promotion appears in, so the alternative left a frozen normative sentence with no realization anywhere. **One correction to the handover, recorded because it changes what was owed:** the `blanket_only` location was never homeless. `Promotion.location` is typed `Optional[AnyLocation]` and `AnyLocation` admits `P02SccLocation`, so the location rides in full at `1.0` as much as at `1.1`; only the condition ID needed the amendment, and "drop both on the floor" over-counted the gap by one. |
| P-03 | `signature-soundness` | deferred | 8 | 8 | Structured skip citing SOW §8. §0.4 also holds its three condition IDs back (DEC-05 D6). |
| P-04 | `dataflow-completeness` | wedge | 11 | 11 | Assert model equality. Validator: VAL-09 — landed; nine of its eleven obligations match (the six `dataflow-completeness/` fixtures, `mixed/02`'s cross-property record, `mixed/10`'s witness entry — green since the DEC-23 corpus revision closed `FM-003` — and `mixed/08`'s primary, green since the DEC-24 revision closed `FM-009`), one is the deviation `FM-008`, and one is the pre-existing ruled deferral `FM-006`, which `unmodelled` decides before any validator runs. Two repo-authored ordering choices ride here, with the same exposure. §4.3 fixes no order for `DataflowCoverage.satisfied_by` and the field is not `SetCompared`, so VAL-09 emits it in the ledger §6 comparator (documented at `_display_sorted`); and §4.4 Step 4 says only "BFS-shortest" of `location.path`, so where several shortest paths exist the tie-break — expand successors in ledger §6 order, first parent wins — decides which one is emitted (`test_the_offending_path_is_the_shortest_one` asserts length rather than identity for exactly that reason). All three positives and every negative agree, which is everywhere the corpus speaks; a future fixture listing a different member order, or a different equal-length path, is a matrix question, never an edit. |
| P-05 | `guard-exhaustiveness` | deferred | 0 | 0 | No fixture in the corpus. |
| P-06 | `effect-safety` | wedge | 10 | 10 | Assert model equality. Validator: VAL-10 — landed; **all ten** obligations match, with no deviation and no new row in §3: the six `effect-safety/` fixtures, `mixed/01` and `mixed/09` as `PR-1` primaries, `mixed/06` as a `PR-2` record multiset (P-06 riding P-07's report), and `mixed/10`'s `PR-4` witness entry. **Three** repo-authored spellings ride here, none of them an ordering choice. (1) `P06NodeLocation.effect` and `P06EffectRecord.effect` are `SetCompared` per §6.3, so their order is not compared — the validator emits the set **as declared**, which is what the location is evidence of. (2) §6.3 permits display-only prose in `remediation` while §6.4's pseudocode produces none; the validator emits none, which is what the four negatives' `expected:` blocks require under exact model equality. (3) **The `dangling_compensation_hook` narrowing**, which is a behaviour on input the spec's own models exclude rather than a choice among readings: §6.3 types that evidence field `Optional[NodeId]` and IR-SPEC §3.4 types `hook` as "a node id under the §5 grammar", but `Compensation.hook` is an unconstrained `str`, so a hand-authored hook breaking the §5 grammar would make emitting the field raise inside the validator. The field is dropped instead. The verdict is provably invariant, not merely observed: `Node.id` is `NodeIdStr`, so every member of `node_ids` is §5-valid and a grammar-invalid hook can never be `hook_ok` — condition ID, severity, claim class, anchor, `fanout` and packaging are all untouched. Deliberately **not** an `FM-` row: no fixture states the shape, and `gebra.extract()` cannot produce it, so it is the same gap class PD-009 finding 4 ruled for `pure` + trigger-tag (hand-authored/foreign IR, filed rather than built). Ruled defensible — not a WA-03 event and not a fixture question — by `the property-spec pre-review` at VAL-10 pre-review, which recommended it be recorded here. Two shapes §6.7 names have **no fixture** and are exercised only by hand-built IRs in `tests/verify/test_effect_safety.py` — a `retry_policy`-only retry region (no cycle, so no anchor) and a dangling compensation hook — because DEC-13 left the gap-fixture half of §6.7 (v) open as its own WA-04 item. Neither is a matrix question until a fixture states one. |
| P-07 | `retry-coherence` | deferred | 8 | 8 | Structured skip citing SOW §8. |
| P-08 | `determinism-replay` | wedge | 6 | 6 | Assert model equality. Validator: VAL-04 — landed; **all six** obligations match since TE-04 — the four single-property fixtures, `mixed/10`'s witness entry, and `mixed/03`'s advisory records, which closed as `FM-004` when `PR-3` began reducing both sides to the §0.3 anchor (REPORT-FORMAT-SPEC §3.2 rule 3). P-08's own report still anchors on §8.3's `DeterminismNodeLocation` with its full `form`/`effects` evidence; what changed is that the harness now compares an advisory against an advisory. |
| P-09 | `parallel-safety` | deferred | 8 | 8 | Structured skip citing SOW §8. |
| P-10 | `subgraph-consistency` | deferred | 0 | 0 | No fixture in the corpus. |
| P-11 | `join-key-soundness` | deferred | 0 | 0 | No fixture in the corpus. |
| P-12 | `evolution-safety` | deferred | 7 | 7 | Structured skip citing SOW §8. Its six pair fixtures plus `mixed/05`. |
| P-13 | `interrupt-gate-coverage` | deferred | 0 | 0 | No fixture in the corpus. |

## 6. Adding, closing and reopening an entry

1. Run `python tools/golden_harness.py --deviations` and take the obligation id, the status
   and the detail from its report.
2. Decide the route, and say why in the disposition. The `Route` column takes exactly one of
   three values, and the gate's companion test holds it to them: **fix the validator** (the
   corpus is right), **R-05 fixture revision** (the corpus is wrong — proposal → R-05
   sign-off → re-vendor, WA-04), or **no change (recorded)** when a frozen spec has not yet
   fixed the shape, which must name the passage or ruling that says so.
3. Add the row to §3 with the next free `FM-nnn`. Ids are never reused.
4. When it stops reproducing, move the row to §4 with what resolved it. The gate will fail
   until you do — an open row that no longer reproduces is as much a drift as an unrecorded
   deviation.

A deviation is never resolved by relaxing the comparison. `models_equivalent`'s set-compared
fields carry spec citations; adding one is a spec statement, not a harness convenience.

**One thing to know before you close the last row, recorded so it is not discovered as a red
gate.** `parse_matrix` requires §3 to carry a *table*, and it reads a table as its rows: empty
§3 → `MatrixError` → `python tools/golden_harness.py` exits non-zero on the very state step 4
drives towards. Nothing depends on that today (four rows are open) and fixing it is TE-02's
gate semantics rather than a matrix edit, so it is named here rather than patched from a card
that does not own it. Two things already account for it: the corpus-green gate reads this file
through `golden_harness.open_obligations` and can be run without it at all
(`check(..., matrix_path=None)`, which is strictly stricter), and the WA-07 tripwire in
`tests/testing/test_hermeticity.py` uses exactly that mode, so a governance document reaching
its end state cannot turn a never-invokes tripwire red. Surfaced by the never-invokes
pre-review at TE-04.
