# IR-models API freeze (F3 — IR-06)

> **What this is.** The freeze record for card IR-06 (tracked in the maintainers' development-process repository).
> Master plan §3 names freeze event **F3**: "IR-models + validator-result API freezes
> (IR-06, VAL-12, at G5) — jointly the D-12 promotion trigger (CLI-08)." F3 has two
> halves owned by two different tracks. This document is the IR half — the IR pydantic
> models, node-identity grammar, and canonical serialization + hash surface
> (`gebra.ir`). The validator-result half is VAL-12's, recorded in
> [`VALIDATOR-API-FREEZE.md`](VALIDATOR-API-FREEZE.md); that document does not speak
> for this one and this one does not speak for it.

**Status: FROZEN**, recorded 2026-08-13.

## 1. What is frozen

The public surface of `gebra.ir` as landed by IR-01 through IR-05 (68 flat exports
re-exported from `gebra.ir.__init__`), specifically:

- **The core models** (IR-SPEC §2.5) — `WorkflowIR`, `Node`, `Annotations` (all fifteen
  slots, incl. the nine new-in-1.0 slots per PD-003 Appendix A: `args_schema`,
  `retry_policy`, `variant`, `compensation`, `prompt_digest`, `config_digest`,
  `runtime.recursion_limit`, `runtime.interrupts`, `runtime.checkpointer`), the
  discriminated `Edge` union (`NormalEdge`, `ConditionalEdge`, `SendEdge`, and the ir
  1.1 `DynamicEdge` — DEC-28), `Runtime`, `RecursionLimit`, `Interrupts`, `Checkpointer`,
  `RetryPolicy`, `Variant`, `Compensation`, `IdempotentKey`, `DeterministicSpec`,
  `StateField`, and the frozen `IRModel` base (`IRModel`, `extra="forbid"`, PC-1..PC-6).
  `IR_VERSION`, `IR_VERSIONS`, `IR_VERSION_DYNAMIC_EDGES`, `IrVersion`,
  `lowest_ir_version`, `refuse_dynamic_edges`, `DynamicEdgeUnsupportedError`.
- **The node-identity grammar** (IR-SPEC §5) — `NodeId`, `NodeIdStr`, `Segment`,
  `SegmentKind`, `NodeIdError`, `NodeIdErrorReason`, `RESERVED_SEGMENTS`,
  `SEGMENT_SEPARATOR`, `SYNTHETIC_KINDS`, `escape_segment`, `unescape_segment`,
  `join_node_id`, `split_node_id`, `node_id_from_names`, `synthetic_segment`,
  `parse_node_id`, `is_valid_node_id`, `validate_node_id`, the OpenInference
  derivations (`OPENINFERENCE_ID`, `OPENINFERENCE_NAME`, `OPENINFERENCE_PARENT_ID`,
  `openinference_attributes`).
- **Canonical serialization + content hash** (IR-SPEC §6) — `canonical_bytes`,
  `canonical_annotations_bytes`, `canonical_foreign_bytes`, `graph_version`,
  `render_digest`, `verify_graph_version`, `CanonicalizationError`,
  `CanonicalizationErrorReason`, `I_JSON_MAX_INT`, `I_JSON_MIN_INT`.
- **YAML/JSON loaders** (IR-SPEC §2.5 note; SOW §2 criterion 6) — `load_yaml`,
  `load_json`, `dump_yaml`, `dump_json`, `read_ir`, `write_ir`, `IRSerializationError`,
  `IRSerializationErrorReason`, `JSON_SUFFIXES`, `YAML_SUFFIXES`.

This is the **Python model/callable surface** — field sets, aliases, requiredness,
discrimination, the identity grammar's functions, and the serialization/hash entry
points — not a document-format version pin by itself. `ir_version` (currently `"1.0"`,
minimally-stamped `"1.1"` iff a `dynamic` edge is present — IR-SPEC §8, DEC-28) is the
frozen surface's own governance field and is exactly what §4 below protects.

**Freeze scope, as amended (DEC-28, 2026-08-09; per the IR-06 card's own freeze-scope
note).** This freeze covers the ir **1.1** surface, not a strict 1.0 cut: the `dynamic`
edge kind, the widened `ir_version` `Literal["1.0", "1.1"]`, and the IR-SPEC §8
minimal-stamping policy are part of what is frozen here. DEC-28's own precondition —
"the EX-03-time union widening and byte-diff must land first" — is satisfied: card
EX-03 (`status: done`, 2026-08-09) landed the model union widening, `canonical.py`'s
`_edge` branch, and the mandated golden-corpus byte-diff under spec pre-review,
per DEC-28's closing line, "IR-06 freezes the 1.1 surface as amended."

The requiredness question the vendored fixture schema and the model stub disagree on
for `retry_policy`/`variant`/`compensation` (`schema.yaml` v2.2 declares no `required`
list; the model requires every member, mirroring IR-01's `RecursionLimit` ruling) is a
known, filed divergence — PD-048 in the development-process repository,
filed by this card per the carry-forward IR-01/IR-03/IR-05 each recorded — not a frozen
ambiguity: the model, as already shipped since IR-01, is the surface this freeze fixes.

A second, ruled divergence of the same kind joined it with card IR-07 (below): the model
refuses a document repeating a node `id`, which `schema.yaml` v2.2 still admits, because
DEC-22 amended IR-SPEC §2.1 and not the vendored fixture schema. It is authorized rather than
accidental, and it leaves the §1 lockstep comparison untouched (that check compares field-name
vocabulary, which neither side changed).

**Ruled enforcement, anticipated here and since landed (card IR-07, 2026-09-04):**
`WorkflowIR` now rejects a document declaring one node `id` twice, at validation, naming the
repeated id — DEC-22's constraint, on the surface this document freezes. It is a ruled change
(DEC-22: `ir_version` stays 1.0, no emitted digest moves, loaders MUST reject duplicates)
that this freeze anticipated rather than contradicts; §4's every-change-needs-a-bump blanket
defers to DEC-22's own no-bump ruling for exactly this constraint, which tightens validation
without touching any conforming document's bytes. Measured rather than asserted: every
vendored corpus payload and every committed golden still loads, and every canonical byte
length and digest is unchanged (`tests/ir/test_node_id_uniqueness.py`). The frozen export set
in §1 is unchanged — the constraint adds no symbol, and it stays out of
`model_json_schema()`, so the IR-05 lockstep check sees the same vocabulary as before.

## 2. Validator-consumer sign-off — "the IR gives validators what they need"

Brief D-08's Definition of Done names this exact sign-off: "D-09 lead signs off:
'The IR gives validators what they need.'" That sign-off is recorded here as met, on
the evidence the VAL track's own cards produced against the surface in §1, per the same
read-off-the-exercise discipline VAL-12 used for its harness-consumer sign-off:

- **VAL-04** (P-08 `determinism-replay`, `done`, 2026-07-31) through **VAL-10** built
  the wedge-five validators as hermetic functions over `WorkflowIR` — no field the
  wedge five need (topology, edge kinds and guards, annotations, `runtime`,
  node identity) was found missing or malformed across that build.
- **VAL-11** (`verify()` aggregation + gate semantics, `done`, 2026-08-06), an IR-06
  prerequisite, is the aggregated exercise: the wedge five run in P-01-gated order over
  real IR built from real `WorkflowIR`/`Node`/`Edge`/`Annotations`/`Runtime` instances,
  the full exit-code matrix (0/1/2, strict promotion, the FATAL-no-snapshot signal) is
  reached through the **real** validators over the models this freeze covers, and
  hermeticity is proven over all 67 corpus IR snapshots.
- **TE-04** (Golden corpus green, `done`, 2026-08-06) is the corpus-scale proof: the
  full envelope + registry + `verify()` aggregation runs over the 60-fixture corpus
  loaded through `gebra.ir`'s own models, with `models_equivalent` structural
  comparison throughout — the IR was heavy-consumer-exercised, not merely type-checked.

No field, alias, or requiredness gap surfaced in that exercise that would have changed
what §1 lists — the ten weeks of validator work since IR-01 landed (2026-07-30) ran
against this surface without a model-shape change being needed to unblock it.

## 3. Snapshot-consumer sign-off — "serialization stable enough to snapshot and diff"

Brief D-08's DoD also names: "D-11 lead signs off:
'Serialization is stable enough to snapshot and diff.'" Recorded here as met, on the SD
track's own exercise, an IR-06
prerequisite (SD-01) plus its immediate successors:

- **SD-01** (Snapshot writer/reader + envelope, `done`, 2026-08-04), an IR-06
  prerequisite, wraps `WorkflowIR` in the D-11 envelope (`version`, `extracted_from`,
  `graph_version`) without widening it (`extra="forbid"` on both `IRModel` and
  `StoreModel` is honored, not fought), reuses `gebra.ir.serialization`'s emitter
  rather than growing a second one, and demonstrates round-trip byte-stability across
  runs, atomic writes surviving injected interruption at all three failure points, and
  the D-025 digest-inclusion behavior (a prompt-body-only change yields a distinct
  `graph_version` and a distinct snapshot) — directly against golden vector 001's
  `sha256:5db68464…`.
- **SD-02** (V.S.F.E parser/comparator/bumper, `done`, 2026-08-04) classifies every one
  of the 54 field paths on the live `WorkflowIR` model tree into the S/F/E component
  set and compares versions by canonical bytes through the same RFC 8785 emitter the
  digest uses — the frozen §6 canonicalization is what makes a version bump
  well-defined at all.
- **SD-03** (Snapshot engine wired to extract, `done`, 2026-08-12) snapshots the
  travel-booking agent end-to-end, with the stored `graph_version` verified equal to a
  fresh extraction's digest at every place the store records it, and re-snapshotting an
  unchanged agent proven a no-op at the byte level.
- **SD-04** (Structural diff engine v1, `done`, 2026-08-04) diffs two `WorkflowIR`s
  over a networkx topology view built from the §4.1 model, anchored on recomputed
  `graph_version`s, deterministic across runs and property-tested against the S-slice
  bridge — "snapshot **and diff**" is exercised, not only "snapshot".

Serialization proved stable under all four: no snapshot, version, or diff card needed a
model-shape change to build against `gebra.ir`, and every one of them reuses this
package's own canonicalization/serialization rather than re-deriving it.

## 4. Post-freeze change policy

As of this freeze, the surface in §1 is no longer ordinary repo-authored iteration.
IR-SPEC §8's evolution policy already governs `ir_version` and is restated here as the
operative rule for this freeze, not superseded by it:

- **Additive-optional = minor** (e.g. `"1.0"` → `"1.1"`): a new OPTIONAL
  omit-normalized slot, or a new token in a closed vocabulary (`edges[].kind` is such a
  vocabulary — DEC-28's own reading). Minor changes never alter digests of existing
  documents (§6.3's corollary), and emitters stamp the **lowest** minor sufficient for
  the document's constructs (§8's general minimal-stamping policy, generalized from
  DEC-28's `dynamic`-edge instance).
- **Breaking = major** (`"1.x"` → `"2.0"`): renaming, removing, retyping, or
  re-semanticizing a field; changing requiredness; or any change to the §6
  canonicalization rules that alters canonical bytes or digests of existing valid
  documents.
- **Every change — minor or major — REQUIRES a decision record plus an `ir_version`
  bump.** Per DEC-09's ratified policy and IR-SPEC §8 verbatim: no field of the frozen
  surface may be added, renamed, removed, retyped, or re-semanticized without a vault
  decision record (`DEC-NN`) and the matching `ir_version` bump — never an in-place
  model edit, never a quiet local change. This mirrors the WA-03/WA-04 discipline the
  frozen specs this surface implements already carry: proposal → R-06 vault sign-off
  → re-vendor commit citing the new vault hash → `ir_version` bump landed alongside the
  code change in one PR.

Additive, non-shape-changing work is unaffected — an internal refactor of `gebra.ir`
that does not move any name, alias, requiredness, discriminator, or digest byte in §1
needs no DEC/bump, exactly as before this freeze.

## 5. D-12 promotion eligibility

F3 is a joint trigger: master plan §3 names it "IR-models + validator-result API
freezes (**IR-06, VAL-12**, at G5) — jointly the D-12 promotion trigger (CLI-08)," and
CLI-08's own `prereqs` list `IR-06`, `VAL-12`, and `CLI-02` by name. This record
discharges **IR-06's half**. As of this writing, `VAL-12` (`status: done`, recorded
2026-08-08) has already discharged its half, and `CLI-02` (CLI-SPEC.md, `status: done`,
2026-08-05) is also `done` — so with this record, **all three of CLI-08's named
prereqs are `done`**, and CLI-08 becomes READY by the board's own derived-readiness
rule (master plan §6: "a freeze event lands or slips (F3 → CLI promotion becomes
READY...)"), with no further board edit needed since CLI-08's `prereqs` already name
all three cards.

This does not itself sign gate **G5**: G5's exit-card list (master plan §4) is larger
than F3's two cards, and as of this record two of its listed exit cards —
**TE-11** ("Round-trip drift tests") and **EX-15** ("Extractor API freeze + 1.x
handoff notes") — are still `status: todo`. F3 (the joint IR + validator API freeze)
is fully recorded by this document and VAL-12's; G5 itself remains open until every
listed exit card reaches `done` and the gate's evidence checklist is observed. See
the delivery plan's §4 G5 row (development-process repository), whose status line this record is cited from.
*(Postscript, added 2026-08-15: TE-11 and EX-15 subsequently landed and G5 was signed on
2026-08-13 — the master plan's G5 row is the authoritative status. The paragraph above
describes this record's own moment and stands as written.)*

## 6. What this freeze does not claim

This record states model/serialization surface stability and API freeze only. It does
not claim that the frozen surface is complete for Phase-1 scope (P-10/P-11's deferred
1.x slots remain future minors per IR-SPEC §8), that the validator-result API is this
document's to freeze (VAL-12's), that `report_format` is stamped final (CLI-08's
event), or that gate **G5** is signed (G5 requires every G5 exit card `done`, not only
the two freeze cards — see §5).
