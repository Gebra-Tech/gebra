"""Drawable-graph mapping for drift test 4 — pure functions over an already-drawn graph.

VERSION-COMPAT §3 row 4 compares ``get_graph(xray=True)`` two ways, and this module is the
mapping both share:

* **The drawable golden**: node/edge counts plus per-edge ``Edge.conditional`` booleans,
  with every endpoint keyed by name + structural position **mapped to the ledger-§5 path
  ids** — the drawn ``:`` namespacing becomes the ledger's ``/`` path delimiter, and raw
  drawing ids (uuid or otherwise) never key anything. :func:`drawable_payload` builds that
  document; the committed golden pins it.
* **The builder-fidelity fold**: the drawing "equals the builder-derived IR after stripping
  the per-level ``__start__``/``__end__`` pseudo-nodes at every xray'd nesting level".
  Under ``xray`` the drawing expands *inside* the subgraphs the builder-derived IR carries
  as single parent nodes (DEC-19), so the two readings meet at builder granularity:
  :func:`folded_topology` folds every drawn id to its top-level segment, routes
  START/END incidences to ``entry``/``finish``, and drops a subgraph-internal edge (both
  endpoints expanded and folding to one node) as an artifact of the expansion with no
  counterpart at this level — the same normalization INTROSPECTION-SPEC §4.3 rule 2 fixes
  for the extractor's own cross-check. :func:`ir_topology` derives the comparison target
  from the canonical core-IR document, expanding a conditional edge's ``path_map`` the way
  §4.3 rule 2's label expansion does.

Everything here reads attributes and container members; nothing is invoked (WA-07). The
functions take the drawn object, not the compiled graph — drawing happens at the caller,
under the armed-fixture ledger.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

#: The drawing's nesting delimiter: an xray'd child of node ``parent`` draws as
#: ``parent:child`` (observed across the frozen matrix; A1 §3).
DRAWN_SEPARATOR: Final = ":"

#: The ledger-§5 path delimiter the drawn ids are mapped onto.
PATH_SEPARATOR: Final = "/"

#: The per-level entry/exit pseudo-nodes (ledger §5 reserved segments).
RESERVED_SEGMENTS: Final = frozenset({"__start__", "__end__"})


def path_id(drawn_id: str) -> str:
    """A drawn id as its ledger-§5 path spelling: ``finalize:polish`` → ``finalize/polish``.

    Delimiter substitution only — no ledger-§5 percent-escaping is performed, which is
    sound for this suite because no drift fixture name contains ``/`` or ``%`` and the
    substrate refuses ``:`` in node names; a reuse over arbitrary names would need the
    escaping pass first.
    """
    return PATH_SEPARATOR.join(drawn_id.split(DRAWN_SEPARATOR))


def drawn_node_ids(drawn: object) -> tuple[str, ...]:
    """The drawn graph's node ids — reads ``.nodes`` (a mapping) and calls nothing."""
    nodes = getattr(drawn, "nodes", None)
    if not isinstance(nodes, Mapping):
        return ()
    return tuple(identifier for identifier in nodes if isinstance(identifier, str))


def drawn_edges(drawn: object) -> tuple[tuple[str, str, bool], ...]:
    """The drawn ``(source, target, conditional)`` triples — attribute reads only."""
    edges = getattr(drawn, "edges", None)
    if not isinstance(edges, Iterable):
        return ()
    triples: list[tuple[str, str, bool]] = []
    for edge in edges:
        source = getattr(edge, "source", None)
        target = getattr(edge, "target", None)
        if isinstance(source, str) and isinstance(target, str):
            triples.append((source, target, bool(getattr(edge, "conditional", False))))
    return tuple(triples)


def drawable_payload(drawn: object) -> dict[str, Any]:
    """The drawable golden document: counts + per-edge conditional booleans, path-id keyed.

    The counts are the raw drawing's (pseudo-nodes included — they are part of what the
    drawing yields, and a heuristic-edge or step-limit change moves them); the edge list
    carries every endpoint in ledger-§5 path spelling, sorted for a stable committed form.
    """
    triples = drawn_edges(drawn)
    edges = [
        {"conditional": conditional, "from": path_id(source), "to": path_id(target)}
        for source, target, conditional in sorted(triples)
    ]
    return {
        "edge_count": len(triples),
        "edges": edges,
        "node_count": len(drawn_node_ids(drawn)),
        "nodes": sorted(path_id(identifier) for identifier in drawn_node_ids(drawn)),
    }


@dataclass(frozen=True)
class Topology:
    """One granularity-normalized reading: what connects to what, and how it is flagged."""

    nodes: frozenset[str]
    edges: frozenset[tuple[str, str, bool]]
    """``(from, to, conditional)`` at builder granularity."""
    entry: frozenset[str]
    finish: frozenset[str]


def _fold(drawn_id: str) -> str | None:
    """A drawn id as the top-level node it belongs to, or ``None`` for a pseudo-node."""
    top = drawn_id.partition(DRAWN_SEPARATOR)[0]
    if top in RESERVED_SEGMENTS:
        return None
    return top


def folded_topology(drawn: object) -> Topology:
    """The drawing folded to builder granularity — §4.3 rule 2's normalization, test-side.

    Per-level ``__start__``/``__end__`` handling: a *top-level* START/END endpoint becomes
    an ``entry``/``finish`` incidence; a pseudo-node at a **deeper** level (a child's own
    entry/exit, on a substrate that draws them — ``finalize:__start__``) folds to its
    parent like any other child id, so a cross-boundary edge through it survives at parent
    granularity while a purely child-internal edge through it is dropped by the
    subgraph-internal rule below — which is what stripping the pseudo-node and re-stitching
    its incidences amounts to at this granularity. A subgraph-internal edge — at least one
    endpoint expanded, both folding to one node — is dropped; a genuine top-level
    self-loop has neither endpoint expanded and survives.
    """
    nodes: set[str] = set()
    for identifier in drawn_node_ids(drawn):
        folded = _fold(identifier)
        if folded is not None:
            nodes.add(folded)
    edges: set[tuple[str, str, bool]] = set()
    entry: set[str] = set()
    finish: set[str] = set()
    for source, target, conditional in drawn_edges(drawn):
        expanded = DRAWN_SEPARATOR in source or DRAWN_SEPARATOR in target
        head, tail = _fold(source), _fold(target)
        if head is None and tail is None:
            continue
        if head is None:
            if source.partition(DRAWN_SEPARATOR)[0] == "__start__" and tail is not None:
                entry.add(tail)
            continue
        if tail is None:
            if target.partition(DRAWN_SEPARATOR)[0] == "__end__":
                finish.add(head)
            continue
        if expanded and head == tail:
            continue
        edges.add((head, tail, conditional))
    return Topology(
        nodes=frozenset(nodes),
        edges=frozenset(edges),
        entry=frozenset(entry),
        finish=frozenset(finish),
    )


def ir_topology(document: Mapping[str, Any]) -> Topology:
    """The builder-derived core-IR document as the same granularity-normalized reading.

    A ``conditional`` (or any other non-``normal``) routing edge expands per ``path_map``
    value with the conditional flag set — the drawing draws one flagged edge per declared
    target, which is §4.3 rule 2's label expansion. A ``path_map`` target of ``__end__``
    would expand to a ``finish`` incidence; a ``dynamic`` edge has no targets to expand and
    is outside this fixture's vocabulary (the six goldens carry none).
    """
    entry = frozenset(_members(document.get("entry", ())))
    finish = set(_members(document.get("finish", ())))
    edges: set[tuple[str, str, bool]] = set()
    for edge in document.get("edges", ()):
        kind = edge.get("kind", "normal")
        source = edge["from"]
        if kind == "normal":
            edges.add((source, edge["to"], False))
            continue
        if "path_map" in edge:
            targets: Iterable[str] = edge["path_map"].values()
        elif "to" in edge:
            targets = (edge["to"],)
        else:  # a targetless (`dynamic`) edge — nothing to expand at this granularity
            continue
        for target in targets:
            if target == "__end__":
                finish.add(source)
            else:
                edges.add((source, target, True))
    return Topology(
        nodes=frozenset(node["id"] for node in document.get("nodes", ())),
        edges=frozenset(edges),
        entry=entry,
        finish=frozenset(finish),
    )


def _members(wired: object) -> tuple[str, ...]:
    """``entry``/``finish`` in either canonical representation (IR-SPEC §6.3), as a tuple."""
    if isinstance(wired, str):
        return (wired,)
    if isinstance(wired, Iterable):
        return tuple(member for member in wired if isinstance(member, str))
    return ()
