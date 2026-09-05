"""The overlay rules — DIAGRAM-STYLE-GUIDE §4, on real reports wherever one exists.

Integration cases run ``verify()`` over corpus and constructed IRs, so what gets painted is
what the pipeline actually emits; the per-kind unit cases construct §0.3 locations directly
for the two anchors no wedge validator produces on the corpus (a plain ``path``, an
unmatchable node). Pairing refusals (§4.1) are asserted against both the checker function
and the rendered path.
"""

from __future__ import annotations

import pytest

import gebra
from gebra.display import render_mermaid
from gebra.display.overlay import (
    OverlayPairingError,
    _paint_finding,
    _Painter,
    _Resolver,
    _statement_entry,
    build_overlay,
    check_pairing,
)
from gebra.ir import graph_version
from gebra.report.findings import Finding
from gebra.verify import (
    STRICT_OFF,
    GateOutcome,
    RunReport,
    SeverityCounts,
    Subject,
    Tool,
    ToolError,
    verify,
)
from gebra.verify.graph import build_graph_model
from gebra.verify.locations import NodeLocation, PathLocation
from tests.cli.conftest import FAILING_FIXTURE, PASSING_FIXTURE, fixture_ir
from tests.display.conftest import ir_of, nodes_of
from tools.mermaid_check import check_mermaid

FIXTURES = PASSING_FIXTURE.parent.parent


def _overlaid(path_name: str) -> str:
    ir = fixture_ir(FIXTURES / path_name)
    return render_mermaid(ir, report=verify(ir))


# ── §4.1 pairing ─────────────────────────────────────────────────────────────────────────


def test_a_report_about_another_workflow_is_refused() -> None:
    passing = fixture_ir(PASSING_FIXTURE)
    failing = fixture_ir(FAILING_FIXTURE)
    with pytest.raises(OverlayPairingError) as excinfo:
        render_mermaid(passing, report=verify(failing))
    assert "differs from the displayed IR's digest" in str(excinfo.value)
    assert "false statement about both" in str(excinfo.value)


def _subjectless_tool_error() -> RunReport:
    return RunReport(
        report_format="1.2",
        tool=Tool(name="gebra", version=gebra.__version__),
        subject=None,
        properties=(),
        gate=GateOutcome(
            exit_code=2,
            outcome="tool-error",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=STRICT_OFF,
            promotions=(),
            snapshot_eligible=False,
        ),
        error=ToolError(stage="input", detail="nothing resolved"),
    )


def test_a_subjectless_report_is_refused_for_want_of_a_digest() -> None:
    with pytest.raises(OverlayPairingError) as excinfo:
        render_mermaid(fixture_ir(PASSING_FIXTURE), report=_subjectless_tool_error())
    assert "names no graph_version" in str(excinfo.value)


def test_check_pairing_passes_a_report_about_this_ir() -> None:
    ir = fixture_ir(PASSING_FIXTURE)
    check_pairing(graph_version(ir), verify(ir))


# ── §4.2–§4.4 painting, on real reports ──────────────────────────────────────────────────


def test_an_scc_finding_paints_the_member_edges_and_the_legend_carries_the_facts() -> None:
    """mixed/01: a FATAL P-02 residual SCC and an ERROR P-06 node finding."""
    ir = fixture_ir(FAILING_FIXTURE)
    text = render_mermaid(ir, report=verify(ir))
    assert "%% overlay: run report for graph_version sha256:" in text
    assert "gate: fail (exit 1)" in text
    assert '    f_1["F1 fatal [defensible] cycle-without-termination-witness' in text
    assert (
        '    f_2["F2 error [defensible-a] unprotected-effect-in-retry-region - node send_sms"'
        in text
    )
    assert '  n_send_5fsms["send_sms [F2]"]' in text
    assert '  n_verify_5fdelivery -->|"retry [F1]"| n_send_5fsms' in text
    assert "  linkStyle 3 stroke:#7f1d1d,stroke-width:3px" in text
    assert "  linkStyle 4 stroke:#7f1d1d,stroke-width:3px" in text
    assert "  class f_1 gebra_fatal" in text
    assert "  class n_send_5fsms,f_2 gebra_error" in text
    check_mermaid(text)


def test_a_dangling_path_map_target_paints_the_phantom_edge() -> None:
    """graph-well-formed/negative-03: P-01's dangling label anchors on the carried edge."""
    text = _overlaid("graph-well-formed/negative-03-path-map-typo-dangling-target.yaml")
    assert "path-map-target-undefined" in text
    assert "gebra_unresolved" in text
    marked = [line for line in text.split("\n") if "[F" in line and "-->" in line]
    assert marked, "no edge carries the P-01 finding's marker"
    check_mermaid(text)


def test_a_dataflow_finding_paints_the_reading_node() -> None:
    """dataflow-completeness/negative-01: a state-key anchor attributed to its reader."""
    text = _overlaid("dataflow-completeness/negative-01-express-path-skips-writer.yaml")
    assert "read-key-never-written-on-path" in text
    assert "state key" in text
    node_lines = [line for line in text.split("\n") if line.startswith("  n_") and "[F" in line]
    assert node_lines, "no node carries the dataflow finding's marker"
    check_mermaid(text)


def test_best_effort_findings_say_so_in_the_legend_and_the_header() -> None:
    """A FATAL P-01 makes the three topology consumers best-effort (§1.3); the diagram
    states it where the findings are, not only in a header nobody renders."""
    ir = fixture_ir(
        FIXTURES / "mixed" / "04-dangling-path-map-target-orphans-downstream-reader.yaml"
    )
    text = render_mermaid(ir, report=verify(ir))
    assert (
        "%% overlay best-effort: termination-witness, dataflow-completeness, effect-safety" in text
    )
    assert "not contract-bearing verdicts" in text
    assert "(best-effort)" in text
    check_mermaid(text)


def test_a_zero_findings_pass_overlay_states_the_gate_and_paints_no_badge() -> None:
    ir = fixture_ir(PASSING_FIXTURE)
    text = render_mermaid(ir, report=verify(ir))
    assert "gate: pass (exit 0)" in text
    assert '    f_0["no findings to paint - gate: pass (exit 0); per-property claim' in text
    assert "  class f_0 gebra_info" in text
    assert "linkStyle" not in text
    check_mermaid(text)


def test_the_legend_carries_every_finding_exactly_once() -> None:
    for name in (
        "mixed/01-witnessed-cycle-with-unkeyed-billable-node.yaml",
        "mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml",
        "graph-well-formed/negative-03-path-map-typo-dangling-target.yaml",
    ):
        ir = fixture_ir(FIXTURES / name)
        report = verify(ir)
        expected = report.gate.counts.fatal + report.gate.counts.error + report.gate.counts.warning
        text = render_mermaid(ir, report=report)
        legend_lines = [line for line in text.split("\n") if line.startswith("    f_")]
        assert len(legend_lines) == expected, name
        for index in range(1, expected + 1):
            assert sum(f'"F{index} ' in line for line in legend_lines) == 1, (name, index)


def test_a_not_drawn_finding_is_still_in_the_legend_with_the_suffix() -> None:
    """A reserved-segment entry reference (m5) is never materialized, so its P-01 finding
    has no on-picture anchor — the legend still carries it, saying so (§4.5)."""
    ir = ir_of({"entry": ["a", "__end__"], "finish": ["a"], "nodes": nodes_of("a"), "edges": []})
    text = render_mermaid(ir, report=verify(ir))
    assert "- not drawn in this diagram" in text
    check_mermaid(text)


def test_strict_promotion_is_stated_and_the_record_keeps_its_own_severity() -> None:
    from gebra.verify import STRICT_ALL, RunPolicy

    ir = fixture_ir(
        FIXTURES / "mixed" / "03-parallel-reducerless-key-with-unpinned-llm-writers.yaml"
    )
    report = verify(ir, RunPolicy(strict=STRICT_ALL))
    assert report.gate.outcome == "fail" and report.gate.promotions
    text = render_mermaid(ir, report=report)
    assert "%% overlay strict: all" in text
    assert "promoted at the gate; promotion moves the gate, never the record" in text
    assert "gebra_fatal" not in text, "a promoted warning was painted above its own grade"
    check_mermaid(text)


# ── Unit seams: the two §4.4 anchors no corpus report reaches ────────────────────────────


def _finding(location: object) -> Finding:
    return Finding(
        owner="graph-well-formed",
        host="graph-well-formed",
        origin="failure",
        severity="error",
        claim_class="defensible",
        property_condition="node-unreachable-from-start",
        location=location,  # type: ignore[arg-type]
    )


def test_a_path_location_paints_every_edge_along_the_recorded_walk() -> None:
    ir = ir_of(
        {
            "entry": "a",
            "finish": ["c"],
            "nodes": nodes_of("a", "b", "c"),
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        }
    )
    model = build_graph_model(ir, carry_unresolved_references=True)
    resolver, painter = _Resolver(model), _Painter()
    drawn = _paint_finding(
        _finding(PathLocation(kind="path", nodes=("START", "a", "b", "c"))),
        "F1",
        resolver,
        painter,
    )
    assert drawn
    painted = {model.edges[index].source for index in painter.link_severity}
    assert painted == {"__start__", "a", "b"}
    assert all(markers == ["F1"] for markers in painter.link_markers.values())


def test_an_anchor_naming_no_vertex_paints_nothing() -> None:
    ir = ir_of({"entry": "a", "finish": ["a"], "nodes": nodes_of("a"), "edges": []})
    model = build_graph_model(ir, carry_unresolved_references=True)
    resolver, painter = _Resolver(model), _Painter()
    drawn = _paint_finding(
        _finding(NodeLocation(kind="node", node="nobody")), "F1", resolver, painter
    )
    assert not drawn
    assert not painter.vertex_severity and not painter.link_severity


def test_severity_precedence_keeps_the_highest_and_accumulates_markers() -> None:
    painter = _Painter()
    painter.paint_vertex("a", "warning", "F1")
    painter.paint_vertex("a", "fatal", "F2")
    painter.paint_vertex("a", "error", "F3")
    assert painter.vertex_severity["a"] == "fatal"
    assert painter.vertex_markers["a"] == ["F1", "F2", "F3"]
    painter.paint_link(0, "error", "F1")
    painter.paint_link(0, "warning", "F2")
    assert painter.link_severity[0] == "error"


def test_a_declared_node_named_start_wins_over_the_sentinel_reading() -> None:
    ir = ir_of({"entry": "START", "finish": ["START"], "nodes": nodes_of("START"), "edges": []})
    model = build_graph_model(ir, carry_unresolved_references=True)
    assert _Resolver(model).vertex("START") == "START"
    assert "START" in model.node_ids


# ── The closed statement-entry vocabulary (§4.3) ─────────────────────────────────────────


def _gate(exit_code: int, outcome: str) -> GateOutcome:
    return GateOutcome(
        exit_code=exit_code,  # type: ignore[arg-type]
        outcome=outcome,  # type: ignore[arg-type]
        counts=SeverityCounts(fatal=0, error=0, warning=0),
        strict=STRICT_OFF,
        promotions=(),
        snapshot_eligible=exit_code == 0,
    )


def test_the_statement_entries_state_the_gate_and_never_a_bare_badge() -> None:
    pass_entry = _statement_entry(_gate(0, "pass"), None)
    assert "per-property claim classes are in the run report" in pass_entry.text
    notes_entry = _statement_entry(_gate(0, "pass-with-notes"), None)
    assert "warning-grade notes are in the run report" in notes_entry.text
    fail_entry = _statement_entry(_gate(1, "fail"), None)
    assert "moved by promotion" in fail_entry.text
    error_entry = _statement_entry(_gate(2, "tool-error"), ToolError(stage="dispatch", detail="d"))
    assert "no verdict was reached (stage: dispatch)" in error_entry.text
    for entry in (pass_entry, notes_entry, fail_entry, error_entry):
        assert entry.severity is None and entry.index == 0


def test_a_subject_bearing_tool_error_report_overlays_as_a_statement() -> None:
    """A dispatch-stage tool error carries a subject, so the §4.1 checks can pass; the
    overlay then paints nothing and says why (§4.3)."""
    ir = fixture_ir(PASSING_FIXTURE)
    digest = graph_version(ir)
    report = RunReport(
        report_format="1.2",
        tool=Tool(name="gebra", version=gebra.__version__),
        subject=Subject(
            input_mode="ir-document",
            source="pass.ir.yaml",
            ir_version="1.0",
            graph_version=digest,
        ),
        properties=(),
        gate=GateOutcome(
            exit_code=2,
            outcome="tool-error",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=STRICT_OFF,
            promotions=(),
            snapshot_eligible=False,
        ),
        error=ToolError(stage="dispatch", detail="no validator registered"),
    )
    text = render_mermaid(ir, report=report)
    assert "gate: tool-error (exit 2)" in text
    assert '    f_0["no verdict was reached (stage: dispatch) - nothing to paint"]' in text
    check_mermaid(text)


def test_build_overlay_header_quotes_the_reports_own_facts() -> None:
    ir = fixture_ir(FAILING_FIXTURE)
    report = verify(ir)
    overlay = build_overlay(
        build_graph_model(ir, carry_unresolved_references=True),
        report,
        digest=graph_version(ir),
    )
    assert any("counts: fatal 1, error 1, warning 0" in line for line in overlay.header_lines)
