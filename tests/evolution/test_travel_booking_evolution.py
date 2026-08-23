"""SD-08's two acceptance boxes — the travel-booking evolution sequence, end to end.

The sequence itself, and the expectations this suite enforces, live in
``tests/sample_workflows/travel_booking_evolution.py`` — eight builder-level versions of the
TE-05 agent covering brief D-11's three safe-extension shapes and the three canonical
breaking cases, with the expected V.S.F.E label and bump class recorded per stage (PD-006
R4's "expected S/F/E classes recorded with the scenario"). This file is the regression test
the card's second box asks for, and its claims are:

1. **Recording the sequence assigns exactly the recorded labels** — ``gebra.snapshot`` over
   each stage in order lands every version at its expected label with its expected bump
   class, the store's history and lineage agree, and every snapshot reloads to the IR it was
   made from.
2. **Every version-pair diff derives exactly the expected classes** — consecutive pairs by
   name with their delta *content* pinned (which key, which node, which slot), then all
   twenty-eight pairs against the union the no-reversion design makes expected, in both
   directions, with the deferred-P-12 marker on every diff and no other movement anywhere.
3. **The eligibility boundary SD-09's pipeline inherits is pinned** — v1–v6 verify clean
   and snapshot-eligible; v7–v8 carry the catalog's FATAL
   ``cycle-without-termination-witness``, so PROPERTY-CATALOG-SPEC §0.2 withdraws their
   recording eligibility, and the sequence stores all eight only through the recorder's
   documented handed-none-records posture — which is how this suite records it.
   Per-version re-verification and audit export are SD-09's own scope (PD-006 R5).
4. **Nothing in any stage runs** (WA-07). Every body in the family raises if called, the
   shared ledger is asserted empty on entry to and exit from every test, every new body is
   fired once through the built graph to prove the guard live, and the whole eight-stage
   extract → snapshot sequence is re-run in a fresh interpreter where name resolution,
   connection opening, socket construction and ``StateGraph.compile`` all raise — each
   raiser armed by a control that proves it can go red.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from gebra import extract
from gebra.diff import (
    EVOLUTION_SAFETY_DEFERRED,
    EdgeRef,
    KeyDeclaration,
    NodesDelta,
    StateKeyRef,
    WiringDelta,
    workflow_diff,
)
from gebra.ir.canonical import graph_version
from gebra.ir.models import WorkflowIR
from gebra.lineage import lineage
from gebra.snapshot import SnapshotAction, SnapshotOutcome, snapshot
from gebra.store import SnapshotStore
from gebra.verify import PropertyReport, verify
from gebra.versioning import Component, Version
from tests.sample_workflows import travel_booking as tb
from tests.sample_workflows import travel_booking_evolution as evo

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every body the evolution module defines — twelve node bodies and two routers, the
#: superseded twins (``replan``, ``check_booking``) included. The arming test requires each
#: to be seen fired through a built graph.
EVOLUTION_BODY_LABELS = frozenset(
    f"travel-booking-evolution.{name}"
    for name in (
        "classify_request",
        "availability_check",
        "replan",
        "replan_unwitnessed",
        "book_flight",
        "book_hotel",
        "check_booking",
        "check_booking_metered",
        "compile_itinerary",
        "notify_traveler",
        "release_hotel_hold",
        "join_waitlist",
        "route_availability",
        "route_booking",
    )
)


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Any:
    """The sequence is read, never run — asserted on entry to and exit from every test.

    Entry as well as exit, for the reason ``tests/testing/test_travel_booking.py`` records:
    module-scoped fixtures run before the first test's own setup, so a fixture that
    *cleared* the ledger here would erase exactly the evidence it exists to keep. The one
    test that fires bodies on purpose restores the ledger itself, the way the TE-05 arming
    test does.
    """
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


def _instant(index: int) -> datetime:
    """The injected clock: one fixed instant per stage, so recording is a pure function."""
    return datetime(2026, 8, 22, 12, 0, index, tzinfo=timezone.utc)


def _source(stage: evo.EvolutionStage) -> str:
    """The CLI-SPEC §2.1-shaped subject reference a caller who knows the builder records."""
    return f"{stage.build.__module__}:{stage.build.__qualname__}"


def _record_sequence(root: Path) -> tuple[SnapshotStore, tuple[SnapshotOutcome, ...]]:
    """Record the whole sequence, v1 first, into a fresh store under ``root``."""
    store = SnapshotStore.for_project(root)
    outcomes = tuple(
        snapshot(
            stage.build(),
            store=store,
            source=_source(stage),
            extracted_at=_instant(index),
        )
        for index, stage in enumerate(evo.EVOLUTION)
    )
    return store, outcomes


@pytest.fixture(scope="module")
def irs() -> tuple[WorkflowIR, ...]:
    """One extraction per stage — the eight documents every diff in this file is over."""
    return tuple(extract(stage.build()).ir for stage in evo.EVOLUTION)


@pytest.fixture(scope="module")
def evolved(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[SnapshotStore, tuple[SnapshotOutcome, ...]]:
    """The sequence recorded once, in order — the store the read-only tests share."""
    return _record_sequence(tmp_path_factory.mktemp("evolution"))


# ── The recorded expectations are coherent before any engine is consulted ─────────────────


def test_the_recorded_expectations_are_self_consistent() -> None:
    """The table's own arithmetic: each label is its predecessor bumped by its class.

    Held by ``gebra.versioning`` alone — no extraction, no diff — so a hand edit to the
    fixture module's table that breaks V.S.F.E arithmetic fails here with the table named,
    rather than downstream as an engine "mismatch". Also the card's floor: N ≥ 5.
    """
    assert len(evo.EVOLUTION) >= 5
    assert len({stage.name for stage in evo.EVOLUTION}) == len(evo.EVOLUTION)

    first = evo.EVOLUTION[0]
    assert first.expected_version == str(Version.initial())
    assert first.expected_bump == frozenset()

    for previous, stage in zip(evo.EVOLUTION, evo.EVOLUTION[1:], strict=False):
        assert stage.expected_bump, stage.name
        bumped = Version.parse(previous.expected_version).bump(*stage.expected_bump)
        assert str(bumped) == stage.expected_version, stage.name


def test_the_sequence_covers_what_the_card_names() -> None:
    """The card's coverage clause, read off the recorded classes rather than off prose.

    Safe extensions AND the three canonical breaking cases means, structurally: at least one
    stage per D-11 safe shape (E for the new optional key, S+F for the new wired node, S for
    the new guarded edge) and the four breaking-case stages (E removal, E retype, F witness,
    F escalation) — every one present in the table by name, and each single component moved
    alone by at least one stage.
    """
    classes = {stage.name: stage.expected_bump for stage in evo.EVOLUTION}

    assert classes["v2-seat-preference"] == frozenset({Component.E})
    assert classes["v3-waitlist-node"] == frozenset({Component.S, Component.F})
    assert classes["v4-waitlist-shortcut"] == frozenset({Component.S})
    assert classes["v5-itinerary-dropped"] == frozenset({Component.E})
    assert classes["v6-availability-retyped"] == frozenset({Component.E})
    assert classes["v7-witness-removed"] == frozenset({Component.F})
    assert classes["v8-billable-confirmation"] == frozenset({Component.F})

    moved_alone = {bump for bump in classes.values() if len(bump) == 1}
    assert moved_alone == {
        frozenset({Component.S}),
        frozenset({Component.F}),
        frozenset({Component.E}),
    }


# ── Acceptance: the sequence snapshots under the expected labels ──────────────────────────


def test_the_sequence_records_under_the_expected_labels(
    evolved: tuple[SnapshotStore, tuple[SnapshotOutcome, ...]],
    irs: tuple[WorkflowIR, ...],
) -> None:
    """Eight recordings, each landing at its recorded label with its recorded bump class.

    The engine is held to the fixture module's table on every outcome member the label
    derivation touches: action, label, bump class, the previous-version chain, and the
    digest — the digest recomputed here from an independent extraction of the same stage,
    not read back off the store.
    """
    store, outcomes = evolved

    for index, (stage, outcome) in enumerate(zip(evo.EVOLUTION, outcomes, strict=True)):
        assert outcome.action is SnapshotAction.RECORDED, stage.name
        assert outcome.version == stage.expected_version, stage.name
        assert outcome.bump_class == stage.expected_bump, stage.name
        assert outcome.graph_version == graph_version(irs[index]), stage.name
        if index == 0:
            assert outcome.first and outcome.previous is None and outcome.diff is None
        else:
            assert outcome.previous == evo.EVOLUTION[index - 1].expected_version, stage.name
            assert outcome.diff is not None and outcome.diff.has_changes, stage.name

    assert store.versions() == tuple(stage.expected_version for stage in evo.EVOLUTION)
    assert store.read_meta().current == evo.EVOLUTION[-1].expected_version
    assert store.check().ok


def test_each_snapshot_reloads_to_the_ir_it_was_made_from(
    evolved: tuple[SnapshotStore, tuple[SnapshotOutcome, ...]],
    irs: tuple[WorkflowIR, ...],
) -> None:
    """D-11's DoD line, over the whole sequence: every stored file reloads to its source.

    Model equality against a fresh, independent extraction of the same stage — so the claim
    covers extract → envelope → emit → disk → parse for all eight versions, not only v1
    (which ``tests/snapshot/test_travel_booking.py`` already holds).
    """
    store, _ = evolved

    for index, stage in enumerate(evo.EVOLUTION):
        reloaded = store.read(stage.expected_version)
        assert reloaded.ir == irs[index], stage.name
        assert reloaded.extracted_from.source == _source(stage), stage.name


def test_the_lineage_lists_the_sequence_with_its_movement_per_step(
    evolved: tuple[SnapshotStore, tuple[SnapshotOutcome, ...]],
) -> None:
    """The store's own history query tells the same story the table records.

    ``lineage()`` derives each step's movement from the *labels* (SD-06), so this is the
    independent answer: the arithmetic the labels record must equal the class the diff
    derived, stage for stage, in label order — V never among them.
    """
    store, _ = evolved
    listing = lineage(store)

    assert listing.total == len(evo.EVOLUTION)
    assert tuple(entry.version for entry in listing.entries) == tuple(
        stage.expected_version for stage in evo.EVOLUTION
    )
    assert listing.entries[0].step is None
    assert listing.entries[-1].is_current

    for entry, stage in zip(listing.entries[1:], evo.EVOLUTION[1:], strict=True):
        assert entry.step is not None, stage.name
        expected_in_label_order = tuple(
            component
            for component in (Component.V, Component.S, Component.F, Component.E)
            if component in stage.expected_bump
        )
        assert entry.step.bump_class == expected_in_label_order, stage.name
        assert entry.step.content_changed, stage.name
        assert entry.step.decreased == (), stage.name


def test_two_independent_recordings_write_one_store(tmp_path: Path) -> None:
    """The whole scenario is a function of its arguments: run it twice, get one store.

    Every builder call constructs a fresh graph and the clock is injected, so two full
    recordings of the sequence must agree byte for byte — SD-01's determinism rules
    observed across the eight-version scenario rather than on one file.
    """
    first_store, _ = _record_sequence(tmp_path / "one")
    second_store, _ = _record_sequence(tmp_path / "two")

    first = {
        path.relative_to(first_store.path): path.read_bytes()
        for path in sorted(first_store.path.rglob("*"))
        if path.is_file()
    }
    second = {
        path.relative_to(second_store.path): path.read_bytes()
        for path in sorted(second_store.path.rglob("*"))
        if path.is_file()
    }
    assert first == second
    assert len(first) == len(evo.EVOLUTION) + 1  # eight snapshots and one index


# ── Acceptance: every version-pair diff derives the expected classes ──────────────────────


def test_every_consecutive_diff_derives_the_expected_class_in_both_directions(
    irs: tuple[WorkflowIR, ...],
) -> None:
    """The seven neighbouring pairs, forward and reversed, against the recorded classes.

    A bump class names domains that moved, not a direction they moved in (SD-05), so the
    reversed diff must derive the same class — and every diff carries the property
    registry's deferred-P-12 marker, which is the PD-006 R4 checklist §S2 obligation on
    this scenario's output.
    """
    for index in range(1, len(irs)):
        stage = evo.EVOLUTION[index]
        forward = workflow_diff(irs[index - 1], irs[index])
        reversed_diff = workflow_diff(irs[index], irs[index - 1])

        assert forward.bump_class == stage.expected_bump, stage.name
        assert reversed_diff.bump_class == stage.expected_bump, stage.name
        assert forward.evolution_safety is EVOLUTION_SAFETY_DEFERRED, stage.name
        assert not forward.identical and forward.has_changes, stage.name


def test_every_pair_derives_the_union_of_its_steps(irs: tuple[WorkflowIR, ...]) -> None:
    """All twenty-eight pairs, not only neighbours — the whole-scenario regression net.

    No stage reverts an earlier stage's edit (the fixture module's stated design), so for
    any i < j the components that moved between stages i and j are exactly the union of the
    per-step classes — in both directions, since a bump class names domains and not a
    direction — with the deferred-P-12 marker on every one of them, and an identical pair
    derives nothing. This is where an accidental revert, a copy drift between two builders,
    or an engine under-report would surface even if every neighbouring diff looked right.
    """
    for i in range(len(irs)):
        assert workflow_diff(irs[i], irs[i]).identical
        for j in range(i + 1, len(irs)):
            expected: frozenset[Component] = frozenset()
            for step in range(i + 1, j + 1):
                expected |= evo.EVOLUTION[step].expected_bump
            pair = workflow_diff(irs[i], irs[j])
            assert pair.bump_class == expected, (i, j)
            assert workflow_diff(irs[j], irs[i]).bump_class == expected, (i, j)
            assert pair.evolution_safety is EVOLUTION_SAFETY_DEFERRED, (i, j)


# ── The named deltas: what each step is, pinned by content ────────────────────────────────


def test_v2_adds_one_optional_state_key_and_nothing_else(irs: tuple[WorkflowIR, ...]) -> None:
    """D-11's "new optional state keys" extension: E alone, and the E delta is one key.

    The arriving declaration carries ``optional: true`` — the graph-input fact PD-021 D1
    makes the extraction record — and no other delta member moves anywhere in the diff.
    The empty contracts delta carries extra weight on this pair: v2 swaps every node and
    router *function* for the evolution module's schema-neutral twins, so contracts being
    byte-equal across the swap is asserted here, not assumed from sharing objects.
    """
    diff = workflow_diff(irs[0], irs[1])

    assert diff.bump_class == frozenset({Component.E})
    assert diff.state.added == (
        StateKeyRef(key="seat_preference", declaration=KeyDeclaration(type="str", optional=True)),
    )
    assert diff.state.removed == () and diff.state.changed == ()
    assert diff.state.present_before and diff.state.present_after
    assert not diff.contracts
    assert not diff.topology.has_changes and not diff.regrouped


def test_v3_adds_a_wired_contracted_node_and_widens_the_finish_set(
    irs: tuple[WorkflowIR, ...],
) -> None:
    """D-11's "new nodes" + "new guarded edges" extension: S and F, each for a named reason.

    S: one added conditional edge under ``route_booking``'s existing condition — which also
    marks the persisting ``check_booking`` rewired, its outgoing set having grown — and the
    finish wiring widened to ``join_waitlist``. F: exactly the arriving node's contract,
    with all three declared slots in its canonical text. Σ does not move.
    """
    diff = workflow_diff(irs[1], irs[2])

    assert diff.bump_class == frozenset({Component.S, Component.F})
    assert diff.topology.nodes == NodesDelta(added=("join_waitlist",), rewired=("check_booking",))
    assert diff.topology.edges.added == (
        EdgeRef(
            kind="conditional",
            source="check_booking",
            target="join_waitlist",
            label="waitlist",
            condition="route_booking",
        ),
    )
    assert diff.topology.edges.removed == () and diff.topology.edges.changed == ()
    assert diff.topology.entry == WiringDelta()
    assert diff.topology.finish == WiringDelta(added=("join_waitlist",))

    assert diff.contracts.removed == () and diff.contracts.changed == ()
    (arrived,) = diff.contracts.added
    assert arrived.node == "join_waitlist"
    assert arrived.contract is not None
    contract = json.loads(arrived.contract)
    assert set(contract) == {"effect", "input", "output"}
    assert sorted(contract["effect"]) == ["external", "network"]
    assert sorted(contract["input"]) == ["availability", "traveler_id"]
    assert contract["output"] == ["booking_status"]

    assert not diff.state


def test_v4_adds_one_guarded_edge_between_existing_nodes(irs: tuple[WorkflowIR, ...]) -> None:
    """D-11's "new guarded edges" extension in isolation: S alone, one added edge.

    Both endpoints already exist, so — unlike v3 — no node and no contract arrives: the
    whole diff is one conditional edge under ``route_availability``'s condition, with both
    persisting endpoints marked rewired (the source's outgoing set and the target's
    incoming set each grew).
    """
    diff = workflow_diff(irs[2], irs[3])

    assert diff.bump_class == frozenset({Component.S})
    assert diff.topology.nodes == NodesDelta(rewired=("availability_check", "join_waitlist"))
    assert diff.topology.edges.added == (
        EdgeRef(
            kind="conditional",
            source="availability_check",
            target="join_waitlist",
            label="waitlist",
            condition="route_availability",
        ),
    )
    assert diff.topology.edges.removed == () and diff.topology.edges.changed == ()
    assert diff.topology.entry == WiringDelta() and diff.topology.finish == WiringDelta()
    assert not diff.contracts and not diff.state and not diff.regrouped


def test_v5_removes_a_key_two_contracts_still_declare(irs: tuple[WorkflowIR, ...]) -> None:
    """Canonical case: read-key removal. E alone — Σ moved and the contracts did not.

    The departing declaration is the bare string form (an internal key carries no
    ``optional`` flag), and what makes this the brief's case is asserted on both sides: the
    writer's and the reader's contracts are byte-identical across the pair, with
    ``itinerary`` still among ``notify_traveler``'s declared reads after the key is gone.
    """
    diff = workflow_diff(irs[3], irs[4])

    assert diff.bump_class == frozenset({Component.E})
    assert diff.state.removed == (
        StateKeyRef(key="itinerary", declaration=KeyDeclaration(type="str")),
    )
    assert diff.state.added == () and diff.state.changed == ()
    assert not diff.contracts
    assert not diff.topology.has_changes and not diff.regrouped

    def annotations_of(ir: WorkflowIR, node_id: str) -> Any:
        (node,) = (node for node in ir.nodes if node.id == node_id)
        return node.annotations

    for node_id in ("compile_itinerary", "notify_traveler"):
        assert annotations_of(irs[3], node_id) == annotations_of(irs[4], node_id)
    after = annotations_of(irs[4], "notify_traveler")
    assert after is not None and "itinerary" in (after.input or ())
    writer = annotations_of(irs[4], "compile_itinerary")
    assert writer is not None and "itinerary" in (writer.output or ())


def test_v6_retypes_a_key_three_contracts_still_read(irs: tuple[WorkflowIR, ...]) -> None:
    """Canonical case: read-key retype. E alone — one persisting key's declared type moves.

    ``str`` to ``list[str]``, both spelled as ir 1.0's opaque type-name strings; the
    ``retyped`` facet is the one that moves, and the readers' contracts are untouched.
    """
    diff = workflow_diff(irs[4], irs[5])

    assert diff.bump_class == frozenset({Component.E})
    assert diff.state.added == () and diff.state.removed == ()
    (changed,) = diff.state.changed
    assert changed.key == "availability"
    assert changed.before == KeyDeclaration(type="str")
    assert changed.after == KeyDeclaration(type="list[str]")
    assert changed.retyped
    assert not changed.reducer_changed and not changed.optional_changed
    assert not diff.contracts
    assert not diff.topology.has_changes and not diff.regrouped


def test_v7_removes_the_termination_witness_from_its_carrier(
    irs: tuple[WorkflowIR, ...],
) -> None:
    """Canonical case: termination-witness removal. F alone — one slot leaves one contract.

    The witness lives in TERMINATION-WITNESS-SPEC's form (c) — the ``variant`` annotation
    slot — so its removal is a node-contract change, not a topology one (SD-02's
    disposition, shown at SD-05, here on the live agent): ``replan`` persists, its
    ``variant`` slot goes from the attested measure to absent, and no other slot on any
    node moves.
    """
    diff = workflow_diff(irs[5], irs[6])

    assert diff.bump_class == frozenset({Component.F})
    assert diff.contracts.added == () and diff.contracts.removed == ()
    (changed,) = diff.contracts.changed
    assert changed.node == "replan"
    assert changed.present_before and changed.present_after
    (slot,) = changed.slots
    assert slot.slot == "variant"
    assert slot.after is None
    assert slot.before is not None
    departed = json.loads(slot.before)
    assert departed["key"] == "replan_budget"
    assert not diff.state
    assert not diff.topology.has_changes and not diff.regrouped


def test_v8_escalates_an_effect_class_into_the_trigger_set(irs: tuple[WorkflowIR, ...]) -> None:
    """Canonical case: effect-class escalation. F alone — one slot's value moves.

    ``check_booking``'s ``effect`` gains ``billable`` — entering the obligation trigger set
    PROPERTY-CATALOG-SPEC §6.3 fixes at ``{billable, irreversible}`` — and nothing else in
    the whole diff moves. What the escalation *means* is no output's claim to make here:
    the class is F because an annotation slot changed, full stop (PD-006 R4).
    """
    diff = workflow_diff(irs[6], irs[7])

    assert diff.bump_class == frozenset({Component.F})
    assert diff.contracts.added == () and diff.contracts.removed == ()
    (changed,) = diff.contracts.changed
    assert changed.node == "check_booking"
    assert changed.present_before and changed.present_after
    (slot,) = changed.slots
    assert slot.slot == "effect"
    assert slot.before is not None and slot.after is not None
    assert sorted(json.loads(slot.before)) == ["network"]
    assert sorted(json.loads(slot.after)) == ["billable", "network"]
    assert not diff.state
    assert not diff.topology.has_changes and not diff.regrouped


# ── Scenario fitness: the DoD pipeline can record all eight ───────────────────────────────


def test_the_eligibility_boundary_the_dod_pipeline_inherits(
    irs: tuple[WorkflowIR, ...],
) -> None:
    """Which stages a verify-gated recorder stores, measured — the fact SD-09 wires around.

    v1–v6 verify clean and snapshot-eligible. That covers both read-key cases, and the
    reason is the catalog's own: P-04 skips a read of a key outside Σ before any supply
    computation (PROPERTY-CATALOG-SPEC §4.4 step 4 — Σ-membership is P-03's finding, and
    P-03 is non-wedge per SOW §8), and no wedge property reads a key's declared type, so a
    Σ-side removal or retype raises nothing in the wedge — the property that would grade
    those *pairs* is P-12, deferred by the same §8 (PD-006 R4), which is why they are
    diff-classification cases at all. v7 and v8 fail P-02 with the
    catalog's FATAL ``cycle-without-termination-witness`` (the SOW §2 defect-1 condition,
    here reached by evolution rather than seeding), and PROPERTY-CATALOG-SPEC §0.2 makes a
    FATAL alone suppress recording — so a recorder handed an eligibility report refuses
    them, and the sequence stores all eight only through the recorder's documented
    handed-none-records posture, which is how every recording test in this file does it.
    SD-09's evolve leg inherits exactly this boundary.
    """
    for index, stage in enumerate(evo.EVOLUTION):
        report = verify(irs[index])
        if index < 6:
            assert report.gate.exit_code == 0, stage.name
            assert report.gate.snapshot_eligible, stage.name
        else:
            assert not report.gate.snapshot_eligible, stage.name
            assert report.gate.counts.fatal >= 1, stage.name
            (p02,) = (
                outcome
                for outcome in report.properties
                if outcome.property == "termination-witness"
            )
            assert isinstance(p02, PropertyReport), stage.name
            assert p02.result == "fail" and p02.failure is not None, stage.name
            assert p02.failure.property_condition == "cycle-without-termination-witness"
            assert p02.failure.severity == "fatal", stage.name


# ── WA-07: the new bodies are armed, and the whole sequence runs under the guard ──────────


def test_every_body_in_the_evolution_module_is_armed() -> None:
    """Fire every body of every evolved stage's graph — superseded twins included.

    The union over v2–v8 rather than the final builder alone: a body *replaced* between
    stages (``replan`` after v6, ``check_booking`` after v7) drops out of v8's graph but
    stays the live runnable five or six stages hand to ``gebra.extract()``, so arming only
    v8 would leave the majority of the extracted surface unproven. The callables come off
    the built graphs and are deduplicated by underlying function identity, so a node added
    to any stage — or swapped in mid-sequence — and forgotten here is still fired, once,
    and the fired label set is pinned to the module's fourteen. v1's bodies are the TE-05
    arming test's own. The ledger is restored at the end, the way that test does.
    """
    seen: dict[int, Any] = {}
    for stage in evo.EVOLUTION[1:]:
        builder = stage.build()
        callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
        callables += [spec.path for group in builder.branches.values() for spec in group.values()]
        for runnable in callables:
            function = runnable
            while hasattr(function, "func"):
                function = function.func
            seen.setdefault(id(function), function)

    fired = 0
    for function in seen.values():
        before = len(tb.TRIPPED)
        with pytest.raises(tb.TravelBookingSentinelError):
            function({})
        assert len(tb.TRIPPED) == before + 1
        fired += 1

    assert fired == 14  # twelve node bodies, two routers
    assert set(tb.TRIPPED) == EVOLUTION_BODY_LABELS
    del tb.TRIPPED[:]


#: The guarded child: the whole eight-stage extract → snapshot sequence, in a fresh
#: interpreter where resolving a name or opening a connection raises from the first line and
#: where ``StateGraph.compile`` is taken away **before gebra is imported at all** — every
#: stage's subject is the builder, so nothing on this path ever compiles. Socket
#: *construction* is counted rather than refused during imports for the reason
#: ``tests/extraction/test_dispatch.py`` records: importing the substrate runs urllib3's own
#: IPv6 capability probe, which builds a loopback socket and closes it without connecting.
_TRIPWIRE = """
import socket, sys, tempfile

attempts = []
built = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _CountSocket(socket.socket):
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the evolution path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

from langgraph.graph.state import StateGraph

StateGraph.compile = _record("StateGraph.compile")

from gebra import extract
from gebra.snapshot import SnapshotAction, snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows import travel_booking as tb
from tests.sample_workflows import travel_booking_evolution as evo

# The import phase is bounded, not excluded — see the note on the constant. From here the run
# is gebra's own work, and socket construction raises too.
assert attempts == [], attempts
socket.socket = _TripSocket

store = SnapshotStore.for_project(tempfile.mkdtemp())

for stage in evo.EVOLUTION:
    outcome = snapshot(stage.build(), store=store, source="child:" + stage.name)
    assert outcome.action is SnapshotAction.RECORDED, outcome
    assert outcome.version == stage.expected_version, outcome
    assert outcome.bump_class == stage.expected_bump, outcome

assert store.versions() == tuple(s.expected_version for s in evo.EVOLUTION), store.versions()

# Identity, not only success: the final stored document is pinned to the evolved node set and
# to the digest a fresh extraction of the final stage produces — the acceptance claim,
# re-asserted under the guard.
held = store.read(evo.EVOLUTION[-1].expected_version)
assert "join_waitlist" in {node.id for node in held.ir.nodes}, held.ir.nodes
assert held.graph_version == extract(evo.build_travel_booking_v8()).graph_version()
assert store.check().ok, store.check()

"""

#: Run last, after any probe — an assertion a probe should be able to trip has to come after
#: the probe. The ledger leg, the no-network-client leg (which no socket raiser can arm, so
#: it has its own probe below), and the import-phase socket count, reported rather than gated.
_REPORT = (
    "assert tb.TRIPPED == [], tb.TRIPPED\n"
    "assert 'langgraph.pregel.remote' not in sys.modules\n"
    "print('import-phase sockets constructed:', len(built))\n"
    "print(attempts)\n"
)


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    """Run the child with ``PYTHONOPTIMIZE`` pinned off — its claims live in ``assert``s."""
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_whole_evolution_sequence_runs_nothing_and_opens_no_socket() -> None:
    """WA-07 over the card's whole path: eight extractions, eight recordings, no execution.

    Every body in every stage raises if called; ``StateGraph.compile`` raises from before
    gebra is imported; nothing resolves a name or opens a connection at any point; and once
    gebra's own work starts, constructing a socket raises too. The child re-asserts the
    label sequence under the guard, so this is the acceptance claim in a hostile
    interpreter rather than a smoke test beside it.
    """
    finished = _run_guarded()
    assert finished.returncode == 0, finished.stderr
    assert "WA07-TRIP" not in finished.stderr
    assert "import-phase sockets constructed:" in finished.stdout
    assert finished.stdout.strip().endswith("[]")


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created on the evolution path"),
        ("socket.getaddrinfo('example.invalid', 443)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 443))\n", "create_connection was reached"),
        (
            "StateGraph.compile(evo.build_travel_booking_v8())\n",
            "StateGraph.compile was reached",
        ),
    ],
)
def test_the_guarded_run_is_armed(probe: str, expected: str) -> None:
    """A guard nobody trips proves nothing — each raiser the claim rests on is fired.

    Matched on the raiser's **full** message rather than a substring, so a control cannot
    drift onto a different raiser than the one the claim rests on and still look green.
    """
    finished = _run_guarded(probe)
    assert finished.returncode != 0
    assert "WA07-TRIP" in finished.stderr
    assert expected in finished.stderr


def test_a_swallowed_attempt_still_fails_the_run() -> None:
    """Record-before-raise, exercised: swallowing the exception does not help.

    The probe runs to completion — exit 0 — and the ledger the child prints last is what
    fails the assertion here.
    """
    finished = _run_guarded(
        "try:\n    socket.getaddrinfo('example.invalid', 443)\nexcept Exception:\n    pass\n"
    )

    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip().endswith("['getaddrinfo']")


def test_the_guarded_run_would_see_a_new_body_run() -> None:
    """The child's ledger leg is live for this module's own bodies, not only TE-05's.

    The probe fires :func:`~tests.sample_workflows.travel_booking_evolution.join_waitlist`
    before ``_REPORT``'s ``assert tb.TRIPPED == []``, in both the raising and the swallowed
    form — the swallowed one is what the record-before-raise ledger exists for.
    """
    fired = _run_guarded("evo.join_waitlist({})\n")
    assert fired.returncode != 0
    assert "TravelBookingSentinelError" in fired.stderr

    swallowed = _run_guarded(
        "try:\n    evo.check_booking_metered({})\nexcept BaseException:\n    pass\n"
    )
    assert swallowed.returncode != 0
    assert "travel-booking-evolution.check_booking_metered" in swallowed.stderr


def test_the_no_network_client_leg_is_armed_too() -> None:
    """The one leg no socket probe can arm: importing the module the guard keeps out.

    A substrate import opens no connection, so the ``langgraph.pregel.remote`` assertion in
    ``_REPORT`` needs its own probe — the same split ``tests/snapshot/test_travel_booking.py``
    records for its child.
    """
    finished = _run_guarded("import langgraph.pregel.remote\n")

    assert finished.returncode != 0
    assert "AssertionError" in finished.stderr
