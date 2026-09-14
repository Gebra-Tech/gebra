"""The Mermaid emitter — DIAGRAM-STYLE-GUIDE §1–§3 and §5, assembled in one pass.

PD-034 (CLI-D2, ratified) fixes the strategy this module implements: the diagram is emitted
**directly from the ``WorkflowIR``** — no ``get_graph()``, no ``draw_mermaid()``, nothing
from the substrate anywhere on this path. The drawn graph is the sentinel-augmented,
label-expanded multigraph of :func:`gebra.verify.graph.build_graph_model`, with unresolved
references carried as dashed phantom vertices (guide §3.1–§3.2) — the same §2.4 expansion
every graph-algorithm consumer applies, so the picture and the findings painted onto it
speak one vocabulary.

The emitter draws; it decides nothing. It runs none of the model's analyses. A
``dynamic``-bearing document (ir 1.1 — DEC-28) draws like any other since CLI-11 (PD-060):
the headless router edge is **carried on its source**, exactly as PD-059 D1 carries it in the
topology diff — a ``[Dn]`` marker on the source vertex and a rendered dispatch note (guide
§3.3) — because an arrow needs a head and any head here would name a vertex the document
declares nowhere, not even as a reference (the guide's §3.2 draws *declared* references and
nothing else; DEC-26 §3 closed the same class one surface over, for report evidence), and
would imply the target set DEC-28's kind exists to deny. No consumer in
this package declines the document now, and none imports the 1.0-vocabulary decline helper
``gebra.ir`` still exports for consumers outside it.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from gebra.display.overlay import Overlay, build_overlay, check_pairing
from gebra.ir import DynamicEdge, WorkflowIR, graph_version
from gebra.verify.base import Severity, to_display
from gebra.verify.graph import END_VERTEX, START_VERTEX, GraphModel, build_graph_model
from gebra.verify.run import RunReport

__all__ = ["mermaid_label", "mermaid_vertex_id", "render_mermaid"]

#: The one drawing header of guide §1.1.
_HEADER: Final = "flowchart TD"

#: The §5 class declarations, in their fixed emission order; only used classes are emitted.
_CLASS_DEFS: Final[tuple[tuple[str, str], ...]] = (
    ("gebra_fatal", "fill:#dc2626,stroke:#7f1d1d,color:#ffffff"),
    ("gebra_error", "fill:#fecaca,stroke:#dc2626,color:#7f1d1d"),
    ("gebra_warning", "fill:#fef3c7,stroke:#d97706,color:#78350f"),
    ("gebra_sentinel", "fill:#f3f4f6,stroke:#374151,color:#111827"),
    ("gebra_unresolved", "fill:#f9fafb,stroke:#6b7280,stroke-dasharray: 4 3,color:#374151"),
    ("gebra_info", "fill:#f3f4f6,stroke:#6b7280,color:#111827"),
)

#: Severity → node class name (§5).
_SEVERITY_CLASS: Final[dict[Severity, str]] = {
    "fatal": "gebra_fatal",
    "error": "gebra_error",
    "warning": "gebra_warning",
}

#: Severity → link paint (§5).
_LINK_STYLE: Final[dict[Severity, str]] = {
    "fatal": "stroke:#7f1d1d,stroke-width:3px",
    "error": "stroke:#dc2626,stroke-width:2px",
    "warning": "stroke:#d97706,stroke-width:2px",
}

_KEEP: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")


def mermaid_vertex_id(vertex: str) -> str:
    """The Mermaid id of a model vertex — guide §2.1's deterministic, injective mapping.

    Sentinels take the fixed ids ``START``/``END``; every other vertex is ``n_`` + its
    escape: characters in ``[A-Za-z0-9]`` kept, every other character replaced by ``_``
    plus two lowercase hex digits per UTF-8 byte (so ``_`` itself becomes ``_5f``, and the
    escape is prefix-free, hence injective).
    """
    if vertex == START_VERTEX:
        return "START"
    if vertex == END_VERTEX:
        return "END"
    escaped: list[str] = []
    for char in vertex:
        if char in _KEEP:
            escaped.append(char)
        else:
            escaped.extend(f"_{byte:02x}" for byte in char.encode("utf-8"))
    return "n_" + "".join(escaped)


def mermaid_label(text: str) -> str:
    """``text`` under the guide §2.4 escape rules, ready to sit inside a quoted label.

    Exactly five rules, each to a Mermaid decimal entity: ``#`` → ``#35;``, ``"`` →
    ``#34;``, ``<`` → ``#60;``, ``>`` → ``#62;``, and control characters → ``#<dec>;``.
    Everything else — non-ASCII included — is kept verbatim.
    """
    escaped: list[str] = []
    for char in text:
        if char in {"#", '"', "<", ">"} or ord(char) < 0x20 or ord(char) == 0x7F:
            escaped.append(f"#{ord(char)};")
        else:
            escaped.append(char)
    return "".join(escaped)


@dataclass(frozen=True)
class _DispatchNote:
    """One rendered dispatch note — guide §3.3's form for a headless router edge.

    A ``dynamic`` edge contributes no member to $G$ (its targets are Runtime-only —
    PROPERTY-CATALOG-SPEC §0.3) and so none to the drawn multigraph, which is that model plus
    §3.2's carried references. There is therefore no arrow to draw and no head to invent: the
    fact is carried on the edge's *source* instead, as this note and the ``[Dn]`` marker its
    :attr:`marker` puts on that source's label.

    Attributes:
        index: The note number, ``1``-based, in the order the sources first appear in
            ``ir.edges``.
        source: The ``from`` string the document declares, byte-for-byte — the same text the
            source's own label carries when it is drawn.
        routers: How many ``dynamic`` edges this source declares (two hintless routers on one
            node are two, as two parallel static edges are two arrows).
        marked: Whether a vertex of the drawing carries this note's marker. False when the
            model resolved the source to nothing and did not carry it — a reserved-segment
            spelling, which (m5) never materializes (guide §3.1). Deliberately *not* "the
            source is drawn": for a ``from`` spelling ``__start__`` a stadium labelled START
            is on the picture, and it is the sentinel, not this reference.
    """

    index: int
    source: str
    routers: int
    marked: bool

    @property
    def marker(self) -> str:
        """``D1`` — the label marker, in the same bracket block the ``[Fn]`` markers ride."""
        return f"D{self.index}"

    @property
    def text(self) -> str:
        """The note's one line (guide §3.3), unescaped — the assembly applies §2.4."""
        routers = "1 dynamic router" if self.routers == 1 else f"{self.routers} dynamic routers"
        line = (
            f"{self.marker} dynamic dispatch - {self.source}: {routers}, targets not "
            "statically known, so no arrow is drawn"
        )
        if not self.marked:
            line += " - no vertex carries this marker"
        return line


def _dispatch_notes(ir: WorkflowIR, model: GraphModel) -> tuple[_DispatchNote, ...]:
    """One note per source declaring a ``dynamic`` edge, in first-authored order (§3.3).

    Grouped per source rather than per edge because the drawn form is an annotation on a
    vertex: two routers on one node mark that node once and are counted on its one note.

    Markability is the **drawing's** own membership question — is this ``from`` string a
    declared node or a carried reference (§3.2's two markable vertex classes)? — and is asked
    that way rather than through
    :attr:`~gebra.verify.graph.GraphModel.dynamic_sources`, which answers §0.3's *participation*
    question. The two sets coincide on these sources today, by the builder's own construction,
    and a reserved-segment spelling is outside both: it is never a node id (IR-SPEC §5.1) and
    never carried, so (m5) leaves no vertex to mark.
    """
    routers: dict[str, int] = {}
    for edge in ir.edges:
        if isinstance(edge, DynamicEdge):
            routers[edge.from_] = routers.get(edge.from_, 0) + 1
    markable = model.node_ids | model.carried
    return tuple(
        _DispatchNote(index=index, source=source, routers=count, marked=source in markable)
        for index, (source, count) in enumerate(routers.items(), start=1)
    )


def _vertex_order(ir: WorkflowIR, model: GraphModel) -> tuple[str, ...]:
    """Guide §3.2's definition order: START, declared nodes as authored, phantoms, END."""
    carried_in_order: list[str] = []
    seen: set[str] = set()
    for record in model.unresolved:
        reference = record.reference
        if reference in model.carried and reference not in seen:
            carried_in_order.append(reference)
            seen.add(reference)
    return (
        START_VERTEX,
        *(node.id for node in ir.nodes),
        *carried_in_order,
        END_VERTEX,
    )


def _marker_suffix(markers: tuple[str, ...]) -> str:
    """`` [F1 F3]`` — the guide §4.4 marker block, or the empty string."""
    return f" [{' '.join(markers)}]" if markers else ""


def _node_line(vertex: str, dispatch: str | None, overlay: Overlay | None) -> str:
    """One node definition line, marker suffix included (guide §3.2, §3.3, §4.4).

    The two marker families share one bracket block, §3's dispatch marker first and the §4
    finding markers after it — ``plan [D1 F2]`` — so a reader meets the topology fact before
    the overlay's.
    """
    diagram_id = mermaid_vertex_id(vertex)
    markers = [] if dispatch is None else [dispatch]
    if overlay is not None:
        markers.extend(overlay.vertex_markers.get(vertex, ()))
    label = mermaid_label(to_display(vertex) + _marker_suffix(tuple(markers)))
    if vertex in (START_VERTEX, END_VERTEX):
        return f'  {diagram_id}(["{label}"])'
    return f'  {diagram_id}["{label}"]'


def _edge_line(source: str, target: str, kind: str, label: str | None) -> str:
    """One edge line in the guide §3.3 arrow vocabulary."""
    arrow = "-.->" if kind == "send" else "-->"
    tail, head = mermaid_vertex_id(source), mermaid_vertex_id(target)
    if label is None:
        return f"  {tail} {arrow} {head}"
    return f'  {tail} {arrow}|"{mermaid_label(label)}"| {head}'


def render_mermaid(
    ir: WorkflowIR, *, report: RunReport | None = None, source: str | None = None
) -> str:
    """The subject's topology as Mermaid text, per DIAGRAM-STYLE-GUIDE.

    Args:
        ir: The workflow definition to draw.
        report: A run report whose findings are painted onto the drawing (guide §4). It
            must be a report **about this IR**: the §4.1 pairing checks run first.
        source: The CLI-SPEC §2.1 subject label for the header comment, when the caller
            has one.

    Returns:
        The complete artifact, every line ``\\n``-terminated (guide §1.4).

    Raises:
        gebra.ir.CanonicalizationError: on the overlay path only, when the displayed IR
            has no §6 digest for the §4.1 provenance check to compare.
        gebra.display.OverlayPairingError: when ``report`` fails the §4.1 pairing checks.
    """
    model = build_graph_model(ir, carry_unresolved_references=True)
    notes = _dispatch_notes(ir, model)
    dispatch = {note.source: note.marker for note in notes if note.marked}
    overlay: Overlay | None = None
    if report is not None:
        digest = graph_version(ir)
        check_pairing(digest, report)
        overlay = build_overlay(model, report, digest=digest)

    lines: list[str] = [
        "%% gebra display: workflow definition as Mermaid (DIAGRAM-STYLE-GUIDE)",
    ]
    if source is not None:
        lines.append(f"%% subject: {source}")
    lines.append(f"%% ir_version: {ir.ir_version}")
    if overlay is not None:
        lines.extend(overlay.header_lines)
    lines.append(_HEADER)

    vertices = _vertex_order(ir, model)
    lines.append("")
    lines.extend(_node_line(vertex, dispatch.get(vertex), overlay) for vertex in vertices)

    if model.edges:
        lines.append("")
        for index, edge in enumerate(model.edges):
            markers = overlay.link_markers.get(index, ()) if overlay is not None else ()
            suffix = _marker_suffix(tuple(markers))
            label: str | None
            if edge.label is not None:
                label = edge.label + suffix
            elif suffix:
                label = suffix.lstrip(" ")
            else:
                label = None
            lines.append(_edge_line(edge.source, edge.target, edge.kind, label))

    if notes:
        lines.append("")
        lines.append('  subgraph gebra_dynamic["gebra dynamic dispatch"]')
        lines.extend(f'    d_{note.index}["{mermaid_label(note.text)}"]' for note in notes)
        lines.append("  end")

    if overlay is not None:
        lines.append("")
        lines.append('  subgraph gebra_findings["gebra findings overlay"]')
        for entry in overlay.legend:
            label_text = mermaid_label(entry.text)
            lines.append(f'    f_{entry.index}["{label_text}"]')
        lines.append("  end")

    lines.append("")
    lines.extend(_style_lines(vertices, model, notes, overlay))
    return "\n".join(lines) + "\n"


def _style_lines(
    vertices: tuple[str, ...],
    model: GraphModel,
    notes: tuple[_DispatchNote, ...],
    overlay: Overlay | None,
) -> list[str]:
    """The guide §5 style block: used classDefs, class assignments, linkStyle paints."""
    members: dict[str, list[str]] = {}
    members["gebra_sentinel"] = ["START", "END"]
    if model.carried:
        members["gebra_unresolved"] = [
            mermaid_vertex_id(vertex) for vertex in vertices if vertex in model.carried
        ]
    if notes:
        # Chrome, like the §4.3 statement entry: a dispatch note states a fact about the
        # definition and grades nothing. The source vertex itself takes no class here — the
        # node-fill channel stays §4.4's severity channel (§3.3).
        members.setdefault("gebra_info", []).extend(f"d_{note.index}" for note in notes)
    if overlay is not None:
        for vertex in vertices:
            severity = overlay.vertex_severity.get(vertex)
            if severity is not None:
                members.setdefault(_SEVERITY_CLASS[severity], []).append(mermaid_vertex_id(vertex))
        for entry in overlay.legend:
            name = _SEVERITY_CLASS[entry.severity] if entry.severity is not None else "gebra_info"
            members.setdefault(name, []).append(f"f_{entry.index}")

    lines = [
        f"  classDef {name} {declarations}" for name, declarations in _CLASS_DEFS if name in members
    ]
    lines.extend(
        f"  class {','.join(ids)} {name}" for name, _ in _CLASS_DEFS if (ids := members.get(name))
    )
    if overlay is not None:
        lines.extend(
            f"  linkStyle {index} {_LINK_STYLE[overlay.link_severity[index]]}"
            for index in sorted(overlay.link_severity)
        )
    return lines
