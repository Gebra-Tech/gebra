"""``CompiledStateGraph`` / Pregel extraction — the INTROSPECTION-SPEC §4 rule set.

Normative authority: INTROSPECTION-SPEC §4 (§4.1 compiled-level surfaces, §4.2 the
``get_graph()`` demotion, §4.3 the ratified authority ruling), DEC-06 (the ruling's record),
§2 (dispatch and the error posture), §7.1 (which fields are Full at which level), §8 (the
``builder-compiled-divergence`` and ``compiled-only-extraction`` rows), and IR-SPEC §3.7 (the
shape of ``runtime.interrupts``/``runtime.checkpointer``) — all under the §1 never-invokes
discipline.

**Two paths, one family.** §4.3 splits the compiled family in two, and so does this module:

* **Builder-primary** (rules 1–3). ``.builder`` is reachable, so §3 defines topology, state
  schema and per-node declarations — this path *calls* :func:`~gebra.extraction.builder.extract_builder`
  on the backreference rather than re-deriving any of it, which is what makes
  "builder-authoritative-when-available" true by construction instead of by agreement. What the
  compiled level adds is layered on: the ``runtime`` block (§4.1), the provenance facts ir 1.0
  has no slot for, and the §4.2 cross-check.
* **Compiled-only** (rule 4). No ``.builder``, so ``get_graph()`` is the only topology surface
  there is and "every §3-derived field is downgraded one knowability class", recorded by one
  ``compiled-only-extraction`` warning per extraction.

**Folded defaults are already in the builder — and that is a substrate fact, not a choice.**
§4.1: "folded ``set_node_defaults`` (defaults are already folded into node specs
post-``compile()``)". Verified on langgraph 1.2.10: ``compile()`` writes the graph-level
defaults into the builder's *own* ``StateNodeSpec`` objects, in place, and the folded value is
the identical object as the default. So §3's pass over the backreference reads a folded
``retry_policy`` exactly as it reads an authored one — the value needs no work here — and what
this module contributes is the *resolution*: which nodes declared it and which inherited it,
which §4.1 puts "in provenance only — no ir 1.0 slot"
(:class:`~gebra.extraction.envelope.FoldedDefault`). Identity is what tells the two apart, and
it is the only thing that can: after the fold there is no other difference to read.

**``get_graph()`` is the one call this module makes, and it is gated.** §4.3 rule 2 asks
extraction to derive the ``get_graph(xray=True)`` edge set and compare; §4.2 demotes the getter
to exactly that, on the grounds that at the pinned version it is a bounded *symbolic execution*
of the Pregel loop. §1 rule 3 licenses the call and adds that it "stays within never-invokes (no
user code runs)" — **and that parenthetical is false on langgraph 1.2.10**. One drawing reaches
user bodies by five routes (a channel's ``get()``, a checkpointer's ``get_next_version()``, a
node's cache ``key_func``, a ``ChannelWrite`` entry's ``mapper`` — through a literal
``Runnable.invoke`` — and a ``__root__`` channel's ``ValueType()`` called as a constructor), and
one route is not about bodies at all: ``RemoteGraph`` implements ``PregelProtocol`` with no
``.builder``, and *its* ``get_graph()`` performs an HTTP request, which §1 rule 1 forbids
outright. :func:`_drawing_hazard` is the single gate in front of both call sites and names all
six; ``tests/extraction/test_compiled.py`` arms one fixture per route, so the gate is checked
rather than reviewed.

What the gate lets through is a real ``langgraph.pregel.Pregel`` — at the object *and* at every
level ``xray`` would recurse into — all of whose channels, checkpointer, cache key functions and
write mappers come from LangGraph itself. Verified as the boundary rather than assumed: node
functions, routers, pydantic state-schema validators and reducers bound to stock channels are
**not** reached by a drawing.

The two call sites are then graded differently, because their costs are:

* As a **cross-check** the call is SHOULD-grade, so a hazard simply declines it. A SHOULD
  standing down costs a diagnostic; running foreign code costs the invariant the whole package
  rests on. The decline is recorded (:class:`~gebra.extraction.envelope.CrossCheck`), so "no
  divergence warning" never silently means "no comparison ran".
* As the **compiled-only extraction surface** it is the only surface §4.3 rule 4 has, so a
  hazard is a boundary refusal instead. That is §2's own branch rather than a new posture: §2
  raises ``ExtractionError`` for "a Pregel-protocol object with neither ``.builder`` nor a
  usable ``get_graph()``", and a getter that cannot be called without violating a MUST is not a
  usable one. What remains — a gated drawing of a stock ``Pregel`` — still reaches that
  ``Pregel``'s own channels, and *that* residue is pinned by a named test rather than narrated.

**A discovered subgraph is its parent node, and that document is complete** (ratified —
DEC-19, 2026-08-03). §4.1: "ir 1.0 carries a discovered subgraph as its parent node only:
child nodes, child edges, and the child's own ``entry``/``finish``/Σ are NOT emitted; the
discovered-parent set is recorded in the provenance envelope, which is the conforming
disclosure — such a document is complete, carries **no warning** for the unexpansion, and
reaches the §8 strict-mode bar." So the parent set rides
:attr:`~gebra.extraction.envelope.CompiledSurfaces.subgraphs` and nothing is warned: a
subgraph-bearing workflow is as clean as any other, which is what makes strict mode usable on
one. §4.1 also forbids improvising the 1.x form ("extraction MUST NOT improvise any of it in
1.0") — child expansion is the named first 1.x feature and its design register is DEC-19's.
Subgraphs compiled with ``checkpointer=False`` are invisible to discovery (§4.1's documented
blind spot), so the recorded tuple is a lower bound rather than a census, and no warning is
possible for what cannot be seen.

**The §3 non-mirrored node-spec members are not read at all.** §3 marks ``metadata``,
``cache_policy``, ``defer``, ``timeout`` and the error-handler members "read but **not
mirrored** in ir 1.0 (no ledger slot); recorded as candidate 1.x extensions in the D-08 handoff
notes" — a docs disposition, and the handoff note is EX-15's. §4.1 separately puts two
*compiled-level* facts in provenance — ``node_error_handler_map`` and folded-defaults resolution
— and those two are carried here. Not reading what is not mirrored is the same observable
behaviour with one fewer attribute touched.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from langgraph.graph import END, START
from langgraph.pregel import Pregel

from gebra.annotations.inference import SourceCache
from gebra.annotations.sidecar import SidecarReading
from gebra.extraction.base import ObjectFamily, type_identity
from gebra.extraction.builder import END_LABEL, extract_builder
from gebra.extraction.contracts import resolve_node
from gebra.extraction.envelope import (
    CompiledSurfaces,
    CrossCheck,
    ExtractedFrom,
    ExtractionEnvelope,
    FoldedDefault,
)
from gebra.extraction.errors import ExtractionError, ExtractionErrorReason
from gebra.extraction.sidecar import sidecar_warnings, unknown_node_warnings
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode
from gebra.ir.identity import RESERVED_SEGMENTS, NodeIdError, node_id_from_names
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    ConditionalEdge,
    DynamicEdge,
    Edge,
    Interrupts,
    Node,
    NormalEdge,
    Runtime,
    WorkflowIR,
    lowest_ir_version,
)

if TYPE_CHECKING:
    from gebra.extraction.dispatch import Dispatch

__all__ = ["extract_compiled"]

#: The ``All`` sentinel of an interrupt gate list — the literal ``"*"`` (§4.1, A1 §3).
ALL_GATES: Final = "*"

#: The ``xray`` level §4.3 rule 2 names for the cross-check. Recorded on the warning and in
#: provenance because §8's row asks for "xray level used", which presupposes it can vary.
CROSS_CHECK_XRAY: Final = True

#: The separator LangGraph's *drawn* ids use between nesting levels. IR-SPEC §5.1 uses ``/``
#: and §4.2 says the drawn form "maps to ledger path segments"; nothing drawn is ever
#: persisted, so this constant exists only to fold a drawn id back to its top-level node for
#: the cross-check comparison.
DRAWN_SEPARATOR: Final = ":"

#: The top-level package a value must come from for a drawing to be allowed to run it.
#: Anything else is user-authored, and :func:`_drawing_hazard` names the five routes by which
#: ``draw_graph`` would reach its body.
_SUBSTRATE_PACKAGE: Final = "langgraph"

#: The channel key whose ``ValueType`` ``draw_graph`` calls as a constructor (``_draw.py``).
_ROOT_CHANNEL: Final = "__root__"

#: The ``_NodeDefaults`` members that name a ``StateNodeSpec`` member of the same name. The
#: substrate's fourth default (``error_handler``) lands on a synthesized handler node rather
#: than on a same-named spec member, so it has no identity comparison to make.
_FOLDABLE_MEMBERS: Final = ("retry_policy", "cache_policy", "timeout")


def extract_compiled(
    dispatch: Dispatch, /, *, sidecar: SidecarReading | None = None
) -> ExtractionEnvelope:
    """Extract a compiled graph (or any Pregel object) into the core IR and its envelope.

    The §4 rule set. Which of §4.3's two readings applies is already decided — §2's dispatch
    put it in :attr:`~gebra.extraction.dispatch.Dispatch.builder`: present means rules 1–3
    (builder-authoritative, compiled-level facts layered on, cross-check recorded), absent
    means rule 4 (compiled-only, downgraded, warned once).

    Args:
        dispatch: The §2 classification decision. ``workflow`` is the compiled object every
            compiled-level surface is read off and every boundary refusal names; ``builder``
            is the ``.builder`` backreference §4.3 rule 1 routes topology through, or ``None``
            for the rule-4 downgrade.
        sidecar: The ANNOTATION §2 sidecar reading for this extraction, resolved once at the
            entry point. ``None`` — for a direct call that bypasses it — means "no sidecar".

    Returns:
        The envelope: the core IR (now carrying the ``runtime`` block §4.1 makes Full-knowable
        at this level), its provenance including the §4 compiled-only facts, and the warnings.

    Raises:
        ExtractionError: at the object boundary only — a §3 refusal reached through the
            backreference, or a builderless Pregel whose ``get_graph()`` yields no usable
            drawing. Never a silent partial IR (§2).
    """
    if dispatch.builder is None:
        return _extract_compiled_only(dispatch, sidecar=sidecar)
    return _extract_builder_primary(dispatch, sidecar=sidecar)


# ── §4.3 rules 1–3: builder-authoritative, compiled facts layered on ─────────────────────


def _extract_builder_primary(
    dispatch: Dispatch, *, sidecar: SidecarReading | None
) -> ExtractionEnvelope:
    """§4.3 rule 1: "When ``.builder`` is reachable, §3 rules define the IR".

    So §3 runs first and entire, and nothing below rewrites a field it produced — the
    disagreement rule (rule 3) is "builder wins for topology intent; compiled wins for
    what-will-execute", and the only fields taken from the compiled level are the ones §3
    records absent by construction (``runtime``, §7.1) or has no slot for at all (provenance).
    A divergence is *recorded*, never resolved: the warning carries both readings and the IR
    keeps the builder's.
    """
    inner = extract_builder(dispatch, sidecar=sidecar)
    node_ids = tuple(node.id for node in inner.ir.nodes)
    runtime, warnings = _read_runtime(dispatch.workflow, node_ids)
    ir = _with_runtime(inner.ir, runtime)
    check, divergences = _cross_check(dispatch.workflow, ir)
    subgraphs = _discover_subgraphs(dispatch.workflow)
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractedFrom(
            source=type_identity(dispatch.workflow),
            family=ObjectFamily.COMPILED,
            sidecar=inner.extracted_from.sidecar,
            managed_state_keys=inner.extracted_from.managed_state_keys,
            compiled=CompiledSurfaces(
                subgraphs=subgraphs,
                folded_defaults=_folded_defaults(dispatch.builder),
                error_handlers=_error_handlers(dispatch.workflow),
                cross_check=check,
            ),
        ),
        warnings=(*inner.warnings, *warnings, *divergences),
    )


def _with_runtime(ir: WorkflowIR, runtime: Runtime) -> WorkflowIR:
    """The §3 IR with the §4.1 ``runtime`` block attached — a new document, validated.

    Rebuilt rather than mutated: the IR models are frozen (A6 PC-1), and rebuilt through the
    constructor rather than through ``model_copy`` so the result is validated exactly as an
    extraction's own output is. Nothing else moves, which is rule 3 made structural.
    """
    return WorkflowIR(
        ir_version=ir.ir_version,
        entry=ir.entry,
        finish=ir.finish,
        state=ir.state,
        nodes=ir.nodes,
        edges=ir.edges,
        runtime=runtime,
    )


# ── §4.1: the compiled-level surfaces ────────────────────────────────────────────────────


def _read_runtime(
    compiled: object, node_ids: Sequence[str]
) -> tuple[Runtime, tuple[ExtractionWarning, ...]]:
    """The ``runtime`` block §4.1 makes Full-knowable at the compiled level (IR-SPEC §3.7).

    Two of the three sub-slots are read here; the third, ``recursion_limit``, is
    annotation-only (§7.1: "invoke-time config is not on the object"), so it stays absent.

    ``checkpointer`` is emitted **either way** — §4.1: "a known fact either way at compiled
    level, so both values are emitted explicitly; at builder level the slot is absent
    (unknown, never guessed)". That asymmetry is the whole point of the slot, and it is why a
    compiled extraction always carries a ``runtime`` object while a builder one never does.
    """
    interrupts, warnings = _read_interrupts(compiled, node_ids)
    return (
        Runtime(
            recursion_limit=None,
            interrupts=interrupts,
            checkpointer=_checkpointer(compiled),
        ),
        warnings,
    )


def _checkpointer(compiled: object) -> Checkpointer | None:
    """``runtime.checkpointer`` — the §4.1 fact, or absence when it is not readable.

    Two values mean "no checkpointer" on the substrate and they are different declarations:
    ``None`` (none was given) and ``False`` (a subgraph explicitly declining to inherit its
    parent's). ir 1.0 carries one boolean, so both map to ``present: false`` — the slot asks
    whether one is attached, and under neither value is one.

    An object that exposes **no** ``checkpointer`` attribute at all is the third case and is
    not the same as either. §4.1 makes presence a known fact "at compiled level"; a surface
    that cannot be read is not that level knowing, so the slot is left absent — §7.1's "absent
    (never guessed)", which is what the builder level already says. No LangGraph object reaches
    this, but §2 defines the family by the Pregel *protocol*, so a third-party implementation
    can. The distinction lands in ``graph_version``, which is why it is drawn rather than
    collapsed into ``false``.

    Compared with ``is``, never ``==``: a foreign object's ``__eq__`` is arbitrary code, and
    ``x in (None, False)`` would run it.
    """
    missing = object()
    checkpointer = getattr(compiled, "checkpointer", missing)
    if checkpointer is missing:
        return None
    return Checkpointer(present=checkpointer is not None and checkpointer is not False)


def _read_interrupts(
    compiled: object, node_ids: Sequence[str]
) -> tuple[Interrupts | None, tuple[ExtractionWarning, ...]]:
    """``interrupt_before_nodes``/``interrupt_after_nodes`` → ``runtime.interrupts`` (§4.1).

    §4.1 states three rules and all three are here: the ``All`` sentinel (the literal ``"*"``)
    "MUST be expanded to the full extracted node-id list (a static, Full-knowable expansion)";
    "an empty gate list emits no member"; and "no gates at all emits no ``interrupts``
    object" — omit-normalized per IR-SPEC §6.3, which maps an empty array onto absence, so
    emitting one would be writing a form canonicalization erases.

    Members are sorted and **not** de-duplicated. IR-SPEC §6.2 classes both arrays as
    set-valued, so authored order carries no semantics and canonicalization re-sorts before
    hashing — sorting here is what keeps two extractions of one unchanged object equal *as
    models*. Deduping would go further than any §6 rule does: §6.3's representation
    normalizations are an exhaustive list and removing duplicates is not among them, and
    :mod:`gebra.ir.canonical` says so in terms for exactly these arrays. Both slots are in
    ``graph_version`` hash scope, so a local dedup would be a digest-affecting choice no spec
    licenses; carrying what the source declared is the only reading that cannot diverge.
    """
    warnings: list[ExtractionWarning] = []
    before = _gate_ids(compiled, "interrupt_before_nodes", node_ids, warnings)
    after = _gate_ids(compiled, "interrupt_after_nodes", node_ids, warnings)
    if not before and not after:
        return None, tuple(warnings)
    return Interrupts(before=before or None, after=after or None), tuple(warnings)


def _gate_ids(
    compiled: object,
    attribute: str,
    node_ids: Sequence[str],
    warnings: list[ExtractionWarning],
) -> tuple[str, ...]:
    """One interrupt gate list as sorted node ids, expanding the ``All`` sentinel."""
    declared = getattr(compiled, attribute, ())
    if isinstance(declared, str):
        if declared == ALL_GATES:
            # The one place a set *is* the right shape: §4.1's expansion is over "the full
            # extracted node-id list", which has one member per node by construction.
            return tuple(sorted(set(node_ids)))
        # The substrate types the member `All | Sequence[str]` with `All = Literal["*"]`, so a
        # different string is out of its own contract. Iterating it would gate on single
        # characters; naming it is the honest reading, and §8's row covers a known field whose
        # *value* is unmappable.
        warnings.append(
            _unsupported(
                "interrupt-gates-unrecognized",
                f"`{attribute}` holds the string {declared!r}, which is neither the `All` "
                f"sentinel {ALL_GATES!r} nor a list of node names, so no gate is projectable",
                location={"attribute": attribute},
            )
        )
        return ()
    if not isinstance(declared, Iterable):
        warnings.append(
            _unsupported(
                "interrupt-gates-unrecognized",
                f"`{attribute}` holds a {type_identity(declared)}, which is neither the "
                f"`All` sentinel nor an iterable of node names",
                location={"attribute": attribute},
            )
        )
        return ()
    gates: list[str] = []
    for name in declared:
        if not isinstance(name, str):
            warnings.append(
                _unsupported(
                    "interrupt-gate-unrepresentable",
                    f"`{attribute}` names a gate of type {type_identity(name)}; an interrupt "
                    "gate is a node id, and only a string names one",
                    location={"attribute": attribute},
                )
            )
            continue
        node_id = _safe_node_id(name)
        if node_id is None:
            warnings.append(
                _unsupported(
                    "interrupt-gate-unrepresentable",
                    f"`{attribute}` names the gate {name!r}, which has no representable node "
                    "id, so it cannot be recorded as one",
                    location={"attribute": attribute},
                )
            )
            continue
        gates.append(node_id)
    return tuple(sorted(gates))


def _discover_subgraphs(compiled: object) -> tuple[str, ...]:
    """``get_subgraphs()`` → the node ids that carry a discovered subgraph (§4.1).

    The parents, not the children: the children's *ids* are specified (``parent/child``) and
    their *wiring* is not, so recording who has one is everything this build can say honestly.
    Total by construction — a substrate that does not expose the getter, or one whose getter
    yields a shape this cannot read, records no subgraph rather than failing an extraction
    over a provenance field.
    """
    getter = getattr(compiled, "get_subgraphs", None)
    if not callable(getter):
        return ()
    try:
        discovered = list(getter())
    except Exception:  # noqa: BLE001 - provenance never fails an extraction
        return ()
    parents: set[str] = set()
    for item in discovered:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        name = item[0]
        if not isinstance(name, str):
            continue
        node_id = _safe_node_id(name)
        if node_id is not None:
            parents.add(node_id)
    return tuple(sorted(parents))


def _folded_defaults(builder: object) -> tuple[FoldedDefault, ...]:
    """Which node-spec members ``compile()` filled from ``set_node_defaults`` (§4.1).

    The fold is in-place and lossless for the *value*, so the only readable difference between
    an inherited member and an authored one is object identity with the graph-level default —
    which is what this compares. Two consequences, both recorded rather than smoothed:
    an author who passes one policy object to both ``set_node_defaults`` and ``add_node``
    reads back as inheriting it (they did declare the same object), and a substrate that stops
    folding by reference records nothing rather than guessing.

    ``builder._node_defaults`` is a private member and no memo pins it. It is read through
    ``getattr`` with a total fallback for exactly that reason: this is provenance with no ir
    1.0 slot, so a substrate that reshapes it costs a diagnostic, never an extraction.
    """
    defaults = getattr(builder, "_node_defaults", None)
    nodes = getattr(builder, "nodes", None)
    if defaults is None or not isinstance(nodes, Mapping):
        return ()
    try:
        names = sorted(nodes)
    except TypeError:  # a foreign builder whose keys do not order — provenance, so no failure
        return ()
    folded: list[FoldedDefault] = []
    for member in _FOLDABLE_MEMBERS:
        default = getattr(defaults, member, None)
        if default is None:
            continue
        for name in names:
            node_id = _safe_node_id(name)
            if node_id is None:  # pragma: no cover - §3 already refused the name at the boundary
                continue
            if getattr(nodes[name], member, None) is default:
                folded.append(FoldedDefault(node=node_id, member=member))
    return tuple(sorted(folded, key=lambda entry: (entry.node, entry.member)))


def _error_handlers(compiled: object) -> dict[str, str]:
    """``node_error_handler_map`` → node id → handler node id (§4.1, provenance only).

    §4.1 puts this map in provenance in terms — "no ir 1.0 slot; candidate 1.x extensions" —
    so it is recorded as the substrate spells it, with both sides escaped to node ids so a
    consumer can join it against ``nodes[]`` without re-deriving the §5 grammar.
    """
    declared = getattr(compiled, "node_error_handler_map", None)
    if not isinstance(declared, Mapping):
        return {}
    handlers: dict[str, str] = {}
    for node, handler in declared.items():
        if not isinstance(node, str) or not isinstance(handler, str):
            continue
        node_id, handler_id = _safe_node_id(node), _safe_node_id(handler)
        if node_id is not None and handler_id is not None:
            handlers[node_id] = handler_id
    return handlers


# ── §4.2 / §4.3 rule 2: the cross-check ──────────────────────────────────────────────────


@dataclass(frozen=True)
class _Topology:
    """One reading's topology, at the granularity the two levels can be compared at.

    Not an IR: a set-of-incidences view of one, with ``entry``/``finish`` kept as the sentinel
    incidences they are (IR-SPEC §4.2) so that a builder's ``entry`` and a drawing's
    ``__start__`` edges are the same fact in the same slot. ``edges`` is **label-expanded**
    (§4.3 rule 2's own word): each ``path_map`` label is one logical directed edge, which is
    the form the drawn graph is already in.
    """

    nodes: frozenset[str] = frozenset()
    edges: frozenset[tuple[str, str]] = frozenset()
    entry: frozenset[str] = frozenset()
    finish: frozenset[str] = frozenset()
    dynamic_sources: frozenset[str] = frozenset()
    """Nodes the builder reading recorded as ``kind: dynamic`` sources (ir 1.1 — DEC-28).

    Not a fifth thing to compare — the reason the comparison is **declined** on such a document
    (:func:`_cross_check`). §1 rule 3 grades the drawing "heuristic for dynamic branches" (§4.2's own words: "invents implicit conditional edges", "demoted to a cross-check"); what
    is measured rather than inferred is how far that reaches, and it is further than the router:
    at the pinned substrate a graph with a targetless router draws ``__start__ → router`` and
    ``router → __end__`` and **nothing else at all**, dropping every declared edge downstream —
    so the drawn reading is not a cross-check on this document, it is a different graph.
    """

    def reading(self) -> dict[str, Any]:
        """This reading as reportable warning detail, deterministically ordered."""
        return {
            "nodes": tuple(sorted(self.nodes)),
            "edges": tuple(sorted(self.edges)),
            "entry": tuple(sorted(self.entry)),
            "finish": tuple(sorted(self.finish)),
        }


def _cross_check(
    compiled: object, ir: WorkflowIR
) -> tuple[CrossCheck, tuple[ExtractionWarning, ...]]:
    """§4.3 rule 2, with §1 rule 1 given right of way when the two collide.

    Returns the record of whether the comparison happened and, when it did and the readings
    disagreed, the one ``builder-compiled-divergence`` warning §4.3 rule 3 requires. The IR is
    never touched: rule 3 is "any topology divergence leaves the builder-derived IR unchanged".
    """
    declined = _drawing_hazard(compiled, xray=CROSS_CHECK_XRAY)
    if declined is not None:
        return CrossCheck(performed=False, xray=CROSS_CHECK_XRAY, declined=declined), ()
    drawn = _draw(compiled, xray=CROSS_CHECK_XRAY)
    if drawn is None:
        return (
            CrossCheck(
                performed=False,
                xray=CROSS_CHECK_XRAY,
                declined=(
                    "`get_graph()` did not return a readable drawing, so there was nothing to "
                    "compare the builder reading against"
                ),
            ),
            (),
        )
    builder_side = _builder_topology(ir)
    if builder_side.dynamic_sources:
        # §4.3 rule 2 is a SHOULD, and `CrossCheck.declined` exists so that "no divergence
        # warning" never silently means "no comparison ran". Declining rather than comparing is
        # the honest outcome here for a measured reason, not a stylistic one: on a document with
        # a targetless router the drawing does not merely guess the router's branch (§4.2's
        # named heuristic) — it stops there, and every declared edge beyond it is missing from
        # the drawn set. Comparing would report the drawing's own limit as a topology
        # disagreement, on every map-reduce workflow, forever.
        return (
            CrossCheck(
                performed=False,
                xray=CROSS_CHECK_XRAY,
                declined=(
                    "the builder declares a router with no static target set "
                    f"({', '.join(sorted(builder_side.dynamic_sources))}), so `get_graph()`'s "
                    "bounded symbolic execution stops at it and the drawn edge set omits the "
                    "declared topology beyond it; §4.2 grades the drawing heuristic for dynamic "
                    "branches, and a comparison against it would report that limit as a "
                    "divergence"
                ),
            ),
            (),
        )
    compiled_side = _drawn_topology(drawn)
    record = CrossCheck(performed=True, xray=CROSS_CHECK_XRAY)
    deltas = _deltas(builder_side, compiled_side)
    if not deltas:
        return record, ()
    return record, (
        ExtractionWarning(
            code=ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE,
            message=(
                "the compiled-level drawing disagrees with the builder-derived topology "
                f"({', '.join(sorted(deltas))}); the builder reading is authoritative and the "
                "IR is unchanged"
            ),
            detail={
                "builder": builder_side.reading(),
                "compiled": compiled_side.reading(),
                "delta": deltas,
                "xray": CROSS_CHECK_XRAY,
                "authority": (
                    "DEC-06 / INTROSPECTION-SPEC §4.3 rule 3: builder wins for topology "
                    "intent, so the divergence is recorded and the IR keeps the builder "
                    "reading; the compiled drawing is a bounded symbolic execution and is "
                    "heuristic for dynamic branches (§1 rule 3)"
                ),
            },
        ),
    )


def _drawing_hazard(compiled: object, *, xray: bool) -> str | None:
    """Why ``get_graph()`` must not be called on this object, or ``None`` when it may.

    **The single never-invokes gate for both call sites**, and the reason it exists is that
    §1 rule 3's parenthetical — ``get_graph()`` "stays within never-invokes (no user code
    runs)" — is not true of langgraph 1.2.10. Read against ``pregel/_draw.py`` and
    ``pregel/_algo.py``, one call reaches user bodies by five distinct routes, each guarded
    below:

    1. any user ``BaseChannel`` subclass's methods — earliest ``from_checkpoint`` through
       ``channels_from_checkpoint``, then ``apply_writes`` → ``is_available()`` → ``get()``.
    2. ``apply_writes`` → ``checkpointer.get_next_version``, once per write-application — a
       documented override point on ``BaseCheckpointSaver``, and a saver is the object most
       likely to touch a database.
    3. ``prepare_next_tasks(for_execution=True)`` → ``cache_policy.key_func(val)`` — supplied
       by ``add_node(..., cache_policy=...)``, a member §3 already names.
    4. ``ChannelWrite.invoke`` → per-entry ``mapper(value)`` — LangGraph's own for a
       ``StateGraph``-compiled node, user-supplied for a hand-built ``Pregel``.
    5. ``specs["__root__"].ValueType()`` — reads a channel property **and calls the result as
       a constructor**, which is §1 rule 4's first named hazard (pydantic validators).

    And one route that is not about bodies at all: ``langgraph.pregel.remote.RemoteGraph``
    implements ``PregelProtocol`` with no ``.builder``, and its ``get_graph()`` issues
    ``GET /assistants/{id}/graph``. §1 rule 1 forbids opening a network connection outright, so
    the first test below is on the *class*: the drawing may be taken only from a real
    ``langgraph.pregel.Pregel``, never from an arbitrary implementation of the protocol §2
    dispatches on. Every level ``xray`` would recurse into is tested the same way, because each
    is drawn by the same loop.

    Conservative in the safe direction throughout: a surface that cannot be read is a hazard,
    not an absence of one.
    """
    for level, graph in _drawing_scope(compiled, xray=xray):
        if not isinstance(graph, Pregel):
            return (
                f"{level} is not a `langgraph.pregel.Pregel`, so what its `get_graph()` does is "
                "its own business — a `PregelProtocol` implementation may reach the network for "
                "it (`RemoteGraph` does), which INTROSPECTION-SPEC §1 rule 1 forbids outright"
            )
        hazard = _level_hazard(graph)
        if hazard is not None:
            return f"{level} {hazard}"
    return None


def _level_hazard(graph: object) -> str | None:
    """The user-authored object a drawing of ``graph`` would run, named, or ``None``."""
    specs = getattr(graph, "channels", None)
    if not isinstance(specs, Mapping):
        return (
            "exposes no readable channel mapping, so the never-invokes precondition for "
            "running `get_graph()` could not be checked"
        )
    if _ROOT_CHANNEL in specs:
        return (
            f"declares a {_ROOT_CHANNEL!r} channel, whose `ValueType` the drawing reads **and "
            "calls as a constructor** — the pydantic-validator hazard INTROSPECTION-SPEC §1 "
            "rule 4 names first"
        )
    foreign = sorted({type_identity(spec) for spec in specs.values() if not _from_substrate(spec)})
    if foreign:
        return (
            f"binds the user-defined channel class(es) {', '.join(foreign)}, whose methods the "
            "drawing calls — earliest `from_checkpoint`, through `channels_from_checkpoint`, "
            "before any value is asked for"
        )
    checkpointer = getattr(graph, "checkpointer", None)
    if checkpointer is not None and checkpointer is not False and not _from_substrate(checkpointer):
        return (
            f"binds the user-defined checkpointer {type_identity(checkpointer)}, whose "
            "`get_next_version()` the drawing calls once per write-application"
        )
    nodes = getattr(graph, "nodes", None)
    if not isinstance(nodes, Mapping):
        return (
            "exposes no readable node mapping, so the never-invokes precondition for running "
            "`get_graph()` could not be checked"
        )
    for node in nodes.values():
        hazard = _node_hazard(node)
        if hazard is not None:
            return hazard
    return None


def _node_hazard(node: object) -> str | None:
    """The two per-node callables a drawing runs: a cache key function and a write mapper."""
    policy = getattr(node, "cache_policy", None)
    key_func = getattr(policy, "key_func", None) if policy is not None else None
    if key_func is not None and not _from_substrate(key_func):
        return (
            f"binds the user-defined cache key function {type_identity(key_func)}, which the "
            "drawing calls while preparing tasks"
        )
    writers = getattr(node, "writers", None)
    if not isinstance(writers, Iterable):
        return None
    for writer in writers:
        entries = getattr(writer, "writes", None)
        if not isinstance(entries, Iterable):
            continue
        for entry in entries:
            mapper = getattr(entry, "mapper", None)
            if mapper is not None and not _from_substrate(mapper):
                return (
                    f"binds the user-defined write mapper {type_identity(mapper)}, which "
                    "`ChannelWrite.invoke` calls — a `Runnable.invoke` the drawing performs"
                )
    return None


def _drawing_scope(compiled: object, *, xray: bool) -> tuple[tuple[str, object], ...]:
    """Every object a drawing at this ``xray`` level would run the Pregel loop over.

    ``Pregel.get_graph`` gathers subgraphs **only when ``xray`` is set** — with it off, the
    drawing is one level deep and what is below is never touched. So the scan is scoped the
    same way: widening it would refuse a compiled-only extraction over a subgraph the drawing
    would not have looked at, which is conservative in the *wrong* direction — it costs the
    extraction without buying any safety.
    """
    scope: list[tuple[str, object]] = [("the compiled graph", compiled)]
    if not xray:
        return tuple(scope)
    getter = getattr(compiled, "get_subgraphs", None)
    if not callable(getter):
        return tuple(scope)
    try:
        discovered = list(getter(recurse=True))
    except Exception:  # noqa: BLE001 - an unreadable subgraph surface is a hazard, below
        return (*scope, ("a subgraph whose discovery surface could not be read", None))
    for item in discovered:
        if isinstance(item, tuple) and len(item) == 2:
            scope.append((f"the subgraph at {item[0]!r}", item[1]))
    return tuple(scope)


def _from_substrate(value: object) -> bool:
    """Whether ``value`` comes from LangGraph itself rather than from the user.

    ``__module__`` off the value where it has one of its own — a function or a class carries
    it, and that is what a mapper or a key function is — and off its type otherwise, which is
    where an *instance* of a channel or a saver answers from. A value that answers with
    anything but a string is treated as foreign: this is the safe direction, and it is the
    answer an exotic metaclass gets rather than an ``AttributeError`` out of ``extract()``.
    """
    module = getattr(value, "__module__", None)
    if not isinstance(module, str):
        module = getattr(type(value), "__module__", None)
    return isinstance(module, str) and module.partition(".")[0] == _SUBSTRATE_PACKAGE


def _draw(compiled: object, *, xray: bool) -> object | None:
    """``get_graph()``, called once and totally — the §4.2 cross-check/extraction surface.

    ``except Exception`` rather than a bare call because the drawing is a 250-step bounded
    symbolic execution of a foreign object; a substrate that raises inside it must cost a
    diagnostic, not an extraction. It is deliberately **not** ``BaseException``: a tripwire
    sentinel that derives from ``BaseException`` must escape this, and the fixtures that
    derive from ``Exception`` record before they raise so a swallowed one still fails the run.
    """
    getter = getattr(compiled, "get_graph", None)
    if not callable(getter):
        return None
    try:
        drawn: object = getter(xray=xray)
    except Exception:  # noqa: BLE001 - see the docstring: a drawing never fails an extraction
        return None
    return drawn


def _builder_topology(ir: WorkflowIR) -> _Topology:
    """The builder-derived reading, label-expanded (§4.3 rule 2).

    A ``dynamic`` edge contributes no incidence — it declares no target to expand — and is
    recorded in :attr:`_Topology.dynamic_sources` instead, which is what keeps the drawing's
    invented branch out of the delta rather than out of sight.
    """
    edges: set[tuple[str, str]] = set()
    finish: set[str] = set(_sentinel_members(ir.finish))
    dynamic_sources: set[str] = set()
    for edge in ir.edges:
        source = getattr(edge, "from_", None) or ""
        if isinstance(edge, NormalEdge):
            edges.add((source, edge.to))
            continue
        if isinstance(edge, ConditionalEdge):
            for target in edge.path_map.values():
                if target == END_LABEL:
                    finish.add(source)
                else:
                    edges.add((source, target))
            continue
        if isinstance(edge, DynamicEdge):
            dynamic_sources.add(source)
            continue
        edges.add((source, edge.to))
    return _Topology(
        nodes=frozenset(node.id for node in ir.nodes),
        edges=frozenset(edges),
        entry=frozenset(_sentinel_members(ir.entry)),
        finish=frozenset(finish),
        dynamic_sources=frozenset(dynamic_sources),
    )


def _sentinel_members(wired: str | Sequence[str]) -> tuple[str, ...]:
    """``entry``/``finish`` in either canonical representation, as a tuple (IR-SPEC §6.3)."""
    return (wired,) if isinstance(wired, str) else tuple(wired)


def _drawn_topology(drawn: object) -> _Topology:
    """The compiled-level reading, folded to the granularity the builder reading is at.

    Two normalizations, both inside §4.3 rule 2's "modulo ``__start__``/``__end__`` and known
    implicit-edge heuristics":

    * A drawn id is folded to its first ``:``-separated segment. §4.2: "Drawn ``:``-prefixed
      ids map to ledger path segments" — under ``xray`` the drawing expands *inside* the
      subgraphs the builder reading holds as single nodes, so folding is what puts the two
      readings at one granularity instead of reporting the expansion itself as a disagreement.
    * An edge whose endpoints fold to one node **and** at least one of whose endpoints was
      expanded is subgraph-internal — an artifact of that expansion with no counterpart at
      this level. A genuine top-level self-loop has neither endpoint expanded and survives,
      which is why the test is on the expansion rather than on the folded equality alone.
    """
    edges: set[tuple[str, str]] = set()
    entry: set[str] = set()
    finish: set[str] = set()
    nodes: set[str] = set()
    for identifier in _drawn_node_ids(drawn):
        folded = _fold(identifier)
        if folded is not None:
            nodes.add(folded)
    for source, target in _drawn_edges(drawn):
        expanded = DRAWN_SEPARATOR in source or DRAWN_SEPARATOR in target
        if source == START and target == END:
            continue
        if source == START:
            folded = _fold(target)
            if folded is not None:
                entry.add(folded)
            continue
        if target == END:
            folded = _fold(source)
            if folded is not None:
                finish.add(folded)
            continue
        head, tail = _fold(source), _fold(target)
        if head is None or tail is None or (expanded and head == tail):
            continue
        edges.add((head, tail))
    return _Topology(
        nodes=frozenset(nodes),
        edges=frozenset(edges),
        entry=frozenset(entry),
        finish=frozenset(finish),
    )


def _fold(identifier: str) -> str | None:
    """A drawn id as the top-level node id it belongs to, or ``None`` when it is a sentinel."""
    top = identifier.partition(DRAWN_SEPARATOR)[0]
    if top in RESERVED_SEGMENTS:
        return None
    return _safe_node_id(top)


def _drawn_node_ids(drawn: object) -> tuple[str, ...]:
    """The drawn graph's node ids. Reads two attributes and calls nothing."""
    nodes = getattr(drawn, "nodes", None)
    if not isinstance(nodes, Mapping):
        return ()
    return tuple(identifier for identifier in nodes if isinstance(identifier, str))


def _drawn_edges(drawn: object) -> tuple[tuple[str, str], ...]:
    """The drawn graph's ``(source, target)`` pairs. Reads attributes and calls nothing."""
    edges = getattr(drawn, "edges", None)
    if not isinstance(edges, Iterable):
        return ()
    pairs: list[tuple[str, str]] = []
    for edge in edges:
        source = getattr(edge, "source", None)
        target = getattr(edge, "target", None)
        if isinstance(source, str) and isinstance(target, str):
            pairs.append((source, target))
    return tuple(pairs)


def _deltas(builder: _Topology, compiled: _Topology) -> dict[str, Any]:
    """What the two readings disagree about, in both directions; empty when they agree."""
    deltas: dict[str, Any] = {}
    for name, left, right in (
        ("nodes", builder.nodes, compiled.nodes),
        ("edges", builder.edges, compiled.edges),
        ("entry", builder.entry, compiled.entry),
        ("finish", builder.finish, compiled.finish),
    ):
        only_builder = tuple(sorted(left - right))
        only_compiled = tuple(sorted(right - left))
        if only_builder:
            deltas[f"{name}_only_in_builder"] = only_builder
        if only_compiled:
            deltas[f"{name}_only_in_compiled"] = only_compiled
    return deltas


# ── §4.3 rule 4: the compiled-only downgrade ─────────────────────────────────────────────


@dataclass
class _DrawnReading:
    """What one pass over a drawn graph has read — the compiled-only counterpart of §3's."""

    node_ids: dict[str, str] = field(default_factory=dict)
    normal_edges: set[tuple[str, str]] = field(default_factory=set)
    conditional_edges: list[Edge] = field(default_factory=list)
    entry: set[str] = field(default_factory=set)
    finish: set[str] = field(default_factory=set)
    warnings: list[ExtractionWarning] = field(default_factory=list)
    end_labelled: bool = False


def _extract_compiled_only(
    dispatch: Dispatch, *, sidecar: SidecarReading | None
) -> ExtractionEnvelope:
    """§4.3 rule 4: "A Pregel object with no ``.builder`` extracts compiled-only".

    "…with every §3-derived field downgraded one knowability class; the downgrade is recorded
    by the ``compiled-only-extraction`` warning (§8), emitted once per extraction." Read
    against §7.1, that sentence fixes what this path may and may not say:

    * **Topology** is Full at builder level and is taken here from a bounded symbolic
      execution, so it lands one class down — Declared-trusted, which is what the warning
      records. It is what the drawing declares, with no target invented.
    * **Σ** has no source at all. §3's ``state`` row reads a ``StateGraph``'s channels *and*
      its schemas and input schema; a raw Pregel carries channels with no declaration of which
      of them are state, and no spec states the difference. So ``state`` is absent — §0's
      Runtime-only discipline, "the IR MUST model its absence honestly, never guess" — rather
      than a guess dressed as a downgrade.
    * **Contracts** are resolved with no bound object. §3 reaches the decorator and
      tool-carried tiers through ``StateNodeSpec.runnable``, which this family has no
      counterpart for that any spec names, so those tiers withdraw and the D-011 defaults
      apply — §7.1's "Declared-trusted; D-011 default → Inferred-warned" is *literally* the
      one-class downgrade, so this is the rule applied rather than a second decision. The
      ``gebra.toml`` tier still applies: a sidecar is a §2 surface, not a §3-derived field,
      and dropping a declaration an author wrote in a file would be a silent loss.

    The compiled-level slots are **not** downgraded: ``runtime.interrupts`` and
    ``runtime.checkpointer`` are Full "at the compiled level only" (§7.1), and this *is* that
    level.
    """
    workflow = dispatch.workflow
    hazard = _drawing_hazard(workflow, xray=False)
    if hazard is not None:
        raise ExtractionError.for_object(
            workflow,
            "this Pregel object has no `.builder` backreference, and its `get_graph()` — the "
            f"only surface §4.3 rule 4 has — cannot be called: {hazard}. INTROSPECTION-SPEC §1 "
            "rule 1 is a MUST and §2's own dispatch already refuses a Pregel-protocol object "
            "with no usable `get_graph()`, so this build refuses rather than running it",
            reason=ExtractionErrorReason.NO_EXTRACTABLE_SURFACE,
            family=ObjectFamily.COMPILED,
        )
    drawn = _draw(workflow, xray=False)
    if drawn is None:
        raise ExtractionError.for_object(
            workflow,
            "this Pregel object has no `.builder` backreference and its `get_graph()` did not "
            "return a readable drawing, so there is no surface to extract from "
            "(INTROSPECTION-SPEC §2, §4.3 rule 4)",
            reason=ExtractionErrorReason.NO_EXTRACTABLE_SURFACE,
            family=ObjectFamily.COMPILED,
        )
    annotations = SidecarReading() if sidecar is None else sidecar
    reading = _read_drawn(drawn, workflow=workflow)
    if not reading.node_ids:
        raise ExtractionError.for_object(
            workflow,
            "this graph draws no node, so there is nothing to extract: the IR requires at "
            "least one node (IR-SPEC §2.1, INTROSPECTION-SPEC §2)",
            reason=ExtractionErrorReason.EMPTY_NODE_SET,
            family=ObjectFamily.COMPILED,
        )
    node_ids = tuple(sorted(reading.node_ids.values()))
    contracts, contract_warnings = _resolve_without_builder(node_ids, annotations)
    runtime, runtime_warnings = _read_runtime(workflow, node_ids)
    edges: tuple[Edge, ...] = (
        *(
            NormalEdge(kind="normal", **{"from": source}, to=target)
            for source, target in sorted(reading.normal_edges)
        ),
        *reading.conditional_edges,
    )
    ir = WorkflowIR(
        # IR-SPEC §8's minimal stamping, through the one helper rather than a literal: this
        # path draws rather than reads declarations, so it emits no `dynamic` edge today and
        # the answer is "1.0" — said by the policy, so a future drawn-router reading cannot
        # leave a stale version behind it.
        ir_version=lowest_ir_version(edges),
        entry=_collapse(reading.entry),
        finish=_collapse(reading.finish),
        state=None,
        nodes=tuple(Node(id=node_id, annotations=contracts.get(node_id)) for node_id in node_ids),
        edges=edges,
        runtime=runtime,
    )
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractedFrom(
            source=type_identity(workflow),
            family=ObjectFamily.COMPILED,
            sidecar=None if annotations.path is None else str(annotations.path),
            compiled=CompiledSurfaces(
                subgraphs=_discover_subgraphs(workflow),
                error_handlers=_error_handlers(workflow),
            ),
        ),
        warnings=(
            *sidecar_warnings(annotations),
            _compiled_only_warning(workflow),
            *reading.warnings,
            *runtime_warnings,
            *contract_warnings,
            *unknown_node_warnings(annotations, node_ids),
        ),
    )


def _compiled_only_warning(workflow: object) -> ExtractionWarning:
    """The one ``compiled-only-extraction`` record — "emitted once per extraction" (§8).

    Once is structural rather than counted: this is the single construction site, called from
    the single place §2's dispatch can reach the rule-4 path.
    """
    return ExtractionWarning(
        code=ExtractionWarningCode.COMPILED_ONLY_EXTRACTION,
        message=(
            f"{type_identity(workflow)} exposes no `.builder` backreference, so it was "
            "extracted from the compiled level alone and every builder-derived field is one "
            "knowability class less certain"
        ),
        detail={
            "object_type": type_identity(workflow),
            "extraction_level": "compiled",
            "downgrade": (
                "every §3-derived field *with a compiled-level source* drops one knowability "
                "class, Runtime-only being the lattice floor: topology comes from "
                "`get_graph()`, a bounded symbolic execution of the Pregel loop, so it is "
                "Declared-trusted rather than Full"
            ),
            "absent": ("state",),
            "state_absent": (
                "Σ's only source is builder-level, so §4.3 rule 4's downgrade does not reach "
                "it and §0's never-guess discipline governs: a raw Pregel declares nowhere "
                "which channels are Σ, and `get_input_jsonschema()` is not a Σ source — it "
                "reflects the input schema, is not total (a single-channel object answers a "
                "bare string schema), and the channel mapping mixes state with plumbing "
                "(ratified — DEC-19)"
            ),
            "contracts_defaulted": (
                "the decorator and tool-carried tiers are reached through "
                "`StateNodeSpec.runnable`, which this family has no counterpart for, so those "
                "tiers withdraw and the D-011 defaults apply; a `gebra.toml` entry still wins "
                "its slots"
            ),
        },
    )


def _resolve_without_builder(
    node_ids: Sequence[str], sidecar: SidecarReading
) -> tuple[dict[str, Annotations], tuple[ExtractionWarning, ...]]:
    """The ANNOTATION §3 chain with no bound object — sidecar tier plus the D-011 defaults."""
    contracts: dict[str, Annotations] = {}
    warnings: list[ExtractionWarning] = []
    cache = SourceCache()
    for node_id in node_ids:
        resolved = resolve_node(
            node_id,
            None,
            sidecar_entry=sidecar.entries.get(node_id),
            state_schema=None,
            cache=cache,
        )
        members = {
            slot: resolved.contract.slot_value(slot) for slot in resolved.contract.declared_slots()
        }
        # The empty case is unreachable while §4's D-011 defaults fill `pure`/`effect` for every
        # node, and it is kept because that is a property of the *chain*, not of this loop: an
        # empty `Annotations` object is not the same document as no annotations at all (§6.3).
        if members:  # pragma: no branch
            contracts[node_id] = Annotations.model_validate(members)
        warnings.extend(resolved.warnings)
    return contracts, tuple(warnings)


def _read_drawn(drawn: object, *, workflow: object) -> _DrawnReading:
    """One pass over a drawn graph — the compiled-only topology reading.

    The drawn graph is already in the label-expanded form the IR's ``path_map`` denotes, so
    the pass groups its conditional edges back per source: a drawn edge's ``data`` **is** the
    ``path_map`` label the declaration carried (verified on langgraph 1.2.10), and an
    unlabelled one falls to the identity map ``{target: target}`` — the substrate's own
    conversion for a list-valued ``path_map``, and the convention §3's ``ends`` row already
    reads across. No ``condition`` is emitted: ``condition`` is "the declared branch name" and
    a drawing carries none, so inventing one would put a string this build made up inside
    ``graph_version``.
    """
    reading = _DrawnReading()
    for identifier in _drawn_node_ids(drawn):
        if identifier in RESERVED_SEGMENTS:
            continue
        node_id = _safe_node_id(identifier)
        if node_id is None:
            reading.warnings.append(
                _unsupported(
                    "drawn-node-unrepresentable",
                    f"the drawn node {identifier!r} has no representable node id, so it cannot "
                    "be carried",
                    location={"node": identifier},
                    ir_partial=True,
                )
            )
            continue
        reading.node_ids[identifier] = node_id
    routers: dict[str, dict[str, str]] = {}
    for edge in _drawn_edge_records(drawn):
        _read_drawn_edge(edge, reading, routers)
    for source in sorted(routers):
        path_map = routers[source]
        # A source only enters `routers` by having a label written to it, so the empty case is
        # unreachable — and it is kept because DEC-18 ruled `path_map: {}` out *in terms*, so
        # emitting one is the failure this guard names rather than a defensive nicety.
        if path_map:  # pragma: no branch
            reading.conditional_edges.append(
                ConditionalEdge(kind="conditional", **{"from": source}, path_map=path_map)
            )
    _warn_missing_wiring(reading)
    return reading


@dataclass(frozen=True)
class _DrawnEdge:
    """One drawn edge, read down to the three members the IR can use."""

    source: str
    target: str
    label: str | None
    conditional: bool


def _drawn_edge_records(drawn: object) -> tuple[_DrawnEdge, ...]:
    """The drawn edges as records. Attribute reads only; nothing on the edge is called."""
    edges = getattr(drawn, "edges", None)
    if not isinstance(edges, Iterable):
        return ()
    records: list[_DrawnEdge] = []
    for edge in edges:
        source = getattr(edge, "source", None)
        target = getattr(edge, "target", None)
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        label = getattr(edge, "data", None)
        records.append(
            _DrawnEdge(
                source=source,
                target=target,
                label=label if isinstance(label, str) and label else None,
                conditional=getattr(edge, "conditional", False) is True,
            )
        )
    return tuple(sorted(records, key=lambda record: (record.source, record.target)))


def _read_drawn_edge(
    edge: _DrawnEdge, reading: _DrawnReading, routers: dict[str, dict[str, str]]
) -> None:
    """One drawn edge into the reading: a sentinel incidence, a normal edge, or a router row."""
    if edge.source == START and edge.target == END:
        reading.warnings.append(
            _unsupported(
                "start-to-end-edge",
                "the drawing wires START directly to END; ir 1.0 records sentinel incidences "
                "through `entry`/`finish` node ids, and neither sentinel is a node id",
                location={"edge": {"from": START, "to": END}},
                ir_partial=True,
            )
        )
        return
    if edge.source == START:
        target = _drawn_reference(edge.target, reading, where="entry wiring")
        if target is not None:
            reading.entry.add(target)
        return
    if edge.target == END:
        source = _drawn_reference(edge.source, reading, where="finish wiring")
        if source is None:
            return
        if edge.conditional and edge.label is not None:
            routers.setdefault(source, {})[_path_map_label(edge.label)] = END_LABEL
            reading.end_labelled = True
        else:
            reading.finish.add(source)
        return
    source = _drawn_reference(edge.source, reading, where="edge source")
    target = _drawn_reference(edge.target, reading, where="edge target")
    if source is None or target is None:
        return
    if edge.conditional:
        label = edge.label if edge.label is not None else edge.target
        routers.setdefault(source, {})[_path_map_label(label)] = target
        return
    reading.normal_edges.add((source, target))


def _drawn_reference(identifier: str, reading: _DrawnReading, *, where: str) -> str | None:
    """A drawn endpoint as a node id, or ``None`` when it has no ir 1.0 form."""
    if identifier in RESERVED_SEGMENTS:
        reading.warnings.append(
            _unsupported(
                "reserved-drawn-target",
                f"the drawing's {where} names the reserved sentinel {identifier!r}; ir 1.0 has "
                "no carrier for it and the segment is never emitted",
                location={"reference": identifier},
                ir_partial=True,
            )
        )
        return None
    node_id = _safe_node_id(identifier)
    if node_id is None:
        reading.warnings.append(
            _unsupported(
                "drawn-node-unrepresentable",
                f"the drawing's {where} names {identifier!r}, which has no representable node id",
                location={"reference": identifier},
                ir_partial=True,
            )
        )
    return node_id


def _warn_missing_wiring(reading: _DrawnReading) -> None:
    """The §2 missing-wiring warnings, read off the drawing instead of off a builder.

    Scoped exactly as DEC-18 scoped them: the finish side fires only when the drawing shows no
    END incidence of either kind, so a graph that reaches END only through a labelled router
    row is ``finish: []`` and warning-free.
    """
    if not reading.entry:
        reading.warnings.append(
            _unsupported(
                "missing-start-wiring",
                "the drawing wires START to no node, so no entry point is statically knowable",
                location={"sentinel": START},
                ir_partial=True,
            )
        )
    if not reading.finish and not reading.end_labelled:
        reading.warnings.append(
            _unsupported(
                "missing-finish-wiring",
                "the drawing wires no node to END and no router row targets it, so no terminal "
                "wiring is statically knowable",
                location={"sentinel": END},
                ir_partial=True,
            )
        )


def _collapse(wired: set[str]) -> str | tuple[str, ...]:
    """A wired sentinel set in its canonical representation (IR-SPEC §6.3)."""
    if len(wired) == 1:
        return next(iter(wired))
    return tuple(sorted(wired))


# ── shared helpers ───────────────────────────────────────────────────────────────────────


def _path_map_label(label: str) -> str:
    """A drawn router label as an IR ``path_map`` key — NFC-normalized, never coerced.

    The same forced reading :func:`gebra.extraction.builder._path_map_label` applies one level
    up, and for the same reason: IR-SPEC §6.3 puts ``path_map`` labels in the NFC identifier
    role and canonicalization **refuses** a label that is not in that form rather than
    normalizing one, so emitting the drawn bytes verbatim would produce an IR that §2 says must
    exist and that raises ``CanonicalizationError`` the moment anyone asks it for a
    ``graph_version``.

    The **unlabelled** row's fallback is the drawn *source name*, normalized here and escaped
    nowhere — deliberately the same spelling ``_read_declared_destinations`` produces for the
    equivalent tuple-valued ``ends`` (label = the declared name, value = its escaped node id),
    so one graph read through the builder and through its own drawing produces one
    ``path_map``. Keying it with the escaped id instead would put two spellings of one routing
    declaration into ``graph_version``.
    """
    return unicodedata.normalize("NFC", label)


def _safe_node_id(name: str) -> str | None:
    """A source name as an IR node id, or ``None`` when the §5 grammar admits none.

    Total where :func:`gebra.extraction.builder._node_id` refuses, and deliberately so: every
    caller here is either a diagnostic (the cross-check, provenance) or a drawn reference the
    §2 error posture keeps inside the IR as a warning. Refusing an extraction over a name the
    §3 pass already accepted would be the compiled level overruling the builder, which §4.3
    rule 1 forbids.
    """
    try:
        return node_id_from_names([name])
    except NodeIdError:
        return None


def _unsupported(
    construct: str,
    why: str,
    *,
    location: Mapping[str, Any],
    ir_partial: bool = False,
    node: str | None = None,
) -> ExtractionWarning:
    """One ``unsupported-construct`` carrying its §8 row's four facts."""
    return ExtractionWarning(
        code=ExtractionWarningCode.UNSUPPORTED_CONSTRUCT,
        message=f"{construct}: {why}",
        node=node,
        detail={
            "construct": construct,
            "location": dict(location),
            "why": why,
            "ir_partial": ir_partial,
        },
    )
