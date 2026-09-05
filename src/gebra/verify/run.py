"""The run-level report and the ``verify()`` aggregation — ``docs/specs/REPORT-FORMAT-SPEC.md``.

PROPERTY-CATALOG-SPEC §0.3 specifies one property's report and hands everything above it —
"all thirteen ``PropertyReport``s + IR identity + exit-code derivation + serialization
profile" — to ``REPORT-FORMAT-SPEC``. This module is that document as built: §1.2's models,
§2's exit-code derivation, and :func:`verify`, which runs the wedge five over one IR and
returns the :class:`RunReport` the CLI, the pytest plugin and the audit export all read.

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
fix the run's gate — exit ``1`` with no snapshot recorded, whatever the other four say. And
the run report *says so*: :attr:`RunReport.best_effort` names the three properties whose
outcomes a consumer must read as diagnostics on that run, so the distinction survives into
the artifact instead of living only in the spec.

**Hermetic, like the validators it drives.** Nothing here imports langgraph, executes a
workflow node, calls a model or opens a network connection (WA-07): the input is a validated
:class:`~gebra.ir.WorkflowIR`, dispatch calls registered validators that read serialized IR,
and the output is structured values. ``tests/verify/test_run.py`` proves it in a guarded
interpreter over the whole vendored corpus rather than asserting it here.

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

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal, TypeAlias

from pydantic import Field, model_validator

import gebra
from gebra.ir import IrVersion, WorkflowIR
from gebra.ir.canonical import CanonicalizationError, graph_version
from gebra.verify.base import (
    ClaimClass,
    ConditionId,
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
    WEDGE_SLUGS,
    NotImplementedMarker,
    PropertyRegistryError,
    is_implemented,
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
    "verify",
]


#: The ``report_format`` this build produces and reads. ``1.2`` under §1.6's MINOR rows, on the
#: post-final route (VAL-14; DEC-28's two optional diagnostics): three optional members join
#: shapes that did not carry them at ``1.1`` — ``WellFormednessWitness.dynamic_dependent``,
#: ``DataflowWitness.outside_static_coverage`` and ``P04Failure.outside_static_coverage`` — and
#: ``Subject.ir_version`` admits ``"1.1"``, the stamp a ``dynamic``-bearing document carries.
#: ``1.1`` (VAL-11) added ``Promotion.property_condition`` on a witness-note promotion and
#: ``RunReport.best_effort``; Phase-0 shipped at it.
REPORT_FORMAT: Final = "1.2"

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


class RunReport(RunReportModel):
    """The run-level wrapper (§1.2; PROPERTY-CATALOG-SPEC §0.3's scope boundary)."""

    report_format: Literal["1.2"]
    tool: Tool
    #: Absent only when a tool error preceded IR identity.
    subject: Subject | None = None
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

    One consequence is interim rather than settled. IR-SPEC §2.4 ties kind ``dynamic`` to
    ``ir_version`` ≥ 1.1 but names no enforcement site for that constraint, so a hand-authored
    document stamped ``"1.0"`` that carries a ``dynamic`` edge loads, is verified under the
    dynamic semantics, and is reported here at its own stamp. Policing the stamp against the
    constructs is a validation-requiredness change on ``WorkflowIR``'s frozen surface and takes
    IR-MODELS-FREEZE §4's DEC route (filed as PD-055 at VAL-14); until it is ruled, verbatim
    reporting is the reading the frozen text supports, not a decision that the under-stamp is
    acceptable.

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
    fixed — exit ``1``, no snapshot — whatever the other four say. Their reports are still
    produced and still carried, because §1.4 wants an outcome per slug and a diagnostic on
    ill-formed topology is worth reading; ``best_effort`` is what stops one being read as a
    contract-bearing verdict.

    Four things become a tool error rather than a verdict (§2.4), because exit ``2`` means
    "no verdict was reached" and each of them means exactly that: an IR with no computable
    digest (``ir-validation``); an unregistered member of the wedge five, since a run that
    silently checked four of the five would be a weakened gate wearing a pass (``dispatch``,
    §1.4 rule 2); an exception escaping a validator, or a validator answering for the wrong
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
        and the SARIF projection are three views of.
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
    unregistered = tuple(slug for slug in WEDGE_SLUGS if not is_implemented(slug))
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
