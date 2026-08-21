"""The thirteen-slug property registry, and the dispatch it drives.

The acceptance claim here is the one SOW §8 makes on Phase-0's behalf: the eight non-wedge
properties are carried by the registry as **structured not-implemented markers, never silent
passes**. So the tests ask, for every one of the thirteen slugs, what dispatch actually
returns — and check that it is never a report, never ``None``, and never an exception a
caller has to guess the meaning of.

The second claim is that the table is the single source of truth D-09 Deliverable 2 asks for:
thirteen rows, exactly the catalog's slugs, each carrying the claim class, severity and
derivation reference the catalog states, and none of them restating a condition ID the §0.4
registry already owns.

Nothing here executes a workflow, a node, or a network call (WA-07). The stub validator
registered in two tests is a local function that reads nothing and returns a fixed report;
dispatch calling it is the only "execution" in this module.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any, get_args

import pytest

from gebra.ir import WorkflowIR
from gebra.verify import (
    NON_WEDGE_SLUGS,
    PROPERTY_REGISTRY,
    PROPERTY_SLUGS,
    WEDGE_SLUGS,
    ClaimClass,
    NotImplementedMarker,
    PropertyEntry,
    PropertyId,
    PropertyRegistryError,
    PropertyReport,
    PropertySlug,
    Severity,
    WellFormednessWitness,
    conditions_for,
    is_implemented,
    not_implemented,
    property_entry,
    register_validator,
    run_property,
    to_data,
    unregister_validator,
    validator_for,
)

#: The wedge five, as SOW §1 and the board's charter name them.
EXPECTED_WEDGE: tuple[PropertySlug, ...] = (
    "graph-well-formed",
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)


@pytest.fixture
def ir() -> WorkflowIR:
    """The smallest valid IR document — dispatch needs an argument, not a graph."""
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": "a",
                "finish": "a",
                "nodes": [{"id": "a"}],
                "edges": [],
            }
        )
    )


def _stub_report(_: WorkflowIR) -> PropertyReport:
    return PropertyReport.passing(
        "graph-well-formed",
        WellFormednessWitness(
            kind="well-formedness",
            reachable_from_start=("a",),
            terminal_nodes=("a",),
            orphan_nodes=(),
            unresolved_targets=(),
        ),
    )


@pytest.fixture
def clean_registrations() -> Any:
    """No test changes what is wired in — dispatch's answer is global state.

    Restoring rather than clearing: shipped validators register at import (P-08 since
    VAL-04), so dropping every slug would leave the rest of the session dispatching to
    ``not-yet-implemented`` for a property that is in fact implemented.
    """
    shipped = {slug: validator_for(slug) for slug in PROPERTY_SLUGS}
    yield
    for slug, implementation in shipped.items():
        unregister_validator(slug)
        if implementation is not None:
            register_validator(slug, implementation)


# ── The table ────────────────────────────────────────────────────────────────────────────


def test_the_registry_is_exactly_the_thirteen_catalog_slugs() -> None:
    assert set(PROPERTY_SLUGS) == set(get_args(PropertySlug))
    assert len(PROPERTY_SLUGS) == 13
    assert set(PROPERTY_REGISTRY) == set(PROPERTY_SLUGS)


def test_property_ids_are_p01_through_p13_in_catalog_order() -> None:
    ids = [PROPERTY_REGISTRY[slug].property_id for slug in PROPERTY_SLUGS]
    assert ids == list(get_args(PropertyId))


def test_the_wedge_is_the_five_sow_names() -> None:
    """SOW §1 in scope, SOW §8 out — the split the whole Phase-0 plan is built on."""
    assert WEDGE_SLUGS == EXPECTED_WEDGE
    assert set(NON_WEDGE_SLUGS) == set(PROPERTY_SLUGS) - set(EXPECTED_WEDGE)
    assert len(NON_WEDGE_SLUGS) == 8


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_every_row_carries_the_columns_the_brief_asks_for(slug: PropertySlug) -> None:
    """D-09 Deliverable 2: slug → claim class → severity → derivation reference, in one table."""
    entry = PROPERTY_REGISTRY[slug]
    assert entry.slug == slug
    assert entry.claim_classes and set(entry.claim_classes) <= set(get_args(ClaimClass))
    assert entry.severities and set(entry.severities) <= set(get_args(Severity))
    assert entry.derivation.strip()
    assert entry.spec_ref.strip()
    assert entry.wedge == (entry.scope == "phase-0-wedge")


def test_p12_is_the_only_two_snapshot_property() -> None:
    """D-09 in-scope item 5: ``validate(ir_before, ir_after)`` is P-12's shape alone."""
    two = [slug for slug in PROPERTY_SLUGS if PROPERTY_REGISTRY[slug].arity == "two-snapshot"]
    assert two == ["evolution-safety"]


def test_the_wedge_grades_match_the_drafted_sections() -> None:
    """The five §P-nn headers, read back off the table."""
    grades = {
        slug: (PROPERTY_REGISTRY[slug].claim_classes, PROPERTY_REGISTRY[slug].severities)
        for slug in WEDGE_SLUGS
    }
    assert grades == {
        "graph-well-formed": (("defensible",), ("fatal",)),
        "termination-witness": (("defensible",), ("fatal",)),
        "dataflow-completeness": (("defensible-a",), ("fatal",)),
        "effect-safety": (("defensible-a",), ("fatal", "error")),
        "determinism-replay": (("heuristic",), ("warning",)),
    }


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_the_table_restates_no_condition_id(slug: PropertySlug) -> None:
    """Condition IDs live in the §0.4 registry; this table reads them, never copies them."""
    entry = PROPERTY_REGISTRY[slug]
    for held in conditions_for(slug):
        assert held.property_id == entry.property_id
        assert held.id not in entry.derivation


def test_an_unknown_slug_is_refused_by_name() -> None:
    with pytest.raises(PropertyRegistryError, match="thirteen catalog slugs"):
        property_entry("graph-wellformed")


# ── Dispatch: the eight are markers, never silent passes ────────────────────────────────


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_dispatch_answers_every_slug_with_something_structured(
    slug: PropertySlug, ir: WorkflowIR
) -> None:
    """No slug returns ``None``, raises, or quietly passes — the registry answers for all 13."""
    answer = run_property(slug, ir)
    assert answer.property == slug
    if is_implemented(slug):
        assert isinstance(answer, PropertyReport)
        return
    assert isinstance(answer, NotImplementedMarker)
    assert not isinstance(answer, PropertyReport)
    assert answer.property_id == PROPERTY_REGISTRY[slug].property_id
    assert answer.kind == "not-implemented"


@pytest.mark.parametrize("slug", NON_WEDGE_SLUGS)
def test_the_eight_non_wedge_slugs_are_deferred_to_phase_1(
    slug: PropertySlug, ir: WorkflowIR
) -> None:
    """SOW §8 + D-09's stub discipline: a distinct status with a human-readable pointer."""
    marker = run_property(slug, ir)
    assert isinstance(marker, NotImplementedMarker)
    assert marker.status == "deferred-to-phase-1"
    assert slug in marker.detail
    assert "not a pass" in marker.detail
    assert PROPERTY_REGISTRY[slug].spec_ref in marker.detail


@pytest.mark.parametrize("slug", WEDGE_SLUGS)
def test_an_unwired_wedge_slug_says_so_in_its_own_words(slug: PropertySlug, ir: WorkflowIR) -> None:
    """Out-of-scope and not-yet-built are different absences; neither is a verdict.

    A wedge slug whose validator has landed answers with a report instead — the marker is
    the *unwired* case, and which wedge slugs those are shrinks as the VAL cards land. Both
    halves are asserted here, off the registry's own answer rather than off a hand-kept list.
    """
    answer = run_property(slug, ir)
    if is_implemented(slug):
        assert isinstance(answer, PropertyReport)
        assert not isinstance(answer, NotImplementedMarker)
        return
    assert isinstance(answer, NotImplementedMarker)
    assert answer.status == "not-yet-implemented"
    assert "not a pass" in answer.detail


def test_the_wedge_validators_that_have_landed_are_the_ones_wired_in() -> None:
    """The build-order statement, asserted rather than assumed (VAL-04 wired P-08; VAL-05 P-01;
    VAL-09 P-04; VAL-10 P-06; VAL-07 P-02 — the wedge five complete)."""
    assert {slug for slug in WEDGE_SLUGS if is_implemented(slug)} == {
        "dataflow-completeness",
        "determinism-replay",
        "effect-safety",
        "graph-well-formed",
        "termination-witness",
    }
    assert not any(is_implemented(slug) for slug in NON_WEDGE_SLUGS)


def test_a_marker_is_not_a_report_and_carries_no_verdict_field() -> None:
    marker = not_implemented("parallel-safety")
    data = to_data(marker)
    assert set(data) == {"kind", "property", "property_id", "status", "detail"}
    assert "result" not in data and "witness" not in data and "failure" not in data
    assert NotImplementedMarker.model_validate_json(json.dumps(data)) == marker


# ── Dispatch: a registered validator answers instead ─────────────────────────────────────


def test_a_registered_validator_takes_over_dispatch(
    ir: WorkflowIR, clean_registrations: Any
) -> None:
    """The registry drives dispatch: wire a validator in, and the marker gives way to it.

    P-01's real validator registers at import since VAL-05, so the unwired half of the
    transition has to be re-created rather than assumed. ``clean_registrations`` puts the
    shipped one back afterwards.
    """
    unregister_validator("graph-well-formed")
    assert isinstance(run_property("graph-well-formed", ir), NotImplementedMarker)

    register_validator("graph-well-formed", _stub_report)

    assert is_implemented("graph-well-formed")
    assert validator_for("graph-well-formed") is _stub_report
    answer = run_property("graph-well-formed", ir)
    assert isinstance(answer, PropertyReport)
    assert answer.result == "pass"

    unregister_validator("graph-well-formed")
    assert isinstance(run_property("graph-well-formed", ir), NotImplementedMarker)


@pytest.mark.parametrize("slug", NON_WEDGE_SLUGS)
def test_registration_is_refused_for_the_eight(
    slug: PropertySlug, clean_registrations: Any
) -> None:
    """A Phase-1 validator cannot appear at runtime: the table is what puts it out of scope."""
    with pytest.raises(PropertyRegistryError, match="out of Phase-0 scope"):
        register_validator(slug, _stub_report)
    assert not is_implemented(slug)


def test_a_second_registration_is_refused(clean_registrations: Any) -> None:
    """P-02's real validator registers at import since VAL-07, so the free slot is re-made."""
    unregister_validator("termination-witness")
    register_validator("termination-witness", _stub_report)
    with pytest.raises(PropertyRegistryError, match="already has a registered validator"):
        register_validator("termination-witness", _stub_report)


def test_a_validator_answering_for_another_property_is_refused(
    ir: WorkflowIR, clean_registrations: Any
) -> None:
    """One property, one report (§0.3) — a mis-wired validator is caught at the boundary."""
    unregister_validator("termination-witness")
    register_validator("termination-witness", _stub_report)
    with pytest.raises(PropertyRegistryError, match="one property, one report"):
        run_property("termination-witness", ir)


def test_dispatch_refuses_an_unknown_slug(ir: WorkflowIR) -> None:
    with pytest.raises(PropertyRegistryError):
        run_property("graph-wellformed", ir)  # type: ignore[arg-type]


def test_the_entry_is_frozen_data() -> None:
    """The table is a contract surface, not a scratch pad."""
    entry: PropertyEntry = PROPERTY_REGISTRY["effect-safety"]
    with pytest.raises(FrozenInstanceError):
        entry.slug = "graph-well-formed"  # type: ignore[misc]
