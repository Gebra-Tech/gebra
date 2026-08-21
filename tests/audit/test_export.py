"""The audit export — SD-07 acceptance box 1, over every version of two whole stores.

The box reads "export validates against REPORT-FORMAT-SPEC §6's snapshot profile **for every
stored version**", so the subject here is a *store*, not a snapshot:
:func:`tests.lineage.stores.evolved_store` carries one workflow through five versions in which
each of S, F and E moves at least once, and :func:`tests.lineage.stores.awkward_store` is the
totality case — a label outside the V.S.F.E grammar (``draft``, which PD-012 still permits as a
file base name), a history that counts down, and two versions carrying one digest. Every
version of both is exported, and every export is read back **through the same
:class:`~gebra.verify.RunReport` model the verify path emits** (REPORT-FORMAT-SPEC §7's
conformance obligation for this card) before the §6.2 obligations are checked against the
store's own index.

The real agent's export is ``tests/audit/test_travel_booking.py``'s; this file is hand-built IR
models throughout (WA-07): no extractor, no substrate, nothing in reach to invoke.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

import gebra.audit.export as export_module
from gebra.audit import (
    AuditError,
    AuditErrorReason,
    check_profile,
    export_store,
    export_version,
    read_export,
    snapshot_report,
)
from gebra.report.native import render_native
from gebra.store import REPORT_SUFFIX, SnapshotStore, StoreError
from gebra.verify import (
    PROPERTY_SLUGS,
    REPORT_FORMAT,
    STRICT_ALL,
    STRICT_OFF,
    WEDGE_SLUGS,
    GateOutcome,
    NotImplementedMarker,
    RunReport,
    SeverityCounts,
    Subject,
    Tool,
    ToolError,
    to_data,
)
from tests.lineage.stores import awkward_store, evolved_labels, evolved_store

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def evolved(tmp_path: Path) -> SnapshotStore:
    """The five-version store — the ordinary multi-version history."""
    return evolved_store(tmp_path / "evolved")


@pytest.fixture
def awkward(tmp_path: Path) -> SnapshotStore:
    """The store whose labels and history the engines have to stay total over."""
    return awkward_store(tmp_path / "awkward")


def _stores(evolved: SnapshotStore, awkward: SnapshotStore) -> tuple[SnapshotStore, ...]:
    return (evolved, awkward)


# ── Box 1: every stored version exports the §6 snapshot profile ──────────────────────────


def test_every_stored_version_exports_the_snapshot_profile(
    evolved: SnapshotStore, awkward: SnapshotStore
) -> None:
    """Acceptance box 1, over both stores and every version in them.

    Each of the §6.2 obligations is asserted against a source outside the export: the version
    against the *file name* it landed under, the digest against the **store's index row** and
    against the stored snapshot itself, and the format against
    :data:`gebra.verify.REPORT_FORMAT`. An export that agreed only with itself would pass a
    weaker test than this one.
    """
    for store in _stores(evolved, awkward):
        versions = store.versions()
        assert versions, "a store with no versions proves nothing about every version"
        outcomes = export_store(store)

        assert tuple(outcome.version for outcome in outcomes) == versions
        for outcome in outcomes:
            snapshot = store.read(outcome.version)
            record = store.read_meta().record_for(outcome.version)
            assert record is not None

            # The path is PD-012's, computed by the store rather than restated here.
            assert outcome.path == store.report_path(outcome.version)
            assert outcome.path.name == f"{outcome.version}{REPORT_SUFFIX}"
            assert outcome.path.is_file()

            # Read back through the model the verify path emits — §7's obligation — and then
            # check the profile against the store, which is what `read_export` does.
            document = read_export(store, outcome.version)
            assert document == outcome.report

            subject = document.subject
            assert subject is not None
            assert subject.input_mode == "snapshot"  # obligation 1
            assert subject.version == outcome.version
            assert subject.version == outcome.path.name.removesuffix(REPORT_SUFFIX)
            assert subject.graph_version == snapshot.graph_version  # obligation 2
            assert subject.graph_version == record.graph_version
            assert document.report_format == REPORT_FORMAT  # obligation 3
            assert document.properties  # a verdict run, not a tool error


def test_the_export_carries_all_thirteen_outcomes_in_catalog_order(
    evolved: SnapshotStore, awkward: SnapshotStore
) -> None:
    """§1.4 rule 1 reaching the audit artifact: thirteen, in order, markers included.

    The eight properties SOW §8 defers appear as the property registry's own structured
    :class:`~gebra.verify.NotImplementedMarker` — never as a pass and never as an omission —
    which is what PD-006 R3.4 asks an audit report to carry.
    """
    for store in _stores(evolved, awkward):
        for outcome in export_store(store):
            report = outcome.report
            assert tuple(entry.property for entry in report.properties) == PROPERTY_SLUGS
            deferred = tuple(
                entry.property
                for entry in report.properties
                if isinstance(entry, NotImplementedMarker)
            )
            assert deferred == tuple(slug for slug in PROPERTY_SLUGS if slug not in WEDGE_SLUGS)
            assert "evolution-safety" in deferred


def test_the_export_is_the_serialized_run_report_and_nothing_around_it(
    evolved: SnapshotStore,
) -> None:
    """The file's bytes are §1.5's profile applied to the report — no wrapper, no envelope."""
    for outcome in export_store(evolved):
        assert outcome.path.read_text(encoding="utf-8") == render_native(
            outcome.report, for_file=True
        )
        assert outcome.path.read_text(encoding="utf-8").endswith("}\n")
        assert "\r" not in outcome.path.read_text(encoding="utf-8")
        assert json.loads(outcome.path.read_text(encoding="utf-8")) == to_data(outcome.report)


def test_the_export_carries_exactly_one_version_line_and_it_is_the_run_reports(
    evolved: SnapshotStore,
) -> None:
    """ "SD-07 … carries no second version line" (§6.3), read off the document rather than argued.

    Every member name anywhere in the written document that carries "version" or "format" is
    swept and accounted for by name. Exactly one is a *schema* line — ``report_format``, the run
    report's own — and the other four are identities the document is required to carry: the IR
    format, the subject's content digest, its V.S.F.E label, and the build that produced it
    (§1.6: "the pairing a consumer cares about rides the document itself"). A second schema line
    under any of the obvious spellings would fail here whatever its nesting level.
    """
    outcome = export_store(evolved)[0]
    data = json.loads(outcome.path.read_text(encoding="utf-8"))

    assert data["report_format"] == REPORT_FORMAT
    assert data["subject"]["ir_version"] == "1.0"
    assert data["tool"]["version"]

    version_members = sorted(_paths_matching(data, lambda key: "version" in key or "format" in key))
    assert version_members == [
        "report_format",  # the one schema line
        "subject.graph_version",  # the IR-SPEC §6 content digest
        "subject.ir_version",  # which IR the subject is
        "subject.version",  # the V.S.F.E label — §6.2 obligation 1
        "tool.version",  # which build produced it
    ]
    for banned in ("schema_version", "export_version", "audit_version", "export_format"):
        assert not _paths_matching(data, lambda key, banned=banned: key == banned)


def test_the_export_carries_no_wall_clock_field(evolved: SnapshotStore) -> None:
    """§1.3: "no wall-clock field exists anywhere in the run report", and §6.2 keeps it out of
    the audit profile too — the dating rides the snapshot's own ``extracted_from.extracted_at``,
    which is in the file the export is named for. Swept by member name over the whole document
    on every stored version, so a timestamp added at any nesting level fails here."""
    for outcome in export_store(evolved):
        data = json.loads(outcome.path.read_text(encoding="utf-8"))
        clocks = _paths_matching(
            data,
            lambda key: any(
                word in key for word in ("_at", "time", "timestamp", "date", "clock", "duration")
            ),
        )
        assert clocks == []


def test_exporting_the_same_version_twice_writes_identical_bytes(evolved: SnapshotStore) -> None:
    """The reproducibility §1.3 says the audit export depends on, observed as bytes.

    Re-exporting is how an audit trail stays current after a validator lands, so it has to be a
    safe act: with no wall-clock field in the document, the second write is the first write.
    """
    first = {outcome.version: outcome.path.read_bytes() for outcome in export_store(evolved)}
    second = {outcome.version: outcome.path.read_bytes() for outcome in export_store(evolved)}

    assert first == second


def test_the_subject_is_read_off_the_snapshots_own_envelope(evolved: SnapshotStore) -> None:
    """§1.3's snapshot bullet: ``source`` is the *store's* provenance field, and
    ``extractor_version`` — "present iff ``input_mode == 'extracted'``" — is absent."""
    for outcome in export_store(evolved):
        snapshot = evolved.read(outcome.version)
        subject = outcome.report.subject
        assert subject is not None
        assert subject.source == snapshot.extracted_from.source
        assert subject.extractor_version is None
        assert subject.sidecar == snapshot.extracted_from.sidecar_path
        assert "extractor_version" not in to_data(subject)


def test_the_strict_policy_in_force_is_recorded_in_the_gate(evolved: SnapshotStore) -> None:
    """§2.3: "the policy in force is recorded verbatim in ``gate.strict``, so a reader of the
    report knows which gate produced the code". An audit read a year later has no other way to
    know it."""
    default = export_version(evolved, evolved.versions()[0])
    strict = export_version(evolved, evolved.versions()[0], strict=STRICT_ALL)

    assert default.report.gate.strict == STRICT_OFF
    assert strict.report.gate.strict == STRICT_ALL
    assert strict.path.read_bytes() == strict.path.read_bytes()


def test_an_empty_store_exports_nothing_and_is_not_an_error(tmp_path: Path) -> None:
    """An empty store is a consistent store: there is nothing about it to audit."""
    store = SnapshotStore.for_project(tmp_path)

    assert export_store(store) == ()
    assert not store.reports_dir.exists()


def test_export_version_refuses_a_version_the_store_does_not_hold(evolved: SnapshotStore) -> None:
    """One fault, the store's own vocabulary — this package does not re-code the store's."""
    with pytest.raises(StoreError) as caught:
        export_version(evolved, "9.9.9.9")

    assert caught.value.reason.value == "snapshot-missing"


# ── The profile check itself ─────────────────────────────────────────────────────────────


def _tool_error_report(subject: Subject | None = None) -> RunReport:
    """A §2.4 tool-error run — exit 2, no outcomes — in either of its two real shapes.

    The default is the **subject-less** one, whose stage is ``ir-validation`` and not
    ``dispatch``: :func:`gebra.verify.verify` establishes the subject *before* dispatching, so
    the only stages that can reach a subject-less report are ``input`` and ``ir-validation``
    (`gebra/verify/run.py`'s two ``subject=None`` call sites). Pairing ``dispatch`` with
    ``subject=None`` would build a document the verify path never produces — and would let the
    profile check look tested against a shape that cannot occur while the shape that *can*
    slipped past, which is exactly the defect this pairing hides. Pass a subject for the
    ``dispatch`` shape, which is the reachable one.
    """
    return RunReport(
        report_format=REPORT_FORMAT,
        tool=Tool(name="gebra", version="0.0.0"),
        subject=subject,
        properties=(),
        gate=GateOutcome(
            exit_code=2,
            outcome="tool-error",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=STRICT_OFF,
            snapshot_eligible=False,
        ),
        error=ToolError(
            stage="dispatch" if subject is not None else "ir-validation",
            detail="no validator is registered for graph-well-formed"
            if subject is not None
            else "the document declares ir_version '1.1'",
        ),
    )


def _snapshot_subject(store: SnapshotStore, version: str) -> Subject:
    """The subject ``verify()`` builds for a stored snapshot — all three obligations satisfied."""
    snapshot = store.read(version)
    return Subject(
        input_mode="snapshot",
        source=snapshot.extracted_from.source,
        ir_version="1.0",
        graph_version=snapshot.graph_version,
        version=snapshot.version,
    )


def test_a_run_that_reached_no_verdict_is_not_the_profile(evolved: SnapshotStore) -> None:
    """The refusal that §6.2's three obligations do not make, and the one that matters.

    A ``dispatch``-stage tool error carries a **full** subject — ``verify()`` builds it before
    dispatching — so it satisfies every one of §6.2's obligations: right ``input_mode``, right
    label, right digest. What it does not carry is an answer. §2.4: "exit 2 is 'no verdict', and
    a half-populated list invites reading one anyway"; a file at the audit path is read as *the*
    record of a stored version, so writing an outcome-less one there is that same failure a
    level up.
    """
    label = evolved.versions()[0]
    report = _tool_error_report(_snapshot_subject(evolved, label))
    assert report.subject is not None
    assert report.subject.input_mode == "snapshot"
    assert report.subject.version == label
    assert report.subject.graph_version == evolved.read(label).graph_version

    with pytest.raises(AuditError) as caught:
        check_profile(
            report,
            version=label,
            graph_version=evolved.read(label).graph_version,
            path=evolved.report_path(label),
        )

    assert caught.value.reason is AuditErrorReason.NO_VERDICT
    # `error.detail` is carried into the message: why a stored version could not be audited
    # lives nowhere else, and the identity refusals above it would report the wrong cause.
    assert "no validator is registered for graph-well-formed" in str(caught.value)


def test_a_subject_less_report_is_not_the_profile_either(tmp_path: Path) -> None:
    """§6's profile is a report *about* a snapshot; one that names none cannot be one.

    Reachable through an ``ir-validation`` stage error — a stored snapshot declaring an
    ``ir_version`` this build's validators are not defined over. The ``no-verdict`` refusal
    catches it first, which is why this test calls the subject check directly by handing in a
    report with no ``error``… it cannot: ``RunReport`` enforces "``error`` present iff exit 2".
    So the two refusals are ordered, and this asserts the order rather than pretending
    otherwise: the *cause* is what a reader needs, and "no verdict — ir-validation: …" is the
    cause, while "no subject" is its consequence.
    """
    with pytest.raises(AuditError) as caught:
        check_profile(
            _tool_error_report(), version="1.0.0.0", graph_version="sha256:0", path=tmp_path / "r"
        )

    assert caught.value.reason is AuditErrorReason.NO_VERDICT
    assert "ir_version '1.1'" in str(caught.value)


def test_the_subject_refusal_stands_on_its_own(tmp_path: Path) -> None:
    """`subject-missing` is not dead code behind the `no-verdict` refusal.

    ``RunReport`` makes ``error`` present iff exit 2 and ``subject`` absent only on a tool-error
    run, so no *document* can reach the subject check with no subject — but ``check_profile`` is
    public and takes a report from wherever the caller got it, and a model whose invariants
    changed would silently fall through to `input_mode` on a ``None``. Constructed here by
    bypassing the wrapper's validator on a value the models still accept member-wise.
    """
    report = _tool_error_report().model_copy(update={"error": None, "subject": None})

    with pytest.raises(AuditError) as caught:
        check_profile(report, version="1.0.0.0", graph_version="sha256:0", path=tmp_path / "r")

    assert caught.value.reason is AuditErrorReason.SUBJECT_MISSING


def test_a_report_over_a_live_target_is_not_the_profile(evolved: SnapshotStore) -> None:
    """Obligation 1: a ``verify`` run over an IR document is a run report and not an export."""
    from gebra.verify import verify

    snapshot = evolved.read(evolved.versions()[0])
    report = verify(snapshot.ir)  # no policy: `input_mode` defaults to `ir-document`

    with pytest.raises(AuditError) as caught:
        check_profile(
            report,
            version=snapshot.version,
            graph_version=snapshot.graph_version,
            path=evolved.report_path(snapshot.version),
        )

    assert caught.value.reason is AuditErrorReason.INPUT_MODE


def test_a_report_about_another_version_is_refused(evolved: SnapshotStore) -> None:
    """Obligation 1's equality: the label in the document and the label in the file name."""
    labels = evolved.versions()
    report = snapshot_report(evolved.read(labels[0]))

    with pytest.raises(AuditError) as caught:
        check_profile(
            report,
            version=labels[1],
            graph_version=evolved.read(labels[0]).graph_version,
            path=evolved.report_path(labels[1]),
        )

    assert caught.value.reason is AuditErrorReason.VERSION_MISMATCH


def test_a_report_whose_digest_is_not_the_snapshots_is_refused(evolved: SnapshotStore) -> None:
    """Obligation 2, in §6.2's own words: "a report whose digest disagrees with its snapshot is
    a corrupt store, not a stale report"."""
    label = evolved.versions()[0]
    report = snapshot_report(evolved.read(label))

    with pytest.raises(AuditError) as caught:
        check_profile(
            report,
            version=label,
            graph_version="sha256:" + "0" * 64,
            path=evolved.report_path(label),
        )

    assert caught.value.reason is AuditErrorReason.DIGEST_MISMATCH


def test_nothing_is_written_when_the_document_is_not_the_profile(
    evolved: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check runs *before* the write, so a non-conforming document never lands on disk.

    Held by substituting the assembly step rather than by reading the source: a build in which
    the two were the other way round would leave the file behind, and this test would see it.
    The substituted document is the **reachable** non-conforming one — a ``dispatch`` tool error
    over this very snapshot, which satisfies all three §6.2 obligations and answers nothing.
    """
    label = evolved.versions()[0]
    subject = _snapshot_subject(evolved, label)
    monkeypatch.setattr(
        export_module, "snapshot_report", lambda *a, **k: _tool_error_report(subject)
    )

    with pytest.raises(AuditError) as caught:
        export_version(evolved, label)

    assert caught.value.reason is AuditErrorReason.NO_VERDICT
    assert not evolved.report_path(label).exists()
    # The whole directory, not only that one path: nothing was written under any name, and no
    # temp file was left behind by an interrupted atomic write.
    assert list(evolved.reports_dir.iterdir()) == []


# ── Reading an export back ───────────────────────────────────────────────────────────────


def test_reading_an_export_that_was_never_written(evolved: SnapshotStore) -> None:
    with pytest.raises(AuditError) as caught:
        read_export(evolved, evolved.versions()[0])

    assert caught.value.reason is AuditErrorReason.REPORT_MISSING


def test_reading_an_export_of_a_version_the_index_does_not_hold(evolved: SnapshotStore) -> None:
    """An orphan export — the store's own ``check()`` reports orphan *snapshots* for the same
    reason. There is nothing to validate it against, and validating it against nothing would be
    the one thing a profile check must not do."""
    label = evolved.versions()[0]
    outcome = export_version(evolved, label)
    orphan = evolved.report_path("7.7.7.7")
    orphan.write_bytes(outcome.path.read_bytes())

    with pytest.raises(AuditError) as caught:
        read_export(evolved, "7.7.7.7")

    assert caught.value.reason is AuditErrorReason.SNAPSHOT_MISSING


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("{ not json", id="not-json"),
        pytest.param('{"report_format": "1.1"}', id="missing-members"),
        pytest.param('{"report_format": "1.1", "unknown": 1}', id="unknown-member"),
    ],
)
def test_reading_a_file_that_is_not_a_run_report(evolved: SnapshotStore, content: str) -> None:
    """Every model in the chain is ``extra="forbid"`` and strict, so reading an export is a
    real check rather than a JSON load."""
    label = evolved.versions()[0]
    evolved.initialize()
    evolved.report_path(label).write_text(content, encoding="utf-8")

    with pytest.raises(AuditError) as caught:
        read_export(evolved, label)

    assert caught.value.reason is AuditErrorReason.REPORT_UNREADABLE


def test_reading_an_export_that_is_a_report_about_something_else(evolved: SnapshotStore) -> None:
    """The profile reasons reach the reader too: a well-formed run report filed under the wrong
    label is refused rather than returned."""
    labels = evolved.versions()
    first = export_version(evolved, labels[0])
    evolved.report_path(labels[1]).write_bytes(first.path.read_bytes())

    with pytest.raises(AuditError) as caught:
        read_export(evolved, labels[1])

    assert caught.value.reason is AuditErrorReason.VERSION_MISMATCH


# ── Surface ──────────────────────────────────────────────────────────────────────────────


def test_the_packages_public_surface_is_what_it_exports() -> None:
    import gebra.audit as package

    assert set(package.__all__) <= set(dir(package))
    assert "AuditError" in package.__all__
    assert evolved_labels()  # the shared fixture is the one this file's stores are built from


def _paths_matching(data: object, predicate: Any, *, prefix: str = "") -> list[str]:
    """Every dotted member path in ``data`` whose leaf key satisfies ``predicate``."""
    found: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if predicate(str(key)):
                found.append(path)
            found.extend(_paths_matching(value, predicate, prefix=path))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            found.extend(_paths_matching(value, predicate, prefix=f"{prefix}[{index}]"))
    return found
