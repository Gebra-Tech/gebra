"""The verification overlay — DIAGRAM-STYLE-GUIDE §4, as a paint plan over the graph model.

This module turns a :class:`~gebra.verify.run.RunReport` into everything the Mermaid
assembly needs to paint it: which vertices and links take which severity style, which
``[Fn]`` markers ride which labels, and the legend entries that carry every finding's own
severity, claim class, condition ID and §4.5 anchor phrase. The walk is
:func:`gebra.report.findings.findings_of` — REPORT-FORMAT-SPEC §2.1's traversal, the same
one the terminal renderer uses — so the diagram and the report beside it paint the same
records (guide §4.2).

Nothing here reaches a verdict or recomputes a structural fact: the finding set, each
record's grade and class, and the gate facts quoted into the header lines are the report's
own (CLI-SPEC §0.1). The one comparison made is :func:`check_pairing`'s string-compare of
two digests — the guide §4.1 provenance check, never a verdict.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from gebra.report.anchors import location_phrase
from gebra.report.findings import Finding, findings_of
from gebra.verify.base import Severity
from gebra.verify.graph import END_VERTEX, START_VERTEX, GraphModel
from gebra.verify.locations import (
    CycleLocation,
    EdgeLocation,
    NodeLocation,
    P01EdgeLocation,
    PathLocation,
    SccLocation,
    StateKeyLocation,
)
from gebra.verify.report import PropertyReport
from gebra.verify.run import GateOutcome, RunReport, ToolError

__all__ = ["LegendEntry", "Overlay", "OverlayPairingError", "build_overlay", "check_pairing"]

#: fatal outranks error outranks warning where two findings paint one element (guide §4.4).
_SEVERITY_RANK: Final[dict[Severity, int]] = {"fatal": 0, "error": 1, "warning": 2}


class OverlayPairingError(ValueError):
    """The report cannot be painted onto this IR — the guide §4.1 pairing checks failed."""


def check_pairing(digest: str, report: RunReport) -> None:
    """The guide §4.1 provenance checks: the report must name its own graph, and this one.

    Args:
        digest: The displayed IR's own IR-SPEC §6 ``graph_version``.
        report: The loaded run report.

    Raises:
        OverlayPairingError: when the report carries no subject (a tool error preceded IR
            identity, so there is no recorded digest to check and nothing to paint), or
            when its recorded ``subject.graph_version`` differs from ``digest``.
    """
    if report.subject is None:
        stage = report.error.stage if report.error is not None else "unknown"
        raise OverlayPairingError(
            f"the report carries no subject (a tool error at stage {stage!r} preceded IR "
            "identity), so it names no graph_version to check against the displayed IR "
            "and holds no findings to paint (CLI-SPEC §4.4)"
        )
    if report.subject.graph_version != digest:
        raise OverlayPairingError(
            f"the report's subject.graph_version {report.subject.graph_version} differs "
            f"from the displayed IR's digest {digest}: painting one workflow's findings "
            "onto another's topology would be a false statement about both (CLI-SPEC §4.4)"
        )


@dataclass(frozen=True)
class LegendEntry:
    """One rendered legend node (guide §4.3).

    Attributes:
        index: The finding number, or ``0`` for the zero-findings statement entry.
        text: The label text, unescaped — the assembly applies the §2.4 escapes.
        severity: The finding's own grade; ``None`` styles the entry as chrome
            (``gebra_info``).
    """

    index: int
    text: str
    severity: Severity | None


@dataclass(frozen=True)
class Overlay:
    """Everything the assembly paints for one accepted report (guide §4).

    Attributes:
        header_lines: The ``%% overlay:`` header comments — the report's own facts, quoted.
        vertex_severity: Vertex → the highest-ranked severity anchored at it.
        vertex_markers: Vertex → the ``Fn`` markers its label carries, in finding order.
        link_severity: Link index → the highest-ranked severity painted along it.
        link_markers: Link index → the ``Fn`` markers its label carries, in finding order.
        legend: Every finding, exactly once, in finding order — or the single statement
            entry when the report holds no findings.
    """

    header_lines: tuple[str, ...]
    vertex_severity: Mapping[str, Severity]
    vertex_markers: Mapping[str, tuple[str, ...]]
    link_severity: Mapping[int, Severity]
    link_markers: Mapping[int, tuple[str, ...]]
    legend: tuple[LegendEntry, ...]


def _elide(digest: str) -> str:
    """A digest prefix that reads as a prefix — the CLI surfaces' own elision (§5.1 rule 1)."""
    algorithm, _, hex_part = digest.partition(":")
    if len(hex_part) <= 16:
        return digest
    return f"{algorithm}:{hex_part[:16]}..."


def _header_lines(report: RunReport, digest: str) -> tuple[str, ...]:
    """The guide §4.1 ``%% overlay:`` lines — every value the report's own, quoted."""
    gate = report.gate
    lines = [
        (
            f"%% overlay: run report for graph_version {_elide(digest)} - "
            f"gate: {gate.outcome} (exit {gate.exit_code})"
        ),
        (
            f"%% overlay counts: fatal {gate.counts.fatal}, error {gate.counts.error}, "
            f"warning {gate.counts.warning}"
        ),
    ]
    if gate.strict.mode == "all":
        lines.append("%% overlay strict: all")
    elif gate.strict.mode == "per-property":
        lines.append(f"%% overlay strict: per-property ({', '.join(gate.strict.properties)})")
    if gate.promotions:
        count = len(gate.promotions)
        lines.append(
            f"%% overlay promotions: {count} warning-grade record(s) promoted at the gate; "
            "promotion moves the gate, never the record"
        )
    if report.best_effort:
        lines.append(
            f"%% overlay best-effort: {', '.join(report.best_effort)} - these outcomes are "
            "best-effort diagnostics, not contract-bearing verdicts"
        )
    return tuple(lines)


class _Painter:
    """Accumulates paints, keeping the highest severity per element (guide §4.4)."""

    def __init__(self) -> None:
        self.vertex_severity: dict[str, Severity] = {}
        self.vertex_markers: dict[str, list[str]] = {}
        self.link_severity: dict[int, Severity] = {}
        self.link_markers: dict[int, list[str]] = {}

    def paint_vertex(self, vertex: str, severity: Severity, marker: str) -> None:
        current = self.vertex_severity.get(vertex)
        if current is None or _SEVERITY_RANK[severity] < _SEVERITY_RANK[current]:
            self.vertex_severity[vertex] = severity
        self.vertex_markers.setdefault(vertex, []).append(marker)

    def paint_link(self, index: int, severity: Severity, marker: str) -> None:
        current = self.link_severity.get(index)
        if current is None or _SEVERITY_RANK[severity] < _SEVERITY_RANK[current]:
            self.link_severity[index] = severity
        self.link_markers.setdefault(index, []).append(marker)


class _Resolver:
    """Report-side references onto model vertices and links (guide §4.4's fixed rules)."""

    def __init__(self, model: GraphModel) -> None:
        self._model = model
        self._pair_links: dict[tuple[str, str], list[int]] = {}
        self._labeled_links: dict[tuple[str, str, str], list[int]] = {}
        for index, edge in enumerate(model.edges):
            self._pair_links.setdefault((edge.source, edge.target), []).append(index)
            if edge.label is not None:
                key = (edge.source, edge.target, edge.label)
                self._labeled_links.setdefault(key, []).append(index)

    def vertex(self, reference: str) -> str | None:
        """A report-side node reference as a model vertex, or ``None`` when not drawn.

        The declared node of that exact id wins; then the display sentinels; then a
        carried reference vertex (guide §4.4: the only deterministic reading of the
        serialized form, per ``from_display``'s own caveat).
        """
        if reference in self._model.node_ids:
            return reference
        if reference == "START":
            return START_VERTEX
        if reference == "END":
            return END_VERTEX
        return self.carried_vertex(reference)

    def carried_vertex(self, reference: str) -> str | None:
        """The phantom vertex drawn for ``reference``, or ``None`` — verbatim, no projection."""
        return reference if reference in self._model.carried else None

    def links_between(self, source: str, target: str, label: str | None) -> tuple[int, ...]:
        """Every link drawn between two vertices — all parallels; a label narrows (§4.4)."""
        if label is not None:
            return tuple(self._labeled_links.get((source, target, label), ()))
        return tuple(self._pair_links.get((source, target), ()))

    def links_along(self, references: Iterable[str], *, close: bool) -> tuple[int, ...]:
        """The member link set of a recorded node sequence — cycle (closed) or path."""
        resolved = [self.vertex(reference) for reference in references]
        pairs = list(pairwise(resolved))
        if close and len(resolved) > 0:
            pairs.append((resolved[-1], resolved[0]))
        links: list[int] = []
        for tail, head in pairs:
            if tail is None or head is None:
                continue
            links.extend(self.links_between(tail, head, None))
        return tuple(links)

    def links_within(self, references: Iterable[str]) -> tuple[int, ...]:
        """Every link with both endpoints in a member set — the SCC paint (guide §4.4)."""
        members = {vertex for r in references if (vertex := self.vertex(r)) is not None}
        return tuple(
            index
            for index, edge in enumerate(self._model.edges)
            if edge.source in members and edge.target in members
        )


def _paint_finding(finding: Finding, marker: str, resolver: _Resolver, painter: _Painter) -> bool:
    """Apply the guide §4.4 paint for one finding; report whether anything was drawn."""
    location = finding.location
    severity = finding.severity
    if isinstance(location, EdgeLocation):
        source = resolver.vertex(location.source)
        if location.target is not None:
            target = resolver.vertex(location.target)
        elif isinstance(location, P01EdgeLocation):
            # A dangling anchor's reference is verbatim, never a display projection: it is
            # drawn iff the model carried it as a phantom vertex (guide §3.2, §4.4).
            target = resolver.carried_vertex(location.undefined_target)
        else:
            target = None
        if source is None or target is None:
            return False
        links = resolver.links_between(source, target, location.label)
        for index in links:
            painter.paint_link(index, severity, marker)
        return bool(links)
    if isinstance(location, CycleLocation):
        links = resolver.links_along(location.nodes, close=True)
        for index in links:
            painter.paint_link(index, severity, marker)
        return bool(links)
    if isinstance(location, SccLocation):
        links = resolver.links_within(location.nodes)
        for index in links:
            painter.paint_link(index, severity, marker)
        return bool(links)
    if isinstance(location, PathLocation):
        links = resolver.links_along(location.nodes, close=False)
        for index in links:
            painter.paint_link(index, severity, marker)
        return bool(links)
    if isinstance(location, StateKeyLocation):
        if location.node is None:
            return False
        vertex = resolver.vertex(location.node)
        if vertex is None:
            return False
        painter.paint_vertex(vertex, severity, marker)
        return True
    if isinstance(location, NodeLocation):
        vertex = resolver.vertex(location.node)
        if vertex is None:
            return False
        painter.paint_vertex(vertex, severity, marker)
        return True
    raise AssertionError(f"no §4.4 paint rule for {type(location).__name__}")


def _statement_entry(gate: GateOutcome, error: ToolError | None) -> LegendEntry:
    """The zero-findings legend entry — the gate's own outcome, stated, never a badge."""
    if gate.outcome == "tool-error":
        stage = error.stage if error is not None else "unknown"
        text = f"no verdict was reached (stage: {stage}) - nothing to paint"
    elif gate.outcome == "fail":
        text = (
            "no findings to paint - gate: fail (exit 1); the gate was moved by promotion "
            "(see the run report)"
        )
    elif gate.outcome == "pass-with-notes":
        text = (
            "no findings to paint - gate: pass-with-notes (exit 0); warning-grade notes "
            "are in the run report"
        )
    else:
        text = (
            "no findings to paint - gate: pass (exit 0); per-property claim classes are "
            "in the run report"
        )
    return LegendEntry(index=0, text=text, severity=None)


def build_overlay(model: GraphModel, report: RunReport, *, digest: str) -> Overlay:
    """The paint plan for ``report`` over ``model`` — guide §4.2–§4.5.

    ``report`` must already have passed :func:`check_pairing` against the model's own IR;
    this function trusts the pairing and only resolves anchors.
    """
    resolver = _Resolver(model)
    painter = _Painter()
    legend: list[LegendEntry] = []
    index = 0
    for outcome in report.properties:
        if not isinstance(outcome, PropertyReport):
            continue  # a not-implemented marker holds no findings (guide §4.2)
        for finding in findings_of(outcome):
            index += 1
            marker = f"F{index}"
            drawn = _paint_finding(finding, marker, resolver, painter)
            text = (
                f"{marker} {finding.severity} [{finding.claim_class}] "
                f"{finding.property_condition} - {location_phrase(finding.location)}"
            )
            if finding.owner in report.best_effort:
                text += " (best-effort)"
            if not drawn:
                text += " - not drawn in this diagram"
            legend.append(LegendEntry(index=index, text=text, severity=finding.severity))
    if not legend:
        legend.append(_statement_entry(report.gate, report.error))
    return Overlay(
        header_lines=_header_lines(report, digest),
        vertex_severity=painter.vertex_severity,
        vertex_markers={k: tuple(v) for k, v in painter.vertex_markers.items()},
        link_severity=painter.link_severity,
        link_markers={k: tuple(v) for k, v in painter.link_markers.items()},
        legend=tuple(legend),
    )
