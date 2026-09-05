"""P-06 ``effect-safety`` — the protection lattice (PROPERTY-CATALOG-SPEC §6).

**Claim class DEFENSIBLE-A** (§6.2), with two severities and three condition IDs: FATAL for
the D-012 forbidden combination (``irreversible`` + keyless ``@gebra.idempotent``), ERROR for a
trigger-tagged node left unprotected inside a retry region or a plain cycle. All three are read
off the §0.4 registry at emission, never restated here.

What P-06 decides, and what it deliberately does not. The trigger set is exactly
``{billable, irreversible}`` (§6.3); ``network``/``external``/``audit``/user tags create **no**
obligation — they ride the ``effect`` tuples as evidence context only. Two protections
discharge the obligation, and both are checked for **binding** rather than presence: a keyed
``idempotent`` whose key is among the node's declared ``input`` (the ledger §3 side condition —
``mixed/06``'s key is the node's own output, so it is not protection), and a
``compensation: {hook}`` naming an existing node (DEC-05 D7, restated normatively at §6.1). The
honest-claims boundary is §6.2's own: these annotations are **declared**, and their truthfulness
is trusted like a type annotation. P-06 records protection *declaration presence and binding* —
never provider dedup behaviour, never that a compensation hook undoes anything, never a runtime
claim (D-018).

**The graph is VAL-03's, not this module's.** §6.4 says so in its own words: "Phases 0 and 2
are steps (1)–(2) of the SCC-condensation procedure in TERMINATION-WITNESS-SPEC — **cited, not
redefined**". So label expansion, the sentinel wiring and Tarjan all come from
:mod:`gebra.verify.graph`, and so does the anchor: :meth:`~gebra.verify.graph.GraphModel
.anchor_cycle` *is* §6.4's ``anchor_cycle(n)``, one multi-source BFS per anchor and never one
per successor (§6.5). This module contributes the property semantics — Phase 1's annotation
sweep, Phase 3's region rule, Phase 4's lattice, Phase 5's packaging — and one edge scan
(:func:`_structural_retry_regions`) that reads the shared model's edge list and component map
rather than building a graph of its own.

**The ``dynamic`` edge (ir 1.1 — ratified DEC-28) is §6.4 Phase 0's ``elif e.kind == dynamic:
continue`` — "no member of G" — realized once in the shared model.** No member means no cycle
membership, no retry re-entry and no ``send`` closure through it: a trigger-tagged node whose only
route back is a dynamic router is in an ``acyclic`` region here, with ``none_required``, and its
dispatcher is simply a node with one fewer out-edge. Static cycles and retry regions beside such an
edge are unchanged. The ``fanout`` evidence reads ``send`` in-edges only, which a ``dynamic`` edge
never is.

**Where §6.4's Phase 0 and the shared model differ in spelling, on P-01-clean topology, never in
answer.** Two of the differences are pure spelling. Phase 0 builds a sentinel-free graph and
``continue``s past a ``path_map`` label valued ``"END"``; the shared model materializes
``__start__``/``__end__`` and wires that label to ``__end__``. By IR-SPEC §4.1 (m5) ``__start__``
has no in-edge and ``__end__`` no out-edge, so each is a trivial component that no cycle can
contain and no edge incident to either can join one — the partition restricted to $V$,
``in_cycle``, every anchor and every region are identical either way. The sentinel wirings are
``kind="normal"``, so they are invisible to the ``fanout`` and send-closure scans too.

The **third** difference is a real one, and it is why the sentence above is scoped. §6.4 writes
Phase 0 in ``nx``, whose ``add_edge`` auto-vivifies, so read literally it materializes a phantom
vertex for a dangling ``normal``/``send`` ``to`` — and for a dangling ``from`` — where this
module drops the edge. §0.3 governs and names P-06's convention outright ("P-06 skips the
edge"), which is ``carry_unresolved_references=False``, and a model carrying phantoms is refused
rather than silently mis-analysed (:func:`_model_for`). But on P-01-**dirty** topology the two
readings can genuinely disagree: a ``mixed/04``-shaped dangling reference used as an edge
*source* would put a phantom inside an SCC under the literal reading and not under this one.
That is exactly the surface §0.3's P-01-clean precondition excludes — P-06's results are
"normatively defined only over P-01-clean topology", where P-01 fails another property's report
is "best-effort diagnostics, not contract-bearing verdicts", and a single-property-scoped run
there is "outside the defined result surface". §0.3 adds that these conventions "are
deliberately local, cross-validator agreement on ill-formed input is NOT promised", so the
divergence is licensed rather than an open question (the property-spec pre-review, VAL-10 N1).

**Compensation is protection, and one frozen text still says the opposite.** IR-SPEC §3.4 reads
"slot now, semantics deferred … until then the slot is declared content that validators MAY
surface but MUST NOT treat as discharging any P-06/P-07 obligation" — with "until then" pointing
at "P-06 formalizes compensation-as-protection later". §6 **is** that formalization: §6.1
restates DEC-05 D7 normatively ("A declared compensation hook discharges the P-06 obligation
exactly as a keyed idempotency declaration does"), §6.4 Phase 4 implements it, §6.7's
walkthrough-#2 disposition (i) records it ratified, and ``effect-safety/positive-03`` pins the
resulting witness. So the IR-SPEC sentence is spent rather than contradicted; it is named here
so a later reader does not take the divergence for an oversight.

Nothing here executes a node, calls a model, or opens a network connection (WA-07): the input is
a validated :class:`~gebra.ir.WorkflowIR` and the output is structured values. P-06 reads
``nodes[].id``, five annotation slots (``effect``, ``idempotent``, ``compensation``,
``retry_policy``, ``input``) and ``edges[].{from, to, kind, path_map}`` — all of the last through
the shared model. $\\Sigma$ is never read, and neither is ``annotations.pure``, delisted as a
P-06 reader by DEC-13. A router's declared ``condition`` string is never read, let alone
evaluated: Phase 3 keys on edge **kind**, not on what the guard says.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Final, Literal

from gebra.ir import Annotations, IdempotentKey, Node, WorkflowIR
from gebra.ir.identity import is_valid_node_id
from gebra.verify.base import ConditionId, PropertySlug
from gebra.verify.conditions import condition, emit_co_failure, emit_failure
from gebra.verify.graph import GraphModel, build_graph_model, ledger_sort_key
from gebra.verify.locations import P06NodeLocation
from gebra.verify.registry import register_validator
from gebra.verify.report import CoFailure, PropertyReport
from gebra.verify.witnesses import EffectSafetyWitness, P06EffectRecord, Region

__all__ = [
    "IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT",
    "PROPERTY_SLUG",
    "TRIGGER_TAGS",
    "UNPROTECTED_EFFECT_IN_CYCLE",
    "UNPROTECTED_EFFECT_IN_RETRY_REGION",
    "check_effect_safety",
]

#: The catalog slug this module answers for (Verification-Properties §1.3).
PROPERTY_SLUG: Final[PropertySlug] = "effect-safety"

#: §6.3/§6.4's ``TRIGGER`` — "the trigger set is exactly ``{billable, irreversible}``"
#: (Verification-Properties §P-06, D-011/D-012). Every other declared tag is evidence.
TRIGGER_TAGS: Final[frozenset[str]] = frozenset({"billable", "irreversible"})

#: The D-012 forbidden combination — §0.4 RATIFIED, FATAL, cycle-independent (``negative-03``).
IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT: Final[ConditionId] = "irreversible-with-keyless-idempotent"

#: §0.4 RATIFIED, ERROR (``negative-01``; ``mixed/01``, ``mixed/06``, ``mixed/09``).
UNPROTECTED_EFFECT_IN_RETRY_REGION: Final[ConditionId] = "unprotected-effect-in-retry-region"

#: §0.4 RATIFIED, ERROR (``negative-02``).
UNPROTECTED_EFFECT_IN_CYCLE: Final[ConditionId] = "unprotected-effect-in-cycle"

#: One §6.4 finding before packaging: the condition and its anchor. Which one is the primary is
#: decided only in Phase 5, after Phase 1's FATALs and Phase 4's ERRORs are ordered together.
_Finding = tuple[ConditionId, P06NodeLocation]

#: The §0.2 ladder as a sort rank — Phase 5's ``severity: fatal < error``. Read off the §0.4
#: registry rather than restated, so a regrade moves this order with it.
_SEVERITY_RANK: Final[dict[str, int]] = {"fatal": 0, "error": 1, "warning": 2}


# ── The check (§6.4) ─────────────────────────────────────────────────────────────────────


def check_effect_safety(ir: WorkflowIR, *, model: GraphModel | None = None) -> PropertyReport:
    """Check every trigger-tagged node of ``ir`` against the protection lattice (§6.4).

    The five phases, in order: the label-expanded multigraph (Phase 0, VAL-03's
    :func:`~gebra.verify.graph.build_graph_model`); the cycle-**independent** FATAL scan for the
    D-012 forbidden combination (Phase 1); the Tarjan partition that decides ``in_cycle``
    (Phase 2, the shared :attr:`~gebra.verify.graph.GraphModel.components`); the structural
    retry regions (Phase 3, DEC-13's ratified send-closure rule); the obligation × protection
    lattice with its anchors (Phase 4); and the §0.3 same-property packaging (Phase 5).

    Args:
        ir: A validated workflow IR. ``state`` is never read (§6.3); nor is
            ``annotations.pure``, delisted as a P-06 reader by DEC-13.
        model: A pre-built model of the *same* ``ir``, when a caller already has one —
            ``verify()`` builds one model and hands it to every topology-facing validator, and
            two builds of one IR are equal values, so sharing changes no result. It must be
            built with ``carry_unresolved_references=False``, which is P-06's own §0.3
            degradation convention ("P-06 skips the edge"); a model carrying phantoms is P-02's
            or P-04's and is refused rather than silently mis-analysed.

    Returns:
        One :class:`~gebra.verify.report.PropertyReport`: ``pass`` with an
        :class:`~gebra.verify.witnesses.EffectSafetyWitness` — the cycle inventory plus one
        record per trigger-tagged node — or ``fail`` with the Phase-5-ordered primary finding
        and every further finding as a same-property ``co_failure`` (§0.3; nothing drops).

    Raises:
        ValueError: if ``model`` carries phantom vertices for unresolved references.
    """
    graph = _model_for(ir, model)

    failures: list[_Finding] = _fatal_findings(ir)  # Phase 1
    fatal_nodes = frozenset(location.node for _, location in failures)

    components = graph.components  # Phase 2
    structural_retry = _structural_retry_regions(graph)  # Phase 3

    records: list[P06EffectRecord] = []
    for node in _canonical_order(ir.nodes):  # Phase 4
        annotations = node.annotations
        effect = _effect(annotations)
        if TRIGGER_TAGS.isdisjoint(effect):
            continue  # no P-06 obligation (§6.4); the node's tags are not this property's

        in_cycle = components.is_nontrivial(node.id)
        retry = _has_retry_policy(annotations) or (in_cycle and node.id in structural_retry)
        region: Region = "retry" if retry else "cycle" if in_cycle else "acyclic"
        anchor = graph.anchor_cycle(node.id) if in_cycle else None

        if region == "acyclic":
            # Outside every cycle and every retry region there is no re-entry for the formal
            # statement's scope to reach — `positive-02`'s whole subject, and the reason P-06
            # is a region analysis rather than a blanket flag on every irreversible effect.
            records.append(
                P06EffectRecord(
                    node=node.id, effect=effect, region=region, protection="none_required"
                )
            )
            continue

        key = _binding_key(annotations)
        hook = _declared_hook(annotations)
        hook_ok = hook is not None and hook in graph.node_ids
        if key is not None:  # precedence: key before hook (§6.4 Phase 4)
            records.append(
                P06EffectRecord(
                    node=node.id,
                    effect=effect,
                    region=region,
                    cycle=anchor,
                    protection="idempotency_key",
                    key=key,
                )
            )
        elif hook_ok:
            records.append(
                P06EffectRecord(
                    node=node.id,
                    effect=effect,
                    region=region,
                    cycle=anchor,
                    protection="compensation_hook",
                    hook=hook,
                )
            )
        elif node.id in fatal_nodes:
            # Same-node dominance (DEC-05 D2, one root cause one report): the Phase-1 FATAL
            # already owns this node, and a second ERROR record on it would report the
            # consequence of a combination the first record rejects outright.
            continue
        else:
            failures.append(
                (
                    UNPROTECTED_EFFECT_IN_RETRY_REGION
                    if region == "retry"
                    else UNPROTECTED_EFFECT_IN_CYCLE,
                    P06NodeLocation(
                        kind="node",
                        node=node.id,
                        effect=effect,
                        cycle=anchor,
                        idempotent="keyless" if _is_keyless(annotations) else None,
                        fanout=_fanout(graph, node.id),
                        dangling_compensation_hook=_dangling(hook, hook_ok),
                    ),
                )
            )

    if failures:  # Phase 5
        (primary, location), *rest = sorted(failures, key=_phase_five_key)
        co_failures: tuple[CoFailure, ...] = tuple(
            emit_co_failure(PROPERTY_SLUG, other, other_location) for other, other_location in rest
        )
        return PropertyReport.failing(
            PROPERTY_SLUG,
            emit_failure(PROPERTY_SLUG, primary, location, co_failures=co_failures or None),
        )

    return PropertyReport.passing(
        PROPERTY_SLUG,
        EffectSafetyWitness(
            kind="effect-safety",
            cycles=_cycle_inventory(graph),
            effects=tuple(records),
        ),
    )


def _model_for(ir: WorkflowIR, model: GraphModel | None) -> GraphModel:
    """The graph P-06 runs on — §6.4 Phase 0, with §0.3's local degradation convention.

    Building it here rather than taking one is the default because a validator handed no model
    must still work; taking one is what lets ``verify()`` pay for the build once.
    """
    if model is None:
        return build_graph_model(ir, carry_unresolved_references=False)
    if model.carried:
        raise ValueError(
            "P-06 runs on the resolvable subgraph: PROPERTY-CATALOG-SPEC §0.3 gives it the "
            "convention 'P-06 skips the edge', which §6.4 Phase 0 writes as "
            "'target not in G: continue — dangling => P-01's finding; skip'. This model "
            f"carries {sorted(model.carried)!r} — build it with "
            "carry_unresolved_references=False (P-02's and P-04's convention is the other one, "
            "and §0.3 does not promise the two agree on ill-formed input)."
        )
    return model


# ── Phase 1 — the FATAL scan, cycle-independent ──────────────────────────────────────────


def _fatal_findings(ir: WorkflowIR) -> list[_Finding]:
    """The D-012 forbidden combination: ``irreversible`` + keyless ``idempotent`` (§6.4).

    **Cycle-independent by design**, which is why this runs before any graph analysis and why
    ``negative-03`` is deliberately acyclic: a bare "the provider dedups" claim that Gebra can
    tie to no input field is a design error wherever it sits, not a consequence of re-entry.
    The boolean form is the only one that fires — an object-form ``idempotent: {key}`` is a
    claim pinned to a declared read, and whether it *binds* is Phase 4's question.
    """
    findings: list[_Finding] = []
    for node in _canonical_order(ir.nodes):
        annotations = node.annotations
        effect = _effect(annotations)
        if "irreversible" in effect and _is_keyless(annotations):
            findings.append(
                (
                    IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
                    P06NodeLocation(kind="node", node=node.id, effect=effect, idempotent="keyless"),
                )
            )
    return findings


# ── Phase 3 — the structural retry regions (DEC-13, ratified verbatim) ───────────────────


def _structural_retry_regions(graph: GraphModel) -> frozenset[str]:
    """$\\bigcup_S T(S)$ over the non-trivial components — §6.4 Phase 3.

    The rule, ratified verbatim by DEC-13 (2026-07-31, lifting §6.4's "flagged for lead
    ratification" marker): for a component $S$,

    * $T(S) := \\bigcup \\mathit{send\\_closure}(t, S)$ over the **conditional label-edges**
      $(u \\to t)$ with $u, t \\in S$ — the re-entry decisions that put the lap back on $t$;
    * $\\mathit{send\\_closure}(t, S) := \\{t\\} \\cup$ the nodes reachable from $t$ **inside**
      $S$ through ``send`` edges only.

    Both halves earn their keep on the corpus, and PD-009 traced four fixtures by hand to fix
    them: the send closure is what makes ``mixed/09``'s ``book_segment`` — one ``send`` hop past
    the literal re-entry target — a retry region, because a ``Send`` dispatcher and its targets
    re-run as one re-dispatch unit; and restricting the closure to ``send`` edges is what keeps
    ``negative-02``'s ``submit_change_request`` a plain **cycle**, because an intervening
    ``normal`` edge is refinement carriage rather than retry. A coarser rule ("any trigger-tagged
    node in a non-trivial SCC is retry") contradicts ``negative-02`` and ``positive-03``; a
    stricter one ("only the literal re-entry target") contradicts ``mixed/09``.

    One scan over the shared model's edge list plus one BFS over the ``send`` sub-adjacency:
    O(|V| + |E'|) total, §6.5's stated bound. Nothing is re-derived — membership comes from the
    shared Tarjan partition, and "inside $S$" is "the two endpoints share a component", which is
    also why an edge into ``__end__`` or out of ``__start__`` can never contribute.
    """
    components = graph.components
    seeds: set[str] = set()
    dispatch: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        index = components.index(edge.source)
        if index != components.index(edge.target) or index not in components.nontrivial:
            continue
        if edge.kind == "conditional":
            seeds.add(edge.target)
        elif edge.kind == "send":
            dispatch[edge.source].append(edge.target)

    closure: set[str] = set()
    queue: deque[str] = deque(seeds)
    while queue:
        vertex = queue.popleft()
        if vertex in closure:
            continue
        closure.add(vertex)
        queue.extend(target for target in dispatch[vertex] if target not in closure)
    return frozenset(closure)


# ── Phase 4 — reading the protection annotations (ledger §3) ─────────────────────────────


def _effect(annotations: Annotations | None) -> tuple[str, ...]:
    """A node's **full declared** effect set, as authored (§6.3).

    Order is the author's and is not normative: ``P06NodeLocation.effect`` and
    ``P06EffectRecord.effect`` both carry the §6.3 ``SetCompared`` mark, so a report is compared
    on the set. Emitting it as declared rather than sorted keeps the evidence field a faithful
    echo of the annotation a reader will go and look at.
    """
    return annotations.effect or () if annotations is not None else ()


def _is_keyless(annotations: Annotations | None) -> bool:
    """``idempotent(n) == true`` — the boolean keyless form, and only that (§6.4 Phase 1)."""
    return annotations is not None and annotations.idempotent is True


def _binding_key(annotations: Annotations | None) -> str | None:
    """The idempotency key **if it binds**, else ``None`` — the ledger §3 side condition.

    §6.4 Phase 4: ``keyed := idempotent(n) == {key: k} and k ∈ input(n)``. A key that is not
    among the node's declared reads is not protection — ``mixed/06``'s ``refund_ref`` is the
    node's own *output*, minted fresh on every lap, so it can stabilise nothing. The diagnostic
    ID for the bad key **itself** belongs to P-07 and is RESERVED in §0.4, so it is deliberately
    not spelled anywhere in this package outside the registry table; §6.3 states the boundary —
    "P-06 owns effect-class protection, P-07 owns purity/idempotence coherence". In a
    P-06-scoped run the node simply reports as unprotected.
    """
    if annotations is None or not isinstance(annotations.idempotent, IdempotentKey):
        return None
    key = annotations.idempotent.key
    return key if key in (annotations.input or ()) else None


def _declared_hook(annotations: Annotations | None) -> str | None:
    """The declared ``compensation.hook``, or ``None`` — §6.4's ``hook`` (⊥ when absent)."""
    if annotations is None or annotations.compensation is None:
        return None
    return annotations.compensation.hook


def _has_retry_policy(annotations: Annotations | None) -> bool:
    """``has(n, retry_policy)`` — presence only (§6.3), never ``max_attempts`` or ``retry_on``.

    This is arm (a) of ``retry_region(n)``, and it is **cycle-independent**: a node declaring a
    retry policy is re-executed by the runtime whether or not the graph loops back to it, so
    §6.4 classifies it ``retry`` with no anchor cycle (§6.3: ``cycle`` is "absent for … the
    retry_policy-only regions"). §6.7 edge case 5 names the shape; the corpus has no fixture for
    it, and DEC-13 left the gap fixture open as a WA-04 item.
    """
    return annotations is not None and annotations.retry_policy is not None


def _fanout(graph: GraphModel, node_id: str) -> Literal["send"] | None:
    """``fanout = "send" if any in-edge of n has kind "send"`` (§6.4 Phase 4).

    The evidence ``mixed/09`` pins: the node is instantiated once per ``Send`` payload, so an
    unprotected effect there is multiplied by the fan-out *and* by the retry rounds. Read off
    the shared model's multigraph in-edge view, where the sentinel wirings are ``normal`` and so
    cannot spoof it.
    """
    return "send" if any(edge.kind == "send" for edge in graph.in_edges(node_id)) else None


def _dangling(hook: str | None, hook_ok: bool) -> str | None:
    """§6.4's ``dangling_compensation_hook = hook if (hook ≠ ⊥ and not hook_ok) else absent``.

    A hook naming no node is **not** protection (DEC-05 D7's side condition; ratified verbatim
    by DEC-13), so the node falls through to the ordinary unprotected-effect condition and the
    bad id rides along as evidence — no new condition ID, the §0.4 registry stays closed
    (§6.7 item 5).

    One narrowing, on a case the frozen texts jointly exclude. IR-SPEC §3.4 types ``hook`` as
    "a node id under the §5 grammar" while ``Compensation.hook`` is an unconstrained ``str``, and
    §6.3 types this evidence field ``Optional[NodeId]`` — so on conforming IR the two always
    agree and this function is §6.4 verbatim. On an IR that breaks §3.4's own typing, emitting
    the field would raise inside the validator on declared content; the evidence is dropped
    instead. Nothing about the verdict moves: an id that breaks the §5 grammar is not in
    ``node_ids`` either, so it was never protection, and the condition, severity and anchor are
    unchanged. Fail-open on an optional diagnostic, never on the finding.
    """
    if hook is None or hook_ok or not is_valid_node_id(hook):
        return None
    return hook


# ── Phase 5 — ordering and the pass witness ──────────────────────────────────────────────


def _phase_five_key(finding: _Finding) -> tuple[int, bytes, bytes]:
    """§6.4 Phase 5's ``(severity: fatal < error, location.node UTF-16, property_condition)``.

    The severity comes off the §0.4 registry, not from where the finding was made, so the
    ordering follows a regrade rather than encoding today's ladder twice. The node comparator is
    the ledger §6 one — UTF-16 code units — which is the order every other list in the report
    already carries.
    """
    condition_id, location = finding
    return (
        _SEVERITY_RANK[condition(condition_id).severity or "warning"],
        ledger_sort_key(location.node),
        ledger_sort_key(condition_id),
    )


def _cycle_inventory(graph: GraphModel) -> tuple[tuple[str, ...], ...]:
    """``cycles=(anchor_cycle(min(S)) for non-trivial S sorted by min id)`` — §6.4 Phase 5.

    One canonical anchor per non-trivial component, so the witness states *where the cycles are*
    without ever enumerating them: §6.5 is explicit that P-06 needs region membership plus one
    deterministic anchor, and that the P-02 output-sensitive blowup is not inherited.
    :attr:`~gebra.verify.graph.Components.members` are already ledger-sorted, so ``members[0]``
    is $\\min(S)$ and this sort is over those minima.
    """
    components = graph.components
    return tuple(
        graph.anchor_cycle(components.members[index][0])
        for index in sorted(
            components.nontrivial, key=lambda index: ledger_sort_key(components.members[index][0])
        )
    )


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _canonical_order(nodes: tuple[Node, ...]) -> list[Node]:
    """``nodes[]`` in ledger §6 canonical order — §6.4's ``sorted by id`` for Phases 1 and 4.

    Canonical IR already arrives in this order, so the sort is defensive; it is not optional,
    because it fixes the witness's ``effects`` order and (with Phase 5) which finding is the
    primary. The comparator is the ledger's UTF-16 one, not Python's default code-point order.
    """
    return sorted(nodes, key=lambda node: ledger_sort_key(node.id))


# Registration is what dispatch runs on, so it happens once, at import (see P-01's note).
register_validator(PROPERTY_SLUG, check_effect_safety)
