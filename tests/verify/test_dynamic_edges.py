"""The ``dynamic`` edge across the wedge five — DEC-28 clauses 1–3 as built (card VAL-14).

A ``dynamic`` edge (IR-SPEC §2.4, ir 1.1 — ratified DEC-28, 2026-08-09; PD-041) declares a
router whose target set is not statically known. PROPERTY-CATALOG-SPEC §0.3 states one
convention for every graph builder — the edge contributes **no** member to $G$ while its source
participates — and the four topology sections annotate their own Step-0 sites: P-01 §1.4 (the
source is wired for (iii) and never a sink for (ii); condition (i) runs under the ruled
over-approximation and surfaces its cost as the witness's ``dynamic_dependent``), P-02 §2.4 and
P-06 §6.4 (``continue``: no static cycle through it), P-04 §4.4 (no path, and the otherwise-silent
hole named by ``outside_static_coverage``). Every test here is one of those sentences, on a
document built by hand to isolate it.

Three claims frame the file. **No false FATAL**: the map-reduce shape that motivated the ruling —
a router whose only route to a node is dynamic — yields no ``node-unreachable-from-start``. **No
silent misroute**: P-02/P-04/P-06 answer over such a document, a static cycle or an unwritten
read *beside* a ``dynamic`` edge is still found, and a route that closes only through the router
is not a static one. **Nothing else moved**: no condition ID is added, and on every corpus
document — none of which carries the kind, machine-checked in ``tests/ir/test_canonical.py`` —
the shared model records no dynamic source and neither diagnostic member reaches the wire.

WA-07: every document here is built from the IR models by hand and read as data. Nothing is
extracted, no node body exists to run, no model is called and no socket is opened. The one test
that reaches a live builder — ``gebra.extract()`` over the bare-``Send`` router — lives in
``tests/test_dynamic_document_seam.py`` beside its execution ledger.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gebra.extraction.base import ObjectFamily
from gebra.extraction.envelope import ExtractedFrom, ExtractionEnvelope
from gebra.ir import DynamicEdgeUnsupportedError, WorkflowIR, graph_version
from gebra.snapshot import record
from gebra.store import SnapshotStore
from gebra.testing import load_corpus
from gebra.verify import (
    DataflowWitness,
    P04Failure,
    PropertyReport,
    RunReport,
    WellFormednessWitness,
    build_graph_model,
    conditions_for,
    run_property,
    to_data,
    to_json,
    verify,
)
from gebra.verify.graph import START_VERTEX, GraphModel
from gebra.verify.properties.dataflow_completeness import READ_KEY_NEVER_WRITTEN_ON_PATH
from gebra.verify.properties.graph_well_formed import (
    DEAD_END_NODE_NOT_WIRED_TO_END,
    EDGE_TARGET_UNDEFINED,
    NODE_UNREACHABLE_FROM_START,
    ORPHAN_NODE,
)
from gebra.verify.witnesses import TerminationWitness
from tests.conftest import FIXTURES_DIR

# ── Document builders ────────────────────────────────────────────────────────────────────


def envelope_of(ir: WorkflowIR) -> ExtractionEnvelope:
    """What ``gebra.extract()`` would have returned for ``ir`` — built, never extracted."""
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractedFrom(
            source="langgraph:StateGraph",
            family=ObjectFamily.BUILDER,
            extractor_version="0.0.2.dev0",
        ),
    )


def _ir(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    entry: str | list[str] = "plan",
    finish: str | list[str] = "collect",
    state: dict[str, Any] | None = None,
    ir_version: str = "1.1",
) -> WorkflowIR:
    """A document through the JSON-mode ingestion path (IR-SPEC §2.5 note 4)."""
    payload: dict[str, Any] = {
        "ir_version": ir_version,
        "entry": entry,
        "finish": finish,
        "nodes": nodes,
        "edges": edges,
    }
    if state is not None:
        payload["state"] = state
    return WorkflowIR.model_validate_json(json.dumps(payload))


def _dynamic(source: str, condition: str | None = "route") -> dict[str, Any]:
    edge: dict[str, Any] = {"kind": "dynamic", "from": source}
    if condition is not None:
        edge["condition"] = condition
    return edge


def _normal(source: str, target: str) -> dict[str, Any]:
    return {"kind": "normal", "from": source, "to": target}


def _node(node_id: str, **annotations: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": node_id}
    if annotations:
        entry["annotations"] = annotations
    return entry


def map_reduce() -> WorkflowIR:
    """DEC-28's motivating shape: ``plan`` dispatches dynamically; the workers converge.

    ``book_leg`` and ``collect`` are reachable **only** through the router — statically, START
    reaches ``plan`` and nothing else.
    """
    return _ir(
        nodes=[_node("plan"), _node("book_leg"), _node("collect")],
        edges=[_dynamic("plan", "route_legs"), _normal("book_leg", "collect")],
        state={"legs": "list[str]"},
    )


def _witness(report: PropertyReport) -> Any:
    assert report.result == "pass", to_json(report)
    return report.witness


def _conditions(report: PropertyReport) -> list[str]:
    """Every condition ID a failing report carries, primary first."""
    assert report.result == "fail", to_json(report)
    failure = report.failure
    assert failure is not None
    return [failure.property_condition, *(c.property_condition for c in failure.co_failures or ())]


def _report(slug: str, ir: WorkflowIR) -> PropertyReport:
    """One wedge validator's answer through dispatch — a report, never a marker.

    Every slug asked for here is registered, so the marker arm of ``run_property``'s return is
    unreachable; asserting it keeps the type narrow for the helpers above.
    """
    outcome = run_property(slug, ir)  # type: ignore[arg-type]
    assert isinstance(outcome, PropertyReport), outcome
    return outcome


# ── The shared model (§0.3's one convention) ─────────────────────────────────────────────


def test_a_dynamic_edge_inserts_no_member_and_records_its_source() -> None:
    model = build_graph_model(map_reduce())

    assert model.dynamic_sources == frozenset({"plan"})
    assert [(e.source, e.target, e.origin, e.index) for e in model.edges] == [
        ("__start__", "plan", "entry", 0),
        ("collect", "__end__", "finish", 0),
        # The authored `ir.edges` index survives the skipped member: edges[1], not edges[0].
        ("book_leg", "collect", "edges", 1),
    ]
    assert model.out_edges("plan") == ()
    assert model.successors("plan") == ()


def test_the_expanded_edge_index_is_the_authored_position_after_a_dynamic_edge() -> None:
    """P-02's multigraph key is ``(ir.edges index, label)`` (§2.4 Step 0); the skip must not
    renumber the guards that follow it."""
    ir = _ir(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[
            _dynamic("c"),
            _normal("a", "b"),
            {
                "kind": "conditional",
                "from": "b",
                "condition": "n < 3",
                "path_map": {"again": "a", "done": "c"},
            },
        ],
        entry="a",
        finish=[],
        state={"n": "int"},
    )
    model = build_graph_model(ir)
    by_index = {(e.index, e.label) for e in model.edges if e.origin == "edges"}
    assert by_index == {(1, None), (2, "again"), (2, "done")}


def test_an_unresolved_dispatcher_is_a_reference_finding_not_a_participant() -> None:
    """§1.4 Step 1 checks ``e.from ∈ V`` before its ``dynamic`` branch: the source is recorded as
    an unresolved ``edge-source`` reference with the authored kind, and nothing joins the set."""
    ir = _ir(nodes=[_node("a")], edges=[_dynamic("ghost")], entry="a", finish="a")

    dropped = build_graph_model(ir, carry_unresolved_references=False)
    assert dropped.dynamic_sources == frozenset()
    assert [(r.role, r.reference, r.kind, r.index) for r in dropped.unresolved] == [
        ("edge-source", "ghost", "dynamic", 0)
    ]
    assert "ghost" not in dropped.vertex_set

    # Under P-02/P-04's convention the phantom is a vertex of the model, and joins the set the
    # way every other carried vertex joins V*; the record is identical either way.
    carried = build_graph_model(ir, carry_unresolved_references=True)
    assert carried.carried == frozenset({"ghost"})
    assert carried.dynamic_sources == frozenset({"ghost"})
    assert carried.unresolved == dropped.unresolved
    # A phantom nobody wires to is not reachable, so it triggers nothing.
    assert carried.reachable_dynamic_sources() == frozenset()


def test_reachability_of_the_dispatcher_is_the_one_shared_trigger() -> None:
    reachable = build_graph_model(map_reduce())
    assert reachable.reachable_dynamic_sources() == frozenset({"plan"})

    island = _ir(
        nodes=[_node("a"), _node("plan")],
        edges=[_dynamic("plan")],
        entry="a",
        finish="a",
    )
    unreachable = build_graph_model(island)
    assert unreachable.dynamic_sources == frozenset({"plan"})
    assert unreachable.reachable_dynamic_sources() == frozenset()


def test_a_subgraph_keeps_the_dynamic_sources_it_keeps() -> None:
    model = build_graph_model(map_reduce())
    assert model.subgraph({"plan", START_VERTEX}).dynamic_sources == frozenset({"plan"})
    assert model.subgraph({"book_leg", "collect"}).dynamic_sources == frozenset()


def test_the_model_is_a_pure_function_of_the_document() -> None:
    assert build_graph_model(map_reduce()) == build_graph_model(map_reduce())


# ── P-01: no false FATAL; (ii)/(iii) participation; the over-approximation ───────────────


def test_the_map_reduce_document_yields_no_node_unreachable_from_start() -> None:
    """DEC-28 clause 1, the false FATAL proven absent (acceptance box 2)."""
    report = _report("graph-well-formed", map_reduce())

    witness = _witness(report)
    assert isinstance(witness, WellFormednessWitness)
    # The nodes only the router reaches are surfaced, not flagged.
    assert witness.dynamic_dependent == ("book_leg", "collect")
    # §1.4 Step 5 as written: `sorted(V)` — every node is possibly reachable, and the ones that
    # depend on the dispatch for it are named beside the list rather than left to inference.
    assert witness.reachable_from_start == ("book_leg", "collect", "plan")
    assert witness.terminal_nodes == ("collect",)
    assert witness.orphan_nodes == () and witness.unresolved_targets == ()


def test_the_dispatcher_is_wired_for_iii_and_never_a_dead_end_for_ii() -> None:
    """Two dispatchers: ``a`` wired from START, ``plan`` with no static edge and no sentinel
    membership at all. Under edge omission ``plan`` would be an orphan **and** a dead end and
    ``a`` a dead end; under the convention each participates through its dynamic edge."""
    ir = _ir(
        nodes=[_node("a"), _node("plan")],
        edges=[_dynamic("a"), _dynamic("plan")],
        entry="a",
        finish=[],
    )

    report = _report("graph-well-formed", ir)

    witness = _witness(report)
    assert isinstance(witness, WellFormednessWitness)
    assert witness.dynamic_dependent == ("plan",)
    assert witness.terminal_nodes == ()  # a dispatcher has a runtime out-route, not an END edge


def test_without_its_dynamic_edge_the_same_node_is_an_orphan_and_a_dead_end() -> None:
    """The control for the test above: drop ``plan``'s edge and both conditions fire — so the
    participation is the edge's doing, not an accident of the document."""
    ir = _ir(
        nodes=[_node("a"), _node("plan")],
        edges=[_dynamic("a")],
        entry="a",
        finish=[],
    )

    report = _report("graph-well-formed", ir)

    # (i) stays silenced by the reachable dispatcher `a`; (iii) and (ii) fire for `plan` in
    # the root-cause order (iv)→(iii)→(i)→(ii).
    assert _conditions(report) == [ORPHAN_NODE, DEAD_END_NODE_NOT_WIRED_TO_END]


def test_a_static_sink_beside_a_dynamic_edge_is_still_a_dead_end() -> None:
    """No silent misroute: the exemption is for the dispatcher, not for the document."""
    ir = _ir(
        nodes=[_node("a"), _node("b")],
        edges=[_dynamic("a"), _normal("a", "b")],
        entry="a",
        finish=[],
    )

    report = _report("graph-well-formed", ir)

    assert _conditions(report) == [DEAD_END_NODE_NOT_WIRED_TO_END]
    failure = report.failure
    assert failure is not None and to_data(failure.location) == {"kind": "node", "node": "b"}


def test_an_unreachable_dispatcher_triggers_nothing_and_condition_i_runs_as_written() -> None:
    """DEC-28 clause 1 is conditioned on the source being *reachable*: a dispatcher no static
    path reaches can never run, so static unreachability stays a DEFENSIBLE claim."""
    ir = _ir(
        nodes=[_node("a"), _node("plan")],
        edges=[_dynamic("plan")],
        entry="a",
        finish="a",
    )

    report = _report("graph-well-formed", ir)

    # `plan` participates for (iii) and (ii) through its edge, so (i) is the whole finding.
    assert _conditions(report) == [NODE_UNREACHABLE_FROM_START]
    failure = report.failure
    assert failure is not None and to_data(failure.location) == {"kind": "node", "node": "plan"}


def test_a_genuinely_disconnected_island_is_surfaced_as_the_priced_coverage_cost() -> None:
    """The cost DEC-28 names and accepts: on a dynamic-bearing document an island is not
    flagged by (i) — it appears in ``dynamic_dependent`` instead, never silently."""
    ir = _ir(
        nodes=[
            _node("plan"),
            _node("book_leg"),
            _node("collect"),
            _node("audit"),
            _node("archive"),
        ],
        edges=[_dynamic("plan"), _normal("book_leg", "collect"), _normal("audit", "archive")],
        finish=["collect", "archive"],
    )

    witness = _witness(_report("graph-well-formed", ir))

    assert isinstance(witness, WellFormednessWitness)
    assert witness.dynamic_dependent == ("archive", "audit", "book_leg", "collect")


def test_an_unresolved_dispatcher_is_edge_target_undefined_and_no_over_approximation() -> None:
    ir = _ir(nodes=[_node("a")], edges=[_dynamic("ghost")], entry="a", finish="a")

    report = _report("graph-well-formed", ir)

    assert _conditions(report) == [EDGE_TARGET_UNDEFINED]
    failure = report.failure
    assert failure is not None
    assert to_data(failure.location) == {
        "kind": "edge",
        "source": "ghost",
        "undefined_target": "ghost",
    }


def test_the_diagnostic_is_absent_when_every_node_is_statically_reachable() -> None:
    """Emitted only when non-empty (DEC-11 discipline): a dynamic edge whose every node is also
    statically wired carries no member, and the witness serializes in the five-key form."""
    ir = _ir(
        nodes=[_node("plan"), _node("collect")],
        edges=[_dynamic("plan"), _normal("plan", "collect")],
    )

    report = _report("graph-well-formed", ir)

    witness = _witness(report)
    assert isinstance(witness, WellFormednessWitness)
    assert witness.dynamic_dependent is None
    assert "dynamic_dependent" not in to_json(report)


# ── P-04: no path through the router; the otherwise-silent hole is named ─────────────────


def test_readers_only_the_router_reaches_are_named_outside_static_coverage() -> None:
    """DEC-28 clause 2 (acceptance box 3): nodes with declared reads, not statically reachable,
    on a document with a reachable ``dynamic`` edge. ``notify`` declares no read and is not
    named; ``plan`` is reachable and is not named."""
    ir = _ir(
        nodes=[
            _node("plan"),
            _node("book_leg", input=["legs"], output=["bookings"]),
            _node("collect", input=["bookings"]),
            _node("notify"),
        ],
        edges=[
            _dynamic("plan", "route_legs"),
            _normal("book_leg", "collect"),
            _normal("collect", "notify"),
        ],
        finish="notify",
        state={"legs": "list[str]", "bookings": "list[str]"},
    )

    report = _report("dataflow-completeness", ir)

    witness = _witness(report)
    assert isinstance(witness, DataflowWitness)
    # No obligation for a dynamic-dependent reader (D2 scope over the static graph) …
    assert witness.coverage == ()
    # … and the absence of coverage is not silent.
    assert witness.outside_static_coverage == ("book_leg", "collect")


def test_the_diagnostic_rides_the_primary_failure_on_the_fail_path() -> None:
    """The one carrier a failing report has: ``plan`` reads an unwritten key and fails; the
    dynamic-dependent reader ``book_leg`` is named on that primary, beside DEC-11's two."""
    ir = _ir(
        nodes=[_node("plan", input=["legs"]), _node("book_leg", input=["legs"]), _node("collect")],
        edges=[_dynamic("plan"), _normal("book_leg", "collect")],
        state={"legs": "list[str]"},
    )

    report = _report("dataflow-completeness", ir)

    assert _conditions(report) == [READ_KEY_NEVER_WRITTEN_ON_PATH]
    failure = report.failure
    assert isinstance(failure, P04Failure)
    assert failure.location.node == "plan" and failure.location.key == "legs"
    assert failure.outside_static_coverage == ("book_leg",)
    assert failure.writers_on_other_paths is None and failure.downstream_writers is None


def test_a_read_outside_sigma_is_still_a_declared_read_for_the_diagnostic() -> None:
    """Σ-membership is P-03's finding (§4.4 Step 4); it is still a read nothing here covers."""
    ir = _ir(
        nodes=[_node("plan"), _node("book_leg", input=["undeclared"]), _node("collect")],
        edges=[_dynamic("plan"), _normal("book_leg", "collect")],
        state={"legs": "list[str]"},
    )

    witness = _witness(_report("dataflow-completeness", ir))

    assert isinstance(witness, DataflowWitness)
    assert witness.outside_static_coverage == ("book_leg",)


def test_no_reachable_dispatcher_means_no_diagnostic_and_d2_scope_alone() -> None:
    """With the dispatcher itself unreachable, the unreachable reader is P-01's finding alone
    (DEC-05 D2) and P-04 adds nothing — the diagnostic is conditioned on a *reachable* edge."""
    ir = _ir(
        nodes=[_node("a"), _node("plan", input=["legs"])],
        edges=[_dynamic("plan")],
        entry="a",
        finish="a",
        state={"legs": "list[str]"},
    )

    report = _report("dataflow-completeness", ir)

    witness = _witness(report)
    assert isinstance(witness, DataflowWitness)
    assert witness.coverage == ()
    assert witness.outside_static_coverage is None
    assert "outside_static_coverage" not in to_json(report)


def test_a_reachable_reader_beside_a_dynamic_edge_is_still_checked() -> None:
    """No silent misroute on the P-04 side: an unwritten read on a static START-path fails as it
    always did, whatever the router beside it may dispatch."""
    ir = _ir(
        nodes=[_node("plan"), _node("check", input=["legs"])],
        edges=[_dynamic("plan"), _normal("plan", "check")],
        finish="check",
        state={"legs": "list[str]"},
    )

    report = _report("dataflow-completeness", ir)

    assert _conditions(report) == [READ_KEY_NEVER_WRITTEN_ON_PATH]
    failure = report.failure
    assert isinstance(failure, P04Failure)
    assert failure.location.path == ("START", "plan", "check")
    assert failure.outside_static_coverage is None


# ── P-02: a dynamic edge forms no static cycle ───────────────────────────────────────────


def test_a_route_closed_only_through_the_router_is_not_a_static_cycle() -> None:
    """§2.4 Step 0: "a dynamic edge forms no static cycle" — no witness is owed for it."""
    ir = _ir(
        nodes=[_node("a"), _node("b")],
        edges=[_normal("a", "b"), _dynamic("b", "back_to_a")],
        entry="a",
        finish=[],
    )

    report = _report("termination-witness", ir)

    witness = _witness(report)
    assert isinstance(witness, TerminationWitness)
    assert witness.inventory == ()
    assert witness.notes == ()
    assert witness.cycles is not None and witness.cycles.cycles == ()
    assert set(witness.certificate) == {"START", "a", "b", "END"}


def test_a_static_cycle_beside_a_dynamic_edge_still_needs_its_witness() -> None:
    ir = _ir(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[
            _dynamic("c"),
            _normal("a", "b"),
            {
                "kind": "conditional",
                "from": "b",
                "condition": "keep_going",
                "path_map": {"again": "a", "done": "c"},
            },
        ],
        entry="a",
        finish=[],
    )

    report = _report("termination-witness", ir)

    assert _conditions(report) == ["cycle-without-termination-witness"]
    failure = report.failure
    assert failure is not None and to_data(failure.location)["nodes"] == ["a", "b"]


def test_a_counter_guard_authored_after_a_dynamic_edge_is_found_at_its_authored_index() -> None:
    """The form-(a) scan and the multigraph key both use the authored ``ir.edges`` index; a
    skipped member must not shift the guard the witness discharges."""
    ir = _ir(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[
            _dynamic("c"),
            _normal("a", "b"),
            {
                "kind": "conditional",
                "from": "b",
                "condition": "'again' if retries < 3 else 'done'",
                "path_map": {"again": "a", "done": "c"},
            },
        ],
        entry="a",
        finish=[],
        state={"retries": "int"},
    )

    witness = _witness(_report("termination-witness", ir))

    assert isinstance(witness, TerminationWitness)
    assert [entry.form for entry in witness.inventory] == ["a"]
    source = witness.inventory[0].source
    assert to_data(source)["guard_edge"] == {"source": "b", "label": "again"}
    assert to_data(source)["counter_key"] == "retries"


# ── P-06: no member means no cycle membership and no re-entry ────────────────────────────


def test_a_trigger_node_whose_only_loop_back_is_dynamic_sits_in_an_acyclic_region() -> None:
    ir = _ir(
        nodes=[_node("a"), _node("charge", effect=["billable"])],
        edges=[_normal("a", "charge"), _dynamic("charge", "maybe_retry")],
        entry="a",
        finish=[],
    )

    report = _report("effect-safety", ir)

    witness = _witness(report)
    data = to_data(witness)
    assert data["cycles"] == []
    assert data["effects"] == [
        {
            "node": "charge",
            "effect": ["billable"],
            "region": "acyclic",
            "protection": "none_required",
        }
    ]


def test_an_unprotected_effect_in_a_static_retry_region_beside_a_dynamic_edge_is_flagged() -> None:
    """§6.4 Phase 3's structural re-entry — ``check`` routes back to ``charge`` on a conditional
    label — is untouched by the dynamic router hanging off ``a``: the region is still ``retry``
    and the unprotected billable node is still flagged."""
    ir = _ir(
        nodes=[_node("a"), _node("charge", effect=["billable"]), _node("check"), _node("d")],
        edges=[
            _normal("a", "charge"),
            _normal("charge", "check"),
            {
                "kind": "conditional",
                "from": "check",
                "condition": "ok",
                "path_map": {"retry": "charge", "done": "END"},
            },
            _normal("a", "d"),
            _dynamic("d"),
        ],
        entry="a",
        finish=[],
    )

    report = _report("effect-safety", ir)

    assert _conditions(report) == ["unprotected-effect-in-retry-region"]
    failure = report.failure
    assert failure is not None and to_data(failure.location)["node"] == "charge"


# ── P-08, and the whole run ──────────────────────────────────────────────────────────────


def test_every_wedge_validator_answers_over_the_map_reduce_document() -> None:
    """Acceptance box 3's "no crash": all five answer, through dispatch, with a real report."""
    for slug in (
        "graph-well-formed",
        "termination-witness",
        "dataflow-completeness",
        "effect-safety",
        "determinism-replay",
    ):
        report = _report(slug, map_reduce())
        assert report.property == slug
        assert report.result == "pass", to_json(report)


def test_verify_reaches_a_verdict_and_the_report_round_trips() -> None:
    """Acceptance box 1: no ``ir-validation`` refusal, thirteen outcomes, the stamp reported."""
    document = map_reduce()

    report = verify(document)

    assert report.error is None
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")
    assert report.subject is not None
    assert report.subject.ir_version == "1.1"
    assert report.subject.graph_version == graph_version(document)
    assert report.report_format == "1.2"
    assert len(report.properties) == 13 and report.best_effort == ()
    assert RunReport.model_validate_json(to_json(report)) == report
    witness = report.outcome_for("graph-well-formed")
    assert isinstance(witness, PropertyReport) and isinstance(
        witness.witness, WellFormednessWitness
    )
    assert witness.witness.dynamic_dependent == ("book_leg", "collect")


def test_a_dynamic_dependent_reader_reaches_the_run_report_as_a_diagnostic_not_a_finding() -> None:
    ir = _ir(
        nodes=[_node("plan"), _node("book_leg", input=["legs"]), _node("collect")],
        edges=[_dynamic("plan"), _normal("book_leg", "collect")],
        state={"legs": "list[str]"},
    )

    report = verify(ir)

    assert report.gate.exit_code == 0
    assert report.gate.counts.blocking == 0
    dataflow = report.outcome_for("dataflow-completeness")
    assert isinstance(dataflow, PropertyReport)
    assert isinstance(dataflow.witness, DataflowWitness)
    assert dataflow.witness.outside_static_coverage == ("book_leg",)


# ── The two predicates say the same thing (SD-12's disclosed divergence) ─────────────────


def test_verify_and_the_store_both_key_on_the_construct_not_the_stamp(tmp_path: Path) -> None:
    """SD-12 disclosed that ``verify()`` keyed on the declared stamp while the store keyed on the
    construct. Neither keys on the stamp now: a hand-authored ``"1.1"`` with no ``dynamic`` edge
    is verified and recorded alike, and a mis-stamped ``"1.0"`` carrying one is verified under
    the dynamic semantics and declined by the store — on the construct, in both.

    The second half pins an **interim** reading, not a settled one. IR-SPEC §2.4 ties kind
    ``dynamic`` to ``ir_version`` ≥ 1.1 but names no enforcement site, so such a document loads
    and is reported at its own stamp; whether ``WorkflowIR`` should refuse it is a
    validation-requiredness change on the frozen IR surface and takes IR-MODELS-FREEZE §4's DEC
    route — filed as PD-055 at VAL-14's ir-contract pre-review. When that ruling lands, the
    ``mis_stamped`` half of this test is the one that moves."""
    stamped_only = _ir(
        nodes=[_node("plan"), _node("collect")],
        edges=[_normal("plan", "collect")],
        ir_version="1.1",
    )
    report = verify(stamped_only)
    assert report.error is None and report.subject is not None
    assert report.subject.ir_version == "1.1"
    outcome = record(
        envelope_of(stamped_only), store=SnapshotStore.for_project(tmp_path), source="probe"
    )
    assert outcome.recorded

    mis_stamped = _ir(
        nodes=[_node("plan"), _node("book_leg"), _node("collect")],
        edges=[_dynamic("plan"), _normal("book_leg", "collect")],
        ir_version="1.0",
    )
    verified = verify(mis_stamped)
    assert verified.error is None and verified.subject is not None
    assert verified.subject.ir_version == "1.0"  # reported verbatim, never re-derived
    p01 = verified.outcome_for("graph-well-formed")
    assert isinstance(p01, PropertyReport) and isinstance(p01.witness, WellFormednessWitness)
    assert p01.witness.dynamic_dependent == ("book_leg", "collect")

    with pytest.raises(DynamicEdgeUnsupportedError):
        record(
            envelope_of(mis_stamped), store=SnapshotStore.for_project(tmp_path / "b"), source="x"
        )


# ── Nothing else moved ───────────────────────────────────────────────────────────────────


def test_no_condition_id_was_added() -> None:
    """Acceptance box 4: the two additions are optional diagnostics, not conditions."""
    assert [entry.id for entry in conditions_for("graph-well-formed")] == [
        "node-unreachable-from-start",
        "dead-end-node-not-wired-to-end",
        "path-map-target-undefined",
        "orphan-node",
        "edge-target-undefined",
    ]
    assert [entry.id for entry in conditions_for("dataflow-completeness")] == [
        "read-key-never-written-on-path"
    ]


_CORPUS_IRS: list[tuple[str, WorkflowIR]] = [
    (f"{fixture.fixture_id}#{index}", ir)
    for fixture in load_corpus(FIXTURES_DIR)
    for index, ir in enumerate(fixture.irs)
]


@pytest.mark.parametrize(("label", "ir"), _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_neither_diagnostic_reaches_the_wire_on_any_corpus_document(
    label: str, ir: WorkflowIR
) -> None:
    """The corpus carries no ``dynamic`` edge (``tests/ir/test_canonical.py`` machine-checks it),
    so the shared model records no source and neither optional member is emitted — every
    corpus verdict serializes byte-for-byte as it did before the slots existed."""
    model: GraphModel = build_graph_model(ir)
    assert model.dynamic_sources == frozenset()
    for slug in ("graph-well-formed", "dataflow-completeness"):
        text = to_json(_report(slug, ir))
        assert "dynamic_dependent" not in text and "outside_static_coverage" not in text, label
