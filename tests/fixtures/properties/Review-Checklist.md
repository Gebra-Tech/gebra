# Fixture Corpus — R-05 Lead Review Checklist

> [!NOTE]
> **Review complete 2026-07-17.**
> Guided walkthrough with the R-05 lead; the eight decisions are recorded in DEC-05-fixture-review-2026-07-17 and applied to the corpus, the Verification-Properties catalog, and Open-Questions the same day. The remaining Part-1/Part-2 items were confirmed as authored.

The 60-fixture corpus was authored 2026-07-17 (lint: PASS; independent QA sampling pass applied — one blocker fixed, identifiers normalized). Per the corpus convention, the **R-05 lead reviews 100% of `mixed/` and ~30% of per-property files before the corpus counts as accepted**. This checklist is that review, pre-digested: each entry says what the judgment call IS, so you confirm decisions rather than hunt for them.

## Part 1 — `mixed/` (all 10; the interaction logic is the review)

- [x] `01-witnessed-cycle-with-unkeyed-billable-node` — **Call:** a PASSING termination witness does not make a billable loop safe; P-06+P-07 co-fail on the same node. Confirm you want witness-pass + effect-fail reported together, not merged.
- [x] `02-unwitnessed-loop-reading-unwritten-key` — **Call:** P-02 and P-04 defects in the same loop body must be reported independently (fixing one still ships the other).
- [x] `03-parallel-reducerless-key-with-unpinned-llm-writers` — **Call (QA-fixed):** writers now carry `effect: [network, external]` as the IR evidence they are LLM nodes (the P-08 evidence rule); P-08 findings filed as WARNING-class `advisories`, P-09 primary. Confirm the evidence rule: bare `deterministic: true` without network/external effects = trivially coherent pass.
- [x] `04-dangling-path-map-target-orphans-downstream-reader` — **Two open semantics calls, flagged in notes:** (a) does P-04 check reads of *unreachable* nodes (global-writer-set reading, as here) or quantify only over START-paths (as `graph-well-formed/negative-01` assumes)? The P-04 spec must pick one. (b) A dangling edge *source* is an anomaly class P-01's formal statement doesn't enumerate — fold into dangling-reference or enumerate?
- [x] `05-evolution-drops-witness-and-state-field` — **Call:** co-failures scoped with a `snapshot: ir_after` field (new convention); and `breaking-diff-read-key-write-removed` extends P-12's enumerated breaking classes ("sole writer severed") — needs a P-12 spec addendum or explicit blessing.
- [x] `06-irreversible-cycle-idempotency-key-not-read` — **Call:** P-06 must not take an idempotency annotation at face value — its verdict depends on P-07's key-placement check (cross-validator sequencing for brief D-09).
- [x] `07-subgraph-leaked-key-collides-with-parallel-sibling` — **Call:** P-09's reducer check must run over the full *observed* write set, not just declared schema keys, or the collision hides behind the P-03 finding.
- [x] `08-express-path-skips-gate-writer-and-witnessed-exit` — **Call:** "every cycle needs a witness" is per-*cycle*, not per-SCC — one express label creates an unwitnessed bypass cycle inside an SCC that also contains a witnessed one. (Same granularity question as the flagship pair below.)
- [x] `09-send-fanout-billable-no-idempotency-in-retry` — **Call:** P-09 filed as ADVISORY (reducer makes writes well-defined; duplicates still accumulate across retries) while P-06/P-07 hard-fail. Confirm the advisory split.
- [x] `10-all-properties-pass-healthy-research-pipeline` — **Call:** the over-flagging guard; notes exempt keyed-idempotent network *reads* from the P-09(ii) commutativity advisory — confirm that exemption rule for the P-09 spec.

## Part 2 — per-property targeted sample (~30% — the files with real judgment calls)

- [x] `termination-witness/positive-02-justified-recursion-limit-refinement-loop` — **IR gap:** IR v0.1 has no slot for a declared `recursion_limit`; the fixture encodes it via `remaining_steps` + guard and omits the numeric value. Feeds brief R-06's IR-SPEC.
- [x] `termination-witness/positive-04` + `negative-02` (flagship nested-SCC pair) — **Call:** per-simple-cycle witness granularity (an SCC-granular validator would wrongly pass negative-02). The P-02 spec sentence must be tightened.
- [x] `termination-witness/negative-03-counter-guard-without-wired-exit` — **Call:** is `counter-guard-without-exit-edge` a distinct condition id or a sub-case of `cycle-without-termination-witness`? (Fixture argues distinct, for diagnostics.)
- [x] `graph-well-formed/negative-03-path-map-typo-dangling-target` — **Call:** documents a within-property cascade + the open question whether implicit finish→END wiring counts toward orphan-hood.
- [x] `signature-soundness/negative-03-args-schema-type-mismatch` — **Call:** forward-looking fixture — the IR has no `args_schema` field yet, so the type mismatch lives in `source_snippet` + expected verdict only; accept as forward-looking or park until R-06 adds the field.
- [x] `effect-safety/positive-03-compensated-billable-hold-loop` — **Call:** compensation hook encoded as free-form effect tag `compensated_by:release_hotel_hold` (no dedicated annotation exists — open question RQ-04-02); also records that P-07's letter doesn't recognize compensation — a P-06/P-07 contract gap.
- [x] `determinism-replay/positive-01` + `negative-02` — **Schema gap:** no temperature slot in `@deterministic`; the pair is distinguished via a usage rule + a provisional `stochastic` effect tag. Recommended fix: DEC-03/schema addendum extending `deterministic` to `{seed, temperature}`, then rewrite negative-02.
- [x] `parallel-safety/negative-02-send-fanout-reducerless-findings` — **Call:** P-09 flags the Send *template* though a 0/1-element fan-out wouldn't collide at runtime — confirm ERROR vs degrade-to-WARNING.
- [x] `retry-coherence/positive-01` + `evolution-safety/negative-02` — spot-checks (QA found both clean; negative-02 is the witness-removed-by-evolution flagship).

## Part 3 — schema/IR gaps the authoring surfaced (decisions for briefs R-05/R-06, not fixture edits)

| Gap | Where it bit | Owner |
|---|---|---|
| No `recursion_limit` slot in the IR | P-02 positive-02 | brief R-06 IR-SPEC |
| No `args_schema` in node annotations | P-03 negative-03 | brief R-06 IR-SPEC |
| No temperature in `deterministic` annotation | P-08 pair | DEC-03 addendum + brief R-06 |
| No `retry_policy` serialization | P-07 (one leg unrepresentable) | brief R-06 IR-SPEC |
| No compensation-hook annotation | P-06 positive-03 | RQ-04-02 / brief R-05 |
| P-02 witness granularity (cycle vs SCC) ambiguous in catalog wording | flagship pair, mixed/08 | brief R-05 TERMINATION-WITNESS-SPEC |
| P-04 semantics for unreachable readers | mixed/04 vs P-01 negative-01 | brief R-05 P-04 section |

All witness shapes corpus-wide are **provisional** (marked in every fixture's `notes:`) until the PROPERTY-CATALOG-SPEC pins per-property I/O contracts — reviewing the shapes now is optional; they get reconciled mechanically when the spec lands.
