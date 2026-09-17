"""The seeded finding, asserted through the plugin's fixtures — and the fix, gated green.

Override ``gebra_workflow`` and ``gebra_verification`` is the whole verification run over
the scenario's graph. The tests below assert what the use-cases page prints: P-04 names the
reader, the key and the path that arrives without it, it is the run's only finding, and the
wiring that summarises before routing clears the gate. Nothing here is red on purpose — the
seeded graph is verified through the fixture and asserted to fail, and only the fixed wiring
is marked — so ``python -m pytest examples/scenarios -q`` is green as a suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from examples.scenarios.support_triage.workflow import (
    build_support_triage,
    build_support_triage_summary_first,
)
from gebra.pytest_plugin import TargetVerification, findings_for, verify_target
from gebra.verify import DataflowLocation, DataflowWitness, P04Failure, PropertyReport


@pytest.fixture
def gebra_workflow() -> Any:
    """The scenario's seeded graph — in your repository, your own builder."""
    return build_support_triage()


def test_the_escalation_reads_a_key_its_path_never_writes(
    gebra_verification: TargetVerification,
) -> None:
    """FATAL, DEFENSIBLE-A, at the reader and the key, with the path and the other writer."""
    report = gebra_verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.snapshot_eligible is False

    outcome = report.outcome_for("dataflow-completeness")
    assert isinstance(outcome, PropertyReport) and isinstance(outcome.failure, P04Failure)
    failure = outcome.failure
    assert failure.property_condition == "read-key-never-written-on-path"
    assert (failure.severity, failure.claim_class) == ("fatal", "defensible-a")
    assert isinstance(failure.location, DataflowLocation)
    assert (failure.location.node, failure.location.key) == ("escalate", "summary")
    assert failure.location.path == ("START", "classify", "escalate")
    assert failure.writers_on_other_paths == ("summarize",)


def test_the_unwritten_read_is_the_only_finding(gebra_verification: TargetVerification) -> None:
    """One seeded defect, one finding: every other property passes, warning-free."""
    report = gebra_verification.report
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (1, 0, 0)
    for slug in ("graph-well-formed", "termination-witness", "effect-safety"):
        assert findings_for(report, slug) == (), slug
    assert findings_for(report, "determinism-replay") == ()
    assert gebra_verification.extraction_notes == ()


def test_summarising_first_clears_the_gate() -> None:
    """The fix: every path to ``escalate`` now passes through ``summarize``."""
    verification = verify_target(
        build_support_triage_summary_first(), name="support_triage_summary_first", source=__name__
    )
    report = verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")

    outcome = report.outcome_for("dataflow-completeness")
    assert isinstance(outcome, PropertyReport)
    assert isinstance(outcome.witness, DataflowWitness)
    covered = {
        (entry.node, entry.key): entry.satisfied_by
        for entry in outcome.witness.coverage
        if entry.node == "escalate"
    }
    assert covered == {
        ("escalate", "category"): ("classify",),
        ("escalate", "summary"): ("summarize",),
    }


@pytest.mark.gebra(name="support_triage_summary_first")
def test_gebra() -> Any:
    """The fix, gated the way CI gates it: one green item per checked property."""
    return build_support_triage_summary_first()
