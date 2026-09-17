"""The seeded finding under both policies, through the plugin's fixtures — and the fix.

Override ``gebra_workflow`` and ``gebra_graph`` is the extracted IR, ``gebra_verification``
the whole verification run over it under the session's policy. The tests below assert what
the use-cases page prints: P-08 reports the unpinned temperature as a WARNING from a
HEURISTIC property, the default gate stays green with the finding on record, a strict policy
naming this property turns the gate red and leaves the record exactly as it was, and the
pinned variant passes with the provider caveat on its witness. The strict leg is run
in-process over ``gebra_graph`` rather than with ``--gebra-strict`` on the command line, so
``python -m pytest examples/scenarios -q`` — the command CI runs — is green as a suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from examples.scenarios.pipeline_replay.workflow import (
    STRICT_ON_P08,
    build_pipeline_replay,
    build_pipeline_replay_pinned,
)
from gebra.ir import WorkflowIR
from gebra.pytest_plugin import TargetVerification, findings_for, verify_target
from gebra.verify import (
    DeterminismNodeLocation,
    DeterminismWitness,
    PropertyReport,
    RunPolicy,
    verify,
)


@pytest.fixture
def gebra_workflow() -> Any:
    """The scenario's seeded graph — in your repository, your own builder."""
    return build_pipeline_replay()


def test_the_claim_is_reported_and_the_default_gate_stays_green(
    gebra_verification: TargetVerification,
) -> None:
    """WARNING, HEURISTIC: exit 0, ``pass-with-notes``, snapshot still eligible."""
    report = gebra_verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass-with-notes")
    assert report.gate.snapshot_eligible is True
    assert report.gate.promotions == ()

    outcome = report.outcome_for("determinism-replay")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    assert failure.property_condition == "deterministic-llm-temperature-unpinned"
    assert (failure.severity, failure.claim_class) == ("warning", "heuristic")
    assert isinstance(failure.location, DeterminismNodeLocation)
    assert failure.location.node == "extract_fields"
    assert (failure.location.seed, failure.location.temperature) == (7, None)


def test_the_unpinned_claim_is_the_only_finding(gebra_verification: TargetVerification) -> None:
    """One seeded defect, one finding: every other property passes, warning-free."""
    report = gebra_verification.report
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (0, 0, 1)
    for slug in ("graph-well-formed", "termination-witness", "dataflow-completeness"):
        assert findings_for(report, slug) == (), slug
    assert findings_for(report, "effect-safety") == ()
    assert gebra_verification.extraction_notes == ()


def test_a_strict_policy_moves_the_gate_and_not_the_record(
    gebra_graph: WorkflowIR, gebra_verification: TargetVerification
) -> None:
    """``--gebra-strict=determinism-replay``: exit 1, one promotion, the record unchanged."""
    strict = verify(gebra_graph, RunPolicy(strict=STRICT_ON_P08))
    assert (strict.gate.exit_code, strict.gate.outcome) == (1, "fail")
    (promotion,) = strict.gate.promotions
    assert (promotion.property, promotion.origin) == ("determinism-replay", "failure")

    default = gebra_verification.report
    assert strict.gate.counts == default.gate.counts
    assert strict.outcome_for("determinism-replay") == default.outcome_for("determinism-replay")


def test_pinning_the_temperature_clears_the_gate_with_the_caveat() -> None:
    """The fix passes under both policies, and its witness says what a pinned seed is not."""
    name = "pipeline_replay_pinned"
    default = verify_target(build_pipeline_replay_pinned(), name=name, source=__name__)
    strict = verify_target(
        build_pipeline_replay_pinned(), name=name, source=__name__, strict=STRICT_ON_P08
    )
    assert (default.report.gate.exit_code, default.report.gate.outcome) == (0, "pass")
    assert (strict.report.gate.exit_code, strict.report.gate.promotions) == (0, ())

    outcome = default.report.outcome_for("determinism-replay")
    assert isinstance(outcome, PropertyReport)
    assert isinstance(outcome.witness, DeterminismWitness)
    assert outcome.witness.caveat == "provider-seed-reproducibility-not-guaranteed"
    claims = {
        claim.node: (claim.llm_backed, claim.seed, claim.temperature)
        for claim in outcome.witness.claims
    }
    assert claims == {"extract_fields": (True, 7, 0.0), "validate_fields": (False, None, None)}


@pytest.mark.gebra(name="pipeline_replay_pinned")
def test_gebra() -> Any:
    """The fix, gated the way CI gates it: one green item per checked property."""
    return build_pipeline_replay_pinned()
