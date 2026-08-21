"""The snapshot engine — extract, wrap in the §4.1 envelope, decide a label, store it.

Brief D-11's week-4 milestone is this module's whole job: "``gebra snapshot`` engine wired to
D-08's ``gebra.extract()``". Everything either side of it already shipped — the extractor
(EX-02…), the store and its envelope (SD-01), the V.S.F.E label engine (SD-02) and the diff
that derives a bump class (SD-04/SD-05). What was missing is the two decisions the card
reserves for whoever wires them together: the API surface, and what happens when a workflow
that has not changed is snapshot again.

**The idempotency policy, stated once.** A call compares the working IR's ``graph_version``
against the store's **current** snapshot:

* equal — nothing is written, no clock is read, and the call answers with the label the store
  already holds (:attr:`~gebra.snapshot.models.SnapshotAction.UNCHANGED`). The digest is what
  makes that sound: two IRs with the same ``graph_version`` have the same canonical form
  (IR-SPEC §6), so "the workflow did not change" and "the digest did not move" are one
  question rather than two that happen to agree;
* different — the label is ``workflow_diff(current, working).bump(current_label)``, i.e. the
  S/F/E counters the diff engine derives, applied to the label the store's current version
  carries;
* an empty store — :meth:`Version.initial() <gebra.versioning.models.Version.initial>`,
  ``1.0.0.0``. A first version is a choice, not a derivation: there is no earlier IR to
  compare against.

**Against `current`, not against the whole history.** A store's history is a log, and this
engine only ever asks "has the definition moved since where the store points?". So reverting
a workflow to the content of an older version records a *new* version carrying that older
digest, rather than silently re-pointing at the old label: the history says what happened, and
two versions holding one digest is a shape the store and the version-history engine both
already model. What this policy will never do is write two *different* contents under one
label, because a digest that moved always moves at least one counter.

**Where the clock is.** :mod:`gebra.store` reads no clock at all — that is what lets a test
hold its emitter to "identical content, identical bytes" — and one has to be read somewhere,
because IR-SPEC §4.1's ``extracted_from`` carries an extraction timestamp. Here is that
somewhere, and it is injectable: pass ``extracted_at`` and the whole path from an envelope to
the bytes on disk is a function of its arguments again.

**The §0.2 recording rule is applied, never re-derived.** PROPERTY-CATALOG-SPEC §0.2 makes a
FATAL finding mean "no snapshot is recorded". This engine does not run validators and does not
decide what a FATAL is: hand it the :class:`~gebra.verify.run.RunReport` of a verify run over
the same IR and it refuses to record when ``gate.snapshot_eligible`` is ``false``, which is
the same field ``docs/specs/CLI-SPEC.md`` §4.2 has ``gebra snapshot`` read. It also checks that
the report is *about* this IR, by comparing the digest the report carries with the digest being
recorded — §4.2's "the digest the store records is the digest the gate saw", made true by
construction rather than by caller discipline. Hand it no report and it records: stated plainly
rather than defaulted-around, because a caller who ran no validators has established nothing
for this engine to apply.

**One document class is refused rather than stored.** Node ids MUST be unique within a document
(IR-SPEC §2.1, ratified DEC-22), and every IR reaching here goes through
:func:`~gebra.diff.topology.resolve_subject` — the same precondition
:func:`~gebra.diff.workflow.workflow_diff` applies — *including* the first snapshot of an empty
store, where there is nothing to diff against. That is deliberate rather than incidental: a
stored snapshot the diff engine would refuse is a snapshot nothing can ever be compared with,
and its digest is authored-order-dependent (PD-032's finding, ratified as DEC-22), which is
exactly what a store must not hold under a content-addressed label. The check stays until IR-07
puts it on the model, where it belongs.

**WA-07.** This is the first module outside :mod:`gebra.extraction` that hands a *live* object
to the extractor, so it inherits the never-invokes obligation rather than the weaker
"no user object is in reach" posture of :mod:`gebra.store`, :mod:`gebra.versioning`,
:mod:`gebra.diff` and :mod:`gebra.lineage`. It adds no extraction path of its own — it calls
``gebra.extract()`` and nothing else — and ``tests/snapshot/test_travel_booking.py`` runs the
whole path over the sentinel-guarded travel-booking agent in a fresh interpreter where name
resolution and connection opening raise from the first line, ``StateGraph.compile`` raises from
before gebra is imported, and socket construction raises from the moment gebra's own work
begins.
"""

from __future__ import annotations

import datetime as _datetime
from typing import TYPE_CHECKING

from gebra.diff.topology import resolve_subject
from gebra.diff.workflow import WorkflowDiff, workflow_diff
from gebra.extraction import extract
from gebra.snapshot.models import (
    SnapshotAction,
    SnapshotError,
    SnapshotErrorReason,
    SnapshotOutcome,
)
from gebra.store.models import ExtractedFrom, Snapshot, format_timestamp
from gebra.versioning.models import Version, VersionFormatError

if TYPE_CHECKING:
    import os

    from gebra.extraction.envelope import ExtractionEnvelope
    from gebra.store.store import SnapshotStore
    from gebra.verify.run import RunReport

__all__ = ["record", "snapshot"]


def snapshot(
    workflow: object,
    *,
    store: SnapshotStore,
    source: str | None = None,
    sidecar: str | os.PathLike[str] | None = None,
    extracted_at: _datetime.datetime | None = None,
    eligibility: RunReport | None = None,
) -> SnapshotOutcome:
    """Extract ``workflow`` and record it in ``store`` — the end-to-end call.

    Exactly :func:`record` over ``gebra.extract(workflow, sidecar=sidecar)``, and the two are
    separate entry points on purpose: ``docs/specs/CLI-SPEC.md`` §4.2 requires the eligibility
    run and the write to "share one resolution and one IR", which a caller who already holds
    an envelope gets from :func:`record` and could not get from here.

    Extraction imports and inspects; it never invokes (INTROSPECTION-SPEC §1), and this
    function adds nothing to what it does.

    Args:
        workflow: A ``StateGraph`` builder, a compiled graph, or an LCEL ``Runnable`` — what
            ``gebra.extract()`` takes.
        store: The ``.gebra/`` store to record in. Created on first write.
        source: The provenance reference to record, or ``None`` to record what extraction
            knows (see :func:`record`).
        sidecar: The ``gebra.toml`` to extract against, or ``None`` for discovery.
        extracted_at: When to say the IR was made; defaults to now, in UTC.
        eligibility: A run report over this same workflow, whose ``gate.snapshot_eligible``
            is applied (§0.2). ``None`` runs no check.

    Returns:
        What the call did — see :class:`~gebra.snapshot.models.SnapshotOutcome`.

    **The extraction warnings are not reachable through this entry point.** They ride the
    envelope this function builds and discards (INTROSPECTION-SPEC §8: warnings "are never
    silently droppable", and a warning-free extraction is part of the strict-mode bar), and
    nothing about a snapshot depends on them — they are outside the hash scope. A caller who
    needs them extracts first and calls :func:`record`, which is the same split the CLI needs
    for its own reason.

    Raises:
        ExtractionError: if ``workflow`` is not extractable (INTROSPECTION-SPEC §2).
        SnapshotError: as for :func:`record`.
        StoreError: as for :func:`record`.
        ValueError: as for :func:`record`.
    """
    return record(
        extract(workflow, sidecar=sidecar),
        store=store,
        source=source,
        extracted_at=extracted_at,
        eligibility=eligibility,
    )


def record(
    envelope: ExtractionEnvelope,
    *,
    store: SnapshotStore,
    source: str | None = None,
    extracted_at: _datetime.datetime | None = None,
    eligibility: RunReport | None = None,
) -> SnapshotOutcome:
    """Record ``envelope``'s IR in ``store`` under the label the policy assigns it.

    The half of the engine that touches no live object: it takes an extraction that already
    happened. This is the entry point ``gebra snapshot`` calls, so that the run deciding
    eligibility and the write share one resolution and one IR.

    Args:
        envelope: What ``gebra.extract()`` returned. Its warnings are not read here — they
            ride the extraction envelope (INTROSPECTION-SPEC §8) and are outside the hash
            scope and outside this engine's question.
        store: The ``.gebra/`` store to record in. Created on first write.
        source: What to record as the snapshot's ``extracted_from.source``. Defaults to what
            extraction knows about itself, which is the object's *type* identity
            (``langgraph:StateGraph``); a caller who named the workflow — the CLI's
            ``--import travel_booking:build_agent`` — passes that reference instead, since
            ``docs/specs/CLI-SPEC.md`` §2.1 reads a stored snapshot's ``source`` back as the
            subject reference of a snapshot-mode report.
        extracted_at: When to say the IR was made. Defaults to now, in UTC, at second
            precision (:data:`~gebra.store.models.TIMESTAMP_FORMAT`). Pass one and this whole
            call becomes a function of its arguments.
        eligibility: A run report over ``envelope.ir``, whose ``gate.snapshot_eligible`` is
            applied. ``None`` runs no check — see the module docstring.

    Returns:
        What the call did — see :class:`~gebra.snapshot.models.SnapshotOutcome`.

    **What the history row says about time.** ``store.write`` is given no separate
    ``created_at``, so the row records the instant the IR was *made* rather than a second
    instant for when it landed. A snapshot is written as soon as it is made here, and pinning
    one instant is what keeps the whole path from an envelope to the bytes on disk a function
    of its arguments — a second clock read would put a moving value into ``meta.yaml``.

    Raises:
        SnapshotError: ``not-snapshot-eligible`` when ``eligibility`` forbids recording;
            ``eligibility-mismatch`` when it is a report about some other IR;
            ``unversionable-current`` when the store's current label is outside the V.S.F.E
            grammar, so no bump can be derived from it; ``no-version-movement`` when the
            content moved and the diff derived no component — see below.
        StoreError: propagated unchanged from the store — ``digest-mismatch`` or
            ``snapshot-unreadable`` for a damaged current snapshot, ``meta-unreadable`` for a
            damaged index, ``duplicate-version`` if the derived label is one the history
            already holds (reachable only in a store whose ``current`` is not its newest
            version).
        CanonicalizationError: if the IR carries a value the canonical form refuses.
        ValueError: if the IR repeats a node id (IR-SPEC §2.1, ratified DEC-22) — refused on
            every path, the first snapshot of an empty store included.
        pydantic.ValidationError: if ``source`` is the empty string, which the store model
            refuses; absence of a source is not spellable here, since extraction always knows
            one.
        VersionFormatError: with reason ``TOO_LONG`` if the bumped label could no longer be a
            snapshot's file name.
    """
    ir, anchor = resolve_subject(envelope.ir)
    digest = anchor.graph_version
    _refuse_ineligible(eligibility, digest)

    current = store.current()

    if current is not None and current.graph_version == digest:
        return SnapshotOutcome(
            action=SnapshotAction.UNCHANGED,
            version=current.version,
            graph_version=digest,
            path=store.snapshot_path(current.version),
            previous=current.version,
            diff=workflow_diff(current, ir),
        )

    if current is None:
        version, diff = Version.initial(), None
    else:
        diff = workflow_diff(current, ir)
        version = _bumped(current.version, diff)

    written = store.write(
        Snapshot.of(
            ir,
            version=str(version),
            extracted_from=_provenance(envelope, source=source, extracted_at=extracted_at),
        )
    )
    return SnapshotOutcome(
        action=SnapshotAction.RECORDED,
        version=str(version),
        graph_version=digest,
        path=written,
        previous=None if current is None else current.version,
        diff=diff,
    )


def _refuse_ineligible(eligibility: RunReport | None, digest: str) -> None:
    """Apply ``gate.snapshot_eligible`` (§0.2), and check the report is about ``digest``.

    The rule is read, never re-derived: one boolean off the report decides, and what counts as
    a FATAL stays the property catalog's question. The field is ``false`` in two situations and
    the message names which one it met — a run that reached a verdict and counted a FATAL
    (§0.2's rule proper), and a run that reached no verdict at all (exit ``2``), where nothing
    was established either way.

    The subject check is the second half of the same guarantee. ``docs/specs/CLI-SPEC.md``
    §4.2 requires that "the digest the store records is the digest the gate saw", and
    :class:`~gebra.verify.run.Subject` carries a ``graph_version`` that :func:`gebra.verify.verify`
    computes rather than accepts — so the two are comparable, and comparing them makes §4.2's
    sentence true by construction instead of by caller discipline. A tool-error report carries
    no subject and is refused by the eligibility half first.
    """
    if eligibility is None:
        return
    if not eligibility.gate.snapshot_eligible:
        raise SnapshotError(
            "the run report handed in is not snapshot-eligible, so nothing is recorded: its "
            f"gate outcome is {eligibility.gate.outcome!r} with "
            f"{eligibility.gate.counts.fatal} FATAL finding(s). PROPERTY-CATALOG-SPEC §0.2 — "
            "a FATAL means the definition is unfit to run and no snapshot is recorded; a run "
            "that reached no verdict established nothing to record one on",
            reason=SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE,
        )
    subject = eligibility.subject
    if subject is not None and subject.graph_version != digest:
        raise SnapshotError(
            f"the run report handed in verified {subject.graph_version}, and the definition "
            f"being recorded is {digest}; a report about some other IR cannot say whether "
            "this one may be recorded (docs/specs/CLI-SPEC.md §4.2 — the digest the store "
            "records is the digest the gate saw)",
            reason=SnapshotErrorReason.ELIGIBILITY_MISMATCH,
        )


def _bumped(current_label: str, diff: WorkflowDiff) -> Version:
    """The label a changed workflow gets, from the store's current one and the diff.

    Two refusals rather than a guess. A current label outside the V.S.F.E grammar has no
    counters to increment — the store's own check on a label is a path-safety floor and
    deliberately wider than the grammar (SD-01), so a store can hold ``draft`` and this engine
    has to say so rather than start a second numbering beside it. And a bump class that
    selects nothing while the digest moved would produce the *current* label for content the
    store does not hold under it; the diff engine's completeness property says that cannot
    happen on a document it accepts, and this is that premise failing loudly instead of
    writing a label that means something else.
    """
    try:
        base = Version.parse(current_label)
    except VersionFormatError as exc:
        raise SnapshotError(
            f"the store's current version is {current_label!r}, which is not a V.S.F.E "
            "label, so there is no counter to bump for the change that was found; give the "
            "store a labelled current version, or record this one yourself",
            reason=SnapshotErrorReason.UNVERSIONABLE_CURRENT,
        ) from exc
    bumped = diff.bump(base)
    if bumped == base:
        raise SnapshotError(
            f"the working definition differs from {current_label!r} but the diff selected no "
            "V.S.F.E component, so no label can be assigned to it; this is a defect in the "
            "diff engine's coverage of the hash scope, not a workflow that cannot be "
            "versioned",
            reason=SnapshotErrorReason.NO_VERSION_MOVEMENT,
        )
    return bumped


def _provenance(
    envelope: ExtractionEnvelope,
    *,
    source: str | None,
    extracted_at: _datetime.datetime | None,
) -> ExtractedFrom:
    """The store's ``extracted_from`` from the extractor's — the bridge SD-01 left to here.

    The two models carry the same name and different jobs (``gebra.store.models`` says so at
    :class:`~gebra.store.models.ExtractedFrom`): extraction's is what one extraction knows
    about itself, clock-free and value-comparable, while this one is what the *store* records
    about a snapshot and is IR-SPEC §4.1's envelope field proper. Three members cross over
    unchanged and one is added:

    * ``source`` — extraction's, or the caller's reference when it has a better one;
    * ``extractor_version`` — extraction's, verbatim;
    * ``sidecar_path`` — extraction's ``sidecar``, renamed to the member PD-012's
      ratification amendment added for ANNOTATION-API-SPEC §2 ("MUST record the absolute
      sidecar path used (or its absence) so digest divergence is diagnosable"). Absence
      crosses over as ``None``, which is how both models spell it;
    * ``extracted_at`` — the one member neither the extractor nor the store supplies, for the
      reason each of them records: a timestamp would make two extractions of one unchanged
      object compare unequal *as envelopes*, and the store reads no clock.

    What deliberately does **not** cross over is the rest of extraction's provenance — the
    object family, the managed state keys, the router codomains, the compiled-level surfaces.
    PD-012 fixed ``extracted_from`` at four members and ``extra="forbid"`` holds it there;
    widening it is an amendment to that ruling, not a decision for the module that happens to
    fill it in.
    """
    moment = extracted_at if extracted_at is not None else _now()
    return ExtractedFrom(
        source=source if source is not None else envelope.extracted_from.source,
        extractor_version=envelope.extracted_from.extractor_version,
        extracted_at=format_timestamp(moment),
        sidecar_path=envelope.extracted_from.sidecar,
    )


def _now() -> _datetime.datetime:
    """The current instant, UTC-aware. The one clock read in the snapshot path."""
    return _datetime.datetime.now(_datetime.timezone.utc)
