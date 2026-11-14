"""The run-level report and the ``verify()`` aggregation — ``docs/specs/REPORT-FORMAT-SPEC.md``.

PROPERTY-CATALOG-SPEC §0.3 specifies one property's report and hands everything above it —
"all thirteen ``PropertyReport``s + IR identity + exit-code derivation + serialization
profile" — to ``REPORT-FORMAT-SPEC``. This module is that document as built: §1.2's models,
§2's exit-code derivation, and :func:`verify`, which runs every registered validator over one
IR and returns the :class:`RunReport` the CLI, the pytest plugin and the audit export all read.

**The record is per-property; the gate is per-run.** A validator answers one question and
never sees a flag: §2.4 of the catalog takes no strict parameter, and §0.2 has promotion
change "the gate, never the record" (DEC-11 item 6, in those words). So everything
policy-dependent lives here, in :class:`GateOutcome`, and nothing in ``properties`` moves when
a strict flag does. A promoted record keeps its own ``severity: "warning"`` and its own claim
class where it stands; the only trace of promotion is the exit code, the outcome word and the
:class:`Promotion` list.

**The three codes** (§0.2, derived over a whole run by §2.2): ``0`` when no finding is FATAL
or ERROR and no promotion was selected — ``pass``, or ``pass-with-notes`` when a WARNING-grade
record or note is present; ``1`` when a FATAL or ERROR finding is present, or when strict mode
selected a WARNING-grade record or note; ``2`` when no verdict was reached at all. Exit ``2``
is never a verification result: a tool-error run carries no outcomes, and an exception
escaping a validator is a tool error rather than a failing property (§2.4).

**P-01 gates the contract-weight of the topology validators.** §0.3 defines P-02, P-04 and
P-06 results "only over P-01-clean topology"; where P-01 fails, their reports on that IR are
"best-effort diagnostics, not contract-bearing verdicts". Two things follow, and this module
does both rather than only the first. P-01 runs first, and its FATAL findings alone already
fix the run's gate — exit ``1`` with no snapshot recorded, whatever the others say. And
the run report *says so*: :attr:`RunReport.best_effort` names the three properties whose
outcomes a consumer must read as diagnostics on that run, so the distinction survives into
the artifact instead of living only in the spec.

**What extraction said rides beside the verdict, never inside it.** A run whose IR was
extracted carries the extraction's warnings and disclosures as
:attr:`RunReport.extraction_notes` (§1.2; PROPERTY-CATALOG-SPEC §0.6 item 8, DEC-35 §3.8) —
structured records in emission order that move no exit code, enter no count and promote under
no strict flag. :func:`verify` reads an IR and never sees an extraction, so the caller that
extracted attaches them: :func:`extraction_notes_of` reads an extraction envelope's records and
:func:`with_extraction_notes` returns the report carrying them.

**Hermetic, like the validators it drives.** Nothing here imports langgraph, executes a
workflow node, calls a model or opens a network connection (WA-07): the input is a validated
:class:`~gebra.ir.WorkflowIR`, dispatch calls registered validators that read serialized IR,
and the output is structured values. ``tests/verify/test_run.py`` proves it in a guarded
interpreter over the whole vendored corpus rather than asserting it here. The extraction notes
do not breach it: :func:`extraction_notes_of` reads the records an extraction already made,
through the attributes they declare, and :mod:`gebra.extraction` is never imported here.

Example — the shape a consumer branches on::

    from gebra.verify import RunPolicy, StrictPolicy, verify

    report = verify(ir)                                   # policy-free: strict off
    report.gate.exit_code                                 # 0 | 1 | 2
    report.gate.snapshot_eligible                         # §2.5, FATAL-only suppression
    strict = RunPolicy(strict=StrictPolicy(mode="per-property",
                                           properties=("determinism-replay",)))
    verify(ir, strict).gate.promotions                    # what that policy selected
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Final, Literal, Protocol, TypeAlias, cast

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

import gebra
from gebra.ir import IrVersion, WorkflowIR
from gebra.ir.canonical import CanonicalizationError, graph_version
from gebra.verify.base import (
    ClaimClass,
    ConditionId,
    NodeId,
    PropertySlug,
    ReportModel,
    Severity,
)
from gebra.verify.locations import (
    AnyLocation,
    CycleLocation,
    EdgeLocation,
    Location,
    NodeLocation,
    PathLocation,
    SccLocation,
    StateKeyLocation,
)
from gebra.verify.properties.termination_witness import strict_promotions
from gebra.verify.registry import (
    PROPERTY_SLUGS,
    NotImplementedMarker,
    PropertyRegistryError,
    is_implemented,
    property_entry,
    run_property,
)
from gebra.verify.report import PropertyReport
from gebra.verify.witnesses import Witness, WitnessNote, WitnessNoteKind

__all__ = [
    "IN_PROCESS_SOURCE",
    "PROMOTION_ORIGINS",
    "REPORT_FORMAT",
    "STRICT_ALL",
    "STRICT_OFF",
    "TOPOLOGY_SLUGS",
    "ExtractionNote",
    "ExtractionNoteCode",
    "GateOutcome",
    "Promotion",
    "PromotionOrigin",
    "PropertyOutcome",
    "RunPolicy",
    "RunReport",
    "RunReportModel",
    "SeverityCounts",
    "StrictPolicy",
    "Subject",
    "SubjectRef",
    "Tool",
    "ToolError",
    "anchor_location",
    "extraction_notes_of",
    "verify",
    "with_extraction_notes",
]


#: The ``report_format`` this build produces and reads. ``1.4`` under §1.6's new-optional-member
#: row — the ``0.2.0`` release's one MINOR. DEC-35 §3.3 rules one bump per release and, for G10,
#: names the members it carries: "``1.4``: ``extraction_notes`` and VAL-17's P-04 members —
#: whichever of CLI-12 and VAL-17 lands second appends". VAL-17 landed first and opened it with
#: DEC-37's P-04 member, ``DataflowWitness.payload_readers`` and
#: ``P04Failure.payload_readers``, emitted only when non-empty and never verdict-bearing; CLI-12
#: appended ``RunReport.extraction_notes`` (DEC-35 §3.8), present only when the run extracted
#: and a note was emitted, and bumped nothing. ``1.3`` (VAL-15; DEC-33) added ``WellFormednessWitness.contained_nodes``,
#: ``DataflowWitness.contained_readers`` and ``P04Failure.contained_readers``, with the
#: catalog-driven restatements of ``reachable_from_start`` and the V_top narrowing; ``1.2``
#: (VAL-14; DEC-28) added ``dynamic_dependent`` and ``outside_static_coverage`` and let
#: ``Subject.ir_version`` admit ``"1.1"``; ``1.1`` (VAL-11) added
#: ``Promotion.property_condition`` on a witness-note promotion and ``RunReport.best_effort``;
#: Phase-0 shipped at ``1.1``.
REPORT_FORMAT: Final = "1.4"

#: The topology-consuming wedge properties: §0.3 defines their results **only over P-01-clean
#: topology**, and where P-01 fails their reports are best-effort diagnostics rather than
#: contract-bearing verdicts. Listed in catalog order, as :attr:`RunReport.best_effort` carries
#: them.
TOPOLOGY_SLUGS: Final[tuple[PropertySlug, ...]] = (
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
)

#: Where a promoted record was carried (§2.3's reach table).
PromotionOrigin: TypeAlias = Literal["failure", "co-failure", "advisory", "witness-note"]

#: The four origins, for a consumer that enumerates them.
PROMOTION_ORIGINS: Final[tuple[PromotionOrigin, ...]] = (
    "failure",
    "co-failure",
    "advisory",
    "witness-note",
)


class RunReportModel(ReportModel):
    """Normative base for the run-level models (§1.2; A6 PC-1/PC-3).

    It extends :class:`~gebra.verify.base.ReportModel` rather than restating its config, so
    §1.5's "in code, this is exactly ``gebra.verify.to_data`` / ``gebra.verify.to_json``" is
    true of the wrapper by construction and not by coincidence: the wrapper serializes under
    the same PC-4 profile as the envelope it wraps, and ``model_construct`` is refused here
    for the same reason it is refused there — it would skip the invariants below.
    """


class Tool(RunReportModel):
    """Which build produced this report (§1.3)."""

    name: Literal["gebra"]
    #: The installed ``gebra.__version__``, verbatim. The one field whose value legitimately
    #: differs between two runs over identical input; goldens normalize it (§1.3).
    version: str


class Subject(RunReportModel):
    """What was verified, and how it was obtained (§1.2/§1.3).

    ``source`` is a **label**, not a locator to resolve, and the report never invents one:
    :func:`verify` takes it from its caller (:class:`SubjectRef`) or falls back to the
    deliberately unresolvable :data:`IN_PROCESS_SOURCE`.
    """

    input_mode: Literal["extracted", "ir-document", "snapshot"]
    source: str
    #: The document's own ``ir_version`` stamp, verbatim — ``"1.0"``, or ``"1.1"`` for a
    #: document carrying a ``dynamic`` edge (IR-SPEC §8; DEC-28). It is inside the
    #: ``graph_version`` hash scope (IR-SPEC §6.4), so it is part of the identity reported here,
    #: and it is read off the document rather than re-derived from its constructs: the stamp's
    #: relation to the constructs is the emitter's obligation (minimal stamping, PD-044 D10),
    #: not this report's to police.
    ir_version: IrVersion
    #: ``"sha256:<64 lowercase hex>"`` — the IR-SPEC §6 content digest of the core IR,
    #: byte-for-byte the string a snapshot envelope carries. Provenance and identity for a
    #: report; never a claim about behavior.
    graph_version: str
    #: The V.S.F.E label; REQUIRED iff ``input_mode == "snapshot"``.
    version: str | None = None
    #: Present iff ``input_mode == "extracted"``.
    extractor_version: str | None = None
    #: The sidecar path extraction recorded, when there was one.
    sidecar: str | None = None

    @model_validator(mode="after")
    def _snapshot_carries_its_label(self) -> Subject:
        if (self.input_mode == "snapshot") != (self.version is not None):
            raise ValueError("`version` present iff input_mode == 'snapshot'")
        return self


class StrictPolicy(RunReportModel):
    """The strict-mode request in force for this run (§0.2), recorded as given.

    Recorded rather than summarized: a reader of the report knows which gate produced the
    code, and a promotion list is legible only beside the policy that selected it.
    """

    mode: Literal["off", "all", "per-property"]
    #: Non-empty iff ``mode == "per-property"``. The catalog slugs of §0.2's second form.
    properties: tuple[PropertySlug, ...] = ()

    @model_validator(mode="after")
    def _properties_iff_per_property(self) -> StrictPolicy:
        if (self.mode == "per-property") != bool(self.properties):
            raise ValueError("`properties` non-empty iff mode == 'per-property'")
        return self

    def promotes(self, property_slug: PropertySlug) -> bool:
        """Whether this policy promotes ``property_slug``'s WARNING-grade records (§0.2)."""
        if self.mode == "all":
            return True
        if self.mode == "per-property":
            return property_slug in self.properties
        return False


#: Strict mode off — the default, and what ``verify(ir)`` runs under.
STRICT_OFF: Final = StrictPolicy(mode="off")

#: Bare ``--gebra-strict``: every WARNING in the run is promoted (§0.2).
STRICT_ALL: Final = StrictPolicy(mode="all")


class Promotion(RunReportModel):
    """One WARNING-grade record the strict policy promoted at the gate (§2.3).

    The record it names is unchanged in ``properties``: promotion moves the gate, never the
    record (§0.2). Nothing here carries a severity or a claim class, because the promoted
    record keeps its own where it stands — a promotion is a pointer, not a second finding.

    ``property_condition`` is the identity the promoted item is **reported under**, never a
    grade and never an input to ``gate.counts``. On a finding-origin promotion it is the
    record's own condition ID. On a ``witness-note`` promotion it is the identity the
    property's own spec fixes for the promoted note — for P-02's
    ``scc-covered-only-by-recursion-limit`` that is TERMINATION-WITNESS-SPEC §6.1's reused
    ``cycle-without-termination-witness`` with ``blanket_only: true`` on the location, "no new
    condition ID is introduced". A note kind whose spec fixes no such identity carries none.
    """

    #: The **owning** property of the record (§2.3) — for an advisory, the advisory's own
    #: property, not the host report's.
    property: PropertySlug
    origin: PromotionOrigin
    #: The record's own condition ID for a finding origin; the promoted-item identity, where
    #: one is fixed, for a witness note.
    property_condition: ConditionId | None = None
    #: Present iff ``origin == "witness-note"``.
    note_kind: WitnessNoteKind | None = None
    location: AnyLocation | None = None

    @model_validator(mode="after")
    def _origin_fixes_what_a_promotion_names(self) -> Promotion:
        is_note = self.origin == "witness-note"
        if is_note != (self.note_kind is not None):
            raise ValueError("`note_kind` present iff origin == 'witness-note'")
        if not is_note and self.property_condition is None:
            raise ValueError("a finding-origin promotion names the record's condition ID")
        return self


class SeverityCounts(RunReportModel):
    """Findings by severity (§2.1). Derived; a consumer that recomputes gets the same numbers.

    Findings only, by their own per-record ``severity``. Notes are counted nowhere here: they
    are not findings, they never fail a gate on their own, and a run's FATAL tally is what
    §2.5 reads for snapshot eligibility.
    """

    fatal: int
    error: int
    warning: int

    @property
    def blocking(self) -> int:
        """FATAL + ERROR — the count §2.2's first verdict branch reads."""
        return self.fatal + self.error


class ToolError(RunReportModel):
    """Why no verdict was reached (§2.4). ``detail`` is display-only prose; never parsed."""

    stage: Literal["input", "extraction", "ir-validation", "dispatch"]
    detail: str


class GateOutcome(RunReportModel):
    """What CI does about the run — the gate, derived from ``properties`` and the policy.

    ``outcome`` is a display-and-branching convenience and ``exit_code`` is the contract; §2.2
    says the two never disagree, and the invariant below is that sentence enforced rather than
    restated.
    """

    exit_code: Literal[0, 1, 2]
    outcome: Literal["pass", "pass-with-notes", "fail", "tool-error"]
    counts: SeverityCounts
    strict: StrictPolicy
    promotions: tuple[Promotion, ...] = ()
    snapshot_eligible: bool

    @model_validator(mode="after")
    def _the_word_and_the_code_agree(self) -> GateOutcome:
        expected: Mapping[str, int] = {
            "pass": 0,
            "pass-with-notes": 0,
            "fail": 1,
            "tool-error": 2,
        }
        if expected[self.outcome] != self.exit_code:
            raise ValueError(
                f"outcome {self.outcome!r} and exit code {self.exit_code} disagree (§2.2)"
            )
        if self.outcome == "tool-error" and self.promotions:
            raise ValueError("a tool-error run reached no verdict and promoted nothing")
        return self


#: One property's answer: a verdict, or the structured statement that no verdict was reached.
#: Resolution is left to right, and deterministic: :class:`NotImplementedMarker` requires
#: ``kind``, which :class:`~gebra.verify.report.PropertyReport` forbids. This is exactly what
#: :func:`gebra.verify.run_property` returns.
PropertyOutcome: TypeAlias = Annotated[
    NotImplementedMarker | PropertyReport, Field(union_mode="left_to_right")
]


# ── §1.2: the extraction notes (PROPERTY-CATALOG-SPEC §0.6 item 8; DEC-35 §3.8) ───────────

#: The closed vocabulary an :class:`ExtractionNote` carries (DEC-35 §3.8): the ten
#: extraction-warning codes of INTROSPECTION-SPEC §8 and ANNOTATION-API-SPEC §4, then every
#: disclosure code an R-06 record admits as a note — §8's disclosures "reach the run report
#: through the extraction-notes member". DEC-36 admitted the first two, which this build's
#: extraction emits; DEC-40 admitted ``barrier-read-per-edge``, which no extraction in this
#: release emits (its emitter is IR 1.2's) and which is spelled here already, so the build that
#: first emits it moves no report member. Spelled rather than imported, because
#: :mod:`gebra.extraction` imports the substrate and nothing on the verify path may (WA-07);
#: ``tests/verify/test_extraction_notes.py`` holds this list to the extractor's warning
#: vocabulary and to §8's disclosure table.
ExtractionNoteCode: TypeAlias = Literal[
    # INTROSPECTION-SPEC §8 and ANNOTATION-API-SPEC §4 — the one warning taxonomy
    "contract-inferred",
    "contract-defaulted",
    "opaque-lambda",
    "builder-compiled-divergence",
    "compiled-only-extraction",
    "barrier-flattened",
    "unsupported-construct",
    "annotation-conflict",
    "annotation-unknown-node",
    "annotation-invalid",
    # INTROSPECTION-SPEC §8 "Extraction disclosures" — DEC-36's two, then DEC-40's
    "subgraph-read-as-one-node",
    "recursion-limit-bound-without-justification",
    "barrier-read-per-edge",
]

#: The members of :data:`ExtractionNoteCode` that are disclosures rather than warnings. A
#: disclosure is rendered under its own label, never a warning's (INTROSPECTION-SPEC §8).
_DISCLOSURE_CODES: Final[frozenset[str]] = frozenset(
    {
        "subgraph-read-as-one-node",
        "recursion-limit-bound-without-justification",
        "barrier-read-per-edge",
    }
)

#: How deep a note's ``detail`` may nest — the bound extraction holds the same records to, so a
#: self-referential mapping is a message rather than a :class:`RecursionError`.
_MAX_DETAIL_DEPTH: Final = 20

#: ``type``'s own ``__name__`` descriptor: a class's name read through it runs nothing of the
#: class's metaclass, where ``cls.__name__`` would go through the metaclass's attribute access.
_TYPE_NAME: Final[Any] = type.__dict__["__name__"]


def _exact_text(value: object) -> object:
    """``value`` as an exact ``str`` when it is any ``str``; anything else unchanged.

    The test is ``issubclass(type(value), str)`` and the conversion the unbound ``str.__str__``:
    a subclass's own ``__str__``, ``__format__``, ``__hash__`` or attribute access never runs
    (INTROSPECTION-SPEC §1 rule 1, the read DEC-38 rules for labels). A value that is not a
    string is left for the field's own strict validation to refuse.
    """
    if issubclass(type(value), str):
        return str.__str__(cast(str, value))
    return value


def _json_detail(value: object, *, path: str, depth: int) -> Any:
    """``value`` as JSON data of exact built-in types, every sequence a tuple; else raise.

    The run-report half of the discipline extraction holds a record's ``detail`` to
    (``gebra.extraction.warnings._reportable``, which this module cannot import): the same
    types admitted and the same refusals, sequences given one representation so that a note
    loaded back from JSON equals the note that was written — and one rule more. A record's
    values can be derived from the workflow (a node name a builder was given), so each is read
    by its exact type through unbound accessors — ``issubclass(type(value), …)``, then
    ``str.__str__``, ``int.__index__``, ``float.__float__``, ``tuple.__iter__``,
    ``list.__iter__`` and ``dict.items`` — and converted to the exact built-in before anything
    hashes, compares, inserts or renders it. No method of a subclass runs here, and a note
    carries exact built-ins only, so a surface that formats one runs no user code either.
    """
    if depth > _MAX_DETAIL_DEPTH:
        raise ValueError(
            f"{path} nests deeper than {_MAX_DETAIL_DEPTH} levels; a note's detail is a record "
            "of what extraction found, not a data structure"
        )
    kind = type(value)
    if value is None or kind is bool:  # `bool` admits no subclass
        return value
    if issubclass(kind, str):
        return str.__str__(cast(str, value))
    if issubclass(kind, int):
        return int.__index__(cast(int, value))
    if issubclass(kind, float):
        number = float.__float__(cast(float, value))
        if not math.isfinite(number):
            raise ValueError(f"{path} is {number!r}; JSON has no form for it")
        return number
    if issubclass(kind, (tuple, list)):
        items: Iterator[object] = (
            tuple.__iter__(cast(tuple[object, ...], value))
            if issubclass(kind, tuple)
            else list.__iter__(cast(list[object], value))
        )
        return tuple(
            _json_detail(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(items)
        )
    if issubclass(kind, dict):
        normalized: dict[str, Any] = {}
        for key, item in dict.items(cast(dict[object, object], value)):
            if not issubclass(type(key), str):
                # ValueError, not TypeError: pydantic turns a ValueError raised in a validator
                # into a ValidationError and lets a TypeError escape as itself.
                raise ValueError(  # noqa: TRY004
                    f"{path} has a key of type {_TYPE_NAME.__get__(type(key))}; JSON keys are "
                    "strings"
                )
            exact = str.__str__(cast(str, key))
            normalized[exact] = _json_detail(item, path=f"{path}[{exact!r}]", depth=depth + 1)
        return normalized
    raise ValueError(
        f"{path} holds a {_TYPE_NAME.__get__(kind)}, which is not JSON data; a note carries what "
        "extraction found, in the form the report is written in"
    )


class ExtractionNote(RunReportModel):
    """One extraction note: a warning or an admitted disclosure, carried into the run report.

    PROPERTY-CATALOG-SPEC §0.6 item 8 (DEC-35 §3.8): the structured record extraction emitted —
    an INTROSPECTION-SPEC §8 / ANNOTATION-API-SPEC §4 warning, or an INTROSPECTION-SPEC §8
    disclosure an R-06 record admits as a note (DEC-36, DEC-40) — with the fields both kinds
    carry. A note is **never a finding**: it moves no exit code, enters no count, promotes under
    no strict flag and is never mixed into a findings list (REPORT-FORMAT-SPEC §2.1, §4.6).

    Every value a note holds is an exact built-in — the strings, the slots and everything in
    ``detail`` are converted on the way in, by type and through unbound accessors — so rendering
    a note runs no code of the workflow's. ``detail`` is a JSON object, a ``dict`` as the
    record's own is: a frozen model does not freeze it, and a note — with a run report that
    carries one — is not hashable, unlike the per-property envelope models (PC-1). Nothing in
    the library hashes a run report or alters a note.

    Attributes:
        code: The record's code, verbatim — a warning code or an admitted disclosure code.
        message: The record's own words. **Display-only** (§4.6 rule 7): every fact a consumer
            branches on is in the fields beside it.
        node: The node id the record names, in the escaped IR-SPEC §5 form, or ``None`` for a
            record about the graph or a file.
        slots: The ANNOTATION-API-SPEC §1 slot names the record names, as it named them — empty
            for a disclosure, which names none, and omitted from the serialized note when
            empty. They were checked against the slot vocabulary where the record was made.
        detail: The rest of what the record carries, as JSON data — the row's "what it carries"
            column (INTROSPECTION-SPEC §8).
    """

    code: ExtractionNoteCode
    message: str = Field(min_length=1)
    node: NodeId | None = None
    slots: tuple[str, ...] = ()
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message", "node", mode="before")
    @classmethod
    def _text_is_exact(cls, value: object) -> object:
        """A string field holds an exact ``str``, whatever the record handed in."""
        return _exact_text(value)

    @field_validator("slots", mode="before")
    @classmethod
    def _slots_are_exact(cls, slots: object) -> object:
        """Each slot an exact ``str``, read through the unbound sequence accessor."""
        kind = type(slots)
        if not issubclass(kind, (tuple, list)):
            return slots  # not a sequence: strict validation reports it
        items: Iterator[object] = (
            tuple.__iter__(cast(tuple[object, ...], slots))
            if issubclass(kind, tuple)
            else list.__iter__(cast(list[object], slots))
        )
        return tuple(_exact_text(slot) for slot in items)

    @field_validator("detail", mode="before")
    @classmethod
    def _detail_is_json_data(cls, detail: object) -> object:
        """Refuse what JSON could not carry; convert the rest to exact built-ins."""
        if not issubclass(type(detail), dict):
            return detail  # not a mapping: strict validation reports it
        return _json_detail(detail, path="detail", depth=-1)

    @model_serializer(mode="wrap")
    def _omit_empty_slots(self, handler: SerializerFunctionWrapHandler) -> Any:
        """``slots`` is optional on the wire (§0.6 item 8): an empty tuple is omitted."""
        data = handler(self)
        if not self.slots and isinstance(data, dict):
            data.pop("slots", None)
        return data

    @property
    def is_disclosure(self) -> bool:
        """Whether the record is a disclosure rather than a warning (INTROSPECTION-SPEC §8).

        Read off the code, because the two vocabularies are disjoint by construction: a
        disclosure is "not a member" of the warning table, and its renderers label it as itself,
        "never a warning's prefix".
        """
        return self.code in _DISCLOSURE_CODES


class RunReport(RunReportModel):
    """The run-level wrapper (§1.2; PROPERTY-CATALOG-SPEC §0.3's scope boundary)."""

    report_format: Literal["1.4"]
    tool: Tool
    #: Absent only when a tool error preceded IR identity.
    subject: Subject | None = None
    #: What extraction said about how the subject's IR was obtained — its warnings, then the
    #: disclosures an R-06 record admits as notes (INTROSPECTION-SPEC §8), in emission order
    #: (PROPERTY-CATALOG-SPEC §0.6 item 8;
    #: DEC-35 §3.8). Present only when the run extracted and a note was emitted, and omitted
    #: from the serialized report otherwise; never findings. :func:`verify` reads an IR and never
    #: sees an extraction, so the caller that extracted attaches them
    #: (:func:`with_extraction_notes`).
    extraction_notes: tuple[ExtractionNote, ...] = ()
    properties: tuple[PropertyOutcome, ...] = ()
    #: The properties whose outcomes in this run are **best-effort diagnostics**, not
    #: contract-bearing verdicts — §0.3's P-01-clean precondition, reported rather than left
    #: to the reader. Non-empty exactly when P-01 produced a FATAL finding, in which case it
    #: is :data:`TOPOLOGY_SLUGS`; empty on every P-01-clean run and on a tool-error run.
    #:
    #: §0.3 says "when P-01 fails"; this is keyed on a FATAL P-01 finding, and the two
    #: coincide because every P-01 condition in the §0.4 registry is FATAL. That equivalence
    #: is read off the registry, not stated by §0.3, so a future P-01 condition at another
    #: grade is a question for this field rather than a silent change of meaning.
    best_effort: tuple[PropertySlug, ...] = ()
    gate: GateOutcome
    error: ToolError | None = None

    @model_validator(mode="after")
    def _tool_error_is_the_whole_run(self) -> RunReport:
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

    @model_validator(mode="after")
    def _notes_come_from_an_extraction(self) -> RunReport:
        """§0.6 item 8's "present only when the run extracted", enforced.

        A subject obtained any other way — an IR document, a stored snapshot — was not
        extracted by this run, so it carries no note. A report with no subject at all is a tool
        error that preceded IR identity; one that follows a successful extraction (an IR with no
        canonical form, say) may carry the notes that extraction emitted, since the run did
        extract and the notes are the most diagnostic thing it has.
        """
        subject = self.subject
        if self.extraction_notes and subject is not None and subject.input_mode != "extracted":
            raise ValueError(
                f"`extraction_notes` is present only when the run extracted; this subject's "
                f"input_mode is {subject.input_mode!r} (PROPERTY-CATALOG-SPEC §0.6 item 8)"
            )
        return self

    @model_serializer(mode="wrap")
    def _omit_empty_notes(self, handler: SerializerFunctionWrapHandler) -> Any:
        """``extraction_notes`` is omitted when empty (§0.6 item 8: "omitted otherwise").

        The one member the PC-4 profile's ``exclude_none`` cannot drop, because its empty value
        is ``()`` rather than ``None``; omission round-trips all the same, since a document
        without the key validates back to ``()``.
        """
        data = handler(self)
        if not self.extraction_notes and isinstance(data, dict):
            data.pop("extraction_notes", None)
        return data

    def outcome_for(self, property_slug: PropertySlug) -> PropertyOutcome:
        """This run's answer for ``property_slug`` — a verdict or a marker, never a lookup miss.

        Raises:
            KeyError: on a tool-error run, which reached no verdict for any property.
        """
        for outcome in self.properties:
            if outcome.property == property_slug:
                return outcome
        raise KeyError(f"this run carries no outcome for {property_slug!r}")


# ── The caller's side: what a run is asked for ───────────────────────────────────────────

#: The ``subject.source`` label a caller that named no reference gets. Deliberately not a
#: resolvable reference and deliberately not shaped like one — §1.3 has the report never
#: inventing a target, and this is the honest statement that none was named. Every real
#: caller (the CLI, the pytest plugin, an audit export) supplies its own.
IN_PROCESS_SOURCE: Final = "<in-process ir>"


@dataclass(frozen=True)
class SubjectRef:
    """The provenance of the IR under verification, as its caller knows it (§1.3).

    :func:`verify` composes this with the IR's own identity — ``ir_version`` and the IR-SPEC
    §6 ``graph_version`` digest, which it computes rather than accepts — into the
    :class:`Subject` the report carries. Splitting it this way is what keeps the two honest:
    a caller can label a run, and cannot mislabel what was actually digested.

    Attributes:
        source: The label §1.3 fixes per input mode — the invocation's own target reference
            for ``extracted``, the IR document path for ``ir-document``, the stored
            snapshot's ``extracted_from.source`` for ``snapshot``.
        input_mode: How the IR was obtained.
        version: The V.S.F.E label; required iff ``input_mode == "snapshot"``.
        extractor_version: Present iff ``input_mode == "extracted"``.
        sidecar: The sidecar path extraction recorded, when there was one.
    """

    source: str
    input_mode: Literal["extracted", "ir-document", "snapshot"] = "ir-document"
    version: str | None = None
    extractor_version: str | None = None
    sidecar: str | None = None


@dataclass(frozen=True)
class RunPolicy:
    """What a run is asked to do that the IR does not decide.

    Deliberately two fields and no more. Strict mode is the one policy §0.2 gives the gate;
    the subject reference is the one fact about a run that the IR cannot carry (§1.3: the
    report never invents a label). Everything else about a run — which validators exist, what
    they find, what the exit code is — is derived, and a knob for it would be a second place
    for the derivation to drift.

    Attributes:
        strict: The §0.2 strict-mode request, recorded verbatim in ``gate.strict``.
        subject: The caller's provenance for the IR, or ``None`` for an unnamed in-process
            run (:data:`IN_PROCESS_SOURCE`).
    """

    strict: StrictPolicy = field(default=STRICT_OFF)
    subject: SubjectRef | None = None


# ── §3.2 rule 3: the anchor projection ───────────────────────────────────────────────────

#: The six §0.3 structural anchors, by discriminator.
_ANCHORS: Final[Mapping[str, type[Location]]] = {
    "node": NodeLocation,
    "edge": EdgeLocation,
    "cycle": CycleLocation,
    "scc": SccLocation,
    "state-key": StateKeyLocation,
    "path": PathLocation,
}


def anchor_location(location: AnyLocation) -> Location:
    """Reduce ``location`` to its §0.3 anchor variant — §3.2 rule 3, as a function.

    When a finding is projected onto **another** property's report, its location keeps the
    anchor (the discriminator plus the anchor's own fields) and drops the concrete subtype's
    evidence members: the full evidence stays where the full record is, which is the
    ``mixed/03`` precedent (P-08 advisories carry a bare ``NodeLocation`` while P-08's own
    report anchors on ``DeterminismNodeLocation``). An anchor projects to itself.

    This is the primitive §3.2 rule 3 names; :func:`verify` assembles no cross-property
    advisories of its own (see the module docstring of the spec §3.2 amendment), so an
    assembler that does — a renderer merging a view, a future host-property rule — has one
    implementation of the rule rather than one each.
    """
    anchor = _ANCHORS[location.kind]
    return anchor(**{name: getattr(location, name) for name in anchor.model_fields})


# ── §2.1: the finding set and the note set ───────────────────────────────────────────────


@dataclass(frozen=True)
class _Finding:
    """One emitted record carrying a ``severity`` (§2.1), with the property that owns it."""

    owner: PropertySlug
    origin: Literal["failure", "co-failure", "advisory"]
    severity: Severity
    claim_class: ClaimClass
    property_condition: ConditionId
    location: AnyLocation


def _findings(report: PropertyReport) -> Iterator[_Finding]:
    """Every finding of ``report`` — the primary, its co-failures and its advisories (§2.1).

    The owner is the record's own property wherever the record carries one: §2.3's advisory
    row is the one that is easy to get wrong, because an advisory riding a host report is
    still its own property's finding.
    """
    failure = report.failure
    if failure is None:
        return
    yield _Finding(
        owner=report.property,
        origin="failure",
        severity=failure.severity,
        claim_class=failure.claim_class,
        property_condition=failure.property_condition,
        location=failure.location,
    )
    for co_failure in failure.co_failures or ():
        yield _Finding(
            owner=co_failure.property,
            origin="co-failure",
            severity=co_failure.severity,
            claim_class=co_failure.claim_class,
            property_condition=co_failure.property_condition,
            location=co_failure.location,
        )
    for advisory in failure.advisories or ():
        yield _Finding(
            owner=advisory.property,
            origin="advisory",
            severity=advisory.severity,
            claim_class=advisory.claim_class,
            property_condition=advisory.property_condition,
            location=advisory.location,
        )


def _witness_notes(witness: Witness | None) -> tuple[WitnessNote, ...]:
    """The structured notes a passing report's witness carries, if its kind carries any.

    Asked of the model rather than of a hard-coded witness class, so a witness kind that
    grows notes is read here without an edit. ``tests/verify/test_run.py`` pins which kinds
    carry the field today, so the generality cannot quietly become a guess.
    """
    if witness is None or "notes" not in type(witness).model_fields:
        return ()
    notes: tuple[WitnessNote, ...] = getattr(witness, "notes", ())
    return notes


def _notes(report: PropertyReport) -> Iterator[WitnessNote]:
    """Every structured note of ``report``, on either result path (§2.1, DEC-23 carriage).

    Notes ride a passing report's witness and — unconditionally, so a failing property never
    silently drops one — ``Failure.notes`` and ``CoFailure.notes`` on the fail path.
    """
    yield from _witness_notes(report.witness)
    failure = report.failure
    if failure is None:
        return
    yield from failure.notes or ()
    for co_failure in failure.co_failures or ():
        yield from co_failure.notes or ()


def _counts(reports: tuple[PropertyReport, ...]) -> SeverityCounts:
    """``gate.counts`` — findings only, by their own per-record severity (§2.1)."""
    tally = {"fatal": 0, "error": 0, "warning": 0}
    for report in reports:
        for finding in _findings(report):
            tally[finding.severity] += 1
    return SeverityCounts(**tally)


# ── §2.3: what a strict policy selects ───────────────────────────────────────────────────


def _note_promotions(report: PropertyReport) -> Iterator[Promotion]:
    """The witness-note promotions of one report, with each property's own identity rule.

    P-02 is the only property with a WARNING-grade note today, and the identity its promoted
    item is reported under is TERMINATION-WITNESS-SPEC §6.1's, which
    :func:`~gebra.verify.properties.termination_witness.strict_promotions` owns — including
    its fail-closed arms (a WARNING-grade kind with no §6.1 row raises rather than being
    dropped; the ID is re-resolved through the §0.4 emission gate). Calling it here rather
    than re-deriving the mapping is what keeps one rule in one place.

    Any other property's WARNING-grade note promotes with no ``property_condition``: §0.2's
    reach is about severity, so the note is selected either way, and inventing an identity
    for it would be exactly the registry improvisation §0.4 closes.
    """
    if report.property == "termination-witness":
        for promotion in strict_promotions(report):
            yield Promotion(
                property=report.property,
                origin="witness-note",
                property_condition=promotion.property_condition,
                note_kind=promotion.note_kind,
                location=promotion.location,
            )
        return
    for note in _notes(report):
        if note.severity != "warning":
            continue
        for location in note.locations or (None,):
            yield Promotion(
                property=report.property,
                origin="witness-note",
                note_kind=note.kind,
                location=location,
            )


def _promotions(reports: tuple[PropertyReport, ...], strict: StrictPolicy) -> tuple[Promotion, ...]:
    """What ``strict`` promoted, in report order then record order (§2.3).

    Reach is §2.3's table: a WARNING ``Failure``, a WARNING ``CoFailure``, an ``Advisory``
    (always WARNING) and a WARNING-grade ``WitnessNote``. The policy matches on the **owning**
    property of the record, which for an advisory is the advisory's own — a strict flag naming
    P-08 promotes a P-08 advisory riding a P-09 report, because the advisory is P-08's finding
    wherever it is carried.
    """
    promotions: list[Promotion] = []
    for report in reports:
        for finding in _findings(report):
            if finding.severity != "warning" or not strict.promotes(finding.owner):
                continue
            promotions.append(
                Promotion(
                    property=finding.owner,
                    origin=finding.origin,
                    property_condition=finding.property_condition,
                    location=finding.location,
                )
            )
        if strict.promotes(report.property):
            promotions.extend(_note_promotions(report))
    return tuple(promotions)


# ── §2.2/§2.5: the derivation ────────────────────────────────────────────────────────────


def _gate(reports: tuple[PropertyReport, ...], strict: StrictPolicy) -> GateOutcome:
    """§2.2's derivation over a verdict run, with §2.5's eligibility rule beside it."""
    counts = _counts(reports)
    promotions = _promotions(reports, strict)
    has_warning_grade = counts.warning > 0 or any(
        note.severity == "warning" for report in reports for note in _notes(report)
    )
    exit_code: Literal[0, 1]
    outcome: Literal["pass", "pass-with-notes", "fail"]
    if counts.blocking or promotions:
        exit_code, outcome = 1, "fail"
    elif has_warning_grade:
        exit_code, outcome = 0, "pass-with-notes"
    else:
        exit_code, outcome = 0, "pass"
    return GateOutcome(
        exit_code=exit_code,
        outcome=outcome,
        counts=counts,
        strict=strict,
        promotions=promotions,
        snapshot_eligible=counts.fatal == 0,
    )


def _tool_error_report(
    stage: Literal["input", "extraction", "ir-validation", "dispatch"],
    detail: str,
    *,
    subject: Subject | None,
    strict: StrictPolicy,
) -> RunReport:
    """Exit ``2``: no verdict was reached, and the run says where it stopped (§2.4).

    Partial outcomes are deliberately not carried — a half-populated list invites reading one
    anyway — and the counts are zero because nothing was counted, not because nothing was
    found.
    """
    return RunReport(
        report_format=REPORT_FORMAT,
        tool=_tool(),
        subject=subject,
        properties=(),
        gate=GateOutcome(
            exit_code=2,
            outcome="tool-error",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=strict,
            promotions=(),
            snapshot_eligible=False,
        ),
        error=ToolError(stage=stage, detail=detail),
    )


def _tool() -> Tool:
    """The installed build, read at call time so a report never pins a stale version."""
    return Tool(name="gebra", version=gebra.__version__)


def _subject(ir: WorkflowIR, reference: SubjectRef | None) -> Subject:
    """The §1.2 subject: the caller's label plus the IR's own identity.

    Both admitted ``ir_version`` stamps are verified. ``"1.1"`` — the ``dynamic`` edge kind
    (ratified — DEC-28, 2026-08-09) — is read by every wedge validator under §0.3's one
    convention (the shared model of :mod:`gebra.verify.graph` inserts no member for such an
    edge and records its source), so nothing here keys on the stamp: the document's declaration
    is carried into the report as identity, and what the validators dispatch on is the
    construct, which is also what :mod:`gebra.snapshot` and :mod:`gebra.audit` key their own
    declines on — one predicate, not two.

    Keying on the construct does not mean the stamp goes unchecked — it means it is checked
    once, earlier, and never here. §2.5 note 7 floors ``ir_version`` at the lowest minor a
    document's constructs require (ratified — DEC-34, 2026-09-06, resolving the PD-055 spec
    defect this docstring used to disclose as interim), so an under-stamped document — ``"1.0"``
    carrying a ``dynamic`` edge — never reaches :func:`verify`: it is a ``ValidationError`` at
    :class:`~gebra.ir.WorkflowIR`, which the CLI reports as ``stage: ir-validation``. What
    arrives here is therefore stamped at or above its floor, and the stamp is carried into the
    report as the document's own declaration, never re-derived from the constructs.

    Raises:
        CanonicalizationError: if the IR has no digest, which :func:`verify` turns into a
            tool error rather than a verdict.
        pydantic.ValidationError: if the caller's reference breaks §1.2's own invariant
            (a snapshot without its V.S.F.E label). A mislabelled run is the caller's bug,
            not a verification result, so it is raised rather than swallowed.
    """
    reference = reference or SubjectRef(source=IN_PROCESS_SOURCE)
    return Subject(
        input_mode=reference.input_mode,
        source=reference.source,
        ir_version=ir.ir_version,
        graph_version=graph_version(ir),
        version=reference.version,
        extractor_version=reference.extractor_version,
        sidecar=reference.sidecar,
    )


def _gated_order() -> tuple[PropertySlug, ...]:
    """Catalog order, with P-01 first — §0.3's P-01-clean precondition, as an order.

    P-01 heads the catalog anyway, so this is a statement rather than a rearrangement: it
    says the order is a decision, and ``tests/verify/test_run.py`` holds it to it should the
    catalog ever be read in another order.
    """
    first: PropertySlug = "graph-well-formed"
    return (first, *(slug for slug in PROPERTY_SLUGS if slug != first))


def _is_fatal(outcome: PropertyOutcome) -> bool:
    """Whether ``outcome`` is a report carrying a FATAL finding."""
    return isinstance(outcome, PropertyReport) and any(
        finding.severity == "fatal" for finding in _findings(outcome)
    )


def verify(ir: WorkflowIR, policy: RunPolicy | None = None) -> RunReport:
    """Run the registered validators over ``ir`` and derive the run's gate.

    The whole of ``REPORT-FORMAT-SPEC`` §1–§3 in one call: all thirteen catalog properties
    answered in catalog order (a marker where no validator is registered, never a silent
    pass), the §2.2 exit-code derivation with §2.3's strict reach and §2.5's snapshot rule,
    and §0.3's P-01-clean precondition reported in ``best_effort``.

    Order is P-01-gated: P-01 runs first, and where it finds a FATAL the run's gate is already
    fixed — exit ``1``, no snapshot — whatever the others say. Their reports are still
    produced and still carried, because §1.4 wants an outcome per slug and a diagnostic on
    ill-formed topology is worth reading; ``best_effort`` is what stops one being read as a
    contract-bearing verdict.

    Four things become a tool error rather than a verdict (§2.4), because exit ``2`` means
    "no verdict was reached" and each of them means exactly that: an IR with no computable
    digest (``ir-validation``); a shipped property — a row in either shipped scope,
    ``phase-0-wedge`` or ``catalog`` — with no registered validator, since a run that silently
    checked four of the five would be a weakened gate wearing a pass (``dispatch``; §1.4
    rule 2, read over both shipped scopes by DEC-35 §3.1); an exception
    escaping a validator, or a validator answering for the wrong
    property — a crash is not a finding (``dispatch``); and a gate that could not be derived
    from the outcomes, which is what a property's own promotion refusal surfaces as
    (``dispatch``). Between them they make this function **total**: it returns a report or it
    does not return, and a caller never has to handle both.

    An ir 1.1 document — one carrying a ``dynamic`` edge (DEC-28) — is **not** among them: the
    wedge five read it under the ruled semantics (PROPERTY-CATALOG-SPEC §0.3; P-01 §1.4; P-02
    §2.4; P-04 §4.4; P-06 §6.4), so it reaches a verdict like any other, with
    ``subject.ir_version`` carrying its stamp.

    Args:
        ir: A validated workflow IR at ``ir_version`` ``"1.0"`` or ``"1.1"``. Each validator
            reads only the fields its own §P-nn.3 I/O contract lists.
        policy: The §0.2 strict-mode request and the caller's subject label. ``None`` is
            strict off over an unnamed in-process IR.

    Returns:
        The :class:`RunReport` of §1 — the one artifact the human rendering, the native JSON
        and the SARIF projection are three views of. It carries no extraction notes: this
        function never sees an extraction, and a caller that extracted the IR attaches them
        with :func:`with_extraction_notes`.
    """
    policy = policy if policy is not None else RunPolicy()
    strict = policy.strict
    try:
        subject = _subject(ir, policy.subject)
    except CanonicalizationError as error:
        return _tool_error_report(
            "ir-validation",
            f"the IR has no canonical form, so it has no identity to report against: {error}",
            subject=None,
            strict=strict,
        )
    # Read off the table when called, so a row that moves to `catalog` is required here the
    # moment it moves — a landing that forgot to import its validator is exit 2, not a green
    # run one property short. A newly registered property then gates like any other: nothing
    # below reads a release or a landing date (DEC-35 §3.2). No arity is exempt: a shipped
    # two-snapshot row counts as registered only through its own registration shape, which
    # P-12's landing adds, so until then such a row is this same tool error.
    unregistered = tuple(
        slug for slug in PROPERTY_SLUGS if property_entry(slug).shipped and not is_implemented(slug)
    )
    if unregistered:
        return _tool_error_report(
            "dispatch",
            "the run could not be assembled: no validator is registered for "
            f"{', '.join(unregistered)}. A run that checked the rest would be a weakened "
            "gate wearing a pass (§1.4 rule 2), so no verdict is reported.",
            subject=subject,
            strict=strict,
        )

    answers: dict[PropertySlug, PropertyOutcome] = {}
    for slug in _gated_order():
        try:
            answers[slug] = run_property(slug, ir)
        except PropertyRegistryError as error:
            return _tool_error_report(
                "dispatch", f"{slug}: {error}", subject=subject, strict=strict
            )
        # A blind catch is the rule here, not a lapse: §2.4 makes *any* exception escaping a
        # validator a tool error, and narrowing it would let some crashes through as a
        # verdict — which is exactly the reading "a crash is not a finding" refuses.
        except Exception as error:  # noqa: BLE001
            return _tool_error_report(
                "dispatch",
                f"the {slug} validator raised {type(error).__name__}: {error}. An exception "
                "escaping a validator is a tool error, never a fail (§2.4).",
                subject=subject,
                strict=strict,
            )

    outcomes = tuple(answers[slug] for slug in PROPERTY_SLUGS)
    reports = tuple(outcome for outcome in outcomes if isinstance(outcome, PropertyReport))
    best_effort = TOPOLOGY_SLUGS if _is_fatal(answers["graph-well-formed"]) else ()
    try:
        gate = _gate(reports, strict)
    # The gate's own refusals reach here, and they are §2.4 `dispatch` for the same reason a
    # validator's crash is: the run could not be assembled. The live case is a property whose
    # promotable-note vocabulary grew past the identity rule its own spec fixes — P-02's
    # `strict_promotions` raises rather than dropping a promotion the user was owed — which
    # would otherwise escape only under a strict policy, so the same IR would answer one way
    # with a flag and another way without it.
    except Exception as error:  # noqa: BLE001
        return _tool_error_report(
            "dispatch",
            f"the gate could not be derived: {type(error).__name__}: {error}. A run whose "
            "gate cannot be assembled reached no verdict (§2.4).",
            subject=subject,
            strict=strict,
        )
    return RunReport(
        report_format=REPORT_FORMAT,
        tool=_tool(),
        subject=subject,
        properties=outcomes,
        best_effort=best_effort,
        gate=gate,
    )


# ── §1.2: what extraction said, carried beside the verdict (DEC-35 §3.8) ─────────────────


class _NoteCode(Protocol):
    """A record's code: a ``str``-valued enum member of extraction's closed vocabularies."""

    @property
    def value(self) -> str: ...


class _NoteRecord(Protocol):
    """What an extraction warning and an extraction disclosure both declare.

    The shape :class:`~gebra.extraction.warnings.ExtractionWarning` and
    :class:`~gebra.extraction.disclosures.ExtractionDisclosure` share (INTROSPECTION-SPEC §8),
    stated structurally so this module reads them without importing the extractor.
    """

    @property
    def code(self) -> _NoteCode: ...

    @property
    def message(self) -> str: ...

    @property
    def node(self) -> str | None: ...

    @property
    def detail(self) -> Mapping[str, Any]: ...


class _NoteSource(Protocol):
    """An extraction envelope, as far as its notes go: the warnings, then the disclosures."""

    @property
    def warnings(self) -> Sequence[_NoteRecord]: ...

    @property
    def disclosures(self) -> Sequence[_NoteRecord]: ...


def extraction_notes_of(envelope: _NoteSource) -> tuple[ExtractionNote, ...]:
    """The extraction notes of ``envelope``, in emission order (§0.6 item 8; DEC-36 §4).

    Every warning first, in the order extraction emitted them, then every disclosure, in the
    order INTROSPECTION-SPEC §8 fixes for them and the envelope already holds — graph-scoped
    first, then node-scoped in node-id order: "emission order" over the union. Each record is
    carried field for field; nothing is re-worded, dropped or summarized.

    Args:
        envelope: What ``gebra.extract()`` returned (an
            :class:`~gebra.extraction.envelope.ExtractionEnvelope`), read through the record
            fields it declares and nothing else.

    Raises:
        pydantic.ValidationError: if a record carries a code this build does not admit as a
            note — a disclosure an R-06 record admitted after this build — which is a
            vocabulary this report cannot spell, never one to drop.
    """
    # Validated rather than constructed with keywords: the code is a plain string here, and the
    # model's Literal is where it is checked against the vocabulary this build admits.
    return tuple(
        ExtractionNote.model_validate(
            {
                "code": record.code.value,
                "message": record.message,
                "node": record.node,
                "slots": getattr(record, "slots", ()),
                "detail": record.detail,
            }
        )
        for record in (*envelope.warnings, *envelope.disclosures)
    )


def with_extraction_notes(report: RunReport, notes: Iterable[ExtractionNote]) -> RunReport:
    """``report``, carrying the extraction notes of the run it answers (§1.2; DEC-35 §3.8).

    :func:`verify` reads an IR and never sees the extraction that produced it, so the caller
    that extracted — the CLI, the pytest plugin, a library caller holding an envelope — hands
    the notes over here. The report comes back revalidated, so §0.6 item 8's "present only when
    the run extracted" holds by the model's own rule: a subject obtained any other way refuses
    them. Nothing else moves — not the gate, not a count, not an outcome: a note is never a
    finding.

    Args:
        report: The run report :func:`verify` returned for the extracted IR.
        notes: The notes, in emission order — :func:`extraction_notes_of` over the envelope.

    Returns:
        ``report`` itself when there is no note to carry; otherwise a new report whose
        ``extraction_notes`` are ``notes``.

    Raises:
        ValueError: if ``report`` already carries notes — a run extracts once, and replacing
            them would drop what the first extraction said.
        pydantic.ValidationError: if ``report``'s subject was not extracted.
    """
    carried = tuple(notes)
    if not carried:
        return report
    if report.extraction_notes:
        raise ValueError(
            "this run report already carries its extraction notes; a run extracts once, and "
            "replacing them would drop what that extraction said"
        )
    members: dict[str, Any] = {name: getattr(report, name) for name in RunReport.model_fields}
    members["extraction_notes"] = carried
    return RunReport.model_validate(members)
