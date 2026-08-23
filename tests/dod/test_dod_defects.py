"""The five seeded defects, each caught per PD-006 C1 — and the harness negative-tested.

C1's definition of **caught**, asserted here per defect: the variant's verify run reports
the named property failing with the expected condition ID at the seeded locus, and the run
gates exit 1 — for defect 3 under the ``determinism-replay`` per-property promotion, with
the stored record retaining ``severity: warning`` and ``claim_class: heuristic``. The
checker is one plain function (:func:`assert_defect_caught`) used by every positive test,
so the negative tests can hold the *harness itself* to C1's closing sentence: an uncaught
defect fails CI. Each negative hands the checker a report in which the defect is absent —
healthy v1's — and requires the checker to refuse it; the cross-check matrix hands every
variant's report to every *other* defect's checker, which is also where PD-006 R1's rider
("defects 2 and 5 anchor at distinct loci so one finding cannot satisfy both") is
demonstrated rather than declared.

Beside the catches, each variant is held to being *exactly* its seed: extraction is
warning-free, the named property is the only wedge property that fails, and the diff
against v1 pins the seeded edit by name — which slot departed, which label arrived, which
nodes were swapped — so a variant that drifted healthy (or grew a second defect) fails
here before it could quietly weaken the DoD claim.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import pytest

from gebra.diff import workflow_diff
from gebra.verify import CONDITION_REGISTRY, EMITTABLE_CONDITION_IDS, PropertyReport, verify
from gebra.versioning import Component
from tests.sample_workflows import travel_booking_defects as dv

if TYPE_CHECKING:
    from gebra.verify import RunReport

    from .conftest import DodScenario

#: The five wedge slugs — the properties a defect may name (SOW §1).
WEDGE_SLUGS = frozenset(
    (
        "graph-well-formed",
        "termination-witness",
        "dataflow-completeness",
        "effect-safety",
        "determinism-replay",
    )
)


def failing_properties(report: RunReport) -> frozenset[str]:
    """The slugs of every property the report says failed."""
    return frozenset(
        outcome.property
        for outcome in report.properties
        if isinstance(outcome, PropertyReport) and outcome.result == "fail"
    )


def assert_defect_caught(
    defect: dv.DefectVariant, report: RunReport, strict_report: RunReport
) -> None:
    """C1's per-defect obligation: named property + condition ID + locus + gate.

    Raises ``AssertionError`` when any part of the catch is missing — which is the whole
    point: the positive tests call it over the variants' reports, and the negative tests
    call it over reports the defect is absent from and require the refusal.
    """
    outcome = report.outcome_for(defect.property)
    assert isinstance(outcome, PropertyReport), (
        f"{defect.name}: {defect.property} reached no verdict"
    )
    assert outcome.result == "fail", f"{defect.name}: {defect.property} did not fail"
    failure = outcome.failure
    assert failure is not None
    assert failure.property_condition == defect.condition, defect.name
    assert failure.severity == defect.severity, defect.name

    location = failure.location
    if len(defect.locus_nodes) > 1:
        assert location.kind == "scc", defect.name
        assert frozenset(getattr(location, "nodes", ())) == frozenset(defect.locus_nodes), (
            defect.name
        )
    else:
        assert getattr(location, "node", None) == defect.locus_nodes[0], defect.name
    if defect.state_key is not None:
        assert getattr(location, "key", None) == defect.state_key, defect.name
    if defect.fanout_send:
        assert getattr(location, "fanout", None) == "send", defect.name

    assert report.gate.exit_code == defect.default_exit, defect.name
    if defect.strict_slug is None:
        assert report.gate.exit_code == 1, defect.name
    else:
        # R2: the gate moves under the per-property promotion; the record never does.
        assert strict_report.gate.exit_code == 1, defect.name
        assert any(
            promotion.property == defect.property
            and promotion.property_condition == defect.condition
            for promotion in strict_report.gate.promotions
        ), defect.name
        assert failure.claim_class == "heuristic", defect.name


@pytest.fixture(params=dv.DEFECTS, ids=[defect.name for defect in dv.DEFECTS])
def defect(request: pytest.FixtureRequest) -> dv.DefectVariant:
    """One row of the recorded defect table."""
    variant: dv.DefectVariant = request.param
    return variant


# ── The catches — acceptance box 2 ────────────────────────────────────────────────────────


def test_the_defect_is_caught_by_its_named_property(
    defect: dv.DefectVariant, dod: DodScenario
) -> None:
    """Each seeded defect satisfies C1's catch definition on its own verify run."""
    assert_defect_caught(
        defect, dod.defect_reports[defect.name], dod.defect_strict_reports[defect.name]
    )


def test_the_named_property_is_the_only_failing_property(
    defect: dv.DefectVariant, dod: DodScenario
) -> None:
    """One seed, one signal: no variant fails any wedge property but its named one."""
    assert failing_properties(dod.defect_reports[defect.name]) == {defect.property}


def test_every_variant_extracts_warning_free(defect: dv.DefectVariant, dod: DodScenario) -> None:
    """The seed is a verify-time fact, not an extraction complaint — no warning rides it."""
    assert dod.defect_envelopes[defect.name].warnings == ()


def test_the_expected_conditions_are_emittable_registry_entries() -> None:
    """The defect-5 rider, held for all five: every expected ID is **emittable** today.

    Emittability, not membership — ``ConditionId`` deliberately spells the whole §0.4
    registry, RESERVED and unratified-PROPOSED strings included, so a membership test
    would wave through exactly the P-09 temptation the rider was written against. The
    registry's own emittable tier is the guard, and the table's per-row grade and owner
    are read **off the registry** rather than restated: a row disagreeing with §0.4's
    columns fails here before any verify run is consulted.
    """
    emittable = frozenset(EMITTABLE_CONDITION_IDS)
    for defect in dv.DEFECTS:
        assert defect.condition in emittable, defect.name
        entry = CONDITION_REGISTRY[defect.condition]
        assert entry.property_slug == defect.property, defect.name
        assert entry.severity == defect.severity, defect.name
        assert defect.property in WEDGE_SLUGS, defect.name


def test_the_gate_side_effects_follow_the_severity_ladder(
    defect: dv.DefectVariant, dod: DodScenario
) -> None:
    """§0.2's recording rule, asserted per variant: a FATAL alone withdraws snapshot
    eligibility, and an ERROR or WARNING — gate-blocking or not — never does."""
    report = dod.defect_reports[defect.name]
    assert report.gate.snapshot_eligible == (defect.severity != "fatal"), defect.name
    assert report.gate.snapshot_eligible == (report.gate.counts.fatal == 0), defect.name


def test_defects_two_and_five_anchor_at_distinct_loci(dod: DodScenario) -> None:
    """PD-006 R1's rider: one finding cannot satisfy both P-06 defects.

    Asserted on the reports rather than only on the table: the two catches share a
    condition ID, so the loci are what tells them apart — different nodes, and only the
    fan-out's carrying the ``fanout: send`` evidence.
    """
    two, five = dv.DEFECTS[1], dv.DEFECTS[4]
    assert two.locus_nodes != five.locus_nodes

    def locus(name: str) -> tuple[object, object]:
        outcome = dod.defect_reports[name].outcome_for("effect-safety")
        assert isinstance(outcome, PropertyReport) and outcome.failure is not None
        location = outcome.failure.location
        return getattr(location, "node", None), getattr(location, "fanout", None)

    assert locus(two.name) == ("book_flight", None)
    assert locus(five.name) == ("book_leg", "send")


def test_defect_three_keeps_its_record_under_promotion(dod: DodScenario) -> None:
    """R2 verbatim: promotion changes the gate, never the record.

    The default and strict runs must carry byte-equal property records — the WARNING
    severity and HEURISTIC claim class included — while only the gate differs.
    """
    name = dv.DEFECTS[2].name
    default, strict = dod.defect_reports[name], dod.defect_strict_reports[name]

    assert default.gate.exit_code == 0 and default.gate.outcome == "pass-with-notes"
    assert strict.gate.exit_code == 1 and strict.gate.outcome == "fail"
    assert [outcome.model_dump() for outcome in default.properties] == [
        outcome.model_dump() for outcome in strict.properties
    ]
    assert default.gate.counts == strict.gate.counts
    assert default.gate.counts.warning >= 1 and default.gate.counts.blocking == 0


def test_the_promotion_moves_no_other_variants_gate(dod: DodScenario) -> None:
    """The strict leg is surgical: under ``determinism-replay`` promotion, every other
    variant's exit code is what it already was, and healthy v1 stays 0 — so a defect-3
    catch can never be an artifact of the policy alone."""
    assert dod.healthy_strict_report.gate.exit_code == 0
    assert dod.healthy_strict_report.gate.promotions == ()
    for defect in dv.DEFECTS:
        if defect.strict_slug is not None:
            continue
        strict = dod.defect_strict_reports[defect.name]
        assert strict.gate.exit_code == dod.defect_reports[defect.name].gate.exit_code
        assert strict.gate.promotions == ()


# ── The negatives — acceptance box 3 ──────────────────────────────────────────────────────


def test_an_uncaught_defect_fails_the_harness(defect: dv.DefectVariant, dod: DodScenario) -> None:
    """C1's closing sentence, executed: a report the defect is absent from is refused.

    Healthy v1's report is exactly what every variant's report would look like if a
    regression stopped its defect being caught — the named property passing, no finding,
    exit 0 — so the checker must raise on it, which is what makes an uncaught defect a red
    CI rather than a silent pass.
    """
    with pytest.raises(AssertionError):
        assert_defect_caught(defect, dod.stage_reports[0], dod.healthy_strict_report)


def test_no_other_variants_report_satisfies_a_defects_checker(dod: DodScenario) -> None:
    """Every catch is specific: variant X's report never satisfies defect Y's checker."""
    for expected, actual in itertools.permutations(dv.DEFECTS, 2):
        with pytest.raises(AssertionError):
            assert_defect_caught(
                expected,
                dod.defect_reports[actual.name],
                dod.defect_strict_reports[actual.name],
            )


def test_the_checker_goes_red_on_a_doctored_catch(dod: DodScenario) -> None:
    """The armed control for the checker's own fields: a report whose finding is real but
    whose *expectation* is wrong (right property, wrong condition / wrong locus) is
    refused — so the checker demonstrably reads condition and locus, not only the gate."""
    real = dv.DEFECTS[1]
    wrong_condition = dv.DefectVariant(
        number=real.number,
        name=real.name,
        build=real.build,
        property=real.property,
        condition="unprotected-effect-in-cycle",
        severity=real.severity,
        locus_nodes=real.locus_nodes,
        state_key=None,
        fanout_send=False,
        strict_slug=None,
        default_exit=1,
        summary=real.summary,
    )
    wrong_locus = dv.DefectVariant(
        number=real.number,
        name=real.name,
        build=real.build,
        property=real.property,
        condition=real.condition,
        severity=real.severity,
        locus_nodes=("book_hotel",),
        state_key=None,
        fanout_send=False,
        strict_slug=None,
        default_exit=1,
        summary=real.summary,
    )
    report = dod.defect_reports[real.name]
    strict = dod.defect_strict_reports[real.name]
    with pytest.raises(AssertionError):
        assert_defect_caught(wrong_condition, report, strict)
    with pytest.raises(AssertionError):
        assert_defect_caught(wrong_locus, report, strict)


# ── The seed is exactly one edit — each variant pinned against v1 by content ─────────────


def test_defect_1_departs_exactly_the_variant_slot(dod: DodScenario) -> None:
    """v1 → defect 1: one contract changed, one slot departed, nothing else anywhere."""
    diff = workflow_diff(dod.stage_envelopes[0].ir, dod.defect_envelopes[dv.DEFECTS[0].name].ir)
    assert diff.bump_class == frozenset({Component.F})
    (changed,) = diff.contracts.changed
    assert changed.node == "replan"
    (slot,) = changed.slots
    assert slot.slot == "variant" and slot.before is not None and slot.after is None
    assert not diff.contracts.added and not diff.contracts.removed
    assert not (diff.state.added or diff.state.removed or diff.state.changed)


def test_defect_2_departs_exactly_the_idempotent_slot(dod: DodScenario) -> None:
    """v1 → defect 2: ``book_flight`` loses ``idempotent`` and nothing else moves."""
    diff = workflow_diff(dod.stage_envelopes[0].ir, dod.defect_envelopes[dv.DEFECTS[1].name].ir)
    assert diff.bump_class == frozenset({Component.F})
    (changed,) = diff.contracts.changed
    assert changed.node == "book_flight"
    (slot,) = changed.slots
    assert slot.slot == "idempotent" and slot.before is not None and slot.after is None


def test_defect_3_changes_exactly_the_deterministic_slot(dod: DodScenario) -> None:
    """v1 → defect 3: the claim object loses its ``temperature`` member, in place."""
    diff = workflow_diff(dod.stage_envelopes[0].ir, dod.defect_envelopes[dv.DEFECTS[2].name].ir)
    assert diff.bump_class == frozenset({Component.F})
    (changed,) = diff.contracts.changed
    assert changed.node == "classify_request"
    (slot,) = changed.slots
    assert slot.slot == "deterministic"
    assert slot.before is not None and slot.after is not None
    assert "temperature" in slot.before and "temperature" not in slot.after


def test_defect_4_adds_exactly_the_express_label(dod: DodScenario) -> None:
    """v1 → defect 4: one conditional edge arrives under the unchanged router; the two
    persisting endpoints report rewired; no contract and no Σ movement."""
    diff = workflow_diff(dod.stage_envelopes[0].ir, dod.defect_envelopes[dv.DEFECTS[3].name].ir)
    assert diff.bump_class == frozenset({Component.S})
    (added,) = diff.topology.edges.added
    assert added.kind == "conditional"
    assert added.source == "availability_check" and added.target == "notify_traveler"
    assert added.label == "express" and added.condition == "route_availability"
    assert not diff.topology.edges.removed and not diff.topology.edges.changed
    assert diff.topology.nodes.rewired == ("availability_check", "notify_traveler")
    assert not diff.contracts.changed and not diff.contracts.added
    assert not (diff.state.added or diff.state.removed or diff.state.changed)


def test_defect_5_swaps_the_serial_bookings_for_the_fanout(dod: DodScenario) -> None:
    """v1 → defect 5: two nodes out, two in, one ``send`` template edge under the new
    router — and Σ untouched, so the variant's whole story is topology + contracts."""
    diff = workflow_diff(dod.stage_envelopes[0].ir, dod.defect_envelopes[dv.DEFECTS[4].name].ir)
    assert diff.bump_class == frozenset({Component.S, Component.F})
    assert diff.topology.nodes.added == ("book_leg", "dispatch_bookings")
    assert diff.topology.nodes.removed == ("book_flight", "book_hotel")
    send_edges = [edge for edge in diff.topology.edges.added if edge.kind == "send"]
    (send,) = send_edges
    assert send.source == "dispatch_bookings" and send.target == "book_leg"
    assert send.condition == "route_legs"
    assert not (diff.state.added or diff.state.removed or diff.state.changed)


# ── Table coherence — asserted before any engine is trusted ───────────────────────────────


def test_the_recorded_table_is_coherent() -> None:
    """Five rows in SOW order, unique names and builders, loci stated for every row."""
    assert tuple(defect.number for defect in dv.DEFECTS) == (1, 2, 3, 4, 5)
    assert len({defect.name for defect in dv.DEFECTS}) == 5
    assert len({defect.build for defect in dv.DEFECTS}) == 5
    for defect in dv.DEFECTS:
        assert defect.locus_nodes, defect.name
        assert defect.severity in {"fatal", "error", "warning"}, defect.name
        assert defect.default_exit in {0, 1}, defect.name
        # A WARNING-severity defect needs R2's strict leg; blocking ones must not.
        assert (defect.strict_slug is not None) == (defect.severity == "warning"), defect.name


def test_a_fresh_verify_run_agrees_with_the_scenario(dod: DodScenario) -> None:
    """The scenario's cached reports are what a fresh run answers — no fixture staleness."""
    defect = dv.DEFECTS[0]
    fresh = verify(dod.defect_envelopes[defect.name].ir)
    assert fresh.gate.exit_code == dod.defect_reports[defect.name].gate.exit_code
    assert failing_properties(fresh) == failing_properties(dod.defect_reports[defect.name])
