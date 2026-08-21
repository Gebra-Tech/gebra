"""The topology diff engine — two snapshots or IRs in, one :class:`TopologyDiff` out.

The card's objective, implemented end to end: :func:`topology_diff` compares two workflow
definitions **over networkx** (each side is built into the :func:`~gebra.diff.graph.
topology_graph` multigraph and every fact the diff reads comes off those graphs), reports
nodes and edges added/removed/rewired, and anchors the report on node identity (renames are
new nodes, IR-SPEC §5.3) and on ``graph_version`` (both sides named by their §6 digest,
equal digests short-circuiting to the empty diff).

How the comparison runs:

1. **Resolve and anchor.** Each side may be a bare :class:`~gebra.ir.models.WorkflowIR` or
   a store :class:`~gebra.store.models.Snapshot`. The digest is recomputed from the IR
   either way — the anchor states what was actually diffed. A snapshot whose stored
   ``graph_version`` disagrees with its own IR is refused (the §6.1 step-9 recompute is the
   §1.2 conformance operation; diffing under a wrong anchor would misattribute every
   finding).
2. **Short-circuit on identity.** One digest = byte-equal canonical content (§1.2), so the
   diff is empty by construction and neither graph is built.
3. **Compare the graphs.** Declared node ids as sets (identity is the id, nothing else);
   ``entry``/``finish`` wired sets; expanded edges as a **multiset** of descriptors — the
   canonical form keeps duplicate edge objects, so multiplicity is content.
4. **Fold exact identity matches into changes.** After multiset subtraction, an unmatched
   before/after pair collapses into one :class:`~gebra.diff.models.EdgeChanged` when a
   persisting authored identity carries it and the pairing is unambiguous — exactly one
   unmatched edge on each side under a conditional routing slot ``(source, label)`` or a
   ``normal``/``send`` source ``(kind, source)``. Everything else stays removed/added.
5. **Derive rewired nodes.** A node declared on both sides that is incident to any wiring
   or edge delta kept its identity while its connections moved. A conditional target
   spelled ``"END"`` is the END sentinel (m3), so it never marks a node — not even one
   named ``END`` — while the same spelling on a ``normal``/``send`` edge is an ordinary
   reference (PD-007) and does.

What the result never says: whether a change is safe. P-12 ``evolution-safety`` is deferred
out of Phase 0 (SOW §8); this engine reports structure, and the S bump class is derived from
it — together with the ``regrouped`` category no expanded graph can show — by
:attr:`~gebra.diff.workflow.WorkflowDiff.bump_class`.

Determinism: the output is a pure function of the two inputs. Every tuple is sorted by the
ledger §6 comparator, no clock is read, and no set/dict iteration order reaches the result
— ``tests/diff/test_topology.py`` holds four child interpreters under different
``PYTHONHASHSEED`` values to one output.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07): the inputs
are IR models, and there is no user object in reach to invoke.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import TypeAlias

import networkx as nx

from gebra.diff.graph import END_LITERAL, topology_graph
from gebra.diff.models import (
    DiffAnchor,
    EdgeChanged,
    EdgeRef,
    EdgesDelta,
    NodesDelta,
    TopologyDiff,
    WiringDelta,
    ledger_sort_key,
)
from gebra.ir.canonical import graph_version
from gebra.ir.models import WorkflowIR
from gebra.store.models import Snapshot

__all__ = [
    "DiffSubject",
    "resolve_subject",
    "topology_deltas",
    "topology_diff",
]

#: What can stand on either side of a diff: a bare IR, or a store snapshot (whose V.S.F.E
#: label then rides the anchor).
DiffSubject: TypeAlias = "WorkflowIR | Snapshot"

#: A pairing key — the persisting authored identity under which one unmatched edge on each
#: side collapses into an :class:`EdgeChanged`.
_PairKey: TypeAlias = "tuple[str, str]"


def topology_diff(before: DiffSubject, after: DiffSubject) -> TopologyDiff:
    """The topology delta from ``before`` to ``after``, anchored by content digest.

    Args:
        before: The side compared from — a ``WorkflowIR``, or a ``Snapshot`` whose
            ``version`` label then appears on the anchor.
        after: The side compared to.

    Returns:
        The delta. ``added`` members are present only on the ``after`` side, ``removed``
        only on the ``before`` side; swapping the arguments swaps those members and the
        before/after halves of every changed entry.

    Raises:
        ValueError: if a ``Snapshot``'s stored ``graph_version`` is not the digest of its
            own IR (IR-SPEC §6.1 step 9) — a corrupted or hand-altered snapshot, refused
            rather than diffed under a wrong anchor.
        CanonicalizationError: if an IR carries a value the canonical form refuses
            (IR-SPEC §6.1 step 5); such a document has no digest to anchor on.
    """
    before_ir, before_anchor = resolve_subject(before)
    after_ir, after_anchor = resolve_subject(after)
    return topology_deltas(
        before_ir, after_ir, before_anchor=before_anchor, after_anchor=after_anchor
    )


def topology_deltas(
    before_ir: WorkflowIR,
    after_ir: WorkflowIR,
    *,
    before_anchor: DiffAnchor,
    after_anchor: DiffAnchor,
) -> TopologyDiff:
    """Steps 2–5 of :func:`topology_diff`, for a caller holding resolved sides and anchors.

    Internal to :mod:`gebra.diff`, and not part of the package's public surface.
    :func:`~gebra.diff.workflow.workflow_diff` is the caller it exists for: it resolves both
    subjects once for the whole diff, and re-resolving here would either recompute two digests
    or — worse — rebuild the anchors from bare IRs and drop the V.S.F.E labels a snapshot side
    carries.

    **The anchors are taken on trust**, which is the whole reason this is not on the public
    surface: :func:`resolve_subject` is what makes an anchor trustworthy (IR-SPEC §6.1 step 9),
    and passing anchors that do not belong to these two IRs would produce a report named after
    content it does not describe. Callers outside this package use :func:`topology_diff`.
    """
    if before_anchor.graph_version == after_anchor.graph_version:
        return TopologyDiff(before=before_anchor, after=after_anchor)

    edges_before, entry_before, finish_before, declared_before = _collect(topology_graph(before_ir))
    edges_after, entry_after, finish_after, declared_after = _collect(topology_graph(after_ir))

    removed = edges_before - edges_after
    added = edges_after - edges_before
    changed = _pair(removed, added)

    entry_delta = WiringDelta.of(
        added=entry_after - entry_before, removed=entry_before - entry_after
    )
    finish_delta = WiringDelta.of(
        added=finish_after - finish_before, removed=finish_before - finish_after
    )
    edges_delta = EdgesDelta.of(added=added.elements(), removed=removed.elements(), changed=changed)
    rewired = _touched(edges_delta, entry_delta, finish_delta) & declared_before & declared_after
    nodes_delta = NodesDelta.of(
        added=declared_after - declared_before,
        removed=declared_before - declared_after,
        rewired=rewired,
    )
    return TopologyDiff(
        before=before_anchor,
        after=after_anchor,
        nodes=nodes_delta,
        entry=entry_delta,
        finish=finish_delta,
        edges=edges_delta,
    )


def resolve_subject(subject: DiffSubject) -> tuple[WorkflowIR, DiffAnchor]:
    """The IR to diff and the anchor naming it — digest recomputed, never trusted.

    A snapshot read through :class:`~gebra.store.store.SnapshotStore` was digest-verified on
    the way in; recomputing here extends the same §6.1 step-9 check to snapshots built or
    altered outside a store, so the anchor is the digest of the IR actually compared.

    This is also where the engine's one **precondition on the document itself** is checked:
    node ids must be unique. IR-SPEC §2.1's ``nodes`` row makes that a MUST — "**Node ``id``s
    MUST be unique within a document** … a duplicate id has no meaning under §5.3's identity
    rules and loaders MUST reject it" (ratified DEC-22) — and §6.2's sort totality is a stated
    consequence of it. Every diff in this package is anchored on node identity (§5.3:
    "Renaming a node … is a **new identity**"), so a document repeating an id has no identity
    to anchor on: the §6.2 sort key ties, the tied entries' authored order reaches the digest
    — which §6.4 excludes — and every delta keyed by id collapses them, under-reporting the S
    and F counters while ``graph_version`` moves. PD-012 makes a V.S.F.E label a snapshot's
    file name, so that under-report is a second workflow content under a file that already
    holds one. Such a document is therefore **refused**, from either side and before the
    identity short-circuit.

    The check is a floor, not the enforcement point: DEC-22 puts the load-time constraint on
    the model (card IR-07), after which no ``WorkflowIR`` reaching here can violate it and
    this becomes an assertion. It stays until then, because the rule is only worth having if
    something enforces it. (It is also what found the defect: §2.1 carried no uniqueness
    constraint before DEC-22, and SD-05's IR-spec pre-review reproduced two
    canonical forms — two digests — for one node set. Record: PD-032.)

    Public because every engine in this package resolves its two sides the same way and a
    second implementation of the step-9 recompute would be a second opinion about which IR a
    diff is actually about (:mod:`gebra.diff.workflow` is the other caller).

    Raises:
        ValueError: if a ``Snapshot``'s stored ``graph_version`` is not the digest of its own
            IR (IR-SPEC §6.1 step 9), or if the IR declares one node id twice (§2.1, DEC-22).
    """
    _require_unique_node_ids(subject.ir if isinstance(subject, Snapshot) else subject)
    if isinstance(subject, Snapshot):
        digest = graph_version(subject.ir)
        if digest != subject.graph_version:
            raise ValueError(
                f"snapshot {subject.version!r} carries graph_version "
                f"{subject.graph_version!r}, but its IR digests to {digest!r} "
                "(IR-SPEC §6.1 step 9); refusing to diff under a wrong anchor"
            )
        return subject.ir, DiffAnchor(graph_version=digest, version=subject.version)
    return subject, DiffAnchor(graph_version=graph_version(subject))


def _require_unique_node_ids(ir: WorkflowIR) -> None:
    """Refuse a document that declares one node id twice — see :func:`resolve_subject`."""
    seen: set[str] = set()
    for node in ir.nodes:
        if node.id in seen:
            raise ValueError(
                f"node id {node.id!r} is declared twice, which IR-SPEC §2.1 forbids: node "
                "ids MUST be unique within a document (ratified DEC-22). This engine anchors "
                "every delta on node identity (§5.3), so a document that repeats an id has "
                "no total canonical node order and cannot be diffed without under-reporting "
                "the S and F counters. Refused rather than misreported"
            )
        seen.add(node.id)


def _collect(
    graph: nx.MultiDiGraph,
) -> tuple[Counter[EdgeRef], frozenset[str], frozenset[str], frozenset[str]]:
    """Read the diff universe off one graph: edge multiset, wired sets, declared ids.

    Wired members and targets come from edge attributes (the authored spellings) and the
    edge source from the tail vertex, whose name is the authored ``from`` verbatim. The
    head vertices — the one place sentinel mapping lives — are never read at all, so the
    graph's vertex-naming conventions cannot leak into the comparison.
    """
    edges: Counter[EdgeRef] = Counter()
    entry: set[str] = set()
    finish: set[str] = set()
    for source, _head, data in graph.edges(data=True):
        origin: str = data["origin"]
        if origin == "entry":
            entry.add(data["target"])
        elif origin == "finish":
            finish.add(data["target"])
        else:
            edges[
                EdgeRef(
                    kind=data["kind"],
                    source=source,
                    target=data["target"],
                    label=data["label"],
                    condition=data["condition"],
                )
            ] += 1
    declared = frozenset(vertex for vertex, role in graph.nodes(data="role") if role == "node")
    return edges, frozenset(entry), frozenset(finish), declared


def _pair(removed: Counter[EdgeRef], added: Counter[EdgeRef]) -> list[EdgeChanged]:
    """Collapse unambiguous before/after pairs into changes, consuming them from the counters.

    Two passes over disjoint kinds, so neither can steal the other's candidates: conditional
    routing slots first, then ``normal``/``send`` sources. Keys are visited in ledger §6
    order — order only matters for determinism of the (already order-free) result, since a
    pairing is made only when it is the unique one for its key.
    """
    changed: list[EdgeChanged] = []
    _pair_exact(removed, added, _slot_key, changed)
    _pair_exact(removed, added, _route_key, changed)
    return changed


def _slot_key(ref: EdgeRef) -> _PairKey | None:
    """The conditional routing slot ``(source, label)`` — ledger §4's named logical edge."""
    if ref.kind != "conditional" or ref.label is None:
        return None
    return (ref.source, ref.label)


def _route_key(ref: EdgeRef) -> _PairKey | None:
    """The ``normal``/``send`` anchor ``(kind, source)`` — one remaining out-edge of that
    kind on a persisting source. Kind is in the key, so a re-kinded edge never pairs: a
    ``send`` is a fan-out template (T-W-SPEC §1), a different edge rather than a changed
    one."""
    if ref.kind == "conditional":
        return None
    return (ref.kind, ref.source)


def _pair_exact(
    removed: Counter[EdgeRef],
    added: Counter[EdgeRef],
    key_of: Callable[[EdgeRef], _PairKey | None],
    changed: list[EdgeChanged],
) -> None:
    """Pair keys carried by exactly one unmatched edge on each side; anything wider stays.

    "Exactly one" counts multiplicity — a key covering two unmatched parallel edges on one
    side is ambiguous, and ambiguity is reported as removed/added rather than resolved by
    a tiebreak that would be an invented identity.
    """
    removed_groups = _grouped(removed, key_of)
    added_groups = _grouped(added, key_of)
    shared = removed_groups.keys() & added_groups.keys()
    for key in sorted(shared, key=lambda pair: tuple(ledger_sort_key(part) for part in pair)):
        before_group = removed_groups[key]
        after_group = added_groups[key]
        if len(before_group) != 1 or len(after_group) != 1:
            continue
        before_ref, after_ref = before_group[0], after_group[0]
        changed.append(
            EdgeChanged(
                kind=before_ref.kind,
                source=before_ref.source,
                label=before_ref.label,
                target_before=before_ref.target,
                target_after=after_ref.target,
                condition_before=before_ref.condition,
                condition_after=after_ref.condition,
            )
        )
        # Group size counts copies, so a paired ref has multiplicity exactly one.
        del removed[before_ref]
        del added[after_ref]


def _grouped(
    counter: Counter[EdgeRef], key_of: Callable[[EdgeRef], _PairKey | None]
) -> dict[_PairKey, list[EdgeRef]]:
    """Unmatched edges by pairing key, multiplicity expanded so group size counts copies.

    Every entry of ``counter`` is positive: multiset subtraction drops non-positives, and
    the pairing pass deletes what it consumes.
    """
    table: dict[_PairKey, list[EdgeRef]] = {}
    for ref, count in counter.items():
        key = key_of(ref)
        if key is None:
            continue
        table.setdefault(key, []).extend([ref] * count)
    return table


def _touched(edges: EdgesDelta, entry: WiringDelta, finish: WiringDelta) -> set[str]:
    """Every reference incident to a delta — the rewired-node candidates.

    A conditional target spelled ``"END"`` is the m3 sentinel, never a node reference; on
    ``normal``/``send`` edges the same spelling is an ordinary reference (PD-007), so it
    stays. The caller intersects with the declared-on-both-sides set, which is what turns
    references into nodes.
    """
    touched: set[str] = set()
    for ref in (*edges.added, *edges.removed):
        touched.add(ref.source)
        if not (ref.kind == "conditional" and ref.target == END_LITERAL):
            touched.add(ref.target)
    for change in edges.changed:
        touched.add(change.source)
        for target in (change.target_before, change.target_after):
            if not (change.kind == "conditional" and target == END_LITERAL):
                touched.add(target)
    touched.update(entry.added, entry.removed, finish.added, finish.removed)
    return touched
