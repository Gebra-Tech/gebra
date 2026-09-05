"""The finding and note traversal a rendering walks — REPORT-FORMAT-SPEC §2.1, for display.

§2.1 defines a **finding** as any emitted record carrying a ``severity`` — a failing report's
primary ``Failure``, every ``CoFailure`` in it, every ``Advisory`` it carries — and a **note**
as a WARNING-grade ``WitnessNote``, on either result path (DEC-23 carriage). A rendering has to
walk both to show them, so the walk lives here, once, for all three surfaces.

**This is a traversal, not a derivation.** CLI-SPEC §0.1 rule 3 keeps the presentation layer
from recomputing a structural fact the report already carries: the severity tally a rendering
prints is ``gate.counts``, the exit code is ``gate.exit_code``, and the promotions are
``gate.promotions`` — never a recount taken off this walk. What the walk supplies is the
records themselves, in the order §1.4 rule 3 fixes, so each can be rendered whole.
``tests/report/test_findings.py`` holds the walk to ``gate.counts`` over the whole corpus, so
the two cannot drift even though only one of them is authoritative.

**The owner of a record is the record's own property** (§2.3's easy-to-get-wrong row): an
``Advisory`` riding another property's report is still its own property's finding, which is why
:attr:`Finding.owner` and :attr:`Finding.host` are separate fields and why the SARIF bag reads
``gebra/property`` off the first.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from gebra.verify.base import ClaimClass, ConditionId, PropertyId, PropertySlug, Severity
from gebra.verify.locations import AnyLocation
from gebra.verify.report import P04Failure, PropertyReport
from gebra.verify.witnesses import WitnessNote

__all__ = ["Finding", "FindingOrigin", "findings_of", "notes_of"]

#: Where a finding was carried on its host report (§2.1's three record kinds).
FindingOrigin: TypeAlias = Literal["failure", "co-failure", "advisory"]


@dataclass(frozen=True)
class Finding:
    """One §2.1 finding, flattened for rendering with everything a surface needs.

    Attributes:
        owner: The property the record belongs to — for an advisory, the advisory's own
            property, never the host report's (§2.3, §3.2).
        host: The property whose report carries it. Equal to ``owner`` except on an advisory.
        origin: Which of §2.1's three record kinds this is.
        severity: The record's own grade. Unchanged by strict promotion (§2.3).
        claim_class: The record's own class. Never inherited from a primary (§0.1).
        property_condition: The §0.4 condition ID the record is reported under.
        location: The structural anchor, concrete subtype included (§4.5).
        subsumed_by: The property that owns the root cause, carried as given (§3.2 rule 4).
        remediation: Display-only prose; never parsed (§4.6 rule 7).
        note: ``CoFailure.note`` — display-only prose, distinct from ``notes``.
        notes: Structured same-property notes riding this record (DEC-23 fail-path carriage).
        evidence: The concrete failure subtype's extra diagnostics, keyed for a SARIF property
            bag (§4.4: P-04's two optional members "ride ``result.properties``").
    """

    owner: PropertySlug
    host: PropertySlug
    origin: FindingOrigin
    severity: Severity
    claim_class: ClaimClass
    property_condition: ConditionId
    location: AnyLocation
    subsumed_by: PropertyId | None = None
    remediation: str | None = None
    note: str | None = None
    notes: tuple[WitnessNote, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)


def _failure_evidence(failure: P04Failure) -> dict[str, Any]:
    """P-04's three optional diagnostics, emitted only when non-empty (§4.4).

    The third, ``outside_static_coverage`` (DEC-28 clause 2; ir 1.1), is report-level context
    riding the primary finding — the readers a ``dynamic`` router alone reaches, whose declared
    reads no analysis covered — and projects to the property bag like the other two.
    """
    evidence: dict[str, Any] = {}
    if failure.writers_on_other_paths:
        evidence["gebra/writersOnOtherPaths"] = list(failure.writers_on_other_paths)
    if failure.downstream_writers:
        evidence["gebra/downstreamWriters"] = list(failure.downstream_writers)
    if failure.outside_static_coverage:
        evidence["gebra/outsideStaticCoverage"] = list(failure.outside_static_coverage)
    return evidence


def findings_of(report: PropertyReport) -> Iterator[Finding]:
    """Every finding of ``report``, in the order §1.4 rule 3 carries through.

    The primary first, then its co-failures, then its advisories — each property section
    fixes the order within those lists, and this walk preserves it untouched.
    """
    failure = report.failure
    if failure is None:
        return
    yield Finding(
        owner=report.property,
        host=report.property,
        origin="failure",
        severity=failure.severity,
        claim_class=failure.claim_class,
        property_condition=failure.property_condition,
        location=failure.location,
        subsumed_by=failure.subsumed_by,
        remediation=failure.remediation,
        notes=failure.notes or (),
        evidence=_failure_evidence(failure) if isinstance(failure, P04Failure) else {},
    )
    for co_failure in failure.co_failures or ():
        yield Finding(
            owner=co_failure.property,
            host=report.property,
            origin="co-failure",
            severity=co_failure.severity,
            claim_class=co_failure.claim_class,
            property_condition=co_failure.property_condition,
            location=co_failure.location,
            subsumed_by=co_failure.subsumed_by,
            note=co_failure.note,
            notes=co_failure.notes or (),
        )
    for advisory in failure.advisories or ():
        yield Finding(
            owner=advisory.property,
            host=report.property,
            origin="advisory",
            severity=advisory.severity,
            claim_class=advisory.claim_class,
            property_condition=advisory.property_condition,
            location=advisory.location,
        )


def notes_of(report: PropertyReport) -> Iterator[WitnessNote]:
    """Every structured note of ``report``, on either result path (§2.1, DEC-23).

    Notes ride a passing report's witness and — unconditionally, so a failing property never
    silently drops one — ``Failure.notes`` and ``CoFailure.notes`` on the fail path. A note is
    not a finding: it fails no gate on its own and is counted separately.
    """
    witness = report.witness
    if witness is not None and "notes" in type(witness).model_fields:
        notes: tuple[WitnessNote, ...] = getattr(witness, "notes", ())
        yield from notes
    failure = report.failure
    if failure is None:
        return
    yield from failure.notes or ()
    for co_failure in failure.co_failures or ():
        yield from co_failure.notes or ()
