"""Mermaid rendering of the Gebra IR — ``docs/specs/DIAGRAM-STYLE-GUIDE.md``, as built.

The presentation package behind ``gebra display`` (CLI-SPEC §4.4). PD-034 (CLI-D2,
ratified) fixes the strategy: Mermaid is emitted **directly from the ``WorkflowIR``** by
this gebra-owned emitter — no dependency on ``get_graph()`` or ``draw_mermaid()`` anywhere
on this path — with a run report's findings painted on as an overlay per the style guide.
Presentation only (CLI-SPEC §0.1): nothing here reaches a verdict, recomputes a structural
fact, or executes anything (WA-07); the one comparison made is the guide §4.1 provenance
check — two digests, string-compared.

Surface::

    from gebra.display import render_html, render_mermaid
    text = render_mermaid(ir)                     # topology only
    text = render_mermaid(ir, report=run_report)  # with the findings overlay
    page = render_html(ir, report=run_report)     # the same text, in one HTML page that renders it

``render_html`` (card REL-05) is a wrapper and nothing more: the page carries the exact text
``render_mermaid`` produces for the same arguments and loads mermaid.js from a CDN at view
time, so the drawing rules stay the guide's and the package gains no runtime dependency.
"""

from gebra.display.html import MERMAID_VERSION, render_html
from gebra.display.mermaid import mermaid_label, mermaid_vertex_id, render_mermaid
from gebra.display.overlay import OverlayPairingError

__all__ = [
    "MERMAID_VERSION",
    "OverlayPairingError",
    "mermaid_label",
    "mermaid_vertex_id",
    "render_html",
    "render_mermaid",
]
