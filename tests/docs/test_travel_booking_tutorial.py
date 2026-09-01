"""``docs/tutorials/travel-booking-end-to-end.md`` pinned to the scenario it narrates (DOC-16).

The flagship tutorial's claim is structural: it tells the acceptance scenario's story —
extract → verify → snapshot → evolve → diff → report — over the SAME assets the DoD CI job
runs, so the page and the scenario cannot drift apart. This module is that claim held by
machine, in both halves:

* **same assets** — no example on the page constructs a graph of its own, and the set of
  ``tests.sample_workflows`` modules the page's examples import is exactly the set
  ``tests/dod/conftest.py`` imports;
* **same facts** — every defect catch is re-derived from a fresh verify run and compared
  against the recorded ``DEFECTS`` expectations, the evolution rows against ``EVOLUTION``,
  the four breaking-case diffs byte for byte against the verb, the recorder's refusals
  against its own reason vocabulary, the summary example's leg order against the DoD
  harness's ``LEGS``, and the CI-job facts against the workflow's own constants.

The module builds stores from the sentinel-guarded travel-booking fixtures, whose bodies
record into the shared ledger and raise if anything calls them; every test asserts that
ledger empty on entry and exit, so a run in which a node executed could not report these
results (WA-07).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pytest

import gebra
from gebra.audit import export_store, freshness
from gebra.cli import main
from gebra.diff import EVOLUTION_SAFETY_DEFERRED
from gebra.lineage import compare, dump_lineage, lineage
from gebra.snapshot import SnapshotError, SnapshotErrorReason, record, snapshot
from gebra.store import REPORT_SUFFIX, SnapshotStore
from gebra.verify import (
    PropertyReport,
    RunPolicy,
    RunReport,
    StrictPolicy,
    property_for_condition,
    verify,
)
from gebra.verify import condition as registered
from gebra.versioning import Component
from tests.dod.conftest import LEGS, LINEAGE_EXPORT_NAME
from tests.dod.test_dod_job import DESIGNATED_CELL
from tests.sample_workflows import travel_booking
from tests.sample_workflows.travel_booking_defects import DEFECTS, DefectVariant
from tests.sample_workflows.travel_booking_evolution import EVOLUTION
from tools.honest_claims_lint import load_phrases, scan

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "tutorials" / "travel-booking-end-to-end.md"
DOD_CONFTEST: Final = REPO_ROOT / "tests" / "dod" / "conftest.py"
CI_WORKFLOW: Final = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: The instant the page's store-building examples pin. Restated here because this module
#: rebuilds the same store to re-derive what the page shows.
PINNED: Final = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)

#: The four evolution steps the page renders as full diff reports — the sequence's four
#: breaking cases (the fixture module's own framing: stages v5–v8 are "the three canonical
#: breaking cases … with the read-key case in both of its spellings"). Each is the
#: (predecessor, stage) label pair of one of ``EVOLUTION``'s last four rows, asserted below
#: so the page cannot silently show fewer cases than the sequence carries.
BREAKING_STEPS: Final[tuple[tuple[str, str], ...]] = (
    ("1.2.1.1", "1.2.1.2"),
    ("1.2.1.2", "1.2.1.3"),
    ("1.2.1.3", "1.2.2.3"),
    ("1.2.2.3", "1.2.3.3"),
)

#: Every condition ID the page prints, with the owning property, severity and claim class
#: shown beside it — checked against the registry rather than transcribed.
NAMED_CONDITIONS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("cycle-without-termination-witness", "termination-witness", "fatal", "defensible"),
    ("unprotected-effect-in-retry-region", "effect-safety", "error", "defensible-a"),
    ("deterministic-llm-temperature-unpinned", "determinism-replay", "warning", "heuristic"),
    ("read-key-never-written-on-path", "dataflow-completeness", "fatal", "defensible-a"),
    ("unprotected-effect-in-cycle", "effect-safety", "error", "defensible-a"),
)


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(page_text: str) -> str:
    """The page with every whitespace run collapsed, for sentence-level assertions."""
    return re.sub(r"\s+", " ", page_text)


@pytest.fixture(autouse=True)
def _ledger_is_clean() -> Iterator[None]:
    """WA-07: nothing in this module may run a node body, before or after (the TE-05 idiom)."""
    assert travel_booking.TRIPPED == []
    yield
    assert travel_booking.TRIPPED == []


@pytest.fixture(autouse=True)
def _stable_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Renderings must be runner-independent — the page's transcripts came from the DOC-01
    harness's child, which inherits none of these."""
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLORTERM", "COLUMNS", "LINES"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def evolved_store(tmp_path_factory: pytest.TempPathFactory) -> SnapshotStore:
    """The page's diff/report store: the eight stages recorded with the pinned instant."""
    store = SnapshotStore(tmp_path_factory.mktemp("gebra-tutorial-store") / ".gebra")
    for stage in EVOLUTION:
        snapshot(
            stage.build(),
            store=store,
            source=f"travel_booking:{stage.name}",
            extracted_at=PINNED,
        )
    return store


@pytest.fixture(scope="module")
def defect_runs() -> dict[DefectVariant, RunReport]:
    """One default-policy verify run per seeded-defect variant — the loop the page executes."""
    return {defect: verify(gebra.extract(defect.build()).ir) for defect in DEFECTS}


def _example_blocks(text: str) -> dict[str, str]:
    """Every ``gebra:example`` code block on the page, by id."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"<!-- gebra:example id=([a-z0-9-]+) -->\n```python\n(.*?)```", text, flags=re.DOTALL
        )
    }


def _output_block(text: str, example_id: str) -> str:
    """The pinned output block of one example, by its id."""
    match = re.search(
        rf"<!-- gebra:output id={re.escape(example_id)} -->\n```text\n(.*?)```",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, f"no output block for {example_id!r}"
    return match.group(1)


def _sole_failure(report: RunReport) -> PropertyReport:
    """The run's single failing property — the page's ``[finding] = [...]`` premise."""
    [finding] = [
        outcome
        for outcome in report.properties
        if isinstance(outcome, PropertyReport) and outcome.failure is not None
    ]
    return finding


# ── Shared, not copied: the page adds no assets of its own ───────────────────────────────


def test_no_example_builds_a_graph_of_its_own(page_text: str) -> None:
    """The mechanism behind "same assets as the scenario": there is nothing here to drift.

    An example that constructed a ``StateGraph``, added a node or declared a contract would
    be a fourth asset the acceptance job never sees; the page's examples import subjects and
    never author them.
    """
    blocks = _example_blocks(page_text)
    assert len(blocks) == 10
    for example_id, code in blocks.items():
        for marker in (
            "StateGraph(",
            "add_node(",
            "add_edge(",
            "add_conditional_edges(",
            "@gebra.",
        ):
            assert marker not in code, f"{example_id} authors workflow content: {marker}"


def test_the_examples_import_exactly_the_scenarios_modules(page_text: str) -> None:
    """The set of sample-workflow modules the page imports is the DoD conftest's own set."""
    pattern = re.compile(r"from tests\.sample_workflows(?:\.(\w+))? import (\w+)")

    def imported(source: str) -> set[str]:
        modules = set()
        for submodule, name in pattern.findall(source):
            modules.add(submodule or name)
        return modules

    page_modules = imported("".join(_example_blocks(page_text).values()))
    dod_modules = imported(DOD_CONFTEST.read_text(encoding="utf-8"))

    assert page_modules == dod_modules
    assert page_modules == {"travel_booking", "travel_booking_defects", "travel_booking_evolution"}


def test_the_topology_sketch_is_the_builders_own(page_text: str) -> None:
    """The sketch is quoted from ``build_travel_booking_agent``'s docstring, not redrawn."""
    sketch = re.search(r"```text\n(START → .*?)```", page_text, flags=re.DOTALL)
    assert sketch is not None
    docstring_lines = [
        line.strip()
        for line in (travel_booking.build_travel_booking_agent.__doc__ or "").splitlines()
    ]

    for line in sketch.group(1).splitlines():
        assert line.strip() in docstring_lines, (
            f"sketch line not in the builder docstring: {line!r}"
        )


# ── The extraction facts ─────────────────────────────────────────────────────────────────


def test_the_first_transcript_is_v1s_own_extraction(page_text: str) -> None:
    """Digest, node count and provenance in the opening transcript are the envelope's."""
    envelope = gebra.extract(travel_booking.build_travel_booking_agent())
    block = _output_block(page_text, "meeting-the-agent")

    assert f"graph_version  {envelope.graph_version()}" in block
    assert f"nodes          {len(envelope.ir.nodes)}" in block
    assert f"ir_version     {envelope.ir.ir_version}" in block
    assert (
        f"extracted from {envelope.extracted_from.source} at {envelope.extracted_from.family.value} level"
        in block
    )
    assert "warnings       []" in block
    assert "bodies run     []" in block
    # The same digest anchors the snapshot section: the gate's and the store's line pair.
    gate_block = _output_block(page_text, "v1-through-the-gate")
    assert f"digest the gate saw    {envelope.graph_version()}" in gate_block
    assert f"digest the store wrote {envelope.graph_version()}" in gate_block


def test_the_v1_gate_facts_are_a_real_runs(page_text: str) -> None:
    """Five verdicts, eight markers, a passing gate and eligibility — re-derived."""
    report = verify(gebra.extract(travel_booking.build_travel_booking_agent()).ir)
    verdicts = [item for item in report.properties if isinstance(item, PropertyReport)]
    markers = [item for item in report.properties if not isinstance(item, PropertyReport)]
    block = _output_block(page_text, "the-wedge-five-at-v1")

    assert [outcome.result for outcome in verdicts] == ["pass"] * 5
    for outcome in verdicts:
        assert f"{outcome.property:22} pass" in block
    assert f"+ {len(markers)} catalog properties outside this release" in block
    assert f"{markers[0].kind}: {markers[0].status}" in block
    assert report.gate.outcome == "pass" and report.gate.snapshot_eligible
    assert "gate pass, exit 0; snapshot eligible" in block


# ── The five defect catches ──────────────────────────────────────────────────────────────


def test_each_defect_is_caught_as_the_recorded_expectation_says(
    defect_runs: dict[DefectVariant, RunReport], page_text: str
) -> None:
    """Per variant: the named property fails with the named condition at the seeded locus,
    the registry's severity and claim class are the printed ones, and the default gate is
    the recorded one — re-derived, then found on the page."""
    block = _output_block(page_text, "five-defects-five-catches")

    for defect, report in defect_runs.items():
        finding = _sole_failure(report)
        failure = finding.failure
        assert failure is not None
        entry = registered(failure.property_condition)

        assert finding.property == defect.property
        assert failure.property_condition == defect.condition
        assert failure.severity == defect.severity == entry.severity
        assert failure.claim_class == entry.claim_class
        assert report.gate.exit_code == defect.default_exit

        location = failure.location
        if len(defect.locus_nodes) > 1:
            assert location.kind == "scc"
            assert frozenset(getattr(location, "nodes", ())) == frozenset(defect.locus_nodes)
        else:
            assert getattr(location, "node", None) == defect.locus_nodes[0]
        if defect.state_key is not None:
            assert getattr(location, "key", None) == defect.state_key
        assert bool(getattr(location, "fanout", None)) == defect.fanout_send

        assert f"defect {defect.number} — {defect.summary}" in block
        assert (
            f"{defect.property}: {defect.condition} [{failure.severity} · {failure.claim_class}]"
            in block
        )
    assert "fanout send" in block  # defect 5's evidence is shown, not summarized away


def test_one_seed_produces_exactly_one_finding(defect_runs: dict[DefectVariant, RunReport]) -> None:
    """The page's destructuring claim: ``_sole_failure`` above would raise on 0 or 2."""
    for report in defect_runs.values():
        _sole_failure(report)


def test_the_strict_catch_moves_the_gate_and_never_the_record(page_text: str) -> None:
    """Defect 3's R2 shape: default 0, promoted 1, model-equal records — re-derived."""
    variant = next(defect for defect in DEFECTS if defect.strict_slug is not None)
    envelope = gebra.extract(variant.build())
    assert variant.strict_slug == variant.property  # the promotion names the property itself
    promotion = RunPolicy(strict=StrictPolicy(mode="per-property", properties=(variant.property,)))
    default_run, strict_run = verify(envelope.ir), verify(envelope.ir, promotion)

    def p08(run: RunReport) -> PropertyReport:
        return next(
            outcome
            for outcome in run.properties
            if isinstance(outcome, PropertyReport) and outcome.property == variant.property
        )

    assert variant.number == 3 and variant.default_exit == 0
    assert (default_run.gate.outcome, default_run.gate.exit_code) == ("pass-with-notes", 0)
    assert (strict_run.gate.outcome, strict_run.gate.exit_code) == ("fail", 1)
    [promoted] = strict_run.gate.promotions
    assert (promoted.property, promoted.property_condition) == (variant.property, variant.condition)
    assert p08(default_run) == p08(strict_run)

    block = _output_block(page_text, "the-catch-that-needs-strict")
    assert "default  gate pass-with-notes exit 0" in block
    assert "strict   gate fail exit 1" in block
    assert f"promoted {variant.property}: {variant.condition}" in block
    assert "model-equal across both runs: True" in block


@pytest.mark.parametrize(("condition", "slug", "severity", "claim_class"), NAMED_CONDITIONS)
def test_every_condition_id_the_page_prints_is_the_registrys(
    page_text: str, condition: str, slug: str, severity: str, claim_class: str
) -> None:
    """A condition in a transcript is emittable, owned as named, and shown with its class."""
    entry = registered(condition)

    assert entry.emittable
    assert entry.property_slug == slug == property_for_condition(condition)
    assert (entry.severity, entry.claim_class) == (severity, claim_class)
    assert f"{condition} [{severity} · {claim_class}]" in page_text


# ── The evolve leg: labels, bump classes, refusals ───────────────────────────────────────


def test_the_evolution_rows_are_the_recorded_expectations(page_text: str) -> None:
    """Every version row of the evolve transcript is ``EVOLUTION``'s label, bump and summary."""
    lines = _output_block(page_text, "seven-more-versions").splitlines()
    rows = [line for line in lines if not line.startswith(" ")]
    refusal_lines = [line for line in lines if line.startswith(" ")]

    assert len(rows) == len(EVOLUTION)
    for row, stage in zip(rows, EVOLUTION, strict=True):
        expected = " ".join(part.value for part in Component if part in stage.expected_bump)
        assert row.startswith(f"{stage.expected_version:9} {expected or '—':4}")
        assert row.endswith(stage.summary)

    assert len(refusal_lines) == 2
    for line, stage in zip(refusal_lines, EVOLUTION[6:], strict=True):
        assert line.strip() == (
            f"{stage.name}: refused with its report — "
            f"{SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE.value}"
        )


def test_the_recorder_really_refuses_the_two_fatal_stages(tmp_path: Path) -> None:
    """The evolve leg re-derived end to end: gate-eligible stages record with their reports,
    the two FATAL-bearing stages are refused with them and land handed-none."""
    store = SnapshotStore(tmp_path / ".gebra")
    versions, refused = [], []
    for index, stage in enumerate(EVOLUTION):
        envelope = gebra.extract(stage.build())
        report = verify(envelope.ir)
        when = datetime(2026, 9, 1, 9, 0, index, tzinfo=timezone.utc)
        source = f"travel_booking:{stage.name}"
        try:
            outcome = record(
                envelope, store=store, source=source, extracted_at=when, eligibility=report
            )
        except SnapshotError as refusal:
            assert refusal.reason is SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE
            refused.append(stage.name)
            outcome = record(
                envelope, store=store, source=source, extracted_at=when, eligibility=None
            )
        versions.append(outcome.version)

    assert versions == [stage.expected_version for stage in EVOLUTION]
    assert refused == [stage.name for stage in EVOLUTION[6:]]


# ── The diff leg: every breaking case, classified ────────────────────────────────────────


def test_the_breaking_steps_are_the_sequences_last_four(page_text: str) -> None:
    """The four rendered pairs are exactly the last four evolution steps — none elided."""
    expected = tuple(
        (EVOLUTION[index - 1].expected_version, EVOLUTION[index].expected_version)
        for index in range(4, len(EVOLUTION))
    )
    assert BREAKING_STEPS == expected
    block = _output_block(page_text, "every-breaking-case-classified")
    for before, after in BREAKING_STEPS:
        assert f"before                  {before}" in block
        assert f"after                   {after}" in block


def test_the_four_rendered_diffs_are_the_verbs_own_output(
    page_text: str, evolved_store: SnapshotStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole output block is the four reports as the verb renders them, byte for byte,
    each carrying the deferred-P-12 marker in the slot where a classification would go."""
    renders = []
    for before, after in BREAKING_STEPS:
        assert main(["diff", "--store", str(evolved_store.path), before, after]) == 0
        renders.append(capsys.readouterr().out)

    joined = "".join(f"{render}\n" for render in renders)
    block = _output_block(page_text, "every-breaking-case-classified")
    assert joined.rstrip("\n") == block.rstrip("\n")

    marker = EVOLUTION_SAFETY_DEFERRED
    for render in renders:
        assert f"{marker.property_id} {marker.property}   not checked [{marker.status}]" in render


def test_the_breaking_case_bump_classes_are_derived_not_asserted(
    evolved_store: SnapshotStore,
) -> None:
    """E, E, F, F — re-derived from the store's own files, matching ``EVOLUTION``."""
    for (before, after), stage in zip(BREAKING_STEPS, EVOLUTION[4:], strict=True):
        diff = compare(evolved_store, before, after)
        assert diff.bump_class == stage.expected_bump
        assert diff.evolution_safety is EVOLUTION_SAFETY_DEFERRED


def test_what_verification_adds_is_a_real_runs_findings(
    page_text: str, evolved_store: SnapshotStore
) -> None:
    """The v6/v7/v8 gate-and-findings table re-derived from the stored documents."""
    block_lines = _output_block(page_text, "what-verification-adds").splitlines()
    expected_lines = []
    for label in ("1.2.1.3", "1.2.2.3", "1.2.3.3"):
        report = verify(evolved_store.read(label).ir)
        expected_lines.append(
            f"{label}  gate {report.gate.outcome:4}  exit {report.gate.exit_code}"
        )
        for outcome in report.properties:
            if isinstance(outcome, PropertyReport) and outcome.failure is not None:
                failure = outcome.failure
                expected_lines.append(
                    f"         {failure.property_condition} [{failure.severity} · {failure.claim_class}]"
                )
    assert block_lines == expected_lines


def test_the_page_states_why_v8_is_the_plain_cycle_condition(prose: str) -> None:
    """The retry-region/plain-cycle contrast the page draws is the region rule, not color."""
    assert "not itself a re-entry target" in prose
    assert "`unprotected-effect-in-cycle`" in prose or "unprotected-effect-in-cycle [" in prose


# ── The report leg ───────────────────────────────────────────────────────────────────────


def test_the_audit_trail_facts_are_the_stores_own(
    page_text: str, evolved_store: SnapshotStore
) -> None:
    """Export names and exits, the lineage document's identity and one step, freshness —
    all re-derived from a store built the way the page builds one."""
    block = _output_block(page_text, "the-audit-trail")

    exports = export_store(evolved_store)
    assert [exported.path.name for exported in exports] == [
        f"{stage.expected_version}{REPORT_SUFFIX}" for stage in EVOLUTION
    ]
    exits = [exported.report.gate.exit_code for exported in exports]
    assert exits == [0, 0, 0, 0, 0, 0, 1, 1]
    for exported in exports:
        assert f"{exported.path.name:24} gate exit {exported.report.gate.exit_code}" in block

    lineage_path = evolved_store.reports_dir / LINEAGE_EXPORT_NAME
    lineage_path.write_text(dump_lineage(lineage(evolved_store)), encoding="utf-8")
    document = json.loads(lineage_path.read_text(encoding="utf-8"))
    assert f"lineage.json   lineage_version {document['lineage_version']}," in block
    assert f"{document['total']} versions, current {document['current']}" in block
    step = document["entries"][6]["step"]
    assert step["previous"] == "1.2.1.3"
    assert step["bump_class"] == ["F"] and step["content_changed"] is True
    assert "entry 1.2.2.3  from 1.2.1.3: bump ['F'], content_changed True" in block

    outcome = freshness(gebra.extract(EVOLUTION[-1].build()).ir, store=evolved_store)
    assert outcome.state.value == "fresh"
    assert f"freshness      fresh — {outcome.summary().splitlines()[0]}" in block


# ── The one-run summary, and the leg order it shares with the harness ────────────────────


def test_the_summary_walks_the_legs_in_the_harnesss_order(page_text: str) -> None:
    """Six lines, first words exactly ``tests/dod/conftest.py``'s ``LEGS``, in order."""
    lines = _output_block(page_text, "the-dod-scenario-in-one-run").splitlines()

    assert [line.split()[0] for line in lines] == list(LEGS)


def test_the_summary_numbers_are_the_scenarios(
    page_text: str, defect_runs: dict[DefectVariant, RunReport]
) -> None:
    """Every count on the six lines re-derived: subjects, catches, refusals, steps, reports."""
    block = _output_block(page_text, "the-dod-scenario-in-one-run")

    assert f"extract   {len(EVOLUTION)} stages + {len(DEFECTS)} defect variants" in block
    catches = [
        defect
        for defect, report in defect_runs.items()
        if _sole_failure(report).failure.property_condition == defect.condition  # type: ignore[union-attr]
    ]
    assert f"{len(catches)}/5 defects caught" in block
    strict_defect = next(defect for defect in DEFECTS if defect.strict_slug is not None)
    assert f"defect {strict_defect.number} exit 1 under its promotion" in block
    fatal_stages = [
        stage for stage in EVOLUTION if stage.expected_version in ("1.2.2.3", "1.2.3.3")
    ]
    assert f"{len(fatal_stages)} refused with a report, recorded handed none" in block
    steps = ", ".join(
        "+".join(part.value for part in Component if part in stage.expected_bump)
        for stage in EVOLUTION[1:]
    )
    assert f"{len(EVOLUTION) - 1} steps: {steps};" in block
    marker = EVOLUTION_SAFETY_DEFERRED
    assert f"every diff carries {marker.property_id} {marker.status}" in block
    assert f"report    {len(EVOLUTION)} audit reports + {LINEAGE_EXPORT_NAME} in the store" in block


# ── The CI-job facts, and the sharing statement ──────────────────────────────────────────


def test_the_ci_job_facts_match_the_workflow(prose: str) -> None:
    """Cell, invocation and budget as the `dod` job actually declares them."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert DESIGNATED_CELL in prose
    assert "pytest tests/dod tests/evolution -q" in prose
    assert "tests/dod tests/evolution" in workflow
    assert "five-minute `timeout-minutes` budget" in prose
    assert re.search(r"^\s+timeout-minutes: 5$", workflow, re.MULTILINE)
    assert "`dod` in `.github/workflows/ci.yml`" in prose


def test_the_sharing_statement_is_on_the_page(prose: str) -> None:
    """The by-construction claim, stated where a reader can hold the page to it."""
    assert "This page adds no assets on top of that." in prose
    assert "No example above builds a graph of its own" in prose
    assert "the acceptance harness and this page would fail together, on the same commit" in prose


# ── The honest-claims boundary ───────────────────────────────────────────────────────────


def test_the_boundary_sentences_are_on_the_page(prose: str) -> None:
    """WA-06 on the page's own copy: presence, no grading, markers are not passes."""
    assert "**A witness is presence, not a proof of behavior.**" in prose
    assert "Neither is a statement about whether any run halts" in prose
    assert "the measure is attested by the author and trusted, never checked" in prose
    assert "**No output grades a change.**" in prose
    assert "mine, not any tool's" in prose
    assert "**A marker is not a pass.**" in prose
    assert "a question that was not asked is reported as exactly that" in prose
    assert "the judgment is the reviewer's" in prose


def test_the_page_is_inside_the_honest_claims_vocabulary() -> None:
    """The phrase lint, on this page specifically, on every run."""
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    include = ("docs/tutorials/travel-booking-end-to-end.md",)
    report = scan(REPO_ROOT, phrases, include=include, exclude=())

    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]
