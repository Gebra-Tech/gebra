"""Property tests for the composed diff — the claims the constructed table illustrates.

The load-bearing one is **agreement with the version engine**: for any pair of IRs,
:attr:`WorkflowDiff.bump_class` equals :func:`~gebra.versioning.changed_components`. That is
not true by construction — the diff derives its class from its own categories, and the version
engine derives its from the canonical component slices — so the equality is a real claim about
two independent computations, and it is the one that has to hold: PD-012 makes a V.S.F.E label
a snapshot's file name, so a component the diff failed to report would put a second workflow
content under a label that already names one.

The three per-component bridges are asserted separately from their conjunction, because a
failure in one of them says which delta is incomplete and the conjunction does not.

The regrouping case gets its own generator rather than waiting for two independent draws to
collide: :func:`split_routers` turns any IR into one whose ``edges[]`` array differs and whose
expanded routes do not, which is exactly the shape the ``regrouped`` category exists for.

**The generator's domain is the engine's domain, stated rather than assumed.**
:func:`diff_irs` draws node ids ``unique=True``, which is what IR-SPEC §2.1 requires of a
conforming document (ratified DEC-22). The restriction is load-bearing: a document repeating
a node id has no total canonical node order (§6.2's sort key ties) and would break the
agreement claim. It is not quietly excluded — :func:`duplicated_id_irs` generates exactly that
class and asserts the engine *refuses* it, so the boundary is tested rather than avoided. That
class is what SD-05's pre-review used to falsify the first cut of the agreement claim; it is
recorded in PD-032, ruled non-conforming by DEC-22, and refused at model validation since card
IR-07 — so the generator now has to reach past validation to build one at all.

Everything here is pure data (WA-07): strategies build IR models, and a diff is a function of
two of them.
"""

from __future__ import annotations

from typing import Any, Final

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gebra.diff import (
    ContractsDelta,
    NodeContractChanged,
    NodeContractRef,
    SlotChange,
    StateDelta,
    StateKeyChanged,
    StateKeyRef,
    WorkflowDiff,
    workflow_diff,
)
from gebra.ir import dump_json, load_json
from gebra.ir.canonical import graph_version
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    ConditionalEdge,
    Edge,
    Interrupts,
    Node,
    NormalEdge,
    RecursionLimit,
    Runtime,
    SendEdge,
    StateField,
    WorkflowIR,
)
from gebra.versioning import Component, Version, changed_components
from tests.versioning.test_classify_properties import INTEGERS, NODE_IDS, TEXT, node_contracts

#: Deliberately tiny alphabets for guards and router labels: two independently drawn edges
#: should collide on a source, a condition and a label often enough that parallel routes,
#: ambiguous pairings and re-grouped routers are all reachable.
CONDITIONS: Final = st.sampled_from(["g", "h"])
LABELS: Final = st.sampled_from(["a", "b", "c"])


@st.composite
def diff_irs(draw: st.DrawFn) -> WorkflowIR:
    """A generated ``WorkflowIR`` shaped for *diffing*, not just for versioning.

    Wider than the SD-02 strategy in the three places this card's deltas have categories the
    version engine does not: several edges may share a source (so routers can be merged or
    split), Σ values carry reducers, and the empty-versus-absent pairs — ``annotations: {}``,
    ``runtime: {}``, ``state: {}`` against each one's absence — are all reachable, because
    canonicalization keeps them apart and so must the deltas.
    """
    ids = draw(st.lists(NODE_IDS, min_size=1, max_size=3, unique=True))
    contracts = st.none() | st.just(Annotations()) | node_contracts()
    nodes = tuple(Node(id=node_id, annotations=draw(contracts)) for node_id in ids)

    sources = st.sampled_from(ids)
    targets = st.sampled_from([*ids, "END"])
    edge = (
        st.builds(
            lambda source, to, condition: NormalEdge(
                kind="normal", **{"from": source}, to=to, condition=condition
            ),
            sources,
            targets,
            st.none() | CONDITIONS,
        )
        | st.builds(
            lambda source, to, condition: SendEdge(
                kind="send", **{"from": source}, to=to, condition=condition
            ),
            sources,
            targets,
            st.none() | CONDITIONS,
        )
        | st.builds(
            lambda source, condition, path_map: ConditionalEdge(
                kind="conditional", **{"from": source}, condition=condition, path_map=path_map
            ),
            sources,
            st.none() | CONDITIONS,
            st.dictionaries(LABELS, targets, max_size=3),
        )
    )
    edges = tuple(draw(st.lists(edge, max_size=4)))

    values = TEXT | st.builds(
        StateField,
        type=TEXT,
        reducer=st.none() | TEXT,
        optional=st.none() | st.booleans(),
    )
    state = draw(st.none() | st.dictionaries(TEXT, values, max_size=3))
    runtime = draw(
        st.none()
        | st.builds(
            Runtime,
            recursion_limit=st.none()
            | st.builds(RecursionLimit, value=INTEGERS, justification=TEXT),
            interrupts=st.none()
            | st.builds(Interrupts, before=st.lists(st.sampled_from(ids), max_size=2).map(tuple)),
            checkpointer=st.none() | st.builds(Checkpointer, present=st.booleans()),
        )
    )
    return WorkflowIR(
        ir_version="1.0",
        entry=draw(st.sampled_from(ids) | st.just(tuple(ids))),
        finish=draw(st.sampled_from(ids) | st.just(tuple(ids))),
        state=state,
        nodes=nodes,
        edges=edges,
        runtime=runtime,
    )


@st.composite
def duplicated_id_irs(draw: st.DrawFn) -> WorkflowIR:
    """An IR that declares one node id twice — the class this engine refuses.

    Non-conforming by IR-SPEC §2.1's uniqueness MUST (ratified DEC-22), and no longer
    *loadable*: ``WorkflowIR`` refuses it at validation since card IR-07. It is still
    *constructible*, which is why the engine's own refusal is still load-bearing —
    ``model_copy(update=...)`` skips validation by design, and the model it returns
    canonicalizes, so the document does have a ``graph_version``. What it does not have is a
    total canonical node order, since §6.2's sort key ties on the repeated id — the whole
    defect.
    """
    ir = draw(diff_irs())
    twin = draw(st.sampled_from(ir.nodes))
    return ir.model_copy(
        update={
            "nodes": (
                *ir.nodes,
                Node(id=twin.id, annotations=draw(st.none() | node_contracts())),
            )
        }
    )


def split_routers(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` with every router split into one router per ``path_map`` label.

    IR-SPEC §2.4 label-expands routers before any graph algorithm runs, so this rewrite
    preserves every logical edge exactly while changing the authored ``edges[]`` array — and
    a router with no labels disappears, which changes the array and expands to nothing either
    way. It is the rewrite the ``regrouped`` category exists for: within the ``edges`` member,
    it is the only way ir 1.0 moves ``graph_version`` without moving the expanded routing
    graph. (Elsewhere in the S slice there is one more, and it is not covered but *refused* —
    repeating a node id, which IR-SPEC §2.1's uniqueness MUST forbids and
    :func:`~gebra.diff.topology.resolve_subject` rejects; see
    :func:`test_a_repeated_node_id_is_refused_by_the_whole_engine`.)
    """
    edges: list[Edge] = []
    for edge in ir.edges:
        if isinstance(edge, ConditionalEdge):
            edges.extend(
                ConditionalEdge(
                    kind="conditional",
                    **{"from": edge.from_},
                    condition=edge.condition,
                    path_map={label: target},
                )
                for label, target in edge.path_map.items()
            )
        else:
            edges.append(edge)
    return ir.model_copy(update={"edges": tuple(edges)})


# ── The claim that keeps a label naming one content ──────────────────────────────────────


@given(before=diff_irs(), after=diff_irs())
def test_the_bump_class_is_the_version_engines_answer(
    before: WorkflowIR, after: WorkflowIR
) -> None:
    """Derived from diff categories on one side, from canonical component slices on the
    other, and equal — in both directions, so neither over- nor under-reports."""
    assert workflow_diff(before, after).bump_class == changed_components(before, after)


@given(doubled=duplicated_id_irs(), other=diff_irs())
def test_a_repeated_node_id_is_refused_by_the_whole_engine(
    doubled: WorkflowIR, other: WorkflowIR
) -> None:
    """The boundary of the claim above, tested rather than assumed away.

    A document repeating a node id is non-conforming (IR-SPEC §2.1's MUST, DEC-22) and is
    refused at model validation since card IR-07 — but it is still constructible past
    validation, and it does have a ``graph_version``. Every delta this engine reports is keyed
    by node id, so reporting one
    would collapse the two entries and could leave S and F standing while the digest moved — a
    second workflow content under a label that already names one (PD-012 makes the label a
    file name). The engine refuses instead, from either side and in either order, including
    when both sides are the same document, where the digest short-circuit would otherwise
    answer before the check ran.
    """
    assert graph_version(doubled)  # built past validation, so it still canonicalizes

    for pair in ((doubled, other), (other, doubled), (doubled, doubled)):
        with pytest.raises(ValueError, match="declared twice"):
            workflow_diff(*pair)


@given(before=diff_irs(), after=diff_irs())
def test_each_delta_is_non_empty_exactly_when_its_component_moved(
    before: WorkflowIR, after: WorkflowIR
) -> None:
    """The three bridges the conjunction above is made of, asserted one at a time so a
    failure names the incomplete delta."""
    diff = workflow_diff(before, after)
    moved = changed_components(before, after)

    assert (diff.topology.has_changes or diff.regrouped) == (Component.S in moved)
    assert bool(diff.contracts) == (Component.F in moved)
    assert bool(diff.state) == (Component.E in moved)


@given(ir=diff_irs())
def test_splitting_routers_moves_s_and_nothing_the_graph_can_see(ir: WorkflowIR) -> None:
    """The regrouping case, generated rather than waited for: same routes, different
    ``edges[]``. Either the rewrite was a no-op on the canonical form — in which case the
    diff is empty — or S moved with the expanded-edge delta still empty."""
    split = split_routers(ir)
    diff = workflow_diff(ir, split)

    assert diff.bump_class == changed_components(ir, split)
    assert not diff.topology.edges
    if diff.identical:
        assert not diff.regrouped and diff.bump_class == frozenset()
    else:
        assert diff.regrouped
        assert diff.bump_class == frozenset({Component.S})
        assert not diff.topology.has_changes


@given(before=diff_irs(), after=diff_irs())
def test_regrouped_implies_the_expanded_edges_agree(before: WorkflowIR, after: WorkflowIR) -> None:
    """``regrouped`` is about the authored array only: it never fires beside a reported edge
    change, so the two categories never describe the same difference twice."""
    diff = workflow_diff(before, after)

    if diff.regrouped:
        assert not diff.topology.edges
        assert Component.S in diff.bump_class


# ── Equal content, empty diff ────────────────────────────────────────────────────────────


@given(ir=diff_irs())
def test_a_workflow_never_differs_from_itself(ir: WorkflowIR) -> None:
    diff = workflow_diff(ir, ir)

    assert diff.identical and not diff.has_changes
    assert diff.bump_class == frozenset()
    assert diff.contracts == ContractsDelta() and diff.state == StateDelta()
    assert not diff.regrouped


@given(ir=diff_irs())
def test_a_workflow_never_differs_from_its_serialized_self(ir: WorkflowIR) -> None:
    """Round-tripping through the serialized form is not an edit — the same claim SD-01's
    round-trip goldens make, read at the diff."""
    reloaded = load_json(WorkflowIR, dump_json(ir))

    assert graph_version(reloaded) == graph_version(ir)
    assert not workflow_diff(ir, reloaded).has_changes


@given(before=diff_irs(), after=diff_irs())
def test_anything_changed_is_anything_at_all(before: WorkflowIR, after: WorkflowIR) -> None:
    """S, F and E cover the whole hash scope except ``ir_version`` (IR-SPEC §8 puts format
    migrations in the other regime), so "some counter bumps" and "the digests differ" are one
    fact. Checked rather than assumed: it is the diff-level face of the version engine's
    covering property."""
    diff = workflow_diff(before, after)

    assert diff.has_changes == (not diff.identical)
    assert diff.identical == (graph_version(before) == graph_version(after))


# ── Direction, order, determinism ────────────────────────────────────────────────────────


@given(before=diff_irs(), after=diff_irs())
def test_the_reverse_diff_mirrors(before: WorkflowIR, after: WorkflowIR) -> None:
    """Swapping the sides swaps added with removed and both halves of every change, and
    leaves the bump class alone — a class names domains, not a direction."""
    forward = workflow_diff(before, after)
    reverse = workflow_diff(after, before)

    assert reverse.bump_class == forward.bump_class
    assert reverse.regrouped == forward.regrouped
    assert reverse.before == forward.after and reverse.after == forward.before
    assert reverse.contracts == ContractsDelta.of(
        added=forward.contracts.removed,
        removed=forward.contracts.added,
        changed=[
            NodeContractChanged(
                node=change.node,
                present_before=change.present_after,
                present_after=change.present_before,
                slots=tuple(
                    sorted(
                        (
                            SlotChange(slot=slot.slot, before=slot.after, after=slot.before)
                            for slot in change.slots
                        ),
                        key=SlotChange.sort_key,
                    )
                ),
            )
            for change in forward.contracts.changed
        ],
        runtime=type(forward.contracts.runtime)(
            present_before=forward.contracts.runtime.present_after,
            present_after=forward.contracts.runtime.present_before,
            slots=tuple(
                sorted(
                    (
                        SlotChange(slot=slot.slot, before=slot.after, after=slot.before)
                        for slot in forward.contracts.runtime.slots
                    ),
                    key=SlotChange.sort_key,
                )
            ),
        ),
    )
    assert reverse.state == StateDelta.of(
        added=forward.state.removed,
        removed=forward.state.added,
        changed=[
            StateKeyChanged(key=change.key, before=change.after, after=change.before)
            for change in forward.state.changed
        ],
        present_before=forward.state.present_after,
        present_after=forward.state.present_before,
    )


@given(before=diff_irs(), after=diff_irs())
def test_every_reported_tuple_is_already_sorted(before: WorkflowIR, after: WorkflowIR) -> None:
    """Nothing in the output depends on set or dict iteration order: every tuple comes back
    in the ledger §6 order its own sort key defines."""
    diff = workflow_diff(before, after)

    _assert_sorted(diff.contracts.added, key=NodeContractRef.sort_key)
    _assert_sorted(diff.contracts.removed, key=NodeContractRef.sort_key)
    _assert_sorted(diff.contracts.changed, key=NodeContractChanged.sort_key)
    _assert_sorted(diff.contracts.runtime.slots, key=SlotChange.sort_key)
    for change in diff.contracts.changed:
        _assert_sorted(change.slots, key=SlotChange.sort_key)
    _assert_sorted(diff.state.added, key=StateKeyRef.sort_key)
    _assert_sorted(diff.state.removed, key=StateKeyRef.sort_key)
    _assert_sorted(diff.state.changed, key=StateKeyChanged.sort_key)


def _assert_sorted(values: tuple[Any, ...], *, key: Any) -> None:
    assert list(values) == sorted(values, key=key)


@given(before=diff_irs(), after=diff_irs())
def test_a_reported_change_always_moved(before: WorkflowIR, after: WorkflowIR) -> None:
    """Nothing is reported whose two sides are equal — a delta never pads itself with
    unchanged members it happened to walk past."""
    diff = workflow_diff(before, after)

    for change in diff.contracts.changed:
        assert change.slots or change.present_before != change.present_after
        for slot in change.slots:
            assert slot.before != slot.after
    for slot in diff.contracts.runtime.slots:
        assert slot.before != slot.after
    for key_change in diff.state.changed:
        assert key_change.before != key_change.after
    assert {ref.key for ref in diff.state.added} & {ref.key for ref in diff.state.removed} == set()
    assert set(diff.contracts.added) & set(diff.contracts.removed) == set()


@given(
    before=diff_irs(),
    after=diff_irs(),
    current=st.builds(
        Version, v=st.just(1), s=st.integers(0, 9), f=st.integers(0, 9), e=st.integers(0, 9)
    ),
)
def test_the_bump_moves_exactly_the_named_counters(
    before: WorkflowIR, after: WorkflowIR, current: Version
) -> None:
    """Applying a bump class: V is carried through, each named counter moves by one, nothing
    resets, and an identical pair leaves the label alone."""
    diff = workflow_diff(before, after)
    bumped = diff.bump(current)

    assert bumped.v == current.v
    assert bumped.s == current.s + (Component.S in diff.bump_class)
    assert bumped.f == current.f + (Component.F in diff.bump_class)
    assert bumped.e == current.e + (Component.E in diff.bump_class)
    assert (bumped == current) == (not diff.has_changes)
    assert bumped >= current


# ── The vocabulary the deltas hard-code, held to the live models ─────────────────────────


def test_the_state_facets_are_the_whole_state_field_model() -> None:
    """:class:`~gebra.diff.state.KeyDeclaration` names ``type``/``reducer``/``optional`` by
    hand — the one place in these deltas where a field vocabulary is written out rather than
    read off the canonical view. A field added to ``StateField`` without a facet here would
    be silently dropped from the E delta, so it fails here instead."""
    assert set(StateField.model_fields) == {"type", "reducer", "optional"}


def test_the_contract_and_runtime_slots_are_read_not_listed() -> None:
    """The complement of the claim above: the contract and runtime deltas name no slot at
    all, so every member of ``Annotations`` and ``Runtime`` classifies without an edit — the
    check is that a slot of each is reported by name, not that a list of them exists."""
    before = WorkflowIR(
        ir_version="1.0",
        entry="a",
        finish="a",
        nodes=(Node(id="a", annotations=Annotations(pure=True)),),
        edges=(),
        runtime=Runtime(checkpointer=Checkpointer(present=True)),
    )
    after = before.model_copy(
        update={
            "nodes": (Node(id="a", annotations=Annotations(pure=False)),),
            "runtime": Runtime(checkpointer=Checkpointer(present=False)),
        }
    )
    diff = workflow_diff(before, after)

    assert [slot.slot for change in diff.contracts.changed for slot in change.slots] == ["pure"]
    assert [slot.slot for slot in diff.contracts.runtime.slots] == ["checkpointer"]
    assert set(Annotations.model_fields) | set(Runtime.model_fields) >= {"pure", "checkpointer"}


@given(before=diff_irs(), after=diff_irs())
def test_the_deferred_marker_rides_every_diff(before: WorkflowIR, after: WorkflowIR) -> None:
    """P-12 is deferred for every pair, identical ones included — the marker is a statement
    about this release, not about the change in front of it."""
    diff: WorkflowDiff = workflow_diff(before, after)

    assert diff.evolution_safety.property_id == "P-12"
    assert diff.evolution_safety.status == "deferred-to-phase-1"
