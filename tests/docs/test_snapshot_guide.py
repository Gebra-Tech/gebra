"""``docs/guides/snapshot-diff-and-evolution.md`` pinned to the shapes it documents (DOC-14).

The guide teaches a reviewer to read a diff report, so the page states a lot of small facts
that are true of *code*: which counters a field moves, what a store directory is called, what
the diff header's rows are, what the deferred-P-12 marker carries, and which of the sequence's
steps move a gate. Prose cannot hold itself to any of that, so this module does:

* the V.S.F.E table is ``FIELD_COMPONENTS`` itself, checked in both directions;
* the store's directory and file names are :mod:`gebra.store`'s own constants;
* the eight labels and their bump classes are ``EVOLUTION``'s recorded expectations, and the
  gate verdicts the page tabulates are re-derived from a store this module builds;
* the marker's four fields are read off the shared ``EVOLUTION_SAFETY_DEFERRED`` instance, and
  the exit codes the page documents are taken from real in-process CLI runs;
* the sentences carrying the WA-06 boundary — that no surface here grades a change — are pinned,
  and the phrase lint runs over the page.

The module builds stores from the sentinel-guarded travel-booking fixtures, whose bodies record
into the shared ledger and raise if anything calls them; every test below asserts that ledger is
empty when it finishes, so a run in which a node executed could not report these results (WA-07).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from gebra.audit import Freshness
from gebra.cli import main
from gebra.diff import EVOLUTION_SAFETY_DEFERRED
from gebra.lineage import compare
from gebra.snapshot import snapshot
from gebra.store import (
    META_FILENAME,
    REPORT_SUFFIX,
    REPORTS_DIRNAME,
    SNAPSHOT_SUFFIX,
    SNAPSHOTS_DIRNAME,
    STORE_DIRNAME,
    SnapshotStore,
)
from gebra.verify import (
    PROPERTY_SLUGS,
    PropertyReport,
    is_implemented,
    property_for_condition,
    verify,
)
from gebra.verify import condition as registered
from gebra.versioning import FIELD_COMPONENTS, Component
from tests.sample_workflows import travel_booking
from tests.sample_workflows.travel_booking_evolution import EVOLUTION
from tools.honest_claims_lint import load_phrases, scan

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "guides" / "snapshot-diff-and-evolution.md"

#: The instant every example on the page pins, so a stored timestamp is a function of the
#: example rather than of the clock. Restated here because this module rebuilds the same store.
PINNED: Final = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)

#: The two conditions the page names by id in a transcript, with the owning property, the
#: severity and the claim class it prints beside each. Checked against the registry rather than
#: transcribed — and the claim class is not optional decoration: REPORT-FORMAT-SPEC §4.6 rule 1
#: requires it beside any finding a user sees, which is why both transcripts print it.
NAMED_CONDITIONS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("cycle-without-termination-witness", "termination-witness", "fatal", "defensible"),
    ("unprotected-effect-in-cycle", "effect-safety", "error", "defensible-a"),
)


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(page_text: str) -> str:
    """The page with every run of whitespace collapsed, for sentence-level assertions.

    Re-wrapping a paragraph must not fail a test that is about a claim; table and fence
    assertions read ``page_text`` instead, where layout is content.
    """
    return re.sub(r"\s+", " ", page_text)


@pytest.fixture(autouse=True)
def _ledger_is_clean() -> Iterator[None]:
    """WA-07: nothing in this module may run a node body, before or after (the TE-05 idiom)."""
    assert travel_booking.TRIPPED == []
    yield
    assert travel_booking.TRIPPED == []


@pytest.fixture(autouse=True)
def _stable_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """`tests/cli/conftest.py`'s fixture, restated: renderings must be runner-independent.

    The page's transcripts came out of the DOC-01 harness's child, which inherits none of
    these; a contributor with `COLUMNS` exported would otherwise re-render at a width the
    page never showed.
    """
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLORTERM", "COLUMNS", "LINES"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def evolved_store(tmp_path_factory: pytest.TempPathFactory) -> SnapshotStore:
    """The page's own store: the eight stages recorded in order, with the pinned instant."""
    store = SnapshotStore(tmp_path_factory.mktemp("gebra-doc-store") / STORE_DIRNAME)
    for stage in EVOLUTION:
        snapshot(
            stage.build(),
            store=store,
            source=f"travel_booking:{stage.name}",
            extracted_at=PINNED,
        )
    return store


def _output_block(text: str, example_id: str) -> str:
    """The pinned output block of one example, by its id."""
    match = re.search(
        rf"<!-- gebra:output id={re.escape(example_id)} -->\n```text\n(.*?)```",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, f"no output block for {example_id!r}"
    return match.group(1)


# ── The V.S.F.E definition ───────────────────────────────────────────────────────────────


def test_the_counter_table_is_the_engines_own(page_text: str) -> None:
    """The printed S/F/E table is ``FIELD_COMPONENTS``, row for row, in both directions."""
    printed = _output_block(page_text, "what-the-counters-count").splitlines()
    assert len(printed) == len(FIELD_COMPONENTS)

    for line, (path, components) in zip(printed, FIELD_COMPONENTS.items(), strict=True):
        field, _, moved = line.partition(" ")
        expected = " ".join(part.value for part in Component if part in components)
        assert field == ".".join(path)
        assert moved.strip() == (expected or "— no component")


def test_the_two_counters_a_node_moves_are_named(prose: str) -> None:
    """The S+F rule is the one a reader most often gets wrong, so the page states it."""
    assert FIELD_COMPONENTS[("nodes",)] == frozenset({Component.S, Component.F})
    assert "**`nodes` moves S *and* F.**" in prose
    assert "a renamed node is a new identity" in prose


def test_v_is_never_derived(prose: str) -> None:
    """The engine never moves V, and the page says so rather than leaving it to be assumed."""
    assert Component.derived() == (Component.S, Component.F, Component.E)
    assert "**V** is yours, and nothing in gebra ever moves it" in prose


# ── The store layout ─────────────────────────────────────────────────────────────────────


def test_the_store_layout_is_the_modules_own_names(page_text: str) -> None:
    """Every path the first example's tree shows is spelled by a store constant."""
    tree = _output_block(page_text, "a-first-snapshot")

    assert f"{STORE_DIRNAME}/{META_FILENAME}" in tree
    assert f"{STORE_DIRNAME}/{REPORTS_DIRNAME}" in tree
    assert f"{STORE_DIRNAME}/{SNAPSHOTS_DIRNAME}" in tree
    assert f"{STORE_DIRNAME}/{SNAPSHOTS_DIRNAME}/1.0.0.0{SNAPSHOT_SUFFIX}" in tree


def test_the_report_path_the_page_documents_is_the_stores(prose: str, page_text: str) -> None:
    """The audit export's path is PD-012's, named on the page in the store's own vocabulary."""
    assert f"{REPORTS_DIRNAME}/<version>{REPORT_SUFFIX}" in prose
    assert f"1.2.2.3{REPORT_SUFFIX}" in _output_block(page_text, "the-audit-export")


# ── The sequence, its labels and its verdicts ────────────────────────────────────────────


def test_the_walkthrough_records_the_sequence_the_scenario_evolves(page_text: str) -> None:
    """The eight labels and summaries are ``EVOLUTION``'s, in evolution order."""
    printed = _output_block(page_text, "eight-versions-one-store").splitlines()
    rows = [line for line in printed if line and not line.startswith(f"{STORE_DIRNAME}/")]

    assert len(rows) == len(EVOLUTION)
    for row, stage in zip(rows, EVOLUTION, strict=True):
        label, _, rest = row.partition("  ")
        expected = " ".join(part.value for part in Component if part in stage.expected_bump)
        assert label.strip() == stage.expected_version
        assert rest.strip().startswith(expected or "—")
        assert rest.strip().endswith(stage.summary)


def test_the_step_table_is_the_verdicts_a_real_store_produces(
    page_text: str, evolved_store: SnapshotStore
) -> None:
    """Every row of the survey table is re-derived, so a moved verdict fails the build.

    Each step contributes one ``before -> after`` row and one indented line per finding, and
    every finding line carries its claim class beside its severity (REPORT-FORMAT-SPEC §4.6
    rule 1) — checked here as well as in the per-condition test, because this is the surface a
    reader scans rather than the one they look a condition up in.
    """
    printed = _output_block(page_text, "every-step-and-its-verdict").splitlines()
    assert printed[0].split() == ["step", "moved", "gate"]

    steps: list[tuple[str, list[str]]] = []
    for line in printed[1:]:
        if line.startswith(" "):
            steps[-1][1].append(line.strip())
        else:
            steps.append((line, []))

    labels = [stage.expected_version for stage in EVOLUTION]
    for (row, findings), (before, after) in zip(steps, pairwise(labels), strict=True):
        diff = compare(evolved_store, before, after)
        report = verify(evolved_store.read(after).ir)
        counters = " ".join(part.value for part in Component if part in diff.bump_class)
        expected = [
            f"{outcome.failure.property_condition} "
            f"[{outcome.failure.severity} · {outcome.failure.claim_class}]"
            for outcome in report.properties
            if isinstance(outcome, PropertyReport) and outcome.failure is not None
        ]
        assert row.startswith(f"{before} -> {after}")
        assert counters in row
        assert row.endswith(report.gate.outcome)
        assert findings == expected


def test_the_two_e_bumps_are_the_pair_the_page_contrasts(evolved_store: SnapshotStore) -> None:
    """The page's spine: an added key and a still-declared removed key carry one bump class."""
    added = compare(evolved_store, "1.0.0.0", "1.0.0.1")
    removed = compare(evolved_store, "1.2.1.1", "1.2.1.2")

    assert added.bump_class == removed.bump_class == frozenset({Component.E})
    assert [key.key for key in added.state.added] == ["seat_preference"]
    assert [key.key for key in removed.state.removed] == ["itinerary"]


def test_the_removed_key_is_still_declared_by_the_two_named_contracts(
    evolved_store: SnapshotStore, page_text: str
) -> None:
    """The cross-reference the page says a reader has to assemble is the one it printed."""
    readers = [
        node.id
        for node in evolved_store.read("1.2.1.2").ir.nodes
        if node.annotations is not None
        and "itinerary" in (*(node.annotations.input or ()), *(node.annotations.output or ()))
    ]

    assert readers == ["compile_itinerary", "notify_traveler"]
    assert str(readers) in _output_block(page_text, "two-changes-one-counter")


def test_snapshot_eligibility_is_the_fatal_rule_the_page_states(
    evolved_store: SnapshotStore, prose: str
) -> None:
    """The page's eligibility rule — an ERROR fails the gate and stays eligible — over the eight.

    Written as the rule rather than as a verdict list, because the sentence it pins is about
    what eligibility *turns on*: FATAL findings and a verdict having been reached, never a
    clean gate. The two failing versions are the ones that make it non-vacuous.
    """
    verdicts = {}
    for stage in EVOLUTION:
        gate = verify(evolved_store.read(stage.expected_version).ir).gate
        assert gate.snapshot_eligible == (gate.exit_code != 2 and gate.counts.fatal == 0)
        verdicts[stage.expected_version] = (gate.outcome, gate.snapshot_eligible)

    assert verdicts["1.2.2.3"] == ("fail", False)
    assert "an ERROR fails the gate and the version is still" in prose
    assert "the store stops before the first version carrying a FATAL" in prose


# ── The deferred marker, and the honest-claims boundary ──────────────────────────────────


def test_the_marker_fields_are_the_registrys(page_text: str) -> None:
    """The four fields the page prints are the shared instance's, not a retelling of it."""
    printed = _output_block(page_text, "not-checked-is-not-a-pass")
    marker = EVOLUTION_SAFETY_DEFERRED

    assert f"kind     {marker.kind}" in printed
    assert f"property {marker.property_id} {marker.property}" in printed
    assert f"status   {marker.status}" in printed
    assert marker.detail.split(";")[0] in re.sub(r"\s+", " ", printed)


@pytest.mark.parametrize(
    ("example_id", "before", "after"),
    (
        ("a-diff-report", "1.2.1.1", "1.2.1.2"),
        ("an-effect-class-escalates", "1.2.2.3", "1.2.3.3"),
    ),
)
def test_both_rendered_diffs_are_the_verbs_own_output(
    page_text: str,
    evolved_store: SnapshotStore,
    capsys: pytest.CaptureFixture[str],
    example_id: str,
    before: str,
    after: str,
) -> None:
    """The page's two diff transcripts are what the verb renders, not a transcription of it.

    The example appends its own ``exit N`` line after the artifact, so that line is dropped
    before the comparison; everything above it must be byte-equal to the verb's own output.
    """
    assert main(["diff", "--store", str(evolved_store.path), before, after]) == 0
    rendered = capsys.readouterr().out
    printed = _output_block(page_text, example_id)
    artifact, _, tail = printed.rpartition("exit ")

    assert tail.strip() == "0"
    assert artifact == rendered

    marker = EVOLUTION_SAFETY_DEFERRED
    assert f"{marker.property_id} {marker.property}" in artifact
    assert f"not checked [{marker.status}]" in artifact


def test_evolution_safety_is_not_implemented_in_this_release() -> None:
    """The premise the whole page rests on, asserted rather than assumed."""
    assert "evolution-safety" in PROPERTY_SLUGS
    assert not is_implemented("evolution-safety")


def test_the_deferred_count_the_export_section_states_is_the_registrys(page_text: str) -> None:
    """The answered/deferred split is derived from the catalog, not a number typed once."""
    deferred = [slug for slug in PROPERTY_SLUGS if not is_implemented(slug)]
    answered = [slug for slug in PROPERTY_SLUGS if is_implemented(slug)]
    block = _output_block(page_text, "the-audit-export")

    assert f"{len(PROPERTY_SLUGS)} — {len(answered)} answered, {len(deferred)} deferred" in block
    assert "thirteen catalog properties" in re.sub(r"\s+", " ", page_text).lower()


def test_no_surface_on_this_page_grades_a_change(prose: str) -> None:
    """WA-06 on the page's own copy: the bump class routes a reader, it never scores one."""
    assert "**A bump class is a routing decision" in prose
    assert "never a risk grade.**" in prose
    assert "It also does not classify." in prose
    assert "the judgment is not in the store" in prose
    # The two headings that use "breaking change" attribute the word before using it.
    assert "they are the *reviewer's* words, and mine" in prose
    assert "Nothing gebra prints on this page applies either to a change" in prose
    assert prose.count("## A breaking change:") == 2


def test_the_page_never_reads_the_marker_as_a_verdict(prose: str) -> None:
    """`not checked` is stated as an absent question, never as a clean bill."""
    assert '"Not checked" is not a pass' in prose
    assert "It carries no `result`, because it is not a result" in prose
    assert "says a question was not asked" in prose


def test_the_page_is_inside_the_honest_claims_vocabulary() -> None:
    """The phrase lint, on this page specifically, on every run."""
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    include = ("docs/guides/snapshot-diff-and-evolution.md",)
    report = scan(REPO_ROOT, phrases, include=include, exclude=())

    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]


# ── The conditions and the states the page names ─────────────────────────────────────────


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


def test_the_three_freshness_states_are_the_engines(prose: str) -> None:
    """The page's three-states-rather-than-two claim is read off the enum it is about."""
    assert len(Freshness) == 3
    assert "It answers in three states rather than two" in prose


# ── The CLI behaviour the page documents ─────────────────────────────────────────────────


def test_the_diff_exit_codes_are_what_the_page_documents(
    evolved_store: SnapshotStore, capsys: pytest.CaptureFixture[str], prose: str
) -> None:
    """A real run of each documented case, in process — 0 by default, 1 only when asked."""
    store_argument = str(evolved_store.path)

    assert main(["diff", "--store", store_argument, "1.2.1.1", "1.2.1.2"]) == 0
    assert main(["diff", "--store", store_argument, "1.2.1.1", "1.2.1.2", "--exit-code"]) == 1
    assert main(["diff", "--store", store_argument, "1.2.1.1", "1.2.1.1", "--exit-code"]) == 0
    assert main(["diff", "--store", store_argument, "1.2.1.1", "9.9.9.9"]) == 2
    capsys.readouterr()

    assert "does not fail a build for having found a difference unless you ask it to" in prose
    assert "A `2` means no comparison was made at all" in prose


def test_the_history_column_vocabulary_is_the_verbs(
    evolved_store: SnapshotStore, capsys: pytest.CaptureFixture[str], page_text: str
) -> None:
    """The listing the page prints is the listing the verb renders for the same store."""
    assert main(["history", "--store", str(evolved_store.path)]) == 0
    rendered = capsys.readouterr().out
    printed = _output_block(page_text, "reading-the-history")

    header = next(line for line in rendered.splitlines() if line.strip().startswith("#  version"))
    assert header in printed
    for stage in EVOLUTION:
        assert stage.expected_version in printed
    assert printed.count("content changed") == rendered.count("content changed")
