# Extractor + annotation API freeze (EX-15)

> **What this is.** The freeze record for card EX-15 (tracked in the maintainers' development-process repository).
> Brief D-08 names this event in terms at its API-freeze milestone (freeze,
> documentation pass, handoff to the serialization and CLI tracks). The delivery
> plan lists EX-15 among
> **G5**'s exit cards ("Integrated substrate + API freezes"); it is not one of the three
> named freeze events F1–F3 (master plan §3) — G5 exits it on its own, alongside TE-11.
> This document is the extractor half of that documentation pass: the freeze of
> `gebra.extract()`, the `gebra.extraction` package, and the `@gebra.contract`
> annotation surface (`gebra.annotations`), together with the design-tracked 1.x backlog
> the specs already name but ir 1.0 has no slot for.

**Status: FROZEN**, recorded 2026-08-13.

## 1. What is frozen

The public surface of `gebra.extract()`/`@gebra.contract` and their two subpackages, as
landed by EX-01 through EX-14, EX-16, and EX-17 (all `status: done` on
`boards/extractor.md`):

### 1.1 Top-level `gebra` entry points (INTROSPECTION-SPEC §2; ANNOTATION-API-SPEC §1)

Ten names, resolved lazily out of the two subpackages below (`gebra/__init__.py`'s
`__getattr__`, PEP 562) so that neither the substrate nor the extractor is in the closure
of a bare `import gebra`: `extract`, `ExtractionError`, `contract`, `GebraContractError`,
`pure`, `effect`, `idempotent`, `deterministic`, `variant`, `compensation`.

### 1.2 `gebra.extraction` (72 exports)

- **Entry points & dispatch registry** — `extract`, `extract_builder`, `extract_compiled`,
  `extract_lcel_fragment`, `extractor_for`, `register_extractor`, `unregister_extractor`,
  `Extractor`, `Dispatch`, `ObjectFamily`.
- **Provenance envelope & compiled/LCEL facts** (IR-SPEC §4; INTROSPECTION-SPEC §4.1/§5) —
  `ExtractionEnvelope`, `ExtractedFrom`, `CompiledSurfaces`, `CrossCheck`, `FoldedDefault`,
  `Declarations`, `NodeContracts`, `NodeDigests`, `StateReading`, `PromptGap`,
  `FragmentKind`, `FragmentReading`, `stitch_fragment`.
- **Errors & the §8 warnings taxonomy** — `ExtractionError`, `ExtractionErrorReason`
  (+`LABEL_COLLISION`, the DEC-32-sanctioned additive member, 2026-08-22),
  `ExtractionModel`, `ExtractionWarning`, `ExtractionWarningCode`, `WarningRule`,
  `WARNING_RULES`, `warning_rule`, `contract_warnings`, `sidecar_warnings`,
  `unknown_node_warnings`, `out_of_range_warning`, `FINDING_CODES`,
  `HEURISTIC_GRADE_CODES`.
- **Annotation-resolution bridge** (§7.4 digests; ANNOTATION-API-SPEC §5 slot grades) —
  `ANNOTATION_SLOTS`, `AnnotationSlot`, `SlotGrade`, `slot_grade`, `CarrierRule`,
  `config_form`, `prompt_form`, `digests_for`, `coerce`, `type_identity`, `to_data`,
  `to_json`.
- **LCEL fragment kind & stock-binding admission** (§5; §7.4 (c)/(d)) — `kind_of`,
  `is_binding`, `ADMITTED_BINDING_CLASSES`, `STOCK_BINDING_NAMES`,
  `STOCK_BINDING_SUBCLASSES`, `FRAGMENT_CLASSES`, `WRAPPER_MEMBERS`.
- **Σ / state reading & node resolution** (§3 `.channels` row) — `read_state`,
  `state_schema_of`, `resolve_node`, `walk`, `UNREPRESENTABLE`,
  `UNREPRESENTABLE_REDUCER`, `UNREPRESENTABLE_TYPE`.
- **Version-compat first-extract check** (VERSION-COMPAT §4; EX-12) —
  `check_version_once`, `classify`, `classify_substrate`, `read_installed_versions`,
  `SubstrateVersions`, `VersionCheck`, `CompatClass`, `GebraVersionWarning`.
- **Sidecar loading** — `load_sidecar` (the annotation-precedence read of the resolved
  `gebra.toml` path; the sidecar model itself is §1.3's).

### 1.3 `gebra.annotations` (55 exports)

- **Decorators & the shorthand family** (ANNOTATION-API-SPEC §1) — `contract`, `pure`,
  `effect`, `idempotent`, `deterministic`, `variant`, `compensation`,
  `CONTRACT_ATTRIBUTE`, `NodeContract`, `NodeSource`, `carriable`, `GebraContractError`,
  `ContractErrorReason`, `Blocker`, `SLOT_KEYWORDS`.
- **`gebra.toml` sidecar** (§2) — `discover_sidecar`, `read_sidecar`,
  `SIDECAR_FILENAME`, `SIDECAR_SCHEMA`, `SidecarReading`, `SidecarSource`, `SidecarRule`,
  `SidecarIssue`, `repository_root`.
- **Shallow inference** (§4; DEC-08 pattern table) — `infer`, `infer_node`, `Inference`,
  `InferenceFinding`, `InferredKey`, `Pattern`, `DEFAULT_EFFECT`, `EFFECT_TAGS`,
  `NEVER_INFERRED`, `INFERENCE_SLOTS`, `read_node_source`, `SourceCache`, `SourceRule`,
  `StateSchema`.
- **Per-slot precedence & the resolved contract** (§3) — `resolve`, `Resolution`,
  `ResolutionIssue`, `ResolutionRule`, `PRECEDENCE`, `IssueKind`, `Contribution`,
  `DefaultRule`, `ANNOTATION_SLOTS`, `AnnotationSlot`, `IDENTIFIER_SLOTS`, `TIER_SLOTS`,
  `SlotGrade`, `slot_bytes`, `slot_data`, `read_contract`, `Surface`.

This is the **Python callable/model surface** — entry-point signatures, dispatch
registration, the envelope/warning shapes, and the decorator/sidecar/inference/precedence
API — not the IR document `ir_version` itself, which is IR-06's own freeze
(`IR-MODELS-FREEZE.md`). Nothing here changes what ir 1.0/1.1 can carry; §2 below is the
list of what it still cannot.

## 2. The 1.x backlog — deferred slots, each needing a future DEC

Every row below is a shape the extractor already reads, classifies, or declines today,
but for which ir 1.0/1.1 carries no ledger slot. Each is anchored to the spec section
that names the gap, and none of them may be emitted, coerced, or improvised into an
existing slot without the decision record named — that is the WA-03 discipline this
freeze exists to keep explicit rather than let drift into a quiet local call.

| # | Item | What it would carry | Spec anchor | Status |
|---|---|---|---|---|
| 1 | `projection` | Declared parent↔child state projection for a subgraph (P-10) | INTROSPECTION-SPEC §7.3 item 2; IR-SPEC §8 "Named deferred 1.x candidates: P-10 / P-11 slots" | Deferred to 1.x by walkthrough #1 (DEC-09, 2026-07-18) — **needs future DEC** |
| 2 | Subgraph child-topology expansion | Child nodes, child edges, and the child's own `entry`/`finish`/Σ for a discovered subgraph (ir 1.0/1.1 carries the parent node only) | INTROSPECTION-SPEC §4.1 (Subgraph discovery); DEC-19 (2026-08-03) | Named "the first 1.x feature"; its own design register (boundary-edge encoding, child `entry`/`finish`/Σ carriage, per-level sentinel ban, `ir_version` bump, H3 activation, P-10 consumption) is ratified as **not to be improvised in 1.0** — **needs future DEC** |
| 3 | `join_key` | Declared branch join keys for a merge node (P-11) | INTROSPECTION-SPEC §7.3 item 2; IR-SPEC §8 | Deferred to 1.x by walkthrough #1 (DEC-09, 2026-07-18) — **needs future DEC** |
| 4 | `codomain` | A router codomain declared independently of `path_map` (P-05(i) coverage) | INTROSPECTION-SPEC §7.3 item 5; §6 codomain-capture rule (DEC-29, 2026-08-10) | Disposition awaits walkthrough #2 (not ratified by walkthrough #1); today the hint lands in provenance only, warning-free — **needs future DEC** |
| 5 | `kind: join` | The all-of barrier semantics of `waiting_edges` (currently flattened to one `normal` edge per source, with a `barrier-flattened` warning) | INTROSPECTION-SPEC §7.3 item 3 | Candidate name recorded; flattening is the accepted 1.0 posture — **needs future DEC** |
| 6 | Managed-value marker slot | A `RemainingSteps`-style managed-value declaration (currently P-02 corroborating provenance only, never a core-IR field) | INTROSPECTION-SPEC §3 (`.channels` row); §7.3 item 4 | No candidate slot name yet — **needs future DEC** |
| 7 | Checkpointer *type* | Which checkpointer class/backend is configured (ir 1.0/1.1 carries only `runtime.checkpointer.present: bool`) | IR-SPEC §3.7 evolution note | "If ever wanted, lands as an additive-optional 1.x extension — never a change to `present`" — **needs future DEC** |
| 8 | Tool projection for `BaseTool`-object bindings | A bound `BaseTool` object's own surface (name/description/schema), so an edit to it moves `config_digest` the way a JSON-schema-dict tool already does | INTROSPECTION-SPEC §7.4 (c)/(d) | Recorded by EX-16 (PD-043 D4): a `BaseTool` object digests by class identity under rule 12 today; widening it is a §7.4 (b)-shaped closed-vocabulary extension — **needs future DEC** |
| 9 | Non-mirrored `StateNodeSpec` builder fields | `metadata`, `cache_policy`, `defer`, `timeout`, the error-handler pair (`is_error_handler`/`error_handler_node`) | INTROSPECTION-SPEC §3 (node-spec table row: "Read but not mirrored in ir 1.0") | Recorded by EX-05 (PD-023 D6, verbatim): dropped, not read at all — **needs future DEC** |
| 10 | Non-mirrored compiled-level provenance facts | `node_error_handler_map`; the folded-`set_node_defaults` resolution (which node declared it) | INTROSPECTION-SPEC §4.1 ("still land in provenance only — no ir 1.0 slot; candidate 1.x extensions") | Recorded by EX-05 (PD-023 D6, verbatim): carried in `CompiledSurfaces.error_handlers` / `CompiledSurfaces.folded_defaults` provenance today, not the core IR — **needs future DEC** |
| 11 | PD-028 D1 fact-pin correction | The ratified correction PD-028's consequences route to this backlog | PD-028 consequences | *(row added at the 2026-08-13 post-landing review — routed here by its PD but missing from the table as landed)* — **needs future DEC** |
| 12 | `_ChatModelBinding` exact-type posture at 1.x | Whether the stock-binding admission stays exact-type or admits subclasses | PD-028 D5 | *(added 2026-08-13, same review)* — **needs future DEC** |
| 13 | Builder-level bound-tool digest coverage | PD-028 D10's coverage gap | PD-028 D10 | *(added 2026-08-13)* — **needs future DEC** |
| 14 | Recognized-template / configurable-fields / `lc_secrets` extension points | PD-014's named extension points | PD-014 via PD-028 | *(added 2026-08-13)* — **needs future DEC** |
| 15 | `RunnableRetry` → `retry_policy` carrier | LCEL retry wrapper mapped to the declared retry slot | PD-025 | *(added 2026-08-13)* — **needs future DEC** |
| 16 | Synthetic composition kinds beyond §5.2 | New segment-kind tokens for compositions 1.0 refuses | PD-025 | *(added 2026-08-13)* — **needs future DEC** |
| 17 | Router-contract surface | `@gebra.contract` on a router is silently inert in 1.0/1.1 (PD-044 D13) | PD-044 D13 | *(added 2026-08-13)* — **needs future DEC** |
| 18 | Send-classified codomain recording | `_record_codomain` is conditional-branch-only in 1.0/1.1 (PD-044 D14) | PD-044 D14 | *(added 2026-08-13)* — **needs future DEC** |
| 19 | Non-string `path_map` label projection | Declined in 1.0/1.1 — DEC-32 rules refusal; a closed projection table (exact-type `bool` first: `"true"`/`"false"`, matching §7.4(d) Coercion K's JCS rendering) is the candidate. Design constraints from the 2026-08-20 probes bind any future table: explicit dispatch order (enum-int hybrids match two rows); no instance dunder reads (`int.__str__` resolves through `object.__str__` to a subclass `__repr__`; the safe spellings are `int.__repr__(x)` and the enum machinery's own `name` getter); composite `Flag` `.name` is `None` on py3.10 vs `"A|B"` on 3.13 (interpreter-varying — cannot enter hash scope); source-dict equal-hash merges (`{True: 'a', 1: 'b'}`) happen before extraction can see them, so collision-is-error is enforceable only post-projection; str-subclass labels never reach the table (verbatim-value, DEC-32). Trigger: a genuine production refusal report. | DEC-32 | *(added 2026-08-22)* — **needs future DEC** |

Items 9 and 10 are EX-05's non-mirrored-fields disposition (PD-023 D6), taken here
verbatim per that decision's own "Consequences" clause ("EX-15 takes D6 verbatim as the
non-mirrored-fields disposition its objective names"). One further D6 item — the subgraph
boundary-wiring encoding — is **not** listed as an open backlog row: PD-023 flagged it "a
defect rather than a backlog row until it is ruled," and DEC-19 (2026-08-03) has since
ruled it (ir 1.0 carries the parent node only; child expansion is 1.x). It appears above
as backlog item 2 instead, on its ratified DEC-19 terms.

## 3. Post-freeze change policy

An ordinary change to `gebra.extraction` or `gebra.annotations` that does not move the
surface in §1 or emit one of the §2 rows — a refactor, a new test, a bug fix to a
declined/refused shape — is unaffected by this freeze and follows the usual WA-08 review
(IR-spec and never-invokes pre-review, then human merge).

A change that would emit any §2 item — landing `projection`, `join_key`, `codomain`,
`kind: join`, a managed-value marker, checkpointer type, tool projection, or a new ledger
slot for any §3/§4.1 non-mirrored field — is a **minor `ir_version` bump** under
IR-SPEC §8's additive-optional rule, and per WA-03/WA-04 that requires a vault decision
record *first*: a proposal, R-06 vault sign-off, a re-vendored commit citing the new vault
hash, and the `ir_version` bump landed alongside the code change in one PR. None of the
backlog rows may be improvised into an existing slot, coerced into provenance-as-data, or
inferred from a heuristic in the meantime — the extractor's present posture (decline, or
provenance-only, per §2's "Status" column) is the conforming one until its DEC lands.

## 4. What this freeze does not claim

This record states extractor/annotation API surface stability and the 1.x backlog's spec
anchors only. It does not claim: that gate **G5** is signed (G5's exit-card list, master
plan §4, is larger than this one card — TE-11 is also still open as of this writing); that
any §2 backlog item is ratified (every row awaits a future DEC — "candidate" and "needs
future DEC" throughout, never "planned" or "coming"); that the IR-models freeze (IR-06) or
the validator-result freeze (VAL-12) are this document's to record — each is its own
card's; or that the rows in §2 are the *complete* set of everything ir 1.x might ever
need — they are the deferred items the specs and the EX-05/EX-16 cards name today, and a
future review may add rows the same way EX-16 added row 8.
