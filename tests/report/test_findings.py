"""The rendering layer's finding walk against ``gate.counts`` (card CLI-03).

``gebra.report.findings`` walks §2.1's finding set so each record can be rendered whole. It is
a traversal, not a derivation — CLI-SPEC §0.1 rule 3 keeps the presentation layer from
recomputing what the report carries — but a traversal that disagreed with ``gate.counts`` would
render a different run than the gate describes. So this module holds the two equal, over the
variant catalog *and* over the whole vendored corpus run through the real validators.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07): the corpus is
serialized IR and the validators read it.
"""

from __future__ import annotations

from typing import Any

import pytest

from gebra.report.findings import findings_of, notes_of
from gebra.testing import load_corpus
from gebra.verify import RunPolicy, StrictPolicy, SubjectRef, verify
from gebra.verify.report import PropertyReport
from gebra.verify.run import RunReport
from tests.conftest import FIXTURES_DIR
from tests.report.variants import CASES


def _tally(report: RunReport) -> dict[str, int]:
    counts = {"fatal": 0, "error": 0, "warning": 0}
    for outcome in report.properties:
        if isinstance(outcome, PropertyReport):
            for finding in findings_of(outcome):
                counts[finding.severity] += 1
    return counts


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_walk_agrees_with_the_gate_on_the_catalog(case: Any) -> None:
    counts = case.report.gate.counts
    assert _tally(case.report) == {
        "fatal": counts.fatal,
        "error": counts.error,
        "warning": counts.warning,
    }


def test_the_walk_agrees_with_the_gate_over_the_whole_corpus() -> None:
    """The strongest available cross-check: 60 vendored fixtures, real validators, real gates."""
    corpus = load_corpus(FIXTURES_DIR)
    single = [fixture for fixture in corpus if fixture.ir is not None]
    checked = 0
    for fixture in single:
        assert fixture.ir is not None
        report = verify(
            fixture.ir,
            RunPolicy(
                strict=StrictPolicy(mode="all"),
                subject=SubjectRef(source=str(fixture.fixture_id)),
            ),
        )
        assert report.error is None, f"{fixture.fixture_id}: {report.error}"
        counts = report.gate.counts
        assert _tally(report) == {
            "fatal": counts.fatal,
            "error": counts.error,
            "warning": counts.warning,
        }, fixture.fixture_id
        checked += 1
    # The seven the loop skips are the evolution pairs, which carry `ir_before`/`ir_after`
    # rather than one snapshot — P-12 is a two-snapshot property outside the wedge.
    assert len(corpus) == 71
    assert checked == len(single) == 64


def test_an_advisory_keeps_its_own_owner_and_its_host() -> None:
    """§2.3's easy-to-get-wrong row, as a field pair rather than a comment."""
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    advisories = [
        finding
        for outcome in report.properties
        if isinstance(outcome, PropertyReport)
        for finding in findings_of(outcome)
        if finding.origin == "advisory"
    ]
    assert advisories
    for finding in advisories:
        assert finding.owner != finding.host


def test_notes_ride_both_carriage_paths() -> None:
    """§2.1 with DEC-23: a note rides a passing witness and a failing record alike."""
    passing = next(case.report for case in CASES if case.name == "rich-witnesses")
    failing = next(case.report for case in CASES if case.name == "wedge-failures")
    for report in (passing, failing):
        notes = [
            note
            for outcome in report.properties
            if isinstance(outcome, PropertyReport)
            for note in notes_of(outcome)
        ]
        assert notes, "both carriage paths must surface a note"


def test_a_pass_carries_no_findings() -> None:
    report = CASES[0].report
    assert _tally(report) == {"fatal": 0, "error": 0, "warning": 0}


def test_p04_extras_are_carried_as_evidence() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    evidence = [
        finding.evidence
        for outcome in report.properties
        if isinstance(outcome, PropertyReport)
        for finding in findings_of(outcome)
        if finding.evidence
    ]
    assert evidence
    assert any("gebra/writersOnOtherPaths" in bag for bag in evidence)
    assert any("gebra/downstreamWriters" in bag for bag in evidence)


def test_the_dec_28_p04_diagnostic_is_carried_as_evidence() -> None:
    """DEC-28 clause 2's third diagnostic (report_format 1.2) rides the primary P-04 finding of
    the dynamic-dispatch failure case, keyed for the SARIF property bag like the other two."""
    report = next(case.report for case in CASES if case.name == "dynamic-dispatch-dataflow-failure")
    evidence = [
        finding.evidence
        for outcome in report.properties
        if isinstance(outcome, PropertyReport)
        for finding in findings_of(outcome)
        if finding.evidence
    ]
    assert evidence == [{"gebra/outsideStaticCoverage": ["book_leg"]}]
