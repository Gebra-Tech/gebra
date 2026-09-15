"""The HTML wrapper — one self-contained page that renders the Mermaid artifact (card REL-05).

``gebra display`` emits Mermaid text, which a reader cannot look at without a renderer. This
module wraps that text — **the exact bytes** :func:`gebra.display.render_mermaid` produces,
overlay included — in a complete HTML5 document that loads mermaid.js from a CDN *at view
time* and renders the text in the browser. The wrapper adds no drawing rule, no vertex and
no paint: every line of the diagram is DIAGRAM-STYLE-GUIDE's, and the page is only the
frame around it (CLI-SPEC §4.4; the guide's §9 REL-05 note). The package gains no runtime
dependency — the pinned release below is fetched by the browser that opens the page, never
by gebra.

The Mermaid text is embedded twice, for two readers. A ``<script type="application/json">``
element carries it as one JSON string literal, which is how the module script reads it back
(``JSON.parse``) and how a test recovers it byte for byte (``json.loads``): no HTML-entity
round trip touches a label. A ``<noscript>`` block carries it HTML-escaped inside a ``<pre>``,
so a reader with scripts disabled still sees the artifact. Nothing on this page runs when the
page is emitted (WA-07): rendering is a string assembly over the text, and the one script on
it executes only in a browser that opens the file.

Byte-reproducible like the text it wraps (guide §1.3): equal inputs give identical documents,
and the page embeds no tool version and no timestamp — the pinned mermaid release is the only
version literal in it, and it is a constant of this module, not of the build.
"""

from __future__ import annotations

import html
import json
from typing import Final

from gebra.display.mermaid import render_mermaid
from gebra.ir import WorkflowIR
from gebra.verify.run import RunReport

__all__ = ["MERMAID_MODULE_URL", "MERMAID_VERSION", "UNTITLED", "render_html"]

#: The one mermaid.js release the page loads, pinned exactly — a ``11.x.y`` per REL-05's
#: ruling, the newest of that line on jsdelivr when the card landed (2026-09-15). Moving it
#: is a landing note in DIAGRAM-STYLE-GUIDE §9, which names this value and is held to it.
MERMAID_VERSION: Final = "11.17.2"

#: Where the module script imports mermaid from at view time. jsdelivr serves a versioned path
#: immutably, so the pin above is the whole of the page's dependency on the outside world. No
#: ``integrity`` attribute: an ES-module ``import`` statement carries none, and the ESM entry
#: loads chunk files an entry-point hash would not cover (the §9 note records both facts).
MERMAID_MODULE_URL: Final = (
    f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.esm.min.mjs"
)

#: The ``<title>`` (and heading) when the caller supplies no subject label — the library
#: function admits ``None``; the verb always supplies the CLI-SPEC §2.1 label.
UNTITLED: Final = "gebra display"

#: The ``id`` of the JSON script element carrying the text, and of the element the rendered
#: SVG lands in. Distinct from every id mermaid itself assigns.
_DIAGRAM_ELEMENT_ID: Final = "diagram"
_VIEW_ELEMENT_ID: Final = "diagram-view"

#: The minimal page frame — layout only. No colour, no font of the diagram's own: the
#: drawing's paint is the Mermaid text's (guide §5), never a stylesheet's.
_STYLE_LINES: Final[tuple[str, ...]] = (
    "  body { margin: 0 auto; padding: 1rem; max-width: 100rem; font-family: system-ui, sans-serif; }",
    "  h1 { font-size: 1rem; font-weight: 600; margin: 0 0 1rem; }",
    f"  #{_VIEW_ELEMENT_ID} svg {{ max-width: 100%; height: auto; }}",
    "  pre { overflow: auto; }",
)

#: The one module script on the page: import the pinned release, read the embedded text back
#: with ``JSON.parse`` and render it. ``startOnLoad`` is off so mermaid reads nothing but the
#: JSON block; a render error shows the message *and* the text rather than a blank page.
_MODULE_SCRIPT_LINES: Final[tuple[str, ...]] = (
    f'import mermaid from "{MERMAID_MODULE_URL}";',
    "",
    f'const text = JSON.parse(document.getElementById("{_DIAGRAM_ELEMENT_ID}").textContent);',
    f'const view = document.getElementById("{_VIEW_ELEMENT_ID}");',
    "mermaid.initialize({ startOnLoad: false });",
    "try {",
    '  const { svg } = await mermaid.render("gebra-diagram-svg", text);',
    "  view.innerHTML = svg;",
    "} catch (error) {",
    '  const fallback = document.createElement("pre");',
    '  fallback.textContent = "mermaid could not render this diagram: " + error + "\\n\\n" + text;',
    "  view.replaceChildren(fallback);",
    "}",
)


def _json_script_body(text: str) -> str:
    """``text`` as one JSON string literal that is safe as a ``<script>`` element's content.

    The HTML tokenizer ends a script element's content at the first ``</script`` it meets and
    changes state at ``<!--`` and ``<script``, whatever the element's ``type``. Every ``<`` in
    the literal is therefore written as its JSON escape ``\\u003c`` — the literal then contains
    no ``<`` at all, so no sequence the tokenizer acts on can arise, and ``JSON.parse`` (or
    ``json.loads``) returns the text byte for byte. Everything else, non-ASCII included, is
    kept verbatim: the page is UTF-8 and the guide keeps non-ASCII label text verbatim (§2.4).
    """
    return json.dumps(text, ensure_ascii=False).replace("<", "\\u003c")


def render_html(
    ir: WorkflowIR, *, report: RunReport | None = None, source: str | None = None
) -> str:
    """The subject's diagram as one HTML document that renders it when opened (CLI-SPEC §4.4).

    One file carrying the whole text; the renderer, mermaid.js, is fetched from a CDN by the
    browser that opens the page, so viewing needs the CDN reachable at view time.

    Args:
        ir: The workflow definition to draw.
        report: A run report whose findings are painted onto the drawing (guide §4), passed
            through to :func:`~gebra.display.render_mermaid` unchanged — the §4.1 pairing
            checks run there.
        source: The CLI-SPEC §2.1 subject label. It becomes the page's ``<title>`` and
            heading, and the text's own ``%% subject:`` header line, when given.

    Returns:
        A complete HTML5 document, every line ``\\n``-terminated: the Mermaid text
        :func:`~gebra.display.render_mermaid` produces for the same arguments, embedded as a
        JSON string literal (byte-exact recovery) and as a ``<noscript>`` fallback, plus the
        one module script that renders it with the pinned mermaid release at view time.

    Raises:
        gebra.ir.CanonicalizationError: on the overlay path only, as the text renderer.
        gebra.display.OverlayPairingError: when ``report`` fails the §4.1 pairing checks.
    """
    text = render_mermaid(ir, report=report, source=source)
    title = html.escape(UNTITLED if source is None else source, quote=False)
    embedded = f'<script type="application/json" id="{_DIAGRAM_ELEMENT_ID}">'
    embedded += f"{_json_script_body(text)}</script>"
    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title>",
        "<style>",
        *_STYLE_LINES,
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{title}</h1>",
        f'<div id="{_VIEW_ELEMENT_ID}"></div>',
        "<noscript>",
        f"<pre>{html.escape(text, quote=False)}</pre>",
        "</noscript>",
        embedded,
        '<script type="module">',
        *_MODULE_SCRIPT_LINES,
        "</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(lines) + "\n"
