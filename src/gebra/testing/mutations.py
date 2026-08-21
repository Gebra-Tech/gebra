"""Mutation operators that break exactly one property — D-10 W7/W10.

Where :mod:`gebra.testing.strategies` generates *well-formed* IR, this module rewrites one
into IR that carries one deliberate defect, together with the statement of what the validator
that owns it must say::

    from gebra.testing.mutations import dataflow_mutations

    @given(mutation=dataflow_mutations())
    def test_p04_reports_what_the_operator_injected(mutation: Mutation) -> None:
        assert check_dataflow_completeness(mutation.origin).result == "pass"
        report = check_dataflow_completeness(mutation.ir)
        assert (report.failure is None) == (mutation.condition is None)

A :class:`Mutation` is that pair plus its prediction: :attr:`~Mutation.origin` — the
*normalized* draw, on which the target property passes — and :attr:`~Mutation.ir`, on which the
target property must say exactly what :attr:`~Mutation.condition`, :attr:`~Mutation.node` and
:attr:`~Mutation.key` state. A ``condition`` of ``None`` means the operator is **coherent**: the
target property must still pass, which is what makes a repair testable in the same shape as a
break.

**"Breaks exactly one property", stated so it can be checked.** D-10 In-Scope 4 asks for
"mutation strategies that break exactly one property". The checkable form of that is a statement
about the *pair*, not about the mutant alone: between ``origin`` and ``ir``, the only property
whose verdict moves is the operator's target, and it moves exactly when ``condition`` is not
``None``. Every operator here is built to satisfy it, which is why each family normalizes the
draw first (:func:`without_reads`, :func:`without_effects`, :func:`without_determinism`) rather
than mutating whatever the draw happened to carry: a draw may already fail the property under
test, and then "the mutation broke it" would be unfalsifiable. Three consequences are worth
naming because they are where the operators earn that claim:

* the P-06 operators introduce their state keys with ``optional: true``, so the read they add is
  in P-04's boundary set $I_0$ and P-04's verdict cannot move (§4.2 "Graph inputs");
* the P-06 operators write their unbound idempotency key into ``output`` and never into
  ``input`` — a key that is not among the node's declared reads is not protection (§6.4 Phase 4,
  the ``mixed/06`` precedent) — because *removing* a read would move P-04's verdict;
* the P-08 operators **extend** a node's effect tuple rather than replacing it, so the
  ``{billable, irreversible}`` trigger set P-06 reads is untouched (§6.3).

**What is deliberately not preserved.** Two operators produce documents that break an IR-SPEC
§2.3 cross-field obligation on purpose, because the frozen text says what the validator does
with exactly that shape: :func:`foreign_read` declares a read of a key outside $\\Sigma$ (§4.4
Step 4 ``continue``s past it — "Σ-membership is P-03's finding") and :func:`unbound_key`
declares ``idempotent: {key}`` naming a key that is not an input (§6.4 Phase 4, and ``mixed/06``
is the in-corpus precedent). A third, :func:`unqualified_variant`, declares ``variant.key``
naming a key outside $\\Sigma$ — **not** a §2.3 obligation, since IR-SPEC §3.3 fixes only the
field names and delegates the semantics; the membership requirement is T-W-SPEC §2.3's, and it
is enforced by §4 path 4's ``variant-key-not-in-state`` note rather than by IR validation. Each
is named at its operator rather than left for a reader to discover.

**The one family whose mutants are NOT well-formed**, and the property that says so.
:data:`WELL_FORMEDNESS_OPERATORS` breaks the topology itself, so a breaking P-01 mutation
produces a document P-01 refuses — and §0.3 puts the other properties' results on P-01-dirty
topology outside the defined result surface ("cross-validator agreement on ill-formed input is
NOT promised"). :attr:`Mutation.well_formed` is the flag a metaproperty scopes on, so a
cross-cutting claim about *every* operator can stay true without quietly asserting something
§0.3 declines to promise. Every other family's mutants are still P-01 clean and still
canonicalizable.

**Scope.** All five wedge properties, in two halves. TE-10 built the contract and advisory
operators — P-04 ``dataflow-completeness``, P-06 ``effect-safety``, P-08 ``determinism-replay``
— and TE-09 the structural ones: P-01 ``graph-well-formed`` (:data:`WELL_FORMEDNESS_OPERATORS`)
and P-02 ``termination-witness`` (:data:`TERMINATION_OPERATORS`), on the same :class:`Mutation`
record widened by one location-valued slot.

Nothing in this module imports langgraph or langchain, opens a socket, or executes a workflow
node, a model call or any document content: it reads frozen pydantic values and builds new
frozen pydantic values through the constructors (never ``model_construct``, banned by memo A6
PC-6). The guard strings the P-02 operators write are *declared text* — assembled from a format
string and never parsed as Python here or anywhere else (T-W-SPEC §3 matches syntax with
:mod:`re`). The one thing this module *runs* is
:func:`~gebra.verify.graph.build_graph_model`, in the acyclicity precondition shared by
:func:`unprotected_cycle` and every P-02 operator — VAL-03's hermetic in-repo pre-analysis over
serialized IR. The tripwire is ``tests/testing/test_hermeticity.py``, whose guarded child draws
a mutation from each family and runs the five wedge validators over it in an interpreter where a
substrate import, a socket and a name resolution each raise.

Like :mod:`gebra.testing.strategies`, this module needs ``hypothesis`` — a development
dependency — so it is not imported by :mod:`gebra.testing`'s package body, and importing it
without hypothesis installed raises an :class:`ImportError` that says so.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import pairwise
from typing import Any, Final

try:
    from hypothesis import strategies as st
except ImportError as error:  # pragma: no cover - the dev environment always has it
    raise ImportError(
        "gebra.testing.mutations needs hypothesis, which gebra declares as a development "
        "dependency rather than a runtime one: install it with `pip install hypothesis` (or "
        '`pip install "gebra[dev]"`). Every other module in gebra.testing works without it.'
    ) from error

from gebra.ir.identity import is_valid_node_id
from gebra.ir.models import (
    Annotations,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    Edge,
    IdempotentKey,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    StateField,
    Variant,
    WorkflowIR,
)
from gebra.testing.strategies import DEFAULT_ENVELOPE, SizeEnvelope, workflow_irs
from gebra.verify.base import ConditionId, PropertySlug, to_display
from gebra.verify.graph import START_VERTEX, build_graph_model, ledger_sort_key
from gebra.verify.locations import (
    AnyLocation,
    GuardEdgeLabels,
    NodeLocation,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
)
from gebra.verify.properties.dataflow_completeness import (
    PROPERTY_SLUG as DATAFLOW_SLUG,
)
from gebra.verify.properties.dataflow_completeness import (
    READ_KEY_NEVER_WRITTEN_ON_PATH,
)
from gebra.verify.properties.determinism_replay import (
    LLM_EVIDENCE_TAGS,
    SEED_UNPINNED,
    TEMPERATURE_UNPINNED,
)
from gebra.verify.properties.determinism_replay import (
    PROPERTY_SLUG as DETERMINISM_SLUG,
)
from gebra.verify.properties.effect_safety import (
    IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
    TRIGGER_TAGS,
    UNPROTECTED_EFFECT_IN_CYCLE,
    UNPROTECTED_EFFECT_IN_RETRY_REGION,
)
from gebra.verify.properties.effect_safety import (
    PROPERTY_SLUG as EFFECT_SAFETY_SLUG,
)
from gebra.verify.properties.graph_well_formed import (
    DEAD_END_NODE_NOT_WIRED_TO_END,
    EDGE_TARGET_UNDEFINED,
    NODE_UNREACHABLE_FROM_START,
    ORPHAN_NODE,
    PATH_MAP_TARGET_UNDEFINED,
)
from gebra.verify.properties.graph_well_formed import (
    PROPERTY_SLUG as WELL_FORMEDNESS_SLUG,
)
from gebra.verify.properties.termination_witness import (
    COUNTER_GUARD_WITHOUT_EXIT_EDGE,
    CYCLE_WITHOUT_TERMINATION_WITNESS,
)
from gebra.verify.properties.termination_witness import (
    PROPERTY_SLUG as TERMINATION_SLUG,
)

__all__ = [
    "DATAFLOW_OPERATORS",
    "DETERMINISM_OPERATORS",
    "EFFECT_SAFETY_OPERATORS",
    "OPERATORS",
    "PROBE_BOUND",
    "PROBE_COUNTER",
    "PROBE_ELSE_LABEL",
    "PROBE_HOOK",
    "PROBE_JUSTIFICATION",
    "PROBE_KEY",
    "PROBE_LABEL",
    "PROBE_MEASURE",
    "PROBE_NODE",
    "PROBE_RECURSION_LIMIT",
    "PROBE_TARGET",
    "PROBE_THEN_LABEL",
    "TERMINATION_OPERATORS",
    "WELL_FORMEDNESS_OPERATORS",
    "Mutation",
    "acyclic_envelope",
    "bare_claim",
    "bound_key",
    "boundary_read",
    "chain_wiring",
    "compensation_hook",
    "counter_guard_with_exit",
    "counter_guard_without_exit",
    "dangling_hook",
    "dataflow_mutations",
    "dead_end_node",
    "determinism_mutations",
    "disclaimed_determinism",
    "effect_safety_mutations",
    "empty_entry",
    "forbidden_combination",
    "foreign_read",
    "local_claim",
    "mutations",
    "orphan_node",
    "permute_nodes",
    "pinned_claim",
    "removed_blanket",
    "removed_variant",
    "self_write",
    "severed_edge",
    "star_wiring",
    "termination_mutations",
    "unbound_key",
    "undefined_edge_source",
    "undefined_edge_target",
    "undefined_entry_id",
    "undefined_finish_id",
    "undefined_path_map_target",
    "universal_write",
    "unpinned_temperature",
    "unprotected_cycle",
    "unprotected_retry_region",
    "unqualified_variant",
    "unreachable_node",
    "unwitnessed_two_cycle",
    "unwritten_read",
    "update_contract",
    "well_formedness_mutations",
    "wired_leaf",
    "with_edge",
    "with_node",
    "with_recursion_limit",
    "with_self_loop",
    "with_state_field",
    "with_wiring",
    "without_determinism",
    "without_edge",
    "without_effects",
    "without_reads",
    "without_witnesses",
]

#: The base name a dataflow or protection operator gives the state key it introduces. Long
#: enough that :func:`~gebra.testing.strategies.state_schemas` (four lowercase characters at
#: most) can never draw it; :func:`_fresh` still checks, because "cannot collide" is a fact
#: about today's generator and this module is handed IR from elsewhere too.
PROBE_KEY: Final = "gebra_probe_key"

#: The node id :func:`dangling_hook` points its compensation hook at. Grammatical under
#: IR-SPEC §5.1 on purpose: §6.4 says only that ``dangling_compensation_hook`` carries the hook
#: when it resolves to no node, but §0.3 types that evidence field ``Optional[NodeId]`` and
#: §3.4 types ``hook`` as a node id, so :mod:`~gebra.verify.properties.effect_safety` drops an
#: ungrammatical hook from the evidence rather than raising on declared content. An
#: ungrammatical probe would therefore silently test something weaker.
PROBE_HOOK: Final = "gebra_absent_hook"

#: The id a structural operator gives the node it *declares*. Grammatical, and long enough that
#: :func:`~gebra.testing.strategies.node_ids` cannot draw it; :func:`_fresh` still checks.
PROBE_NODE: Final = "gebra_probe_node"

#: The id a condition-(iv) operator points a reference at — grammatical under IR-SPEC §5.1 and
#: **declared nowhere**, which is what makes it an unresolved reference rather than an invalid
#: document. It has to be grammatical for the same reason :data:`PROBE_HOOK` does: P-01 spells
#: it into a ``P01EdgeLocation``, whose ``source`` is a ``NodeId``.
PROBE_TARGET: Final = "gebra_absent_node"

#: The ``path_map`` label :func:`undefined_path_map_target` hangs its dangling reference on.
PROBE_LABEL: Final = "probe"

#: The two ``label-literal`` tokens of the P-02 form-(a) guard the counter operators write
#: (T-W-SPEC §3). The then-label is R6's gated $\\hat{l}$; the else-label is the implicit
#: negation context and is never discharged.
#:
#: They are also in that order under IR-SPEC §6.2's member sort, and that is deliberate rather
#: than lucky: §2.3 fixes no ordering for ``P02CycleLocation.guard_edge.labels`` — the validator
#: emits authored ``path_map`` order — so a prediction of ``(then, else)`` is only stable while
#: the operator writes them in that order *and* nothing canonicalizes the map between here and
#: the report. Choosing labels that sort the same way removes the second dependency.
PROBE_THEN_LABEL: Final = "again"
PROBE_ELSE_LABEL: Final = "stop"

#: The ``int-literal`` of that guard's ``bounded-comparison``. Small and positive: §3 excludes
#: signed literals, and §1.1 reads nothing off the value.
PROBE_BOUND: Final = 3

#: The ``counter-ref`` identifier. Matches §3's ASCII ``identifier`` production, and is declared
#: ``int`` in $\\Sigma$ by the operator so R1's §2.1 half qualifies.
PROBE_COUNTER: Final = "gebra_probe_counter"

#: The ``measure`` a form-(c) ``variant`` declares (IR-SPEC §3.3). Attested and recorded, never
#: checked — §1.1: "the attested components are recorded and trusted".
PROBE_MEASURE: Final = "decreasing"

#: The form-(b) blanket a P-02 operator declares (IR-SPEC §3.5; T-W-SPEC §2.2). ``justification``
#: is REQUIRED and non-empty, because an empty one is §4 path 3's note rather than a witness.
PROBE_RECURSION_LIMIT: Final = 25
PROBE_JUSTIFICATION: Final = "probe: a declared bound, recorded and trusted"

#: The P-04 operators, in the order :func:`dataflow_mutations` offers them — breaking first,
#: because that is what shrinks to.
DATAFLOW_OPERATORS: Final[tuple[str, ...]] = (
    "unwritten-read",
    "self-write",
    "boundary-read",
    "universal-write",
    "foreign-read",
)

#: The P-06 operators. The first five are unprotected or mis-declared shapes; the last two are
#: the two protections §6.1 recognizes, so a suite can assert the discharge as well as the gap.
EFFECT_SAFETY_OPERATORS: Final[tuple[str, ...]] = (
    "unprotected-retry-region",
    "unprotected-cycle",
    "forbidden-combination",
    "unbound-key",
    "dangling-hook",
    "bound-key",
    "compensation-hook",
)

#: The P-08 operators — the two incoherent claims, the two coherent ones, and the disclaimer.
DETERMINISM_OPERATORS: Final[tuple[str, ...]] = (
    "bare-claim",
    "unpinned-temperature",
    "pinned-claim",
    "local-claim",
    "disclaimer",
)

#: The P-01 operators — one per §1 condition, plus the four DEC-12 reference sites and the
#: coherent repair. Breaking first, and the two whose finding set is a *cascade*
#: (``orphan-node``, ``empty-entry``) after the single-finding ones, so a shrunk counterexample
#: carries the smallest report.
WELL_FORMEDNESS_OPERATORS: Final[tuple[str, ...]] = (
    "unreachable-node",
    "severed-edge",
    "dead-end-node",
    "undefined-entry-id",
    "undefined-finish-id",
    "undefined-edge-source",
    "undefined-edge-target",
    "undefined-path-map-target",
    "orphan-node",
    "empty-entry",
    "wired-leaf",
)

#: The P-02 operators. The first three are a witnessed cycle with one witness taken away or
#: mis-declared; the fourth is the only one whose cycle runs through two nodes, which is what
#: makes the representative-cycle extraction and the canonical rotation non-vacuous; the last two
#: are the D4 wiring pair, which differ in one ``path_map`` value.
TERMINATION_OPERATORS: Final[tuple[str, ...]] = (
    "removed-variant",
    "removed-blanket",
    "unqualified-variant",
    "unwitnessed-two-cycle",
    "counter-guard-without-exit",
    "counter-guard-with-exit",
)

#: Every operator name, by the property it targets.
OPERATORS: Final[dict[PropertySlug, tuple[str, ...]]] = {
    DATAFLOW_SLUG: DATAFLOW_OPERATORS,
    EFFECT_SAFETY_SLUG: EFFECT_SAFETY_OPERATORS,
    DETERMINISM_SLUG: DETERMINISM_OPERATORS,
    WELL_FORMEDNESS_SLUG: WELL_FORMEDNESS_OPERATORS,
    TERMINATION_SLUG: TERMINATION_OPERATORS,
}

#: How many built strategies to keep, per builder — the same reason and the same bound as
#: :data:`gebra.testing.strategies._CACHE_SIZE`: a ``@st.composite`` body runs once per example,
#: so a strategy constructed inside one is rebuilt on every draw.
_CACHE_SIZE: Final = 256


# ── The record ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Mutation:
    """One applied mutation and the verdict it obliges its target property to reach.

    Attributes:
        origin: The **normalized** draw the operator started from. The target property passes
            on it, always — that is what normalization is for, and it is what makes
            "the mutation broke it" a falsifiable claim rather than an assumption about the
            draw.
        ir: The mutant. Well-formed in every respect the operator does not deliberately break;
            P-01 clean whenever :attr:`well_formed` is true, which is every family but a
            breaking P-01 mutation (asserted at scale by the two metaproperty suites).
        operator: Which operator produced it — a member of :data:`OPERATORS` for
            :attr:`target`.
        target: The catalog slug whose validator owns the injected defect.
        condition: The §0.4 condition ID the target property must report, or ``None`` when the
            operator is *coherent* and the target property must still pass.
        node: The node id the finding must be anchored at, when the operator injects one.
        key: The state key the finding names, for the P-04 operators; the idempotency key, for
            the two P-06 key operators; the counter key, for the two P-02 guard operators; and
            the ``variant.key`` for the two P-02 form-(c) operators — the *declared* one, which
            for :func:`unqualified_variant` is the key Σ does not carry, since that is the one
            the note names. ``None`` where the operator declares none.
        location: The **whole** anchor of the primary finding, when the operator can state it —
            a ``P01EdgeLocation`` for an unresolved reference, a ``P02SccLocation`` for a
            witness-free cycle, a ``NodeLocation`` for the rest. The structural anchors are
            location-valued rather than scalar (§1.3 anchors P-01 at an edge; §2.3 anchors P-02
            at an SCC or a cycle), so one slot carries them instead of a scalar per field.
            ``None`` for a coherent operator, and for the contract and advisory families, whose
            anchors :attr:`node` and :attr:`key` already state.
    """

    origin: WorkflowIR
    ir: WorkflowIR
    operator: str
    target: PropertySlug
    condition: ConditionId | None
    node: str | None = None
    key: str | None = None
    location: AnyLocation | None = None

    @property
    def breaking(self) -> bool:
        """Whether the target property must **fail** on :attr:`ir`."""
        return self.condition is not None

    @property
    def well_formed(self) -> bool:
        """Whether :attr:`ir` is still P-01 clean — false only for a breaking P-01 mutation.

        The scope flag for every cross-cutting claim, because §0.3 defines P-02's, P-04's and
        P-06's results *over P-01-clean topology* and says in terms that "cross-validator
        agreement on ill-formed input is NOT promised". A metaproperty that asserted "exactly
        one verdict moved" over a mutant with a dangling reference would be asserting something
        the frozen text declines to promise, and would be asserting it about four validators
        each running its own local degradation convention.
        """
        return not (self.breaking and self.target == WELL_FORMEDNESS_SLUG)


# ── Rewrites (pure, deterministic, validated) ────────────────────────────────────────────


def _rebuilt(ir: WorkflowIR, **changes: Any) -> WorkflowIR:
    """``ir`` with ``changes`` applied, rebuilt **through the constructor**.

    Never ``model_copy``: it skips validation the same way ``model_construct`` does, and A6
    PC-6's ban is about the document that reaches a consumer, not about which method spelled
    it. Every field the caller does not name is carried over by identity — the models are
    frozen (PC-1), so sharing a sub-model between an origin and its mutant is safe.
    """
    values: dict[str, Any] = {name: getattr(ir, name) for name in WorkflowIR.model_fields}
    values.update(changes)
    return WorkflowIR(**values)


def _updated(contract: Annotations | None, **changes: Any) -> Annotations:
    """``contract`` (or an empty one) with ``changes`` applied, rebuilt through the constructor."""
    current = contract if contract is not None else Annotations()
    values: dict[str, Any] = {name: getattr(current, name) for name in Annotations.model_fields}
    values.update(changes)
    return Annotations(**values)


def update_contract(ir: WorkflowIR, node_id: str, **changes: Any) -> WorkflowIR:
    """``ir`` with one node's contract updated slot by slot (IR-SPEC §2.3).

    A node carrying no ``annotations`` gets an :class:`~gebra.ir.Annotations` built from
    ``changes`` alone, so an operator never has to branch on absence.

    Raises:
        KeyError: if ``node_id`` names no declared node.
    """
    if node_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{node_id!r} is not a declared node of this workflow")
    return _rebuilt(
        ir,
        nodes=tuple(
            Node(id=node.id, annotations=_updated(node.annotations, **changes))
            if node.id == node_id
            else node
            for node in ir.nodes
        ),
    )


def _update_every_contract(ir: WorkflowIR, **changes: Any) -> WorkflowIR:
    """``changes`` applied to every node's contract at once."""
    return _rebuilt(
        ir,
        nodes=tuple(
            Node(id=node.id, annotations=_updated(node.annotations, **changes)) for node in ir.nodes
        ),
    )


def with_state_field(ir: WorkflowIR, key: str, field: str | StateField) -> WorkflowIR:
    """``ir`` with ``key`` declared in $\\Sigma$ (IR-SPEC §2.2), replacing any existing entry."""
    state: dict[str, str | StateField] = dict(ir.state or {})
    state[key] = field
    return _rebuilt(ir, state=state)


def with_self_loop(ir: WorkflowIR, node_id: str) -> WorkflowIR:
    """``ir`` with a ``normal`` self-loop on ``node_id`` appended to ``edges``.

    A self-loop is a simple cycle (T-W-SPEC §1), so this is the smallest edit that puts a node
    in a non-trivial component. It cannot break P-01: adding an edge unreaches nothing, creates
    no sink and orphans nobody, and its target is a declared node.

    Raises:
        KeyError: if ``node_id`` names no declared node.
    """
    if node_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{node_id!r} is not a declared node of this workflow")
    loop: Edge = NormalEdge(kind="normal", **{"from": node_id}, to=node_id)
    return _rebuilt(ir, edges=(*ir.edges, loop))


def with_node(ir: WorkflowIR, node_id: str, annotations: Annotations | None = None) -> WorkflowIR:
    """``ir`` with one more entry appended to ``nodes[]`` (IR-SPEC §2.1).

    Appending declares a node and wires it to nothing: whether the result is well-formed is
    then entirely the caller's business, which is what makes this the seam every P-01 operator
    starts from — the same node is an orphan, an unreachable node or a dead end depending only
    on which wiring the operator adds next.

    Raises:
        ValueError: if ``node_id`` is already declared. Duplicate ids are a §2.1 violation the
            models do not catch, and a silent one would make the operator's prediction false.
    """
    if node_id in {node.id for node in ir.nodes}:
        raise ValueError(f"{node_id!r} is already declared: nodes[].id is pairwise distinct (§2.1)")
    return _rebuilt(ir, nodes=(*ir.nodes, Node(id=node_id, annotations=annotations)))


def with_edge(ir: WorkflowIR, edge: Edge) -> WorkflowIR:
    """``ir`` with ``edge`` appended to ``edges`` (IR-SPEC §2.4).

    Nothing is checked: a reference naming no declared node is exactly what the condition-(iv)
    operators are for, and IR-SPEC §2.4 constrains the *grammar* of an edge, never the
    resolvability of its targets — that is P-01 condition (iv)'s question.
    """
    return _rebuilt(ir, edges=(*ir.edges, edge))


def without_edge(ir: WorkflowIR, index: int) -> WorkflowIR:
    """``ir`` with ``edges[index]`` removed.

    Raises:
        IndexError: if ``index`` names no edge.
    """
    if not -len(ir.edges) <= index < len(ir.edges):
        raise IndexError(f"edges[{index}] does not exist: this workflow declares {len(ir.edges)}")
    position = index % len(ir.edges)
    return _rebuilt(ir, edges=(*ir.edges[:position], *ir.edges[position + 1 :]))


def with_wiring(ir: WorkflowIR, field: str, *ids: str) -> WorkflowIR:
    """``ir`` with ``ids`` appended to ``entry`` or ``finish``, in the list form (IR-SPEC §2.1).

    Always the list form, whichever form the draw was in: the scalar spelling admits exactly one
    id, so appending to it has no scalar counterpart. Ids already present are not repeated —
    ``entry``/``finish`` denote sets under (m1)/(m2), and a repeat would build a second sentinel
    edge that no reading of §4.1 asks for.

    Raises:
        ValueError: if ``field`` is neither ``"entry"`` nor ``"finish"``.
    """
    if field not in ("entry", "finish"):
        raise ValueError(f"{field!r} is not a wiring list: IR-SPEC §2.1 has entry and finish")
    current: str | tuple[str, ...] = getattr(ir, field)
    return _rebuilt(ir, **{field: tuple(dict.fromkeys((*_wired(current), *ids)))})


def with_recursion_limit(ir: WorkflowIR, value: int, justification: str) -> WorkflowIR:
    """``ir`` with ``runtime.recursion_limit`` declared — the P-02 form-(b) blanket.

    IR-SPEC §3.5 makes ``justification`` REQUIRED and T-W-SPEC §2.2 makes the pair the blanket
    witness; the other two ``runtime`` sub-slots are carried through, so this is the one-slot
    edit its name says it is rather than a replacement of the block.
    """
    current = ir.runtime
    return _rebuilt(
        ir,
        runtime=Runtime(
            recursion_limit=RecursionLimit(value=value, justification=justification),
            interrupts=None if current is None else current.interrupts,
            checkpointer=None if current is None else current.checkpointer,
        ),
    )


def _wired(value: str | tuple[str, ...]) -> tuple[str, ...]:
    """``entry``/``finish`` as a tuple, whichever of the two §2.1 surface forms it is in."""
    return (value,) if isinstance(value, str) else value


def permute_nodes(ir: WorkflowIR, shift: int) -> WorkflowIR:
    """``ir`` with ``nodes[]`` rotated by ``shift``.

    The order of ``nodes[]`` is a surface fact: every validator that reads the list sorts it by
    the ledger §6 comparator first, and canonical serialization re-orders it anyway (IR-SPEC
    §6). So a rotation is the cheapest edit that changes the document without changing anything
    a report may depend on — which is what makes it a usable irrelevant mutation.
    """
    if not ir.nodes:  # pragma: no cover - IR-SPEC §2.1 makes nodes[] 1*
        return ir
    offset = shift % len(ir.nodes)
    return _rebuilt(ir, nodes=(*ir.nodes[offset:], *ir.nodes[:offset]))


def star_wiring(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` rewired so every node is both an ``entry`` and a ``finish``, with no edges.

    P-01 clean by construction — (m1) makes every node reachable from ``__start__`` and (m2)
    gives every node an outgoing edge to ``__end__`` — and about as far from a drawn topology as
    a document can get while staying clean. Paired with :func:`chain_wiring` it is what makes
    §8.7's "the validator must not couple to topology" a property rather than a review note.
    """
    ids = tuple(node.id for node in ir.nodes)
    return _rebuilt(ir, entry=ids, finish=ids, edges=())


def chain_wiring(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` rewired as a single path through every node, in declaration order.

    The other pole from :func:`star_wiring`: one entry, one finish, and a ``normal`` edge per
    consecutive pair. Also P-01 clean — every node is reachable, only the last is a sink, and it
    is the ``finish``.
    """
    ids = tuple(node.id for node in ir.nodes)
    edges: tuple[Edge, ...] = tuple(
        NormalEdge(kind="normal", **{"from": source}, to=target) for source, target in pairwise(ids)
    )
    return _rebuilt(ir, entry=ids[0], finish=ids[-1], edges=edges)


# ── Normalizers — what makes "the mutation broke it" falsifiable ─────────────────────────


def without_reads(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` with every declared read dropped — a vacuous P-04 pass.

    ``annotations.input`` is what P-04 quantifies over ("absent ≡ ∅", §4.4 Step 1), so an IR
    with no reads generates no obligation and passes with an empty coverage witness. A keyed
    ``idempotent`` marker goes with it, because §2.3 scopes its key to ``input`` and leaving one
    behind would produce a document that violates that obligation for no purpose.
    """
    return _rebuilt(
        ir,
        nodes=tuple(
            Node(
                id=node.id,
                annotations=_updated(
                    node.annotations,
                    input=None,
                    idempotent=(
                        None
                        if isinstance(_slot(node, "idempotent"), IdempotentKey)
                        else _slot(node, "idempotent")
                    ),
                ),
            )
            for node in ir.nodes
        ),
    )


def without_effects(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` with every ``annotations.effect`` dropped — a vacuous P-06 pass.

    P-06's obligation is created by a declared trigger tag and by nothing else (§6.3), so an IR
    declaring no effects has no obligations and passes with a witness carrying the cycle
    inventory and no records.
    """
    return _update_every_contract(ir, effect=None)


def without_determinism(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` with every ``annotations.deterministic`` dropped — a vacuous P-08 pass.

    A node with no claim carries no obligation either way (§8.4), so the witness is the empty
    ``claims`` tuple and, by the §8.3 iff, no caveat.
    """
    return _update_every_contract(ir, deterministic=None)


def without_witnesses(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` with every declared termination witness dropped — a vacuous P-02 pass on an
    acyclic draw.

    Two of T-W-SPEC §2.2's three forms are *declared* and so can be removed here: form (c),
    ``annotations.variant``, and form (b), ``runtime.recursion_limit``. Form (a) is not a slot
    but a recognized shape in a router's ``condition`` string, and nothing is dropped for it —
    :func:`~gebra.testing.strategies.workflow_irs` draws its conditions from a fixed vocabulary
    of opaque router names, none of which derives §3's ``guard`` production, so no draw carries
    a form-(a) witness to remove. A P-02 operator that *wants* one writes it (see
    :func:`counter_guard_with_exit`).

    Nodes carrying no ``variant`` are left untouched rather than rebuilt with an empty contract,
    so the normalizer changes exactly the documents that declared something.
    """
    stripped = _rebuilt(
        ir,
        nodes=tuple(
            Node(id=node.id, annotations=_updated(node.annotations, variant=None))
            if _slot(node, "variant") is not None
            else node
            for node in ir.nodes
        ),
    )
    runtime = ir.runtime
    if runtime is not None and runtime.recursion_limit is not None:
        runtime = Runtime(
            recursion_limit=None,
            interrupts=runtime.interrupts,
            checkpointer=runtime.checkpointer,
        )
    return _rebuilt(stripped, runtime=runtime)


def _slot(node: Node, name: str) -> Any:
    """One annotation slot of ``node``, or ``None`` when it carries no contract at all."""
    return None if node.annotations is None else getattr(node.annotations, name)


def _fresh(base: str, taken: Sequence[str] | frozenset[str] | set[str]) -> str:
    """``base``, suffixed until it is not in ``taken`` — a name no other declaration uses."""
    candidate = base
    while candidate in taken:
        candidate += "_"
    return candidate


def _require_acyclic(ir: WorkflowIR, node_id: str, operator: str, *, whole_graph: bool) -> None:
    """Refuse a draw that already carries the cycle an operator is about to inject.

    Checked rather than assumed, and the two callers need **different** strengths, which is what
    ``whole_graph`` selects.

    P-06's :func:`unprotected_cycle` needs ``node_id``'s component to be *trivial*, so that its
    self-loop decides ``region == "cycle"`` by construction (§6.4 Phase 3; DEC-13) — a cyclic
    draw could leave the region ``retry`` and the operator would predict the wrong *condition*.
    A cycle elsewhere in the graph is P-06's business only through the node it anchors at, so
    the node-scoped test is the whole precondition there.

    The P-02 operators need more: the normalized origin must **pass** P-02, and it does that by
    carrying no cycle *anywhere* — a witness-free cycle somewhere else would fail the origin, and
    "removing the witness broke it" would be unfalsifiable. It would also mis-predict the
    *primary*: §2.3 orders findings by (sorted node tuple of the anchor SCC, condition ID), so a
    ledger-smaller foreign SCC would take ``failure`` and the operator's ``location`` would name a
    co-failure instead. Both callers draw from :func:`acyclic_envelope`, so neither test fires on
    the generated path; this raises rather than filters, because a wrong prediction is worse than
    a missing one, and a direct call on a hand-built IR is exactly where one would come from.

    Raises:
        KeyError: if ``node_id`` is not declared.
        ValueError: if the required part of the graph already carries a cycle.
    """
    if node_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{node_id!r} is not a declared node of this workflow")
    components = build_graph_model(ir).components
    cyclic = bool(components.nontrivial) if whole_graph else components.is_nontrivial(node_id)
    if cyclic:
        subject = (
            "this workflow already lies on a cycle"
            if whole_graph
            else f"{node_id!r} already lies on a cycle"
        )
        raise ValueError(
            f"{subject}: {operator} needs an acyclic draw so that the cycle it injects is the "
            "only one, and is therefore the cycle its prediction names "
            "(PROPERTY-CATALOG-SPEC §6.4 Phase 3 and DEC-13 for P-06; TERMINATION-WITNESS-SPEC "
            "§5 and PROPERTY-CATALOG-SPEC §2.3's merged ordering for P-02). Draw from "
            "acyclic_envelope()."
        )


# ── P-04 operators (PROPERTY-CATALOG-SPEC §4) ────────────────────────────────────────────


def unwritten_read(ir: WorkflowIR, node_id: str) -> Mutation:
    """Declare a read of a fresh $\\Sigma$ key that nothing writes — the P-04 defect itself.

    The key is added to ``state`` in its bare-type form, so it is **not** ``optional`` and
    therefore not in the boundary set $I_0$ (§4.2 "Graph inputs"), and no node declares it in
    ``output``. Every ``START``-path to the reader therefore leaves it unwritten, which is
    §4's statement negated at one point.

    After normalization the document declares exactly one read, so P-04's report carries exactly
    one finding: the primary, with no co-failures and — since the key has no other writer and
    the reader is not its own downstream writer — neither of the two DEC-11 diagnostics.
    """
    origin = without_reads(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    mutant = update_contract(with_state_field(origin, key, "str"), node_id, input=(key,))
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="unwritten-read",
        target=DATAFLOW_SLUG,
        condition=READ_KEY_NEVER_WRITTEN_ON_PATH,
        node=node_id,
        key=key,
    )


def self_write(ir: WorkflowIR, node_id: str) -> Mutation:
    """Declare a read **and** the matching write on one node — first-arrival semantics, negated.

    ``IN[v]`` is the state *before* $v$ runs (§4.2), so a node's own write never satisfies its
    own read: the first arrival at $v$ finds the key unwritten however many laps follow. This is
    the operator that would pass if a validator confused ``IN`` with ``OUT``, and it is why the
    reachability form's endpoint exemption is ``∖ {v}`` (A8 T5).
    """
    origin = without_reads(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    mutant = update_contract(
        with_state_field(origin, key, "str"), node_id, input=(key,), output=(key,)
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="self-write",
        target=DATAFLOW_SLUG,
        condition=READ_KEY_NEVER_WRITTEN_ON_PATH,
        node=node_id,
        key=key,
    )


def boundary_read(ir: WorkflowIR, node_id: str, *, optional: bool) -> Mutation:
    """Declare a read of a fresh key whose $\\Sigma$ entry is or is not ``optional``.

    The two polarities of one edit, which is what makes the boundary set observable: with
    ``optional: true`` the key is in $I_0$ and §4.2 treats it as written at ``START``, so the
    read is covered at every reachable node and the coverage entry's ``satisfied_by`` is exactly
    the display sentinel ``START``; with ``optional: false`` the same document violates §4 at
    the same point.
    """
    origin = without_reads(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    field = StateField(type="str", optional=optional)
    mutant = update_contract(with_state_field(origin, key, field), node_id, input=(key,))
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="boundary-read",
        target=DATAFLOW_SLUG,
        condition=None if optional else READ_KEY_NEVER_WRITTEN_ON_PATH,
        node=node_id,
        key=key,
    )


def universal_write(ir: WorkflowIR, node_id: str) -> Mutation:
    """Have **every** node write a fresh key, and one node read it — covered iff it is not an entry.

    The sharpest statement of first-arrival semantics that a whole-graph edit can make. If the
    reader is not in ``entry``, every ``START``-path to it runs through some entry node first,
    that node writes the key, and the obligation is covered whatever the topology. If the reader
    *is* in ``entry``, the one-step path ``START → v`` has no interior at all, so nothing writes
    the key before $v$ reads it — and the emitted ``path`` is exactly ``("START", v)``, because
    the reachability form removes $W_k \\setminus \\{v\\}$, which here is every other node.
    """
    origin = without_reads(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    writing = _update_every_contract(
        with_state_field(origin, key, "str"),
        output=(key,),
    )
    mutant = update_contract(writing, node_id, output=(key,), input=(key,))
    entry_ids = (origin.entry,) if isinstance(origin.entry, str) else origin.entry
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="universal-write",
        target=DATAFLOW_SLUG,
        condition=READ_KEY_NEVER_WRITTEN_ON_PATH if node_id in entry_ids else None,
        node=node_id,
        key=key,
    )


def foreign_read(ir: WorkflowIR, node_id: str) -> Mutation:
    """Declare a read of a key that $\\Sigma$ does not declare — **not** P-04's finding.

    §4.4 Step 4 ``continue``s past a read whose key is outside $\\Sigma$, with the reason stated
    in terms: "Σ-membership is P-03's finding", never P-04's. So the coherent answer is a P-04
    pass with no coverage entry for the key at all — not a failure, and not a coverage entry
    claiming something covered it.

    This is one of the two operators that deliberately produces a document breaking an IR-SPEC
    §2.3 cross-field obligation (``input ⊆ keys(state)``). It is here because the frozen text
    says what the validator does with it, and a validator that instead reported it would be
    minting a finding for a property outside the wedge.
    """
    origin = without_reads(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    return Mutation(
        origin=origin,
        ir=update_contract(origin, node_id, input=(key,)),
        operator="foreign-read",
        target=DATAFLOW_SLUG,
        condition=None,
        node=node_id,
        key=key,
    )


# ── P-06 operators (PROPERTY-CATALOG-SPEC §6) ────────────────────────────────────────────


def _bare_trigger(ir: WorkflowIR, node_id: str, tag: str, **extra: Any) -> WorkflowIR:
    """``node_id`` tagged with one trigger and stripped of both protections (§6.4 Phase 4).

    ``extra`` overrides the stripping, which is how an operator puts exactly one protection —
    or exactly one mis-declared protection — back on the node it just cleared.
    """
    changes: dict[str, Any] = {
        "effect": (tag,),
        "idempotent": None,
        "compensation": None,
        "retry_policy": None,
    }
    changes.update(extra)
    return update_contract(ir, node_id, **changes)


def unprotected_retry_region(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """A trigger-tagged node declaring a ``retry_policy`` and no protection.

    Arm (a) of §6.3's ``retry_region(n)`` is presence of ``retry_policy`` and is
    **cycle-independent**: a node declaring one is re-executed by the runtime whether or not the
    graph loops back to it, so the region is ``retry`` for every topology and the condition is
    decided by construction rather than by what the draw happened to wire. §6.7 edge case 5
    names the shape; DEC-13 left the corpus fixture for it open as a WA-04 item, so this
    operator is the only adversarial coverage it has.
    """
    origin = without_effects(ir)
    mutant = _bare_trigger(
        origin, node_id, tag, retry_policy=RetryPolicy(max_attempts=1, retry_on=())
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="unprotected-retry-region",
        target=EFFECT_SAFETY_SLUG,
        condition=UNPROTECTED_EFFECT_IN_RETRY_REGION,
        node=node_id,
    )


def unprotected_cycle(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """A trigger-tagged node put on a fresh self-loop, with no protection and no retry policy.

    The other ERROR condition, and the one that needs the *region* to come out right: a node is
    ``cycle`` rather than ``retry`` exactly when it is in a non-trivial component and outside
    every structural retry region (§6.4 Phase 3, DEC-13). Adding a ``normal`` self-loop to a node
    whose component was **trivial** gives both halves by construction — the new component is the
    singleton, and its only intra-component edge is the ``normal`` loop, so DEC-13's rule (which
    seeds on *conditional* intra-component edges) admits nothing. The anchor is therefore
    ``(node_id,)``, the shortest cycle there is.

    **Both halves carry a justified ``runtime.recursion_limit``**, and that is not decoration:
    the self-loop this operator adds is an unwitnessed simple cycle, so once P-02 is registered
    the same edit moves P-06's *verdict* and P-02's, and "breaks exactly one property" would be
    false of it. The form-(b) blanket (T-W-SPEC §2.2; IR-SPEC §3.5) discharges every cycle at
    once without touching an edge kind, so P-02 passes on both halves and P-06's prediction is
    untouched — no wedge validator but P-02 reads ``runtime`` at all (§1.3, §4.3, §6.3, §8.3).
    The obvious alternative, making the loop ``conditional`` with a counter guard, is worse than
    the problem: a conditional intra-component edge puts the node in a structural retry region
    under §6.4 Phase 3, which destroys this operator's own ``region == "cycle"`` prediction.
    Recorded at TE-10's hand-off and applied at TE-09, when P-02 landed.

    **What the blanket does not make identical**, named so a reader does not over-read the
    paragraph above: P-02's *record* still moves across the pair. $S_b$ never enters residual
    construction (§6.1), so the mutant's self-loop survives into the residual and is carried on
    the WARNING-grade ``scc-covered-only-by-recursion-limit`` note with ``blanket_only: true``,
    where the origin carries none — which means ``strict_promotions`` returns one on the mutant
    and none on the origin, and a ``--gebra-strict`` gate naming P-02 moves even though no
    verdict does. That is §0.2's rule working as written ("the gate changes, never the record"),
    and the "exactly one property" claim is stated over verdicts throughout; a P-02 metaproperty
    that wanted the gate would use :func:`removed_blanket`, which is built for it.

    Raises:
        ValueError: if ``node_id`` already lies on a cycle. The precondition is checked rather
            than assumed: a caller that hands in a cyclic draw would get a ``retry`` region
            whenever the component carried a conditional re-entry edge, and the mutation would
            silently predict the wrong condition.
    """
    origin = with_recursion_limit(without_effects(ir), PROBE_RECURSION_LIMIT, PROBE_JUSTIFICATION)
    _require_acyclic(origin, node_id, "unprotected_cycle", whole_graph=False)
    mutant = with_self_loop(_bare_trigger(origin, node_id, tag), node_id)
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="unprotected-cycle",
        target=EFFECT_SAFETY_SLUG,
        condition=UNPROTECTED_EFFECT_IN_CYCLE,
        node=node_id,
    )


def forbidden_combination(ir: WorkflowIR, node_id: str) -> Mutation:
    """``irreversible`` plus a keyless ``idempotent`` — the D-012 combination, FATAL.

    §6.4 Phase 1 runs before any graph analysis and the finding is cycle-independent: a bare
    "the provider dedups" claim that no input field pins is a design error wherever it sits.
    Only the boolean form fires; the object form is a claim tied to a declared read, and whether
    it *binds* is Phase 4's question — which is what :func:`bound_key` and :func:`unbound_key`
    exercise.

    This is the one operator that deliberately does **not** go through :func:`_bare_trigger`, so
    a drawn ``retry_policy`` survives and the node may well be inside a region Phase 4 would
    otherwise report on. That the report still carries exactly one record is Phase 4's same-node
    FATAL dominance (DEC-05 D2: one root cause, one report), not an accident of the draw — worth
    knowing before "simplifying" this to match its neighbours.
    """
    origin = without_effects(ir)
    mutant = update_contract(
        origin, node_id, effect=("irreversible",), idempotent=True, compensation=None
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="forbidden-combination",
        target=EFFECT_SAFETY_SLUG,
        condition=IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
        node=node_id,
    )


def unbound_key(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """A keyed ``idempotent`` whose key is the node's own **output**, never an input.

    §6.4 Phase 4's ``keyed := idempotent(n) == {key: k} and k ∈ input(n)`` is a binding test, not
    a presence test, and ``mixed/06`` is the in-corpus precedent for exactly this shape: a
    reference minted fresh on every lap can stabilise nothing. The key is declared
    ``optional: true`` in $\\Sigma$ and written rather than read, so P-04's verdict cannot move
    with it — the mutation stays P-06's.

    The document breaks IR-SPEC §2.3's ``idempotent.key ∈ input`` on purpose; the vendored
    corpus does the same, which is why §6.4 has a rule for it.
    """
    origin = without_effects(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    declared = with_state_field(origin, key, StateField(type="str", optional=True))
    written = tuple(dict.fromkeys((*(_declared(declared, node_id, "output")), key)))
    mutant = _bare_trigger(
        declared,
        node_id,
        tag,
        output=written,
        idempotent=IdempotentKey(key=key),
        retry_policy=RetryPolicy(max_attempts=1, retry_on=()),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="unbound-key",
        target=EFFECT_SAFETY_SLUG,
        condition=UNPROTECTED_EFFECT_IN_RETRY_REGION,
        node=node_id,
        key=key,
    )


def dangling_hook(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """A ``compensation.hook`` naming no declared node — declared, but not protection.

    DEC-05 D7's side condition, restated normatively at §6.1 and ratified verbatim by DEC-13: a
    hook that resolves to nothing discharges nothing, so the node falls through to the ordinary
    unprotected-effect condition and the bad id rides along as the
    ``dangling_compensation_hook`` evidence field — no new condition ID, the §0.4 registry stays
    closed (§6.7 item 5).
    """
    origin = without_effects(ir)
    hook = _fresh(PROBE_HOOK, frozenset(node.id for node in origin.nodes))
    mutant = _bare_trigger(
        origin,
        node_id,
        tag,
        compensation=Compensation(hook=hook),
        retry_policy=RetryPolicy(max_attempts=1, retry_on=()),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="dangling-hook",
        target=EFFECT_SAFETY_SLUG,
        condition=UNPROTECTED_EFFECT_IN_RETRY_REGION,
        node=node_id,
    )


def bound_key(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """A keyed ``idempotent`` whose key **is** among the node's declared reads — protection.

    The first of §6.1's two protections, and the coherent counterpart of :func:`unbound_key`:
    same node, same region, same tag, one field different. The key is declared ``optional: true``
    so that the read it adds sits in P-04's boundary set and P-04's verdict does not move.
    """
    origin = without_effects(ir)
    key = _fresh(PROBE_KEY, frozenset(origin.state or {}))
    declared = with_state_field(origin, key, StateField(type="str", optional=True))
    read = tuple(dict.fromkeys((*(_declared(declared, node_id, "input")), key)))
    mutant = _bare_trigger(
        declared,
        node_id,
        tag,
        input=read,
        idempotent=IdempotentKey(key=key),
        retry_policy=RetryPolicy(max_attempts=1, retry_on=()),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="bound-key",
        target=EFFECT_SAFETY_SLUG,
        condition=None,
        node=node_id,
        key=key,
    )


def compensation_hook(ir: WorkflowIR, node_id: str, tag: str, hook: str) -> Mutation:
    """A ``compensation.hook`` naming a declared node — the second protection (DEC-05 D7).

    §6.1 restates it normatively: "a declared compensation hook discharges the P-06 obligation
    exactly as a keyed idempotency declaration does". IR-SPEC §3.4's "MUST NOT treat as
    discharging any P-06/P-07 obligation" sentence is spent **for P-06** — §6 is the
    formalization its "until then" points at — which is why this operator is coherent rather
    than breaking. Its P-07 half is still live: §6.1 leaves that contract gap open by name, so
    nothing here reads the sentence as retired outright.

    Raises:
        KeyError: if ``hook`` names no declared node, which would make it :func:`dangling_hook`.
    """
    origin = without_effects(ir)
    if hook not in {node.id for node in origin.nodes}:
        raise KeyError(f"{hook!r} is not a declared node: that is dangling_hook, not protection")
    mutant = _bare_trigger(
        origin,
        node_id,
        tag,
        compensation=Compensation(hook=hook),
        retry_policy=RetryPolicy(max_attempts=1, retry_on=()),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="compensation-hook",
        target=EFFECT_SAFETY_SLUG,
        condition=None,
        node=node_id,
    )


def _declared(ir: WorkflowIR, node_id: str, slot: str) -> tuple[str, ...]:
    """One node's ``input``/``output``/``effect`` tuple, empty when absent.

    "Absent ≡ ∅ (omit-normalized)" is §4.4 Step 1's rule for the two contract sets, and §6.3
    reads ``effect`` the same way, so an operator that extends one of them never has to branch
    on a node carrying no contract at all.
    """
    for node in ir.nodes:
        if node.id == node_id:
            values: tuple[str, ...] | None = _slot(node, slot)
            return values or ()
    raise KeyError(f"{node_id!r} is not a declared node of this workflow")


# ── P-08 operators (PROPERTY-CATALOG-SPEC §8, Appendix B) ────────────────────────────────


def _with_llm_evidence(ir: WorkflowIR, node_id: str, tag: str) -> WorkflowIR:
    """``node_id``'s effect tuple **extended** by one LLM-evidence tag (Appendix B C-1).

    Extended rather than replaced, so the ``{billable, irreversible}`` trigger set P-06 reads is
    untouched and a P-08 operator cannot move P-06's verdict.
    """
    tags = tuple(dict.fromkeys((*_declared(ir, node_id, "effect"), tag)))
    return update_contract(ir, node_id, effect=tags)


def bare_claim(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """``deterministic: true`` on a node whose effects evidence a remote LLM call — C-2.

    The bare boolean pins no seed anywhere, so on an LLM-backed node the claim is incoherent
    (``deterministic-llm-seed-unpinned``). The severity stays WARNING and the claim class
    HEURISTIC in the stored record whatever a strict gate does with it (§0.2): strict mode
    changes the gate, never the record.
    """
    origin = without_determinism(ir)
    mutant = update_contract(_with_llm_evidence(origin, node_id, tag), node_id, deterministic=True)
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="bare-claim",
        target=DETERMINISM_SLUG,
        condition=SEED_UNPINNED,
        node=node_id,
    )


def unpinned_temperature(
    ir: WorkflowIR, node_id: str, tag: str, seed: int, temperature: float | None
) -> Mutation:
    """A seeded claim whose temperature is absent or nonzero — C-3, both halves.

    §8.4 compares numerically, so ``0`` and ``0.0`` are the same pinned value and anything else
    — including absence, the tutorial §7 case — fires
    ``deterministic-llm-temperature-unpinned``.

    Raises:
        ValueError: if ``temperature`` is zero, which is :func:`pinned_claim`.
    """
    if temperature is not None and temperature == 0:
        raise ValueError("temperature=0 is the coherent pinning: that is pinned_claim")
    origin = without_determinism(ir)
    mutant = update_contract(
        _with_llm_evidence(origin, node_id, tag),
        node_id,
        deterministic=DeterministicSpec(seed=seed, temperature=temperature),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="unpinned-temperature",
        target=DETERMINISM_SLUG,
        condition=TEMPERATURE_UNPINNED,
        node=node_id,
    )


def pinned_claim(ir: WorkflowIR, node_id: str, tag: str, seed: int) -> Mutation:
    """A seeded claim at ``temperature: 0`` on an LLM-backed node — coherent (C-4, C-5).

    The pass this operator asks for is the one that carries the mandatory provider caveat: what
    is pinned is the *declaration*, and a provider is free to return something else on replay
    (Appendix B §B.1). The witness model enforces the iff; this operator is what supplies a
    generated instance of it.
    """
    origin = without_determinism(ir)
    mutant = update_contract(
        _with_llm_evidence(origin, node_id, tag),
        node_id,
        deterministic=DeterministicSpec(seed=seed, temperature=0.0),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="pinned-claim",
        target=DETERMINISM_SLUG,
        condition=None,
        node=node_id,
    )


def local_claim(ir: WorkflowIR, node_id: str) -> Mutation:
    """``deterministic: true`` on a node with **no** LLM evidence — trivially coherent (C-1).

    The gate is the effect tags, so the same bare boolean that is incoherent in
    :func:`bare_claim` is fine here: pure local computation carries no pinning obligation, and
    the claim is recorded with ``basis: pure-local-computation`` and no caveat. Only the two
    evidence tags are removed, so P-06's trigger set is untouched.
    """
    origin = without_determinism(ir)
    tags = tuple(
        tag for tag in _declared(origin, node_id, "effect") if tag not in LLM_EVIDENCE_TAGS
    )
    mutant = update_contract(origin, node_id, effect=tags or None, deterministic=True)
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="local-claim",
        target=DETERMINISM_SLUG,
        condition=None,
        node=node_id,
    )


def disclaimed_determinism(ir: WorkflowIR, node_id: str, tag: str) -> Mutation:
    """``deterministic: false`` on an LLM-backed node — the explicit disclaimer (§8.4).

    No claim is made, so no obligation arises and no record is written: the witness must not
    carry the node at all. The distinction from absence is the point — an author who writes the
    disclaimer is saying something, and P-08 must still record nothing.
    """
    origin = without_determinism(ir)
    mutant = update_contract(_with_llm_evidence(origin, node_id, tag), node_id, deterministic=False)
    return Mutation(
        origin=origin,
        ir=mutant,
        operator="disclaimer",
        target=DETERMINISM_SLUG,
        condition=None,
        node=node_id,
    )


# ── P-01 operators (PROPERTY-CATALOG-SPEC §1) ────────────────────────────────────────────
#
# These are the one family whose mutants are **not** well-formed: each breaks one of §1's four
# conditions, so P-01 refuses the document by design. No normalizer is needed for the target —
# `workflow_irs` is P-01 clean by construction (TE-08), so the origin passes without being
# rewritten, which is why every operator here takes the draw as its own origin. What each one is
# built for instead is a *predictable finding set*: nine of the eleven emit exactly one finding,
# and the two that cascade (`orphan_node`, `empty_entry`) cascade in a way that is stated in full
# at the operator and asserted in the suite.


def unreachable_node(ir: WorkflowIR) -> Mutation:
    """Declare a node that nothing wires to, but list it in ``finish`` — condition (i) alone.

    The ``finish`` membership is what isolates the condition. Under (m2) it gives the new node an
    edge to ``__end__``, so it is not a sink and condition (ii) stays silent; under Reading A
    (DEC-11) it *is* edge participation, so condition (iii) stays silent too. Nothing wires
    ``__start__`` to it, so exactly one condition fails, and the report is a single finding
    anchored at the node — the smallest statement of "unreachable" a document can make.
    """
    node_id = _fresh(PROBE_NODE, {node.id for node in ir.nodes})
    return Mutation(
        origin=ir,
        ir=with_wiring(with_node(ir, node_id), "finish", node_id),
        operator="unreachable-node",
        target=WELL_FORMEDNESS_SLUG,
        condition=NODE_UNREACHABLE_FROM_START,
        node=node_id,
        location=NodeLocation(kind="node", node=node_id),
    )


def severed_edge(ir: WorkflowIR, source_id: str) -> Mutation:
    """Attach a fresh leaf by one edge, then **delete that edge** — reachability, by removal.

    The card's own example ("removing an edge breaks reachability verdicts"), and the reason it
    is built in two steps rather than by deleting an edge of the draw: removing an arbitrary edge
    unreaches an arbitrary set of nodes, may strand its source as a new sink and may orphan
    someone, so the prediction would be a distribution rather than a statement. Attaching the
    leaf *first* makes the origin a P-01-clean document that differs from the draw by one node,
    and then the removal has exactly one consequence — the leaf loses its only inbound wiring.

    The source keeps whatever outgoing edges it had, and if the removal leaves it a sink it was
    already one before the leaf was attached, so P-01 clean means it is in ``finish``: condition
    (ii) cannot fire on it either.

    Raises:
        KeyError: if ``source_id`` names no declared node.
    """
    if source_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{source_id!r} is not a declared node of this workflow")
    node_id = _fresh(PROBE_NODE, {node.id for node in ir.nodes})
    attached = with_wiring(
        with_edge(
            with_node(ir, node_id), NormalEdge(kind="normal", **{"from": source_id}, to=node_id)
        ),
        "finish",
        node_id,
    )
    return Mutation(
        origin=attached,
        ir=without_edge(attached, len(attached.edges) - 1),
        operator="severed-edge",
        target=WELL_FORMEDNESS_SLUG,
        condition=NODE_UNREACHABLE_FROM_START,
        node=node_id,
        location=NodeLocation(kind="node", node=node_id),
    )


def dead_end_node(ir: WorkflowIR, source_id: str) -> Mutation:
    """Wire a fresh node in, and wire nothing out of it — condition (ii) alone.

    §1.4 Step 4's scan is over $G^*$ and is catalog-literal: a node with no outgoing edge strands
    execution unless ``finish`` supplies the (m2) edge to ``__end__``. This declares the node,
    reaches it from an existing one so condition (i) stays silent, gives it edge participation so
    condition (iii) stays silent, and leaves it out of ``finish``.

    Raises:
        KeyError: if ``source_id`` names no declared node.
    """
    return _leaf(ir, source_id, "dead-end-node", wired=False)


def wired_leaf(ir: WorkflowIR, source_id: str) -> Mutation:
    """The same fresh node, listed in ``finish`` — **coherent**, and the repair of the one above.

    One field apart from :func:`dead_end_node`, which is what makes ``finish`` membership
    observable as the thing condition (ii) turns on rather than as a coincidence of the draw.

    Raises:
        KeyError: if ``source_id`` names no declared node.
    """
    return _leaf(ir, source_id, "wired-leaf", wired=True)


def _leaf(ir: WorkflowIR, source_id: str, operator: str, *, wired: bool) -> Mutation:
    """A fresh node reached by one new edge, in ``finish`` or not — the two polarities."""
    if source_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{source_id!r} is not a declared node of this workflow")
    node_id = _fresh(PROBE_NODE, {node.id for node in ir.nodes})
    attached = with_edge(
        with_node(ir, node_id), NormalEdge(kind="normal", **{"from": source_id}, to=node_id)
    )
    return Mutation(
        origin=ir,
        ir=with_wiring(attached, "finish", node_id) if wired else attached,
        operator=operator,
        target=WELL_FORMEDNESS_SLUG,
        condition=None if wired else DEAD_END_NODE_NOT_WIRED_TO_END,
        node=node_id,
        location=None if wired else NodeLocation(kind="node", node=node_id),
    )


def orphan_node(ir: WorkflowIR) -> Mutation:
    """Declare a node and wire it to nothing at all — the §1.4 Step 5 cascade, in full.

    The one operator here whose report is deliberately more than one finding, because the
    document cannot make it fewer: a node in no edge, in no ``entry`` and in no ``finish``
    violates (iii), (i) and (ii) at once. What that buys is the only executable statement of
    Step 5's **root-cause order** — (iv) → (iii) → (i) → (ii) — since a validator that ordered by
    (i) first would still report all three and would still fail exactly the same documents. The
    primary is therefore ``orphan-node`` and the two co-failures follow in that order, all three
    anchored at the same node.
    """
    node_id = _fresh(PROBE_NODE, {node.id for node in ir.nodes})
    return Mutation(
        origin=ir,
        ir=with_node(ir, node_id),
        operator="orphan-node",
        target=WELL_FORMEDNESS_SLUG,
        condition=ORPHAN_NODE,
        node=node_id,
        location=NodeLocation(kind="node", node=node_id),
    )


def empty_entry(ir: WorkflowIR) -> Mutation:
    """Set ``entry`` to the empty list — every declared node loses its root at once.

    DEC-18 ratifies the empty list as a *value* rather than an omission, and (m1) then wires
    ``__start__`` to nothing, so condition (i) fails at **every** node: the finding set is
    exactly $V$, in the ledger §6 order §1.4 Steps 2–4 iterate. Nothing else moves — a node with
    no explicit edge incidence was a sink in the clean draw and is therefore in ``finish``, which
    both keeps condition (ii) silent and keeps it out of condition (iii) under Reading A. This is
    the widest single-field P-01 break there is, and the primary anchors at the ledger-least
    declared node.

    :func:`~gebra.testing.strategies.topologies` deliberately never *draws* this shape ("with no
    wiring from ``START`` every node is unreachable, so it is a P-01-failing shape and belongs to
    a mutation operator, not here"). This is that operator.
    """
    return Mutation(
        origin=ir,
        ir=_rebuilt(ir, entry=()),
        operator="empty-entry",
        target=WELL_FORMEDNESS_SLUG,
        condition=NODE_UNREACHABLE_FROM_START,
        location=NodeLocation(
            kind="node", node=min((node.id for node in ir.nodes), key=ledger_sort_key)
        ),
    )


def undefined_entry_id(ir: WorkflowIR) -> Mutation:
    """Add an ``entry`` id naming no node — DEC-12 site 1, anchored at ``START``.

    The first of the four sites DEC-12 gives ``edge-target-undefined``. The anchor is the vertex
    a person would edit, which for a bad root is the sentinel: nothing else in the document
    mentions the id.
    """
    return _dangling(ir, "undefined-entry-id", lambda ref: with_wiring(ir, "entry", ref))


def undefined_finish_id(ir: WorkflowIR) -> Mutation:
    """Add a ``finish`` id naming no node — DEC-12 site 2, anchored at the id **itself**.

    §1.4's symmetric check anchors this one at the unresolved id rather than at a sentinel, which
    is the asymmetry with :func:`undefined_entry_id` and the reason the two are separate
    operators rather than one parametrized by field.
    """
    return _dangling(
        ir,
        "undefined-finish-id",
        lambda ref: with_wiring(ir, "finish", ref),
        source=lambda ref: ref,
    )


def undefined_edge_source(ir: WorkflowIR, target_id: str) -> Mutation:
    """Add an edge whose ``from`` names no node — DEC-12 site 3.

    The site with §1.4 Step 1's own asymmetry behind it: the edge's ``to`` is never checked,
    because Step 1 ``continue``s past an unresolved ``from`` on a ``normal``/``send`` edge. So
    this emits **one** finding even though the edge carries two references, and a model that
    "helpfully" checked the target too would emit two.

    Raises:
        KeyError: if ``target_id`` names no declared node.
    """
    if target_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{target_id!r} is not a declared node of this workflow")
    return _dangling(
        ir,
        "undefined-edge-source",
        lambda ref: with_edge(ir, NormalEdge(kind="normal", **{"from": ref}, to=target_id)),
        source=lambda ref: ref,
    )


def undefined_edge_target(ir: WorkflowIR, source_id: str) -> Mutation:
    """Add a ``normal`` edge whose ``to`` names no node — DEC-12 site 4.

    Raises:
        KeyError: if ``source_id`` names no declared node.
    """
    if source_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{source_id!r} is not a declared node of this workflow")
    return _dangling(
        ir,
        "undefined-edge-target",
        lambda ref: with_edge(ir, NormalEdge(kind="normal", **{"from": source_id}, to=ref)),
        source=lambda _: source_id,
    )


def undefined_path_map_target(ir: WorkflowIR, source_id: str) -> Mutation:
    """Add a router label valued at no node — the **other** condition (iv) ID.

    ``path-map-target-undefined`` keeps its own §0.4 name while the four sites above share one,
    because DEC-05 D4 reserves a distinct ID for a diagnostically distinct failure and a dangling
    *label* is one: the anchor names the router and the label, and its ``target`` stays omitted
    per §0.3's dangling-label rule.

    Raises:
        KeyError: if ``source_id`` names no declared node.
    """
    if source_id not in {node.id for node in ir.nodes}:
        raise KeyError(f"{source_id!r} is not a declared node of this workflow")
    return _dangling(
        ir,
        "undefined-path-map-target",
        lambda ref: with_edge(
            ir,
            ConditionalEdge(
                kind="conditional",
                **{"from": source_id},
                condition=None,
                path_map={PROBE_LABEL: ref},
            ),
        ),
        source=lambda _: source_id,
        label=PROBE_LABEL,
        condition=PATH_MAP_TARGET_UNDEFINED,
    )


def _dangling(
    ir: WorkflowIR,
    operator: str,
    rewrite: Callable[[str], WorkflowIR],
    *,
    source: Callable[[str], str] | None = None,
    label: str | None = None,
    condition: ConditionId = EDGE_TARGET_UNDEFINED,
) -> Mutation:
    """One unresolved reference, at whichever of the five sites ``rewrite`` writes it to.

    The reference is freshened against the declared ids, so it resolves to nothing however the
    draw happened to name its nodes, and it is grammatical (:data:`PROBE_TARGET`) so P-01 can
    spell it into a ``P01EdgeLocation``.
    """
    reference = _fresh(PROBE_TARGET, {node.id for node in ir.nodes})
    anchor = to_display(START_VERTEX) if source is None else to_display(source(reference))
    return Mutation(
        origin=ir,
        ir=rewrite(reference),
        operator=operator,
        target=WELL_FORMEDNESS_SLUG,
        condition=condition,
        location=P01EdgeLocation(
            kind="edge", source=anchor, label=label, undefined_target=reference
        ),
    )


# ── P-02 operators (PROPERTY-CATALOG-SPEC §2; TERMINATION-WITNESS-SPEC) ──────────────────
#
# Every operator here draws from an **acyclic** narrowing of its envelope and adds exactly one
# self-loop, so the normalized origin passes P-02 vacuously and the mutant's residual carries one
# singleton SCC whose representative cycle is the loop itself. Two normalizers run first and both
# are load-bearing: `without_witnesses` (so the loop is not silently discharged by a drawn
# `variant` or a drawn `recursion_limit`) and `without_effects` (so the new cycle cannot move
# P-06's verdict — the mirror image of the blanket TE-10's `unprotected_cycle` now carries).
#
# The loop is always a **self**-loop, never a two-node cycle, and that is a P-04 constraint
# rather than an aesthetic one: a self-loop adds the constraint `IN[v] ⊆ IN[v] ∪ writes(v)`,
# which every solution already satisfies, so P-04's greatest fixpoint cannot move (MP-04-9 pins
# it); a second edge into some other node would add a predecessor to a meet and could.


def removed_variant(ir: WorkflowIR, node_id: str) -> Mutation:
    """A cycle discharged by a form-(c) ``variant``, with the ``variant`` taken away.

    The card's own example — "removing a witness flips the P-02 outcome" — and the pair is
    literally one annotation slot apart: same graph, same cycle, same Σ, one ``variant``. §4's
    discharge table admits form (c) when ``variant.key ∈ keys(Σ)``, and then §5's Lemma 1 finds
    the element residual acyclic because the whole carrier node leaves it. Without it the
    residual keeps the loop, and Step 5 reports that singleton SCC with the loop as its
    representative cycle.

    Raises:
        ValueError: if ``node_id`` already lies on a cycle (see :func:`_require_acyclic`).
        KeyError: if ``node_id`` names no declared node.
    """
    looped, key = _witnessable_loop(ir, node_id, "removed_variant")
    return Mutation(
        origin=update_contract(looped, node_id, variant=Variant(key=key, measure=PROBE_MEASURE)),
        ir=looped,
        operator="removed-variant",
        target=TERMINATION_SLUG,
        condition=CYCLE_WITHOUT_TERMINATION_WITNESS,
        node=node_id,
        key=key,
        location=_scc_location(node_id),
    )


def removed_blanket(ir: WorkflowIR, node_id: str) -> Mutation:
    """The same cycle covered by the form-(b) blanket, with ``recursion_limit`` taken away.

    The other removable witness form, and the one whose *pass* is the interesting half: a blanket
    never enters the element residual (§6.1 — a blanket over $E$ would make Lemma 1 vacuous), so
    the origin passes while still carrying the surviving SCC on the WARNING-grade
    ``scc-covered-only-by-recursion-limit`` note with ``blanket_only: true``. That is the record
    §6.1's third row promotes under ``--gebra-strict``, unchanged, which is what makes this
    operator the generated instance of "the gate changes, never the record".

    Raises:
        ValueError: if ``node_id`` already lies on a cycle.
        KeyError: if ``node_id`` names no declared node.
    """
    looped, _ = _witnessable_loop(ir, node_id, "removed_blanket")
    return Mutation(
        origin=with_recursion_limit(looped, PROBE_RECURSION_LIMIT, PROBE_JUSTIFICATION),
        ir=looped,
        operator="removed-blanket",
        target=TERMINATION_SLUG,
        condition=CYCLE_WITHOUT_TERMINATION_WITNESS,
        node=node_id,
        location=_scc_location(node_id),
    )


def unqualified_variant(ir: WorkflowIR, node_id: str) -> Mutation:
    """The same ``variant``, its ``key`` moved off $\\Sigma$ — declared, and not a witness.

    §4's form-(c) row is a **membership** test, not a presence test, so a ``variant`` whose key
    $\\Sigma$ does not declare discharges nothing, and the cycle fails exactly as if the
    annotation were absent — with the difference §4 **path 4** requires: the
    ``variant-key-not-in-state`` note, so a misspelled key is surfaced rather than silently
    shrinking coverage.

    The obligation this breaks is **T-W-SPEC §2.3**'s ("``key`` MUST be in $\\mathrm{keys}
    (\\Sigma)$"), not an IR-SPEC §2.3 cross-field one: IR-SPEC §3.3 fixes the field names and
    says so, delegating what discharge requires to R-05. Which is why the shape loads at all,
    and why §4 has a path for it.

    Raises:
        ValueError: if ``node_id`` already lies on a cycle.
        KeyError: if ``node_id`` names no declared node.
    """
    looped, key = _witnessable_loop(ir, node_id, "unqualified_variant")
    absent = _fresh(_fresh(PROBE_KEY, {key}), frozenset(looped.state or {}))
    return Mutation(
        origin=update_contract(looped, node_id, variant=Variant(key=key, measure=PROBE_MEASURE)),
        ir=update_contract(looped, node_id, variant=Variant(key=absent, measure=PROBE_MEASURE)),
        operator="unqualified-variant",
        target=TERMINATION_SLUG,
        condition=CYCLE_WITHOUT_TERMINATION_WITNESS,
        node=node_id,
        key=absent,
        location=_scc_location(node_id),
    )


def unwitnessed_two_cycle(ir: WorkflowIR, node_id: str) -> Mutation:
    """A cycle through **two** nodes and no witness — the multi-node residual SCC.

    Every other operator in this family loops one node onto itself, and a singleton SCC makes
    three things vacuous that Step 5 actually does: A7 Lemma 3's representative extraction has no
    tree path to walk, §0.3's canonical rotation has one id to order, and the SCC's ``nodes``
    tuple has nothing to sort. So this one declares a fresh node $p$ and wires
    $v \\to p \\to v$, which is the smallest cycle where all three have work to do — and the
    fresh id lands on either side of ``node_id`` under the ledger §6 comparator, so the rotation
    varies across draws rather than being fixed by construction.

    The mutant is still exactly one property's: $p$ carries no contract, so P-08's claim
    inventory is unchanged; it is reached from $v$ and reaches $v$, so P-01 stays clean; and the
    normalizers clear reads and effects, which is what makes the *second* edge safe. That last
    part is why the reads are cleared here and nowhere else in the family: a self-loop adds a
    constraint P-04's fixpoint already satisfies, but $p \\to v$ adds a **predecessor** to a meet
    and could move P-04's verdict on a draw that declared one.

    Raises:
        ValueError: if the draw already carries a cycle (see :func:`_require_acyclic`).
        KeyError: if ``node_id`` names no declared node.
    """
    normalized = without_reads(without_effects(without_witnesses(ir)))
    _require_acyclic(normalized, node_id, "unwitnessed_two_cycle", whole_graph=True)
    partner = _fresh(PROBE_NODE, {node.id for node in normalized.nodes})
    mutant = with_edge(
        with_edge(
            with_node(normalized, partner),
            NormalEdge(kind="normal", **{"from": node_id}, to=partner),
        ),
        NormalEdge(kind="normal", **{"from": partner}, to=node_id),
    )
    members = tuple(sorted((node_id, partner), key=ledger_sort_key))
    return Mutation(
        origin=normalized,
        ir=mutant,
        operator="unwitnessed-two-cycle",
        target=TERMINATION_SLUG,
        condition=CYCLE_WITHOUT_TERMINATION_WITNESS,
        node=partner,
        location=P02SccLocation(
            kind="scc",
            nodes=members,
            # The DFS of A7 Lemma 3 roots at the ledger-least member and expands successors in
            # ledger order, so on a two-cycle the tree path is (least, other) and the back edge
            # closes it; `canonical_rotation` then leaves it alone, the rotation already being
            # least-first.
            representative_cycle=members,
            exhaustive=False,
        ),
    )


def counter_guard_without_exit(ir: WorkflowIR, node_id: str) -> Mutation:
    """A recognized counter guard on a self-loop whose labels both stay inside it — D4.

    DEC-05 D4's distinct wiring defect, and the one P-02 emits *during* S-construction rather
    than from the residual: the guard qualifies under §3/§2.1, so counter saturation is bounded,
    but no ``path_map`` label leaves the loop — saturation has nowhere to go. §2.3 anchors it on
    the cycle through the guard's source with the counter key and the guard's labels as evidence,
    which is what this operator predicts in full.

    The prediction does not turn on which of DEC-23 Q4's two tests the validator took, and the
    reason is narrower than it may look: the draw comes from :func:`acyclic_envelope`, so the
    only cycle in the mutant is the self-loop this operator wrote, $\\mathrm{SCC}(v) =
    \\{v\\}$ = the natural loop of $v \\to v$, and both labels target $v$. The three readings
    coincide *on this shape*; the general claim that they coincide on every self-loop does not
    hold, and nothing here relies on it.

    Raises:
        ValueError: if ``node_id`` already lies on a cycle.
        KeyError: if ``node_id`` names no declared node.
    """
    return _counter_guard(ir, node_id, "counter-guard-without-exit", exit_target=None)


def counter_guard_with_exit(ir: WorkflowIR, node_id: str) -> Mutation:
    """The same guard with its else-label wired to ``END`` — **coherent**, form (a) discharged.

    One ``path_map`` value apart from :func:`counter_guard_without_exit`, and the pair is what
    makes the D4 side condition observable. Only the *gated then-label edge* enters $S$ (DEC-23
    Q1), and removing it from the element residual leaves the residual acyclic, so the pass
    carries a form-(a) inventory entry naming the guard, its counter key and its bound.

    The exit is ``"END"`` rather than a declared node on purpose: ``__end__`` has no outgoing
    edge (m5), so it can never be in the loop under either the natural-loop or the SCC reading,
    and a label wired to a *node* would risk that node lying on the cycle in some draw.

    Raises:
        ValueError: if ``node_id`` already lies on a cycle.
        KeyError: if ``node_id`` names no declared node.
    """
    return _counter_guard(ir, node_id, "counter-guard-with-exit", exit_target="END")


def _witnessable_loop(ir: WorkflowIR, node_id: str, operator: str) -> tuple[WorkflowIR, str]:
    """The normalized draw plus one self-loop and one fresh Σ key — the shared P-02 substrate.

    Returns the *unwitnessed* document (which fails P-02) and the key a form-(c) ``variant`` can
    name, so an operator builds its passing half by adding one annotation and its failing half by
    leaving it off.
    """
    normalized = without_effects(without_witnesses(ir))
    _require_acyclic(normalized, node_id, operator, whole_graph=True)
    looped = with_self_loop(normalized, node_id)
    key = _fresh(PROBE_KEY, frozenset(looped.state or {}))
    return with_state_field(looped, key, "str"), key


def _scc_location(node_id: str) -> P02SccLocation:
    """§2.3's residual-SCC anchor for a self-loop: the singleton, and the loop as its cycle.

    ``blanket_only`` stays absent, not ``false``: §2.3's fail shape omits the member and every
    residual-SCC fixture in the corpus omits it too (see
    :class:`~gebra.verify.locations.P02SccLocation`). A failing P-02 report here is by
    construction one with no justified blanket, so there is nothing for the member to say.
    """
    return P02SccLocation(
        kind="scc", nodes=(node_id,), representative_cycle=(node_id,), exhaustive=False
    )


def _counter_guard(
    ir: WorkflowIR, node_id: str, operator: str, *, exit_target: str | None
) -> Mutation:
    """A form-(a) guard on a fresh conditional self-loop, with or without a wired escape."""
    normalized = without_effects(without_witnesses(ir))
    _require_acyclic(normalized, node_id, operator, whole_graph=True)
    counter = _fresh(PROBE_COUNTER, frozenset(normalized.state or {}))
    origin = with_state_field(normalized, counter, "int")
    labels = {
        PROBE_THEN_LABEL: node_id,
        PROBE_ELSE_LABEL: node_id if exit_target is None else exit_target,
    }
    mutant = with_edge(
        origin,
        ConditionalEdge(
            kind="conditional",
            **{"from": node_id},
            condition=f"'{PROBE_THEN_LABEL}' if {counter} < {PROBE_BOUND} else '{PROBE_ELSE_LABEL}'",
            path_map=labels,
        ),
    )
    return Mutation(
        origin=origin,
        ir=mutant,
        operator=operator,
        target=TERMINATION_SLUG,
        condition=None if exit_target is not None else COUNTER_GUARD_WITHOUT_EXIT_EDGE,
        node=node_id,
        key=counter,
        location=None
        if exit_target is not None
        else P02CycleLocation(
            kind="cycle",
            nodes=(node_id,),
            counter_key=counter,
            guard_edge=GuardEdgeLabels(source=node_id, labels=tuple(labels)),
        ),
    )


# ── The strategies ───────────────────────────────────────────────────────────────────────


def dataflow_mutations(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE, operators: Sequence[str] | None = None
) -> st.SearchStrategy[Mutation]:
    """P-04 mutations over well-formed draws — :data:`DATAFLOW_OPERATORS`, or a named subset.

    Args:
        envelope: The size bounds the underlying draw uses
            (:class:`~gebra.testing.strategies.SizeEnvelope`).
        operators: Which operators to offer; every one by default. Naming a single operator is
            how a metaproperty targets one defect shape, and how a reachability ``find``
            asserts that shape is producible at all.

    Raises:
        ValueError: if ``operators`` names something that is not a P-04 operator.
    """
    return _dataflow_mutations(envelope, _selected(DATAFLOW_SLUG, operators))


def effect_safety_mutations(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE, operators: Sequence[str] | None = None
) -> st.SearchStrategy[Mutation]:
    """P-06 mutations over well-formed draws — :data:`EFFECT_SAFETY_OPERATORS`, or a subset.

    ``unprotected-cycle`` draws from an **acyclic** narrowing of ``envelope``
    (``max_extra_edges=0``, ``max_path_map_labels=1``, which together leave only the spanning
    forest), because it needs a node on no cycle to put its own self-loop on. Every other
    operator draws from ``envelope`` itself.

    Raises:
        ValueError: if ``operators`` names something that is not a P-06 operator.
    """
    return _effect_safety_mutations(envelope, _selected(EFFECT_SAFETY_SLUG, operators))


def determinism_mutations(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE, operators: Sequence[str] | None = None
) -> st.SearchStrategy[Mutation]:
    """P-08 mutations over well-formed draws — :data:`DETERMINISM_OPERATORS`, or a subset.

    Raises:
        ValueError: if ``operators`` names something that is not a P-08 operator.
    """
    return _determinism_mutations(envelope, _selected(DETERMINISM_SLUG, operators))


def well_formedness_mutations(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE, operators: Sequence[str] | None = None
) -> st.SearchStrategy[Mutation]:
    """P-01 mutations over well-formed draws — :data:`WELL_FORMEDNESS_OPERATORS`, or a subset.

    The one family whose breaking mutants are **not** P-01 clean — that is the point of it — so a
    cross-cutting metaproperty over :func:`mutations` scopes on
    :attr:`Mutation.well_formed` before quantifying anything §0.3 defines only over clean
    topology.

    Raises:
        ValueError: if ``operators`` names something that is not a P-01 operator.
    """
    return _well_formedness_mutations(envelope, _selected(WELL_FORMEDNESS_SLUG, operators))


def termination_mutations(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE, operators: Sequence[str] | None = None
) -> st.SearchStrategy[Mutation]:
    """P-02 mutations over well-formed draws — :data:`TERMINATION_OPERATORS`, or a subset.

    Every operator draws from the **acyclic** narrowing of ``envelope`` (the same one
    :func:`effect_safety_mutations` gives ``unprotected-cycle``, and for the same reason): each
    adds its own self-loop and needs the normalized origin to carry no cycle, so that it passes
    P-02 vacuously and the flip is attributable to the witness rather than to the draw.

    Raises:
        ValueError: if ``operators`` names something that is not a P-02 operator.
    """
    return _termination_mutations(envelope, _selected(TERMINATION_SLUG, operators))


def mutations(*, envelope: SizeEnvelope = DEFAULT_ENVELOPE) -> st.SearchStrategy[Mutation]:
    """Every operator of every target property — what a cross-cutting metaproperty ranges over."""
    return _mutations(envelope)


def _selected(slug: PropertySlug, operators: Sequence[str] | None) -> tuple[str, ...]:
    """``operators`` validated against the target property's table, in that table's order."""
    known = OPERATORS[slug]
    if operators is None:
        return known
    unknown = sorted(set(operators) - set(known))
    if unknown:
        raise ValueError(f"{unknown!r} are not {slug} operators; known: {list(known)}")
    chosen = tuple(name for name in known if name in set(operators))
    if not chosen:
        raise ValueError(f"no operator selected for {slug}")
    return chosen


@lru_cache(maxsize=_CACHE_SIZE)
def acyclic_envelope(envelope: SizeEnvelope) -> SizeEnvelope:
    """``envelope`` narrowed to draws with no cycle at all.

    Two bounds do it together, and both are needed. ``max_extra_edges=0`` leaves only the
    spanning structure, whose every edge runs from an earlier id to a later one. But a spanning
    edge may be a *router*, and a router's ``path_map`` carries extra labels drawn to arbitrary
    targets — so ``max_path_map_labels=1`` is what removes the backwards label that would
    otherwise close a cycle through an edge nobody counted as "extra".

    Public because every operator that *adds* a cycle needs its draw to carry none — P-06's
    ``unprotected-cycle`` and the whole P-02 family — and because a metaproperty that builds
    both polarities of one loop edit from a single draw (rather than from a
    :class:`Mutation`) needs the same narrowing to satisfy the same precondition.
    """
    return replace(envelope, max_extra_edges=0, max_path_map_labels=1)


@lru_cache(maxsize=_CACHE_SIZE)
def _one_of(values: tuple[str, ...]) -> st.SearchStrategy[str]:
    return st.sampled_from(values)


@lru_cache(maxsize=_CACHE_SIZE)
def _indices(count: int) -> st.SearchStrategy[int]:
    return st.integers(min_value=0, max_value=count - 1)


#: The two §6.3 trigger tags, sorted so a shrunk counterexample is stable.
_TRIGGERS: Final[tuple[str, ...]] = tuple(sorted(TRIGGER_TAGS))

#: The two Appendix B C-1 evidence tags, likewise.
_EVIDENCE: Final[tuple[str, ...]] = tuple(sorted(LLM_EVIDENCE_TAGS))

#: A pinned seed. Small and positive: §8 reads nothing off the value, and a shrunk
#: counterexample saying ``seed=0`` is easier to read than one saying ``seed=-4503599627370495``.
_SEEDS: Final = st.integers(min_value=0, max_value=9999)

#: A temperature that is **not** pinned to zero — absent, or a positive value.
_UNPINNED_TEMPERATURES: Final = st.none() | st.floats(
    min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False
)


@lru_cache(maxsize=_CACHE_SIZE)
def _dataflow_mutations(
    envelope: SizeEnvelope, operators: tuple[str, ...]
) -> st.SearchStrategy[Mutation]:
    return _draw_dataflow(envelope, operators)


@st.composite
def _draw_dataflow(draw: st.DrawFn, envelope: SizeEnvelope, operators: tuple[str, ...]) -> Mutation:
    """Draw an operator, a well-formed workflow and the node to anchor the defect at."""
    operator = draw(_one_of(operators))
    ir = draw(workflow_irs(envelope=envelope))
    node_id = ir.nodes[draw(_indices(len(ir.nodes)))].id
    if operator == "unwritten-read":
        return unwritten_read(ir, node_id)
    if operator == "self-write":
        return self_write(ir, node_id)
    if operator == "boundary-read":
        return boundary_read(ir, node_id, optional=draw(st.booleans()))
    if operator == "universal-write":
        return universal_write(ir, node_id)
    return foreign_read(ir, node_id)


@lru_cache(maxsize=_CACHE_SIZE)
def _effect_safety_mutations(
    envelope: SizeEnvelope, operators: tuple[str, ...]
) -> st.SearchStrategy[Mutation]:
    return _draw_effect_safety(envelope, operators)


@st.composite
def _draw_effect_safety(
    draw: st.DrawFn, envelope: SizeEnvelope, operators: tuple[str, ...]
) -> Mutation:
    """Draw an operator, then the workflow from whichever envelope that operator needs."""
    operator = draw(_one_of(operators))
    bounds = acyclic_envelope(envelope) if operator == "unprotected-cycle" else envelope
    ir = draw(workflow_irs(envelope=bounds))
    node_id = ir.nodes[draw(_indices(len(ir.nodes)))].id
    tag = draw(_one_of(_TRIGGERS))
    if operator == "unprotected-retry-region":
        return unprotected_retry_region(ir, node_id, tag)
    if operator == "unprotected-cycle":
        return unprotected_cycle(ir, node_id, tag)
    if operator == "forbidden-combination":
        return forbidden_combination(ir, node_id)
    if operator == "unbound-key":
        return unbound_key(ir, node_id, tag)
    if operator == "dangling-hook":
        return dangling_hook(ir, node_id, tag)
    if operator == "bound-key":
        return bound_key(ir, node_id, tag)
    hook = ir.nodes[draw(_indices(len(ir.nodes)))].id
    return compensation_hook(ir, node_id, tag, hook)


@lru_cache(maxsize=_CACHE_SIZE)
def _determinism_mutations(
    envelope: SizeEnvelope, operators: tuple[str, ...]
) -> st.SearchStrategy[Mutation]:
    return _draw_determinism(envelope, operators)


@st.composite
def _draw_determinism(
    draw: st.DrawFn, envelope: SizeEnvelope, operators: tuple[str, ...]
) -> Mutation:
    """Draw an operator, a well-formed workflow, the claiming node and its evidence tag."""
    operator = draw(_one_of(operators))
    ir = draw(workflow_irs(envelope=envelope))
    node_id = ir.nodes[draw(_indices(len(ir.nodes)))].id
    tag = draw(_one_of(_EVIDENCE))
    if operator == "bare-claim":
        return bare_claim(ir, node_id, tag)
    if operator == "unpinned-temperature":
        return unpinned_temperature(ir, node_id, tag, draw(_SEEDS), draw(_UNPINNED_TEMPERATURES))
    if operator == "pinned-claim":
        return pinned_claim(ir, node_id, tag, draw(_SEEDS))
    if operator == "local-claim":
        return local_claim(ir, node_id)
    return disclaimed_determinism(ir, node_id, tag)


@lru_cache(maxsize=_CACHE_SIZE)
def _well_formedness_mutations(
    envelope: SizeEnvelope, operators: tuple[str, ...]
) -> st.SearchStrategy[Mutation]:
    return _draw_well_formedness(envelope, operators)


@st.composite
def _draw_well_formedness(
    draw: st.DrawFn, envelope: SizeEnvelope, operators: tuple[str, ...]
) -> Mutation:
    """Draw an operator, a well-formed workflow and the node the new wiring hangs off."""
    operator = draw(_one_of(operators))
    ir = draw(workflow_irs(envelope=envelope))
    node_id = ir.nodes[draw(_indices(len(ir.nodes)))].id
    if operator == "unreachable-node":
        return unreachable_node(ir)
    if operator == "severed-edge":
        return severed_edge(ir, node_id)
    if operator == "dead-end-node":
        return dead_end_node(ir, node_id)
    if operator == "undefined-entry-id":
        return undefined_entry_id(ir)
    if operator == "undefined-finish-id":
        return undefined_finish_id(ir)
    if operator == "undefined-edge-source":
        return undefined_edge_source(ir, node_id)
    if operator == "undefined-edge-target":
        return undefined_edge_target(ir, node_id)
    if operator == "undefined-path-map-target":
        return undefined_path_map_target(ir, node_id)
    if operator == "orphan-node":
        return orphan_node(ir)
    if operator == "empty-entry":
        return empty_entry(ir)
    return wired_leaf(ir, node_id)


@lru_cache(maxsize=_CACHE_SIZE)
def _termination_mutations(
    envelope: SizeEnvelope, operators: tuple[str, ...]
) -> st.SearchStrategy[Mutation]:
    return _draw_termination(acyclic_envelope(envelope), operators)


@st.composite
def _draw_termination(
    draw: st.DrawFn, envelope: SizeEnvelope, operators: tuple[str, ...]
) -> Mutation:
    """Draw an operator, an **acyclic** workflow and the node the self-loop goes on."""
    operator = draw(_one_of(operators))
    ir = draw(workflow_irs(envelope=envelope))
    node_id = ir.nodes[draw(_indices(len(ir.nodes)))].id
    if operator == "removed-variant":
        return removed_variant(ir, node_id)
    if operator == "removed-blanket":
        return removed_blanket(ir, node_id)
    if operator == "unqualified-variant":
        return unqualified_variant(ir, node_id)
    if operator == "unwitnessed-two-cycle":
        return unwitnessed_two_cycle(ir, node_id)
    if operator == "counter-guard-without-exit":
        return counter_guard_without_exit(ir, node_id)
    return counter_guard_with_exit(ir, node_id)


@lru_cache(maxsize=_CACHE_SIZE)
def _mutations(envelope: SizeEnvelope) -> st.SearchStrategy[Mutation]:
    return st.one_of(
        _dataflow_mutations(envelope, DATAFLOW_OPERATORS),
        _effect_safety_mutations(envelope, EFFECT_SAFETY_OPERATORS),
        _determinism_mutations(envelope, DETERMINISM_OPERATORS),
        _well_formedness_mutations(envelope, WELL_FORMEDNESS_OPERATORS),
        _termination_mutations(envelope, TERMINATION_OPERATORS),
    )


# Three node-id constants are checked at import rather than trusted, because an ungrammatical one
# would silently test something weaker instead of failing: a grammatical probe hook is what makes
# the `dangling_compensation_hook` evidence field observable at all (§6.4 drops an ungrammatical
# one), a grammatical `PROBE_NODE` is what lets a declared node be declared at all, and a
# grammatical `PROBE_TARGET` is what lets P-01 spell an unresolved reference into a
# `P01EdgeLocation`, whose `source` is a `NodeId`. This module is imported by every suite that
# uses it, so the check runs once and early.
for _constant, _value in (
    ("PROBE_HOOK", PROBE_HOOK),
    ("PROBE_NODE", PROBE_NODE),
    ("PROBE_TARGET", PROBE_TARGET),
):
    if not is_valid_node_id(_value):  # pragma: no cover - constants, checked once
        raise ValueError(f"{_constant}={_value!r} must satisfy the IR-SPEC §5.1 node-id grammar")
