# REPORT-FORMAT-SPEC — the run-level report format

> **What this document is.** A repo-authored **contract specification**, produced by card
> CLI-01. It fixes the run-level wrapper that PROPERTY-CATALOG-SPEC §0.3 explicitly leaves to
> it — "all thirteen `PropertyReport`s + IR identity + exit-code derivation + serialization
> profile" — so that the rendering engine (CLI-03), the `verify()` aggregation (VAL-11) and
> the audit export (SD-07) build against one shape instead of three.
>
> **It is not user documentation and not a vendored spec.** Nothing here describes a shipped
> capability: no `gebra` command exists yet, and the tutorials that will describe one are the
> DOC track's (WA-12 — docs tell no futures). The frozen, vendored specs
> (PROPERTY-CATALOG-SPEC, IR-SPEC, TERMINATION-WITNESS-SPEC, …) live in the delivery
> repository and are read-only; this file restates them where it must and redefines nothing.
>
> **Status: FINAL.** Ratified as CLI-01's artifact, and **stamped final at the D-12 promotion
> on 2026-08-31** (card CLI-08; the record is
> [docs/governance/D-12-PROMOTION.md](../governance/D-12-PROMOTION.md), which also
> dispositions every item in Appendix B). **`report_format` is `1.1`, final.** `1.0` was this
> document's shape before VAL-11 built it and was never emitted; the one MINOR amendment since
> is recorded in §1.6, whose bump table — including the value-rule row added at the promotion
> — is the route any later change travels. Final means no Phase-0 card amends this contract
> further; editorial corrections and landing records are not amendments.

---

## Table of contents

- [0. Scope, authority, status](#0-scope-authority-status)
- [1. The run report](#1-the-run-report)
- [2. Exit-code derivation](#2-exit-code-derivation)
- [3. Run-level assembly rules](#3-run-level-assembly-rules)
- [4. The rendering catalog](#4-the-rendering-catalog)
- [5. The human profile](#5-the-human-profile)
- [6. The audit-export profile](#6-the-audit-export-profile)
- [7. Conformance obligations](#7-conformance-obligations)
- [Appendix A — SARIF 2.1.0 projection](#appendix-a--sarif-210-projection)
- [Appendix B — Open items](#appendix-b--open-items)

---

## 0. Scope, authority, status

### 0.1 One document, three surfaces

A verification run produces exactly one logical artifact — the **run report** of §1. The three
output surfaces are that one artifact seen three ways:

| Surface | Selector | Relationship to the run report |
|---|---|---|
| Human terminal | no flag (the default) | A **rendering**. Every fact it shows is read off the run report; it adds none. |
| Native JSON | `--format json` | The run report **itself**, serialized (§1.5). Lossless. |
| SARIF 2.1.0 | `--format sarif` | A **projection**: lossy, findings-only, derived from the run report and never round-tripped (PROPERTY-CATALOG-SPEC §0.5, Appendix C.3). |

The flag surface is CLI-D1's ruling (PD-015, ratified 2026-07-31): both machine formats ship
behind a single `--format`, native JSON is the source of truth every other machine format
derives from, and human terminal output stays the no-flag default. Flag spelling, the full
flag table, and verb naming belong to CLI-SPEC (card CLI-02), not here.

### 0.2 What this document fixes

1. The run-report wrapper: tool identity, subject (IR) identity, the thirteen per-property
   outcomes, and the gate outcome (§1).
2. Exit-code derivation from the §0.2 severity ladder, including strict-mode promotion and
   snapshot eligibility (§2).
3. The run-level assembly rules the per-property envelope deliberately does not state — how
   cross-property advisories are carried, and what order means above a single report (§3).
4. A rendering for **every** §0.3 witness, failure and location variant, on all three
   surfaces (§4), plus the human profile's own obligations (§5).
5. The audit-export profile SD-07 writes to `.gebra/reports/<version>.report.json` (§6).
6. The SARIF projection, restating PROPERTY-CATALOG-SPEC Appendix C as an implementable
   exporter contract (Appendix A).

### 0.3 Authority chain

| Question | Authority |
|---|---|
| Per-property result envelope (witness/failure/location models, claim classes, severities) | PROPERTY-CATALOG-SPEC §0.1–§0.4 — **frozen**; this document restates, never redefines |
| Condition IDs, their tiers and emittability | PROPERTY-CATALOG-SPEC §0.4 registry; in code, `gebra.verify.conditions.CONDITION_REGISTRY` |
| Which machine formats ship, and under which flag | PD-015 (CLI-D1 ruling, ratified 2026-07-31) |
| Human terminal rendering framework and degradation | PD-031 (CLI-D3 ruling, ratified 2026-08-04) |
| SARIF mapping | PROPERTY-CATALOG-SPEC Appendix C (memo A5) — restated in Appendix A |
| IR identity (`ir_version`, `graph_version` digest) | IR-SPEC §4.1, §6; the field ledger §7 |
| Store paths and file naming (`.gebra/reports/…`) | PD-012 (SD-D2 ruling); in code, `gebra.store.SnapshotStore` |
| V.S.F.E label grammar and bump class | `gebra.versioning` (SD track) |

Where this document and a frozen spec appear to disagree, the frozen spec wins and the
disagreement is a defect to file (WA-03), never a local reinterpretation.

### 0.4 What this document does not own

- **Verification semantics.** The run report presents verdicts; it never derives one. A
  property's verdict, its witness shape and its condition IDs are the catalog's (D-12's
  presentation-only boundary).
- **Verbs, flags, config files, diagnostics conventions.** CLI-SPEC (CLI-02).
- **Renderer architecture, palette, exact layout and wording.** CLI-03's latitude, per its
  card and PD-031; §4 and §5 fix the *facts* a rendering must carry and the copy rules it
  must obey, not its typography.
- **Diagram output.** `gebra display` and DIAGRAM-STYLE-GUIDE (CLI-06).
- **Diff and history output.** A structural diff is not a run report; see §7 note 5.
- **Store layout, snapshot writing, freshness policy.** SD track (PD-012, SD-01/SD-03/SD-07).

### 0.5 Never-invokes

Nothing in this format requires executing a workflow node, calling a model, or opening a
network connection: every field is derived from serialized IR, from the validators' structured
output, or from the run's own configuration (WA-07). A format that carried, say, an observed
runtime value would be outside what gebra can honestly produce — there is no such field, and
adding one is a scope change, not a schema change.

---

## 1. The run report

### 1.1 Shape at a glance

```json
{
  "report_format": "1.1",
  "tool": { "name": "gebra", "version": "0.0.1.dev0" },
  "subject": {
    "input_mode": "extracted",
    "source": "travel_booking:build_graph",
    "ir_version": "1.0",
    "graph_version": "sha256:5db68464…",
    "extractor_version": "0.0.1.dev0"
  },
  "properties": [
    { "property": "graph-well-formed", "result": "pass", "witness": { "kind": "well-formedness", "…": "…" } },
    { "property": "termination-witness", "result": "fail", "failure": { "…": "…" } },
    { "kind": "not-implemented", "property": "signature-soundness", "property_id": "P-03",
      "status": "deferred-to-phase-1", "detail": "…" },
    "… thirteen entries, in catalog order …"
  ],
  "best_effort": [],
  "gate": {
    "exit_code": 1,
    "outcome": "fail",
    "counts": { "fatal": 1, "error": 0, "warning": 0 },
    "strict": { "mode": "off" },
    "snapshot_eligible": false
  }
}
```

### 1.2 Normative model stubs

The stubs below are normative in the same sense PROPERTY-CATALOG-SPEC §0.3's are: they fix
field names, types, optionality and the model invariants. They follow the same A6 conventions
as the envelope they wrap — PC-1/PC-3 (frozen, `extra="forbid"`, strict), PC-2 (tuples, unions
discriminated where a discriminator exists), PC-4 (canonical serialization: definition order,
`exclude_none=True`).

```python
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gebra.verify import (  # the frozen §0.3 envelope, unchanged
    PROPERTY_SLUGS,
    AnyLocation,
    ConditionId,
    NotImplementedMarker,
    PropertyReport,
    PropertySlug,
    ReportModel,
    WitnessNoteKind,
)


class RunReportModel(ReportModel):
    """Normative base for the run-level models (A6 PC-1/PC-3).

    It *extends* the envelope's base rather than restating its config — which is the same
    `ConfigDict(frozen=True, extra="forbid", strict=True)` — so that §1.5's "in code, this
    is exactly `gebra.verify.to_data`" is true of the wrapper by construction. It inherits
    the PC-6 `model_construct()` refusal with it, for the same reason: construction that
    skips validation would skip the invariants below.
    """


class Tool(RunReportModel):
    name: Literal["gebra"]
    version: str  # the installed gebra.__version__, verbatim


class Subject(RunReportModel):
    """What was verified, and how it was obtained."""

    input_mode: Literal["extracted", "ir-document", "snapshot"]
    source: str  # see §1.3
    ir_version: Literal["1.0"]
    graph_version: str  # "sha256:<64 lowercase hex>" (IR-SPEC §6)
    version: Optional[str] = None  # V.S.F.E label; REQUIRED iff input_mode == "snapshot"
    extractor_version: Optional[str] = None  # present iff input_mode == "extracted"
    sidecar: Optional[str] = None  # the sidecar path extraction recorded, when there was one

    @model_validator(mode="after")
    def _snapshot_carries_its_label(self) -> "Subject":
        if (self.input_mode == "snapshot") != (self.version is not None):
            raise ValueError("`version` present iff input_mode == 'snapshot'")
        return self


class StrictPolicy(RunReportModel):
    """The strict-mode request in force for this run (§0.2), recorded as given."""

    mode: Literal["off", "all", "per-property"]
    properties: tuple[PropertySlug, ...] = ()  # non-empty iff mode == "per-property"

    @model_validator(mode="after")
    def _properties_iff_per_property(self) -> "StrictPolicy":
        if (self.mode == "per-property") != bool(self.properties):
            raise ValueError("`properties` non-empty iff mode == 'per-property'")
        return self


class Promotion(RunReportModel):
    """One WARNING-grade record the strict policy promoted at the gate (§2.3).

    The record it names is unchanged in `properties`: promotion moves the gate, never the
    record (PROPERTY-CATALOG-SPEC §0.2). Nothing here carries a severity or a claim class —
    the promoted record keeps its own where it stands, and a promotion is a pointer at it.
    """

    property: PropertySlug  # the OWNING property of the record (§2.3)
    origin: Literal["failure", "co-failure", "advisory", "witness-note"]
    # The identity the promoted item is REPORTED UNDER, never a grade (§2.3). Required on a
    # finding origin, where it is the record's own condition ID. On a witness-note promotion
    # it is present iff the owning property's spec fixes an identity for the promoted note
    # kind — TERMINATION-WITNESS-SPEC §6.1 does, for P-02's only promotable kind; nothing
    # else does, and inventing one would breach the §0.4 registry discipline.
    property_condition: Optional[ConditionId] = None
    note_kind: Optional[WitnessNoteKind] = None  # present iff origin == "witness-note"
    location: Optional[AnyLocation] = None

    @model_validator(mode="after")
    def _origin_fixes_what_a_promotion_names(self) -> "Promotion":
        is_note = self.origin == "witness-note"
        if is_note != (self.note_kind is not None):
            raise ValueError("`note_kind` present iff origin == 'witness-note'")
        if not is_note and self.property_condition is None:
            raise ValueError("a finding-origin promotion names the record's condition ID")
        return self


class SeverityCounts(RunReportModel):
    """Findings by severity (§2.1). Derived; a consumer that recomputes gets the same numbers."""

    fatal: int
    error: int
    warning: int


class ToolError(RunReportModel):
    """Why no verdict was reached (§2.4). `detail` is display-only prose; never parsed."""

    stage: Literal["input", "extraction", "ir-validation", "dispatch"]
    detail: str


class GateOutcome(RunReportModel):
    exit_code: Literal[0, 1, 2]
    outcome: Literal["pass", "pass-with-notes", "fail", "tool-error"]
    counts: SeverityCounts
    strict: StrictPolicy
    promotions: tuple[Promotion, ...] = ()
    snapshot_eligible: bool

    @model_validator(mode="after")
    def _the_word_and_the_code_agree(self) -> "GateOutcome":
        """§2.2's "the two never disagree", enforced rather than restated."""
        expected = {"pass": 0, "pass-with-notes": 0, "fail": 1, "tool-error": 2}
        if expected[self.outcome] != self.exit_code:
            raise ValueError(f"outcome {self.outcome!r} and exit code {self.exit_code} disagree")
        if self.outcome == "tool-error" and self.promotions:
            raise ValueError("a tool-error run reached no verdict and promoted nothing")
        return self


#: One property's answer: a verdict, or the structured statement that no verdict was reached.
#: Resolution is left to right, and deterministic: NotImplementedMarker requires `kind`, which
#: PropertyReport forbids. This is exactly what `gebra.verify.run_property()` returns.
PropertyOutcome = Annotated[
    Union[NotImplementedMarker, PropertyReport], Field(union_mode="left_to_right")
]


class RunReport(RunReportModel):
    """The run-level wrapper (PROPERTY-CATALOG-SPEC §0.3 scope boundary)."""

    report_format: Literal["1.1"]
    tool: Tool
    subject: Optional[Subject] = None  # absent only when a ToolError preceded IR identity
    properties: tuple[PropertyOutcome, ...] = ()
    # The properties whose outcomes in THIS run are best-effort diagnostics rather than
    # contract-bearing verdicts — PROPERTY-CATALOG-SPEC §0.3's P-01-clean precondition,
    # reported instead of left to the reader. Non-empty exactly when P-01 produced a FATAL
    # finding, in which case it is (P-02, P-04, P-06) in catalog order; empty otherwise.
    best_effort: tuple[PropertySlug, ...] = ()
    gate: GateOutcome
    error: Optional[ToolError] = None

    @model_validator(mode="after")
    def _tool_error_is_the_whole_run(self) -> "RunReport":
        if (self.error is not None) != (self.gate.exit_code == 2):
            raise ValueError("`error` present iff exit_code == 2 (§0.2: exit 2 is never a verdict)")
        if self.error is not None:
            if self.properties:
                raise ValueError("a tool-error run reached no verdict and carries no outcomes")
            if self.best_effort:
                raise ValueError("a tool-error run reached no verdict to qualify")
            return self
        if self.subject is None:
            raise ValueError("`subject` may be absent only on a tool-error run")
        slugs = tuple(outcome.property for outcome in self.properties)
        if slugs != PROPERTY_SLUGS:  # the thirteen catalog slugs, in catalog order
            raise ValueError("a verdict run carries all thirteen properties, in catalog order")
        return self
```

### 1.3 Field notes

- **`tool.version`** is the installed package version verbatim (`gebra.__version__`). It is the
  one field whose value legitimately differs between two runs over identical input; goldens
  normalize it rather than pinning it.
- **`subject.source`** is a label, not a locator to resolve:
  - `input_mode: "extracted"` → the target reference the invocation resolved, verbatim (e.g.
    `travel_booking:build_graph`; CLI-SPEC §2.1–§2.2). An in-process caller that named no
    reference supplies its own label — the field is required and the report never invents one.
    **Amended 2026-08-05 (CLI-02).** This bullet read "the extraction envelope's
    `extracted_from.source` verbatim". That field is the extracted *object's type* identity
    (`gebra.naming.type_identity`, e.g. `langgraph:StateGraph`), so it is the same string for
    every extracted run — which would collapse `automationDetails.id` (A.7) onto one value for
    every workflow in a repository, defeating the reason A.7 gives for deriving it from
    `subject.source`. The example was always the invocation's own reference; the pointer beside
    it was wrong, and the rule now says what the example showed. The type identity stays in the
    extraction envelope and is not duplicated here. No model changes, so no `report_format`
    bump (§1.6).
  - `input_mode: "ir-document"` → the IR document path exactly as the invocation gave it;
  - `input_mode: "snapshot"` → the stored snapshot's `extracted_from.source` (the store's own
    provenance field, which is free text the producer chose — `gebra.store.ExtractedFrom` —
    not the extraction envelope's type identity).
- **`subject.graph_version`** is the IR-SPEC §6 content digest of the **core IR** — the same
  string the snapshot envelope carries, byte-for-byte (`"sha256:<hex>"`). It is provenance and
  identity for a report, never a claim about behavior: two reports with the same digest were
  produced over IRs with the same canonical form.
- **`subject.version`** carries the V.S.F.E label when — and only when — the run is bound to a
  stored snapshot (§6). A `verify` run over a live target has no label yet; deciding one is
  SD-03's, not this report's.
- **`best_effort`** is derived from P-01's own outcome, and it is a *qualification*, not a
  suppression: the three properties it names still carry their full reports, and a reader is
  told how to weigh them. PROPERTY-CATALOG-SPEC §0.3 defines P-02, P-04 and P-06 results only
  over P-01-clean topology and calls their reports on a P-01 failure "best-effort diagnostics,
  not contract-bearing verdicts" — a distinction that lived only in the spec until this field
  carried it into the artifact. It is not a second gate: the run already exits `1` with no
  snapshot on P-01's FATAL alone (§2.5), whatever the other four found.
- **`gate.counts`** and **`gate.promotions`** are derived from `properties` (§2). They are
  carried because every consumer needs the headline, and because a renderer that recomputed
  them independently would be a second place for the derivation to drift.
- **No wall-clock field exists anywhere in the run report.** A timestamp would make two runs
  over one unchanged workflow compare unequal, and every golden in CLI-07 and every audit
  export in §6 depends on byte-reproducibility. Dating belongs to the layer that dates
  something: the snapshot envelope's `extracted_from.extracted_at`. The extraction envelope
  already declines the same field for the same reason.

### 1.4 Ordering, completeness and determinism

1. **All thirteen, always.** A verdict run carries one outcome per catalog slug, in the catalog
   order `P-01 … P-13` (`gebra.verify.PROPERTY_SLUGS`). A property with no registered validator
   contributes a `NotImplementedMarker`, never an omission and never a pass.
2. **A missing wedge validator is a tool error, not a thin gate.** If any member of the wedge
   five (P-01, P-02, P-04, P-06, P-08) has no registered validator, the run is exit `2` with
   `error.stage: "dispatch"` (§2.4). A run that silently checked four of the five would be a
   weakened gate wearing a pass.
3. **Within a property, order is the catalog's.** Each §P-nn section fixes its own ordering
   rule for its records (which finding is primary, and the order of `co_failures`); the run
   report carries that order through untouched.
4. **Above a property, order is not normative** — see §3.3.
5. **Determinism.** Given the same IR, the same registered validators and the same strict
   policy, the run report is byte-identical across runs, processes and platforms, with
   `tool.version` the only environment-dependent value.

### 1.5 Serialization profile

- **Encoding** UTF-8, no BOM. Newlines LF. A report written to a file ends with a single
  trailing newline; a report written to a stream does not add one.
- **Member order** definition order, as the stubs declare it — never alphabetical, never
  sorted at write time.
- **Absent optionals are omitted**, not `null` (`exclude_none=True`, PC-4). Omission
  round-trips: a key the producer never set and a key a consumer drops read back the same.
- **Indentation** two spaces, matching `.editorconfig`; the compact single-line form is
  available for stream consumers and carries identical content.
- **Non-ASCII characters stay themselves** (`ensure_ascii=False`).
- In code, this is exactly `gebra.verify.to_data` / `gebra.verify.to_json` — the profile the
  per-property envelope already serializes under, applied to the wrapper.
- **The run report is not JCS-canonicalized.** JCS is the IR digest path (IR-SPEC §6); a report
  is not hashed, and imposing a second canonicalization would invite the two to be confused.

### 1.6 `report_format` versioning

`report_format` is a `MAJOR.MINOR` string, independent of `ir_version`, of the SARIF version and
of the package version. The pairing a consumer cares about rides the document itself:
`subject.ir_version` says which IR the subject is, `tool.version` says which build produced it.

| Change | Bump |
|---|---|
| A new optional member; a new member joining a discriminated union (a witness `kind`, a location subtype, a condition ID ratified into §0.4) | MINOR |
| A new `NotImplementedStatus`, a new `Promotion.origin`, a new `input_mode` | MINOR |
| An existing optional member's present-iff rule widens, so a document carries it where `1.x` did not | MINOR — the documents are a superset, and a strict consumer built against the narrower rule may refuse one (added at `1.1`, VAL-11; the **present-iff half** of the class OI-7 flagged as unrowed, which is the class the `1.1` amendment itself is) |
| A documented member's **value rule** widens, or the same value comes to mean something else, while the model is untouched | MINOR — the model parses either way, so the break is not a parse error but a misreading: a consumer built against the narrower rule may refuse a value it was never told to expect, or, worse, accept one and read it wrong (added at the D-12 promotion, CLI-08 — the **value-rule half** of OI-7's class). **This row reaches only members whose value rules this document owns**; values fixed by PROPERTY-CATALOG-SPEC — condition IDs (§0.4, string-identical across analyses by SARIF contract), claim classes (§0.1), severities and exit codes (§0.2) — change only by catalog addendum under WA-03, never by a bump here |
| A documented member's **value rule** narrows or is merely made precise, admitting nothing a consumer was not already told to expect | none — every conforming document a consumer will meet is one it could already read, and its reading of it does not change. The 2026-08-05 `subject.source` correction (§1.3) is the worked example: the field always held the invocation's own reference, and the pointer beside the example was what was wrong |
| Removing a member, retyping one, making an optional member required, renaming anything | MAJOR |
| Any change to exit-code derivation (§2), to the finding set (§2.1), or to strict-mode reach (§2.3) | MAJOR |
| Editorial change, clarified prose, a new illustrative example | none |

**Where two rows apply, the more severe class governs.** The table is read as a whole, not
top to bottom: a value-rule change that also moves exit-code derivation, the finding set or
strict-mode reach is MAJOR by that row, whatever the value-rule rows would say on their own.
Stated because the value-rule rows are the two most likely to be classified from the table
alone.

Because every model is `extra="forbid"`, a strict consumer built against `1.0` will reject a
`1.1` document that uses a new member. That is the intended failure: **read `report_format`
first**. A consumer MUST refuse a MAJOR it does not know, and MAY refuse a higher MINOR;
a consumer that wants tolerance reads the fields it knows off the parsed JSON rather than
loosening the models.

`report_format` is fixed by this document and was **stamped final at the D-12 promotion on
2026-08-31** (CLI-08; [docs/governance/D-12-PROMOTION.md](../governance/D-12-PROMOTION.md)).
It is `1.1`, and no Phase-0 card moves it: before the stamp an amendment was an ordinary edit
to this file by whichever card found the need — that is how `1.1` landed at VAL-11 — and after
it, a bump needs its own card, its own row in the amendment log, and the CHANGELOG entry that
always went with one. The two value-rule rows above were added by the promotion itself and are
not a bump: they classify future changes without making one, on this table's own
"editorial change, clarified prose" row.

**Amendment log.**

| Version | Change | Class | Landed |
|---|---|---|---|
| `1.0` | The shape as first specified. Never emitted by anything: no `RunReport` existed in code until VAL-11 built one. | — | CLI-01 |
| `1.1` | Two members join shapes that did not carry them at `1.0`: `Promotion.property_condition` on a `witness-note` promotion (§2.3), and `RunReport.best_effort` (§1.3). Two invariants `1.0` stated only in prose become model validators — §2.2's "the two never disagree" on `GateOutcome`, and `Promotion`'s own present-iff rules. | MINOR — `best_effort` on the new-optional-member row; `property_condition` on the present-iff row, which this amendment added because it was the class OI-7 flagged as unrowed and this is an instance of it (its field declaration is unchanged; what widened is when it is populated) | VAL-11, 2026-08-06 |

The `1.1` amendment is recorded rather than folded in because §1.6's rule is applied
literally, on the CLI-02 precedent (its `subject.source` amendment was measured against this
same table and came out "no bump"). That no `1.0` document was ever produced is why the class
is the mild one and not a compatibility event; it is not a reason to skip the bump.

---

## 2. Exit-code derivation

PROPERTY-CATALOG-SPEC §0.2 fixes the ladder and the three codes; this section fixes the
derivation over a whole run, which is the only part §0.2 leaves open.

### 2.1 The finding set

A **finding** is any emitted record that carries a `severity`:

- the primary `Failure` of every `PropertyReport` whose `result` is `"fail"`;
- every `CoFailure` in that failure's `co_failures`;
- every `Advisory` in its `advisories` (always WARNING-grade, §0.3).

A **note** is a `WitnessNote` with `severity: "warning"`, wherever the record carries one:
on a passing report's witness, and — per DEC-23 (PD-037 Q2), which makes the carriage
unconditional so that a failing property never silently drops one — on `Failure.notes` or
`CoFailure.notes` of a failing report. §2.3's reach table places no passing-report
restriction on the `WitnessNote` row, and P-02's `scc-covered-only-by-recursion-limit` is
promotable on both paths (a blanket-covered SCC rides the failure when another P-02 finding
gates the report). Promoting a fail-path note changes no exit code — the report already
carries the finding that made it `1` — but omitting it from `gate.promotions` would
understate what a strict run selected.

Notes are not findings: they never fail a gate on their own, and they are counted separately
from `gate.counts`. Everything else in a witness is evidence, not a grade.

`gate.counts` tallies findings only, by their own per-record `severity` — never by the property's
`PropertyEntry.severities` union, which is a documentation-level statement about what a property
*can* emit.

### 2.2 Derivation

```
if a tool error occurred (§2.4):
    exit_code = 2, outcome = "tool-error"
elif any finding has severity in {"fatal", "error"}:
    exit_code = 1, outcome = "fail"
elif strict promotion (§2.3) selected at least one WARNING-grade record or note:
    exit_code = 1, outcome = "fail"
elif any finding or note is WARNING-grade:
    exit_code = 0, outcome = "pass-with-notes"
else:
    exit_code = 0, outcome = "pass"
```

`outcome` is a display-and-branching convenience; `exit_code` is the contract. The two never
disagree: `"fail"` and `"tool-error"` are the non-zero outcomes, `"pass"` and
`"pass-with-notes"` the zero ones.

**`result: "fail"` is not the same as a failed gate.** A property whose findings are all
WARNING-grade — P-08 `determinism-replay` is the catalog's home case, every one of its
conditions being a WARNING from a HEURISTIC property — reports `result: "fail"` in the record
and leaves the run at exit `0` unless strict mode names it. The record says what was found; the
gate says what CI does about it, and §0.2 keeps those two separate on purpose.

A `NotImplementedMarker` never contributes to the exit code. It is neither a pass nor a fail:
the eight non-wedge properties are out of Phase-0 scope (SOW §8), and a run is not stronger or
weaker for having said so.

### 2.3 Strict mode

`--gebra-strict` (bare) promotes every WARNING; `--gebra-strict=<slug>[,<slug>…]` promotes only
the named properties' WARNINGs (§0.2). The policy in force is recorded verbatim in
`gate.strict`, so a reader of the report knows which gate produced the code.

**Reach.** Promotion selects, from the run:

| Promotable record | Owning property (what the policy matches on) |
|---|---|
| A `Failure` with `severity: "warning"` | the report's own `property` |
| A `CoFailure` with `severity: "warning"` | the record's own `property` field |
| An `Advisory` (always `warning`) | the record's own `property` field — **not** the host report's |
| A `WitnessNote` with `severity: "warning"` | the report's own `property` |

The advisory row is the one that is easy to get wrong: `--gebra-strict=determinism-replay` promotes
a P-08 advisory riding a P-09 report, because the advisory is P-08's finding wherever it is
carried. §0.2's promotion rule is about findings, not about hosts.

**The record never changes.** A promoted finding keeps `severity: "warning"` and its claim class
in `properties`; the only trace of promotion is `gate.exit_code`, `gate.outcome` and the
`gate.promotions` list. Rewriting a HEURISTIC advisory into an ERROR to explain a non-zero exit
would be exactly the overstatement WA-06 exists to prevent.

**What a promotion names (amended at `1.1`, VAL-11).** `Promotion.property_condition` is the
identity the promoted item is **reported under** — never a grade, never an input to
`gate.counts`, and never rendered with a finding's weight (§4.6 rule 8). On a finding origin it
is the record's own condition ID. On a `witness-note` origin it is present when the owning
property's own spec fixes an identity for the promoted note kind, and absent when none does:

- P-02's `scc-covered-only-by-recursion-limit` promotes under
  `cycle-without-termination-witness`, with `blanket_only: true` on the `P02SccLocation` this
  promotion carries. That is TERMINATION-WITNESS-SPEC §6.1's third profile row verbatim — "the
  strict promotion reuses the same condition ID; `blanket_only` is the distinguishing
  structured field — no new condition ID is introduced". `gate.promotions` is the only artifact
  a promotion ever appears in (§4.3: a note "does not project" to SARIF), so this is the one
  place that frozen rule can be realized; at `1.0` it had none, which is the gap VAL-08 handed
  forward and this amendment closes.
- Every other WARNING-grade note promotes with no `property_condition`. §0.2's reach is about
  severity, so the note is still selected; minting a name for it would breach §0.4's closed
  registry, and the run report does not.

The identity is resolved by the owning property, not by the aggregation: in code,
`gebra.verify.strict_promotions` applies §6.1's rule for P-02, including its refusals (a
WARNING-grade kind with no §6.1 row raises rather than being dropped, and the ID is
re-resolved through the §0.4 emission gate).

**The pass stays a pass in the record.** A pass-with-notes report whose note was promoted still
reads `result: "pass"` with its witness intact; the run around it exits `1`.

### 2.4 Tool error (exit 2)

Exit `2` means no verdict was reached. `error.stage` says where it stopped:

| `stage` | When |
|---|---|
| `input` | The invocation could not be resolved to a subject at all (no such target, unreadable file). |
| `extraction` | `gebra.extract()` failed on a live target. |
| `ir-validation` | The IR document did not validate against `ir_version` 1.0. |
| `dispatch` | The run could not be assembled: a wedge validator is not registered (§1.4 rule 2), a validator returned a report for a different property, or the gate could not be derived from the outcomes (below). |

A tool-error run carries `properties: []` and, where identity was never established,
`subject: null`. Partial outcomes are deliberately not carried: exit `2` is "no verdict", and a
half-populated list invites reading one anyway. `error.detail` is display-only prose.

An exception escaping a validator is a tool error, never a fail: a crash is not a finding.

**And so is a gate that cannot be derived** (added at `1.1`, VAL-11). §2.3 lets a property refuse
to promote a record it cannot name — P-02 raises rather than dropping a promotion a strict run
selected, because a dropped promotion is a gate the user was owed. A refusal is not a verdict
about the workflow, and it must not be a policy-dependent crash either: without this rule the same
IR would answer normally with strict off and raise with strict on. It lands as `dispatch` with the
refusal in `error.detail`, which makes `verify()` **total** — every call returns a run report, and
a consumer never has to handle both a report and an exception.

### 2.5 Snapshot eligibility

§0.2: a FATAL finding means **no snapshot is recorded**. `gate.snapshot_eligible` carries that
decision as a field so the CLI and the SD engines read one rule rather than each re-deriving it:

```
snapshot_eligible = (exit_code != 2) and (counts.fatal == 0)
```

ERROR-grade findings do **not** suppress recording (§0.2: "CI gate blocks; snapshot recorded"),
and neither do WARNINGs, promoted or not — promotion moves the gate, not the ladder.
`snapshot_eligible` is a statement about the §0.2 rule only; whether a snapshot is actually
written also depends on the verb the user invoked and on SD-03's re-snapshot policy.

---

## 3. Run-level assembly rules

§0.3 specifies one property's report. Three questions only arise once thirteen of them sit in one
document, and §0.3's scope boundary hands them here.

### 3.1 One property, one outcome

The run report holds exactly one entry per catalog slug. It never merges findings from different
properties into one report's `co_failures`: §0.3 makes `co_failures` **same-property** carriage,
and a merged list would contradict it. Cross-property carriage has exactly one licensed shape —
the `Advisory` (§3.2).

### 3.2 Cross-property advisory carriage

A validator sees only its own findings, so advisories are assembled **above** the validators, by
the aggregation that builds the run report. The rules:

1. **Only WARNING-grade findings may be carried as advisories** (§0.3). An ERROR- or FATAL-grade
   finding is that property's own report to make, and it already has one in the same run.
2. **Carriage never removes the source record.** An advisory is a pointer for the reader of the
   host report; the finding also stands in its own property's outcome, with its full shape. A
   run report therefore never loses a finding by carrying it, and never invents one.
3. **The advisory's location is the §0.3 anchor.** When a finding is projected onto another
   property's report, its location is reduced to the anchor variant (`kind` plus the anchor's
   own fields), dropping the concrete subtype's evidence members. The full evidence stays where
   the full record is. This matches the corpus precedent — `mixed/03` carries P-08 advisories
   with a bare `NodeLocation` while P-08's own report anchors on `DeterminismNodeLocation` —
   and it is the reading the models already admit: `Advisory.location` accepts either shape
   for loading (PC-6's fixture duty), and this rule fixes what an assembler *emits*.
4. **`subsumed_by` is carried, never inferred.** One root cause, one report (DEC-05 D2): if a
   record names an upstream owner, the run report keeps that attribution as given. The
   aggregation does not compute subsumption of its own.

Fidelity-matrix note: entry `FM-004` records that the advisory location shape awaited "whichever
of the §P-09 merge or REPORT-FORMAT-SPEC lands first". Rule 3 is this document meeting it. The
matrix entry stays open until the golden harness observes the projected shape — closing a matrix
row that still reproduces is the one thing the harness's two-way cross-check refuses.
**TE-04 (2026-08-06) made it observe it, and the row is closed.** The harness's `PR-3`
obligation *is* a rule-3 comparison: the fixture states what P-08's findings look like riding
another property's report, and the harness was comparing that projected form against P-08's own
un-projected records. Applying `anchor_location` to both sides is the rule, not a relaxation of
the comparison — and it is idempotent on the side that was already an anchor. What rule 3 does
**not** decide, and what nothing in this document decides, is which host report a WARNING-grade
finding rides; that is still §P-09's, and it is why `verify()` assembles no advisories.

**What the Phase-0 aggregation actually assembles (VAL-11, recorded rather than left to be
inferred).** `verify()` carries **no** advisories of its own, and that is the rules above
applied rather than a gap in them. Rule 3 fixes the *shape* an assembler emits; nothing in any
frozen spec fixes **which** host report a WARNING-grade finding rides, and rule 2 makes the
question cost nothing — carriage never removes the source record, and a run report carries all
thirteen outcomes, so no finding is lost by not being projected. Inventing a host rule would be
verification semantics (§0.4's boundary), not presentation. The rule-3 projection itself ships
as `gebra.verify.anchor_location`, so the assembler that does need it — a renderer merging a
cross-property view, or a §P-09 merge that fixes a host rule — has one implementation of it
rather than one each. ~~`FM-004` therefore stays open on its own terms: its host report is
P-09's, whose section is not drafted.~~ **That inference was wrong and TE-04 closed the row;
the reasoning above it is not.** Which host report a WARNING-grade finding rides is still
§P-09's question, and `verify()` still assembles no advisories for exactly the reason stated
here. What does not follow is "so the harness can observe no projected shape": the golden
harness's `PR-3` obligation never compared against `verify()`'s output — it compares the
fixture's advisory records against the property's *own* report, which is a projected form
against an un-projected one, and rule 3 is what makes them comparable. See the note above.

### 3.3 Order above a property is not normative

Within one property's report, order is exact and the catalog's (§1.4 rule 3). Above it — the
order in which several properties' records are presented, merged or listed by any consumer —
**order carries no meaning**: records are identified by `(property, property_condition, location)`
and never by position. Two run reports whose per-property records agree are the same run report,
however a renderer chose to interleave them.

This is the run-level answer to fidelity-matrix entry `FM-007`, which records a merged
cross-property list in `mixed/04` whose order matches neither P-01's own order (PROPERTY-CATALOG-SPEC
§1.4 Step 5) nor catalog order, and names "a merged-list ordering rule (REPORT-FORMAT-SPEC or a
§0.3 addendum)" as its resolution. The rule is: there is no normative merged order, because the run
report has no merged list — and any consumer that builds one for display is free to order it as it
likes. This does **not** relax the within-report order each §P-nn section fixes, which stays exact
and exactly compared; and it
does not itself close `FM-007`, whose residue is a fixture-authoring/projection question the
harness still observes.

**TE-04 (2026-08-06) closed that residue with the `PR-1` amendment this rule licenses, and the
line above is what licensed it.** `mixed/04`'s vendored `co_failures` is a merged list; the
harness's `PR-1` projection restricts it to P-01's records and used to compare the result
positionally against P-01's §1.4 Step 5 order — a normative order tested against one this
section says carries no meaning. `PR-1` now compares the restricted records of a *merged*
source as a multiset and everything else in the report exactly. The scope is deliberately the
narrow one: `Failure.co_failures` is **not** marked `SetCompared`, because that would assert
what §1.4 Step 5 denies, and P-01's own order stays pinned in its validator suite.

### 3.4 The corpus's `multi-property` wrapper is not the run report

`mixed/10` carries `witness: {kind: "multi-property", properties: {<slug>: <witness>, …}}` — a
mapping of slug to witness. That is a **fixture-authoring convention** for expressing a whole
run inside one fixture's `expected:` block, bridged by the golden harness's `PR-4` projection.
The run report is not a fixture `expected:` block: it is a tuple of thirteen outcomes in catalog
order, and it carries markers and a gate, which no fixture does. Neither shape is derived from
the other, and a producer of one must not emit the other.

---

## 4. The rendering catalog

### 4.1 How to read it

Every §0.3 variant a run report can carry appears below with a rendering on all three surfaces.
The catalog is the acceptance surface of this card: if a variant exists in the envelope, it has a
row here.

- **Native JSON** — the variant's own PC-4 serialization (§1.5). This column states what, if
  anything, the wrapper adds; "as serialized" means the wrapper adds nothing and the envelope's
  own shape is the answer.
- **Human** — the **facts that must appear**, normatively. Layout, ordering within a block,
  color, box-drawing and phrasing are CLI-03's latitude (its card and PD-031 reserve them); the
  fact set and the copy rules of §4.6 are not.
- **SARIF** — the projection, or `does not project`. Pass witnesses have no SARIF home at all
  (Appendix C.3); saying so per variant is the point of the column, not an omission.

Class names below are the models in `gebra.verify`, which are PROPERTY-CATALOG-SPEC §0.3's
stubs as built.

### 4.2 Report-level variants

| Variant | Native JSON | Human — facts that must appear | SARIF |
|---|---|---|---|
| `PropertyReport` (`result: "pass"`) | as serialized, inside `properties` | property id + slug; the word *pass*; the **claim class**, read from the property catalog (a pass carries no per-record grade); a witness summary per §4.3 | does not project (C.3) |
| `PropertyReport` (`result: "fail"`) | as serialized, inside `properties` | property id + slug; the primary finding rendered per §4.4; every co-failure and advisory rendered too — never summarized away | one `result` per finding (A.4) |
| `NotImplementedMarker` (`status: "deferred-to-phase-1"`) | as serialized, inside `properties` | property id + slug; *not checked*; that it is outside the Phase-0 wedge; explicitly **not a pass** | does not project — a rule with no result would advertise a check that did not run |
| `NotImplementedMarker` (`status: "not-yet-implemented"`) | as serialized | as above, with the reason being that no validator is registered in this build | does not project |
| `ToolError` | `error`, with `properties: []` | the stage; the detail prose; that no verdict was reached; exit code 2 | a valid log with `results: []` MAY be written; it MUST NOT be presented as a clean run (A.7) |
| `GateOutcome` | `gate` | counts by severity; the exit code and why; snapshot eligibility per §2.5; the strict policy in force and what it promoted | run-level properties (A.7) |
| `Promotion` | as serialized, inside `gate.promotions` | the owning property; what was promoted (the record's condition id, or the note kind); its location; that the record is **unchanged** and keeps its own WARNING grade. A `property_condition` here is the identity the item is *reported under* — never shown as a severity, never as a second finding (§4.6 rule 8) | does not project — a promotion is a gate decision, not a finding |
| `RunReport.best_effort` (non-empty) | as serialized | which properties this run answered on topology their contract does not cover, and that their reports are **diagnostics, not verdicts** (§1.3); shown beside those reports, not only in the summary | does not project — SARIF has no place to qualify a result's weight, so the qualification stays in the native report |
| `RunReport.best_effort` (empty) | as serialized (`[]`) | nothing — an empty list is the normal case and needs no line | — |

### 4.3 Witness variants

Every member of the §0.3 `Witness` union, and every substructure under it.

| Variant | Native JSON | Human — facts that must appear | SARIF |
|---|---|---|---|
| `WellFormednessWitness` (`kind: "well-formedness"`) | as serialized | how many nodes are reachable from START; the terminal nodes; that the orphan check and the unresolved-target check were evaluated and found empty — the two empty tuples are evidence, not padding, and a rendering that drops them loses the claim | does not project |
| `TerminationWitness` (`kind: "termination"`) | as serialized | the inventory size and the form of each entry; that a re-checkable acyclicity certificate is present; every note (below); the census when present. Wording is **witness presence** only (§4.6) | does not project |
| ↳ `WitnessInventoryEntry` form `a` (`CounterGuardSource`, `GuardEdgeRef`) | as serialized | the guard edge as `<source> --<label>-->`; the counter key; the declared bound; what it discharges | — |
| ↳ `WitnessInventoryEntry` form `b` (`RecursionLimitSource`, `RecursionLimitDecl`) | as serialized | that the cover is the graph-level `recursion_limit`, its value and its declared justification; that it is a blanket over the edge set rather than a per-loop bound | — |
| ↳ `WitnessInventoryEntry` form `c` (`VariantSource`, `VariantDecl`) | as serialized | the carrier node; the variant key and declared measure; that the measure is **declared and trusted**, not checked | — |
| ↳ form `c` with `discharges: []` | as serialized (empty tuple) | that the annotation is declared on a node lying on no cycle — surfaced as declared content, with **no finding of any severity** implied | — |
| ↳ `WitnessNote` `scc-covered-only-by-recursion-limit` | as serialized | the note kind; its `warning` severity; the residual SCCs in `locations`; that it is promotable under a strict flag naming P-02 | does not project (a note is not a finding) |
| ↳ `WitnessNote` `recursion-limit-without-justification` | as serialized | the note kind and severity as carried | does not project |
| ↳ `WitnessNote` `variant-key-not-in-state` | as serialized | the note kind and severity as carried; the carrier `node` and missing `key` | does not project |
| ↳ `WitnessNote` `counter-key-not-qualified` | as serialized | the note kind; the near-missed guard edge (`guard_edge`), the unmatched `identifier`, and — for the wrong-type case — the `declared_type` (DEC-23, PD-037 Q2). On a failing report the same note rides `Failure.notes`/`CoFailure.notes` and MUST still render | does not project |
| ↳ `WitnessNote` `cycle-census-capped` | as serialized | that enumeration stopped at the cap, so no census list is carried — never rendered as "no cycles" | does not project |
| ↳ `CycleCensus` | as serialized | that the census is exhaustive under the cap, and the cycles it lists | — |
| `DataflowWitness` (`kind: "dataflow"`) | as serialized; `coverage` order is not normative (`SetCompared`) | how many (reader, key) obligations were covered; on request, the per-obligation writers | does not project |
| ↳ `DataflowCoverage` | as serialized | the reading node, the key, and the covering writers — with `START` shown as the boundary source, not as a node | — |
| `EffectSafetyWitness` (`kind: "effect-safety"`) | as serialized | the cycle inventory; one line per effect record (below) | does not project |
| ↳ `P06EffectRecord`, `region: "retry"` | as serialized | the node, its declared effect tags, that the region is a retry region, and the binding protection | — |
| ↳ `P06EffectRecord`, `region: "cycle"` | as serialized | as above, plus the anchor cycle | — |
| ↳ `P06EffectRecord`, `region: "acyclic"` | as serialized | as above, with no cycle anchor and typically `protection: "none_required"` | — |
| ↳ `protection: "idempotency_key"` | as serialized | the key that satisfied it — protection is binding, so naming the key is the evidence | — |
| ↳ `protection: "compensation_hook"` | as serialized | the hook node that satisfied it | — |
| ↳ `protection: "none_required"` | as serialized | that no obligation arose here, and why (region) — never rendered as "protected" | — |
| `DeterminismWitness` (`kind: "determinism"`) | as serialized | every claim (below); the `claim_class: heuristic` it carries in-band; the caveat when present | does not project |
| ↳ `DeterminismClaim`, `llm_backed: true` | as serialized | the node; the pinned seed and temperature; the divergence-handling echo | — |
| ↳ `DeterminismClaim`, `llm_backed: false` | as serialized | the node; the declared basis (`pure-local-computation`); that no pinning was required | — |
| ↳ `caveat: "provider-seed-reproducibility-not-guaranteed"` | as serialized | rendered **verbatim and adjacent** to the claims it qualifies, never in a footnote a reader can miss — the caveat is the honest-claims boundary of this witness | — |
| ↳ empty `claims` (vacuous pass) | as serialized (`claims: []`) | that no node declared determinism, so nothing was checked — never "all deterministic" | — |

### 4.4 Failure-side variants

| Variant | Native JSON | Human — facts that must appear | SARIF |
|---|---|---|---|
| `Failure` (primary) | as serialized | the severity word as the envelope spells it (`fatal`/`error`/`warning` — §5.1 rule 3); the **claim class**; the `property_condition` id; the owning property id + slug; the location per §4.5 | one `result` (A.4) |
| ↳ `remediation` | as serialized when present | rendered as display-only guidance, clearly separate from the finding, and never parsed by anything | `rule.help` — never `message.text` |
| ↳ `subsumed_by` | as serialized when present | that the finding is owned upstream by the named property, so a reader does not count it twice | `result.properties["gebra/subsumedBy"]` |
| `P04Failure` | as serialized | everything a `Failure` shows, plus the two optional diagnostics when present | as `Failure`; the extras ride `result.properties` |
| ↳ `writers_on_other_paths` | as serialized when non-empty | that writers exist on *other* paths, listed — this is what makes the finding legible rather than baffling | property bag |
| ↳ `downstream_writers` | as serialized when non-empty | that the writers are wired **after** the reader, listed | property bag |
| `CoFailure` | as serialized under the primary | its own severity **and** claim class (never inherited from the primary); its condition id; its location; its `note` when present | one `result` of its own |
| ↳ `CoFailure` with `subsumed_by` | as serialized | as above, plus the upstream owner — shown as context, not as a second charge | property bag |
| `Advisory` | as serialized under the primary | its own `warning` severity and claim class; the property it **belongs to** (which is not the host report's); its condition id and anchor location | one `result` of its own, at `level: "warning"` |
| A failing report with several records | all records under one `failure` | every record rendered; a count that matches; no record dropped, collapsed or re-packaged | one `result` per record |

### 4.5 Location variants

Each row states the anchor facts a rendering must carry. Node ids are rendered byte-for-byte in
the frozen IR-SPEC §5 grammar; the display sentinels `START`/`END` appear exactly where the
envelope carries them (§0.3) and the reserved spellings `__start__`/`__end__` never appear.

| Variant | Human — facts that must appear | SARIF `logicalLocations[0]` |
|---|---|---|
| `NodeLocation` | the node id | `kind: "function"`, FQN `node:<id>` |
| `EdgeLocation` (resolved) | source, target, and the label when the edge is one label expansion | `kind: "edge"`, FQN `edge:<src>-><dst>#<kind>[<label>]` |
| `EdgeLocation` (dangling label — `target` omitted) | source and label, and that the target is **unresolved** — never an empty or invented target | `kind: "edge"`, FQN with the target segment omitted |
| `CycleLocation` | the cycle in its canonical rotation (least id first), rendered as a closed walk | `kind: "cycle"`, FQN from the canonical rotation |
| `SccLocation` | the component's nodes, sorted | `kind: "scc"`, FQN from the sorted members |
| `StateKeyLocation` | the Σ key, and the attributed node when one is named | `kind: "variable"`, FQN `state:<key>` — Appendix C's amended cell (DEC-25, 2026-08-09; formerly `state:<SchemaName>.<key>`, un-fillable in IR 1.0); see reading 2 below and Appendix B OI-8 (closed) |
| `PathLocation` | the path in order, with `START`/`END` shown as sentinels | primary anchor + one `relatedLocations[]` entry per step |
| `P01EdgeLocation` | everything `EdgeLocation` shows, plus `undefined_target` — the string that names no node | as `EdgeLocation`; `undefined_target` rides `result.properties` |
| `P02SccLocation` | the SCC; the single `representative_cycle`; that the cycle list is **not exhaustive** (`exhaustive: false`) so a re-run may surface another; `blanket_only` when present | as `SccLocation`; the flags ride `result.properties` |
| `P02CycleLocation` | the cycle; the counter key; the guard's source and the labels under test (`GuardEdgeLabels`) | as `CycleLocation`; the guard evidence rides `result.properties` |
| `DataflowLocation` | the key; the required reading node; the shortest offending `START→node` path | as `StateKeyLocation`; the path rides `relatedLocations[]` |
| `P06NodeLocation` | the node; its **full declared effect set** as context (not as the obligation source); the anchor cycle when present; `idempotent: "keyless"`, `fanout: "send"` and `dangling_compensation_hook` when present | as `NodeLocation`; the evidence rides `result.properties` |
| `DeterminismNodeLocation` | the node; the declared annotation; `form`, `effects`, `seed`, `temperature` as carried — the IR-decidable evidence, never a prose summary | as `NodeLocation`; the evidence rides `result.properties` |

**Three FQN readings, recorded at CLI-03 rather than left to each producer.** All are editorial
clarifications of what the grammar above can mean given what the envelope carries — no member
changes and no `report_format` bump (§1.6's last row).

1. **The edge FQN's `#<kind>` segment.** An `EdgeLocation` carries no ledger edge kind, only the
   `label` that says whether the anchor is one label-expansion of a conditional edge. The
   segment therefore reports what the anchor carries — `conditional` when a label is present,
   `normal` otherwise — and not a re-derived IR fact; the ledger's third kind (`send`) is not
   distinguishable from an edge anchor at all, so it never appears. A dangling anchor keeps the
   rest of the grammar with its target segment empty (`edge:<src>->#conditional[<label>]`),
   which is what keeps it distinguishable from a resolved one without inventing an endpoint.
2. **The state-key FQN is `state:<key>`, not `state:<SchemaName>.<key>`.** PROPERTY-CATALOG-SPEC
   Appendix C spells the schema-qualified form, but IR 1.0's Σ is a **nameless mapping**
   (IR-SPEC §2.2: `state` is key → type) and the §0.3 envelope carries no schema identity
   either, so no producer can fill `<SchemaName>`. Supplying one from outside the report would
   make `gebraConditionHash/v1` depend on the caller, which A.6 requires it not to. This is the
   same disposition A.5 takes for the physical anchor — state the consequence rather than
   fabricate the value — and it is recorded as Appendix B OI-8. One consequence follows and is
   stated rather than discovered: two P-04 findings that read the same Σ key on different paths
   share an FQN, hence share `gebraConditionHash/v1`; the full evidence stays in the native
   report, where the two are separate records.
3. **A cycle, SCC or path FQN is spaceless.** `cycle:a->b`, `scc:a,b`, `path:START->a->b` — the
   `->` the edge grammar already writes, and a comma for the sorted members of an SCC. An FQN is
   matched and fingerprinted rather than read (A.6), so it is an identifier; the spaced form
   (`a -> b`) is the human surface's, where it is prose.

In code, all three readings are `gebra.report.anchors` (CLI-03).

### 4.6 Copy rules

These bind every surface, and they are lint-enforced (WA-06, TE-15; `tools/honest_claims_lint.py`).

1. **The claim class is always displayed** with any finding or verdict a user sees. A failing
   record carries its own; a passing report's class is read from the property catalog, since a
   pass carries no per-record grade.
2. **Witness-presence wording only.** P-02 reports that every simple cycle carries a *declared
   bound*, that a variant measure is *declared and trusted*, that a certificate is *present and
   re-checkable*. It never says a workflow halts, terminates, or is safe to run.
3. **The subject is the definition, never the agent.** A green run says the workflow
   *definition* passed the catalog. Runtime behavior is not observed by anything here — gebra
   never executes a workflow (D-018).
4. **Banned phrasings are banned in generated copy too**, including strings a renderer
   assembles at run time. The lint reads templates; a template that composes a banned phrase
   from parts is still a violation.
5. **A not-implemented marker is never rendered as a pass**, never counted in a "checks passed"
   tally, and never omitted from a summary that implies completeness.
6. **A HEURISTIC advisory is never presented with the weight of a DEFENSIBLE finding**, whatever
   the exit code — including when strict mode promoted it. The gate changed; the finding did not.
7. **Prose fields are display-only.** `remediation`, `CoFailure.note`, `NotImplementedMarker.detail`
   and `ToolError.detail` are shown to people and parsed by nothing.
8. **A promotion is not a finding, and its condition id is not a grade.** `gate.promotions`
   entries are rendered as what a strict policy selected, beside the policy that selected it;
   a `property_condition` there names the item, and the §0.4 severity registered for that id is
   **not** the promoted record's — the record keeps its own WARNING grade, which is the one a
   rendering shows. P-02's promoted note is the live case: the id it is reported under is
   registered FATAL, and displaying it as a fatal finding would invert §0.2's whole rule. A
   `Promotion` carries no grade of its own precisely so it cannot be read as one, which means a
   rendering that wants the grade joins back to the record: §3.3's identity tuple
   `(property, property_condition, location)` is the join, with `note_kind` standing in for the
   condition on a `witness-note` origin.
9. **A best-effort report is never shown as a plain verdict.** Where `best_effort` names a
   property, its pass or fail is rendered as a diagnostic on topology outside its contract
   (§1.3), never counted toward "checks passed", and never used to soften P-01's own failure.

---

## 5. The human profile

The default, no-flag surface. Framework and degradation are PD-031's ruling (`rich`, with
automatic downgrade on a non-tty, `NO_COLOR` and `TERM=dumb`); this section fixes what the
rendering must *say*.

### 5.1 Obligations

1. **A subject line** identifying what was verified: `subject.source`, `graph_version` (elided
   for length is fine; a digest prefix must be recognizable as a prefix), `ir_version`, and the
   V.S.F.E label when the subject carries one.
2. **One block per finding**, carrying the §4.4 fact set, with the location rendered per §4.5.
   Multiple findings render in one pass — the multi-error obligation of OQ-12-03.
3. **The severity word is the envelope's own** — `fatal`, `error` or `warning`. FATAL is not
   collapsed into "error": SARIF is forced to collapse it (Appendix C), and the human surface
   has no such constraint, so the §0.2 distinction stays visible where it can.
   Witness notes render under a fourth label (`note`), which is not a severity.
4. **Pass reports are shown, not implied.** A property that passed appears with its claim class
   and a witness summary; a reader can see what was checked, not merely that nothing was said.
5. **Markers are shown** as *not checked*, with their status, adjacent to the passes and fails
   they are not.
6. **A summary closes the run**: counts by severity, how many properties produced no verdict,
   the exit code with the reason it took, snapshot eligibility when it is `false`, and the strict
   policy in force with what it promoted.
7. **A non-empty `best_effort` is stated where its reports are**, not only in the summary: each
   named property's block says the run answered it on topology P-01 found ill-formed, so the
   answer is a diagnostic (§1.3, §4.6 rule 9). Silence here is the failure mode the field
   exists to prevent — a P-02 pass on a graph with a dangling target reads as a verdict.
8. **Degradation changes styling only.** No finding is dropped, reordered or reworded going from
   styled to plain output (PD-031).

### 5.2 Illustrative rendering

Non-normative — the fact set above is the contract, this is one legible way to meet it.

```text
gebra verify — travel_booking:build_graph
  ir_version 1.0 · graph_version sha256:5db68464… · strict off

fatal: cycle-without-termination-witness        [P-02 termination-witness · DEFENSIBLE]
  scc              book_flight, confirm, retry_booking
  representative   book_flight → retry_booking → confirm → book_flight   (one of possibly several)
  finding          No simple cycle in this component carries a declared bound.
  remediation      Declare a bounded counter guard with an exit edge, or annotate a loop variant.

warning: deterministic-llm-seed-unpinned        [P-08 determinism-replay · HEURISTIC]
  node             draft_itinerary   (annotation deterministic, form bare-boolean)
  finding          The node declares determinism without a pinned seed.

pass: graph-well-formed                          [P-01 · DEFENSIBLE]
  witness          7 nodes reachable from START · 1 terminal node · no orphans · no unresolved targets

pass: effect-safety                              [P-06 · DEFENSIBLE-A]
  witness          1 cycle · book_flight [billable] in a retry region, protected by idempotency key booking_ref

pass: dataflow-completeness                      [P-04 · DEFENSIBLE-A]
  witness          12 (reader, key) obligations covered

not checked: retry-coherence                     [P-07 · deferred-to-phase-1]
  no verdict was reached — this is not a pass
  … seven further properties are outside the Phase-0 wedge and are listed the same way …

5 properties reported · 8 not checked · 1 fatal · 0 error · 1 warning
exit 1 — a FATAL finding is present. No snapshot is recorded for this run (§0.2).
```

---

## 6. The audit-export profile

### 6.1 What it is

SD-07's per-version audit export is a **run report in the snapshot profile**, written to the path
PD-012 fixes and `gebra.store.SnapshotStore.report_path()` computes:

```
.gebra/reports/<version>.report.json
```

One file per stored version, named by the V.S.F.E label exactly as the snapshot file is.

### 6.2 Deltas from a `verify` run

The document is the same `RunReport` model of §1, with three additional obligations:

1. `subject.input_mode` is `"snapshot"`, so `subject.version` is REQUIRED and equals the version
   label in the file name.
2. `subject.graph_version` equals the stored snapshot's `graph_version`, byte-for-byte. A report
   whose digest disagrees with its snapshot is a corrupt store, not a stale report.
3. `report_format` is the same version as any other run report; there is no separate audit
   schema and no separate version line to keep in step.

Everything else is unchanged, including the absence of any wall-clock field (§1.3): the export is
byte-reproducible from the snapshot and the validator set, and the dating rides the snapshot's
own `extracted_from.extracted_at`.

The snapshot-freshness check — current extraction digest versus the latest snapshot's — is SD-07's
other half and is not a report format question. It reads `subject.graph_version` (or the
snapshot's, equivalently) and produces no run report of its own.

### 6.3 Ratification of SD-07's provisional schema

SD-07's card ships its export "against its own provisional schema, which is reconciled with
REPORT-FORMAT-SPEC when CLI-01 lands". This is that landing:

- **The provisional schema is superseded.** The audit export's schema is §1's `RunReport` in the
  snapshot profile of §6.2. SD-07 defines no export schema of its own and carries no second
  version line.
- **At the time of ratification SD-07 had not yet been built** (card status `todo`), so there was
  no divergence to reconcile — the reconciliation is prospective, and the SD-07 card note was
  edited in the same change to name this document as its schema authority.
- **If SD-07 finds this profile insufficient**, the route is an amendment to this file (with the
  §1.6 bump), never a local export schema: two schemas for one document is the drift this
  ratification exists to prevent.

---

## 7. Conformance obligations

**CLI-03 (rendering engine)** — build the human surface against §4 and §5 and the machine
surfaces against §1.5 and Appendix A. Every variant in §4 renders without error; no rendered
copy contains a banned phrase; the claim class is displayed with every verdict; the SARIF
emission validates against the SARIF 2.1.0 schema. **Landed 2026-08-08** as `gebra.report`:
`render(report, "human" | "json" | "sarif")`, with `gebra.report.human` on PD-031's `rich`,
`gebra.report.native` applying §1.5, `gebra.report.sarif` projecting Appendix A, and
`gebra.report.rules` holding the A.3 rule copy this document handed it. The two FQN readings
of §4.5 and open item OI-8 were recorded in the same change; `tests/report/` renders every §4
variant on all three surfaces against committed goldens, validates every SARIF log against the
schema document, and runs the TE-15 banned-phrase matcher over the rendered text.

**VAL-11 (`verify()` aggregation)** — produce the `RunReport` of §1: all thirteen outcomes in
catalog order, markers where no validator ran, the exit-code derivation of §2 including strict
reach, and the assembly rules of §3 (advisory carriage, anchor projection, carried
`subsumed_by`). Refuse to derive an exit code when a wedge validator is unregistered (§2.4,
`stage: "dispatch"`). **Landed 2026-08-06** as `gebra.verify.verify(ir, policy=None)`, with the
`1.1` amendment of §1.6 and the §3.2 advisory disposition recorded above; `gebra.verify.RunPolicy`
carries the strict request and the caller's subject label, and `gebra.verify.anchor_location` is
§3.2 rule 3.

**SD-07 (audit export + freshness)** — write §6's profile to the PD-012 path; validate every
stored version's export against the same model the verify path emits. **Landed 2026-08-12** as
`gebra.audit`: `export_version` / `export_store` assemble the subject out of the stored
snapshot's own envelope and write `render_native(report, for_file=True)` through the store's
atomic writer, `check_profile` runs *before* every write so a non-conforming document is never
on disk, and `read_export` parses a file back through `RunReport` before checking it against the
store's index. No export schema was defined and no second version line exists (§6.3);
`tests/audit/test_export.py` exports every version of two whole stores and sweeps the written
document's member names for one. The freshness half is `gebra.audit.freshness` plus the
`@pytest.mark.gebra_freshness` pytest gate, and it produces no run report of its own, as §6.2's
last paragraph anticipated.

`check_profile` makes **four** refusals for §6.2's three obligations, and the arithmetic is
worth stating here because it is a gap in §6.2 rather than in the implementation. Obligation 3
is held by construction (`Literal["1.1"]` plus `verify()`'s own stamp), so two of the three are
checkable at all. The fourth refusal is one §6.2 does not ask for: **an exit-2 run is not this
profile.** Every one of §6.2's obligations is about *identity*, and a `dispatch`-stage tool
error carries a full subject — `verify()` builds the subject before dispatching — so an exit-2
run over a stored snapshot satisfies all three while carrying `properties: []`. Writing that to
`reports/<version>.report.json` would put a file that answered nothing where a reader looks for
the audit record of a version: §2.4's "a half-populated list invites reading one anyway", one
level up. It is reachable from SD-07's own `strict` parameter, since §2.4's `1.1` amendment
routes a promotion refusal to `dispatch` precisely so that one policy does not raise where
another answers. A future editor of §6.2 may wish to state the obligation there; until then it
is `gebra.audit.export.check_profile`'s `no-verdict` refusal, which carries `error.detail` into
its message because the reason a stored version could not be audited lives nowhere else.

**Three In-Scope 6 clauses this profile does not carry**, recorded here because a reader
comparing brief D-11 against a written export will find all three. The *timestamp* is refused by
§1.3 and rides the snapshot's `extracted_from.extracted_at`. A *claim class on a passing
property* is refused by §4.2 ("a pass carries no per-record grade") and by the §0.3 envelope,
which carries `claim_class` on findings and the P-08 witness only — so a clean export carries
none and a reader joins to the property catalog. The *classified diff against the previous
version* is refused by §0.4 and by note 5 below ("a structural diff is not a run report … the
S/F/E class of a diff is the SD track's own output shape"), with the content available from
`gebra.lineage`, whose listing carries every version's digest and per-pair bump class and whose
`compare()` returns the diff for any pair. The third has a live tension behind it — PD-006 R4's
*rationale* says audit exports "carry the structural diff" while PD-006's own frozen checklist
block, lifted into `PHASE-0-DOD-CHECKLIST` §S2 and used for G7 acceptance, does not — and it is
recorded as PD-047 rather than left for SD-09 to rediscover. The route stays §6.3's if any of
the three is revisited: an amendment here with the §1.6 bump, never a local schema.

**TE-07 (pytest plugin)** — consume the native run report, not SARIF: strict promotion needs the
lossless envelope, and the plugin's output must tell the same story in the same vocabulary as the
CLI (D-12's shared-formatting requirement).

**CLI-07 (integration suite)** — golden the run reports byte-for-byte; `tool.version` is the only
field a golden normalizes (§1.3).

**CLI-08 (D-12 promotion)** — stamp this document final alongside CLI-SPEC, fix `report_format`,
and close or re-route every open item in Appendix B. **Landed 2026-08-31**, recorded in
[docs/governance/D-12-PROMOTION.md](../governance/D-12-PROMOTION.md): `report_format` is `1.1`,
final; §1.6 gained the two value-rule rows OI-7 commissioned (and says why adding them is not
itself a bump); OI-4 and OI-7 are closed by the promotion, OI-1, OI-2 and OI-5 are re-routed to
Phase-1 cards, and OI-3, OI-6 and OI-8 are reaffirmed as already closed. No producer or consumer
changes: the format the promotion stamps is exactly the one VAL-11 built and CLI-03, SD-07 and
TE-07 read.

**Notes for consumers.** (1) Read `report_format` before anything else (§1.6). (2) Branch on
structured fields only; prose fields are display-only (§4.6 rule 7). (3) A marker is not a
verdict — handle the third member of `PropertyOutcome` explicitly. (4) `gate.counts` and
`gate.promotions` are derived; recomputing them must agree. (5) A structural diff (`gebra diff`)
is **not** a run report: P-12 `evolution-safety` is a two-snapshot property outside the Phase-0
wedge, and the S/F/E class of a diff is the SD track's own output shape.

---

## Appendix A — SARIF 2.1.0 projection

`--format sarif` emits a lossy, findings-only SARIF 2.1.0 projection of the run report, per
PROPERTY-CATALOG-SPEC §0.5 and Appendix C (memo A5, verified there against the OASIS SARIF 2.1.0
spec plus Errata 01, the official JSON schema, and GitHub's code-scanning ingestion docs). The
mapping below restates Appendix C; where the two differ, Appendix C wins and the difference is a
defect to file.

### A.1 Scope and the losses it accepts

The projection is derived from the run report and is **never round-tripped**. Three losses are
structural, not implementation shortcuts:

1. **Pass witnesses do not map** (C.3). SARIF has no witness structure, and `kind: "pass"` results
   require `level: "none"`, which GitHub does not ingest. Witnesses are never smuggled through
   property bags: the envelope owns that schema and remains the source of truth.
2. **FATAL and ERROR collapse** to `level: "error"`; the distinction survives only in
   `result.properties["gebra/severity"]` and in the native report.
3. **Not-implemented markers do not map.** A rule with no result would advertise a check that did
   not run; the eight non-wedge properties are simply absent from a SARIF log, and a consumer
   that needs to know reads the native report.

### A.2 Mapping table

| Run-report concept | SARIF construct | Rule |
|---|---|---|
| Condition ID (§0.4) | `rule.id` = `result.ruleId` | The frozen string verbatim. GitHub's alert dedup keys on `ruleId` being identical across analyses, so the registry freeze is load-bearing. |
| Property id + slug | `rule.name`, `rule.properties.tags` | `rule.name: "P-02 termination-witness"`; tags `["property/<slug>", "claim/<CLASS>"]`. |
| Claim class | `rule.properties["gebra/claimClass"]` | Property bag only — never claim language in `message.text`. The bags and tags carry the **uppercase** display form (`DEFENSIBLE`), a one-way display convention of the projection; the envelope's lowercase form is the parsed one. |
| FATAL | `level: "error"`, `result.properties["gebra/severity"]: "FATAL"`, `rank: 100.0` | The no-snapshot semantics survive in the property bag and in the native report. |
| ERROR | `level: "error"`, `…: "ERROR"`, `rank: 80.0` | |
| WARNING | `level: "warning"`, `…: "WARNING"` | Set per rule via `rule.defaultConfiguration.level` and emitted explicitly on the result too. A promoted WARNING still exports as `warning` (§2.3). |
| Location | `logicalLocations[0]` per §4.5 | FQNs reuse the frozen IR-SPEC §5 node-id grammar byte-for-byte. |
| `graph_version` | `partialFingerprints["gebraGraphVersion/v1"]` and `run.properties["gebra/graphVersion"]` | Provenance, not identity. The V.S.F.E label is a separate field and never a fingerprint; when the subject carries one it rides `run.properties["gebra/version"]`. |
| Stable result identity | `partialFingerprints["gebraConditionHash/v1"]` | `hash(condition ID + canonical logical FQN)` — line-number-independent (A.6). |
| Diff status vs a baseline | `result.baselineState` | `new \| unchanged \| updated \| absent`; only emitted when the run actually has a baseline to compare against. |
| Run identity | `automationDetails.id` | `gebra/verify/<subject-slug>` (A.7). |

### A.3 The `rules[]` catalog

The run's `tool.driver.rules[]` is the §0.4 registry restricted to **emittable** entries — the
thirteen IDs a validator may produce. Non-emittable entries (the RESERVED tier, and any PROPOSED
entry whose dated record has not landed) never appear: a rule for a name no validator can emit
would advertise a check that does not exist.

The catalog is emitted in the table order below (§0.4 table order), whether or not a given rule
produced a result in this run, so that a repository's rule metadata is stable across analyses.

| Condition ID | `rule.name` | `level` | `rank` | `gebra/severity` | `gebra/claimClass` | `shortDescription.text` |
|---|---|---|---|---|---|---|
| `node-unreachable-from-start` | P-01 graph-well-formed | `error` | 100.0 | FATAL | DEFENSIBLE | Node unreachable from START |
| `dead-end-node-not-wired-to-end` | P-01 graph-well-formed | `error` | 100.0 | FATAL | DEFENSIBLE | Dead-end node is not wired to END |
| `path-map-target-undefined` | P-01 graph-well-formed | `error` | 100.0 | FATAL | DEFENSIBLE | Conditional path_map names an undefined target |
| `cycle-without-termination-witness` | P-02 termination-witness | `error` | 100.0 | FATAL | DEFENSIBLE | Simple cycle carries no declared termination witness |
| `counter-guard-without-exit-edge` | P-02 termination-witness | `error` | 100.0 | FATAL | DEFENSIBLE | Bounded-counter guard has no exit edge out of its component |
| `read-key-never-written-on-path` | P-04 dataflow-completeness | `error` | 100.0 | FATAL | DEFENSIBLE-A | State key is read on a path where nothing writes it |
| `unprotected-effect-in-cycle` | P-06 effect-safety | `error` | 80.0 | ERROR | DEFENSIBLE-A | Effect-carrying node in a cycle without binding protection |
| `unprotected-effect-in-retry-region` | P-06 effect-safety | `error` | 80.0 | ERROR | DEFENSIBLE-A | Effect-carrying node in a retry region without binding protection |
| `irreversible-with-keyless-idempotent` | P-06 effect-safety | `error` | 100.0 | FATAL | DEFENSIBLE-A | Irreversible effect declared idempotent without a key |
| `deterministic-llm-seed-unpinned` | P-08 determinism-replay | `warning` | — | WARNING | HEURISTIC | Determinism declared on an LLM-backed node with no pinned seed |
| `deterministic-llm-temperature-unpinned` | P-08 determinism-replay | `warning` | — | WARNING | HEURISTIC | Determinism declared with a seed but no pinned temperature |
| `orphan-node` | P-01 graph-well-formed | `error` | 100.0 | FATAL | DEFENSIBLE | Node participates in no edge |
| `edge-target-undefined` | P-01 graph-well-formed | `error` | 100.0 | FATAL | DEFENSIBLE | Edge endpoint names a node that does not exist |

`rank` is emitted for FATAL (100.0) and ERROR (80.0) only; Appendix C fixes no WARNING rank and
none is invented here.

Each rule also carries, per Appendix C's worked example:

- `fullDescription.text` — the owning property section's statement of the condition, ≤ 1024
  characters;
- `help.text` — the remediation the owning section fixes, plus a pointer to the catalog section,
  ≤ 1024 characters;
- `defaultConfiguration.level` — the `level` column above;
- `properties.tags` — `["property/<slug>", "claim/<CLASS>"]`;
- `properties["problem.severity"]` — `"error"` or `"warning"`, tracking `level`.

Rule copy is repo-authored prose and is held to §4.6: it describes the condition, never a
behavioral claim about a running agent. Writing it is CLI-03's, under these constraints.

### A.4 Result construction

One SARIF `result` per **finding** (§2.1) — the primary `Failure`, each `CoFailure`, and each
`Advisory`. Records are never merged into one result and never dropped:

- `ruleId` — the record's `property_condition`.
- `level`, `rank`, `properties["gebra/severity"]` — from the record's own `severity`, per A.2.
- `properties["gebra/claimClass"]` — the record's own claim class, which for an advisory is the
  advisory's, not the host report's.
- `properties["gebra/property"]` — the **owning** property slug (§3.2), so a consumer can group
  by property without reconstructing carriage.
- `properties["gebra/subsumedBy"]` — present iff the record carries `subsumed_by`.
- `message.text` — a finding-first sentence (GitHub truncates), naming what was found and where.
  It carries no claim language: the claim class lives in the property bag (Appendix C).
- `locations[0].logicalLocations[0]` — per §4.5; `relatedLocations[]` for path steps.
- `partialFingerprints` — A.6.

Result order follows the run report's own traversal: catalog order by property, then each
property's own record order (§1.4 rule 3). SARIF does not attach meaning to result order, and
§3.3 does not either — the rule exists so that two runs over one IR produce byte-identical logs.

**A record with no rule is a refusal, not a fourth loss** (added at CLI-03, when the exporter
was built). A finding whose `property_condition` is registered but **not emittable** has no
entry in the A.3 catalog, so there is no `ruleId` a result could carry — and "never dropped"
above is the rule this would otherwise break silently. `verify()` cannot produce such a report:
§0.4's emission constructors refuse a held name, and the only way one reaches a run report is a
document loaded from another build (PC-6's fixture duty). The exporter therefore **raises**
rather than skipping it. This is a statement about the projection, not a new loss: the record
still stands, in full, in the native report.

### A.5 Locations, and the physical-anchor gap

Appendix C maps every anchor to a `logicalLocation` and adds a `physicalLocation` — the builder
call site — which it flags as **GitHub-mandatory**: GitHub's ingestion page contains zero
occurrences of `logicalLocation`, so logical-only results are spec-valid but invisible there.

**Phase-0 has no source anchors to emit.** IR 1.0 carries no file/line information: IR-SPEC,
INTROSPECTION-SPEC and ANNOTATION-API-SPEC define no source-span field, the extraction envelope
records provenance (`source`, `extractor_version`, sidecar path) but no call site, and the one
place the package reads `co_filename`/`co_firstlineno` is annotation inference, which does not
surface a span into the IR. The projection therefore:

1. emits `logicalLocations` for every result, always;
2. emits `physicalLocation` **only** when the exporter is supplied a call-site resolution from
   outside the IR — there is no such source in Phase-0, so in practice it is absent;
3. states the consequence honestly rather than fabricating a span: a Phase-0 SARIF log uploaded
   to GitHub code scanning may not surface as annotated alerts. The log is spec-valid, and every
   other consumer reads it fully.

Fabricating an artifact URI and line 1 to satisfy the ingestion path is explicitly refused: a
wrong anchor is worse than an absent one, and it would move `primaryLocationLineHash` in ways a
baseline matcher would read as real churn. Closing the gap is a capability question for the
extraction track and a promotion question for D-12 (Appendix B, OI-1).

### A.6 Fingerprints

- `partialFingerprints["gebraConditionHash/v1"]` = a SHA-256 over the condition ID and the
  canonical logical FQN of the result's primary location, joined by a single `\n`, rendered as
  `"<64 lowercase hex>"`. Line-number-independent by construction, so it survives edits that move
  code around.
- `partialFingerprints["gebraGraphVersion/v1"]` = `subject.graph_version` verbatim, including the
  `sha256:` prefix. Provenance for a baseline matcher, never identity.
- `primaryLocationLineHash` is emitted only when a `physicalLocation` was emitted (A.5) — never
  computed from an absent anchor.

### A.7 Run-level fields

- `$schema` `https://json.schemastore.org/sarif-2.1.0.json`; `version` `"2.1.0"`.
- `tool.driver.name` `"gebra"`; `tool.driver.version` = `tool.version` from the run report.
- `automationDetails.id` = `gebra/verify/<subject-slug>`, where `<subject-slug>` is
  `subject.source` lowercased with every run of characters outside `[a-z0-9]` replaced by a single
  `-` and leading/trailing `-` trimmed. Deterministic, so one repository can upload logs for
  several workflows without alert collisions.
- `run.properties["gebra/graphVersion"]`, and `run.properties["gebra/version"]` when the subject
  carries a V.S.F.E label.
- `run.properties["gebra/exitCode"]` — the run's exit code, so a SARIF-only consumer can see the
  gate outcome the projection's `level` collapsing would otherwise hide.
- **A clean run emits `results: []`** in an otherwise complete log, so GitHub closes alerts that
  are fixed. An empty results array is a real statement, not an empty file.
- **A tool-error run (exit 2) MAY emit a log with `results: []`**, and when it does it MUST carry
  `run.properties["gebra/exitCode"]: 2` — an exit-2 log must never be indistinguishable from a
  clean run. Emitting no log at all is equally conforming.

### A.8 Deferred: the `sarif-full` profile

Appendix C mentions an optional `sarif-full` profile carrying cycle fidelity through
`result.graphTraversals` over `run.graphs`. PD-015 explicitly deferred the decision to this
document. **It is deferred again, and not built**: the wedge's cycle locations already carry their
canonical rotation in property bags, no consumer has asked for graph traversals, and a second
profile doubles the exporter's surface for a gain nobody has claimed. Reopening it is an
amendment here (§1.6, MINOR — the profile would be additive), on evidence of a consumer that
needs it.

---

## Appendix B — Open items

| Id | Item | Owner / route |
|---|---|---|
| OI-1 | No source anchors exist in IR 1.0, so SARIF results carry no `physicalLocation` (A.5) and GitHub code-scanning annotations may not surface. | **Re-routed to Phase-1 at the D-12 promotion (CLI-08, 2026-08-31): IR/EX tracks.** The promotion could not close it — the gap needs an extraction-side capability behind an `ir_version` change, which no presentation decision supplies. A.5 declares it. Not a Phase-0 blocker: the log is spec-valid and every other consumer reads it fully. Pairs with CLI-SPEC OI-1, the same gap from the diagnostics side. |
| OI-2 | The `sarif-full` profile is deferred (A.8). | Amendment here on evidence of a consumer that needs it. **Re-routed unchanged at CLI-08 (2026-08-31)**: A.8's argument stands, and reopening it is now a MINOR amendment owned by a Phase-1 card. |
| OI-3 | ~~Fidelity-matrix entries `FM-004` and `FM-007` stay open.~~ **Closed at TE-04, 2026-08-06.** Both were waiting on §3.2 rule 3 and §3.3, and this item read them as unreachable by the harness. That was wrong in one respect, recorded rather than smoothed: the harness's own `PR-3` and `PR-1` obligations *are* projections of the kind those rules govern, so applying rule 3's anchor reduction and §3.3's no-normative-merged-order to the harness's two projection rules closed both rows without a §P-09 merge and without a corpus edit. | Closed. The question this item was right about survives it: which host report a WARNING-grade finding rides is still §P-09's, and `verify()` therefore still assembles no advisories. |
| OI-4 | ~~`report_format` `1.1` is fixed here and stamped final at the D-12 promotion.~~ **Closed at CLI-08, 2026-08-31: stamped.** `report_format` is `1.1`, final; the status block and §1.6 carry the stamp and the post-final route, and [docs/governance/D-12-PROMOTION.md](../governance/D-12-PROMOTION.md) is the record. | Closed. |
| OI-5 | The witness and location unions grow as property sections merge; each new member is a MINOR bump and a new row in §4. | Whichever card merges the section. **Re-routed to Phase-1 at CLI-08 (2026-08-31)**, unchanged: Phase-0 merges no further sections, so nothing is owed here now, and the first Phase-1 card that merges one carries the bump and the §4 row with it. |
| OI-6 | The `--format` default (whether `json` must be spelled explicitly) and the full flag table are CLI-SPEC's. | Closed by CLI-SPEC §4.1 (CLI-02, 2026-08-05): `--format {human,json,sarif}` with `human` as the no-flag default, so `json` is spelled explicitly. |
| OI-7 | ~~§1.6's bump table has no row for "a documented field's *value rule* changes while the model does not" — the shape of the §1.3 `subject.source` amendment above. It was judged "clarified prose" (no bump) on the grounds that nothing has shipped and no producer exists; the next one should not be judged ad hoc.~~ **Closed at CLI-08, 2026-08-31: the rows are added**, exactly as this item routed it. §1.6 now splits the class by direction — a value rule that **widens, or changes what the same value means**, is MINOR (the model parses either way, so the break is a misreading rather than a parse error); one that **narrows or is merely made precise** is none. A value-rule change that also moves exit-code derivation, the finding set or strict reach is MAJOR by the row that already existed. The `subject.source` amendment is recorded as the worked example of the second row, so the judgement that was made ad hoc is now the table's. | Closed. |
| OI-8 | **CLOSED (DEC-25, 2026-08-09; PD-040 Option A ratified).** Appendix C's `StateKeyLocation` row now reads `state:<key>` — the former `<SchemaName>` slot was a pre-freeze placeholder no conforming producer could fill (IR 1.0's `state` is a nameless mapping; no envelope or Subject field carries a Σ identity). The projection's `state:<key>` is the amended cell's own spelling; carrying a Σ identity remains an `ir_version` question. Raised at CLI-03, when the exporter was built. | Appendix C is frozen and wins where the two differ (A.1), so the route is WA-03. **Filed at CLI-03 as PD-040** (the development-process repository's decision log), issue-ready, rather than deferred to CLI-08: the FQN feeds `gebraConditionHash/v1` (A.6), so a later spelling change moves fingerprints that consumers have baselined, and nothing has shipped yet. CLI-08 closes this item on the ruling. **Done at CLI-08, 2026-08-31: reaffirmed closed on DEC-25**, which is the whole of what this item asked the promotion to do — the vault ruling is the authority and the promotion adds nothing to it. Not a Phase-0 blocker: the FQN is deterministic, derived only from the record, and SARIF-valid either way. Pairs with OI-1, which is the same shape of gap on the physical anchor. |
