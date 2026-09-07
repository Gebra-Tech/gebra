"""H3 containment across P-01 and P-04 — DEC-33 as built (card VAL-15).

PROPERTY-CATALOG-SPEC §0.3's containment convention (ratified — DEC-33, 2026-09-06; PD-058 +
PD-056): a node whose id has a proper path prefix, segment-wise over IR-SPEC §5.1's split-safe
``/``, that is itself a member of $V$ is **contained** — a constituent of its containment root,
not a vertex of the enclosing control flow. P-01's node-quantified conditions (i)–(iii) quantify
over the top-level projection $V_{top}$; condition (iv), $V$, $G^*$ and Step 1 stay whole; the
pass witness's three node lists partition $V$ (``reachable_from_start`` ⊎ ``dynamic_dependent`` ⊎
``contained_nodes``); and P-04 names a contained reader outside its static ``Reach`` on
``contained_readers`` while ``outside_static_coverage`` narrows to $V_{top}$ (DEC-33 §3.4).

Every test here is one of DEC-33 §5's measurements, taken again on the landed code: the two
LCEL conformance goldens reach a verdict (rows 1–2, 10); the mount shape yields nothing while a
node-set projection — what the implementation must **not** do — would yield a condition-(iv)
finding (row 6); the orphan-root document yields its root's three findings and never the twelve
participation would (row 4); the two anti-evasion probes pass with the descendants named (row
7); condition (iv) still anchors at a contained source (row 17); the corpus is flat and the
``negative-04`` control is unmoved (rows 5, 8); and P-04's silent hole and double listing are
closed (rows 13–14).

WA-07: every document here is a committed golden read as data, a hand-built ``WorkflowIR``
through the JSON-mode ingestion path, or a vendored property-fixture document loaded through
``gebra.testing``'s YAML loaders (``load_corpus`` for the partition sweep, ``load_fixture`` for the
``negative-04`` control). Nothing is extracted, no node body exists to run, no model is called and
no socket is opened.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gebra.ir import WorkflowIR
from gebra.report.evidence import witness_lines, witness_summary
from gebra.testing import load_corpus, load_fixture
from gebra.verify import (
    DataflowWitness,
    P04Failure,
    PropertyReport,
    RunReport,
    WellFormednessWitness,
    build_graph_model,
    conditions_for,
    models_equivalent,
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
from tests.conftest import FIXTURES_DIR

#: The committed extractor-conformance goldens (WA-05 surface, read-only here): the canonical
#: serialization of two LCEL fragments with a nested frame — the class that failed P-01 as
#: written (27 and 3 FATALs; PD-058) and reaches a verdict under the convention.
CONFORMANCE: Path = Path(__file__).resolve().parents[1] / "extraction" / "golden" / "conformance"

#: The nine contained ids of ``lcel-composite`` and the one of ``lcel-tool-bound``, in ledger
#: §6 order — DEC-33 §1's "12 nodes, 9 contained" and "3 nodes, 1 contained".
LCEL_GOLDENS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "lcel-composite": (
        ("%seq[0]", "%seq[1]", "%seq[2]"),
        (
            "%seq[1]/%map[digest]",
            "%seq[1]/%map[digest]/%lambda[0]",
            "%seq[1]/%map[prose]",
            "%seq[1]/%map[prose]/%branch[0]",
            "%seq[1]/%map[prose]/%branch[1]",
            "%seq[1]/%map[tagged]",
            "%seq[1]/%map[tagged]/%bind[0]",
            "%seq[1]/%map[verbatim]",
            "%seq[2]/%retry[0]",
        ),
    ),
    "lcel-tool-bound": (("%seq[0]", "%seq[1]"), ("%seq[1]/%bind[0]",)),
}


# ── Document builders ────────────────────────────────────────────────────────────────────


def _ir(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    entry: str | list[str],
    finish: str | list[str],
    state: dict[str, Any] | None = None,
    ir_version: str = "1.0",
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


def _node(node_id: str, **annotations: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": node_id}
    if annotations:
        entry["annotations"] = annotations
    return entry


def _edge(source: str, target: str) -> dict[str, Any]:
    return {"kind": "normal", "from": source, "to": target}


def _dynamic(source: str) -> dict[str, Any]:
    return {"kind": "dynamic", "from": source, "condition": "route"}


def _golden(name: str) -> WorkflowIR:
    """One conformance golden, read as data — never re-extracted here."""
    text = (CONFORMANCE / f"{name}.canonical.json").read_text(encoding="utf-8")
    return WorkflowIR.model_validate_json(text)


def _report(slug: str, ir: WorkflowIR) -> PropertyReport:
    outcome = run_property(slug, ir)  # type: ignore[arg-type]
    assert isinstance(outcome, PropertyReport), outcome
    return outcome


def _p01(ir: WorkflowIR) -> PropertyReport:
    return _report("graph-well-formed", ir)


def _p04(ir: WorkflowIR) -> PropertyReport:
    return _report("dataflow-completeness", ir)


def _witness(report: PropertyReport) -> WellFormednessWitness:
    assert report.result == "pass", to_json(report)
    assert isinstance(report.witness, WellFormednessWitness)
    return report.witness


def _dataflow(report: PropertyReport) -> DataflowWitness:
    assert report.result == "pass", to_json(report)
    assert isinstance(report.witness, DataflowWitness)
    return report.witness


def _findings(report: PropertyReport) -> list[tuple[str, dict[str, Any]]]:
    """Every record as ``(condition id, location data)``, primary first."""
    assert report.result == "fail", to_json(report)
    failure = report.failure
    assert failure is not None
    return [
        (failure.property_condition, to_data(failure.location)),
        *((c.property_condition, to_data(c.location)) for c in failure.co_failures or ()),
    ]


def _assert_partition(witness: WellFormednessWitness, ir: WorkflowIR) -> None:
    """§1.3's invariant on every pass: the three node lists are pairwise disjoint and cover V."""
    reachable = set(witness.reachable_from_start)
    dynamic = set(witness.dynamic_dependent or ())
    contained = set(witness.contained_nodes or ())
    assert not (reachable & dynamic) and not (reachable & contained) and not (dynamic & contained)
    assert reachable | dynamic | contained == {node.id for node in ir.nodes}
    # Each optional member is present iff non-empty (DEC-11 optional-diagnostic discipline).
    assert witness.dynamic_dependent != () and witness.contained_nodes != ()


# ── The shared model: the split, once, for every graph builder ───────────────────────────


def test_a_node_is_contained_iff_a_proper_segment_prefix_is_itself_declared() -> None:
    """§0.3's predicate is membership of the *prefix*, never the presence of a ``/``: ``x/y``
    without ``x`` is top-level, an escaped ``%2F`` never splits, and nesting is transitive."""
    ir = _ir(
        nodes=[_node("a"), _node("a/b"), _node("a/b/c"), _node("x/y"), _node("p%2Fq")],
        edges=[_edge("a", "x/y"), _edge("x/y", "p%2Fq")],
        entry="a",
        finish="p%2Fq",
    )
    model = build_graph_model(ir)

    assert model.contained_nodes == frozenset({"a/b", "a/b/c"})
    assert model.top_level_nodes == frozenset({"a", "x/y", "p%2Fq"})
    assert model.top_level_nodes | model.contained_nodes == model.node_ids


def test_the_containment_root_is_the_shortest_declared_prefix_and_is_unique() -> None:
    """§0.3: prefixes-in-V are linearly ordered by length, so the shortest is the only root."""
    ir = _ir(
        nodes=[_node("a"), _node("a/b"), _node("a/b/c"), _node("m/n"), _node("m/n/o")],
        edges=[_edge("a", "m/n")],
        entry="a",
        finish="m/n",
    )
    model = build_graph_model(ir)

    assert model.containment_root("a/b/c") == "a"  # not the nearer `a/b`
    assert model.containment_root("a/b") == "a"
    assert model.containment_root("a") == "a"  # a top-level node is its own root
    assert model.containment_root("m/n/o") == "m/n"  # `m` is not declared, so `m/n` is the root
    with pytest.raises(KeyError):
        model.containment_root("ghost")


def test_the_convention_narrows_the_quantification_and_leaves_the_graph_whole() -> None:
    """§0.3: "G is unchanged and is still built over the whole of V" — a contained node's own
    edge, and its ``entry``/``finish`` membership, enter G* exactly as before."""
    ir = _ir(
        nodes=[_node("plan"), _node("n"), _node("n/%seq[0]"), _node("n/%seq[1]")],
        edges=[_edge("plan", "n"), _edge("n/%seq[0]", "n/%seq[1]")],
        entry="plan",
        finish=["n", "n/%seq[1]"],
    )
    model = build_graph_model(ir)

    assert model.contained_nodes == frozenset({"n/%seq[0]", "n/%seq[1]"})
    assert {"n/%seq[0]", "n/%seq[1]"} <= model.vertex_set
    assert [(e.source, e.target) for e in model.edges if e.origin == "edges"] == [
        ("plan", "n"),
        ("n/%seq[0]", "n/%seq[1]"),
    ]
    assert model.has_edge("n/%seq[1]", "__end__")  # the contained finish id is wired to END


def test_the_model_is_a_pure_function_of_the_document_containment_included() -> None:
    ir = _ir(nodes=[_node("a"), _node("a/x")], edges=[], entry="a", finish="a")
    assert build_graph_model(ir) == build_graph_model(ir)
    assert build_graph_model(ir).contained_nodes == build_graph_model(ir).contained_nodes


# ── P-01: the two LCEL conformance documents reach a verdict (acceptance box 1) ───────────


@pytest.mark.parametrize("name", sorted(LCEL_GOLDENS))
def test_the_lcel_golden_passes_p01_and_the_run_gate(name: str) -> None:
    """DEC-33 §5 rows 1–2 and 10, on the landed code: P-01 ``pass``, ``verify()`` exit 0 with an
    empty ``best_effort`` — where the same documents failed with ``fatal=27`` and ``fatal=3``,
    primary ``orphan-node``, as written."""
    ir = _golden(name)
    top_level, contained = LCEL_GOLDENS[name]

    p01 = _p01(ir)
    witness = _witness(p01)
    assert witness.reachable_from_start == top_level
    assert witness.contained_nodes == contained
    assert witness.dynamic_dependent is None
    assert witness.orphan_nodes == () and witness.unresolved_targets == ()
    _assert_partition(witness, ir)

    report = verify(ir)
    assert report.error is None
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")
    assert report.best_effort == ()
    assert report.gate.counts.fatal == 0
    assert report.report_format == "1.3"
    assert len(report.properties) == 13
    assert RunReport.model_validate_json(to_json(report)) == report


@pytest.mark.parametrize("name", sorted(LCEL_GOLDENS))
def test_every_wedge_validator_passes_the_lcel_golden_contract_bearing(name: str) -> None:
    """§0.3: with P-01 clean, P-02/P-04/P-06's verdicts on a nested fragment become
    contract-bearing for the first time — and each of the five is a pass here."""
    ir = _golden(name)
    for slug in (
        "graph-well-formed",
        "termination-witness",
        "dataflow-completeness",
        "effect-safety",
        "determinism-replay",
    ):
        report = _report(slug, ir)
        assert report.result == "pass", (slug, to_json(report))


def test_the_lcel_goldens_are_read_as_data_and_carry_no_dynamic_edge() -> None:
    """The nested-fragment class is H3 containment alone: no ``dynamic`` edge, so
    ``dynamic_dependent`` never enters the partition on these two documents."""
    for name in LCEL_GOLDENS:
        model = build_graph_model(_golden(name))
        assert model.dynamic_sources == frozenset()
        assert model.contained_nodes == frozenset(LCEL_GOLDENS[name][1])


# ── P-01: the probes DEC-33 §5 measured, re-run on the landed code ────────────────────────


def _mount_shape() -> WorkflowIR:
    """The §5 rule-4 mounted shape hand-authored per PD-025 D4: ``plan → n``, ``finish: n``,
    and the one interior edge a ``seq`` frame emits, ``n/%seq[0] → n/%seq[1]``."""
    return _ir(
        nodes=[_node("plan"), _node("n"), _node("n/%seq[0]"), _node("n/%seq[1]")],
        edges=[_edge("plan", "n"), _edge("n/%seq[0]", "n/%seq[1]")],
        entry="plan",
        finish="n",
    )


def test_the_mount_shape_yields_zero_findings(  # DEC-33 §5 row 6
) -> None:
    """As written this shape failed with 2 × (i) + 1 × (ii); under the quantification amendment
    it passes, with the two constituents named on ``contained_nodes``."""
    witness = _witness(_p01(_mount_shape()))

    assert witness.reachable_from_start == ("n", "plan")
    assert witness.contained_nodes == ("n/%seq[0]", "n/%seq[1]")
    assert witness.terminal_nodes == ("n",)
    _assert_partition(witness, _mount_shape())


def test_a_node_set_projection_is_what_the_implementation_must_not_do() -> None:
    """DEC-33 §5 row 6's control, pinned as the *wrong* reading: projecting the contained ids
    out of ``nodes[]`` while keeping the sibling edge turns that edge into a condition-(iv)
    finding (``edge-target-undefined`` anchored at ``n/%seq[0]``). The ruling amends Steps
    2–4's quantification and leaves V, G and Step 1 whole — so on the full document the same
    edge resolves and no (iv) finding exists (the test above), which is exactly what a
    node-set projection would break."""
    projected = _ir(
        nodes=[_node("plan"), _node("n")],
        edges=[_edge("plan", "n"), _edge("n/%seq[0]", "n/%seq[1]")],
        entry="plan",
        finish="n",
    )

    assert _findings(_p01(projected)) == [
        (
            EDGE_TARGET_UNDEFINED,
            {"kind": "edge", "source": "n/%seq[0]", "undefined_target": "n/%seq[0]"},
        )
    ]
    # And on the real shape the model resolves the edge — no unresolved reference at all.
    assert build_graph_model(_mount_shape()).unresolved == ()


def test_the_orphan_root_yields_its_own_three_findings_never_twelve() -> None:
    """DEC-33 §5 row 4: participation would replicate the root's three findings onto each of
    its three descendants (12); projection reports the root's alone (3) — DEC-05 D2's
    one-root-cause, one-report discipline and §1.2's "one opaque vertex"."""
    ir = _ir(
        nodes=[_node("plan"), _node("n"), _node("n/%seq[0]"), _node("n/%seq[1]"), _node("n/x")],
        edges=[_edge("n/%seq[0]", "n/%seq[1]")],
        entry="plan",
        finish="plan",
    )

    findings = _findings(_p01(ir))

    assert len(findings) == 3
    assert findings == [
        (ORPHAN_NODE, {"kind": "node", "node": "n"}),
        (NODE_UNREACHABLE_FROM_START, {"kind": "node", "node": "n"}),
        (DEAD_END_NODE_NOT_WIRED_TO_END, {"kind": "node", "node": "n"}),
    ]


def test_anti_evasion_a_wired_root_exempts_its_unwired_descendants() -> None:
    """DEC-33 §3.1 rationale (d), first probe: ``plan`` wired, ``plan/x``, ``plan/y``,
    ``plan/y/z`` unwired — 9 findings as written, a pass under the convention with every
    exempted id named on the witness. The exposure is recorded in the ruling, not defended."""
    ir = _ir(
        nodes=[_node("plan"), _node("plan/x"), _node("plan/y"), _node("plan/y/z")],
        edges=[],
        entry="plan",
        finish="plan",
    )

    witness = _witness(_p01(ir))

    assert witness.reachable_from_start == ("plan",)
    assert witness.contained_nodes == ("plan/x", "plan/y", "plan/y/z")
    assert witness.terminal_nodes == ("plan",)
    _assert_partition(witness, ir)


def test_anti_evasion_an_interior_dead_end_is_the_roots_to_answer_for() -> None:
    """DEC-33 §3.1 rationale (d), second probe: ``a/x`` in ``entry``, ``a/x → a/y``, ``a/y`` a
    sink not in ``finish`` — ``dead-end-node-not-wired-to-end`` @ ``a/y`` as written, a pass
    under the convention with ``contained_nodes = [a/x, a/y]``. Renaming the sink to a top-level
    id restores the finding, which is what shows the exemption is containment's and not the
    edge's."""
    ir = _ir(
        nodes=[_node("a"), _node("a/x"), _node("a/y")],
        edges=[_edge("a/x", "a/y")],
        entry=["a", "a/x"],
        finish=["a"],
    )

    witness = _witness(_p01(ir))
    assert witness.reachable_from_start == ("a",)
    assert witness.contained_nodes == ("a/x", "a/y")
    _assert_partition(witness, ir)

    control = _ir(
        nodes=[_node("a"), _node("a/x"), _node("y")],
        edges=[_edge("a/x", "y")],
        entry=["a", "a/x"],
        finish=["a"],
    )
    assert _findings(_p01(control)) == [
        (DEAD_END_NODE_NOT_WIRED_TO_END, {"kind": "node", "node": "y"})
    ]


def test_condition_iv_still_anchors_at_a_contained_source() -> None:
    """DEC-33 §5 row 17: ``a/x → ghost`` is exactly one ``edge-target-undefined`` with
    ``source == "a/x"`` — (i)–(iii) report nothing for a contained node, but its own references
    remain condition (iv)'s, as for any node."""
    ir = _ir(
        nodes=[_node("a"), _node("b"), _node("a/x")],
        edges=[_edge("a", "b"), _edge("a/x", "ghost")],
        entry="a",
        finish="b",
    )

    assert _findings(_p01(ir)) == [
        (EDGE_TARGET_UNDEFINED, {"kind": "edge", "source": "a/x", "undefined_target": "ghost"})
    ]


def test_a_contained_id_in_entry_still_resolves_and_still_wires_start() -> None:
    """Condition (iv) resolves a contained id against the whole of V; the (m1) wiring enters G,
    and the node is reported under ``contained_nodes`` and never under ``reachable_from_start``
    even though the closure reaches it (§3.2 consequence (1))."""
    ir = _ir(nodes=[_node("a"), _node("a/x")], edges=[], entry=["a", "a/x"], finish=["a"])

    model = build_graph_model(ir)
    assert model.unresolved == ()
    assert "a/x" in model.descendants(START_VERTEX)

    witness = _witness(_p01(ir))
    assert witness.reachable_from_start == ("a",)
    assert witness.contained_nodes == ("a/x",)


# ── P-01: the witness partition (acceptance box 2) ───────────────────────────────────────


def test_a_contained_finish_id_lands_in_contained_nodes_and_terminal_nodes() -> None:
    """§3.2 consequence (1): finish wiring is the outgoing ``finish → __end__`` edge, so a
    contained ``finish`` id is not thereby in the closure — it lands in ``contained_nodes`` and,
    as a predecessor of ``__end__``, in ``terminal_nodes``; never in ``reachable_from_start``."""
    ir = _ir(nodes=[_node("a"), _node("a/x")], edges=[], entry="a", finish=["a", "a/x"])

    witness = _witness(_p01(ir))

    assert witness.reachable_from_start == ("a",)
    assert witness.contained_nodes == ("a/x",)
    assert witness.terminal_nodes == ("a", "a/x")
    _assert_partition(witness, ir)


def test_a_contained_node_inside_the_closure_is_still_reported_as_contained() -> None:
    """Wired from a reachable node, ``a/x`` is in the static closure; the ``∩ V_top`` is what
    keeps the three lists disjoint (§3.2 consequence (1))."""
    ir = _ir(nodes=[_node("a"), _node("a/x")], edges=[_edge("a", "a/x")], entry="a", finish="a/x")

    witness = _witness(_p01(ir))

    assert "a/x" in build_graph_model(ir).descendants(START_VERTEX)
    assert witness.reachable_from_start == ("a",)
    assert witness.contained_nodes == ("a/x",)
    assert witness.terminal_nodes == ("a/x",)
    _assert_partition(witness, ir)


def test_a_three_deep_chain_with_the_middle_wired_is_one_root() -> None:
    ir = _ir(
        nodes=[_node("a"), _node("a/b"), _node("a/b/c")],
        edges=[_edge("a", "a/b"), _edge("a/b", "a/b/c")],
        entry="a",
        finish="a",
    )

    witness = _witness(_p01(ir))

    assert witness.reachable_from_start == ("a",)
    assert witness.contained_nodes == ("a/b", "a/b/c")
    _assert_partition(witness, ir)


def test_a_dynamic_edge_beside_a_contained_node_fills_all_three_lists() -> None:
    """The case PD-058's critique named (objection 1): a document that nests a fragment *and*
    carries a reachable ``dynamic`` edge. ``dynamic_dependent`` is ``V_top ∖ reachable`` (DEC-33
    (F)), ``contained_nodes`` is ``V ∖ V_top``, and the three partition V."""
    ir = _ir(
        nodes=[_node("plan"), _node("plan/x"), _node("book")],
        edges=[_dynamic("plan"), _edge("plan", "plan/x")],
        entry="plan",
        finish=["book"],
        ir_version="1.1",
    )

    witness = _witness(_p01(ir))

    assert witness.reachable_from_start == ("plan",)
    assert witness.dynamic_dependent == ("book",)
    assert witness.contained_nodes == ("plan/x",)
    _assert_partition(witness, ir)


_CORPUS_IRS: list[tuple[str, WorkflowIR]] = [
    (f"{fixture.fixture_id}#{index}", ir)
    for fixture in load_corpus(FIXTURES_DIR)
    for index, ir in enumerate(fixture.irs)
]


@pytest.mark.parametrize(("label", "ir"), _CORPUS_IRS, ids=[label for label, _ in _CORPUS_IRS])
def test_the_partition_holds_on_every_corpus_pass(label: str, ir: WorkflowIR) -> None:
    """§1.3's invariant over the whole corpus: on every P-01 pass the three lists partition V —
    and, the corpus being flat (no id contains a ``/``; DEC-33 §5 row 5), the two optional
    members are absent and ``reachable_from_start`` is the whole of V, exactly as before."""
    report = _p01(ir)
    if report.result != "pass":
        return
    witness = _witness(report)
    _assert_partition(witness, ir)
    assert witness.contained_nodes is None and witness.dynamic_dependent is None, label
    assert set(witness.reachable_from_start) == {node.id for node in ir.nodes}, label


def test_negative_04_the_condition_iii_control_is_unmoved() -> None:
    """DEC-33 §5 row 8: the corpus's orphan is a top-level id and fails identically — primary
    ``orphan-node`` @ ``search_hotels``, 3 findings, equal to the fixture's own expected block."""
    fixture = load_fixture(
        FIXTURES_DIR / "graph-well-formed" / "negative-04-unwired-orphan-node.yaml"
    )
    assert fixture.ir is not None
    report = _p01(fixture.ir)

    findings = _findings(report)
    assert len(findings) == 3
    assert findings[0] == (ORPHAN_NODE, {"kind": "node", "node": "search_hotels"})
    assert models_equivalent(report, fixture.expected_report())


def test_no_condition_id_was_added_or_moved() -> None:
    """DEC-33 §3.3: no registry entry is added, removed, renamed or promoted; the three
    node-condition IDs keep their strings, severity and claim class."""
    assert [(e.id, e.severity, e.claim_class) for e in conditions_for("graph-well-formed")] == [
        ("node-unreachable-from-start", "fatal", "defensible"),
        ("dead-end-node-not-wired-to-end", "fatal", "defensible"),
        ("path-map-target-undefined", "fatal", "defensible"),
        ("orphan-node", "fatal", "defensible"),
        ("edge-target-undefined", "fatal", "defensible"),
    ]
    assert [entry.id for entry in conditions_for("dataflow-completeness")] == [
        "read-key-never-written-on-path"
    ]


# ── P-04: `contained_readers`, and `outside_static_coverage` over V_top (box 3) ──────────


def _silent_hole(*, plan_writes_a: bool) -> WorkflowIR:
    """DEC-33 §5 row 13: the mount shape with ``state {a, k}``, ``n`` reading ``a`` and the
    contained ``n/%seq[0]`` reading ``k``, which nothing writes. With ``plan`` writing ``a`` the
    reachable part passes; without it the reachable part fails at ``n``."""
    return _ir(
        nodes=[
            _node("plan", output=["a"]) if plan_writes_a else _node("plan"),
            _node("n", input=["a"]),
            _node("n/%seq[0]", input=["k"]),
            _node("n/%seq[1]"),
        ],
        edges=[_edge("plan", "n"), _edge("n/%seq[0]", "n/%seq[1]")],
        entry="plan",
        finish="n",
        state={"a": "str", "k": "str"},
    )


def test_the_silent_hole_is_named_on_the_pass_witness() -> None:
    """Before DEC-33 §3.4 this document passed P-04 with no diagnostic and, under §3.1 alone,
    the run would have exited 0 with a declared read no property reports."""
    witness = _dataflow(_p04(_silent_hole(plan_writes_a=True)))

    assert [(c.node, c.key) for c in witness.coverage] == [("n", "a")]
    assert witness.contained_readers == ("n/%seq[0]",)
    assert witness.outside_static_coverage is None

    report = verify(_silent_hole(plan_writes_a=True))
    assert report.gate.exit_code == 0 and report.best_effort == ()


def test_the_silent_hole_rides_the_primary_failure_on_the_fail_path() -> None:
    """The one carrier a failing report has (PD-057 D2): the diagnostic rides the primary
    ``P04Failure`` beside DEC-11's two, which are absent here."""
    report = _p04(_silent_hole(plan_writes_a=False))

    assert [c for c, _ in _findings(report)] == [READ_KEY_NEVER_WRITTEN_ON_PATH]
    failure = report.failure
    assert isinstance(failure, P04Failure)
    assert failure.location.node == "n" and failure.location.key == "a"
    assert failure.contained_readers == ("n/%seq[0]",)
    assert failure.outside_static_coverage is None
    assert failure.writers_on_other_paths is None and failure.downstream_writers is None


def test_a_wired_contained_reader_inside_reach_keeps_its_obligation() -> None:
    """DEC-33 §3.4 clause 1: a contained node on a static START-path is analysed by Step 4
    exactly as any other reachable reader — a finding when unwritten, a coverage entry when
    written — and is never a ``contained_readers`` member."""
    unwritten = _ir(
        nodes=[_node("a"), _node("a/x", input=["k"])],
        edges=[_edge("a", "a/x")],
        entry="a",
        finish="a/x",
        state={"k": "str"},
    )
    report = _p04(unwritten)
    failure = report.failure
    assert isinstance(failure, P04Failure)
    assert failure.location.node == "a/x" and failure.location.path == ("START", "a", "a/x")
    assert failure.contained_readers is None

    written = _ir(
        nodes=[_node("a", output=["k"]), _node("a/x", input=["k"])],
        edges=[_edge("a", "a/x")],
        entry="a",
        finish="a/x",
        state={"k": "str"},
    )
    witness = _dataflow(_p04(written))
    assert [(c.node, c.key, c.satisfied_by) for c in witness.coverage] == [("a/x", "k", ("a",))]
    assert witness.contained_readers is None
    assert "contained_readers" not in to_json(_p04(written))


def test_the_double_listing_is_split_between_the_two_members() -> None:
    """DEC-33 §5 row 14 and §3.4 clause 3: ``plan`` dynamic, ``book`` and ``plan/x`` both
    reading ``k`` — today's ``outside_static_coverage`` was ``["book", "plan/x"]``; now the
    top-level reader rides it and the contained reader rides ``contained_readers``, disjointly."""
    ir = _ir(
        nodes=[_node("plan"), _node("book", input=["k"]), _node("plan/x", input=["k"])],
        edges=[_dynamic("plan")],
        entry="plan",
        finish=["book"],
        state={"k": "str"},
        ir_version="1.1",
    )

    witness = _dataflow(_p04(ir))

    assert witness.outside_static_coverage == ("book",)
    assert witness.contained_readers == ("plan/x",)
    assert not set(witness.outside_static_coverage) & set(witness.contained_readers)

    # The whole run: P-01's three lists and P-04's two, on one document, at exit 0.
    report = verify(ir)
    assert report.gate.exit_code == 0 and report.best_effort == ()
    p01 = report.outcome_for("graph-well-formed")
    assert isinstance(p01, PropertyReport)
    p01_witness = _witness(p01)
    assert p01_witness.reachable_from_start == ("plan",)
    assert p01_witness.dynamic_dependent == ("book",)
    assert p01_witness.contained_nodes == ("plan/x",)


def test_contained_readers_needs_no_dispatcher_and_counts_a_read_outside_sigma() -> None:
    """No dispatcher condition (DEC-33 §3.4 clause 2), and "declared reads" is
    ``annotations.input`` Σ-membership aside (PD-057 D3): a contained reader of an undeclared
    key on a flat-wired document is still named."""
    ir = _ir(
        nodes=[_node("a"), _node("a/x", input=["undeclared"])],
        edges=[],
        entry="a",
        finish="a",
        state={"k": "str"},
    )

    witness = _dataflow(_p04(ir))

    assert witness.coverage == ()
    assert witness.contained_readers == ("a/x",)
    assert witness.outside_static_coverage is None


def test_a_contained_node_with_no_declared_read_is_not_a_contained_reader() -> None:
    """``reads(n) ≠ ∅`` is part of the definition: the LCEL goldens' constituents declare no
    ``input``, so neither golden carries the member at all."""
    for name in LCEL_GOLDENS:
        report = _p04(_golden(name))
        assert _dataflow(report).contained_readers is None
        assert "contained_readers" not in to_json(report)


# ── Rendering: the lines claim neither reachability nor interior well-formedness ─────────


def test_the_witness_lines_state_the_partition_without_claiming_reachability() -> None:
    witness = WellFormednessWitness(
        kind="well-formedness",
        reachable_from_start=("plan",),
        terminal_nodes=("plan",),
        orphan_nodes=(),
        unresolved_targets=(),
        dynamic_dependent=("book",),
        contained_nodes=("plan/x",),
    )

    lines = dict(witness_lines(witness))

    assert "of these" not in lines["dynamic-dependent"]  # false under the partition (DEC-33 §3.2)
    assert "beside the list above" in lines["dynamic-dependent"]
    assert "neither claimed nor denied" in lines["dynamic-dependent"]
    assert lines["contained nodes"].endswith(": plan/x")
    assert "containment root" in lines["contained nodes"]
    assert "reachab" not in lines["contained nodes"]
    assert "well-formed" not in lines["contained nodes"]
    assert "says nothing about the root's interior" in lines["contained nodes"]
    assert witness_summary(witness).endswith("| 1 dynamic-dependent node | 1 contained node")


def test_the_dataflow_lines_name_the_contained_readers_as_a_coverage_gap() -> None:
    witness = DataflowWitness(kind="dataflow", coverage=(), contained_readers=("n/%seq[0]",))

    lines = dict(witness_lines(witness))

    assert lines["contained readers"].endswith(": n/%seq[0]")
    assert "no analysis in this run covers those reads" in lines["contained readers"]
    assert "containment root" in lines["contained readers"]
    assert "not by a dynamic router" in lines["contained readers"]
    assert witness_summary(witness) == "0 (reader, key) obligations covered | 1 contained reader"


def test_neither_new_member_reaches_the_wire_on_a_flat_document() -> None:
    """Emitted only when non-empty (DEC-11 discipline): a flat document's P-01 witness is the
    five-key form and its P-04 witness carries neither diagnostic."""
    ir = _ir(
        nodes=[_node("a", output=["k"]), _node("b", input=["k"])],
        edges=[_edge("a", "b")],
        entry="a",
        finish="b",
        state={"k": "str"},
    )
    model: GraphModel = build_graph_model(ir)
    assert model.contained_nodes == frozenset()
    for slug in ("graph-well-formed", "dataflow-completeness"):
        text = to_json(_report(slug, ir))
        assert "contained_nodes" not in text and "contained_readers" not in text
