"""The per-version audit export — a run report over a stored snapshot, written to the store.

Brief D-11 In-Scope 6 and deliverable 5: "audit export: JSON property report per version".
What that document *is* was ratified at CLI-01 and is not this module's to decide — it is
``docs/specs/REPORT-FORMAT-SPEC.md`` §1's :class:`~gebra.verify.RunReport` in the **snapshot
profile** of its §6, written to the path PD-012 fixes::

    from gebra.audit import export_store
    from gebra.store import SnapshotStore

    store = SnapshotStore.for_project(project_root)
    for outcome in export_store(store):
        outcome.path            # <project_root>/.gebra/reports/1.0.0.0.report.json
        outcome.report.gate.exit_code

§6.3 supersedes SD-07's provisional schema in terms: "the audit export's schema is §1's
``RunReport`` in the snapshot profile of §6.2. SD-07 defines no export schema of its own and
carries no second version line." So this module assembles; it invents nothing. Its whole
contribution above :func:`gebra.verify.verify` is the §6.2 profile — three obligations, of
which two are about the subject and one is about *not* having a schema:

1. ``subject.input_mode`` is ``"snapshot"``, so ``subject.version`` is required and is the
   label the file is named for;
2. ``subject.graph_version`` is the stored snapshot's, byte-for-byte;
3. ``report_format`` is the same version as any other run report.

:func:`check_profile` is those obligations as a function, and it runs before every write, so a
document that does not conform is never on disk.

**Three things brief D-11 In-Scope 6 asks the audit report to carry that this document does
not, stated together because leaving any of them to be discovered would be worse than the
absence.** In-Scope 6 lists "V.S.F.E version, ``ir_version``, timestamp, every catalog property
P-01..P-13 with pass/fail, claim class, and witness, plus the classified diff against the
previous version". The first two and the properties are here. The other three are not:

1. **The timestamp.** §1.3 refuses it in terms — "a timestamp would make two runs over one
   unchanged workflow compare unequal, and every … audit export in §6 depends on
   byte-reproducibility" — and puts the dating on the snapshot's own
   ``extracted_from.extracted_at``, which is in the file this export is named for.
2. **A claim class on a passing property.** §4.2 has a pass's class "read from the property
   catalog (a pass carries no per-record grade)", and the §0.3 envelope carries ``claim_class``
   on findings and on the P-08 witness only — so a clean export carries none, and a reader
   joins to ``gebra.verify.PROPERTY_REGISTRY`` for it. Adding one would be a new member and a
   §1.6 bump.
3. **The classified diff against the previous version.** §7 note 5 rules the boundary directly
   — "a structural diff (``gebra diff``) is **not** a run report … the S/F/E class of a diff is
   the SD track's own output shape" — and §0.4 puts diff output outside this document
   altogether. The content is not lost, it is one layer out: :func:`gebra.lineage.lineage`
   lists every version with its per-pair bump class, :func:`gebra.lineage.dump_lineage`
   projects that to stable JSON, and :func:`gebra.lineage.compare` returns the content diff for
   any pair.

The third is worth naming carefully, because two owner-ratified plan artifacts read
differently on it and SD-09 is the card measured against them. **PD-006 R4's rationale
paragraph** (ratified 2026-07-24) says per-version audit exports "list P-01..P-13 with the 8
not-implemented markers (R3.4) **and carry the structural diff**". **PD-006's own checklist
block** — the frozen-on-sign text R6 lifted verbatim into ``PHASE-0-DOD-CHECKLIST`` §S2, which
is what G7 acceptance is actually verified against — says "per-version audit exports list
P-01..P-13 with the 8 not-implemented markers" and drops the diff clause. The acceptance-bearing
text is the checklist's, this module conforms to it, and the substance of the rationale is met
at the store rather than in this file. Recorded as ``PD-047`` so the disposition is reviewable
rather than inferred from what was built; if it is overturned, the route is an amendment to
REPORT-FORMAT-SPEC with its §1.6 bump (§6.3), never a local schema — two schemas for one
document is the drift that ratification exists to prevent.

**No wall-clock field, and that is what makes an export reproducible.** §1.3: a timestamp
"would make two runs over one unchanged workflow compare unequal, and every golden in CLI-07
and every audit export in §6 depends on byte-reproducibility". Dating rides the snapshot's own
``extracted_from.extracted_at``, which is in the snapshot file the export names. So exporting
the same stored version twice with the same validators writes the same bytes, and re-exporting
is a safe, idempotent act rather than a change in the audit trail.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07). Its input is a
stored IR *model*; no user object is ever in reach to invoke.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gebra.audit.models import AuditError, AuditErrorReason, ExportOutcome
from gebra.report.native import render_native
from gebra.store.atomic import write_atomic
from gebra.verify import STRICT_OFF, RunPolicy, RunReport, SubjectRef, verify

if TYPE_CHECKING:
    from pathlib import Path

    from gebra.store.models import Snapshot
    from gebra.store.store import SnapshotStore
    from gebra.verify import StrictPolicy

__all__ = [
    "check_profile",
    "export_store",
    "export_version",
    "read_export",
    "snapshot_report",
]


def snapshot_report(snapshot: Snapshot, *, strict: StrictPolicy = STRICT_OFF) -> RunReport:
    """Verify a stored snapshot and answer with the §6 snapshot-profile run report.

    The subject is assembled from the snapshot's own envelope and nowhere else:

    * ``source`` is the stored ``extracted_from.source`` — REPORT-FORMAT-SPEC §1.3's snapshot
      bullet names exactly that field ("the store's own provenance field, which is free text
      the producer chose"), and pointedly *not* the extraction envelope's type identity, which
      collapses to one value for every workflow in a repository (the 2026-08-05 CLI-02
      amendment). :func:`gebra.snapshot.record` is where a caller gets to choose it.
    * ``version`` is the snapshot's label, which §6.2 obligation 1 requires to equal the file
      name the export lands under — and it does, because both come from this one value.
    * ``sidecar`` is the stored ``extracted_from.sidecar_path``, carried through so that a
      digest that moved because a different ``gebra.toml`` was in reach stays diagnosable
      (ANNOTATION-API-SPEC §2).
    * ``extractor_version`` is deliberately **absent**: §1.2 gives it "present iff
      ``input_mode == 'extracted'``". What produced the IR is not lost by leaving it out — it is
      in the snapshot file's own envelope, which is the layer that records provenance.

    ``graph_version`` is not passed at all: :func:`~gebra.verify.verify` computes it from the
    IR rather than accepting it, which is what makes §6.2 obligation 2 a fact about the stored
    IR instead of a claim about the caller.

    Args:
        snapshot: The stored version to report on. Read it through
            :meth:`~gebra.store.store.SnapshotStore.read`, which checks its digest against its
            IR on the way (IR-SPEC §6.1 step 9) — that check is where obligation 2 comes from.
        strict: The PROPERTY-CATALOG-SPEC §0.2 strict-mode request in force, recorded verbatim
            in ``gate.strict``. Passed rather than fixed because the gate a stored version is
            audited under is a property of the audit, and a reader of the file has to be able
            to see which policy produced the exit code (§2.3).

    Returns:
        The :class:`~gebra.verify.RunReport` — all thirteen catalog outcomes in catalog order,
        markers where no validator ran, and the §2 gate.
    """
    reference = SubjectRef(
        source=snapshot.extracted_from.source,
        input_mode="snapshot",
        version=snapshot.version,
        sidecar=snapshot.extracted_from.sidecar_path,
    )
    return verify(snapshot.ir, RunPolicy(strict=strict, subject=reference))


def check_profile(report: RunReport, *, version: str, graph_version: str, path: Path) -> None:
    """Refuse ``report`` unless it is REPORT-FORMAT-SPEC §6's snapshot profile of ``version``.

    Four refusals for §6.2's three obligations, and the arithmetic is not a mistake.

    Obligation 3 ("``report_format`` is the same version as any other run report") is not a
    comparison this function can fail: the model types the member as a literal and
    :func:`~gebra.verify.verify` stamps :data:`~gebra.verify.REPORT_FORMAT`, so it is held by
    construction — and by ``tests/audit/test_export.py``, which reads the written document's
    own key set and asserts there is exactly one format line in it and it is that one.

    The extra refusal is the **tool-error** one, and it is the load-bearing part of this
    function rather than a belt-and-braces check. §6.2 says the document is "the same
    ``RunReport`` model of §1, with three additional obligations", and every one of the three
    is about *identity* — none of them is about whether a verdict was reached. But a
    ``dispatch``-stage tool error carries a full subject (:func:`gebra.verify.verify` builds it
    before dispatching), so an exit-2 run over a stored snapshot satisfies all three: right
    ``input_mode``, right label, right digest, and ``properties: []``. Writing that to
    ``reports/<version>.report.json`` would put a file that answered nothing where a reader
    looks for the audit record of a version — §2.4's "a half-populated list invites reading one
    anyway", one level up — and it is reachable from this module's own ``strict`` parameter,
    since §2.4's ``1.1`` amendment routes a promotion refusal to ``dispatch`` precisely so that
    the same IR does not raise under one policy and answer under another. So an exit-2 report
    is refused here, with ``error.detail`` carried into the message: the reason a stored version
    could not be audited is the one thing the caller needs, and it lives nowhere else.

    Args:
        report: The document to check.
        version: The V.S.F.E label the export is named for.
        graph_version: The stored snapshot's digest.
        path: The file the fault is about, for the error's ``path``.

    Raises:
        AuditError: ``no-verdict``, ``subject-missing``, ``input-mode``, ``version-mismatch``
            or ``digest-mismatch``.
    """
    if report.error is not None:
        raise AuditError(
            f"the run over {version!r} reached no verdict — {report.error.stage}: "
            f"{report.error.detail} — so there is nothing about that version to audit "
            "(§2.4: exit 2 is never a verification result)",
            reason=AuditErrorReason.NO_VERDICT,
            path=path,
        )
    subject = report.subject
    if subject is None:
        raise AuditError(
            "the run report carries no subject, so it names no stored version; §6's profile "
            "is a report *about* a snapshot and a subject-less report cannot be one",
            reason=AuditErrorReason.SUBJECT_MISSING,
            path=path,
        )
    if subject.input_mode != "snapshot":
        raise AuditError(
            f"the run report's input_mode is {subject.input_mode!r}; an audit export is a run "
            "report in the snapshot profile (§6.2 obligation 1)",
            reason=AuditErrorReason.INPUT_MODE,
            path=path,
        )
    if subject.version != version:
        raise AuditError(
            f"the run report is about version {subject.version!r} and the export is named for "
            f"{version!r}; §6.2 obligation 1 has the two equal",
            reason=AuditErrorReason.VERSION_MISMATCH,
            path=path,
        )
    if subject.graph_version != graph_version:
        raise AuditError(
            f"the run report carries {subject.graph_version} and the stored snapshot carries "
            f"{graph_version}; §6.2 obligation 2: a report whose digest disagrees with its "
            "snapshot is a corrupt store, not a stale report",
            reason=AuditErrorReason.DIGEST_MISMATCH,
            path=path,
        )


def export_version(
    store: SnapshotStore, version: str, *, strict: StrictPolicy = STRICT_OFF
) -> ExportOutcome:
    """Export one stored version to ``.gebra/reports/<version>.report.json``.

    Read (digest-verified) → verify → check the §6.2 profile → write atomically. The write is
    unconditional and overwrites: a report is *derived* from a snapshot and a validator set, so
    it is not append-only the way the snapshots themselves are, and re-exporting after a
    validator lands is how an audit trail stays current. Because the document carries no
    wall-clock field, re-exporting an unchanged version rewrites identical bytes.

    Args:
        store: The store holding the version.
        version: Its V.S.F.E label.
        strict: The §0.2 policy the audit is run under, per :func:`snapshot_report`.

    Returns:
        The :class:`~gebra.audit.models.ExportOutcome` — the label, the file, and the document.

    Raises:
        gebra.store.StoreError: if the version is not held, or the stored snapshot is not
            intact — one fault, the store's own vocabulary.
        AuditError: if the assembled document is not §6's profile, in which case nothing is
            written. ``no-verdict`` is the reachable one: a stored snapshot this build cannot
            reach a verdict over — a wedge validator unregistered, a validator crashing, a
            strict promotion its property refuses to name — is reported here rather than
            written down as an audit record that answers nothing.
        OSError: if the file cannot be written.
    """
    snapshot = store.read(version)
    report = snapshot_report(snapshot, strict=strict)
    path = store.report_path(snapshot.version)
    check_profile(report, version=snapshot.version, graph_version=snapshot.graph_version, path=path)
    store.initialize()
    write_atomic(path, render_native(report, for_file=True))
    return ExportOutcome(version=snapshot.version, path=path, report=report)


def export_store(
    store: SnapshotStore, *, strict: StrictPolicy = STRICT_OFF
) -> tuple[ExportOutcome, ...]:
    """Export **every** version the store holds, oldest first.

    The order is :meth:`~gebra.store.store.SnapshotStore.versions`' — the store's own append
    order — so a caller reading the results sequentially reads the history forwards.

    A store with no versions exports nothing and is not an error: an empty store is a
    consistent store, and there is nothing about it to audit.

    Raises:
        gebra.store.StoreError, AuditError, OSError: as :func:`export_version`, on the first
            version that cannot be exported. Nothing is rolled back — the exports that already
            landed are each complete and correct on their own.
    """
    return tuple(export_version(store, version, strict=strict) for version in store.versions())


def read_export(store: SnapshotStore, version: str) -> RunReport:
    """Read back the export for ``version``, validated as §6's profile.

    The document is parsed through the same :class:`~gebra.verify.RunReport` model the verify
    path emits — REPORT-FORMAT-SPEC §7's conformance obligation for this card, in terms — which
    is what makes reading an export a real check rather than a JSON load: every model in the
    chain is ``extra="forbid"`` and strict, so an unknown member or a retyped one is a refusal.
    The §6.2 obligations are then checked against the store's own index.

    The digest an export is checked against is the **index's** row for that version, not a
    freshly-read snapshot file: an export is validated against what the store records, and
    whether the snapshot file still hashes to that digest is
    :meth:`~gebra.store.store.SnapshotStore.check`'s separate question. That is
    :func:`gebra.lineage.lineage`'s reading of the same boundary, and it keeps a read of one
    file from silently becoming a read of two.

    Raises:
        AuditError: ``report-missing`` if nothing has been exported for that version;
            ``snapshot-missing`` if the index does not hold the version the export is named for,
            so there is nothing to validate it against; ``report-unreadable`` if the file is not
            a run report; the profile reasons if it is a run report about something else.
        gebra.store.StoreError: ``unsafe-version`` for a label that cannot be a file name, or
            ``meta-unreadable`` if the index cannot be read.
    """
    path = store.report_path(version)
    if not path.is_file():
        raise AuditError(
            f"the store holds no audit export at {path}",
            reason=AuditErrorReason.REPORT_MISSING,
            path=path,
        )
    record = store.read_meta().record_for(version)
    if record is None:
        raise AuditError(
            f"{path} is an export of version {version!r}, which the store's index does not "
            "hold; an export is validated against the store and this one has nothing to be "
            "validated against",
            reason=AuditErrorReason.SNAPSHOT_MISSING,
            path=path,
        )
    try:
        report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
    # One branch, not three: pydantic's `ValidationError`, a `json` decoding failure and bytes
    # that are not UTF-8 are all `ValueError`s, and all three mean the same thing here — the
    # file is not a run report. The store's own readers are spelled the same way.
    except ValueError as error:
        raise AuditError(
            f"{path} is not a readable run report: {error}",
            reason=AuditErrorReason.REPORT_UNREADABLE,
            path=path,
        ) from error
    check_profile(report, version=version, graph_version=record.graph_version, path=path)
    return report
