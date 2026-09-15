"""The HTML wrapper — REL-05's claims, held to ``render_mermaid``'s own bytes.

The page is a frame around the Mermaid artifact and nothing more, so what is worth testing
is that the frame changes nothing: the text recovered from the page equals the text the
Mermaid emitter produces for the same inputs (plain and overlaid, over the corpus sample the
display suite already sweeps), the document is HTML5 that ``html.parser`` reads with exactly
one module script importing the pinned mermaid release, and the guide's §9 checker accepts
the embedded text. The CLI half — ``--format html`` through ``gebra.cli.main`` and its two
goldens — lives in ``tests/cli/test_display_verb.py``.

Nothing here runs a workflow: every subject is a corpus IR or a hand-built one, and the page
is text a browser would render — no browser is involved (WA-07).
"""

from __future__ import annotations

import re

import pytest

import gebra
from gebra.display import MERMAID_VERSION, OverlayPairingError, render_html, render_mermaid
from gebra.display.html import MERMAID_MODULE_URL, UNTITLED
from gebra.ir import WorkflowIR
from gebra.verify import verify
from tests.cli.conftest import FAILING_FIXTURE, PASSING_FIXTURE, fixture_ir
from tests.display.conftest import ir_of, nodes_of
from tests.display.pages import embedded_mermaid, read_page
from tests.display.test_corpus import CASES, PHRASES
from tools.mermaid_check import mermaid_problems

SOURCE = "pass.ir.yaml (ir-document)"


def _page(source: str | None = SOURCE) -> str:
    return render_html(fixture_ir(PASSING_FIXTURE), source=source)


# ── The frame changes nothing: recovery equals the Mermaid emitter, corpus-wide ──────────


@pytest.mark.parametrize(("name", "ir"), CASES, ids=[name for name, _ in CASES])
def test_the_embedded_text_is_render_mermaids_own_plain_and_overlaid(
    name: str, ir: WorkflowIR
) -> None:
    """Acceptance box 2, in full: for every corpus IR, plain and overlaid with its own
    ``verify()`` run, the text read back out of the page is the emitter's text byte for
    byte, the §9 checker accepts it, and the whole page is inside the WA-06 vocabulary."""
    source = f"{name} (ir-document)"
    report = verify(ir)
    for kwargs in ({}, {"report": report}):
        page = render_html(ir, source=source, **kwargs)
        text = render_mermaid(ir, source=source, **kwargs)
        assert embedded_mermaid(page) == text
        assert mermaid_problems(embedded_mermaid(page)) == []
        lowered = page.lower()
        for phrase in PHRASES:
            assert phrase not in lowered, f"{name}: the page carries {phrase!r}"


# ── The document: HTML5, one JSON block, one module script, the pinned release ──────────


def test_the_document_is_html5_that_the_standard_parser_reads() -> None:
    page = read_page(_page())
    assert page.doctype == "DOCTYPE html"
    assert _page().startswith('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">')


def test_exactly_one_module_script_imports_the_pinned_mermaid_release() -> None:
    document = _page()
    page = read_page(document)
    assert page.scripts == [
        {"type": "application/json", "id": "diagram"},
        {"type": "module"},
    ]
    assert f'import mermaid from "{MERMAID_MODULE_URL}";' in page.module_body
    assert document.count("mermaid@") == 1, "the release is named once, in the import"
    assert MERMAID_MODULE_URL.startswith("https://cdn.jsdelivr.net/npm/mermaid@")
    assert MERMAID_MODULE_URL.endswith("/dist/mermaid.esm.min.mjs")


def test_the_pin_is_an_exact_11_x_y_release() -> None:
    """REL-05's ruling: an exact ``11.x.y``, never a range, a tag or a major alone."""
    assert re.fullmatch(r"11\.\d+\.\d+", MERMAID_VERSION), MERMAID_VERSION
    assert f"mermaid@{MERMAID_VERSION}/" in MERMAID_MODULE_URL


def test_the_module_script_reads_the_json_block_and_renders_with_start_on_load_off() -> None:
    body = read_page(_page()).module_body
    assert 'JSON.parse(document.getElementById("diagram").textContent)' in body
    assert "mermaid.initialize({ startOnLoad: false })" in body
    assert "mermaid.render(" in body


# ── The title is the source line; the fallback is fixed ──────────────────────────────────


def test_the_title_and_heading_are_the_source_line() -> None:
    page = read_page(_page())
    assert page.title == SOURCE
    assert page.heading == SOURCE
    assert f"%% subject: {SOURCE}" in page.embedded_text


def test_without_a_source_the_title_is_the_fixed_fallback_and_no_subject_line_is_invented() -> None:
    page = read_page(_page(source=None))
    assert page.title == UNTITLED
    assert "%% subject:" not in page.embedded_text


# ── The two embeddings: JSON for the script and the reader, ``<noscript>`` for the rest ──


def test_the_noscript_fallback_carries_the_same_text() -> None:
    page = read_page(_page())
    assert page.noscript_pre == page.embedded_text


def test_the_json_block_carries_no_raw_angle_bracket_so_no_source_can_close_the_script() -> None:
    """A subject label is caller text. One spelling ``</script>`` must stay data inside the
    JSON element rather than end it — the whole page still has exactly two scripts, and the
    text comes back byte for byte, hostile label included."""
    source = "x</script><script>alert(1)</script><!-- (ir-document)"
    ir = fixture_ir(PASSING_FIXTURE)
    document = render_html(ir, source=source)
    page = read_page(document)
    assert "<" not in page.json_body
    assert len(page.scripts) == 2
    assert page.embedded_text == render_mermaid(ir, source=source)
    assert page.title == source


def test_non_ascii_text_is_kept_verbatim_in_a_utf8_page() -> None:
    source = "café.ir.yaml (ir-document)"
    document = _page(source=source)
    assert '<meta charset="utf-8">' in document
    assert "café" in read_page(document).json_body, "the JSON literal escaped non-ASCII"
    assert embedded_mermaid(document) == render_mermaid(fixture_ir(PASSING_FIXTURE), source=source)


# ── A wrapper, not a renderer: no paint, no version, the same refusals ───────────────────


def test_the_style_block_is_a_page_frame_and_paints_nothing() -> None:
    """The guide's §5 palette is the diagram's only paint: the page frame sizes and lays
    out, and names no fill, stroke or colour of its own."""
    style = read_page(_page()).style
    for paint in ("fill", "stroke", "color", "background"):
        assert paint not in style, f"the page frame paints ({paint!r})"


def test_the_page_embeds_no_tool_version_or_timestamp() -> None:
    """Guide §1.3, carried to the wrapper: equal inputs give identical pages across builds,
    which is what lets the CLI goldens survive a version bump unregenerated."""
    document = _page()
    assert gebra.__version__ not in document
    assert render_html(fixture_ir(PASSING_FIXTURE), source=SOURCE) == document
    assert document.endswith("\n") and not document.endswith("\n\n")


def test_the_pairing_refusal_propagates_unchanged() -> None:
    """The wrapper decides nothing: a report about another workflow is refused exactly as
    the Mermaid emitter refuses it (guide §4.1), before any page exists."""
    with pytest.raises(OverlayPairingError) as excinfo:
        render_html(fixture_ir(PASSING_FIXTURE), report=verify(fixture_ir(FAILING_FIXTURE)))
    assert "differs from the displayed IR's digest" in str(excinfo.value)


def test_an_overlaid_page_embeds_the_overlay_header_lines() -> None:
    ir = fixture_ir(FAILING_FIXTURE)
    text = embedded_mermaid(render_html(ir, report=verify(ir), source="fail.ir.yaml (ir-document)"))
    assert "%% overlay: run report for graph_version sha256:" in text
    assert "gebra findings overlay" in text


def test_a_dynamic_bearing_document_wraps_like_any_other() -> None:
    """The ir 1.1 drawing (CLI-11) is carried unchanged: the dispatch note block is inside
    the recovered text, and no arrow was invented on the way into the page."""
    ir = ir_of(
        {
            "ir_version": "1.1",
            "entry": "plan",
            "finish": [],
            "nodes": nodes_of("plan"),
            "edges": [{"kind": "dynamic", "from": "plan", "condition": "route_legs"}],
        }
    )
    text = embedded_mermaid(render_html(ir))
    assert text == render_mermaid(ir)
    assert '  n_plan["plan [D1]"]' in text
    assert "-.->" not in text
