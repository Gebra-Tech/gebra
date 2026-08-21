"""``tools/corpus_green.py`` — SOW §2 criterion 2 held to PD-006 R3's four clauses.

The gate under test, in the two directions that make it evidence rather than a summary.

**Forward:** on the repository as it stands, every clause reports what the corpus actually
is — 60/60 loaded and lint-green, 33/60 composing with the other 27 each attributed to a
named non-wedge cause, 40 of the 41 R3.2-scoped wedge obligations matched, 31 structured
skips, 13 outcomes with 8 markers. Those numbers are asserted, not printed, because a gate
whose counts drift silently is a gate that stopped checking.

**Backward:** each refusal is armed. A non-composing block with no non-wedge cause is a
violation; a non-wedge obligation that reports anything but a structured skip is a violation;
a skip reason that names neither the property nor SOW §8 is a violation. Seeded corpora and
seeded runs prove each one fails rather than passing in silence — which is the half a
"criterion 2 is green" claim cannot rest on prose for.

The distinction the whole module turns on is **residue vs violation**. Residue is a shortfall
that carries a named cause or a routed fidelity-matrix row: reported, counted, never rendered
as a pass. A violation is a shortfall nothing accounts for, and it fails the gate in every
mode. ``--strict`` collapses the two, which is the literal reading of R3.1/R3.2 and is what
the CI job flips to when the last routed item lands.

The four causes an R3.1 shortfall may carry are a **closed set** ratified at PD-039 Q1
(2026-08-08) and re-signed into ``PHASE-0-DOD-CHECKLIST`` C2 clause (1). That is what keeps
the scoped reading of R3.1 from drifting: a fifth cause is a PD event, not an edit here, and
``test_the_four_compose_causes_are_a_closed_set`` is where an added one fails.

WA-07: nothing here executes a workflow node, calls a model, or opens a network connection.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gebra.testing.fixtures import (
    SCHEMA_FILENAME,
    PropertyFixture,
    iter_fixture_paths,
    load_fixture,
)
from gebra.verify import NON_WEDGE_SLUGS, PROPERTY_REGISTRY
from tests.conftest import FIXTURES_DIR
from tools.corpus_green import (
    COMPOSE_CAUSES,
    R32_KINDS,
    ClauseResult,
    CorpusGreenError,
    GreenReport,
    attribute,
    check,
    format_report,
    main,
)

SCHEMA = FIXTURES_DIR / SCHEMA_FILENAME
MATRIX = Path(__file__).resolve().parents[2] / "docs" / "governance" / "FIDELITY-MATRIX.md"

#: What the corpus is today, clause by clause. Each is a *fact about the vendored corpus*, so
#: a re-vendor that moves one fails here by name rather than by a changed summary line.
FIXTURE_COUNT = 60
COMPOSING = 33
R32_SCOPED = 41
R32_MATCHED = 41
NON_WEDGE_OBLIGATIONS = 31

#: How the 27 non-composing blocks divide. The sum is pinned separately, so a cause that
#: silently absorbed another's fixtures fails on the split rather than on the total.
CAUSE_COUNTS = {
    "non-wedge-owner": 23,
    "non-wedge-component": 2,
    "held-back-condition-id": 1,
    "run-level-wrapper": 1,
}


@pytest.fixture(scope="module")
def report() -> GreenReport:
    """One gate run against the vendored corpus."""
    return check(FIXTURES_DIR, SCHEMA)


@pytest.fixture(scope="module")
def fixtures() -> tuple[PropertyFixture, ...]:
    return tuple(load_fixture(path) for path in iter_fixture_paths(FIXTURES_DIR))


def _clause(report: GreenReport, clause_id: str) -> ClauseResult:
    return next(clause for clause in report.clauses if clause.id == clause_id)


# ── Forward: the four clauses on the corpus as it stands ─────────────────────────────────


def test_the_gate_answers_exactly_the_four_pd_006_clauses(report: GreenReport) -> None:
    """Four clauses, in R3's own order — not three, not a summary of them."""
    assert [clause.id for clause in report.clauses] == ["R3.1", "R3.2", "R3.3", "R3.4"]


def test_nothing_in_the_corpus_is_unaccounted(report: GreenReport) -> None:
    """The gate's own question: every shortfall carries a cause or a route.

    This is what the CI job asserts, and it is deliberately weaker than criterion 2 — see
    :func:`test_criterion_2_is_not_yet_met_and_the_gate_says_so`.
    """
    assert report.violations == []
    assert report.accounted


def test_criterion_2_is_met_and_the_gate_says_so(report: GreenReport) -> None:
    """The mirror image its predecessor promised, landed with the M13 execution (DEC-24).

    Both former residue items are gone for the right reasons: `mixed/08`'s one missing
    optional diagnostic landed via its R-05 revision (FM-009 closed), and the R3.1 compose
    attribution was reclassified accounted-not-residue per the ratified PD-039 Q1 reading —
    in the same commit as the CI job's `--strict` flip, exactly as the predecessor's
    docstring scheduled. `met` still computes from accounted-and-no-residue, so a new
    shortfall flips this test red rather than hiding under the flip.
    """
    assert report.met
    assert report.residue == []
    assert "criterion 2 MET" in format_report(report)
    assert "NOT YET MET" not in format_report(report)


def test_the_four_compose_causes_are_a_closed_set() -> None:
    """PD-039 Q1's first strengthening, asserted rather than left to the docstring.

    The ratified reading of R3.1 turns on *which* causes account for a non-composing block,
    so the set is closed by ruling: a fifth is a PD event amending `PHASE-0-DOD-CHECKLIST`
    C2 again, never a code edit. Pinned by name and by count here, so adding one fails with
    this test's name on it — which is the difference between a closed taxonomy and one that
    drifts into "whatever the gate currently tolerates".
    """
    assert COMPOSE_CAUSES == (
        "non-wedge-owner",
        "non-wedge-component",
        "held-back-condition-id",
        "run-level-wrapper",
    )
    assert set(CAUSE_COUNTS) == set(COMPOSE_CAUSES), (
        "the observed split and the ratified set have diverged"
    )


def test_r31_load_layer_counts(report: GreenReport, fixtures: tuple[PropertyFixture, ...]) -> None:
    """All 60 load and lint; 33 compose; the rest are attributed, none merely asserted."""
    clause = _clause(report, "R3.1")
    assert clause.violations == []
    assert len(fixtures) == FIXTURE_COUNT
    assert f"{FIXTURE_COUNT} fixture(s) loaded" in clause.findings[0]
    assert "corpus lint OK" in clause.findings[0]
    assert f"{COMPOSING}/{FIXTURE_COUNT}" in clause.findings[1]


def test_every_non_composing_block_is_attributed_to_a_named_cause(
    fixtures: tuple[PropertyFixture, ...],
) -> None:
    """The checkable half of R3.1: no block is silently non-composing.

    Asserted against the attribution function directly rather than against the report's
    summary line, so the split is pinned fixture by fixture.
    """
    counts = dict.fromkeys(COMPOSE_CAUSES, 0)
    for fixture in fixtures:
        try:
            fixture.expected_report()
        except Exception:  # noqa: BLE001 - any refusal is a non-composing block
            item = attribute(fixture)
            assert item.accounted, f"{item.fixture}: {item.evidence}"
            assert item.cause is not None
            assert item.evidence, "an attribution states what was checked, never only a label"
            counts[item.cause] += 1
    assert counts == CAUSE_COUNTS
    assert sum(counts.values()) == FIXTURE_COUNT - COMPOSING


def test_the_non_wedge_component_cause_is_verified_not_labelled(
    fixtures: tuple[PropertyFixture, ...],
) -> None:
    """``non-wedge-component`` is only claimed where restricting the foreign records works.

    The other three causes are true by inspection; this one is a *claim about what would
    happen*, so the gate composes the PR-1 projection to check it. Both fixtures that carry
    the cause are mixed blocks whose wedge share is a live, matched obligation.
    """
    named = [
        fixture.fixture_id
        for fixture in fixtures
        if attribute(fixture).cause == "non-wedge-component"
    ]
    assert [name.split("-")[0] for name in named] == ["mixed/01", "mixed/09"]
    for fixture in fixtures:
        item = attribute(fixture)
        if item.cause == "non-wedge-component":
            assert "composes once they are restricted out (PR-1)" in item.evidence


def test_r32_scopes_itself_to_the_obligation_kinds_the_ruling_enumerates(
    report: GreenReport,
) -> None:
    """R3.2 names four projections, and a cross-property co-failure is not among them.

    The harness compares those too. Reporting them *inside* the clause would make criterion 2
    stricter than the ruling that defines it; reporting them nowhere would hide six live
    comparisons. They are counted beside it.
    """
    assert "cross-property-co-failure" not in R32_KINDS
    clause = _clause(report, "R3.2")
    assert clause.violations == []
    assert f"{R32_MATCHED}/{R32_SCOPED}" in clause.findings[0]
    assert "model equality" in clause.findings[0]
    assert "never string equality" in clause.findings[0]
    assert "beyond what R3.2's enumeration asks for" in clause.findings[1]


def test_r33_every_non_wedge_component_is_a_structured_skip(report: GreenReport) -> None:
    """R3.3 in full: named, counted, surfaced — and the clause is met, not merely reported."""
    clause = _clause(report, "R3.3")
    assert clause.met
    assert f"{NON_WEDGE_OBLIGATIONS} non-wedge obligation(s)" in clause.findings[0]
    assert "SOW §8" in clause.findings[0]


def test_r34_is_asserted_against_verify_rather_than_restated(report: GreenReport) -> None:
    """R3.4 is ``verify()``'s obligation, so the gate runs it instead of describing it."""
    clause = _clause(report, "R3.4")
    assert clause.met
    assert f"{len(PROPERTY_REGISTRY)} propert(y/ies) in catalog order" in clause.findings[0]
    assert (
        f"{len(NON_WEDGE_SLUGS)} of them with structured not-implemented markers"
        in (clause.findings[0])
    )


# ── Backward: each refusal is armed ──────────────────────────────────────────────────────


def _seeded_corpus(tmp_path: Path) -> Path:
    """A writable copy of the vendored corpus — never the corpus itself (WA-04/WA-11)."""
    root = tmp_path / "properties"
    shutil.copytree(FIXTURES_DIR, root)
    return root


def test_a_non_composing_block_with_no_non_wedge_cause_is_a_violation(tmp_path: Path) -> None:
    """The seed R3.1's compose clause exists to catch.

    A **wedge** fixture whose block stops composing has no non-wedge deferral to hide behind,
    so the gate must refuse it rather than fold it into "the 27". Seeded by retyping one
    wedge negative's severity, which §0.3 pins to an enum.
    """
    root = _seeded_corpus(tmp_path)
    target = root / "determinism-replay" / "negative-01-seedless-deterministic-llm-classifier.yaml"
    text = target.read_text(encoding="utf-8")
    assert "severity: warning" in text, "the seed is stale — re-read the fixture"
    target.write_text(text.replace("severity: warning", "severity: catastrophic"), encoding="utf-8")

    report = check(root, root / SCHEMA_FILENAME)
    clause = _clause(report, "R3.1")
    assert not report.accounted
    assert any("no non-wedge cause accounts for it" in item for item in clause.violations)
    assert "NOT MET" in format_report(report)


def test_a_lint_violation_fails_the_load_layer(tmp_path: Path) -> None:
    """R3.1's first clause is the lint's, and the gate carries its violations rather than
    re-deciding them."""
    root = _seeded_corpus(tmp_path)
    source = root / "determinism-replay" / "positive-01-pinned-seed-zero-temp-classifier.yaml"
    assert source.exists(), "the seed is stale — re-read the corpus"
    shutil.copy(source, source.with_name("stray-copy.yaml"))

    report = check(root, root / SCHEMA_FILENAME)
    assert not report.accounted
    assert any("corpus lint" in item for item in _clause(report, "R3.1").violations)


def _corpus_with_mixed_08_unrevised(tmp_path: Path) -> Path:
    """A corpus copy with `mixed/08` reverted to its pre-DEC-24 block (the key stripped).

    Recreates the FM-009 mismatch on a scratch copy so the residue/violation boundary stays
    testable now that the live corpus is green — the vendored tree is never touched.
    """
    seeded = tmp_path / "properties"
    shutil.copytree(FIXTURES_DIR, seeded)
    fixture = seeded / "mixed" / "08-express-path-skips-gate-writer-and-witnessed-exit.yaml"
    text = fixture.read_text(encoding="utf-8")
    marker = "    writers_on_other_paths: [compliance_gate]\n"
    assert marker in text, "the seed is stale — mixed/08 no longer carries the key"
    fixture.write_text(text.replace(marker, "", 1), encoding="utf-8")
    return seeded


def test_an_unrouted_r32_shortfall_is_a_violation_not_residue(tmp_path: Path) -> None:
    """The line between residue and violation is read off the matrix, never assumed.

    While FM-009 was open, its row is what made `mixed/08` residue; the row is closed now
    (DEC-24), so the same observation — recreated on a corpus copy with the key stripped —
    must read as a violation, because no open row carries it. That keeps the gate's own
    sentence ("an open row carries its route") a claim it verifies, in the end state
    `FIDELITY-MATRIX.md` §6 drives towards.
    """
    report = check(_corpus_with_mixed_08_unrevised(tmp_path), SCHEMA, MATRIX)
    clause = _clause(report, "R3.2")
    assert not report.accounted
    assert any("with no open row" in item for item in clause.violations)
    assert not any("mixed/08" in item for item in report.residue)


def test_an_unreadable_matrix_is_a_tool_error(tmp_path: Path) -> None:
    """A missing decision log is "no verdict was reached", not "criterion 2 failed"."""
    with pytest.raises(CorpusGreenError):
        check(FIXTURES_DIR, SCHEMA, tmp_path / "nowhere.md")


def test_running_without_a_matrix_is_stricter_never_laxer() -> None:
    """``matrix_path=None`` is the mode the WA-07 tripwire uses, and it never launders.

    Handing no decision log means nothing is routed, so every R3.2 shortfall reads as a
    violation. That direction matters: the guarded child in
    ``tests/testing/test_hermeticity.py`` runs this mode so that a matrix reaching its own
    end state — §3 emptied, which is what `FIDELITY-MATRIX.md` §6 step 4 drives towards and
    what `parse_matrix` refuses — can never turn a WA-07 tripwire red. A mode that were
    *laxer* instead would make that trade a bad one.
    """
    report = check(FIXTURES_DIR, SCHEMA, None)
    assert [clause.id for clause in report.clauses] == ["R3.1", "R3.2", "R3.3", "R3.4"]
    assert report.accounted  # the live corpus is green, so no-matrix has nothing to launder
    assert report.violations == []


def test_running_without_a_matrix_reads_a_shortfall_as_a_violation(tmp_path: Path) -> None:
    """The never-laxer half, on the seeded copy: no decision log means nothing is routed."""
    report = check(_corpus_with_mixed_08_unrevised(tmp_path), SCHEMA, None)
    assert not report.accounted
    assert any("mixed/08" in item and "no open row" in item for item in report.violations)
    assert not any("mixed/08" in item for item in report.residue)


def test_a_non_wedge_obligation_that_is_not_a_skip_is_a_violation() -> None:
    """R3.3's refusal, on a hand-built run rather than a seeded corpus.

    The status has to be forged: nothing in the corpus can produce a non-wedge obligation
    that is anything but ``deferred-to-phase-1``, which is the point — the check is a floor
    under a future change, not a description of today.
    """
    from dataclasses import replace

    from gebra.testing.harness import CorpusRun, run_corpus
    from tools.corpus_green import _clause_r33

    run = run_corpus(FIXTURES_DIR)
    forged = CorpusRun(
        tuple(
            replace(outcome, status="matched") if not outcome.obligation.wedge else outcome
            for outcome in run.outcomes
        )
    )
    clause = _clause_r33(forged)
    assert len(clause.violations) == NON_WEDGE_OBLIGATIONS
    assert all("never a pass" in item for item in clause.violations)


def test_a_skip_reason_that_cites_neither_the_property_nor_sow_8_is_a_violation() -> None:
    """R3.3 asks for a *named* skip; "skipped" alone is what it forbids."""
    from dataclasses import replace

    from gebra.testing.harness import CorpusRun, run_corpus
    from tools.corpus_green import _clause_r33

    run = run_corpus(FIXTURES_DIR)
    forged = CorpusRun(
        tuple(
            replace(outcome, detail="skipped") if not outcome.obligation.wedge else outcome
            for outcome in run.outcomes
        )
    )
    clause = _clause_r33(forged)
    assert len(clause.violations) == NON_WEDGE_OBLIGATIONS
    assert all("names neither the property nor SOW §8" in item for item in clause.violations)


def test_an_unrunnable_corpus_is_a_tool_error_not_a_verdict(tmp_path: Path) -> None:
    """Exit 2 territory: "no verdict was reached" is not "criterion 2 failed"."""
    with pytest.raises(CorpusGreenError):
        check(tmp_path / "nowhere", tmp_path / "nowhere" / SCHEMA_FILENAME)


# ── The CLI ──────────────────────────────────────────────────────────────────────────────


def test_both_modes_exit_0_on_the_green_corpus(capsys: pytest.CaptureFixture[str]) -> None:
    """The flip its predecessor scheduled: default AND ``--strict`` exit 0 (DEC-24).

    The green claim is printed only now that it is true; ``--strict`` stays the harder line
    (any future residue fails it) and is what the CI job runs since the flip.
    """
    assert main(["--corpus", str(FIXTURES_DIR)]) == 0
    default = capsys.readouterr()
    assert "criterion 2 MET" in default.out

    assert main(["--corpus", str(FIXTURES_DIR), "--strict"]) == 0
    strict = capsys.readouterr()
    assert "criterion 2 MET" in strict.out


def test_a_tool_error_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--corpus", str(tmp_path / "nowhere")]) == 2
    assert "corpus green:" in capsys.readouterr().err
