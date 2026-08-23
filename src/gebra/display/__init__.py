"""Mermaid rendering of the Gebra IR — ``docs/specs/DIAGRAM-STYLE-GUIDE.md``, as built.

The presentation package behind ``gebra display`` (CLI-SPEC §4.4). PD-034 (CLI-D2,
ratified) fixes the strategy: Mermaid is emitted **directly from the ``WorkflowIR``** by
this gebra-owned emitter — no dependency on ``get_graph()`` or ``draw_mermaid()`` anywhere
on this path — with a run report's findings painted on as an overlay per the style guide.
Presentation only (CLI-SPEC §0.1): nothing here reaches a verdict, recomputes a structural
fact, or executes anything (WA-07); the one comparison made is the guide §4.1 provenance
check — two digests, string-compared.

Surface::

    from gebra.display import render_mermaid
    text = render_mermaid(ir)                     # topology only
    text = render_mermaid(ir, report=run_report)  # with the findings overlay
"""

from gebra.display.mermaid import mermaid_label, mermaid_vertex_id, render_mermaid
from gebra.display.overlay import OverlayPairingError

__all__ = [
    "OverlayPairingError",
    "mermaid_label",
    "mermaid_vertex_id",
    "render_mermaid",
]
