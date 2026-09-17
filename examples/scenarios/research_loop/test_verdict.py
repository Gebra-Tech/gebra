"""The seeded finding, asserted through the plugin's fixtures — and the fix, gated green.

Override ``gebra_workflow`` and ``gebra_verification`` is the whole verification run over
the scenario's graph. The tests below assert what the use-cases page prints: P-02 reports the
loop's component with no witness, it is the run's only finding, and the same wiring with the
variant-carrying node clears the gate. Nothing here is red on purpose — the seeded graph is
verified through the fixture and asserted to fail, and only the bounded variant is marked —
so ``python -m pytest examples/scenarios -q`` is green as a suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from examples.scenarios.research_loop.workflow import (
    build_research_loop,
    build_research_loop_bounded,
)
from gebra.pytest_plugin import TargetVerification, findings_for, verify_target
from gebra.verify import (
    NodeLocation,
    P02SccLocation,
    PropertyReport,
    TerminationWitness,
    VariantSource,
)


@pytest.fixture
def gebra_workflow() -> Any:
    """The scenario's seeded graph — in your repository, your own builder."""
    return build_research_loop()


def test_the_loop_carries_no_termination_witness(gebra_verification: TargetVerification) -> None:
    """FATAL, DEFENSIBLE, on the three-node component — witness absence, nothing more."""
    report = gebra_verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.snapshot_eligible is False

    outcome = report.outcome_for("termination-witness")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    assert failure.property_condition == "cycle-without-termination-witness"
    assert (failure.severity, failure.claim_class) == ("fatal", "defensible")
    assert isinstance(failure.location, P02SccLocation)
    assert failure.location.nodes == ("draft", "reflect", "search")
    assert failure.location.representative_cycle == ("draft", "reflect", "search")


def test_the_missing_witness_is_the_only_finding(gebra_verification: TargetVerification) -> None:
    """One seeded defect, one finding: every other property passes, warning-free."""
    report = gebra_verification.report
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (1, 0, 0)
    for slug in ("graph-well-formed", "dataflow-completeness", "effect-safety"):
        assert findings_for(report, slug) == (), slug
    assert findings_for(report, "determinism-replay") == ()
    assert gebra_verification.extraction_notes == ()


def test_the_bounded_variant_clears_the_gate() -> None:
    """The fix: one variant on ``reflect`` discharges every simple cycle through it."""
    verification = verify_target(
        build_research_loop_bounded(), name="research_loop_bounded", source=__name__
    )
    report = verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")

    outcome = report.outcome_for("termination-witness")
    assert isinstance(outcome, PropertyReport)
    assert isinstance(outcome.witness, TerminationWitness)
    (entry,) = outcome.witness.inventory
    assert entry.form == "c"
    assert isinstance(entry.element, NodeLocation) and entry.element.node == "reflect"
    assert isinstance(entry.source, VariantSource) and entry.source.variant.key == "budget"
    assert entry.discharges == "all-simple-cycles-through-element"


@pytest.mark.gebra(name="research_loop_bounded")
def test_gebra() -> Any:
    """The fix, gated the way CI gates it: one green item per checked property."""
    return build_research_loop_bounded()
