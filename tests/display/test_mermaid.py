"""The emitter's topology rules — DIAGRAM-STYLE-GUIDE §1–§3 and the §2 identity mapping.

Every assertion here is about the *text* the guide licenses, so a drift in the emitter is a
diff against a stated rule rather than a surprise in a golden. The corpus-wide validity
claim lives in ``test_corpus.py``; this module pins the constructs one fixture at a time.
"""

from __future__ import annotations

import pytest

from gebra.display import mermaid_label, mermaid_vertex_id, render_mermaid
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


# ── §3.3's headless router edge: carried on its source, never drawn as an arrow ──────────

#: A map-reduce document: ``plan`` dispatches dynamically, the workers converge on ``collect``.
DISPATCH = {
    "ir_version": "1.1",
    "entry": "plan",
    "finish": ["collect"],
    "nodes": nodes_of("plan", "book_leg", "collect"),
    "edges": [
        {"kind": "dynamic", "from": "plan", "condition": "route_legs"},
        {"from": "book_leg", "to": "collect"},
    ],
}


def _blocks(text: str) -> list[list[str]]:
    """The §1.4 body blocks — node definitions, edges, then the chrome and style blocks."""
    body = text.split("flowchart TD\n\n")[1]
    return [block.split("\n") for block in body.rstrip("\n").split("\n\n")]


def _dispatch_notes(text: str) -> list[str]:
    """The rendered note lines of the §3.3 block, in emission order."""
    if 'subgraph gebra_dynamic["gebra dynamic dispatch"]' not in text:
        return []
    block = text.split('subgraph gebra_dynamic["gebra dynamic dispatch"]')[1].split("  end")[0]
    return [line.strip() for line in block.strip().split("\n")]


def test_a_dynamic_edge_draws_no_arrow_and_invents_no_vertex() -> None:
    """PD-060's whole claim, in one assertion set: the 1.1 document draws, the source is
    marked, and the picture carries exactly the vertices and arrows a document without the
    edge would carry — no head, no glyph, no phantom (DEC-26 §3; DEC-28)."""
    vertices, edges, *_ = _blocks(render_mermaid(ir_of(DISPATCH)))
    assert vertices == [
        '  START(["START"])',
        '  n_plan["plan [D1]"]',
        '  n_book_5fleg["book_leg"]',
        '  n_collect["collect"]',
        '  END(["END"])',
    ]
    assert edges == ["  START --> n_plan", "  n_collect --> END", "  n_book_5fleg --> n_collect"]
    check_mermaid(render_mermaid(ir_of(DISPATCH)))


def test_the_dispatch_note_states_the_absent_target_set_and_resolves_the_marker() -> None:
    text = render_mermaid(ir_of(DISPATCH))
    assert _dispatch_notes(text) == [
        (
            'd_1["D1 dynamic dispatch - plan: 1 dynamic router, targets not statically '
            'known, so no arrow is drawn"]'
        )
    ]
    assert "  class d_1 gebra_info" in text


def test_the_declared_condition_is_elided_like_a_conditional_edges() -> None:
    """§3.3's one elision rule, applied to both router kinds: the guard expression is
    declared IR content a reader finds in the document, not diagram text."""
    text = render_mermaid(ir_of(DISPATCH))
    assert "route_legs" not in text


def test_two_routers_on_one_source_mark_it_once_and_are_counted() -> None:
    """A per-source annotation, not a per-edge glyph: the multiplicity PD-059 D1 keeps in
    the diff is stated on the note rather than drawn twice on the vertex."""
    ir = ir_of(
        {
            "ir_version": "1.1",
            "entry": "plan",
            "finish": [],
            "nodes": nodes_of("plan"),
            "edges": [{"kind": "dynamic", "from": "plan"}, {"kind": "dynamic", "from": "plan"}],
        }
    )
    text = render_mermaid(ir)
    assert '  n_plan["plan [D1]"]' in text
    assert _dispatch_notes(text) == [
        (
            'd_1["D1 dynamic dispatch - plan: 2 dynamic routers, targets not statically '
            'known, so no arrow is drawn"]'
        )
    ]


def test_notes_are_numbered_in_the_order_their_sources_are_authored() -> None:
    ir = ir_of(
        {
            "ir_version": "1.1",
            "entry": "b",
            "finish": [],
            "nodes": nodes_of("a", "b"),
            "edges": [{"kind": "dynamic", "from": "b"}, {"kind": "dynamic", "from": "a"}],
        }
    )
    text = render_mermaid(ir)
    assert '  n_a["a [D2]"]' in text
    assert '  n_b["b [D1]"]' in text
    assert [note[:4] for note in _dispatch_notes(text)] == ["d_1[", "d_2["]
    assert "- b:" in _dispatch_notes(text)[0] and "- a:" in _dispatch_notes(text)[1]
    check_mermaid(text)


def test_an_undeclared_source_is_marked_on_its_carried_phantom_vertex() -> None:
    """A source not in ``nodes[]`` still participates (§0.3), on the phantom convention: the reference is
    drawn dashed like any other carried reference and carries the marker."""
    ir = ir_of(
        {
            "ir_version": "1.1",
            "entry": "a",
            "finish": ["a"],
            "nodes": nodes_of("a"),
            "edges": [{"kind": "dynamic", "from": "ghost"}],
        }
    )
    text = render_mermaid(ir)
    assert '  n_ghost["ghost [D1]"]' in text
    assert "n_ghost" in _class_members(text, "gebra_unresolved")
    assert "the source is not drawn" not in text
    check_mermaid(text)


def test_a_source_the_drawing_never_materializes_is_noted_as_not_drawn() -> None:
    """(m5) keeps a reserved-segment reference off the picture, so there is no vertex to
    mark — and the note says so rather than dropping the router (§4.5's rule, in §3)."""
    ir = ir_of(
        {
            "ir_version": "1.1",
            "entry": "a",
            "finish": ["a"],
            "nodes": nodes_of("a"),
            "edges": [{"kind": "dynamic", "from": "__start__"}],
        }
    )
    text = render_mermaid(ir)
    assert "[D1]" not in text
    assert _dispatch_notes(text) == [
        (
            'd_1["D1 dynamic dispatch - __start__: 1 dynamic router, targets not '
            'statically known, so no arrow is drawn - no vertex carries this marker"]'
        )
    ]
    check_mermaid(text)


def test_a_1_1_stamp_with_no_dynamic_edge_draws_exactly_the_1_0_picture() -> None:
    """The corner CLI-06's ir pre-review recorded as N5 — a hand-authored 1.1 document with
    no ``dynamic`` edge — now answers like every other consumer: the stamp is in the header
    and nothing else moves."""
    plain = render_mermaid(ir_of(KINDS))
    stamped = render_mermaid(ir_of({**KINDS, "ir_version": "1.1"}))
    assert stamped == plain.replace("%% ir_version: 1.0", "%% ir_version: 1.1")
    assert "gebra_dynamic" not in stamped


def test_two_renders_of_one_dynamic_bearing_ir_are_byte_identical() -> None:
    ir = ir_of(DISPATCH)
    assert render_mermaid(ir) == render_mermaid(ir)


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
