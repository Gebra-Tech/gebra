"""The shared graph pre-analysis every topology-facing validator reads its graph from.

Normative authority: IR-SPEC §4.2 (the model-vs-surface split and the m1–m5 sentinel
equivalences), ir-field-ledger §4 (label expansion) and §5/§6 (reserved segments, the
node-id comparator), and TERMINATION-WITNESS-SPEC §5 steps 1–2 (label-expand, then Tarjan —
"the component map feeds the D4 side conditions"). The four topology-facing validators cite
this module rather than restate it: PROPERTY-CATALOG-SPEC §1.4 Step 1 (P-01), §2.4 Step 0–1
(P-02), §4.4 Step 0/Step 3 (P-04) and §6.4 Phases 0/2 (P-06) all open with the *same* graph,
and §6.4 says so in its own words — "Phases 0 and 2 are steps (1)–(2) of the SCC-condensation
procedure in TERMINATION-WITNESS-SPEC — **cited, not redefined**".

The model, in one paragraph. Analyses run on the **model** (sentinels present, labels
expanded); serializations use the **surface** (`entry`/`finish` fields, no sentinel rows in
`nodes[]`) — IR-SPEC §4.2. So :func:`build_graph_model` materializes ``__start__`` and
``__end__`` as real vertices and wires them per m1–m3, expands every ``path_map`` label into
its own directed edge, keeps parallel edges and self-loops distinct (a multigraph, forced —
"nx.DiGraph merges parallels => over-discharge", catalog §2.4 Step 0), and by default
**resolves nothing into existence**: a reference naming no node contributes no vertex and no
edge, and is recorded in :attr:`GraphModel.unresolved` for the validator that owns it.

**The P-01-clean precondition, which is why "one shared graph" is not "one shared answer".**
§0.3: topology-consuming validators "have results **normatively defined only over P-01-clean
topology**", and each section documents its own local degradation convention — P-01 drops
dangling-target edges, P-02 carries a dangling vertex, P-04 carries the phantom with an empty
contract, P-06 skips the edge — conventions that "are deliberately local, cross-validator
agreement on ill-formed input is NOT promised". So the model is shared and the *convention* is
a parameter (:func:`build_graph_model`'s ``carry_unresolved_references``), never a default this
module picks on four validators' behalf. On clean topology the parameter makes no difference at
all; on dirty topology every result is a best-effort diagnostic, not a contract-bearing verdict.

What this module deliberately does not do:

* **No property semantics.** No condition ID, no severity, no witness, no report. The
  envelope is :mod:`gebra.verify.report`'s and the conditions are
  :mod:`gebra.verify.conditions`'; this module hands back graph facts and structured
  evidence of unresolved references, and every judgement about them is the caller's.
* **No cycle enumeration, anywhere.** Coverage is decided by residual acyclicity (Lemma 1,
  T-W-SPEC §5), and the one cycle this module builds is a single deterministic anchor per
  request (:meth:`GraphModel.anchor_cycle`). The capped census of T-W-SPEC §6.3 is VAL-08's,
  not a primitive here.
* **No networkx.** The catalog's "networkx primitives" rows are implementability
  checklists — evidence that each step is available and non-recursive — and §4.4 says
  plainly "spec-level algorithm; production code is brief D-09's". Two facts decide it the
  other way here: ``tests/verify/test_base.py`` asserts ``networkx`` stays out of
  ``import gebra.verify``'s closure, and ``gebra.verify`` imports the validator subpackage;
  and both specs mandate iterative traversal with explicit stacks ("forced, not stylistic",
  catalog §2.4). Every traversal below is iterative for that reason.

Nothing here imports langgraph, executes a node, calls a model, or opens a network
connection (WA-07): it reads a validated :class:`~gebra.ir.models.WorkflowIR` and returns
frozen values.
"""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Final, Literal, TypeAlias

from gebra.ir import ConditionalEdge, WorkflowIR, refuse_dynamic_edges

__all__ = [
    "END_VERTEX",
    "SENTINEL_VERTICES",
    "START_VERTEX",
    "Components",
    "EdgeKind",
    "EdgeOrigin",
    "ExpandedEdge",
    "GraphModel",
    "ReferenceRole",
    "UnresolvedReference",
    "build_graph_model",
    "canonical_rotation",
    "ledger_sort_key",
]


# ── The graph-side sentinels (ledger §5; IR-SPEC §4.2) ───────────────────────────────────

#: The per-level entry pseudo-node, spelled as the ledger §5 reserved segment. Reports use
#: ``"START"`` instead — :func:`gebra.verify.base.to_display` is the one projection between
#: them, and :data:`~gebra.verify.base.NodeId` refuses this spelling, so a validator that
#: forgets the projection fails validation rather than emitting a non-conforming report.
START_VERTEX: Final = "__start__"

#: The per-level exit pseudo-node (ledger §5); report-side spelling ``"END"``.
END_VERTEX: Final = "__end__"

#: Both sentinels, in the order :func:`build_graph_model` materializes them.
SENTINEL_VERTICES: Final[tuple[str, str]] = (START_VERTEX, END_VERTEX)

#: The three edge kinds of ledger §4 (``kind`` defaults to ``normal`` on the surface).
EdgeKind: TypeAlias = Literal["normal", "conditional", "send"]

#: Where an expanded edge came from. ``"edges"`` is a member of ``ir.edges``; ``"entry"``
#: and ``"finish"`` are the implicit sentinel wirings of IR-SPEC §4.2 (m1)/(m2). The
#: distinction is load-bearing exactly once: P-01's condition-(iii) orphan scan counts
#: "only Step-1 edges built from ``ir.edges``" and adds sentinel membership separately
#: (catalog §1.4 Step 2, Reading A per DEC-11).
EdgeOrigin: TypeAlias = Literal["edges", "entry", "finish"]

#: Which reference role failed to resolve. The five roles are exactly the sites catalog
#: §1.4 Step 1 checks, and they map one-to-one onto P-01's two condition IDs:
#: ``"path-map-target"`` is ``path-map-target-undefined``, and the other four are
#: ``edge-target-undefined`` (DEC-12, 2026-07-31 — which folded the unresolved ``from`` and
#: the ``finish``-symmetric check into that condition). This module names the *fact*; the
#: condition ID is P-01's to emit.
ReferenceRole: TypeAlias = Literal[
    "entry", "finish", "edge-source", "edge-target", "path-map-target"
]


def ledger_sort_key(value: str) -> bytes:
    """The ledger §6 comparator: UTF-16 code units, as sortable bytes.

    Ledger §6 orders ``nodes[]`` "by ``id`` (escaped form), compared as UTF-16 code units —
    the same comparator as JCS member sorting (RFC 8785 §3.2.3)". That is **not** Python's
    default string order: the two disagree for ids mixing non-BMP characters with
    U+E000..U+FFFF, because a non-BMP scalar is a surrogate pair (0xD800..0xDFFF) in UTF-16
    and sorts *below* U+E000 there while sorting above it by code point. Big-endian UTF-16
    bytes compare exactly as UTF-16 code units, so this key is the comparator.

    Every deterministic ordering in this module — vertices, successors, SCC members,
    condensation tie-breaks, cycle rotation — is this key, so a validator's findings and
    witnesses inherit the ledger order by construction.
    """
    return value.encode("utf-16-be")


def canonical_rotation(cycle: tuple[str, ...]) -> tuple[str, ...]:
    """Rotate a simple cycle so its least id comes first (§0.3 ``CycleLocation``).

    §0.3 fixes the canonical form of a cycle list as "lexicographically-least id first",
    under the ledger §6 comparator. A simple cycle has pairwise-distinct vertices (T-W-SPEC
    §1), so the minimum is unique and the rotation is total.

    Args:
        cycle: The cycle as a vertex sequence, without the repeated closing vertex.

    Returns:
        The same cycle, rotated. The empty tuple is returned unchanged.
    """
    if not cycle:
        return cycle
    pivot = min(range(len(cycle)), key=lambda index: ledger_sort_key(cycle[index]))
    return cycle[pivot:] + cycle[:pivot]


# ── Expanded edges and unresolved references ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ExpandedEdge:
    """One logical directed edge of the model — ledger §4's unit of graph structure.

    Ledger §4: "each ``path_map`` label denotes one logical directed edge
    ``from → path_map[label]`` carrying that label", expanded *before* any graph algorithm
    runs. A ``normal`` or ``send`` edge maps 1:1 (a send edge's fan-out multiplicity is a
    runtime quantity, "not graph structure — it contributes exactly one structural edge",
    T-W-SPEC §1); a ``conditional`` edge contributes one of these per label.

    ``(origin, index, label)`` is the identity: two labels of one router, or two authored
    edges between the same pair, are distinct members of the model. That is the multigraph
    requirement catalog §2.4 Step 0 states as a soundness matter — merging parallels would
    let one discharged label-edge discharge its sibling.

    Attributes:
        source: The tail vertex — a node id, or ``__start__`` for an ``entry`` wiring.
        target: The head vertex — a node id, or ``__end__`` for a ``finish`` wiring or a
            ``path_map`` label naming the literal ``"END"``.
        kind: The ledger §4 kind of the authored edge this came from. Sentinel wirings are
            ``"normal"``: IR-SPEC §4.2 (m1)/(m2) read them as normal edges.
        origin: Which surface field carried it (see :data:`EdgeOrigin`).
        index: Position within that field — the ``ir.edges`` index, or the position in the
            ``entry``/``finish`` list form. The ``ir.edges`` index is the multigraph key of
            catalog §2.4 Step 0 (``key=(i, label)``).
        label: The ``path_map`` label, on a conditional expansion; ``None`` otherwise.
    """

    source: str
    target: str
    kind: EdgeKind
    origin: EdgeOrigin
    index: int
    label: str | None = None


@dataclass(frozen=True, slots=True)
class UnresolvedReference:
    """A declared reference naming no node in $V$ — recorded, never resolved into a vertex.

    DEC-12 (2026-07-31) fixed the rule this class exists to serve: an unresolved reference
    "emits, inserts nothing — no phantom auto-vivification" (catalog §1.4 Step 1). So the
    model carries no edge for it, conditions (i)–(iii) run on the resolvable subgraph, and
    the fact survives here for P-01 to turn into a finding. Unresolved references are
    recorded one by one, never merged: DEC-12's emission rule is one finding per reference,
    no collapse. What is *not* recorded is a site §1.4 Step 1 never reaches — the ``to`` of a
    ``normal``/``send`` edge whose ``from`` is unresolved, which Step 1 ``continue``s past;
    see :func:`build_graph_model`. That is the pseudocode's own asymmetry, not a collapse.

    The field set is exactly what P-01's ``P01EdgeLocation`` needs, so P-01 reads a location
    off a record rather than re-deriving resolution:

    * ``role="entry"`` → ``source`` is ``__start__``, ``reference`` the unresolved id;
    * ``role="finish"`` → ``source`` *is* the unresolved id (catalog §1.4's symmetric check
      anchors the finding at the id itself);
    * ``role="edge-source"`` → ``source`` is the unresolved ``from``;
    * ``role="edge-target"`` → ``source`` is the edge's ``from``, ``reference`` its ``to``;
    * ``role="path-map-target"`` → ``source`` is the router's ``from``, plus the ``label``.

    Attributes:
        role: Which reference site failed (see :data:`ReferenceRole`).
        reference: The string that resolves to no node.
        source: The anchor vertex for a finding, per the table above.
        index: Position in ``ir.edges``, or in the ``entry``/``finish`` list form.
        label: The ``path_map`` label, for ``role="path-map-target"``; ``None`` otherwise.
        kind: The authored edge's kind, when the reference sits on an edge; ``None`` for
            ``entry``/``finish``.
    """

    role: ReferenceRole
    reference: str
    source: str
    index: int
    label: str | None = None
    kind: EdgeKind | None = None


# ── Strongly connected components ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Components:
    """The Tarjan partition of a :class:`GraphModel` — T-W-SPEC §5 step 2.

    "Tarjan on $G$ — the component map feeds the D4 side conditions" (T-W-SPEC §5); P-06
    §6.4 Phase 2 is the same pass, cited rather than redefined. The partition is total: every
    vertex of the model, sentinels included, is in exactly one component.

    **Non-triviality is a defined term, not a size test.** T-W-SPEC §1: an SCC is trivial
    iff it is a single node carrying no self-loop, and non-trivial otherwise — "≥ 2 nodes,
    *or* a single node with a self-loop (a self-loop is a simple cycle and MUST count)".
    :attr:`nontrivial` is computed against that definition, which is also P-06's
    ``in_cycle(n)`` (§6.4 Phase 2) and P-02's residual test (catalog §2.4 Step 4).

    Attributes:
        members: Component index → its members, each tuple sorted by :func:`ledger_sort_key`.
            Components appear in Tarjan emission order, which is *a* reverse topological
            order of the condensation; :meth:`GraphModel.condensation_order` is the
            deterministic topological order callers should use, never this index order.
        nontrivial: The indices of the non-trivial components.
    """

    members: tuple[tuple[str, ...], ...]
    nontrivial: frozenset[int]

    @cached_property
    def _index_of(self) -> dict[str, int]:
        return {vertex: index for index, group in enumerate(self.members) for vertex in group}

    def index(self, vertex: str) -> int:
        """The component index of ``vertex``.

        Raises:
            KeyError: if ``vertex`` is not a vertex of the model this partition came from.
        """
        return self._index_of[vertex]

    def members_of(self, vertex: str) -> tuple[str, ...]:
        """``vertex``'s whole component, sorted — the ``scc_of[n]`` of both pseudocodes."""
        return self.members[self.index(vertex)]

    def is_nontrivial(self, vertex: str) -> bool:
        """Whether ``vertex`` lies on a cycle — P-06's ``in_cycle(n)`` (§6.4 Phase 2).

        True iff ``vertex``'s component is non-trivial in the T-W-SPEC §1 sense, which for a
        singleton component means it carries a self-loop.
        """
        return self.index(vertex) in self.nontrivial

    def same_component(self, one: str, other: str) -> bool:
        """Whether two vertices share a component — the D4 side condition's test (§4)."""
        return self.index(one) == self.index(other)

    def __len__(self) -> int:
        return len(self.members)


# ── The model ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GraphModel:
    """The sentinel-augmented, label-expanded multigraph the wedge's topology runs on.

    Built by :func:`build_graph_model`; a subgraph by :meth:`subgraph`. Immutable and
    hashable, so it can be built once per IR and handed to every validator — which is the
    caching strategy this module offers (see the module docstring of
    :func:`build_graph_model`). Derived analyses (:attr:`components`, :meth:`condensation`,
    :meth:`descendants`, :meth:`anchor_cycle`) are memoized per instance, so a second ask is
    free and two validators sharing a model share the Tarjan pass.

    Attributes:
        vertices: Every vertex, sorted by :func:`ledger_sort_key`. For a model built from an
            IR this is $V \\cup \\{$``__start__``, ``__end__``$\\}$, plus any carried
            references (see :func:`build_graph_model`).
        node_ids: $V$ — the ids declared in ``ir.nodes``, without sentinels and without
            carried references. The set P-01's conditions (i)–(iii) quantify over.
        edges: Every expanded edge, in emission order: the ``entry`` wirings, the ``finish``
            wirings, then ``ir.edges`` in authored order with each router's ``path_map``
            labels in authored order. Emission order is *not* a normative order — every
            consumer sorts its own output by the ledger §6 comparator — but it is stable, so
            two builds of one IR are equal values.
        unresolved: Every declared reference naming no node, in the same emission order.
            Emission order is **not** P-01's F_iv order: catalog §1.4 Step 5, as amended by
            DEC-12, sorts F_iv by a leading key that puts resolvable anchors first, and only
            then does ``findings[0]`` name the primary. Do not read ``unresolved[0]`` as the
            primary finding — ``mixed/04`` happens to come out right under emission order,
            which is exactly what makes the shortcut look safe.
        carried: Unresolved references that were nonetheless materialized as vertices,
            empty unless ``carry_unresolved_references=True`` was asked for.
    """

    vertices: tuple[str, ...]
    node_ids: frozenset[str]
    edges: tuple[ExpandedEdge, ...]
    unresolved: tuple[UnresolvedReference, ...] = ()
    carried: frozenset[str] = frozenset()

    # ── Adjacency ────────────────────────────────────────────────────────────────────────

    @cached_property
    def vertex_set(self) -> frozenset[str]:
        """:attr:`vertices` as a set, for O(1) membership."""
        return frozenset(self.vertices)

    @cached_property
    def _out(self) -> dict[str, tuple[ExpandedEdge, ...]]:
        table: dict[str, list[ExpandedEdge]] = {vertex: [] for vertex in self.vertices}
        for edge in self.edges:
            table[edge.source].append(edge)
        return {vertex: tuple(group) for vertex, group in table.items()}

    @cached_property
    def _in(self) -> dict[str, tuple[ExpandedEdge, ...]]:
        table: dict[str, list[ExpandedEdge]] = {vertex: [] for vertex in self.vertices}
        for edge in self.edges:
            table[edge.target].append(edge)
        return {vertex: tuple(group) for vertex, group in table.items()}

    @cached_property
    def _successors(self) -> dict[str, tuple[str, ...]]:
        return {
            vertex: tuple(sorted({edge.target for edge in group}, key=ledger_sort_key))
            for vertex, group in self._out.items()
        }

    @cached_property
    def _predecessors(self) -> dict[str, tuple[str, ...]]:
        return {
            vertex: tuple(sorted({edge.source for edge in group}, key=ledger_sort_key))
            for vertex, group in self._in.items()
        }

    def out_edges(self, vertex: str) -> tuple[ExpandedEdge, ...]:
        """Every expanded edge leaving ``vertex``, in emission order — parallels kept."""
        return self._out[vertex]

    def in_edges(self, vertex: str) -> tuple[ExpandedEdge, ...]:
        """Every expanded edge entering ``vertex``, in emission order — parallels kept."""
        return self._in[vertex]

    def successors(self, vertex: str) -> tuple[str, ...]:
        """``vertex``'s distinct successors, in ledger §6 order.

        The de-duplicated *simple-digraph* view. Both pseudocodes ask for exactly this
        wherever determinism is at stake — P-06 §6.4's anchor BFS is "seeded with
        ``H.successors(n)`` **in id order**" — while :meth:`out_edges` keeps the multigraph
        view for the analyses that need edge identity.
        """
        return self._successors[vertex]

    def predecessors(self, vertex: str) -> tuple[str, ...]:
        """``vertex``'s distinct predecessors, in ledger §6 order.

        P-01's pass witness reads ``terminal_nodes`` off ``G.predecessors("__end__")``
        (catalog §1.4 Step 5).

        Tabled once per model, exactly as :meth:`successors` is. The asymmetry this closes was
        measurable rather than theoretical: P-04's fixpoint asks for every vertex's
        predecessors on every round-robin pass, and re-deriving the set and re-sorting it by a
        UTF-16 encode each time was **74% of the fixpoint's runtime** on an adversarial graph
        (2.5 s of 3.5 s at |V| = 1600, the never-invokes pre-review at VAL-09). The result is
        identical — same set, same comparator — so this is a table, not a semantics.
        """
        return self._predecessors[vertex]

    def has_edge(self, source: str, target: str) -> bool:
        """Whether at least one expanded edge runs ``source → target``."""
        return any(edge.target == target for edge in self._out.get(source, ()))

    def has_self_loop(self, vertex: str) -> bool:
        """Whether ``vertex`` carries a self-loop — a simple cycle of length 1 (T-W-SPEC §1)."""
        return self.has_edge(vertex, vertex)

    def degree(self, vertex: str, *, origins: Iterable[EdgeOrigin] | None = None) -> int:
        """In-degree plus out-degree, optionally restricted to edges of some origins.

        The restriction is what P-01's condition-(iii) scan needs: "in+out degree of ``id``
        counting only Step-1 edges built from ``ir.edges``", with sentinel membership added
        separately as Reading A's implicit wiring (catalog §1.4 Step 2; DEC-11). Passing
        ``origins=("edges",)`` is that count; the default counts everything. A self-loop
        contributes 2, as an undirected degree does.

        The other half of Step 2 needs no separate read of ``ir.entry``/``ir.finish``:
        for an id in :attr:`node_ids`, ``degree(id, origins=("entry", "finish")) == 0`` is
        equivalent to Step 2's ``[id ∈ entry_ids] + [id ∈ finish_ids] == 0``, because a
        resolvable id carries a wiring edge exactly when it is a member. (A duplicated id in
        a list form changes the count but never the zero test, which is all Step 2 asks.)
        """
        if origins is None:
            return len(self._out[vertex]) + len(self._in[vertex])
        wanted = frozenset(origins)
        return sum(edge.origin in wanted for edge in self._out[vertex]) + sum(
            edge.origin in wanted for edge in self._in[vertex]
        )

    # ── Derived analyses (memoized) ──────────────────────────────────────────────────────

    @cached_property
    def components(self) -> Components:
        """The Tarjan partition — T-W-SPEC §5 step 2, computed once per model.

        Iterative, with an explicit stack: catalog §2.4's closing note makes that a
        requirement rather than a style choice, "forced, not stylistic: deep agent graphs
        would exhaust the interpreter recursion limit". $O(|V| + |E^*|)$ (Tarjan 1972).

        **The sentinels do not perturb this**, which is what lets P-06 use the shared model
        even though §6.4 Phase 0 builds a sentinel-free graph: by (m5) ``__start__`` has no
        in-edges and ``__end__`` no out-edges, so each is a trivial component that no cycle
        can contain, and the partition restricted to :attr:`node_ids` is the same either
        way. The same argument covers §6.4's ``if target == "END" … continue``: an edge into
        ``__end__`` can never join a cycle.
        """
        return _tarjan(self)

    @cached_property
    def condensation(self) -> tuple[tuple[int, ...], ...]:
        """The condensation DAG: component index → its distinct successor components, sorted.

        Self-loops of the condensation are impossible by construction (an edge inside a
        component is not a condensation edge), so the result is acyclic — the fact P-04's
        worklist order and P-02's certificate both rest on.
        """
        components = self.components
        arcs: list[set[int]] = [set() for _ in range(len(components))]
        for edge in self.edges:
            tail = components.index(edge.source)
            head = components.index(edge.target)
            if tail != head:
                arcs[tail].add(head)
        return tuple(tuple(sorted(group)) for group in arcs)

    @cached_property
    def condensation_order(self) -> tuple[int, ...]:
        """A topological order of the condensation, deterministic by least member id.

        Kahn's algorithm with the ready set kept as a heap keyed by each component's least
        member under :func:`ledger_sort_key`, so the order is a pure function of the model.
        """
        arcs = self.condensation
        indegree = [0] * len(arcs)
        for group in arcs:
            for head in group:
                indegree[head] += 1
        ready: list[tuple[bytes, int]] = [
            (ledger_sort_key(self.components.members[index][0]), index)
            for index in range(len(arcs))
            if indegree[index] == 0
        ]
        heapq.heapify(ready)
        order: list[int] = []
        while ready:
            _, index = heapq.heappop(ready)
            order.append(index)
            for head in arcs[index]:
                indegree[head] -= 1
                if indegree[head] == 0:
                    heapq.heappush(ready, (ledger_sort_key(self.components.members[head][0]), head))
        return tuple(order)

    @cached_property
    def worklist_order(self) -> tuple[str, ...]:
        """Vertices in condensation order, members of a component kept together.

        P-04 §4.4 Step 3's iteration order, verbatim: ``[v for scc in
        topological_sort(condensation(G)) for v in members(scc)]``.

        On an **acyclic** model every component is a singleton, so this is a topological
        order of the model itself — which is P-02's acyclicity certificate, ``list(
        nx.topological_sort(R))`` over the residual (catalog §2.4 Step 6; T-W-SPEC §6.2).
        One primitive, two call sites; there is no second topological sort to write.

        .. warning::

           Condensation supplies iteration **ORDER ONLY** — never collapse SCCs (catalog
           §4.2). Collapsing a component into a supernode with unioned writes is unsound for
           P-04: the union is a may-eventually-write summary, while must-write-before-first-
           read is order-sensitive inside the component (memo A8 T3). The dual collapse
           (ignoring intra-SCC writes) is incomplete. This tuple is a *schedule*; the
           node-level equations remain the semantics.
        """
        members = self.components.members
        return tuple(vertex for index in self.condensation_order for vertex in members[index])

    def descendants(self, source: str) -> frozenset[str]:
        """Every vertex reachable from ``source``, ``source`` itself excluded.

        The forward closure P-01 §1.4 Step 3 and P-04 §4.4 Steps 2/4 both take, with the
        semantics the primitive they name has: ``nx.descendants`` subtracts the source
        **unconditionally**, so a vertex on a cycle is not among its own descendants. §4.4
        Step 2 is the direct evidence — ``Reach := {START} ∪ nx.descendants(G, START)``
        needs that union only because the source is missing from the set. The exclusion is
        observable in §4.4's ``downstream_writers = W[k] ∩ nx.descendants(G, v)``: a
        self-writing reader on a cycle is not its own downstream writer.

        To ask whether ``source`` lies on a cycle, ask that question —
        ``components.is_nontrivial(source)`` (T-W-SPEC §1). To include the source in the
        set, union it in, as §4.4 Step 2 does.

        Iterative BFS, $O(|V| + |E^*|)$; memoized per source.
        """
        cached = self._descendant_cache.get(source)
        if cached is not None:
            return cached
        seen: set[str] = set()
        queue = deque(self.successors(source))
        while queue:
            vertex = queue.popleft()
            if vertex in seen:
                continue
            seen.add(vertex)
            queue.extend(target for target in self.successors(vertex) if target not in seen)
        result = frozenset(seen) - {source}
        self._descendant_cache[source] = result
        return result

    @cached_property
    def _descendant_cache(self) -> dict[str, frozenset[str]]:
        return {}

    def subgraph(self, vertices: Iterable[str]) -> GraphModel:
        """The subgraph induced on ``vertices`` — ``G.subgraph(K)`` of both pseudocodes.

        Keeps every expanded edge with both endpoints inside, so parallels and self-loops
        survive. Unresolved references are not carried over: they are facts about the whole
        document, not about an induced piece of it.

        Vertices absent from this model are ignored rather than added, so a caller cannot
        widen the vertex set through the subgraph route. This is also the sanctioned way to
        *remove* vertices — building a :class:`GraphModel` directly requires that every edge
        endpoint be a member of ``vertices`` and that ``vertices`` be ledger-sorted, neither
        of which the constructor checks.

        **Mind the polarity when porting a pseudocode's `restricted_view`.** §4.4 Step 4's
        ``nx.restricted_view(G, nodes = W[k] ∖ {v})`` *removes* those nodes, so the
        equivalent here is ``model.subgraph(model.vertex_set - (W_k - {v}))`` — not
        ``subgraph(W_k - {v})``, which keeps exactly what the spec throws away.
        """
        kept = frozenset(vertices) & self.vertex_set
        return GraphModel(
            vertices=tuple(sorted(kept, key=ledger_sort_key)),
            node_ids=self.node_ids & kept,
            edges=tuple(edge for edge in self.edges if edge.source in kept and edge.target in kept),
            carried=self.carried & kept,
        )

    def anchor_cycle(self, vertex: str) -> tuple[str, ...]:
        """One deterministic simple cycle through ``vertex``, canonically rotated.

        The shared formulation of P-06 §6.4's ``anchor_cycle(n)`` and P-02 §2.4's
        ``cycle_through(G, n, scc_of)`` — the catalog writes the second as "the §6.4
        ``anchor_cycle`` formulation", so it is one primitive with two call sites:

        * a self-loop answers immediately with ``(vertex,)``;
        * otherwise **one** multi-source BFS over the induced subgraph of ``vertex``'s
          component, seeded with ``successors(vertex)`` in id order, first-shortest-found
          wins — never one BFS per successor (§6.5 is explicit about the difference).

        Determinism comes from the seed order and from expanding neighbours in ledger §6
        order: among the shortest cycles through ``vertex`` the answer is a pure function of
        the model. $O(|V| + |E^*|)$ per call.

        Returns:
            The cycle as a vertex tuple with no repeated closing vertex, rotated so its
            least id comes first (§0.3 ``CycleLocation``).

        Raises:
            ValueError: if ``vertex`` lies on no cycle. Callers gate on
                :meth:`Components.is_nontrivial` first — that is exactly what P-06 §6.4's
                ``anchor := anchor_cycle(n) if in_cycle(n)`` does.
        """
        cached = self._anchor_cache.get(vertex)
        if cached is not None:
            return cached
        if not self.components.is_nontrivial(vertex):
            raise ValueError(
                f"{vertex!r} lies on no cycle: its strongly connected component is trivial "
                "(TERMINATION-WITNESS-SPEC §1). Gate on Components.is_nontrivial() first."
            )
        cycle = canonical_rotation(self._anchor_walk(vertex))
        self._anchor_cache[vertex] = cycle
        return cycle

    @cached_property
    def _anchor_cache(self) -> dict[str, tuple[str, ...]]:
        return {}

    def _anchor_walk(self, vertex: str) -> tuple[str, ...]:
        """The un-rotated anchor: ``vertex`` followed by a shortest successor → vertex path.

        One multi-source BFS. The seeds are ``vertex``'s successors inside its own
        component, so the walk found is a shortest successor → ``vertex`` path and the cycle
        it closes is a shortest cycle through ``vertex``. ``vertex`` is never a seed — a
        vertex that is its own successor carries a self-loop, answered above — so the parent
        chain from ``vertex`` always ends at a seed.
        """
        if self.has_self_loop(vertex):
            return (vertex,)
        inside = self._component_subgraph(vertex)
        parents: dict[str, str | None] = {}
        queue: deque[str] = deque()
        for successor in inside.successors(vertex):
            parents[successor] = None
            queue.append(successor)
        while queue:
            current = queue.popleft()
            if current == vertex:
                break
            for successor in inside.successors(current):
                if successor not in parents:
                    parents[successor] = current
                    queue.append(successor)
        step = parents.get(vertex)
        if step is None:  # pragma: no cover — unreachable: the component is non-trivial
            raise ValueError(f"no cycle through {vertex!r} inside its own component")
        walk: list[str] = []
        while step is not None:
            walk.append(step)
            step = parents[step]
        walk.reverse()
        return (vertex, *walk)

    def _component_subgraph(self, vertex: str) -> GraphModel:
        """``vertex``'s component as an induced subgraph — one build per component."""
        index = self.components.index(vertex)
        cached = self._component_subgraph_cache.get(index)
        if cached is None:
            cached = self.subgraph(self.components.members[index])
            self._component_subgraph_cache[index] = cached
        return cached

    @cached_property
    def _component_subgraph_cache(self) -> dict[int, GraphModel]:
        return {}


# ── Construction ─────────────────────────────────────────────────────────────────────────

#: The one target string ledger §1/§4 bless inside a ``path_map`` value (IR-SPEC §4.2 m3).
_END_LITERAL: Final = "END"


def _as_ids(wired: str | tuple[str, ...]) -> tuple[str, ...]:
    """The ``entry``/``finish`` surface, scalar or list form, as a tuple (ledger §1)."""
    return (wired,) if isinstance(wired, str) else wired


def build_graph_model(ir: WorkflowIR, *, carry_unresolved_references: bool = False) -> GraphModel:
    """Build the sentinel-augmented, label-expanded model of ``ir`` — IR-SPEC §4.2 (m1)–(m5).

    The five equivalences, each realized here:

    * **(m1)** each id in ``entry`` becomes a ``normal`` edge ``__start__ → e``;
    * **(m2)** each id in ``finish`` becomes a ``normal`` edge ``f → __end__``;
    * **(m3)** each ``path_map`` label valued ``"END"`` becomes a label-edge targeting
      ``__end__`` — label expansion applies first (ledger §4);
    * **(m4)** an edge targeting END — the case this model **declines to read into the
      surface**. The ``"END"`` literal is blessed for ``path_map`` values only (ledger
      §1/§4; PD-007 Q2, ratified 2026-07-24; IR-SPEC §4.2 (m4) as corrected at DEC-27,
      2026-08-09), so ``to: "END"`` on a ``normal``/``send`` edge is looked up in $V$ like
      any other target — resolving to a declared node of that id if one exists ("END" is a
      legal §5 node id) — and, when it names no node, it is recorded as an unresolved
      reference, which is what catalog §1.4 Step 1 does with it. Nothing in the corpus
      writes the shape.
    * **(m5)** ``__start__`` gets no incoming edge and ``__end__`` no outgoing edge, and
      neither sentinel appears in ``nodes[]``. The last is the node-id grammar's doing (the
      ledger §5 reserved segments are refused on ``nodes[].id``); the first two are this
      function's, because reference-role strings are deliberately *not* constrained by the
      IR models — so a reference spelling ``__start__`` or ``__end__`` is recorded as
      unresolved and is never carried, even under ``carry_unresolved_references``.

    Unresolved references contribute **no vertex and no edge** by default: DEC-12's rule is
    "emit, insert nothing — no phantom auto-vivification" (catalog §1.4 Step 1), so
    conditions (i)–(iii) run on the resolvable subgraph and every reference is reported at
    its own site. A conditional edge whose ``from`` is unresolved still has its labels
    resolved and checked — also DEC-12 — while a ``normal``/``send`` edge's ``to`` is not,
    because §1.4 Step 1 ``continue``s past it. That asymmetry is the frozen text's, and it
    is mirrored rather than smoothed so the record list stays one-to-one with the findings
    P-01 emits.

    **``ir_version`` 1.1 is declined here, not defaulted.** A ``dynamic`` edge (DEC-28,
    2026-08-09) contributes no member to $G$ while its source still participates for P-01's
    conditions (ii)/(iii), and P-01's condition (i) runs under a ruled over-approximation —
    all of which DEC-28 assigns to a paired validator regression card. Dropping the edge
    *quietly* would be the false FATAL that ruling forbids by name, so a ``dynamic``-bearing
    document raises :class:`~gebra.ir.models.DynamicEdgeUnsupportedError` instead. ``verify()``
    refuses such a document one layer earlier, with an ``ir-validation`` tool error, so this is
    the guard for a direct single-property call.

    Args:
        ir: A validated ``ir_version`` 1.0 workflow.
        carry_unresolved_references: Materialize each unresolved reference as a vertex and
            insert the incidence anyway, the way an ``nx`` ``add_edge`` auto-vivifies.

            **Which setting is whose** is not this module's call to make: §0.3's P-01-clean
            precondition ratifies four *different* local degradation conventions by name and
            adds that they "are deliberately local, cross-validator agreement on ill-formed
            input is NOT promised". Off — the default — is **P-01**'s ("drops dangling-target
            edges") and **P-06**'s ("skips the edge"). On is **P-02**'s ("P-02's ``resolve``
            would carry a dangling vertex", also §2.7) and **P-04**'s ("carries the phantom
            vertex with an empty contract", §4.4 Step 0). Either way the references stay
            listed in :attr:`GraphModel.unresolved` and the carried vertices in
            :attr:`GraphModel.carried`, so a consumer can always tell a declared node from a
            phantom — which matters for ``DataflowLocation.path``, whose members are
            report-side node ids.

    Returns:
        The model. Equal inputs give equal models: emission order is authored order and every
        derived ordering is the ledger §6 comparator.

    Raises:
        DynamicEdgeUnsupportedError: if the document carries a ``dynamic`` edge (above).
    """
    static_edges = refuse_dynamic_edges(ir.edges, consumer="the shared validator graph model")
    node_ids = frozenset(node.id for node in ir.nodes)
    edges: list[ExpandedEdge] = []
    unresolved: list[UnresolvedReference] = []
    carried: set[str] = set()

    def record(reference: UnresolvedReference) -> bool:
        """Log an unresolved reference; report whether it should still be wired.

        A reference spelling a reserved sentinel segment is never carried, whatever the
        flag says: carrying one would wire an edge into ``__start__`` or out of ``__end__``
        and break (m5), and the IR models constrain reference-role strings nowhere.
        """
        unresolved.append(reference)
        if carry_unresolved_references and reference.reference not in SENTINEL_VERTICES:
            carried.add(reference.reference)
            return True
        return False

    for position, entry_id in enumerate(_as_ids(ir.entry)):
        wired = entry_id in node_ids or record(
            UnresolvedReference("entry", entry_id, START_VERTEX, position)
        )
        if wired:
            edges.append(ExpandedEdge(START_VERTEX, entry_id, "normal", "entry", position))

    for position, finish_id in enumerate(_as_ids(ir.finish)):
        wired = finish_id in node_ids or record(
            UnresolvedReference("finish", finish_id, finish_id, position)
        )
        if wired:
            edges.append(ExpandedEdge(finish_id, END_VERTEX, "normal", "finish", position))

    for index, edge in enumerate(static_edges):
        source = edge.from_
        source_ok = source in node_ids or record(
            UnresolvedReference("edge-source", source, source, index, kind=edge.kind)
        )
        if isinstance(edge, ConditionalEdge):
            for label, target in edge.path_map.items():
                if target == _END_LITERAL:
                    resolved: str | None = END_VERTEX
                elif target in node_ids:
                    resolved = target
                else:
                    resolved = (
                        target
                        if record(
                            UnresolvedReference(
                                "path-map-target",
                                target,
                                source,
                                index,
                                label=label,
                                kind="conditional",
                            )
                        )
                        else None
                    )
                if source_ok and resolved is not None:
                    edges.append(
                        ExpandedEdge(source, resolved, "conditional", "edges", index, label)
                    )
            continue
        # §1.4 Step 1 `continue`s past an unresolved `from` on a normal/send edge, so its
        # `to` is never checked and never emits — while a conditional edge's labels still
        # are (DEC-12). The asymmetry is the frozen text's; mirroring it keeps the record
        # list one-to-one with the findings P-01 emits.
        if not source_ok:
            continue
        target_ok = edge.to in node_ids or record(
            UnresolvedReference("edge-target", edge.to, source, index, kind=edge.kind)
        )
        if target_ok:
            edges.append(ExpandedEdge(source, edge.to, edge.kind, "edges", index))

    vertices = tuple(sorted(node_ids | carried | set(SENTINEL_VERTICES), key=ledger_sort_key))
    return GraphModel(
        vertices=vertices,
        node_ids=node_ids,
        edges=tuple(edges),
        unresolved=tuple(unresolved),
        carried=frozenset(carried),
    )


# ── Tarjan ───────────────────────────────────────────────────────────────────────────────


def _tarjan(model: GraphModel) -> Components:
    """Tarjan's strongly-connected-components algorithm, iterative (Tarjan 1972).

    Roots are taken in :attr:`GraphModel.vertices` order and successors in
    :meth:`GraphModel.successors` order, so both the partition and its emission order are a
    pure function of the model. Parallel edges are irrelevant to connectivity, which is why
    the de-duplicated successor view is the right one here; self-loops are picked up by the
    non-triviality test rather than by the traversal.
    """
    order: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    groups: list[tuple[str, ...]] = []
    counter = 0

    for root in model.vertices:
        if root in order:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            vertex, cursor = work[-1]
            if cursor == 0:
                order[vertex] = low[vertex] = counter
                counter += 1
                stack.append(vertex)
                on_stack.add(vertex)
            successors = model.successors(vertex)
            descended = False
            for position in range(cursor, len(successors)):
                successor = successors[position]
                if successor not in order:
                    work[-1] = (vertex, position + 1)
                    work.append((successor, 0))
                    descended = True
                    break
                if successor in on_stack:
                    low[vertex] = min(low[vertex], order[successor])
            if descended:
                continue
            work.pop()
            if low[vertex] == order[vertex]:
                group: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == vertex:
                        break
                groups.append(tuple(sorted(group, key=ledger_sort_key)))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[vertex])

    members = tuple(groups)
    nontrivial = frozenset(
        index
        for index, group in enumerate(members)
        if len(group) > 1 or model.has_self_loop(group[0])
    )
    return Components(members=members, nontrivial=nontrivial)
