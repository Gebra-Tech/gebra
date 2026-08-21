"""The networkx representation the topology diff runs over — IR-SPEC §4.1 as a multigraph.

Brief D-11 asks for "graph-structural diff algorithms over networkx representations of the
Gebra IR"; :func:`topology_graph` is that representation. It realizes the §4.1 model view —
sentinels materialized, labels expanded — with one deliberate difference from the shared
validator model (:mod:`gebra.verify.graph`), stated up front:

**This graph is total over authored content.** The validator model follows DEC-12 and drops
what does not resolve, because P-01 owns reporting it. A diff that dropped unresolved
references would go blind exactly where review needs it most — deleting the edge
``triage → ghost`` from a workflow must report as a removed edge whether or not ``ghost``
ever resolved. So every authored edge and every wired ``entry``/``finish`` member appears
here, endpoints materialized as vertices when nothing declared them (the ``role`` vertex
attribute keeps a declared node distinguishable from a bare reference), and the edge-diff
universe is exactly the ``graph_version`` hash scope's topology slice: two IRs with one
digest build graphs with one descriptor multiset.

The §4.1 equivalences, as built here:

* **(m1)/(m2)** — each member of the ``entry``/``finish`` *wired set* becomes a ``normal``
  edge from ``__start__`` / to ``__end__``, carrying ``origin="entry"``/``"finish"``. The
  wired **set**: §6.3 collapses duplicate members and picks one canonical surface per set
  (§4.2 m5), so the graph collapses them too — a duplicated ``entry`` member is not a
  second edge, exactly as it is not a digest change.
* **(m3)** — a ``path_map`` label valued ``"END"`` wires to ``__end__``; the edge's
  ``target`` attribute keeps the authored ``"END"`` spelling. The blessing is positional
  and unconditional (ledger §1/§4): it applies even when a node happens to be *named*
  ``END``, which is why that node can never be a router target.
* **(m4)** — not adopted, per PD-007 Q2: ``to: "END"`` on a ``normal``/``send`` edge is an
  ordinary reference, wired verbatim to a vertex named ``END`` (a declared node of that
  name, or a bare reference vertex). Note that IR-SPEC §4.1's own (m4) sentence still reads
  it as a sentinel incidence: neither PD-007 nor DEC-12 amended the spec text, so the two
  disagree on paper and the ruling is what this module follows — as the shared validator
  model does.
* **(m5)** — ``__start__``/``__end__`` are materialized once and never appear in
  ``nodes[]`` (the §5 grammar refuses the reserved segments, so the sentinel names cannot
  collide with a declared node). A *reference* spelling a reserved segment — ``entry:
  ["__end__"]``, ``from: "__start__"`` — is admitted by the IR models (reference-role
  strings are unconstrained there) and lands on the sentinel vertex of that name, totality
  winning over (m5)'s letter on such a document; the edge attributes keep the authored
  spelling, so the diff is unaffected.

Every edge carries its whole descriptor as attributes — ``origin``, ``kind``, ``label``,
``condition``, ``target`` (the authored reference the edge encodes: the wired member on an
``entry``/``finish`` wiring, the authored target on an ``ir.edges`` edge — equal to the
head vertex except on a finish wiring and an m3 expansion). A tail vertex name is the
authored ``from`` verbatim, so a consumer reads authored facts off attributes and tails and
never reconstructs them from the sentinel-mapped heads.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07): the input is
a validated IR model, the output a networkx graph of plain strings. networkx itself is in
reach by design — it is the representation the brief mandates — and the WA-07 tripwire for
this path (``tests/diff/test_topology.py``) pins that the substrate and the network stay
out.
"""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

import networkx as nx

from gebra.diff.models import ledger_sort_key
from gebra.ir import ConditionalEdge, WorkflowIR, refuse_dynamic_edges

__all__ = [
    "END_LITERAL",
    "END_VERTEX",
    "START_VERTEX",
    "EdgeOrigin",
    "VertexRole",
    "topology_graph",
    "wired_set",
]

#: The per-level entry pseudo-node, spelled as the ledger §5 reserved segment — reserved on
#: ``nodes[].id`` by the §5 grammar, so no declared node can collide with it.
START_VERTEX: Final = "__start__"

#: The per-level exit pseudo-node (ledger §5).
END_VERTEX: Final = "__end__"

#: The one target string ledger §1/§4 bless inside a ``path_map`` value (IR-SPEC §4.1 m3).
END_LITERAL: Final = "END"

#: Which surface field carried an edge: a member of ``ir.edges``, or an implicit sentinel
#: wiring of IR-SPEC §4.1 (m1)/(m2).
EdgeOrigin: TypeAlias = Literal["entry", "finish", "edges"]

#: What a vertex is. ``"node"`` — declared in ``ir.nodes`` (the identity universe the node
#: diff runs over); ``"start"``/``"end"`` — the sentinels; ``"reference"`` — a string some
#: edge or wiring names that no node declares (kept so the graph stays total; whether it
#: *should* resolve is P-01's question, never this engine's).
VertexRole: TypeAlias = Literal["start", "end", "node", "reference"]


def wired_set(value: str | tuple[str, ...]) -> tuple[str, ...]:
    """The ``entry``/``finish`` wired set: duplicates collapsed, ledger §6 order.

    The scalar and list surface forms land on one value, exactly as canonicalization lands
    them on one canonical surface (IR-SPEC §6.3; §4.2 m5) — so the graphs and diffs of two
    spellings of one wired set are equal, as their digests are.
    """
    members = (value,) if isinstance(value, str) else value
    return tuple(sorted(set(members), key=ledger_sort_key))


def topology_graph(ir: WorkflowIR) -> nx.MultiDiGraph:
    """Build the sentinel-augmented, label-expanded multigraph of ``ir``.

    A multigraph, not a digraph: parallel authored edges are distinct content (the canonical
    form keeps duplicate edge objects, so they are in the digest), and two labels of one
    router may target one node. Vertices carry ``role`` (:data:`VertexRole`); edges carry
    ``origin``, ``kind``, ``label``, ``condition`` and ``target`` as described in the module
    docstring.

    Equal IRs build graphs with equal vertex/attribute sets and equal edge-descriptor
    multisets. Iteration *order* over an ``nx`` graph follows insertion, which follows the
    authored document — so consumers that need a canonical order sort, as the diff does;
    none of the diff's output depends on it.

    **``ir_version`` 1.1 is declined, and totality is the reason.** A ``dynamic`` edge
    (DEC-28, 2026-08-09) has no head at all, and this graph's contract is that its
    edge-descriptor universe *is* the ``graph_version`` topology slice — so dropping such an
    edge would make two documents with different digests diff as unchanged, which is the one
    failure mode a review tool must not have. What a headless edge should look like in an
    ``nx`` representation is unruled (a materialized pseudo-head would be exactly the phantom
    vertex DEC-26 closed elsewhere), so this refuses rather than choosing.

    Raises:
        DynamicEdgeUnsupportedError: if the document carries a ``dynamic`` edge (above).
    """
    static_edges = refuse_dynamic_edges(ir.edges, consumer="the topology-diff graph")
    graph = nx.MultiDiGraph()
    graph.add_node(START_VERTEX, role="start")
    graph.add_node(END_VERTEX, role="end")
    for node in ir.nodes:
        graph.add_node(node.id, role="node")

    def vertex(reference: str) -> str:
        """The vertex for a reference, materialized with ``role="reference"`` if new."""
        if reference not in graph:
            graph.add_node(reference, role="reference")
        return reference

    for member in wired_set(ir.entry):
        graph.add_edge(
            START_VERTEX,
            vertex(member),
            origin="entry",
            kind="normal",
            label=None,
            condition=None,
            target=member,
        )
    for member in wired_set(ir.finish):
        graph.add_edge(
            vertex(member),
            END_VERTEX,
            origin="finish",
            kind="normal",
            label=None,
            condition=None,
            target=member,
        )
    for edge in static_edges:
        source = vertex(edge.from_)
        if isinstance(edge, ConditionalEdge):
            for label, target in edge.path_map.items():
                head = END_VERTEX if target == END_LITERAL else vertex(target)
                graph.add_edge(
                    source,
                    head,
                    origin="edges",
                    kind="conditional",
                    label=label,
                    condition=edge.condition,
                    target=target,
                )
        else:
            graph.add_edge(
                source,
                vertex(edge.to),
                origin="edges",
                kind=edge.kind,
                label=None,
                condition=edge.condition,
                target=edge.to,
            )
    return graph
