"""P-01 ``graph-well-formed`` — the topology gate (PROPERTY-CATALOG-SPEC §1).

**Claim class DEFENSIBLE, severity FATAL, always** (§1.3): both are read off the §0.4
registry at emission, never restated here. P-01 asserts well-formedness of the **definition**
only — no behavioural claim (§1.4's closing note; D-018: Gebra verifies,
LangGraph runs). What it checks is the catalog's four conditions over the sentinel-augmented
graph $G^*$:

* **(i)** every node is reachable from ``START`` — ``node-unreachable-from-start``;
* **(ii)** ``END`` is reachable from every node that has *no outgoing edge* —
  ``dead-end-node-not-wired-to-end``. Sinks only, catalog-literal: a *trap component* (every
  member with ``out_degree > 0``, none able to reach ``__end__``) is deliberately out of
  scope, ruled at PD-007 Q1 / VAL-D1 so that cycle-adjacent structural defects stay P-02's
  (one root cause, one report — DEC-05 D2);
* **(iii)** no orphan nodes, under **Reading A** (ratified — walkthrough #2, DEC-11):
  membership in ``entry``/``finish`` *is* edge participation, so a finish-only node with no
  explicit edge is wired, not an orphan — ``orphan-node``;
* **(iv)** every reference names a node that exists — ``path-map-target-undefined`` for a
  ``path_map`` value, ``edge-target-undefined`` for the other four sites (``entry`` ids,
  ``finish`` ids, an edge's ``from``, a ``normal``/``send`` edge's ``to``), which is DEC-12's
  ratified scope.

**The ``dynamic`` edge (ir 1.1 — ratified DEC-28, 2026-08-09; PD-041) is read under the ruled
semantics, never dropped.** §0.3's one convention: the edge contributes no member to $G^*$ —
its targets are Runtime-only — while its source *participates*: wired for condition (iii)
(Step 2's ``dynamic`` term), never a sink for condition (ii) (Step 4's ``id ∉
dynamic_sources``), and, when statically reachable, the trigger of condition (i)'s
over-approximation (Step 3): "the dispatcher may target any node at runtime, so static
unreachability stops being a DEFENSIBLE claim — (i) MUST NOT fire for any node". The coverage
that costs — a genuinely disconnected island goes unflagged on such a document — is surfaced
rather than silent, on the witness's optional ``dynamic_dependent`` member (emitted only when
non-empty, DEC-11 discipline, never verdict-bearing). Dropping the edge *quietly* would have
reported ``node-unreachable-from-start`` for every node only the router reaches — the false
FATAL DEC-28 clause 1 forbids by name and the same trap DEC-18 rejected edge omission for. An
unresolved dispatcher is not a participant: Step 1 checks ``e.from ∈ V`` before its ``dynamic``
branch, so it is an ``edge-target-undefined`` finding and nothing more.

**P-01 is cycle-agnostic and never enumerates cycles** (§1.1, §1.5). The whole check is one
graph build, one forward BFS and two degree scans, plus the ledger §6 sorts — O(|V| log |V| +
|E*|), independent of |Σ|. Nothing here touches the shared module's SCC, condensation or
anchor-cycle machinery, and ``tests/verify/test_graph_well_formed.py`` asserts that
structurally rather than by inspection: those derivations are memoized, so their *absence* from
a model P-01 has run over is direct evidence none was asked for. A second test counts every
adjacency read on a graph carrying 2^60 simple cycles and finds it bounded by a small multiple
of the vertex count.

**The graph is VAL-03's, not this module's** (§1.4 Step 1 is
:func:`~gebra.verify.graph.build_graph_model`'s job): label expansion, the (m1)–(m5) sentinel
wiring and the unresolved-reference records all come from
:mod:`gebra.verify.graph`, so P-01, P-02, P-04 and P-06 agree on the graph by construction.
This module supplies only the property semantics — which record becomes which finding, in
which order, and what the pass witness says.

**The degradation convention is P-01's own** (§0.3's P-01-clean precondition): "P-01 drops
dangling-target edges", so the model is built with ``carry_unresolved_references=False`` and
conditions (i)–(iii) run on the resolvable subgraph. That is what DEC-12 closed the
phantom-node hole with: an unresolved reference emits a finding and inserts nothing, so a
non-``V`` id can never leak into a passing witness's ``terminal_nodes``. §0.3 is explicit
that this convention is local — P-02 and P-04 carry the phantom instead — and that
"cross-validator agreement on ill-formed input is NOT promised".

Nothing here executes a node, calls a model, or opens a network connection (WA-07): the input
is a validated :class:`~gebra.ir.WorkflowIR` and the output is structured values. P-01 reads
``entry``, ``finish``, ``nodes[].id`` and ``edges[].{from,to,kind,path_map}`` and nothing else
(§1.3 "Not read": ``state``, ``annotations``, ``runtime``, and ``condition`` router strings) —
every one of them through the shared model. A fixture's ``source_snippet`` is never read, let
alone run.
"""

from __future__ import annotations

from typing import Final

from gebra.ir import WorkflowIR
from gebra.verify.base import ConditionId, NodeId, PropertySlug, to_display
from gebra.verify.conditions import emit_co_failure, emit_failure
from gebra.verify.graph import (
    END_VERTEX,
    START_VERTEX,
    GraphModel,
    UnresolvedReference,
    build_graph_model,
    ledger_sort_key,
)
from gebra.verify.locations import NodeLocation, P01EdgeLocation
from gebra.verify.registry import register_validator
from gebra.verify.report import CoFailure, PropertyReport
from gebra.verify.witnesses import WellFormednessWitness

__all__ = [
    "DEAD_END_NODE_NOT_WIRED_TO_END",
    "EDGE_TARGET_UNDEFINED",
    "NODE_UNREACHABLE_FROM_START",
    "ORPHAN_NODE",
    "PATH_MAP_TARGET_UNDEFINED",
    "PROPERTY_SLUG",
    "check_graph_well_formed",
]

#: The catalog slug this module answers for (Verification-Properties §1.3).
PROPERTY_SLUG: Final[PropertySlug] = "graph-well-formed"

#: Condition (i) — §0.4 RATIFIED (``negative-01``; ``mixed/04``).
NODE_UNREACHABLE_FROM_START: Final[ConditionId] = "node-unreachable-from-start"

#: Condition (ii) — §0.4 RATIFIED (``negative-02``).
DEAD_END_NODE_NOT_WIRED_TO_END: Final[ConditionId] = "dead-end-node-not-wired-to-end"

#: Condition (iii) — §0.4 PROPOSED tier, ratified and emittable by DEC-11.
ORPHAN_NODE: Final[ConditionId] = "orphan-node"

#: Condition (iv) on a ``path_map`` value — §0.4 RATIFIED (``negative-03``; ``mixed/04``).
PATH_MAP_TARGET_UNDEFINED: Final[ConditionId] = "path-map-target-undefined"

#: Condition (iv) on the other four reference sites — §0.4 PROPOSED tier, ratified and
#: emittable by DEC-12 (2026-07-31), which fixed its scope: ``entry`` ids, ``finish`` ids,
#: edge ``from`` fields, and ``normal``/``send`` edge ``to`` fields.
EDGE_TARGET_UNDEFINED: Final[ConditionId] = "edge-target-undefined"

#: One §1.4 finding, before packaging: the condition and its anchor. The pseudocode's
#: ``finding(...)`` — deliberately not a :class:`~gebra.verify.report.Failure` yet, because
#: which one is the primary is decided only after all four blocks are ordered (Step 5).
_Finding = tuple[ConditionId, P01EdgeLocation | NodeLocation]


# ── The check (§1.4) ─────────────────────────────────────────────────────────────────────


def check_graph_well_formed(ir: WorkflowIR, *, model: GraphModel | None = None) -> PropertyReport:
    """Check the four §1 conditions over ``ir``'s sentinel-augmented graph (§1.4).

    The five steps of the pseudocode, in order: build $G^*$ with the labels expanded and
    condition (iv)'s unresolved references recorded (Step 1, VAL-03's
    :func:`~gebra.verify.graph.build_graph_model`); the condition-(iii) orphan scan under
    Reading A (Step 2); one forward BFS for condition (i) — or, on a document with a reachable
    ``dynamic`` edge, DEC-28's over-approximation and the witness's ``dynamic_dependent``
    diagnostic (Step 3); one out-degree scan for condition (ii) (Step 4); and the root-cause
    ordering (iv)→(iii)→(i)→(ii) that names the primary (Step 5).

    Args:
        ir: A validated workflow IR at ``ir_version`` ``"1.0"`` or ``"1.1"``. Only ``entry``,
            ``finish``, ``nodes[].id`` and ``edges[].{from,to,kind,path_map}`` are read (§1.3);
            ``edges[].kind`` distinguishes ``dynamic`` (no target fields) from the other three.
        model: A pre-built model of the *same* ``ir``, when a caller already has one —
            ``verify()`` builds one model and hands it to every topology-facing validator, and
            two builds of one IR are equal values, so sharing changes no result. It must be
            built with ``carry_unresolved_references=False``, which is P-01's own §0.3
            degradation convention; a model carrying phantoms is P-02's or P-04's and is
            refused rather than silently mis-analysed.

    Returns:
        One :class:`~gebra.verify.report.PropertyReport`: ``pass`` with the 5-key
        :class:`~gebra.verify.witnesses.WellFormednessWitness`, or ``fail`` with the
        root-cause-ordered primary finding and every further finding as a same-property
        ``co_failure`` (§0.3 packaging; findings are never dropped).

    Raises:
        ValueError: if ``model`` carries phantom vertices for unresolved references.
    """
    graph = _model_for(ir, model)
    node_ids = graph.node_ids
    unreachable, dynamic_dependent = _condition_i(graph)

    findings: list[_Finding] = [
        *_condition_iv(graph),  # Step 1's F_iv, ordered by Step 5's DEC-12 key
        *_condition_iii(graph),  # Step 2 — orphans, Reading A + the DEC-28 dynamic term
        *unreachable,  # Step 3 — forward reachability from START, or its over-approximation
        *_condition_ii(graph),  # Step 4 — sinks not wired to END; a dispatcher is never one
    ]

    if findings:
        (condition, location), *rest = findings
        co_failures: tuple[CoFailure, ...] = tuple(
            emit_co_failure(PROPERTY_SLUG, other_condition, other_location)
            for other_condition, other_location in rest
        )
        return PropertyReport.failing(
            PROPERTY_SLUG,
            emit_failure(PROPERTY_SLUG, condition, location, co_failures=co_failures or None),
        )

    return PropertyReport.passing(
        PROPERTY_SLUG,
        WellFormednessWitness(
            kind="well-formedness",
            # §1.4 Step 5 writes `sorted(V)`, with the comment "== reachable on pass". On a
            # static pass it is, because a non-reachable id would have filled F_i and there
            # would be no witness to write. Under DEC-28's over-approximation the operative
            # line is followed as written — every node is *possibly* reachable, since the
            # dispatcher may target any of them — and the members that depend on the dispatch
            # for it are named in `dynamic_dependent` beside this list, so a reader is never
            # left to infer the static picture. The comment's equality no longer holds on that
            # case and Step 5 was not amended with Step 3: a WA-03 clarification of whether
            # this list is V or the static START-closure is filed as PD-056; the literal line
            # is the reading until it is ruled. `graph.vertices` is already the ledger §6 order.
            reachable_from_start=_ids(graph, node_ids),
            terminal_nodes=tuple(to_display(v) for v in graph.predecessors(END_VERTEX)),
            # Empty by construction: a non-empty one would have filled `failure` instead.
            orphan_nodes=(),
            unresolved_targets=(),
            # "Emitted only when non-empty" (DEC-28 clause 1; DEC-11 discipline). The PC-4
            # profile drops the `None`, so a 1.0 witness serializes exactly as it always has.
            dynamic_dependent=dynamic_dependent or None,
        ),
    )


def _model_for(ir: WorkflowIR, model: GraphModel | None) -> GraphModel:
    """The graph P-01 runs on — §1.4 Step 1, with §0.3's local degradation convention.

    Building it here rather than taking one is the default because a validator handed no
    model must still work; taking one is what lets ``verify()`` pay for the build once.
    """
    if model is None:
        return build_graph_model(ir, carry_unresolved_references=False)
    if model.carried:
        raise ValueError(
            "P-01 runs on the resolvable subgraph: PROPERTY-CATALOG-SPEC §0.3 gives it the "
            "convention 'P-01 drops dangling-target edges', and DEC-12 closed the phantom "
            "path by which an unresolvable reference could otherwise leak a non-V id into a "
            f"passing witness. This model carries {sorted(model.carried)!r} — build it with "
            "carry_unresolved_references=False (P-02's and P-04's convention is the other "
            "one, and §0.3 does not promise the two agree on ill-formed input)."
        )
    return model


# ── Step 1 / Step 5 — condition (iv), the unresolved references ──────────────────────────


def _condition_iv(graph: GraphModel) -> list[_Finding]:
    """F_iv: one finding per unresolved reference, in the DEC-12 order (§1.4 Steps 1 and 5).

    **Emission is complete — no collapse.** Every recorded reference becomes its own finding
    (DEC-12; §0.3's findings-are-never-dropped rule). The shared model already mirrors §1.4
    Step 1's one asymmetry — a ``normal``/``send`` edge whose ``from`` is unresolved has its
    ``to`` skipped, while a conditional edge's labels are still resolved and checked — so the
    record list is one-to-one with the findings emitted here.

    The sort is Step 5's, as amended by DEC-12: a leading key puts findings whose
    ``location.source`` resolves in $V \\cup \\{$``__start__``$\\}$ before findings whose source
    is itself unresolved, so the primary stays at an actionable edit site; the ledger §6
    comparator over ``(source, label ?? "", undefined_target)`` applies within each group.
    """
    anchors = graph.node_ids | {START_VERTEX}
    ordered = sorted(
        graph.unresolved,
        key=lambda reference: (
            reference.source not in anchors,
            ledger_sort_key(reference.source),
            ledger_sort_key(reference.label or ""),
            ledger_sort_key(reference.reference),
        ),
    )
    return [_reference_finding(reference) for reference in ordered]


def _reference_finding(reference: UnresolvedReference) -> _Finding:
    """One unresolved reference as its §1.3 condition and ``P01EdgeLocation``.

    The role → condition-ID mapping is DEC-12's scope statement read directly: a ``path_map``
    value keeps its own ID, and the other four sites are one condition, because DEC-05 D4
    reserves a distinct ID only for a *diagnostically distinct* failure and "a reference names
    a node that does not exist" is one defect four ways.

    The anchor is the record's, not re-derived: ``source`` is the vertex a person would edit
    (``__start__`` for a bad ``entry`` id, the id itself for a bad ``finish`` id or an
    unresolved edge ``from``, the router for a dangling label), projected to its report-side
    spelling, and ``undefined_target`` is the string that resolves to nothing. The anchor's own
    ``target`` stays omitted, per §0.3's dangling-label rule.
    """
    condition = (
        PATH_MAP_TARGET_UNDEFINED if reference.role == "path-map-target" else EDGE_TARGET_UNDEFINED
    )
    return (
        condition,
        P01EdgeLocation(
            kind="edge",
            source=to_display(reference.source),
            label=reference.label,
            undefined_target=reference.reference,
        ),
    )


# ── Step 2 — condition (iii), orphans under Reading A ────────────────────────────────────


def _condition_iii(graph: GraphModel) -> list[_Finding]:
    """F_iii: nodes participating in no edge at all (§1.4 Step 2; Reading A, DEC-11).

    Reading A counts the implicit sentinel wirings as participation, so the test is
    ``explicit + sentinel == 0`` where ``explicit`` is the in+out degree over edges built from
    ``ir.edges`` and ``sentinel`` is membership in ``entry``/``finish``. Both halves are asked
    of the shared model rather than of the IR: for an id in $V$, carrying an ``entry`` or
    ``finish`` wiring edge is exactly being a member of that list, so P-01 need not read
    ``ir.entry`` at all (:meth:`~gebra.verify.graph.GraphModel.degree` documents the
    equivalence).

    The splitter case §1.3 names — a single-node graph with ``entry == finish == n`` and no
    edges — passes here, which is what makes this Reading A rather than Reading B.

    Step 2's third term is DEC-28's: ``dynamic ← [id ∈ dynamic_sources]`` — "a dynamic edge
    wires its source". The edge inserted no member, so neither degree count sees it; membership
    in :attr:`~gebra.verify.graph.GraphModel.dynamic_sources` is what says the node
    participates. A dispatcher with no other edge and no sentinel wiring is therefore *not* an
    orphan — which is exactly the false FATAL edge-omission would have produced (PD-041
    rationale 3).
    """
    return [
        (ORPHAN_NODE, NodeLocation(kind="node", node=vertex))
        for vertex in _sorted_nodes(graph)
        if graph.degree(vertex, origins=("edges",)) == 0
        and graph.degree(vertex, origins=("entry", "finish")) == 0
        and vertex not in graph.dynamic_sources
    ]


# ── Step 3 — condition (i), forward reachability from START ──────────────────────────────


def _condition_i(graph: GraphModel) -> tuple[list[_Finding], tuple[NodeId, ...]]:
    """F_i, or its DEC-28 over-approximation: ``(findings, dynamic_dependent)`` (§1.4 Step 3).

    One BFS closure, O(|V| + |E*|). Unresolved references contributed no edge (Step 1), so a
    node reachable only through a dangling reference is correctly unreachable here — which is
    the cascade ``negative-03`` and ``mixed/04`` pin, reported alongside its root cause rather
    than instead of it.

    **The dynamic-dispatch over-approximation** (ratified — DEC-28 clause 1; PD-041). When
    some ``dynamic`` edge's *source* is statically reachable, the dispatcher may target any node
    at runtime, so static unreachability stops being a DEFENSIBLE claim and condition (i) MUST
    NOT fire for any node: the findings list is empty and the nodes it would have named are
    returned as ``dynamic_dependent`` for the witness — the coverage cost, priced in the DEC,
    surfaced rather than silent. When no dispatcher is reachable the dispatch can never run,
    and (i) runs as written with an empty second member. Exactly one of the two is non-empty,
    and on an ir 1.0 document the second always is.
    """
    reachable = graph.descendants(START_VERTEX)
    unreachable = tuple(vertex for vertex in _sorted_nodes(graph) if vertex not in reachable)
    if graph.reachable_dynamic_sources():
        return [], tuple(to_display(vertex) for vertex in unreachable)
    return [
        (NODE_UNREACHABLE_FROM_START, NodeLocation(kind="node", node=vertex))
        for vertex in unreachable
    ], ()


# ── Step 4 — condition (ii), sinks not wired to END ──────────────────────────────────────


def _condition_ii(graph: GraphModel) -> list[_Finding]:
    """F_ii: nodes with no outgoing edge in $G^*$ (§1.4 Step 4).

    Catalog-literal, and the ``finish`` wiring is why one scan suffices: a node listed in
    ``finish`` carries an edge to ``__end__``, so it is never a sink and needs no separate
    test. A node that is neither wired onward nor in ``finish`` strands execution — the
    ``negative-02`` case.

    Step 4's ``id ∉ dynamic_sources`` is DEC-28's: "a dynamic edge's source has a runtime
    out-route and is never a dead end". Its out-degree in $G^*$ is what the static edges make
    it — possibly zero — so the exclusion is by membership, not by degree.

    Trap components are **not** checked here. §1.7 open item 4 names the gap, PD-007 Q1
    (VAL-D1, ratified 2026-07-24) disposed it, and DEC-12's closing line confirms it in the
    vault — "condition (ii) (trap components) … confirmed as written, no scope change". The
    strict alternative $V \\setminus \\texttt{ancestors}(\\texttt{\\_\\_end\\_\\_})$ would widen
    P-01's formal scope over structures P-02 already owns (DEC-05 D2: one root cause, one
    report), and it is drafted as a Phase-1 item instead. The gap is deliberate and named, not
    an oversight to close locally: closing it needs its own vault ruling.
    """
    return [
        (DEAD_END_NODE_NOT_WIRED_TO_END, NodeLocation(kind="node", node=vertex))
        for vertex in _sorted_nodes(graph)
        if not graph.out_edges(vertex) and vertex not in graph.dynamic_sources
    ]


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _sorted_nodes(graph: GraphModel) -> tuple[str, ...]:
    """$V$ in ledger §6 order — the ``sorted(V)`` every one of Steps 2–4 iterates.

    Read off :attr:`~gebra.verify.graph.GraphModel.vertices`, which is already sorted by that
    comparator, so the O(|V| log |V|) term of §1.5 is paid once by the model rather than three
    times here.
    """
    return tuple(vertex for vertex in graph.vertices if vertex in graph.node_ids)


def _ids(graph: GraphModel, wanted: frozenset[str]) -> tuple[NodeId, ...]:
    """``wanted`` in ledger §6 order, report-side spelling — a witness node list."""
    return tuple(to_display(vertex) for vertex in graph.vertices if vertex in wanted)


# Registration is what dispatch runs on, so it happens once, at import (registry note N8).
# It is deliberately not made re-entrant: `register_validator` refuses a second registration
# rather than replacing one silently, and the only way this line runs twice is two module
# identities for this file — a duplicated package on `sys.path`, or a reload — which is an
# environment defect worth failing loudly at import rather than resolving by guesswork.
register_validator(PROPERTY_SLUG, check_graph_well_formed)
