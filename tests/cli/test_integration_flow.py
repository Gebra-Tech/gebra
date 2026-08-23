"""The travel-booking flow through all five verbs, as child processes — card CLI-07.

Brief D-12's outline Definition of Done names this scenario: "All five subcommands run
end-to-end against the rewritten travel-booking tutorial workflow." This module is that run,
at the process boundary: one scenario directory, the SD-08 evolution sequence
(``tests/sample_workflows/travel_booking_evolution.py``) driven through the shipped CLI —
``verify`` over the live definition and over a stored version, ``snapshot`` recording the
six clean stages and refusing the FATAL one, ``diff`` over stored pairs and a mixed
stored-versus-live pair, ``history`` over the store the flow itself built, and ``display``
plain and overlaid with a report the flow's own ``verify`` wrote.

The expectations are SD-08's, never invented here: every recorded label is
``EVOLUTION[i].expected_version`` and every rendered movement is
``EVOLUTION[i].expected_bump`` — the CLI is held to *render* what the engines derive, which
is CLI-SPEC §0.1's presentation-only boundary observed end-to-end. Where output embeds
clock values (``history`` over a live-recorded store) the assertion is structural, or
byte-equality against the engine's own projection over the same store — never a golden with
a normalization CLI-SPEC §7 does not license ("goldens normalize ``tool.version`` and
nothing else").

Never-invokes posture (WA-07): the children resolve sentinel-guarded builders through the
``--call`` opt-in CLI-05's tripwire suite pins; a node body running in a child raises the
module's ``BaseException`` sentinel, crashing that child and failing the exit-code
assertions here loudly. In this process the fixture module is only imported (defining
callables and constants — its own stated import contract), and the autouse guard below
asserts the ledger stays empty on entry to and exit from every test, the way every
travel-booking-consuming suite does.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from gebra.lineage import dump_lineage, lineage
from gebra.store import SnapshotStore
from gebra.verify import RunReport
from gebra.versioning import Component
from tests.cli.goldens import compare_golden
from tests.cli.integration import ProcessResult, run_gebra
from tests.sample_workflows import travel_booking as tb
from tests.sample_workflows import travel_booking_evolution as evo
from tools.mermaid_check import mermaid_problems

#: The stored span after the flow records the six clean stages (SD-08's labels).
FIRST_LABEL = evo.EVOLUTION[0].expected_version
NEWEST_LABEL = evo.EVOLUTION[5].expected_version

#: Every store-touching invocation names the store relatively, so rendered paths (the
#: snapshot verb's `file` line, the history header) stay bare names and goldens byte-stable
#: wherever the scenario directory lands — the CLI-05 suites' own discipline.
STORE = ("--store", ".gebra")


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """The fixture modules are imported and read here, never run — entry and exit both."""
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


def reference(stage: evo.EvolutionStage) -> str:
    """The CLI-SPEC §2.2 rule-3 import reference for a stage's builder."""
    return f"{stage.build.__module__}:{stage.build.__qualname__}"


def moved_letters(stage: evo.EvolutionStage) -> str:
    """The stage's expected bump class as the S/F/E letters the CLI renders, label order."""
    return " ".join(
        component.name
        for component in (Component.S, Component.F, Component.E)
        if component in stage.expected_bump
    )


@dataclass(frozen=True)
class RecordedFlow:
    """The scenario directory after the recording spine ran, with each step's capture."""

    root: Path
    recordings: tuple[ProcessResult, ...]
    refusal: ProcessResult

    @property
    def store(self) -> SnapshotStore:
        return SnapshotStore.for_project(self.root)


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> RecordedFlow:
    """Record the sequence through the CLI, v1 first: six recordings, then the v7 refusal.

    Module-scoped so every test below reads one flow rather than re-running the spine; the
    captures are part of the fixture, so each test stays meaningful on its own under ``-k``.
    """
    root = tmp_path_factory.mktemp("travel-booking-flow")
    recordings = tuple(
        run_gebra("snapshot", "--import", reference(stage), "--call", *STORE, cwd=root)
        for stage in evo.EVOLUTION[:6]
    )
    refusal = run_gebra(
        "snapshot", "--import", reference(evo.EVOLUTION[6]), "--call", *STORE, cwd=root
    )
    return RecordedFlow(root=root, recordings=recordings, refusal=refusal)


# ── snapshot: the six clean stages record under SD-08's labels ────────────────────────────


def test_the_six_clean_stages_record_under_the_expected_labels(flow: RecordedFlow) -> None:
    """Each recording exits 0 with the SD-08 label and bump class in its rendering."""
    for index, (stage, result) in enumerate(zip(evo.EVOLUTION[:6], flow.recordings, strict=True)):
        assert result.exit_code == 0, stage.name
        assert result.stderr == "", stage.name
        assert f"recorded {stage.expected_version}" in result.stdout, stage.name
        if index == 0:
            assert "the store's first snapshot" in result.stdout
        else:
            assert f"previous                {evo.EVOLUTION[index - 1].expected_version}" in (
                result.stdout
            ), stage.name
            moved = next(
                line for line in result.stdout.splitlines() if line.strip().startswith("moved")
            )
            assert moved.split("moved", 1)[1].strip() == moved_letters(stage), stage.name

    assert flow.store.versions() == tuple(stage.expected_version for stage in evo.EVOLUTION[:6])
    assert flow.store.read_meta().current == NEWEST_LABEL


def test_the_first_and_a_multi_component_recording_match_their_goldens(
    flow: RecordedFlow,
) -> None:
    """Byte-level pins on two shapes: the first record, and the v3 S F bump."""
    compare_golden("integration/flow-snapshot-first.txt", flow.recordings[0].stdout)
    compare_golden("integration/flow-snapshot-bump.txt", flow.recordings[2].stdout)


def test_the_fatal_stage_is_refused_with_the_report_rendered(flow: RecordedFlow) -> None:
    """v7 (witness removed) is §0.2's refusal: exit 1, the FATAL findings legible, no write."""
    assert flow.refusal.exit_code == 1
    assert "cycle-without-termination-witness" in flow.refusal.stdout
    assert "not recorded" in flow.refusal.stderr
    assert "fatal" in flow.refusal.stderr.lower()
    compare_golden("integration/flow-snapshot-refused.txt", flow.refusal.stdout)

    # The refused stage left the store exactly as the six recordings built it.
    assert flow.store.versions() == tuple(stage.expected_version for stage in evo.EVOLUTION[:6])
    assert flow.store.read_meta().current == NEWEST_LABEL
    assert flow.store.check().ok


# ── verify: the live definition, and a stored version ─────────────────────────────────────


def test_verify_over_the_live_definition(flow: RecordedFlow) -> None:
    """The v1 builder through §2.2 detection and the §2.4 ``--call`` opt-in: gate pass."""
    target = reference(evo.EVOLUTION[0])
    human = run_gebra("verify", target, "--call", cwd=flow.root)
    assert human.exit_code == 0
    assert human.stderr == ""
    compare_golden("integration/flow-verify-live.txt", human.stdout)

    machine = run_gebra("verify", target, "--call", "--format", "json", cwd=flow.root)
    assert machine.exit_code == 0
    report = RunReport.model_validate_json(machine.stdout)
    assert report.gate.outcome == "pass"
    assert report.subject is not None
    assert report.subject.input_mode == "extracted"
    assert report.subject.source == target
    assert report.subject.extractor_version is not None


def test_verify_over_a_stored_version(flow: RecordedFlow) -> None:
    """The store the flow built serves ``--snapshot`` subjects with the §2.1 invariants."""
    human = run_gebra("verify", "--snapshot", NEWEST_LABEL, *STORE, cwd=flow.root)
    assert human.exit_code == 0
    assert human.stderr == ""
    compare_golden("integration/flow-verify-stored.txt", human.stdout)

    machine = run_gebra(
        "verify", "--snapshot", NEWEST_LABEL, *STORE, "--format", "json", cwd=flow.root
    )
    report = RunReport.model_validate_json(machine.stdout)
    assert report.subject is not None
    assert report.subject.input_mode == "snapshot"
    assert report.subject.version == NEWEST_LABEL


# ── diff: stored span, mixed stored-versus-live, and the difference signal ────────────────


def test_diff_across_the_stored_span_shows_the_union_class(flow: RecordedFlow) -> None:
    """v1..v6 moved S, F and E between them (SD-08: unions, nothing reverted): all three
    render, with the deferred-P-12 marker and no safe/breaking claim (its own suite's box,
    re-observed at the process boundary)."""
    result = run_gebra("diff", FIRST_LABEL, NEWEST_LABEL, *STORE, cwd=flow.root)
    assert result.exit_code == 0
    assert result.stderr == ""
    assert "not checked" in result.stdout
    compare_golden("integration/flow-diff-span.txt", result.stdout)


def test_diff_mixed_stored_and_live_derives_the_step_class(flow: RecordedFlow) -> None:
    """The stored v6 against the live v7 builder: the F-alone step SD-08 records for v7."""
    result = run_gebra(
        "diff", NEWEST_LABEL, reference(evo.EVOLUTION[6]), "--call", *STORE, cwd=flow.root
    )
    assert result.exit_code == 0
    compare_golden("integration/flow-diff-live.txt", result.stdout)


def test_the_exit_code_flag_is_a_difference_signal_only(flow: RecordedFlow) -> None:
    """§3.2's diff row at the process level: 0 without the flag, 1 with it when sides
    differ, 0 with it when nothing moved (the same stage rebuilt against its snapshot)."""
    differing = run_gebra("diff", FIRST_LABEL, NEWEST_LABEL, "--exit-code", *STORE, cwd=flow.root)
    assert differing.exit_code == 1

    same = run_gebra(
        "diff",
        NEWEST_LABEL,
        reference(evo.EVOLUTION[5]),
        "--call",
        "--exit-code",
        *STORE,
        cwd=flow.root,
    )
    assert same.exit_code == 0
    assert "not checked" in same.stdout  # the marker precedes the identical-pair return


# ── history: the store the flow built, listed ─────────────────────────────────────────────


def test_history_lists_the_recorded_sequence(flow: RecordedFlow) -> None:
    """Six rows oldest-first, the current pointer on the newest, each step's movement the
    SD-08 class. Timestamps come from the live clock, so the assertions are structural —
    CLI-SPEC §7 licenses normalizing ``tool.version`` and nothing else."""
    result = run_gebra("history", *STORE, cwd=flow.root)
    assert result.exit_code == 0
    assert result.stderr == ""

    assert f"6 versions; current {NEWEST_LABEL}" in result.stdout
    rows = [line for line in result.stdout.splitlines() if "sha256:" in line]
    assert len(rows) == 6
    for row, stage in zip(rows, evo.EVOLUTION[:6], strict=True):
        assert stage.expected_version in row, stage.name
    assert not rows[0].lstrip().startswith("*")
    assert rows[-1].lstrip().startswith("*"), "the newest row carries the current pointer"
    assert "n/a (oldest version)" in rows[0]
    for row, stage in zip(rows[1:], evo.EVOLUTION[1:6], strict=True):
        for letter in moved_letters(stage).split():
            assert f"+{letter}" in row, stage.name


def test_history_json_is_the_engine_projection_verbatim(flow: RecordedFlow) -> None:
    """``--format json`` over the flow's store equals ``dump_lineage`` over the same store,
    byte for byte — the engine's own projection, clock values included, no second schema."""
    result = run_gebra("history", "--format", "json", *STORE, cwd=flow.root)
    assert result.exit_code == 0
    assert result.stdout == dump_lineage(lineage(flow.store))


# ── display: the stored definition, plain and overlaid with the flow's own report ─────────


def test_display_renders_the_stored_definition(flow: RecordedFlow) -> None:
    """The stored v6 as Mermaid on stdout, parse-checked against the style guide's checker."""
    result = run_gebra("display", "--snapshot", NEWEST_LABEL, *STORE, cwd=flow.root)
    assert result.exit_code == 0
    assert result.stderr == ""
    assert mermaid_problems(result.stdout) == []
    compare_golden("integration/flow-display-plain.mmd", result.stdout)


def test_display_overlays_the_report_the_flow_wrote(flow: RecordedFlow) -> None:
    """verify ``--format json -o`` hands its artifact to ``display --report``: the §4.4
    pairing checks pass because the report names the displayed graph's own digest."""
    written = run_gebra(
        "verify",
        "--snapshot",
        NEWEST_LABEL,
        *STORE,
        "--format",
        "json",
        "-o",
        "report.json",
        cwd=flow.root,
    )
    assert written.exit_code == 0
    report = RunReport.model_validate_json((flow.root / "report.json").read_text("utf-8"))
    assert report.gate.outcome == "pass"

    overlaid = run_gebra(
        "display", "--snapshot", NEWEST_LABEL, *STORE, "--report", "report.json", cwd=flow.root
    )
    assert overlaid.exit_code == 0
    assert mermaid_problems(overlaid.stdout) == []
    compare_golden("integration/flow-display-overlaid.mmd", overlaid.stdout)


def test_history_windows_pass_through_over_the_flow_store(flow: RecordedFlow) -> None:
    """One window over the live store: the engine's own window arguments, unchanged."""
    result = run_gebra(
        "history",
        "--since",
        evo.EVOLUTION[3].expected_version,
        "--limit",
        "2",
        *STORE,
        cwd=flow.root,
    )
    assert result.exit_code == 0
    assert evo.EVOLUTION[4].expected_version in result.stdout
    assert evo.EVOLUTION[5].expected_version in result.stdout
    assert evo.EVOLUTION[1].expected_version not in result.stdout
    assert "showing 2 of 6" in result.stdout


def test_two_flow_reports_agree_on_the_definition(flow: RecordedFlow) -> None:
    """The live v6 builder and the stored v6 speak the same digest — extraction, the store
    and the loaders one chain: the report verify wrote for the stored subject names the
    graph_version the recording rendered at snapshot time."""
    recorded = flow.recordings[5].stdout
    digest_line = next(
        line for line in recorded.splitlines() if line.strip().startswith("graph_version")
    )
    prefix = digest_line.split("graph_version", 1)[1].strip().rstrip(".")
    machine = run_gebra(
        "verify", "--snapshot", NEWEST_LABEL, *STORE, "--format", "json", cwd=flow.root
    )
    report = RunReport.model_validate_json(machine.stdout)
    assert report.subject is not None
    assert report.subject.graph_version is not None
    assert report.subject.graph_version.startswith(prefix)

    parsed = json.loads(machine.stdout)
    assert parsed["subject"]["version"] == NEWEST_LABEL
