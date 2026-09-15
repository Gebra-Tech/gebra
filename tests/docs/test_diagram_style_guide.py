"""DIAGRAM-STYLE-GUIDE.md pinned to the code that claims to implement it (card CLI-06).

The card's acceptance says "overlays match the guide", and prose cannot hold itself to
code, so this module does: the guide's §5 palette block is parsed and compared to the
emitter's own declarations, the §2 identity examples are executed, the §4.4 dispatch table
is held to the frozen §0.3 anchor vocabulary, and the emitted header strings are the
guide's. A drift in either direction — code or document — fails here rather than shipping
as a diagram that quietly stopped matching its contract.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final, get_args

import pytest

from gebra.display import MERMAID_VERSION, mermaid_label, mermaid_vertex_id, render_mermaid
from gebra.display.html import MERMAID_MODULE_URL
from gebra.display.mermaid import _CLASS_DEFS, _LINK_STYLE, _DispatchNote
from gebra.ir import WorkflowIR
from gebra.ir.serialization import load_json
from gebra.verify.locations import Location

REPO_ROOT: Final = Path(__file__).parent.parent.parent
GUIDE_PATH: Final = REPO_ROOT / "docs" / "specs" / "DIAGRAM-STYLE-GUIDE.md"


@pytest.fixture(scope="module")
def guide_text() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_the_guide_is_in_the_library_repo_beside_the_code() -> None:
    """CLI-06's artifact is an in-repo contract, like CLI-SPEC and REPORT-FORMAT-SPEC."""
    assert GUIDE_PATH.is_file(), f"{GUIDE_PATH} is missing"


def test_the_guide_names_its_authorities(guide_text: str) -> None:
    for authority in ("PD-034", "CLI-SPEC", "PROPERTY-CATALOG-SPEC", "REPORT-FORMAT-SPEC", "WA-06"):
        assert authority in guide_text, f"the guide never cites {authority}"


def test_the_s5_classdef_block_is_exactly_the_emitters_palette(guide_text: str) -> None:
    """The guide's fenced §5 block, line for line against ``_CLASS_DEFS`` — one palette,
    stated once in prose and once in code, held equal."""
    block = re.search(r"```\n(classDef[^`]+)```", guide_text)
    assert block is not None, "the §5 classDef block is missing"
    documented = [line for line in block.group(1).strip().split("\n")]
    built = [f"classDef {name} {declarations}" for name, declarations in _CLASS_DEFS]
    assert documented == built


def test_the_s5_link_paints_are_the_emitters_own(guide_text: str) -> None:
    assert f"fatal `{_LINK_STYLE['fatal']}`" in guide_text
    assert f"error\n`{_LINK_STYLE['error']}`" in guide_text.replace("error `", "error\n`")
    for severity in ("fatal", "error", "warning"):
        assert _LINK_STYLE[severity] in guide_text, f"the {severity} link paint drifted"


def test_the_s2_identity_examples_execute(guide_text: str) -> None:
    """The mapping rules as stated: fixed sentinel ids, the ``n_`` escape, ``_`` → ``_5f``."""
    assert mermaid_vertex_id("__start__") == "START"
    assert mermaid_vertex_id("__end__") == "END"
    assert mermaid_vertex_id("a_b") == "n_a_5fb"
    assert "`_` itself becomes `_5f`" in guide_text


def test_the_s24_escape_rules_are_the_five_the_guide_states(guide_text: str) -> None:
    for rule in ("`#` → `#35;`", '`"` → `#34;`', "`<` → `#60;`", "`>` → `#62;`"):
        assert rule in guide_text, f"escape rule {rule} missing from the guide"
    assert mermaid_label('#"<>') == "#35;#34;#60;#62;"
    assert mermaid_label("\n") == "#10;"


def test_the_s33_dispatch_note_template_is_the_emitters_own_line(guide_text: str) -> None:
    """The §3.3 fenced note form, held to the line the emitter builds: every fixed word of
    the template, in order, is in a real note — so a reworded emitter or a reworded guide
    fails here rather than drifting apart (card CLI-11)."""
    block = re.search(r"```\n\s*(D<i> dynamic dispatch[^`]+?)\s*```", guide_text)
    assert block is not None, "the §3.3 note template is missing"
    note = _DispatchNote(index=1, source="plan", routers=1, marked=True)
    position = 0
    for fixed in re.split(r"<[a-z]+>", block.group(1).strip()):
        assert fixed in note.text[position:], f"{fixed!r} is not in the emitted note"
        position = note.text.index(fixed, position) + len(fixed)
    assert note.text.startswith("D1 dynamic dispatch - plan: 1 dynamic router")
    assert _DispatchNote(index=2, source="p", routers=2, marked=True).text.startswith(
        "D2 dynamic dispatch - p: 2 dynamic routers"
    )


def test_the_s33_not_drawn_suffix_is_the_emitters_own(guide_text: str) -> None:
    suffix = " - no vertex carries this marker"
    assert f"`{suffix}`" in guide_text
    assert _DispatchNote(index=1, source="__start__", routers=1, marked=False).text.endswith(suffix)


def test_the_s33_marker_example_renders_as_the_guide_writes_it(guide_text: str) -> None:
    """`plan [D1 F2]` is the guide's worked example of the shared bracket block; the marker
    half of it is executed here, on a document whose one router dispatches dynamically."""
    assert "`plan [D1 F2]`" in guide_text
    ir = load_json(
        WorkflowIR,
        json.dumps(
            {
                "ir_version": "1.1",
                "entry": "plan",
                "finish": [],
                "nodes": [{"id": "plan"}],
                "edges": [{"kind": "dynamic", "from": "plan", "condition": "route_legs"}],
            }
        ),
    )
    text = render_mermaid(ir)
    assert '  n_plan["plan [D1]"]' in text
    assert '  subgraph gebra_dynamic["gebra dynamic dispatch"]' in text
    assert "  class d_1 gebra_info" in text
    assert "-->" not in text.split("START --> n_plan")[1], "a headless edge was drawn"


def test_the_s34_section_declines_nothing(guide_text: str) -> None:
    """The acceptance box's own question — what, if anything, this guide still declines —
    answered in the section that used to carry the one decline."""
    section = guide_text.split("### 3.4 Documents this guide declines")[1].split("## 4.")[0]
    assert section.lstrip().startswith("**None.**")
    assert "CLI-11 ruled it" in section and "the decline is lifted" in section


def test_the_s44_dispatch_table_covers_exactly_the_frozen_anchor_kinds(
    guide_text: str,
) -> None:
    """One row per §0.3 ``kind``, no invented kind, none missing — the frozen vocabulary
    read off the ``Location`` union itself, not restated here."""
    section = guide_text.split("### 4.4")[1].split("### 4.5")[0]
    rows = re.findall(r"^\| `([a-z-]+)` \|", section, flags=re.MULTILINE)
    frozen: set[str] = set()
    for anchor in get_args(get_args(Location)[0]):
        frozen.update(get_args(anchor.model_fields["kind"].annotation))
    assert set(rows) == frozen
    assert len(rows) == len(frozen)


def test_the_header_strings_are_the_guides(guide_text: str) -> None:
    assert "%% gebra display: workflow definition as Mermaid (DIAGRAM-STYLE-GUIDE)" in guide_text
    assert "`flowchart TD`" in guide_text


def test_plantuml_is_a_decision_statement_not_a_capability(guide_text: str) -> None:
    section = guide_text.split("## 8. PlantUML")[1].split("## 9.")[0]
    assert "no PlantUML emitter in Phase-0" in section
    assert "WA-12" in section


def test_the_conformance_checker_the_guide_names_exists(guide_text: str) -> None:
    assert "tools/mermaid_check.py" in guide_text
    assert (REPO_ROOT / "tools" / "mermaid_check.py").is_file()


def test_the_guide_states_what_parse_checked_claims(guide_text: str) -> None:
    """The acceptance box's own honesty: the checker parses the licensed subset; it is not
    the Mermaid renderer, and the guide says so rather than implying more."""
    flat = " ".join(guide_text.split("## 9. Conformance")[1].split())
    assert "not the Mermaid renderer" in flat
    assert "**refuses any construct outside it**" in flat


def test_the_s9_html_note_names_the_pinned_mermaid_release_the_wrapper_loads(
    guide_text: str,
) -> None:
    """REL-05's landing note is held to the emitter's own pin: the release the page imports
    is the one the guide records, so moving either alone fails here rather than drifting."""
    conformance = guide_text.split("## 9. Conformance")[1]
    assert "**REL-05" in conformance, "§9 carries no REL-05 landing note"
    note = " ".join(conformance.split("**REL-05")[1].split())
    assert MERMAID_MODULE_URL in note
    assert f"`{MERMAID_VERSION}`" in note
    assert "no rule, palette value, escape or id mapping moved" in note
    assert "integrity" in note, "the SRI decision is unrecorded"
