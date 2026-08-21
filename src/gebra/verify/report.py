"""The negative verdict and the one report model — §0.3's ``Failure`` and ``PropertyReport``.

**One property, one report** (§0.3, ratified envelope-wide at walkthrough #2 — DEC-11).
A property that finds several things does not emit several reports: the deterministically
first finding fills ``failure`` — each section fixes its own ordering rule — and every
further **same-property** finding rides ``Failure.co_failures``. Findings are never dropped
and never re-packaged as self-referential advisories. ``advisories`` is for **cross-property**
WARNING-class side findings only (the ``mixed/03`` precedent, where P-08 findings ride a
P-09 primary).

**Every record classifies itself.** The primary ``Failure``, every ``CoFailure`` and every
``Advisory`` carries its own ``severity`` and ``claim_class`` (§0.1), so a consumer can
never mistake a HEURISTIC advisory for a proof-backed finding — including inside a report
whose primary finding is DEFENSIBLE.

**Strict mode changes the gate, never the record** (§0.2). A promoted finding keeps
``severity: "warning"`` and its claim class here; ``--gebra-strict`` is a CI policy choice
applied above this model, and rewriting a HEURISTIC advisory into an ERROR would be the
overstatement WA-06 exists to prevent. Nothing in this module reads a strict flag.

**Scope.** §0 specifies the per-property envelope only. The run-level wrapper — all thirteen
reports, the IR identity, exit-code derivation, the report file format — is
REPORT-FORMAT-SPEC's to own (§0.3 scope boundary), and the ``verify()`` aggregation that
feeds it is its own card.
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Literal, TypeAlias

from pydantic import Field, TypeAdapter, model_validator

from gebra.verify.base import (
    ClaimClass,
    ConditionId,
    NodeId,
    PropertyId,
    PropertySlug,
    ReportModel,
    Severity,
    json_text,
)
from gebra.verify.locations import AnyLocation, DataflowLocation
from gebra.verify.witnesses import Witness, WitnessNote

__all__ = [
    "Advisory",
    "AnyFailure",
    "CoFailure",
    "Failure",
    "P04Failure",
    "PropertyReport",
    "validate_failure",
    "validate_location",
    "validate_report",
    "validate_witness",
]


class Advisory(ReportModel):
    """A WARNING-class side finding from **another** property (``mixed/03`` precedent).

    Cross-property carriage only: a same-property co-finding is a :class:`CoFailure`, never
    an advisory. ``severity`` is fixed at ``warning`` because that is what riding another
    property's report licenses — an ERROR-grade finding of its own is that property's report
    to make.
    """

    property: PropertySlug
    property_condition: ConditionId
    severity: Literal["warning"]
    claim_class: ClaimClass
    location: AnyLocation


class CoFailure(ReportModel):
    """A further finding on the same report (``mixed/04``, ``mixed/01`` precedents).

    ``subsumed_by`` names the property that owns the root cause (DEC-05 D2): one root
    cause, one report, no double-blame. The pinned case is ``mixed/04`` — P-01 reports a
    node unreachable from START, and the P-04 read that node would have made carries
    ``subsumed_by: "P-01"`` rather than counting as an independent gap.
    """

    property: PropertySlug
    property_condition: ConditionId
    location: AnyLocation
    severity: Severity
    claim_class: ClaimClass
    subsumed_by: PropertyId | None = None
    #: Display-only prose; never parsed.
    note: str | None = None
    #: Same-property structured notes on the closed ``WitnessNoteKind`` vocabulary (§2.3),
    #: carried unconditionally on the fail path — DEC-23 (PD-037 Q2). Distinct from
    #: :class:`Advisory` (cross-property, DEC-11) and from :attr:`note` (display prose).
    #: This is where a P-02 qualification-failure note rides when P-02's finding travels as
    #: a co-failure on another property's report (run-level composition).
    notes: tuple[WitnessNote, ...] | None = None


class Failure(ReportModel):
    """The structured negative verdict (§0.3).

    ``remediation`` is display-only prose — the one place a report speaks to a person —
    and is never parsed. Everything a consumer branches on is structured: the condition ID
    (a §0.4 registry member), the location, the severity and the claim class.
    """

    property_condition: ConditionId
    location: AnyLocation
    severity: Severity
    claim_class: ClaimClass
    #: Display-only prose; never parsed.
    remediation: str | None = None
    co_failures: tuple[CoFailure, ...] | None = None
    advisories: tuple[Advisory, ...] | None = None
    #: This finding is owned upstream (DEC-05 D2).
    subsumed_by: PropertyId | None = None
    #: Same-property structured notes on the closed ``WitnessNoteKind`` vocabulary (§2.3),
    #: carried unconditionally whenever the property's result is fail — DEC-23 (PD-037
    #: Q2): every qualification-failure note recorded during P-02's witness search rides
    #: the resulting failure, with no "sole witness attempt" or any other gating. Distinct
    #: from ``advisories`` (cross-property, DEC-11) and from ``remediation`` (prose).
    notes: tuple[WitnessNote, ...] | None = None


class P04Failure(Failure):
    """P-04's concrete failure subtype (§4.3).

    It exists because ``extra="forbid"`` means the base cannot carry P-04's two optional
    diagnostics, which DEC-11 pin 3 keeps: ``writers_on_other_paths`` (writers that cover
    *other* paths) and ``downstream_writers`` (writers wired after the reader). Both are
    diagnostic context, emitted only when non-empty, and never part of the verdict.

    The narrowed ``location`` is what makes the subtype recognisable. Resolving on the two
    optional extras alone would leave a P-04 failure that happens to carry neither of them
    loading as a base :class:`Failure` while the validator constructs a ``P04Failure`` —
    and pydantic equality is class-sensitive, so the PC-6 fixture-vs-output identity would
    break on exactly the fixtures that need it least. A ``DataflowLocation`` (``kind:
    "state-key"`` with a required ``node`` and ``path``) resolves *every* P-04 failure here,
    extras or not.
    """

    location: DataflowLocation
    writers_on_other_paths: tuple[NodeId, ...] | None = None
    downstream_writers: tuple[NodeId, ...] | None = None


#: What ``PropertyReport.failure`` carries: the wedge's concrete failure subtypes, then the
#: base. Left-to-right, like :data:`~gebra.verify.locations.AnyLocation` and for the same
#: reason — a subtype cannot re-use the base's shape under ``extra="forbid"``.
AnyFailure: TypeAlias = Annotated[P04Failure | Failure, Field(union_mode="left_to_right")]


class PropertyReport(ReportModel):
    """One property's verdict — the one report model (§0.3; A6 PC-6).

    The same class validates a fixture's ``expected:`` block and a validator's output, so a
    fixture cannot drift from the result type and comparison is model equality rather than
    raw-dict or string equality.
    """

    property: PropertySlug
    result: Literal["pass", "fail"]
    #: REQUIRED iff ``result == "pass"``.
    witness: Witness | None = None
    #: REQUIRED iff ``result == "fail"``.
    failure: AnyFailure | None = None

    @model_validator(mode="after")
    def _witness_xor_failure(self) -> PropertyReport:
        if (self.result == "pass") != (self.witness is not None):
            raise ValueError("witness present iff result == pass")
        if (self.result == "fail") != (self.failure is not None):
            raise ValueError("failure present iff result == fail")
        return self

    @classmethod
    def passing(cls, property: PropertySlug, witness: Witness) -> PropertyReport:
        """A passing report carrying ``witness`` — the XOR rule satisfied by construction."""
        return cls(property=property, result="pass", witness=witness)

    @classmethod
    def failing(cls, property: PropertySlug, failure: Failure) -> PropertyReport:
        """A failing report carrying ``failure`` — the XOR rule satisfied by construction."""
        return cls(property=property, result="fail", failure=failure)


# ── Ingestion: parsed document data → envelope model ─────────────────────────────────────

_WITNESS_ADAPTER: Final[TypeAdapter[Any]] = TypeAdapter(Witness)
_FAILURE_ADAPTER: Final[TypeAdapter[Any]] = TypeAdapter(AnyFailure)
_LOCATION_ADAPTER: Final[TypeAdapter[Any]] = TypeAdapter(AnyLocation)


def validate_report(data: object) -> PropertyReport:
    """Validate parsed document data as a :class:`PropertyReport`.

    This is §0.3's ``PropertyReport.model_validate({"property": fixture["property"],
    **fixture["expected"]})``, spelled for strict models: the data is re-encoded and
    validated in JSON mode, where a sequence lands in the tuple-typed members. Composing
    that mapping — an ``expected:`` block omits ``property``, which lives at the fixture top
    level — belongs to the fixture loader; validating it is this function.

    Raises:
        TypeError: if ``data`` holds a value JSON has no form for.
        pydantic.ValidationError: if the data does not satisfy the §0.3 envelope.
    """
    return PropertyReport.model_validate_json(json_text(data))


def validate_witness(data: object) -> Witness:
    """Validate parsed document data as one member of the §0.3 :data:`Witness` union.

    Raises:
        TypeError: if ``data`` holds a value JSON has no form for.
        pydantic.ValidationError: if the data satisfies no member of the union.
    """
    witness: Witness = _WITNESS_ADAPTER.validate_json(json_text(data))
    return witness


def validate_failure(data: object) -> Failure:
    """Validate parsed document data as a :class:`Failure` or a concrete subtype.

    Raises:
        TypeError: if ``data`` holds a value JSON has no form for.
        pydantic.ValidationError: if the data does not satisfy the §0.3 failure shape.
    """
    failure: Failure = _FAILURE_ADAPTER.validate_json(json_text(data))
    return failure


def validate_location(data: object) -> AnyLocation:
    """Validate parsed document data as an anchor or a concrete location subtype.

    Raises:
        TypeError: if ``data`` holds a value JSON has no form for.
        pydantic.ValidationError: if the data satisfies no member of the union.
    """
    location: AnyLocation = _LOCATION_ADAPTER.validate_json(json_text(data))
    return location
