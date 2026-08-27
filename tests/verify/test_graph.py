"""VAL-03 — the shared graph pre-analysis P-01/P-02/P-04/P-06 read their graph from.

Three obligations, and the module is tested against each:

* **label expansion** (ir-field-ledger §4) — every ``path_map`` label is its own directed
  edge, expanded before any graph algorithm runs, with parallels and self-loops kept
  distinct;
* **sentinel-augmented model construction** (IR-SPEC §4.1 m1–m5) — ``__start__``/``__end__``
  materialized as real vertices, wired from ``entry``/``finish`` and from the blessed
  ``path_map`` ``"END"`` literal;
* **Tarjan SCC + condensation** (TERMINATION-WITNESS-SPEC §5 steps 1–2, cited verbatim by
  PROPERTY-CATALOG-SPEC §6.4 Phases 0/2 and §4.4 Step 3).

The corpus is the primary evidence and it is a frozen contract surface (WA-04/WA-11):
nothing here writes to it. Every one of the 71 vendored fixtures' IR blocks is built into a
model and cross-checked against an independent naive oracle, and the topologies whose SCCs
the specs and fixtures name by hand are pinned individually. Hand-authored IRs cover only
the shapes the corpus does not carry — the ``"END"`` literals, unresolved ``entry``/``finish``
ids, and graphs deep enough to prove the traversals are iterative.

Nothing here executes a workflow node, calls a model, or opens a network connection (WA-07);
:func:`test_building_models_over_the_corpus_creates_no_socket_and_resolves_no_name` proves it
in a fresh interpreter, import **and** call.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from itertools import groupby, pairwise
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from gebra.ir import DynamicEdgeUnsupportedError, WorkflowIR, canonical_bytes, load_json
from gebra.testing import load_corpus
from gebra.verify.graph import (
    END_VERTEX,
    SENTINEL_VERTICES,
    START_VERTEX,
    ExpandedEdge,
    GraphModel,
    UnresolvedReference,
    build_graph_model,
    canonical_rotation,
    ledger_sort_key,
)
from tests.conftest import FIXTURES_DIR

# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _ir(document: dict[str, Any]) -> WorkflowIR:
    """A hand-authored IR through the documented ingestion path (IR-SPEC §2.5 note 4)."""
    return load_json(WorkflowIR, json.dumps({"ir_version": "1.0", **document}))


def _nodes(*ids: str) -> list[dict[str, str]]:
    return [{"id": node_id} for node_id in ids]


def _model(document: dict[str, Any], **options: bool) -> GraphModel:
    return build_graph_model(_ir(document), **options)


def _fixture_model(relative: str) -> GraphModel:
    fixture = next(f for f in _CORPUS if f.fixture_id == relative)
    assert fixture.ir is not None
    return build_graph_model(fixture.ir)


def _arcs(model: GraphModel) -> list[tuple[str, str, str | None]]:
    return [(edge.source, edge.target, edge.label) for edge in model.edges]


def _naive_reachable(model: GraphModel, source: str) -> set[str]:
    """Transitive closure by repeated relaxation — an oracle written a different way.

    ``source`` is subtracted at the end, as ``nx.descendants`` does unconditionally.
    """
    seen: set[str] = set(model.successors(source))
    changed = True
    while changed:
        changed = False
        for vertex in list(seen):
            for successor in model.successors(vertex):
                if successor not in seen:
                    seen.add(successor)
                    changed = True
    return seen - {source}


def _naive_components(model: GraphModel) -> set[frozenset[str]]:
    """Mutual reachability, computed without Tarjan — the SCC oracle."""
    closure = {vertex: _naive_reachable(model, vertex) for vertex in model.vertices}
    return {
        frozenset(
            {vertex}
            | {
                other
                for other in model.vertices
                if other in closure[vertex] and vertex in closure[other]
            }
        )
        for vertex in model.vertices
    }


_CORPUS = load_corpus(FIXTURES_DIR)

#: Every IR snapshot in the corpus, with the fixture id it came from — 71 fixtures, and the
#: evolution pairs contribute both of their snapshots.
_CORPUS_IRS: list[tuple[str, WorkflowIR]] = [
    (f"{fixture.fixture_id}#{index}", ir)
    for fixture in _CORPUS
    for index, ir in enumerate(fixture.irs)
]


# ── The ledger §6 comparator ─────────────────────────────────────────────────────────────


def test_the_comparator_is_utf16_code_units_not_pythons_default() -> None:
    """Ledger §6: ids compare as **UTF-16 code units** (RFC 8785 §3.2.3), not code points.

    Pinned against the IR canonicalizer's own ``nodes[]`` ordering rather than restated, so
    the two cannot drift: they disagree exactly for ids mixing a non-BMP scalar with
    U+E000..U+FFFF, where Python sorts U+1F600 after U+FFFD and the ledger sorts it before.
    """
    ids = ("\U0001f600", "�", "a")
    assert sorted(ids) != sorted(ids, key=ledger_sort_key)

    ir = _ir({"entry": "a", "finish": "a", "nodes": _nodes(*ids), "edges": []})
    canonical = json.loads(canonical_bytes(ir))
    model = build_graph_model(ir)
    ordered = [vertex for vertex in model.vertices if vertex not in SENTINEL_VERTICES]
    assert ordered == [node["id"] for node in canonical["nodes"]]


def test_canonical_rotation_puts_the_least_id_first() -> None:
    """§0.3 ``CycleLocation``: "lexicographically-least id first", under the ledger order."""
    assert canonical_rotation(("c", "a", "b")) == ("a", "b", "c")
    assert canonical_rotation(("a", "b", "c")) == ("a", "b", "c")
    assert canonical_rotation(()) == ()
    assert canonical_rotation(("only",)) == ("only",)
    assert canonical_rotation(("�", "\U0001f600")) == ("\U0001f600", "�")


# ── Label expansion (ledger §4) ──────────────────────────────────────────────────────────


def test_each_path_map_label_becomes_its_own_directed_edge() -> None:
    """Ledger §4: "each ``path_map`` label denotes one logical directed edge"."""
    model = _model(
        {
            "entry": "router",
            "finish": "b",
            "nodes": _nodes("router", "a", "b"),
            "edges": [
                {
                    "from": "router",
                    "kind": "conditional",
                    "path_map": {"left": "a", "right": "b"},
                }
            ],
        }
    )
    assert ("router", "a", "left") in _arcs(model)
    assert ("router", "b", "right") in _arcs(model)
    assert [edge.kind for edge in model.out_edges("router")] == ["conditional"] * 2


def test_normal_and_send_edges_map_one_to_one() -> None:
    """T-W-SPEC §1: a send edge's fan-out multiplicity "is a runtime quantity, not graph
    structure — it contributes exactly one structural edge"."""
    model = _fixture_model("mixed/09-send-fanout-billable-no-idempotency-in-retry.yaml")
    dispatched = model.out_edges("dispatch_bookings")
    assert [(edge.target, edge.kind) for edge in dispatched] == [("book_segment", "send")]


def test_parallel_label_edges_stay_distinct() -> None:
    """The multigraph requirement of catalog §2.4 Step 0, on the one corpus case of it.

    ``termination-witness/negative-03`` routes two labels of one router to the same node.
    Merging them — what a simple digraph would do — would let one discharged label-edge
    discharge its sibling, which §2.4 calls out as over-discharge and therefore unsound.
    """
    model = _fixture_model("termination-witness/negative-03-counter-guard-without-wired-exit.yaml")
    parallel = [edge for edge in model.out_edges("throttle_check") if edge.target == "fetch_rates"]
    assert len(parallel) == 2
    assert sorted(edge.label or "" for edge in parallel) == ["delayed", "immediate"]
    assert model.successors("throttle_check") == ("fetch_rates",)


def test_two_labels_to_one_target_are_two_edges_and_one_successor() -> None:
    model = _model(
        {
            "entry": "r",
            "finish": "t",
            "nodes": _nodes("r", "t"),
            "edges": [{"from": "r", "kind": "conditional", "path_map": {"x": "t", "y": "t"}}],
        }
    )
    assert len(model.out_edges("r")) == 2
    assert model.successors("r") == ("t",)
    assert model.degree("r", origins=("edges",)) == 2


def test_expansion_happens_before_any_analysis() -> None:
    """A cycle that exists only through one label of a router is a cycle of the model."""
    model = _model(
        {
            "entry": "a",
            "finish": "b",
            "nodes": _nodes("a", "b"),
            "edges": [
                {"from": "a", "to": "b"},
                {"from": "b", "kind": "conditional", "path_map": {"again": "a"}},
            ],
        }
    )
    assert model.components.is_nontrivial("a")
    assert model.components.members_of("a") == ("a", "b")


# ── Sentinel-augmented construction (IR-SPEC §4.1 m1–m5) ─────────────────────────────────


def test_m1_entry_becomes_a_start_edge_in_both_surface_forms() -> None:
    scalar = _model({"entry": "a", "finish": "a", "nodes": _nodes("a"), "edges": []})
    assert _arcs(scalar) == [(START_VERTEX, "a", None), ("a", END_VERTEX, None)]

    listed = _model({"entry": ["a", "b"], "finish": "b", "nodes": _nodes("a", "b"), "edges": []})
    assert (START_VERTEX, "a", None) in _arcs(listed)
    assert (START_VERTEX, "b", None) in _arcs(listed)
    assert [edge.index for edge in listed.out_edges(START_VERTEX)] == [0, 1]


def test_m2_finish_becomes_an_end_edge_in_both_surface_forms() -> None:
    listed = _model({"entry": "a", "finish": ["a", "b"], "nodes": _nodes("a", "b"), "edges": []})
    assert listed.predecessors(END_VERTEX) == ("a", "b")
    assert {edge.origin for edge in listed.in_edges(END_VERTEX)} == {"finish"}


def test_m3_a_path_map_end_label_targets_the_end_sentinel() -> None:
    """Ledger §1/§4 bless the ``"END"`` literal as a ``path_map`` value; §4.1 (m3) reads it
    as an incidence on END, and T-W-SPEC §1 adds that such a label-edge appears in the
    residual "like any other expanded edge"."""
    model = _model(
        {
            "entry": "r",
            "finish": "a",
            "nodes": _nodes("r", "a"),
            "edges": [{"from": "r", "kind": "conditional", "path_map": {"stop": "END", "go": "a"}}],
        }
    )
    assert ("r", END_VERTEX, "stop") in _arcs(model)
    assert model.unresolved == ()
    assert "END" not in model.vertices


def test_m4_the_end_literal_is_not_blessed_on_a_normal_or_send_edge() -> None:
    """PD-007 Q2 (ratified 2026-07-24): the ``"END"`` blessing stays ``path_map``-only.

    IR-SPEC §4.1 (m4) reads *an edge targeting END* as a sentinel incidence, and the open
    item was whether ``to: "END"`` spells one. The ruling left it unblessed, so the literal
    is looked up in V like any other target and, naming no node, is recorded rather than
    resolved — which is also what catalog §1.4 Step 1 does with it. No corpus fixture writes
    the shape (PD-007 confirmed that empirically), so nothing vendored changes either way.
    """
    for kind in ("normal", "send"):
        model = _model(
            {
                "entry": "a",
                "finish": "a",
                "nodes": _nodes("a"),
                "edges": [{"from": "a", "kind": kind, "to": "END"}],
            }
        )
        assert model.edges == (
            ExpandedEdge(START_VERTEX, "a", "normal", "entry", 0),
            ExpandedEdge("a", END_VERTEX, "normal", "finish", 0),
        )
        assert model.unresolved == (UnresolvedReference("edge-target", "END", "a", 0, kind=kind),)


def test_m5_holds_by_construction_on_every_corpus_topology() -> None:
    """§4.1 (m5): START has no incoming edge, END no outgoing edge, and neither sentinel
    appears in ``nodes[]``."""
    for label, ir in _CORPUS_IRS:
        model = build_graph_model(ir)
        assert model.in_edges(START_VERTEX) == (), label
        assert model.out_edges(END_VERTEX) == (), label
        assert not (model.node_ids & set(SENTINEL_VERTICES)), label


def test_m5_the_reserved_spellings_can_never_be_declared_nodes() -> None:
    """The other half of (m5) is the node-id grammar's, not this module's: IR-SPEC §5.1
    reserves ``__start__``/``__end__``, so a document naming one fails to load at all."""
    for reserved in SENTINEL_VERTICES:
        with pytest.raises(ValidationError):
            _ir(
                {
                    "entry": reserved,
                    "finish": reserved,
                    "nodes": _nodes(reserved),
                    "edges": [],
                }
            )


def test_the_sentinels_are_materialized_even_for_an_edgeless_graph() -> None:
    model = _model({"entry": "a", "finish": "a", "nodes": _nodes("a"), "edges": []})
    assert set(SENTINEL_VERTICES) <= set(model.vertices)
    assert model.node_ids == frozenset({"a"})


def test_the_end_sentinel_is_always_a_trivial_component() -> None:
    """T-W-SPEC §1: ``__end__`` has no outgoing edges, so "an END-label always satisfies the
    D4 exit test and can never lie on a cycle"."""
    for label, ir in _CORPUS_IRS:
        model = build_graph_model(ir)
        assert not model.components.is_nontrivial(END_VERTEX), label
        assert not model.components.is_nontrivial(START_VERTEX), label


# ── Unresolved references (DEC-12; catalog §1.4 Step 1) ──────────────────────────────────


def test_a_dangling_path_map_target_contributes_no_vertex_and_no_edge() -> None:
    """``graph-well-formed/negative-03`` — the catalog's own typo example (§1.2)."""
    model = _fixture_model("graph-well-formed/negative-03-path-map-typo-dangling-target.yaml")
    assert model.unresolved == (
        UnresolvedReference(
            "path-map-target",
            "send_confirmatoin",
            "review_booking",
            1,
            label="confirm",
            kind="conditional",
        ),
    )
    assert "send_confirmatoin" not in model.vertices
    assert model.carried == frozenset()
    assert all(edge.target != "send_confirmatoin" for edge in model.edges)


def test_an_unresolved_edge_source_is_recorded_and_its_edge_dropped() -> None:
    """``mixed/04`` carries both roles at once, and DEC-12 folded the dangling *source* into
    ``edge-target-undefined`` (P-01 open item 6). The dropped ``legal_hold_review →
    compliance_log`` edge is what makes ``compliance_log`` unreachable, which is the
    fixture's own second finding."""
    model = _fixture_model("mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml")
    assert model.unresolved == (
        UnresolvedReference(
            "path-map-target",
            "legal_hold_review",
            "triage",
            1,
            label="legal",
            kind="conditional",
        ),
        UnresolvedReference(
            "edge-source", "legal_hold_review", "legal_hold_review", 2, kind="normal"
        ),
    )
    assert "legal_hold_review" not in model.vertices
    assert "compliance_log" not in model.descendants(START_VERTEX)


def test_an_unresolved_source_still_has_its_labels_resolved_and_checked() -> None:
    """DEC-12: "labels still resolved and checked, but no expansion edges inserted"."""
    model = _model(
        {
            "entry": "a",
            "finish": "a",
            "nodes": _nodes("a"),
            "edges": [
                {
                    "from": "ghost",
                    "kind": "conditional",
                    "path_map": {"here": "a", "nowhere": "phantom"},
                }
            ],
        }
    )
    assert [reference.role for reference in model.unresolved] == [
        "edge-source",
        "path-map-target",
    ]
    assert all(edge.origin != "edges" for edge in model.edges)


def test_every_unresolved_reference_is_recorded_separately() -> None:
    """DEC-12's emission rule: one finding per unresolved reference, no collapse — so two
    labels naming the same missing node are two records, not one."""
    model = _model(
        {
            "entry": "r",
            "finish": "r",
            "nodes": _nodes("r"),
            "edges": [
                {
                    "from": "r",
                    "kind": "conditional",
                    "path_map": {"one": "ghost", "two": "ghost"},
                }
            ],
        }
    )
    assert [reference.label for reference in model.unresolved] == ["one", "two"]


def test_unresolved_entry_and_finish_ids_anchor_where_p01_needs_them() -> None:
    """Catalog §1.4 Step 1 anchors the ``entry`` finding at ``__start__`` and the
    ``finish``-symmetric one at the unresolved id itself (DEC-12)."""
    model = _model({"entry": "ghost", "finish": "spook", "nodes": _nodes("a"), "edges": []})
    assert model.unresolved == (
        UnresolvedReference("entry", "ghost", START_VERTEX, 0),
        UnresolvedReference("finish", "spook", "spook", 0),
    )
    assert model.edges == ()


def test_an_unresolved_source_suppresses_its_own_edges_to_check() -> None:
    """Catalog §1.4 Step 1 ``continue``s past an unresolved ``from`` on a normal/send edge,
    so that edge's ``to`` is never checked and never emits — while a conditional edge's
    labels still are (DEC-12). Mirroring the asymmetry keeps the record list one-to-one with
    the findings P-01 emits, rather than handing it one Step 1 does not have."""
    model = _model(
        {
            "entry": "a",
            "finish": "a",
            "nodes": _nodes("a"),
            "edges": [{"from": "ghost", "to": "phantom"}],
        }
    )
    assert model.unresolved == (
        UnresolvedReference("edge-source", "ghost", "ghost", 0, kind="normal"),
    )


def test_a_reserved_sentinel_spelling_is_never_carried() -> None:
    """(m5) is a structural invariant, and the IR models leave reference-role strings
    unconstrained (only ``nodes[].id`` is checked against the §5 grammar) — so a reference
    spelling ``__start__``/``__end__`` stays recorded and unwired even under the carry flag,
    which would otherwise wire an edge into START or out of END."""
    document = {
        "entry": "a",
        "finish": "a",
        "nodes": _nodes("a"),
        "edges": [
            {"from": "a", "to": START_VERTEX},
            {"from": "a", "kind": "conditional", "path_map": {"out": END_VERTEX}},
        ],
    }
    for carried in (False, True):
        model = _model(document, carry_unresolved_references=carried)
        assert [reference.reference for reference in model.unresolved] == [
            START_VERTEX,
            END_VERTEX,
        ]
        assert model.carried == frozenset()
        assert model.in_edges(START_VERTEX) == ()
        assert [edge.source for edge in model.in_edges(END_VERTEX)] == ["a"]


def test_carrying_unresolved_references_is_opt_in_and_stays_visible() -> None:
    """Catalog §4.4's other reading — "the vertex is still carried, with empty contract" —
    made explicit rather than assumed. The references stay listed either way, so a consumer
    can always tell a declared node from a phantom."""
    document = {
        "entry": "a",
        "finish": "a",
        "nodes": _nodes("a"),
        "edges": [{"from": "a", "to": "ghost"}],
    }
    strict = _model(document)
    carried = _model(document, carry_unresolved_references=True)

    assert "ghost" not in strict.vertices and strict.carried == frozenset()
    assert "ghost" in carried.vertices and carried.carried == frozenset({"ghost"})
    assert carried.has_edge("a", "ghost")
    assert strict.unresolved == carried.unresolved
    assert "ghost" not in carried.node_ids


# ── MultiDiGraph handling ────────────────────────────────────────────────────────────────


def test_a_self_loop_is_a_non_trivial_component() -> None:
    """T-W-SPEC §1: an SCC is non-trivial for "≥ 2 nodes, *or* a single node with a
    self-loop (a self-loop is a simple cycle and MUST count)". The corpus carries exactly
    one: ``signature-soundness/positive-03``'s ``poll_status`` retry label."""
    model = _fixture_model(
        "signature-soundness/positive-03-witnessed-polling-loop-full-contract.yaml"
    )
    assert model.has_self_loop("poll_status")
    assert model.components.members_of("poll_status") == ("poll_status",)
    assert model.components.is_nontrivial("poll_status")
    assert not model.components.is_nontrivial("submit_booking")


def test_degree_can_be_restricted_to_the_authored_edges() -> None:
    """Catalog §1.4 Step 2 counts "only Step-1 edges built from ``ir.edges``" and adds
    ``entry``/``finish`` membership separately — Reading A, ratified by DEC-11. A node wired
    only through ``finish`` therefore has authored degree 0 and is still not an orphan."""
    model = _model({"entry": "a", "finish": "a", "nodes": _nodes("a"), "edges": []})
    assert model.degree("a", origins=("edges",)) == 0
    assert model.degree("a") == 2


def test_a_self_loop_counts_twice_in_the_degree() -> None:
    model = _model(
        {
            "entry": "a",
            "finish": "a",
            "nodes": _nodes("a"),
            "edges": [{"from": "a", "kind": "conditional", "path_map": {"again": "a"}}],
        }
    )
    assert model.degree("a", origins=("edges",)) == 2


def test_successors_are_deduplicated_and_ordered_while_edges_are_not() -> None:
    model = _model(
        {
            "entry": "r",
            "finish": "b",
            "nodes": _nodes("r", "b", "a"),
            "edges": [
                {"from": "r", "kind": "conditional", "path_map": {"z": "b", "y": "a"}},
                {"from": "r", "to": "b"},
            ],
        }
    )
    assert model.successors("r") == ("a", "b")
    assert [edge.label for edge in model.out_edges("r")] == ["z", "y", None]


# ── Tarjan (T-W-SPEC §5 step 2) ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_tarjan_agrees_with_a_naive_mutual_reachability_oracle(label: str, ir: WorkflowIR) -> None:
    """The partition, cross-checked against a computation written a different way.

    The oracle takes each vertex's transitive closure by repeated relaxation and groups by
    mutual reachability — the *definition* of a strongly connected component, with none of
    Tarjan's machinery in it. Run over every IR snapshot in the vendored corpus.
    """
    model = build_graph_model(ir)
    assert {frozenset(group) for group in model.components.members} == _naive_components(model), (
        label
    )


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_the_partition_is_total_and_disjoint(label: str, ir: WorkflowIR) -> None:
    model = build_graph_model(ir)
    members = [vertex for group in model.components.members for vertex in group]
    assert sorted(members) == sorted(model.vertices), label
    assert len(members) == len(set(members)), label
    for vertex in model.vertices:
        assert vertex in model.components.members_of(vertex), label


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_non_triviality_is_the_spec_definition_not_a_size_test(label: str, ir: WorkflowIR) -> None:
    model = build_graph_model(ir)
    for index, group in enumerate(model.components.members):
        expected = len(group) > 1 or model.has_self_loop(group[0])
        assert (index in model.components.nontrivial) is expected, (label, group)


@pytest.mark.parametrize(
    "relative,expected",
    [
        (
            "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml",
            ("assess_itinerary", "draft_itinerary", "quote_fares", "validate_quote"),
        ),
        (
            "termination-witness/negative-02-nested-scc-outer-only-witness.yaml",
            ("assess_itinerary", "draft_itinerary", "judge_fare", "poll_fare"),
        ),
        (
            "termination-witness/negative-04-supervisor-delegation-scc-no-witness.yaml",
            ("flight_worker", "hotel_worker", "supervisor"),
        ),
        (
            "mixed/08-express-path-skips-gate-writer-and-witnessed-exit.yaml",
            ("compliance_gate", "draft_reply", "final_check", "polish", "quality_gate"),
        ),
    ],
)
def test_the_named_flagship_sccs_are_the_ones_the_fixtures_describe(
    relative: str, expected: tuple[str, ...]
) -> None:
    """The topologies the specs and fixture notes name by hand — ``positive-04``'s notes
    spell its SCC out member by member, and the rest are the D1 flagship pair, the
    multi-cycle SCC of §6.1, and the A7 E1 bypass shape."""
    model = _fixture_model(relative)
    nontrivial = [model.components.members[index] for index in sorted(model.components.nontrivial)]
    assert nontrivial == [expected]


def test_the_traversals_are_iterative_on_a_graph_deeper_than_the_recursion_limit() -> None:
    """Catalog §2.4: "All traversals are iterative with explicit stacks — forced, not
    stylistic: deep agent graphs would exhaust the interpreter recursion limit"."""
    depth = 2_000
    assert depth > sys.getrecursionlimit()
    ids = [f"n{index:05d}" for index in range(depth)]
    chain = _ir(
        {
            "entry": ids[0],
            "finish": ids[-1],
            "nodes": _nodes(*ids),
            "edges": [{"from": tail, "to": head} for tail, head in pairwise(ids)]
            + [{"from": ids[-1], "to": ids[0]}],
        }
    )
    model = build_graph_model(chain)
    assert len(model.components.members_of(ids[0])) == depth
    assert model.components.is_nontrivial(ids[0])
    assert len(model.descendants(START_VERTEX)) == depth + 1
    assert len(model.anchor_cycle(ids[0])) == depth


# ── Condensation (catalog §4.4 Step 3) ───────────────────────────────────────────────────


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_the_condensation_is_acyclic_and_its_order_is_topological(
    label: str, ir: WorkflowIR
) -> None:
    model = build_graph_model(ir)
    order = model.condensation_order
    assert sorted(order) == list(range(len(model.components))), label
    position = {index: rank for rank, index in enumerate(order)}
    for tail, heads in enumerate(model.condensation):
        assert tail not in heads, label
        for head in heads:
            assert position[tail] < position[head], label


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_the_worklist_order_keeps_every_vertex_and_never_collapses_a_component(
    label: str, ir: WorkflowIR
) -> None:
    """Catalog §4.1's warning is the point: condensation supplies iteration ORDER only.

    Every vertex appears exactly once and each component's members stay contiguous — so the
    order is a schedule over the *node-level* equations, and a component is never a
    supernode with unioned writes (which memo A8 T3 shows is unsound for P-04's
    must-write-before-first-read).
    """
    model = build_graph_model(ir)
    order = model.worklist_order
    assert sorted(order) == sorted(model.vertices), label
    positions = [model.components.index(vertex) for vertex in order]
    blocks = [index for index, _ in groupby(positions)]
    assert blocks == list(model.condensation_order), label


def test_the_worklist_order_lists_scc_members_individually() -> None:
    model = _fixture_model("termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml")
    members = model.components.members_of("quote_fares")
    assert len(members) == 4
    assert [vertex for vertex in model.worklist_order if vertex in members] == list(members)


# ── Reachability ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_descendants_agree_with_a_naive_closure(label: str, ir: WorkflowIR) -> None:
    model = build_graph_model(ir)
    for vertex in model.vertices:
        assert model.descendants(vertex) == _naive_reachable(model, vertex), (label, vertex)


def test_an_unreachable_node_is_absent_from_the_start_closure() -> None:
    """``graph-well-formed/negative-01`` — condition (i) isolated from (iii): the stranded
    handler participates in an edge, so it is wired, and is still unreachable."""
    model = _fixture_model("graph-well-formed/negative-01-unreachable-escalation-node.yaml")
    assert model.node_ids - model.descendants(START_VERTEX) == frozenset({"escalate_to_human"})
    assert model.degree("escalate_to_human", origins=("edges",)) == 1


def test_a_vertex_is_never_its_own_descendant_even_on_a_cycle() -> None:
    """``nx.descendants`` — the primitive §1.4 Step 3 and §4.4 Steps 2/4 name — subtracts the
    source unconditionally. §4.4 Step 2's ``Reach := {START} ∪ nx.descendants(G, START)``
    only needs that union because of it.

    The exclusion is envelope-visible in §4.4's
    ``downstream_writers = W[k] ∩ nx.descendants(G, v)``: a self-writing reader sitting on a
    cycle must not be listed as its own downstream writer. Whether a vertex lies on a cycle
    is a different question with its own answer, ``components.is_nontrivial``.
    """
    model = _fixture_model(
        "signature-soundness/positive-03-witnessed-polling-loop-full-contract.yaml"
    )
    assert model.has_self_loop("poll_status")
    assert "poll_status" not in model.descendants("poll_status")
    assert model.components.is_nontrivial("poll_status")

    nested = _fixture_model(
        "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml"
    )
    assert "quote_fares" not in nested.descendants("quote_fares")
    assert "validate_quote" in nested.descendants("quote_fares")


def test_reachability_is_memoized_per_source() -> None:
    model = _fixture_model("graph-well-formed/positive-01-linear-document-pipeline.yaml")
    assert model.descendants(START_VERTEX) is model.descendants(START_VERTEX)


# ── Anchor cycles (catalog §6.4 / §2.4 `cycle_through`) ──────────────────────────────────


def test_a_self_loop_anchors_to_itself() -> None:
    model = _fixture_model(
        "signature-soundness/positive-03-witnessed-polling-loop-full-contract.yaml"
    )
    assert model.anchor_cycle("poll_status") == ("poll_status",)


def test_the_anchors_of_the_nested_scc_are_its_two_simple_cycles() -> None:
    """``positive-04``'s own capped census lists exactly two simple cycles; the anchors
    through the inner and the outer loop are those two, canonically rotated (§0.3)."""
    model = _fixture_model("termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml")
    assert model.anchor_cycle("quote_fares") == ("quote_fares", "validate_quote")
    assert model.anchor_cycle("draft_itinerary") == (
        "assess_itinerary",
        "draft_itinerary",
        "quote_fares",
        "validate_quote",
    )


@pytest.mark.parametrize("label,ir", _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_every_anchor_is_a_real_simple_cycle_canonically_rotated(
    label: str, ir: WorkflowIR
) -> None:
    model = build_graph_model(ir)
    for index in sorted(model.components.nontrivial):
        for vertex in model.components.members[index]:
            cycle = model.anchor_cycle(vertex)
            assert vertex in cycle, (label, vertex)
            assert len(set(cycle)) == len(cycle), (label, cycle)
            assert cycle == canonical_rotation(cycle), (label, cycle)
            for tail, head in zip(cycle, cycle[1:] + cycle[:1], strict=True):
                assert model.has_edge(tail, head), (label, tail, head)


def test_the_anchor_is_a_shortest_cycle_through_its_vertex() -> None:
    """§6.4: one multi-source BFS seeded with the successors, first shortest found wins —
    so the inner two-cycle wins over the outer four-cycle for a vertex on both."""
    model = _fixture_model("termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml")
    assert len(model.anchor_cycle("validate_quote")) == 2


def test_the_anchor_seed_order_is_the_id_order() -> None:
    """§6.4 seeds the BFS with ``H.successors(n)`` **in id order**, so among equally short
    cycles the answer is a pure function of the model rather than of authoring order."""
    document = {
        "entry": "hub",
        "finish": "hub",
        "nodes": _nodes("hub", "zeta", "alpha"),
        "edges": [
            {"from": "hub", "kind": "conditional", "path_map": {"z": "zeta", "a": "alpha"}},
            {"from": "zeta", "to": "hub"},
            {"from": "alpha", "to": "hub"},
        ],
    }
    reversed_document = {
        **document,
        "nodes": _nodes("hub", "alpha", "zeta"),
        "edges": [
            {"from": "hub", "kind": "conditional", "path_map": {"a": "alpha", "z": "zeta"}},
            {"from": "alpha", "to": "hub"},
            {"from": "zeta", "to": "hub"},
        ],
    }
    assert _model(document).anchor_cycle("hub") == ("alpha", "hub")
    assert _model(reversed_document).anchor_cycle("hub") == ("alpha", "hub")


def test_an_anchor_is_refused_on_a_vertex_that_lies_on_no_cycle() -> None:
    model = _fixture_model("graph-well-formed/positive-01-linear-document-pipeline.yaml")
    with pytest.raises(ValueError, match="lies on no cycle"):
        model.anchor_cycle("extract_text")


def test_anchors_are_memoized() -> None:
    model = _fixture_model(
        "signature-soundness/positive-03-witnessed-polling-loop-full-contract.yaml"
    )
    assert model.anchor_cycle("poll_status") is model.anchor_cycle("poll_status")


# ── Subgraphs ────────────────────────────────────────────────────────────────────────────


def test_a_subgraph_keeps_only_the_edges_with_both_endpoints_inside() -> None:
    model = _fixture_model("termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml")
    inside = model.subgraph(model.components.members_of("quote_fares"))
    assert inside.vertices == model.components.members_of("quote_fares")
    assert all(
        edge.source in inside.vertex_set and edge.target in inside.vertex_set
        for edge in inside.edges
    )
    assert START_VERTEX not in inside.vertices
    assert inside.components.is_nontrivial("quote_fares")


def test_a_subgraph_cannot_widen_the_vertex_set() -> None:
    model = _fixture_model("graph-well-formed/positive-01-linear-document-pipeline.yaml")
    assert model.subgraph({"extract_text", "not_a_vertex"}).vertices == ("extract_text",)


# ── Value semantics and caching ──────────────────────────────────────────────────────────


def test_two_builds_of_one_ir_are_the_same_value() -> None:
    """The caching strategy rests on this: a model is a value, so building it once per IR
    and handing it to every validator cannot change any validator's answer."""
    fixture = next(
        f
        for f in _CORPUS
        if f.fixture_id == "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml"
    )
    assert fixture.ir is not None
    first = build_graph_model(fixture.ir)
    second = build_graph_model(fixture.ir)
    assert first == second
    assert hash(first) == hash(second)
    assert first.components.members == second.components.members


def test_the_tarjan_pass_runs_once_per_model() -> None:
    model = _fixture_model("termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml")
    assert model.components is model.components
    assert model.condensation is model.condensation


# ── VAL-03's contract on its consumers ───────────────────────────────────────────────────

#: Names this module owns. A validator that defines one of them has forked the machinery,
#: which is exactly what VAL-03 exists to prevent and what VAL-10's acceptance box calls
#: "cited from VAL-03, not redefined".
_MACHINERY_NAMES = frozenset(
    {
        "anchor_cycle",
        "build_graph_model",
        "canonical_rotation",
        "components",
        "condensation",
        "condensation_order",
        "descendants",
        "ledger_sort_key",
        "predecessors",
        "strongly_connected_components",
        "subgraph",
        "successors",
        "tarjan",
        "worklist_order",
    }
)

_VALIDATORS_DIR = Path(build_graph_model.__globals__["__file__"]).parent / "properties"


def _validator_modules() -> list[Path]:
    """Every validator module, at any nesting — a subpackage is not an escape hatch."""
    return sorted(path for path in _VALIDATORS_DIR.rglob("*.py") if path.name != "__init__.py")


def _takes_the_shared_model(tree: ast.Module) -> bool:
    """Whether a module gets its graph from here, in any of the three import spellings.

    Importing ``START_VERTEX`` alone is deliberately not enough: the exemption has to name
    the model itself, or a module could take one constant and hand-roll the rest.
    """
    wanted = {
        "gebra.verify.graph": {"build_graph_model", "GraphModel"},
        "gebra.verify": {"graph"},
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and "gebra.verify.graph" in {
            alias.name for alias in node.names
        }:
            return True
        if isinstance(node, ast.ImportFrom) and wanted.get(node.module or "", set()) & {
            alias.name for alias in node.names
        }:
            return True
    return False


def _machinery_violations(name: str, source: str) -> list[str]:
    """Every way ``source`` forks the shared machinery. Reads and parses; never imports."""
    tree = ast.parse(source, filename=name)
    violations: list[str] = []
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    if {"edges", "path_map"} <= attributes and not _takes_the_shared_model(tree):
        violations.append(
            f"{name} reads both `.edges` and `.path_map` without taking the shared model — "
            "expand labels with build_graph_model()"
        )
    owned: list[tuple[int, str]] = [
        (node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.name in _MACHINERY_NAMES
    ]
    # Module-level bindings only: a *local* `successors = model.successors(v)` is a caller
    # using the machinery, which is the point, not a fork of it.
    owned += [
        (statement.lineno, target.id)
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name) and target.id in _MACHINERY_NAMES
    ]
    violations += [
        f"{name}:{line} defines `{spelling}`, which gebra.verify.graph owns — "
        "import it instead of redefining it"
        for line, spelling in sorted(owned)
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in SENTINEL_VERTICES:
            violations.append(
                f"{name}:{node.lineno} spells {node.value!r} as a literal — "
                "import START_VERTEX/END_VERTEX from gebra.verify.graph"
            )
    return violations


def test_no_validator_redefines_the_shared_graph_machinery() -> None:
    """The mechanical half of "P-02 and P-06 consume this module without redefining it".

    Three rules over every validator module, checked on the syntax tree:

    1. a module that reads both ``.edges`` and ``.path_map`` is doing label expansion, and
       must take the shared model. The pairing is the test rather than either name alone:
       P-02 reads ``path_map`` for a guard's declared label set (T-W-SPEC §4) and a guard
       recognizer reads ``condition`` strings, neither of which is graph construction;
    2. no module may define any name this module owns;
    3. no module may write the reserved sentinel spellings as literals — ``START_VERTEX``
       and ``END_VERTEX`` are importable, and a hand-written ``"__start__"`` is how a
       second sentinel convention starts.

    What it cannot catch is a validator that takes the model and then rebuilds adjacency out
    of it anyway; that residue is what VAL-07's and VAL-10's review boxes are for. This is
    the part that cannot be forgotten between now and then. The guard is checked against a
    forked module below, so it is not passing vacuously while the validators are unwritten.
    """
    violations = [
        violation
        for path in _validator_modules()
        for violation in _machinery_violations(path.name, path.read_text(encoding="utf-8"))
    ]
    assert violations == [], "\n".join(violations)


def test_the_redefinition_guard_fires_on_a_forked_validator() -> None:
    """The guard's own negative control — all three rules, on one fabricated module.

    Parsed as text, never imported: the source below is a string, and
    :func:`_machinery_violations` only ever calls :func:`ast.parse` on it (WA-07).
    """
    forked = (
        "def check(ir):\n"
        "    adjacency = {'__start__': [ir.entry]}\n"
        "    for edge in ir.edges:\n"
        "        for label, target in edge.path_map.items():\n"
        "            adjacency.setdefault(edge.from_, []).append(target)\n"
        "    return adjacency\n"
        "\n"
        "def descendants(adjacency, source):\n"
        "    return set()\n"
    )
    violations = _machinery_violations("forked.py", forked)
    assert len(violations) == 3, violations
    assert any("path_map" in violation for violation in violations)
    assert any("`descendants`" in violation for violation in violations)
    assert any("'__start__'" in violation for violation in violations)


def test_the_redefinition_guard_leaves_a_guard_recognizer_alone() -> None:
    """The rule-1 pairing exists so VAL-06's syntactic recognizer is not swept up: it reads
    declared ``condition`` strings and a router's labels, and constructs no graph."""
    recognizer = (
        "def recognize(edge):\n"
        "    labels = tuple(edge.path_map)\n"
        "    return edge.condition, labels\n"
    )
    assert _machinery_violations("recognizer.py", recognizer) == []


def test_every_graph_step_the_p02_and_p06_pseudocode_name_is_available_here() -> None:
    """A reference consumer: catalog §2.4 Steps 0–1 and §6.4 Phases 0/2, through the public
    API only, on the fixture each pseudocode is written against.

    §6.4 says its Phases 0 and 2 "are steps (1)–(2) of the SCC-condensation procedure in
    TERMINATION-WITNESS-SPEC — **cited, not redefined**", and §2.4's Step 0/Step 1 are those
    same two steps. Everything either one needs before its own property semantics begin is
    exercised below with no graph code outside this module.
    """
    p02 = _fixture_model("termination-witness/negative-03-counter-guard-without-wired-exit.yaml")
    # §2.4 Step 0: the label-expanded multigraph with sentinels wired.
    assert p02.has_edge(START_VERTEX, "fetch_rates")
    assert len([e for e in p02.out_edges("throttle_check") if e.label]) == 2
    # §2.4 Step 1: the component map that feeds the D4 side condition (§4).
    guard_source, guard_target = "evaluate_rates", "fetch_rates"
    assert p02.components.same_component(guard_source, guard_target)

    p06 = _fixture_model("mixed/09-send-fanout-billable-no-idempotency-in-retry.yaml")
    # §6.4 Phase 0: send edges carry their kind, and label-edges their label.
    assert [e.kind for e in p06.out_edges("dispatch_bookings")] == ["send"]
    # §6.4 Phase 2: `in_cycle(n)`, and Phase 4's anchor.
    assert p06.components.is_nontrivial("book_segment")
    assert p06.anchor_cycle("book_segment") == (
        "book_segment",
        "check_bookings",
        "dispatch_bookings",
    )
    assert not p06.components.is_nontrivial("send_summary")


# ── WA-07 ────────────────────────────────────────────────────────────────────────────────


def test_building_models_over_the_corpus_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the pre-analysis path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter builds a model from every fixture IR in the vendored corpus and runs
    every analysis on it, with socket creation and name resolution replaced by
    record-and-raise probes that also announce themselves on stderr, so a swallowed
    exception still fails the run. No execution-substrate or HTTP/LLM-client package may
    enter the closure; ``networkx`` is in that list because this module deliberately does
    not use it (see its docstring), and because ``gebra.verify`` imports the validator
    subpackage, so a graph library pulled in here would land in the envelope's own closure.
    Stdlib module presence is not asserted — VAL-13 traced that to version-dependent stdlib
    internals with no network involved. Residual gap, accepted and named for honesty, the
    same one VAL-13 recorded: code calling the C-level ``_socket.socket`` directly would
    evade the wrapper. Nothing in this closure does, and the substrate-absence assertion
    keeps it that way.
    """
    forbidden = (
        "{'langgraph', 'langchain', 'langchain_core', 'networkx', 'openai', 'anthropic', "
        "'httpx', 'requests', 'aiohttp', 'urllib3'}"
    )
    script = (
        "import socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the VAL-03 path')\n"
        "def _trip_dns(*a, **k):\n"
        "    attempts.append('getaddrinfo'); print('WA07-TRIP', file=sys.stderr)\n"
        "    raise AssertionError('name resolved on the VAL-03 path')\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip_dns\n"
        "from gebra.testing import load_corpus\n"
        "from gebra.verify.graph import build_graph_model\n"
        f"corpus = load_corpus({str(FIXTURES_DIR)!r})\n"
        "seen = 0\n"
        "for fixture in corpus:\n"
        "    for ir in fixture.irs:\n"
        "        model = build_graph_model(ir)\n"
        "        model.worklist_order\n"
        "        model.descendants('__start__')\n"
        "        for index in model.components.nontrivial:\n"
        "            model.anchor_cycle(model.components.members[index][0])\n"
        "        seen += 1\n"
        "assert len(corpus) == 71, len(corpus)\n"
        "assert seen >= len(corpus), seen\n"
        f"print([m for m in sys.modules if m.split('.')[0] in {forbidden}] + attempts)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_module_cites_no_graph_library() -> None:
    """A source-level conformance check on the no-networkx decision — the hermeticity claim
    itself is the fresh-interpreter tripwire above, which no import spelling can evade."""
    source = Path(build_graph_model.__globals__["__file__"]).read_text(encoding="utf-8")
    for graph_library in ("import networkx", "import igraph", "import graph_tool"):
        assert graph_library not in source


def test_the_module_enumerates_no_cycles() -> None:
    """T-W-SPEC §6.4 rejects full enumeration as the default: Johnson's circuit count "can
    grow faster with n than the exponential 2^n". The mandatory path here is Tarjan plus one
    anchor per request, and the capped census of §6.3 is VAL-08's card, not a primitive
    offered here."""
    source = Path(build_graph_model.__globals__["__file__"]).read_text(encoding="utf-8")
    assert "simple_cycles" not in source
    assert "johnson" not in source.lower()


# ── ir 1.1: the `dynamic` kind, declined rather than defaulted (DEC-28) ───────────────────


def test_a_dynamic_edge_is_declined_rather_than_dropped() -> None:
    """DEC-28 clause 1, from the side that would otherwise get it wrong.

    A ``dynamic`` edge contributes no member to $G$ (PROPERTY-CATALOG-SPEC §0.3) **and** its
    source participates for conditions (ii)/(iii) while condition (i) runs under a ruled
    over-approximation. Implementing only the first half — dropping the edge — would make P-01
    report ``node-unreachable-from-start`` for every node the router reaches at runtime, which is
    the false FATAL DEC-28 forbids by name and the same trap DEC-18 rejected edge omission for.

    So this model declines such a document until the semantics land (DEC-28's paired validator
    regression card), and the decline is a ``NotImplementedError`` subclass: anything catching
    broadly — ``verify()`` turns an escaping exception into a §2.4 tool error — then answers "no
    verdict was reached" rather than a verdict.
    """
    ir = load_json(
        WorkflowIR,
        json.dumps(
            {
                "ir_version": "1.1",
                "entry": "plan",
                "finish": [],
                "nodes": [{"id": "plan"}, {"id": "book"}],
                "edges": [{"kind": "dynamic", "from": "plan", "condition": "route_legs"}],
            }
        ),
    )

    with pytest.raises(DynamicEdgeUnsupportedError) as caught:
        build_graph_model(ir)

    assert isinstance(caught.value, NotImplementedError)
    assert "edges[0]" in str(caught.value)
    assert "DEC-28" in str(caught.value)
    assert "paired validator regression card" in str(caught.value)


@pytest.mark.parametrize(("fixture_id", "ir"), _CORPUS_IRS, ids=[name for name, _ in _CORPUS_IRS])
def test_the_guard_leaves_every_corpus_document_untouched(fixture_id: str, ir: WorkflowIR) -> None:
    """The guard is a test on the edge kinds and nothing else, so no 1.0 document changes.

    Quantified over every corpus snapshot rather than a sample, because "the guard changed
    nothing" is the claim that matters most about it, and the corpus is what the golden-green gate
    rests on.
    """
    assert build_graph_model(ir).vertices
