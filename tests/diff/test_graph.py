"""The networkx representation — IR-SPEC §4.1 (m1)–(m5) as :func:`topology_graph` builds it.

What is pinned here: the sentinel vertices and their roles; the wired-set collapse on
``entry``/``finish`` (§6.3/§4.2 m5); label expansion with the positional ``"END"`` blessing
(m3, ledger §1/§4); PD-007's refusal to read ``to: "END"`` as a sentinel; multigraph
parallels; and the totality rule this graph takes where the shared validator model
(:mod:`gebra.verify.graph`) takes DEC-12's drop-and-record — every authored edge appears,
undeclared endpoints materialized as ``role="reference"`` vertices.

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
"""

from __future__ import annotations

import networkx as nx
import pytest

from gebra.diff import (
    END_VERTEX,
    START_VERTEX,
    topology_graph,
    wired_set,
)
from gebra.ir.models import (
    ConditionalEdge,
    DynamicEdge,
    DynamicEdgeUnsupportedError,
    NormalEdge,
    SendEdge,
    WorkflowIR,
)
from tests.versioning.workflows import EDGES, NODES, node, workflow


def _descriptors(graph: nx.MultiDiGraph) -> list[tuple[str, str, tuple[tuple[str, object], ...]]]:
    """Every edge as ``(tail, head, sorted-attrs)`` — the order-free comparison view."""
    return sorted(
        (tail, head, tuple(sorted(data.items()))) for tail, head, data in graph.edges(data=True)
    )


# ── Vertices and roles ───────────────────────────────────────────────────────────────────


def test_sentinels_are_materialized_with_their_roles() -> None:
    graph = topology_graph(workflow())

    assert graph.nodes[START_VERTEX] == {"role": "start"}
    assert graph.nodes[END_VERTEX] == {"role": "end"}


def test_declared_nodes_carry_the_node_role() -> None:
    graph = topology_graph(workflow())

    assert {vertex for vertex, role in graph.nodes(data="role") if role == "node"} == {
        "plan",
        "work",
        "report",
    }


def test_an_undeclared_endpoint_is_a_reference_vertex() -> None:
    """Totality over authored content: the edge to ``ghost`` exists, and ``ghost`` is a
    vertex — but a *reference* vertex, distinguishable from a declared node, which is what
    keeps the node diff's identity universe exactly ``ir.nodes``."""
    graph = topology_graph(
        workflow(edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="ghost")))
    )

    assert graph.nodes["ghost"] == {"role": "reference"}
    assert graph.has_edge("plan", "ghost")


def test_a_reference_spelling_a_reserved_segment_lands_on_the_sentinel_vertex() -> None:
    """Reference-role strings are unconstrained by the IR models, so ``entry: ["__end__"]``
    loads; the graph wires it to the vertex of that name — the sentinel — keeping the graph
    total, and the edge's authored attributes keep the diff unaffected."""
    graph = topology_graph(workflow(entry=("plan", "__end__")))

    assert graph.nodes[END_VERTEX] == {"role": "end"}
    wirings = [
        data["target"]
        for _tail, head, data in graph.edges(START_VERTEX, data=True)
        if head == END_VERTEX
    ]
    assert wirings == ["__end__"]


# ── START/END wiring (m1/m2) and the wired-set collapse ──────────────────────────────────


def test_entry_and_finish_wire_the_sentinels() -> None:
    graph = topology_graph(workflow())

    assert _descriptors(graph) == [
        (
            START_VERTEX,
            "plan",
            (
                ("condition", None),
                ("kind", "normal"),
                ("label", None),
                ("origin", "entry"),
                ("target", "plan"),
            ),
        ),
        (
            "plan",
            "work",
            (
                ("condition", None),
                ("kind", "normal"),
                ("label", None),
                ("origin", "edges"),
                ("target", "work"),
            ),
        ),
        (
            "report",
            END_VERTEX,
            (
                ("condition", None),
                ("kind", "normal"),
                ("label", None),
                ("origin", "finish"),
                ("target", "report"),
            ),
        ),
        (
            "work",
            "report",
            (
                ("condition", None),
                ("kind", "normal"),
                ("label", None),
                ("origin", "edges"),
                ("target", "report"),
            ),
        ),
    ]


def test_the_wired_set_collapses_duplicates_and_surface_forms() -> None:
    """A scalar, a singleton list and a duplicated list are one wired set — the same
    collapse §6.3 applies before the digest is taken, so graph equality tracks digest
    equality on these forms."""
    scalar = topology_graph(workflow(entry="plan"))
    singleton = topology_graph(workflow(entry=("plan",)))
    duplicated = topology_graph(workflow(entry=("plan", "plan")))

    assert _descriptors(scalar) == _descriptors(singleton) == _descriptors(duplicated)


def test_wired_set_orders_by_the_ledger_comparator() -> None:
    assert wired_set(("b", "a", "b")) == ("a", "b")
    assert wired_set("only") == ("only",)


# ── Label expansion (m3) and PD-007 (m4 unadopted) ───────────────────────────────────────


def test_a_path_map_expands_one_edge_per_label() -> None:
    graph = topology_graph(
        workflow(
            edges=(
                ConditionalEdge(
                    kind="conditional",
                    **{"from": "plan"},
                    condition="route",
                    path_map={"go": "work", "skip": "report"},
                ),
                EDGES[1],
            )
        )
    )

    labelled = sorted(
        (data["label"], head)
        for _tail, head, data in graph.edges("plan", data=True)
        if data["origin"] == "edges"
    )
    assert labelled == [("go", "work"), ("skip", "report")]


def test_an_end_valued_label_wires_the_end_sentinel_and_keeps_the_authored_spelling() -> None:
    graph = topology_graph(
        workflow(
            edges=(
                ConditionalEdge(kind="conditional", **{"from": "plan"}, path_map={"done": "END"}),
                EDGES[1],
            ),
        )
    )

    (edge,) = [
        (head, data)
        for _tail, head, data in graph.edges("plan", data=True)
        if data["label"] == "done"
    ]
    assert edge[0] == END_VERTEX
    assert edge[1]["target"] == "END"


def test_the_end_blessing_is_positional_even_when_a_node_is_named_end() -> None:
    """Ledger §1/§4 bless ``"END"`` inside a ``path_map`` value unconditionally — which is
    exactly why a node named ``END`` can never be a router target."""
    graph = topology_graph(
        workflow(
            nodes=(*NODES, node("END", None)),
            edges=(
                ConditionalEdge(kind="conditional", **{"from": "plan"}, path_map={"done": "END"}),
                EDGES[1],
            ),
        )
    )

    heads = [
        head for _tail, head, data in graph.edges("plan", data=True) if data["label"] == "done"
    ]
    assert heads == [END_VERTEX]
    assert graph.nodes["END"] == {"role": "node"}


def test_to_end_on_a_normal_edge_is_an_ordinary_reference() -> None:
    """PD-007 Q2 (ratified 2026-07-24) left (m4) unadopted: ``to: "END"`` resolves like any
    other reference — here to nothing, so it is a reference vertex, never the sentinel."""
    graph = topology_graph(
        workflow(edges=(*EDGES, NormalEdge(kind="normal", **{"from": "work"}, to="END")))
    )

    assert graph.nodes["END"] == {"role": "reference"}
    assert graph.has_edge("work", "END")
    assert not graph.has_edge("work", END_VERTEX)


# ── Multigraph semantics ─────────────────────────────────────────────────────────────────


def test_parallel_authored_edges_stay_distinct() -> None:
    """The canonical form keeps duplicate edge objects (§6.2 sorts, removes nothing), so
    multiplicity is content and the graph is a multigraph."""
    graph = topology_graph(workflow(edges=(*EDGES, EDGES[0])))

    assert graph.number_of_edges("plan", "work") == 2


def test_two_labels_of_one_router_may_target_one_node() -> None:
    graph = topology_graph(
        workflow(
            edges=(
                ConditionalEdge(
                    kind="conditional",
                    **{"from": "plan"},
                    path_map={"go": "work", "retry": "work"},
                ),
                EDGES[1],
            )
        )
    )

    assert graph.number_of_edges("plan", "work") == 2


def test_a_guard_rides_every_kind() -> None:
    """``condition`` is admitted on every kind (inert on ``normal``/``send``, IR-SPEC §2.4)
    and is hash-scope content, so the graph carries it wherever it was authored."""
    graph = topology_graph(
        workflow(
            edges=(
                NormalEdge(kind="normal", **{"from": "plan"}, to="work", condition="retry < 3"),
                SendEdge(kind="send", **{"from": "work"}, to="report", condition="fan"),
            )
        )
    )

    conditions = {
        (tail, data["kind"]): data["condition"]
        for tail, _head, data in graph.edges(data=True)
        if data["origin"] == "edges"
    }
    assert conditions == {("plan", "normal"): "retry < 3", ("work", "send"): "fan"}


# ── Determinism of the representation ────────────────────────────────────────────────────


def test_equal_documents_build_equal_graphs() -> None:
    """Vertex-attribute sets and edge-descriptor multisets are pure functions of the
    document — the property the diff's own determinism stands on."""
    first = topology_graph(workflow())
    second = topology_graph(workflow())

    assert sorted(first.nodes(data=True)) == sorted(second.nodes(data=True))
    assert _descriptors(first) == _descriptors(second)


# ── ir 1.1: the `dynamic` kind, declined because totality is this graph's contract ────────


def test_a_dynamic_edge_is_declined_rather_than_dropped() -> None:
    """This graph's edge universe *is* the ``graph_version`` topology slice, so it cannot drop one.

    A ``dynamic`` edge (DEC-28) has no head, and an ``nx`` edge needs two endpoints. Dropping it
    would break the module's own contract in the direction that matters for a review tool: two
    documents whose digests differ would diff as unchanged. Materializing a pseudo-head instead
    would invent a vertex — the phantom-leak class DEC-26 closed elsewhere — and what a headless
    edge should look like here is unruled. So it declines, and says which edge and why.
    """
    base = workflow()
    ir = WorkflowIR(
        ir_version="1.1",
        entry=base.entry,
        finish=base.finish,
        state=base.state,
        nodes=base.nodes,
        edges=(
            NormalEdge(kind="normal", **{"from": "plan"}, to="work"),
            DynamicEdge(kind="dynamic", **{"from": "work"}, condition="route_legs"),
        ),
        runtime=base.runtime,
    )

    with pytest.raises(DynamicEdgeUnsupportedError) as caught:
        topology_graph(ir)

    assert isinstance(caught.value, NotImplementedError)
    assert "the topology-diff graph" in str(caught.value)
    assert "edges[1]" in str(caught.value)
