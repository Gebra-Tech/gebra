"""The emitter's topology rules — DIAGRAM-STYLE-GUIDE §1–§3 and the §2 identity mapping.

Every assertion here is about the *text* the guide licenses, so a drift in the emitter is a
diff against a stated rule rather than a surprise in a golden. The corpus-wide validity
claim lives in ``test_corpus.py``; this module pins the constructs one fixture at a time.
"""

from __future__ import annotations

import pytest

from gebra.display import mermaid_label, mermaid_vertex_id, render_mermaid
from gebra.ir import DynamicEdgeUnsupportedError
from tests.display.conftest import ir_of, nodes_of
from tools.mermaid_check import check_mermaid

#: A router workflow exercising every 1.0 edge kind and both sentinel wirings.
KINDS = {
    "entry": "plan",
    "finish": "wrap",
    "nodes": nodes_of("plan", "route", "left", "right", "wrap"),
    "edges": [
        {"from": "plan", "to": "route"},
        {"kind": "conditional", "from": "route", "path_map": {"a": "left", "b": "right"}},
        {"kind": "send", "from": "left", "to": "wrap"},
        {"from": "right", "to": "wrap"},
    ],
}


def test_the_artifact_opens_with_the_header_comment_then_flowchart_td() -> None:
    text = render_mermaid(ir_of(KINDS), source="demo.ir.yaml (ir-document)")
    lines = text.split("\n")
    assert lines[0] == "%% gebra display: workflow definition as Mermaid (DIAGRAM-STYLE-GUIDE)"
    assert lines[1] == "%% subject: demo.ir.yaml (ir-document)"
    assert lines[2] == "%% ir_version: 1.0"
    assert lines[3] == "flowchart TD"


def test_without_a_source_no_subject_line_is_invented() -> None:
    text = render_mermaid(ir_of(KINDS))
    assert "%% subject:" not in text


def test_sentinels_are_stadium_nodes_with_the_display_spelling() -> None:
    text = render_mermaid(ir_of(KINDS))
    assert '  START(["START"])' in text
    assert '  END(["END"])' in text
    assert "__start__" not in text and "__end__" not in text


def test_entry_and_finish_wire_the_sentinels_as_solid_edges() -> None:
    text = render_mermaid(ir_of(KINDS))
    assert "  START --> n_plan" in text
    assert "  n_wrap --> END" in text


def test_each_path_map_label_is_one_labeled_solid_arrow() -> None:
    text = render_mermaid(ir_of(KINDS))
    assert '  n_route -->|"a"| n_left' in text
    assert '  n_route -->|"b"| n_right' in text


def test_a_send_edge_is_a_dashed_arrow_with_no_fanout_count() -> None:
    text = render_mermaid(ir_of(KINDS))
    assert "  n_left -.-> n_wrap" in text


def test_definition_order_is_start_then_authored_nodes_then_end() -> None:
    text = render_mermaid(ir_of(KINDS))
    body = text.split("flowchart TD")[1]
    positions = [
        body.index(marker)
        for marker in ('START(["START"])', "n_plan[", "n_route[", "n_wrap[", 'END(["END"])')
    ]
    assert positions == sorted(positions)


def test_two_renders_of_one_ir_are_byte_identical() -> None:
    ir = ir_of(KINDS)
    assert render_mermaid(ir) == render_mermaid(ir)


def test_every_line_is_newline_terminated_and_the_artifact_parse_checks() -> None:
    text = render_mermaid(ir_of(KINDS))
    assert text.endswith("\n") and not text.endswith("\n\n")
    check_mermaid(text)


def test_a_path_map_label_valued_end_targets_the_end_vertex() -> None:
    ir = ir_of(
        {
            "entry": "a",
            "finish": [],
            "nodes": nodes_of("a"),
            "edges": [{"kind": "conditional", "from": "a", "path_map": {"stop": "END"}}],
        }
    )
    text = render_mermaid(ir)
    assert '  n_a -->|"stop"| END' in text


def test_to_end_on_a_normal_edge_is_an_unresolved_reference_not_a_sentinel() -> None:
    """IR-SPEC §4.2 (m4), as corrected at DEC-27: the literal is blessed for path_map
    values only, so a ``to: "END"`` names a node — here none exists, so the reference is
    drawn as a dashed phantom named END, distinct from the sentinel's stadium."""
    ir = ir_of(
        {
            "entry": "a",
            "finish": ["a"],
            "nodes": nodes_of("a"),
            "edges": [{"from": "a", "to": "END"}],
        }
    )
    text = render_mermaid(ir)
    assert '  n_END["END"]' in text
    assert "  n_a --> n_END" in text
    assert "n_END" in _class_members(text, "gebra_unresolved")


def test_an_unresolved_path_map_target_is_a_dashed_phantom_vertex() -> None:
    ir = ir_of(
        {
            "entry": "a",
            "finish": ["b"],
            "nodes": nodes_of("a", "b"),
            "edges": [
                {"kind": "conditional", "from": "a", "path_map": {"ok": "b", "oops": "ghost"}}
            ],
        }
    )
    text = render_mermaid(ir)
    assert '  n_ghost["ghost"]' in text
    assert '  n_a -->|"oops"| n_ghost' in text
    assert "n_ghost" in _class_members(text, "gebra_unresolved")
    check_mermaid(text)


def test_a_reserved_segment_reference_is_never_materialized() -> None:
    """(m5): a reference spelling ``__end__`` is recorded, not drawn — no vertex, no
    edge — so the sentinel keeps its no-incoming/no-outgoing shape."""
    ir = ir_of(
        {
            "entry": ["a", "__end__"],
            "finish": ["a"],
            "nodes": nodes_of("a"),
            "edges": [],
        }
    )
    text = render_mermaid(ir)
    edge_lines = [line for line in text.split("\n") if "-->" in line or "-.->" in line]
    assert edge_lines == ["  START --> n_a", "  n_a --> END"]
    assert "n__5f" not in text, "the reserved segment was drawn as a phantom"
    assert "gebra_unresolved" not in text
    check_mermaid(text)


def test_parallel_edges_between_one_pair_are_both_drawn() -> None:
    ir = ir_of(
        {
            "entry": "a",
            "finish": ["b"],
            "nodes": nodes_of("a", "b"),
            "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "b"}],
        }
    )
    text = render_mermaid(ir)
    assert text.count("  n_a --> n_b") == 2


def test_a_dynamic_bearing_document_is_declined_by_name() -> None:
    ir = ir_of(
        {
            "ir_version": "1.1",
            "entry": "a",
            "finish": ["a"],
            "nodes": nodes_of("a"),
            "edges": [{"kind": "dynamic", "from": "a"}],
        }
    )
    with pytest.raises(DynamicEdgeUnsupportedError) as excinfo:
        render_mermaid(ir)
    assert "display emitter" in str(excinfo.value)


class TestVertexIds:
    def test_the_mapping_is_the_guide_s2_escape(self) -> None:
        assert mermaid_vertex_id("plan_trip") == "n_plan_5ftrip"
        assert mermaid_vertex_id("chain/%seq[0]") == "n_chain_2f_25seq_5b0_5d"
        assert mermaid_vertex_id("__start__") == "START"
        assert mermaid_vertex_id("__end__") == "END"

    def test_the_escape_is_injective_on_lookalike_ids(self) -> None:
        ids = ["a_b", "a/b", "a b", "a_5fb", "a%b", "aébé", "START", "end"]
        mapped = {mermaid_vertex_id(node_id) for node_id in ids}
        assert len(mapped) == len(ids)

    def test_a_declared_node_named_start_does_not_collide_with_the_sentinel(self) -> None:
        assert mermaid_vertex_id("START") == "n_START"

    def test_multibyte_characters_escape_per_utf8_byte(self) -> None:
        assert mermaid_vertex_id("é") == "n__c3_a9"


class TestLabels:
    @pytest.mark.parametrize(
        ("raw", "escaped"),
        [
            ("plain", "plain"),
            ('say "hi"', "say #34;hi#34;"),
            ("a # b", "a #35; b"),
            ("%map[<lambda>]", "%map[#60;lambda#62;]"),
            ("line\nbreak", "line#10;break"),
            ("tab\there", "tab#9;here"),
            ("naïve", "naïve"),
        ],
    )
    def test_the_five_escape_rules(self, raw: str, escaped: str) -> None:
        assert mermaid_label(raw) == escaped

    def test_a_hostile_node_id_still_parse_checks(self) -> None:
        ir = ir_of(
            {
                "entry": 'we "quote" # and <tag>',
                "finish": ['we "quote" # and <tag>'],
                "nodes": [{"id": 'we "quote" # and <tag>'}],
                "edges": [],
            }
        )
        check_mermaid(render_mermaid(ir))


def _class_members(text: str, class_name: str) -> str:
    """The ids assigned to ``class_name``, or the empty string when none are."""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("class ") and stripped.endswith(f" {class_name}"):
            return stripped[len("class ") : -len(class_name) - 1]
    return ""
