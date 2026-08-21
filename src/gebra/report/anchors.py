"""Structural anchors, rendered — REPORT-FORMAT-SPEC §4.5, once, for every surface.

§4.5 states each location variant twice: the facts a human rendering must carry, and the
SARIF ``logicalLocations[0]`` it projects to. Both readings live here so the two surfaces
cannot drift: :func:`location_lines` is the human column, :func:`logical_anchor` is the SARIF
one, and :func:`location_phrase` is the one-line form ``message.text`` front-loads (A.4).

Node ids are rendered byte-for-byte in the frozen IR-SPEC §5 grammar, and the display
sentinels ``START``/``END`` appear exactly where the envelope carries them — the reserved
spellings ``__start__``/``__end__`` are refused by the envelope's own ``NodeId`` annotation,
so they cannot reach this module.

**Two readings this module fixes, both recorded in §4.5 rather than invented here.**

1. The edge FQN's ``#<kind>`` segment. ``EdgeLocation`` carries no ledger edge kind, only the
   ``label`` that says whether the anchor is one label-expansion of a conditional edge. So the
   segment reports what the anchor carries: ``conditional`` when a label is present,
   ``normal`` otherwise. It is not a re-derived IR fact, and the ledger's third kind
   (``send``) is not distinguishable from an edge anchor at all.
2. The state-key FQN. PROPERTY-CATALOG-SPEC Appendix C spells it ``state:<SchemaName>.<key>``,
   but IR 1.0's Σ is a **nameless mapping** (IR-SPEC §2.2: ``state`` is key → type) and the
   §0.3 envelope carries no schema identity either, so no producer can fill ``<SchemaName>``.
   The projection emits ``state:<key>``, which is deterministic and derived only from the
   record — the disposition A.5 already takes for the physical anchor, recorded as
   REPORT-FORMAT-SPEC Appendix B OI-8.

One consequence of (2) is worth stating rather than discovering: two P-04 findings that read
the same Σ key on different paths share an FQN, hence share ``gebraConditionHash/v1`` (A.6).
That follows from the frozen mapping, which keys the anchor on the key alone; the full
evidence stays in the native report, where the two findings are separate records.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from gebra.verify.locations import (
    AnyLocation,
    CycleLocation,
    DataflowLocation,
    DeterminismNodeLocation,
    EdgeLocation,
    NodeLocation,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
    P06NodeLocation,
    PathLocation,
    SccLocation,
    StateKeyLocation,
)

__all__ = [
    "LogicalAnchor",
    "location_evidence",
    "location_lines",
    "location_phrase",
    "logical_anchor",
]

#: The SARIF ``logicalLocation.kind`` per §0.3 anchor discriminator (§4.5). ``function`` and
#: ``variable`` are SARIF's own suggested kinds; ``edge``, ``cycle``, ``scc`` and ``path`` are
#: custom strings, which Appendix C notes are spec-legal ("no suggested SARIF kind fits an
#: edge").
_LOGICAL_KIND: Final[dict[str, str]] = {
    "node": "function",
    "edge": "edge",
    "cycle": "cycle",
    "scc": "scc",
    "state-key": "variable",
    "path": "path",
}


@dataclass(frozen=True)
class LogicalAnchor:
    """One location's SARIF projection (§4.5, A.5 rule 1: every result carries one)."""

    kind: str
    fully_qualified_name: str
    #: ``logicalLocation.name`` where the anchor has a single natural name; absent otherwise.
    name: str | None = None
    #: The FQNs of ``relatedLocations[]`` — one per path step, for the two path-carrying
    #: variants (§4.5: ``PathLocation`` and ``DataflowLocation``).
    related: tuple[str, ...] = ()


def _walk(nodes: tuple[str, ...]) -> str:
    """A path or cycle as a walk, for a person to read: ``a -> b -> c``."""
    return " -> ".join(nodes)


def _fqn_walk(nodes: tuple[str, ...]) -> str:
    """The same walk as an identifier: ``a->b->c``.

    Spaceless, because a fully qualified name is matched and fingerprinted rather than read
    (A.6), and because it is the separator Appendix C already writes into the edge FQN.
    """
    return "->".join(nodes)


def _closed_walk(nodes: tuple[str, ...]) -> str:
    """A cycle as a closed walk — the rotation, returning to its first node (§4.5)."""
    return _walk((*nodes, nodes[0])) if nodes else ""


def _edge_kind(location: EdgeLocation) -> str:
    """``conditional`` for a label-expansion, ``normal`` otherwise — see the module docstring."""
    return "conditional" if location.label is not None else "normal"


def _edge_fqn(location: EdgeLocation) -> str:
    """``edge:<src>-><dst>#<kind>[<label>]`` (§4.5).

    A dangling label carries no resolved target, so the target segment is omitted and the
    rest of the grammar is unchanged — which keeps a dangling anchor distinguishable from a
    resolved one instead of inventing an endpoint for it.
    """
    label = f"[{location.label}]" if location.label is not None else ""
    return f"edge:{location.source}->{location.target or ''}#{_edge_kind(location)}{label}"


def logical_anchor(location: AnyLocation) -> LogicalAnchor:
    """The SARIF ``logicalLocations[0]`` (and any ``relatedLocations[]``) for ``location``."""
    kind = _LOGICAL_KIND[location.kind]
    if isinstance(location, EdgeLocation):
        return LogicalAnchor(kind=kind, fully_qualified_name=_edge_fqn(location))
    if isinstance(location, CycleLocation):
        return LogicalAnchor(kind=kind, fully_qualified_name=f"cycle:{_fqn_walk(location.nodes)}")
    if isinstance(location, SccLocation):
        return LogicalAnchor(kind=kind, fully_qualified_name=f"scc:{','.join(location.nodes)}")
    if isinstance(location, DataflowLocation):
        return LogicalAnchor(
            kind=kind,
            fully_qualified_name=f"state:{location.key}",
            name=location.key,
            related=tuple(f"node:{node}" for node in location.path),
        )
    if isinstance(location, StateKeyLocation):
        return LogicalAnchor(
            kind=kind, fully_qualified_name=f"state:{location.key}", name=location.key
        )
    if isinstance(location, PathLocation):
        return LogicalAnchor(
            kind=kind,
            fully_qualified_name=f"path:{_fqn_walk(location.nodes)}",
            related=tuple(f"node:{node}" for node in location.nodes),
        )
    if isinstance(location, NodeLocation):
        return LogicalAnchor(
            kind=kind, fully_qualified_name=f"node:{location.node}", name=location.node
        )
    raise AssertionError(f"no §4.5 anchor projection for {type(location).__name__}")


def location_evidence(location: AnyLocation) -> dict[str, Any]:
    """The concrete subtype's evidence members, for ``result.properties`` (§4.5).

    An anchor carries none: the anchor's own fields are already in ``logicalLocations[0]``.
    Every key is namespaced ``gebra/…``, like A.4's own property-bag members, so a consumer
    never has to guess which producer wrote one.
    """
    evidence: dict[str, Any] = {}
    if isinstance(location, P01EdgeLocation):
        evidence["gebra/undefinedTarget"] = location.undefined_target
    elif isinstance(location, P02SccLocation):
        evidence["gebra/representativeCycle"] = list(location.representative_cycle)
        evidence["gebra/exhaustive"] = location.exhaustive
        if location.blanket_only is not None:
            evidence["gebra/blanketOnly"] = location.blanket_only
    elif isinstance(location, P02CycleLocation):
        evidence["gebra/counterKey"] = location.counter_key
        evidence["gebra/guardEdgeSource"] = location.guard_edge.source
        evidence["gebra/guardEdgeLabels"] = list(location.guard_edge.labels)
    elif isinstance(location, P06NodeLocation):
        evidence["gebra/effect"] = list(location.effect)
        if location.cycle is not None:
            evidence["gebra/cycle"] = list(location.cycle)
        if location.idempotent is not None:
            evidence["gebra/idempotent"] = location.idempotent
        if location.fanout is not None:
            evidence["gebra/fanout"] = location.fanout
        if location.dangling_compensation_hook is not None:
            evidence["gebra/danglingCompensationHook"] = location.dangling_compensation_hook
    elif isinstance(location, DeterminismNodeLocation):
        evidence["gebra/annotation"] = location.annotation
        if location.form is not None:
            evidence["gebra/form"] = location.form
        if location.effects is not None:
            evidence["gebra/effects"] = list(location.effects)
        if location.seed is not None:
            evidence["gebra/seed"] = location.seed
        if location.temperature is not None:
            evidence["gebra/temperature"] = location.temperature
    return evidence


def location_lines(location: AnyLocation) -> tuple[tuple[str, str], ...]:
    """The facts §4.5 requires a human rendering of ``location`` to carry, as label/value pairs.

    Every row of §4.5 is covered, anchors and concrete subtypes alike: a subtype's evidence
    members are shown beside the anchor's own, never instead of them.
    """
    lines: list[tuple[str, str]] = []
    if isinstance(location, EdgeLocation):
        target = location.target if location.target is not None else "(unresolved)"
        lines.append(("edge", f"{location.source} -> {target}"))
        if location.label is not None:
            lines.append(("label", location.label))
        if location.target is None:
            lines.append(("target", "unresolved — this label names no node"))
        if isinstance(location, P01EdgeLocation):
            lines.append(("undefined target", location.undefined_target))
    elif isinstance(location, CycleLocation):
        lines.append(("cycle", _closed_walk(location.nodes)))
        if isinstance(location, P02CycleLocation):
            lines.append(("counter key", location.counter_key))
            labels = ", ".join(location.guard_edge.labels) or "(no labels)"
            lines.append(("guard edge", f"{location.guard_edge.source} on {labels}"))
    elif isinstance(location, SccLocation):
        lines.append(("component", ", ".join(location.nodes)))
        if isinstance(location, P02SccLocation):
            lines.append(("representative", _closed_walk(location.representative_cycle)))
            lines.append(
                ("cycle list", "not exhaustive — a re-run after a fix may surface another")
            )
            if location.blanket_only:
                lines.append(
                    ("cover", "only the graph-level recursion_limit covers this component")
                )
    elif isinstance(location, StateKeyLocation):
        lines.append(("state key", location.key))
        if isinstance(location, DataflowLocation):
            lines.append(("reading node", location.node))
            lines.append(("shortest path", _walk(location.path)))
        elif location.node is not None:
            lines.append(("node", location.node))
    elif isinstance(location, PathLocation):
        lines.append(("path", _walk(location.nodes)))
    elif isinstance(location, NodeLocation):
        lines.append(("node", location.node))
        if isinstance(location, P06NodeLocation):
            lines.append(("declared effects", ", ".join(location.effect) or "(none)"))
            if location.cycle is not None:
                lines.append(("anchor cycle", _closed_walk(location.cycle)))
            if location.idempotent is not None:
                lines.append(("idempotent", location.idempotent))
            if location.fanout is not None:
                lines.append(("fan-out", location.fanout))
            if location.dangling_compensation_hook is not None:
                lines.append(
                    (
                        "compensation hook",
                        f"{location.dangling_compensation_hook} — names no node",
                    )
                )
        elif isinstance(location, DeterminismNodeLocation):
            declared = [f"annotation {location.annotation}"]
            if location.form is not None:
                declared.append(f"form {location.form}")
            if location.effects is not None:
                declared.append(f"effects {', '.join(location.effects) or '(none)'}")
            if location.seed is not None:
                declared.append(f"seed {location.seed}")
            if location.temperature is not None:
                declared.append(f"temperature {location.temperature}")
            lines.append(("declared", " | ".join(declared)))
    else:  # pragma: no cover - the union is closed and every member is handled above
        raise TypeError(f"no §4.5 rendering for {type(location).__name__}")
    return tuple(lines)


def location_phrase(location: AnyLocation) -> str:
    """A one-line anchor phrase — what ``message.text`` names as *where* (A.4).

    Deliberately the anchor and nothing more: the concrete subtype's evidence rides
    ``result.properties`` (:func:`location_evidence`), and A.4 wants the sentence front-loaded
    rather than complete.
    """
    if isinstance(location, EdgeLocation):
        target = location.target if location.target is not None else "an unresolved target"
        label = f" on label {location.label}" if location.label is not None else ""
        return f"edge {location.source} -> {target}{label}"
    if isinstance(location, CycleLocation):
        return f"cycle {_closed_walk(location.nodes)}"
    if isinstance(location, SccLocation):
        return f"component {', '.join(location.nodes)}"
    if isinstance(location, DataflowLocation):
        return f"state key {location.key} read by node {location.node}"
    if isinstance(location, StateKeyLocation):
        at_node = f" at node {location.node}" if location.node is not None else ""
        return f"state key {location.key}{at_node}"
    if isinstance(location, PathLocation):
        return f"path {_walk(location.nodes)}"
    if isinstance(location, NodeLocation):
        return f"node {location.node}"
    raise AssertionError(f"no §4.5 phrase for {type(location).__name__}")
