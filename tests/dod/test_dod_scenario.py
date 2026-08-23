"""The DoD scenario's six legs, asserted over the one store the conftest built.

PD-006 R5 names the scenario — extract → verify → snapshot → evolve → diff → report over
the travel-booking agent, the five defect variants plus the R4 evolution sequence — and
this module holds each leg to what the checklist says it produces: the healthy agent clean
end to end, the sequence recorded under the recorded labels through the measured
eligibility boundary, the store-derived diffs deriving the recorded classes with the
deferred-P-12 marker, a conforming audit export for every stored version (thirteen
properties, eight structured not-implemented markers — R3.4), the PD-047 lineage document
sitting beside the reports, and the freshness check green at the final version. The catches
themselves are ``test_dod_defects.py``'s; the wedge-five plugin run is
``test_dod_plugin.py``'s; WA-07 is ``test_dod_guard.py``'s.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gebra.audit import export_store, read_export
from gebra.lineage import dump_lineage, lineage, lineage_document
from gebra.snapshot import SnapshotAction, SnapshotErrorReason
from gebra.verify import NotImplementedMarker, PropertyReport
from gebra.versioning import Component
from tests.sample_workflows import travel_booking_evolution as evo

from .conftest import LEGS, LINEAGE_EXPORT_NAME

if TYPE_CHECKING:
    from gebra.verify import RunReport

    from .conftest import DodScenario


def _thirteen_with_eight_markers(report: RunReport) -> None:
    """R3.4's run-level shape: all thirteen properties, the eight non-wedge as markers."""
    assert len(report.properties) == 13
    markers = [o for o in report.properties if isinstance(o, NotImplementedMarker)]
    reports = [o for o in report.properties if isinstance(o, PropertyReport)]
    assert len(markers) == 8 and len(reports) == 5
    assert all(marker.kind == "not-implemented" for marker in markers)


# ── extract + verify: the healthy agent, clean end to end ────────────────────────────────


def test_the_healthy_agent_verifies_clean(dod: DodScenario) -> None:
    """C1's opening sentence, API side: v1 extracts warning-free and passes the wedge five
    with exit 0, snapshot-eligible, thirteen properties listed."""
    assert dod.stage_envelopes[0].warnings == ()
    report = dod.stage_reports[0]
    assert report.gate.exit_code == 0 and report.gate.outcome == "pass"
    assert report.gate.snapshot_eligible
    _thirteen_with_eight_markers(report)
    for outcome in report.properties:
        if isinstance(outcome, PropertyReport):
            assert outcome.result == "pass", outcome.property


# ── snapshot + evolve: the sequence lands under the recorded labels ──────────────────────


def test_the_sequence_records_under_the_recorded_labels(dod: DodScenario) -> None:
    """Eight recordings, each at its recorded label with its recorded bump class."""
    for stage, outcome in zip(evo.EVOLUTION, dod.outcomes, strict=True):
        assert outcome.action is SnapshotAction.RECORDED, stage.name
        assert outcome.version == stage.expected_version, stage.name
        assert outcome.bump_class == stage.expected_bump, stage.name
    assert dod.store.versions() == tuple(s.expected_version for s in evo.EVOLUTION)
    assert dod.store.read_meta().current == evo.EVOLUTION[-1].expected_version
    assert dod.store.check().ok


def test_the_evolve_leg_applies_the_eligibility_boundary(dod: DodScenario) -> None:
    """SD-08's measured boundary, wired the way the scenario must wire it.

    v1–v6 went through the gate — recorded **with** their eligibility reports, so the
    digest each gate saw is the digest stored. v7–v8, offered with their FATAL-bearing
    reports, were refused with the engine's own reason; they landed only handed-none,
    which is the documented posture PD-006 R4's "snapshotted and re-verified" rides on.
    """
    refused = {name for name in dod.refusals}
    assert refused == {"v7-witness-removed", "v8-billable-confirmation"}
    for reason in dod.refusals.values():
        assert reason is SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE
    for index, report in enumerate(dod.stage_reports):
        assert report.gate.snapshot_eligible == (index < 6), evo.EVOLUTION[index].name


# ── diff: the store's own files derive the recorded classes ──────────────────────────────


def test_the_diff_leg_derives_the_recorded_classes(dod: DodScenario) -> None:
    """Every consecutive pair, re-read from disk: the recorded class, the deferred-P-12
    marker, and no safe/breaking slot anywhere a verdict could hide."""
    assert len(dod.pair_diffs) == len(evo.EVOLUTION) - 1
    for stage, diff in zip(evo.EVOLUTION[1:], dod.pair_diffs, strict=True):
        assert diff.bump_class == stage.expected_bump, stage.name
        assert diff.evolution_safety.kind == "not-implemented", stage.name
        assert diff.evolution_safety.property == "evolution-safety", stage.name
        assert diff.has_changes and not diff.identical, stage.name


def test_the_lineage_agrees_with_the_recorded_expectations(dod: DodScenario) -> None:
    """The label arithmetic tells the same story the table records, step for step."""
    assert dod.listing.total == len(evo.EVOLUTION)
    for entry, stage in zip(dod.listing.entries[1:], evo.EVOLUTION[1:], strict=True):
        assert entry.step is not None, stage.name
        expected = tuple(
            component
            for component in (Component.V, Component.S, Component.F, Component.E)
            if component in stage.expected_bump
        )
        assert entry.step.bump_class == expected, stage.name
        assert entry.step.content_changed, stage.name


# ── report: a conforming audit export per version, the lineage document beside them ───────


def test_every_stored_version_has_a_conforming_export(dod: DodScenario) -> None:
    """One report per version at the PD-012 path, each the §6 snapshot profile: the label
    equals the file name and the subject, the digest equals the store's, thirteen
    properties with the eight markers (R3.4), and ``read_export`` reloads it equal."""
    assert tuple(outcome.version for outcome in dod.exports) == dod.store.versions()
    for outcome in dod.exports:
        assert outcome.path == dod.store.report_path(outcome.version)
        assert outcome.path.is_file()
        report = outcome.report
        assert report.subject is not None
        assert report.subject.input_mode == "snapshot"
        assert report.subject.version == outcome.version
        snapshot = dod.store.read(outcome.version)
        assert report.subject.graph_version == snapshot.graph_version
        _thirteen_with_eight_markers(report)
        assert read_export(dod.store, outcome.version) == report


def test_the_exports_reverify_every_version_at_the_recorded_boundary(
    dod: DodScenario,
) -> None:
    """R4's "re-verified", from the store's own files: v1–v6 export exit 0; v7–v8 export
    exit 1 carrying the FATAL ``cycle-without-termination-witness`` — the audit trail says
    exactly what the evolution seeded."""
    for stage, outcome in zip(evo.EVOLUTION, dod.exports, strict=True):
        gate = outcome.report.gate
        if stage.name in dod.refusals:
            assert gate.exit_code == 1 and gate.counts.fatal >= 1, stage.name
            p02 = outcome.report.outcome_for("termination-witness")
            assert isinstance(p02, PropertyReport) and p02.failure is not None
            assert p02.failure.property_condition == "cycle-without-termination-witness"
        else:
            assert gate.exit_code == 0, stage.name


def test_re_exporting_writes_byte_identical_reports(dod: DodScenario) -> None:
    """The report leg is a pure function of the store: run it again, get the same bytes."""
    before = {outcome.path: outcome.path.read_bytes() for outcome in dod.exports}
    for outcome in export_store(dod.store):
        assert outcome.path.read_bytes() == before[outcome.path]


def test_the_lineage_document_sits_beside_the_reports(dod: DodScenario) -> None:
    """The PD-047 mitigation, executed and pinned: a lineage document in
    ``.gebra/reports/`` beside the per-version reports, in ``dump_lineage``'s own
    version-locked vocabulary, byte-stable, so the audit files answer "what changed"
    without a ``gebra`` installation."""
    assert dod.lineage_path.name == LINEAGE_EXPORT_NAME
    assert dod.lineage_path.parent == dod.exports[0].path.parent
    text = dod.lineage_path.read_text(encoding="utf-8")
    assert text == dod.lineage_text
    assert text == dump_lineage(lineage(dod.store))
    assert text.endswith("\n") and "\r" not in text

    document = json.loads(text)
    assert document == lineage_document(dod.listing)
    assert document["lineage_version"] == "1.0"
    assert [entry["version"] for entry in document["entries"]] == [
        stage.expected_version for stage in evo.EVOLUTION
    ]
    steps = [entry["step"]["bump_class"] for entry in document["entries"][1:]]
    assert steps == [
        [
            c.value
            for c in (Component.V, Component.S, Component.F, Component.E)
            if c in stage.expected_bump
        ]
        for stage in evo.EVOLUTION[1:]
    ]


def test_the_freshness_check_is_green_at_the_final_version(dod: DodScenario) -> None:
    """The CI-check surface, inside the scenario: the final working definition matches the
    store's current, so the gate that fails on drift has nothing to say."""
    assert dod.freshness_outcome.fresh
    assert dod.freshness_outcome.version == evo.EVOLUTION[-1].expected_version


# ── the sub-metric: the legs were measured ────────────────────────────────────────────────


def test_the_scenario_timed_every_leg(dod: DodScenario) -> None:
    """The R5 sub-metric has a value for each of the six legs — non-gating by ruling, so
    nothing here asserts a duration, only that the measurement exists to report."""
    for leg in LEGS:
        assert leg in dod.timings, leg
        assert dod.timings[leg] >= 0.0
