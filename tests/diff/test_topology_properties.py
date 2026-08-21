"""Property tests for the topology diff — the claims the constructed pairs are examples of.

Quantified over the same generated-IR strategy the version engine's properties use
(``tests.versioning.test_classify_properties``), so the two engines are held to each other
on the whole shape space they share:

* **The digest anchor.** Equal ``graph_version`` ⟹ the diff is empty and says
  ``identical``; a workflow never diffs against itself, its reserialized copy, or its
  reordered copy.
* **The S-slice bridge.** If SD-02's S component slice is byte-equal, the topology diff is
  empty; if the topology diff is non-empty, ``Component.S`` is among the changed
  components. (The converses are deliberately not claimed: a router regrouping moves the S
  bytes without moving the expanded graph — the constructed-pair table pins one.)
* **Direction, not content.** The reverse diff mirrors added/removed and swaps the
  before/after halves of every change; rewired nodes are the same set either way.
* **Shape invariants.** Rewired ⊆ declared-on-both-sides; added/removed node sets are
  disjoint; every reported tuple is already in its sorted report order.

Everything here is pure data (WA-07): strategies build IR models, and the diff is a
function of two of them.
"""

from __future__ import annotations

from hypothesis import given

from gebra.diff import EdgeChanged, EdgesDelta, NodesDelta, TopologyDiff, WiringDelta, topology_diff
from gebra.ir import dump_json, load_json
from gebra.ir.canonical import graph_version
from gebra.ir.models import WorkflowIR
from gebra.versioning import Component, canonical_view, changed_components, component_bytes
from tests.versioning.test_classify_properties import workflow_irs


def _mirrored(diff: TopologyDiff) -> TopologyDiff:
    """What the reverse diff must be, computed from the forward one."""
    return TopologyDiff(
        before=diff.after,
        after=diff.before,
        nodes=NodesDelta.of(
            added=diff.nodes.removed, removed=diff.nodes.added, rewired=diff.nodes.rewired
        ),
        entry=WiringDelta.of(added=diff.entry.removed, removed=diff.entry.added),
        finish=WiringDelta.of(added=diff.finish.removed, removed=diff.finish.added),
        edges=EdgesDelta.of(
            added=diff.edges.removed,
            removed=diff.edges.added,
            changed=[
                EdgeChanged(
                    kind=change.kind,
                    source=change.source,
                    label=change.label,
                    target_before=change.target_after,
                    target_after=change.target_before,
                    condition_before=change.condition_after,
                    condition_after=change.condition_before,
                )
                for change in diff.edges.changed
            ],
        ),
    )


# ── The digest anchor ────────────────────────────────────────────────────────────────────


@given(ir=workflow_irs())
def test_a_workflow_never_diffs_against_itself(ir: WorkflowIR) -> None:
    diff = topology_diff(ir, ir)

    assert diff.identical and not diff.has_changes


@given(ir=workflow_irs())
def test_a_workflow_never_diffs_against_a_reserialized_copy(ir: WorkflowIR) -> None:
    """A round trip through the serialized form is how a *stored* IR reaches a diff in the
    first place — a snapshot is read back before it is compared."""
    reloaded = load_json(WorkflowIR, dump_json(ir))
    diff = topology_diff(ir, reloaded)

    assert diff.identical and not diff.has_changes


@given(ir=workflow_irs())
def test_a_reordered_copy_is_not_a_topology_change(ir: WorkflowIR) -> None:
    """§6.2 normalizes authored array order out of the digest, and the diff agrees."""
    reordered = WorkflowIR(
        ir_version=ir.ir_version,
        entry=ir.entry,
        finish=ir.finish,
        state=ir.state,
        nodes=tuple(reversed(ir.nodes)),
        edges=tuple(reversed(ir.edges)),
        runtime=ir.runtime,
    )
    diff = topology_diff(ir, reordered)

    assert diff.identical and not diff.has_changes


@given(left=workflow_irs(), right=workflow_irs())
def test_equal_digests_mean_an_empty_diff(left: WorkflowIR, right: WorkflowIR) -> None:
    if graph_version(left) == graph_version(right):
        diff = topology_diff(left, right)
        assert diff.identical and not diff.has_changes


# ── The S-slice bridge to the version engine ─────────────────────────────────────────────


@given(left=workflow_irs(), right=workflow_irs())
def test_an_equal_s_slice_means_an_empty_diff(left: WorkflowIR, right: WorkflowIR) -> None:
    """The diff universe is a function of the topology slice of the canonical form — so
    when SD-02's S bytes are equal, there is nothing for this engine to report."""
    same_topology_bytes = component_bytes(canonical_view(left), Component.S) == component_bytes(
        canonical_view(right), Component.S
    )
    if same_topology_bytes:
        assert not topology_diff(left, right).has_changes


@given(left=workflow_irs(), right=workflow_irs())
def test_a_reported_change_always_moves_the_s_counter(left: WorkflowIR, right: WorkflowIR) -> None:
    """The other direction of the bridge: a non-empty topology diff is always an S change
    in the version engine's terms — the two engines cannot disagree about whether the
    topology domain moved when this one says it did."""
    if topology_diff(left, right).has_changes:
        assert Component.S in changed_components(left, right)


# ── Direction, not content ───────────────────────────────────────────────────────────────


@given(left=workflow_irs(), right=workflow_irs())
def test_the_reverse_diff_mirrors_the_forward_one(left: WorkflowIR, right: WorkflowIR) -> None:
    assert topology_diff(right, left) == _mirrored(topology_diff(left, right))


@given(left=workflow_irs(), right=workflow_irs())
def test_diffing_twice_yields_one_value(left: WorkflowIR, right: WorkflowIR) -> None:
    first = topology_diff(left, right)
    second = topology_diff(left, right)

    assert first == second
    assert repr(first) == repr(second)


# ── Shape invariants of the report ───────────────────────────────────────────────────────


@given(left=workflow_irs(), right=workflow_irs())
def test_rewired_nodes_are_declared_on_both_sides(left: WorkflowIR, right: WorkflowIR) -> None:
    diff = topology_diff(left, right)
    declared_left = {node.id for node in left.nodes}
    declared_right = {node.id for node in right.nodes}

    assert set(diff.nodes.rewired) <= declared_left & declared_right
    assert set(diff.nodes.added) == declared_right - declared_left
    assert set(diff.nodes.removed) == declared_left - declared_right
    assert not set(diff.nodes.added) & set(diff.nodes.removed)


@given(left=workflow_irs(), right=workflow_irs())
def test_every_reported_tuple_is_in_its_sorted_order(left: WorkflowIR, right: WorkflowIR) -> None:
    """The report order is part of the output contract — a consumer rendering a diff never
    sorts, so the engine must have."""
    diff = topology_diff(left, right)

    for members in (
        diff.nodes.added,
        diff.nodes.removed,
        diff.nodes.rewired,
        diff.entry.added,
        diff.entry.removed,
        diff.finish.added,
        diff.finish.removed,
    ):
        assert list(members) == sorted(members, key=lambda member: member.encode("utf-16-be"))
    assert list(diff.edges.added) == sorted(diff.edges.added, key=lambda ref: ref.sort_key())
    assert list(diff.edges.removed) == sorted(diff.edges.removed, key=lambda ref: ref.sort_key())
    assert list(diff.edges.changed) == sorted(
        diff.edges.changed, key=lambda change: change.sort_key()
    )
