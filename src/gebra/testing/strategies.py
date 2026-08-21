"""Hypothesis strategies that generate well-formed ``ir_version`` 1.0 workflows — D-10 W6.

This is the generation substrate the metaproperty suites are built on: it produces
:class:`~gebra.ir.WorkflowIR` values that are *well-formed*, so a suite that wants a broken
IR mutates one of these rather than hoping a random draw is broken in the way it needs.

    from gebra.testing.strategies import workflow_irs

    @given(ir=workflow_irs())
    def test_something_about_every_well_formed_workflow(ir: WorkflowIR) -> None:
        ...

**What "well-formed" means here**, stated as the checkable list the accompanying suite
(``tests/testing/test_strategies.py``) holds this module to:

1. the document validates as ``ir_version`` 1.0 — the models' own requirement, and every
   value is built through validation (memo A6 PC-6 bans ``model_construct``);
2. ``nodes[].id`` satisfies the IR-SPEC §5 grammar, ids are pairwise distinct, and no
   segment is a reserved sentinel;
3. **every reference resolves** — ``entry``, ``finish``, an edge's ``from``, a
   ``normal``/``send`` edge's ``to``, every ``path_map`` value (bar the ``"END"`` literal),
   ``runtime.interrupts`` members and ``annotations.compensation.hook``;
4. the graph is **P-01 clean**: every node reachable from ``START``, no node without an
   outgoing edge in $G^*$, no orphan under Reading A, no unresolved reference — i.e.
   :func:`~gebra.verify.properties.graph_well_formed.check_graph_well_formed` passes;
5. the IR-SPEC §2.3 cross-field obligations hold — ``annotations.input``/``output`` are
   subsets of ``keys(state)`` and ``idempotent.key`` names a member of ``input`` — as does
   §3.3's reading of ``variant.key`` as a state key;
6. every scalar is canonicalizable: integers inside ±(2^53−1) and doubles finite and inside
   the same range (IR-SPEC §6.3; PD-004), so ``graph_version`` never refuses a draw.

Two details of the frozen semantics decide the shape of the generator, and both are easy to
get wrong from the surface syntax alone:

* **``to: "END"`` is not a sentinel incidence.** PD-007 Q2 blessed the ``"END"`` literal for
  ``path_map`` values only, so a ``normal``/``send`` edge writing it is an *unresolved
  reference* (see :func:`~gebra.verify.graph.build_graph_model`'s (m4) note). END is
  therefore reached here in exactly the two ways the model admits: ``finish`` membership
  (m2), and a ``path_map`` label valued ``"END"`` (m3).
* **A node with no outgoing edge must be in ``finish``**, because P-01's condition (ii) is a
  sink scan over $G^*$ and ``finish`` membership is what supplies the edge to ``__end__``.
  :func:`topologies` therefore derives ``finish`` from the edge set rather than drawing it
  freely.

**What is deliberately *not* constrained.** P-02, P-04, P-06 and P-08 verdicts are free: a
draw may or may not have a termination witness, complete dataflow, safe effects or pinned
determinism. That variation is the point — it is what the contract/advisory metaproperties
have to range over — and §0.3's precondition is that those validators are defined over
P-01-clean topology, which is what item 4 supplies.

**Envelopes.** Every strategy takes an ``envelope`` (:class:`SizeEnvelope`), a frozen record
of the size bounds; :data:`DEFAULT_ENVELOPE` is what the metaproperty suites should use,
:data:`MINIMAL_ENVELOPE` pins the degenerate single-node graph, and :data:`WIDE_ENVELOPE`
trades speed for shape variety. Bounds are *maxima*: the minima are structural (one node, and
zero of everything else), so shrinking always converges on the same floor — one node, ``entry
== finish ==`` that node, no edges, no state, no contracts, no runtime.

**Composition seams.** :func:`topologies` yields a :class:`Topology` — ids, edges and the two
wiring lists — before any contract or schema content is attached, and :func:`workflow_irs`
accepts one as an argument. That is the seam a mutation operator wants: it can rewrite the
topology and rebuild the IR around it without regenerating anything else.

Nothing here imports langgraph or langchain, opens a socket, or executes anything: the
strategies build frozen pydantic values out of generated primitives, and the node-id work is
string and Unicode transformation over :mod:`gebra.ir.identity` (WA-07). The tripwire is
``tests/testing/test_hermeticity.py``, whose guarded child generates from this module and runs
P-01 over each draw in an interpreter where a substrate import, a socket and a name resolution
each raise.

This module is the one part of :mod:`gebra.testing` that needs ``hypothesis``, which is a
development dependency rather than a runtime one — so it is deliberately *not* imported by
:mod:`gebra.testing`'s package body, and importing it without hypothesis installed raises an
:class:`ImportError` that says so.
"""

from __future__ import annotations

import string
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final, TypeVar

try:
    from hypothesis import strategies as st
except ImportError as error:  # pragma: no cover - the dev environment always has it
    raise ImportError(
        "gebra.testing.strategies needs hypothesis, which gebra declares as a development "
        "dependency rather than a runtime one: install it with `pip install hypothesis` (or "
        '`pip install "gebra[dev]"`). Every other module in gebra.testing works without it.'
    ) from error

from gebra.ir.canonical import I_JSON_MAX_INT
from gebra.ir.identity import RESERVED_SEGMENTS, SYNTHETIC_KINDS, escape_segment, synthetic_segment
from gebra.ir.identity import join_node_id as _join_node_id
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    Edge,
    IdempotentKey,
    Interrupts,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    SendEdge,
    StateField,
    Variant,
    WorkflowIR,
)

__all__ = [
    "CONTRACT_SLOTS",
    "DEFAULT_ENVELOPE",
    "EFFECT_TAGS",
    "END_LITERAL",
    "MINIMAL_ENVELOPE",
    "RUNTIME_SLOTS",
    "WIDE_ENVELOPE",
    "SizeEnvelope",
    "Topology",
    "digests",
    "node_contracts",
    "node_id_sets",
    "node_ids",
    "nodes",
    "runtimes",
    "source_names",
    "state_schemas",
    "synthetic_segments",
    "topologies",
    "user_segments",
    "workflow_irs",
]

#: The one target string that is not a node id — blessed for ``path_map`` values only
#: (ledger §1/§4; PD-007 Q2), which is why it never appears as a ``normal``/``send`` ``to``.
END_LITERAL: Final = "END"

#: The effect vocabulary the vendored corpus uses (``tests/fixtures/properties/``). Tags are
#: opaque strings to the IR models; drawing from the corpus's set keeps a generated contract
#: recognizable to a reader who knows the fixtures, and keeps P-06's input space realistic.
EFFECT_TAGS: Final[tuple[str, ...]] = ("billable", "external", "irreversible", "network")

#: Every member of :class:`~gebra.ir.Annotations` — the eight retained §2.3 slots followed by
#: the six new-in-1.0 §3 slots (PD-003 Appendix A rows 1–6), in model declaration order.
#: :func:`node_contracts` draws a *subset* of these to populate, and
#: ``tests/testing/test_strategies.py`` checks the tuple against the live model, so a slot
#: added to the IR without being added here fails that suite rather than going ungenerated.
CONTRACT_SLOTS: Final[tuple[str, ...]] = (
    "pure",
    "effect",
    "idempotent",
    "deterministic",
    "input",
    "output",
    "source",
    "map",
    "args_schema",
    "retry_policy",
    "variant",
    "compensation",
    "prompt_digest",
    "config_digest",
)

#: The three sub-slots of :class:`~gebra.ir.Runtime` (IR-SPEC §3.5, §3.7), in model
#: declaration order. :func:`runtimes` draws a subset, the same way :func:`node_contracts`
#: does, and the accompanying suite checks the tuple against the live model.
RUNTIME_SLOTS: Final[tuple[str, ...]] = ("recursion_limit", "interrupts", "checkpointer")

#: The value a slot-conditional draw returns, in :func:`node_contracts`.
_T = TypeVar("_T")

#: How many built strategies to keep, per builder.
#:
#: **Why any of this is cached.** A ``@st.composite`` body runs once per example, so every
#: strategy it *constructs* is rebuilt a thousand times over a thousand-example run — and the
#: tree under :func:`workflow_irs` is deep enough that rebuilding it, rather than drawing from
#: it, was two thirds of the per-example cost when measured. Strategy objects are immutable
#: and reusable, so the public entry points below are thin argument-normalizing wrappers over
#: cached private builders; hypothesis's own ``st.*`` functions are memoized for exactly this
#: reason. Every cache key is a value — a :class:`SizeEnvelope`, a tuple of ids, an int — or a
#: strategy the caller passed in, so a bound is enough to keep a caller that hands in freshly
#: built strategies in a loop from growing one without limit.
_CACHE_SIZE: Final = 512


# ── The size envelope ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SizeEnvelope:
    """The size bounds a family of strategies draws inside.

    Every field is a **maximum**; the minima are structural and not configurable, because
    they are what makes shrinking converge. A workflow has at least one node and at least one
    ``entry`` id, and everything else bottoms out at zero: no edges beyond the ones
    reachability needs, no state keys, no contract, no runtime block.

    Attributes:
        max_nodes: Upper bound on ``len(nodes)``. At least 1.
        max_entry_ids: Upper bound on ``len(entry)`` — the number of roots the spanning
            structure starts from. At least 1, and clamped to the node count.
        max_extra_edges: Edges drawn *beyond* the spanning structure. These are what
            introduce cycles, self-loops and parallel edges, so zero means "every draw is a
            forest".
        max_extra_finish: ``finish`` members drawn beyond the sinks that P-01's condition (ii)
            requires.
        max_state_keys: Upper bound on ``len(state)``.
        max_contract_keys: Upper bound on ``len(annotations.input)`` and ``…output``, further
            clamped to the number of state keys (they are subsets of it, §2.3).
        max_contract_slots: Upper bound on how many of the fourteen :data:`CONTRACT_SLOTS` one
            contract *draws a value for*. Zero means every drawn contract is ``Annotations()``.
            One member can ride along beyond this bound, and only one: a keyed ``idempotent``
            marker also populates ``input`` when ``input`` was not itself drawn, because §2.3
            scopes the key to it.
        max_id_segments: Nesting depth of a generated node id (IR-SPEC §5.1). At least 1.
        max_path_map_labels: Upper bound on ``len(path_map)``. At least 1 — a conditional
            edge with no labels expands to nothing and could not carry its spanning target.
        max_effect_tags: Upper bound on ``len(annotations.effect)``.
        max_retry_on: Upper bound on ``len(annotations.retry_policy.retry_on)``.
        max_args_schema_keys: Upper bound on ``len(annotations.args_schema)``.
        max_interrupts: Upper bound on ``len(runtime.interrupts.before)`` and ``…after``.
        max_runtime_slots: Upper bound on how many of the three :data:`RUNTIME_SLOTS` a
            ``runtime`` block populates. Zero means every drawn block is ``Runtime()``.

    Raises:
        ValueError: if a bound is below its structural floor.
    """

    max_nodes: int = 5
    max_entry_ids: int = 2
    max_extra_edges: int = 4
    max_extra_finish: int = 2
    max_state_keys: int = 4
    max_contract_keys: int = 3
    max_contract_slots: int = 4
    max_id_segments: int = 2
    max_path_map_labels: int = 3
    max_effect_tags: int = 2
    max_retry_on: int = 2
    max_args_schema_keys: int = 2
    max_interrupts: int = 2
    max_runtime_slots: int = 3

    def __post_init__(self) -> None:
        floors = {
            "max_nodes": 1,
            "max_entry_ids": 1,
            "max_id_segments": 1,
            "max_path_map_labels": 1,
            "max_extra_edges": 0,
            "max_extra_finish": 0,
            "max_state_keys": 0,
            "max_contract_keys": 0,
            "max_contract_slots": 0,
            "max_effect_tags": 0,
            "max_retry_on": 0,
            "max_args_schema_keys": 0,
            "max_interrupts": 0,
            "max_runtime_slots": 0,
        }
        for name, floor in floors.items():
            value = getattr(self, name)
            if value < floor:
                raise ValueError(
                    f"{name}={value} is below the structural floor {floor}: a SizeEnvelope "
                    "field is a maximum, and the minima are what make shrinking converge"
                )


#: What the metaproperty suites should quantify over: small enough that a thousand examples
#: is cheap, wide enough that cycles, routers, fan-out templates, nested ids and populated
#: contracts are all reachable (each one asserted reachable in the accompanying suite).
DEFAULT_ENVELOPE: Final = SizeEnvelope()

#: The degenerate floor: exactly one node, no edges, and every optional block either absent or
#: empty. Useful for pinning what a shrunk counterexample looks like, and for suites that only
#: need *a* valid workflow as cheaply as possible.
MINIMAL_ENVELOPE: Final = SizeEnvelope(
    max_nodes=1,
    max_entry_ids=1,
    max_extra_edges=0,
    max_extra_finish=0,
    max_state_keys=0,
    max_contract_keys=0,
    max_contract_slots=0,
    max_id_segments=1,
    max_path_map_labels=1,
    max_effect_tags=0,
    max_retry_on=0,
    max_args_schema_keys=0,
    max_interrupts=0,
    max_runtime_slots=0,
)

#: Shape variety over speed — for a suite that wants denser graphs than a per-example budget
#: of a millisecond or two allows.
WIDE_ENVELOPE: Final = SizeEnvelope(
    max_nodes=10,
    max_entry_ids=3,
    max_extra_edges=14,
    max_extra_finish=4,
    max_state_keys=8,
    max_contract_keys=5,
    max_contract_slots=8,
    max_id_segments=3,
    max_path_map_labels=4,
    max_effect_tags=4,
    max_retry_on=3,
    max_args_schema_keys=3,
    max_interrupts=3,
    max_runtime_slots=3,
)


# ── Names, segments and node ids (IR-SPEC §5) ────────────────────────────────────────────

#: A plain lowercase identifier — the shape a hand-written fixture uses, and the shape a
#: shrunk counterexample should end up with.
_PLAIN_NAME: Final = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_", min_size=1, max_size=6
)

#: Source names that exercise the §5.1 escaping rules rather than the graph: a literal ``/``
#: and a literal ``%``, something already shaped like a synthetic token, a precomposed and a
#: decomposed accented form (NFC normalization is part of escaping), a non-BMP scalar (which
#: is where the ledger §6 UTF-16 comparator and Python's code-point order disagree), and a
#: space. Escaping is :func:`~gebra.ir.identity.escape_segment`'s, never this module's.
_AWKWARD_NAMES: Final[tuple[str, ...]] = (
    "a/b",
    "100%",
    "%seq[0]",
    "caf\u00e9",  # precomposed — already NFC
    "cafe\u0301",  # decomposed — escaping NFC-normalizes it onto the line above
    "\U0001f600",
    "two words",
)

#: A short label for a ``path_map`` key or a state key.
_LABEL: Final = st.text(alphabet=string.ascii_lowercase + "_", min_size=1, max_size=4)

#: Declared state types and reducers, as the corpus spells them (IR-SPEC §2.2).
_STATE_TYPES: Final = st.sampled_from(("str", "int", "bool", "list[str]", "dict[str, Any]"))
_REDUCERS: Final = st.sampled_from(("operator.add", "operator.or_", "add_messages"))

#: Opaque exception-name strings for ``retry_policy.retry_on`` (IR-SPEC §3.2).
_EXCEPTION_NAMES: Final = st.sampled_from(("ValueError", "TimeoutError", "ConnectionError"))

#: Declared measures for a §3.3 variant, and router/guard expressions. Both are inert
#: declared content — never parsed and never evaluated (§2.4).
_MEASURES: Final = st.sampled_from(("decreasing", "len", "bounded"))
_CONDITIONS: Final = st.sampled_from(("route", "should_continue", "needs_review"))

#: Integers inside the I-JSON exact range (IR-SPEC §6.3; PD-004) — outside it a document has
#: no canonical form, so a generator that left the range would produce un-hashable draws.
_EXACT_INTEGERS: Final = st.integers(min_value=-I_JSON_MAX_INT, max_value=I_JSON_MAX_INT)

#: Finite doubles, bounded to the same range: §6.3 reads an integral double as an integer, so
#: ``9007199254740992.0`` is an out-of-range integer rather than a large float.
_EXACT_FLOATS: Final = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-I_JSON_MAX_INT, max_value=I_JSON_MAX_INT
)


def source_names() -> st.SearchStrategy[str]:
    """A *source-level* name — what a segment is escaped **from** (IR-SPEC §5.1).

    Plain identifiers first, then the awkward forms that exercise escaping and NFC
    normalization. Names escaping to a reserved segment are excluded, so a name from here is
    always usable at any nesting level.

    The grammar itself is fuzzed over arbitrary text by ``tests/ir/test_identity_properties``;
    the alphabet here is curated because these strategies are about *graph shape*, and an id
    that is hard to read costs a reader of a shrunk counterexample far more than it buys.
    """
    return _source_names()


def user_segments() -> st.SearchStrategy[str]:
    """One escaped user segment — :func:`~gebra.ir.identity.escape_segment` of a source name."""
    return _user_segments()


def synthetic_segments() -> st.SearchStrategy[str]:
    """One synthetic LCEL segment, ``"%" kind "[" selector "]"`` (IR-SPEC §5.2).

    ``kind`` is drawn from the closed 1.0 vocabulary
    (:data:`~gebra.ir.identity.SYNTHETIC_KINDS`) and the selector is either a structural
    index or a source-level key, which is exactly the two cases §5.2 names.
    """
    return _synthetic_segments()


def node_ids(*, envelope: SizeEnvelope = DEFAULT_ENVELOPE) -> st.SearchStrategy[str]:
    """A node id: one to ``envelope.max_id_segments`` segments, ``/``-joined (IR-SPEC §5.1).

    Joining goes through :func:`~gebra.ir.identity.join_node_id`, which validates every
    segment — so a draw that reached a caller has already been through the grammar rather
    than merely been built to look like it.
    """
    return _node_ids(envelope)


def node_id_sets(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE
) -> st.SearchStrategy[tuple[str, ...]]:
    """One to ``envelope.max_nodes`` pairwise-distinct node ids."""
    return _node_id_sets(envelope)


def digests() -> st.SearchStrategy[str]:
    """A ``"sha256:<64 lowercase hex>"`` string — the §3.6 digest form.

    Rendered from a small integer rather than drawn character by character: the shape is
    fixed, nothing in 1.0 reads the value, and this way a shrunk example is
    ``sha256:000…0`` instead of sixty-four independently shrinking characters.
    """
    return _digests()


@lru_cache(maxsize=1)
def _source_names() -> st.SearchStrategy[str]:
    return (_PLAIN_NAME | st.sampled_from(_AWKWARD_NAMES)).filter(
        lambda name: escape_segment(name) not in RESERVED_SEGMENTS
    )


@lru_cache(maxsize=1)
def _user_segments() -> st.SearchStrategy[str]:
    return _source_names().map(escape_segment)


@lru_cache(maxsize=1)
def _synthetic_segments() -> st.SearchStrategy[str]:
    return st.builds(
        synthetic_segment,
        kind=st.sampled_from(sorted(SYNTHETIC_KINDS)),
        selector=st.integers(min_value=0, max_value=3) | _source_names(),
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _node_ids(envelope: SizeEnvelope) -> st.SearchStrategy[str]:
    segments = st.lists(
        _user_segments() | _synthetic_segments(),
        min_size=1,
        max_size=envelope.max_id_segments,
    )
    return segments.map(_join_node_id)


@lru_cache(maxsize=_CACHE_SIZE)
def _node_id_sets(envelope: SizeEnvelope) -> st.SearchStrategy[tuple[str, ...]]:
    return st.lists(
        _node_ids(envelope),
        min_size=1,
        max_size=envelope.max_nodes,
        unique=True,
    ).map(tuple)


@lru_cache(maxsize=1)
def _digests() -> st.SearchStrategy[str]:
    return st.integers(min_value=0, max_value=2**32 - 1).map(lambda value: f"sha256:{value:064x}")


@lru_cache(maxsize=_CACHE_SIZE)
def _one_of(values: tuple[str, ...]) -> st.SearchStrategy[str]:
    """``st.sampled_from(values)``, built once per distinct id tuple."""
    return st.sampled_from(values)


@lru_cache(maxsize=_CACHE_SIZE)
def _counts(minimum: int, maximum: int) -> st.SearchStrategy[int]:
    """``st.integers(minimum, maximum)``, built once per distinct bound pair."""
    return st.integers(min_value=minimum, max_value=maximum)


@lru_cache(maxsize=_CACHE_SIZE)
def _distinct_subsets(values: tuple[str, ...], max_size: int) -> st.SearchStrategy[list[str]]:
    """A distinct sub-list of ``values``, built once per (values, bound) pair."""
    if not values or max_size == 0:
        return st.just([])
    return st.lists(_one_of(values), max_size=min(len(values), max_size), unique=True)


# ── Topology (IR-SPEC §2.4, §4.1; PROPERTY-CATALOG-SPEC §1) ──────────────────────────────


@dataclass(frozen=True, slots=True)
class Topology:
    """A generated graph before any contract or schema content is attached to it.

    The seam a mutation operator wants: rewrite one of these and rebuild the IR around it
    with :func:`workflow_irs`, instead of regenerating state and contracts too.

    Attributes:
        node_ids: The declared ids, in the order they become ``nodes[]``.
        entry: The ``entry`` value in its surface form — a scalar id or a tuple (§2.1).
        finish: The ``finish`` value in its surface form. Possibly the empty tuple, when
            every node has an outgoing edge (DEC-18: the empty list is a value).
        edges: The ``edges`` value.
    """

    node_ids: tuple[str, ...]
    entry: str | tuple[str, ...]
    finish: str | tuple[str, ...]
    edges: tuple[Edge, ...]

    @property
    def entry_ids(self) -> tuple[str, ...]:
        """``entry`` as a tuple, whichever surface form it was drawn in."""
        return _as_tuple(self.entry)

    @property
    def finish_ids(self) -> tuple[str, ...]:
        """``finish`` as a tuple, whichever surface form it was drawn in."""
        return _as_tuple(self.finish)


def _as_tuple(wiring: str | tuple[str, ...]) -> tuple[str, ...]:
    return (wiring,) if isinstance(wiring, str) else wiring


def topologies(
    *,
    envelope: SizeEnvelope = DEFAULT_ENVELOPE,
    ids: st.SearchStrategy[Sequence[str]] | None = None,
) -> st.SearchStrategy[Topology]:
    """A P-01-clean topology: reachable from ``START``, no sinks off ``finish``, no orphans.

    Construction, in the order the draws happen — which is also the order shrinking undoes
    them:

    1. **The ids** (:func:`node_id_sets`, or ``ids`` when a caller supplies one).
    2. **The roots.** The first one to ``envelope.max_entry_ids`` ids become ``entry``. The
       empty ``entry`` DEC-18 ratifies is deliberately *not* generated: with no wiring from
       ``START`` every node is unreachable, so it is a P-01-*failing* shape and belongs to a
       mutation operator, not here.
    3. **A spanning structure.** Each remaining id is attached by one edge from an id already
       known to be reachable, so condition (i) holds by construction rather than by filtering
       — no ``assume``, no rejected draws.
    4. **Extra edges**, up to ``envelope.max_extra_edges``, from any id to any id or to
       ``"END"``. This is where cycles, self-loops, parallel edges and router-terminated
       wiring (m3) come from.
    5. **``finish``.** Every id that is not the ``from`` of some edge has no outgoing edge in
       $G^*$, so P-01's condition (ii) requires it in ``finish``; those are included, plus up
       to ``envelope.max_extra_finish`` others. When every id has an outgoing edge the result
       may be the empty tuple, which is the ratified serialization rather than a gap.

    Condition (iii) needs no step of its own: under Reading A (DEC-11) ``entry``/``finish``
    membership is edge participation, and every id is in ``entry``, or in ``finish``, or
    carries a spanning edge.
    """
    return _topologies(envelope, ids if ids is not None else _node_id_sets(envelope))


@lru_cache(maxsize=_CACHE_SIZE)
def _topologies(
    envelope: SizeEnvelope, ids: st.SearchStrategy[Sequence[str]]
) -> st.SearchStrategy[Topology]:
    return _draw_topology(envelope, ids)


@st.composite
def _draw_topology(
    draw: st.DrawFn, envelope: SizeEnvelope, ids: st.SearchStrategy[Sequence[str]]
) -> Topology:
    """The five construction steps of :func:`topologies`, in draw order."""
    identifiers = tuple(draw(ids))
    if not identifiers:
        raise ValueError("a topology needs at least one node id (IR-SPEC §2.1: nodes[] is 1*)")

    root_count = draw(_counts(1, min(len(identifiers), envelope.max_entry_ids)))
    entry_ids = identifiers[:root_count]
    anywhere = _one_of(identifiers)

    edges: list[Edge] = []
    for position in range(root_count, len(identifiers)):
        source = draw(_one_of(identifiers[:position]))
        edges.append(draw(_edges_from(source, identifiers[position], identifiers, envelope)))

    anywhere_or_end = _one_of((*identifiers, END_LITERAL))
    for _ in range(draw(_counts(0, envelope.max_extra_edges))):
        source = draw(anywhere)
        target = draw(anywhere_or_end)
        edges.append(draw(_edges_from(source, target, identifiers, envelope)))

    sources = {edge.from_ for edge in edges}
    sinks = tuple(node_id for node_id in identifiers if node_id not in sources)
    extra_finish = draw(_distinct_subsets(identifiers, envelope.max_extra_finish))
    finish_ids = tuple(dict.fromkeys((*sinks, *extra_finish)))

    return Topology(
        node_ids=identifiers,
        entry=draw(_wirings(entry_ids)),
        finish=draw(_wirings(finish_ids)),
        edges=tuple(edges),
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _wirings(ids: tuple[str, ...]) -> st.SearchStrategy[str | tuple[str, ...]]:
    """``entry``/``finish`` in one of its admitted surface forms (IR-SPEC §2.1).

    A singleton is authored either as the scalar id or as a one-member list, and both load;
    the scalar comes first so a shrunk example carries the commoner form. Anything else has
    only the list form — including the empty list, whose scalar counterpart §2.1 rules out in
    terms (``""`` would be a second encoding of the empty set).
    """
    if len(ids) == 1:
        return st.sampled_from((ids[0], ids))
    return st.just(ids)


@lru_cache(maxsize=_CACHE_SIZE)
def _edges_from(
    source: str,
    target: str,
    identifiers: tuple[str, ...],
    envelope: SizeEnvelope,
) -> st.SearchStrategy[Edge]:
    """An edge from ``source`` that reaches ``target`` — one per §2.4 kind.

    ``target`` is reached directly for a ``normal`` or ``send`` edge and through one
    ``path_map`` label for a ``conditional`` one, so the caller can rely on the incidence
    whichever kind is drawn.

    ``target`` may be :data:`END_LITERAL`, and then the edge is a router: on a
    ``normal``/``send`` ``to`` the literal would be an unresolved reference rather than a
    wiring to ``__end__`` (PD-007 Q2), so those two kinds are not offered. A router whose only
    label is valued ``"END"`` is what an ordinary router-terminated workflow looks like, which
    is why it is reachable here rather than only as one label among several.
    """
    conditions = st.none() | _CONDITIONS
    conditional: st.SearchStrategy[Edge] = st.builds(
        ConditionalEdge,
        kind=st.just("conditional"),
        from_=st.just(source),
        condition=conditions,
        path_map=_path_maps(target, identifiers, envelope),
    )
    if target == END_LITERAL:
        return conditional
    normal: st.SearchStrategy[Edge] = st.builds(
        NormalEdge,
        kind=st.just("normal"),
        from_=st.just(source),
        to=st.just(target),
        condition=conditions,
    )
    send: st.SearchStrategy[Edge] = st.builds(
        SendEdge,
        kind=st.just("send"),
        from_=st.just(source),
        to=st.just(target),
        condition=conditions,
    )
    return st.one_of(normal, conditional, send)


@lru_cache(maxsize=_CACHE_SIZE)
def _path_maps(
    target: str,
    identifiers: tuple[str, ...],
    envelope: SizeEnvelope,
) -> st.SearchStrategy[dict[str, str]]:
    """A router's label map, containing ``target`` and possibly other labels (§2.4).

    Every value resolves: a declared id, or the ``"END"`` literal, which (m3) expands to the
    ``__end__`` sentinel. The forced label is written last so it survives a key collision
    with one of the drawn labels.
    """
    others = st.dictionaries(
        _LABEL,
        _one_of((*identifiers, END_LITERAL)),
        max_size=envelope.max_path_map_labels - 1,
    )
    return st.builds(
        lambda label, rest: {**rest, label: target},
        label=_LABEL,
        rest=others,
    )


# ── State schema Σ (IR-SPEC §2.2) ────────────────────────────────────────────────────────


def state_schemas(
    *, envelope: SizeEnvelope = DEFAULT_ENVELOPE
) -> st.SearchStrategy[dict[str, str | StateField]]:
    """The ``state`` mapping: key → bare type name, or the object form (IR-SPEC §2.2).

    Both surface forms are drawn, because they are not interchangeable — a value carrying a
    ``reducer`` or an ``optional`` flag *must* be the object form, and those two members are
    what P-04 and P-09 read.
    """
    return _state_schemas(envelope)


@lru_cache(maxsize=_CACHE_SIZE)
def _state_schemas(envelope: SizeEnvelope) -> st.SearchStrategy[dict[str, str | StateField]]:
    values: st.SearchStrategy[str | StateField] = _STATE_TYPES | st.builds(
        StateField,
        type=_STATE_TYPES,
        reducer=st.none() | _REDUCERS,
        optional=st.none() | st.booleans(),
    )
    return st.dictionaries(_LABEL, values, max_size=envelope.max_state_keys)


# ── Node contracts (IR-SPEC §2.3, §3.1–§3.4, §3.6) ───────────────────────────────────────


@lru_cache(maxsize=_CACHE_SIZE)
def _json_values(max_leaves: int = 6) -> st.SearchStrategy[Any]:
    """The interior of ``args_schema`` — a JSON value, carried verbatim (IR-SPEC §3.1).

    1.0 imposes no schema algebra on the contents, so the only bound is canonicalizability:
    finite doubles and exact integers (§6.3).
    """
    leaves = st.none() | st.booleans() | _EXACT_INTEGERS | _EXACT_FLOATS | _LABEL
    return st.recursive(
        leaves,
        lambda children: (
            st.lists(children, max_size=3) | st.dictionaries(_LABEL, children, max_size=3)
        ),
        max_leaves=max_leaves,
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _key_subsets(
    keys: tuple[str, ...], envelope: SizeEnvelope
) -> st.SearchStrategy[tuple[str, ...]]:
    """A distinct subset of ``keys``, as a tuple — what ``input``/``output`` are (§2.3)."""
    return _distinct_subsets(keys, envelope.max_contract_keys).map(tuple)


def node_contracts(
    *,
    state_keys: Sequence[str] = (),
    hook_ids: Sequence[str] = (),
    envelope: SizeEnvelope = DEFAULT_ENVELOPE,
) -> st.SearchStrategy[Annotations]:
    """A node contract in which every cross-field obligation holds.

    Three of them, each cited where the frozen text states it:

    * ``input`` and ``output`` are subsets of ``keys(state)`` (§2.3) — hence ``state_keys``;
    * ``idempotent.key`` names a member of ``input`` (§2.3), so a keyed marker **extends**
      ``input`` to contain its key rather than waiting for ``input`` to have been drawn
      already. That direction is deliberate: making the object form conditional on a second,
      independent slot draw pushed it below one draw in a thousand, and P-06/P-07 metaproperties
      are going to want it.
    * ``variant.key`` names the state key that progresses under ``measure`` (§3.3), so it is
      drawn from ``state_keys``.

    ``compensation.hook`` is a node id under the §5 grammar (§3.4); passing ``hook_ids``
    keeps it a *declared* id, so the slot's content resolves. Per DEC-05 D7 the slot is
    declared content only, and nothing here treats it as discharging an obligation.

    **Which slots are populated is drawn first**, up to ``envelope.max_contract_slots``, and
    only then are values drawn for them. Filling every slot independently would be both
    unrepresentative — a corpus contract populates two to four slots, not fourteen — and about
    twice as expensive per example, which matters when the suites above this one run at a
    thousand examples each. Every slot stays individually reachable (asserted), and the empty
    slot set gives ``Annotations()``, which is the shrink target and itself a valid contract.
    """
    return _node_contracts(tuple(state_keys), tuple(hook_ids), envelope)


@lru_cache(maxsize=_CACHE_SIZE)
def _node_contracts(
    state_keys: tuple[str, ...], hook_ids: tuple[str, ...], envelope: SizeEnvelope
) -> st.SearchStrategy[Annotations]:
    return _draw_contract(state_keys, hook_ids, envelope)


@st.composite
def _draw_contract(
    draw: st.DrawFn,
    keys: tuple[str, ...],
    hook_ids: tuple[str, ...],
    envelope: SizeEnvelope,
) -> Annotations:
    """The slot-set-then-values construction of :func:`node_contracts`."""
    slots = draw(st.sets(st.sampled_from(CONTRACT_SLOTS), max_size=envelope.max_contract_slots))

    def value(slot: str, strategy: st.SearchStrategy[_T]) -> _T | None:
        """``strategy``'s value when ``slot`` was drawn, and absence otherwise."""
        return draw(strategy) if slot in slots else None

    # `input` is drawn before `idempotent`, because §2.3 scopes `idempotent.key` to it: the key
    # comes from `input` when there is one to draw from, and otherwise becomes `input`.
    inputs = value("input", _key_subsets(keys, envelope))
    markers: st.SearchStrategy[bool | IdempotentKey] = st.booleans()
    if keys and envelope.max_contract_keys >= 1:
        markers = markers | st.builds(IdempotentKey, key=_one_of(inputs or keys))
    idempotent = value("idempotent", markers)
    if isinstance(idempotent, IdempotentKey):
        inputs = tuple(dict.fromkeys((*(inputs or ()), idempotent.key)))

    return Annotations(
        pure=value("pure", st.booleans()),
        effect=value("effect", _effects(envelope)),
        idempotent=idempotent,
        deterministic=value("deterministic", _determinism()),
        input=inputs,
        output=value("output", _key_subsets(keys, envelope)),
        source=value("source", _LABEL),
        map=value("map", _LABEL),
        args_schema=value("args_schema", _args_schemas(envelope)),
        retry_policy=value("retry_policy", _retry_policies(envelope)),
        variant=None if not keys else value("variant", _variants(keys)),
        compensation=None if not hook_ids else value("compensation", _compensations(hook_ids)),
        prompt_digest=value("prompt_digest", _digests()),
        config_digest=value("config_digest", _digests()),
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _effects(envelope: SizeEnvelope) -> st.SearchStrategy[tuple[str, ...]]:
    return _distinct_subsets(EFFECT_TAGS, envelope.max_effect_tags).map(tuple)


@lru_cache(maxsize=1)
def _determinism() -> st.SearchStrategy[bool | DeterministicSpec]:
    return st.booleans() | st.builds(
        DeterministicSpec, seed=_EXACT_INTEGERS, temperature=st.none() | _EXACT_FLOATS
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _args_schemas(envelope: SizeEnvelope) -> st.SearchStrategy[dict[str, Any]]:
    return st.dictionaries(_LABEL, _json_values(), max_size=envelope.max_args_schema_keys)


@lru_cache(maxsize=_CACHE_SIZE)
def _retry_policies(envelope: SizeEnvelope) -> st.SearchStrategy[RetryPolicy]:
    return st.builds(
        RetryPolicy,
        max_attempts=_counts(1, 5),
        retry_on=st.lists(_EXCEPTION_NAMES, max_size=envelope.max_retry_on, unique=True).map(tuple),
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _variants(keys: tuple[str, ...]) -> st.SearchStrategy[Variant]:
    return st.builds(Variant, key=_one_of(keys), measure=_MEASURES)


@lru_cache(maxsize=_CACHE_SIZE)
def _compensations(hook_ids: tuple[str, ...]) -> st.SearchStrategy[Compensation]:
    return st.builds(Compensation, hook=_one_of(hook_ids))


def nodes(
    *,
    ids: st.SearchStrategy[str] | None = None,
    state_keys: Sequence[str] = (),
    hook_ids: Sequence[str] = (),
    envelope: SizeEnvelope = DEFAULT_ENVELOPE,
) -> st.SearchStrategy[Node]:
    """One ``nodes[]`` entry: an id, and a contract or none (IR-SPEC §2.3).

    Args:
        ids: Where the id comes from; :func:`node_ids` by default. A caller building a
            workflow passes ``st.just(<id>)`` so the id set stays under its own control.
        state_keys: The state keys ``input``/``output``/``variant.key`` may name.
        hook_ids: The node ids ``compensation.hook`` may name.
        envelope: The size bounds.
    """
    return _nodes(
        ids if ids is not None else _node_ids(envelope),
        tuple(state_keys),
        tuple(hook_ids),
        envelope,
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _nodes(
    ids: st.SearchStrategy[str],
    state_keys: tuple[str, ...],
    hook_ids: tuple[str, ...],
    envelope: SizeEnvelope,
) -> st.SearchStrategy[Node]:
    return st.builds(
        Node,
        id=ids,
        annotations=st.none() | _node_contracts(state_keys, hook_ids, envelope),
    )


# ── Runtime (IR-SPEC §3.5, §3.7) ─────────────────────────────────────────────────────────


def runtimes(
    *,
    interrupt_ids: Sequence[str] = (),
    envelope: SizeEnvelope = DEFAULT_ENVELOPE,
) -> st.SearchStrategy[Runtime]:
    """The graph-level ``runtime`` block — all three sub-slots optional (IR-SPEC §2.1, §3).

    Which of the three :data:`RUNTIME_SLOTS` are populated is drawn first, up to
    ``envelope.max_runtime_slots``, the same way :func:`node_contracts` draws its slot set.

    ``recursion_limit.value`` is drawn positive: §3.5 makes the slot the P-02 witness form
    (b) carrier and pairs it with a REQUIRED ``justification``, so a non-positive limit would
    be a declared bound no execution could respect. ``interrupts`` members are drawn from
    ``interrupt_ids`` so that a gate names a declared node.
    """
    return _runtimes(tuple(interrupt_ids), envelope)


@lru_cache(maxsize=_CACHE_SIZE)
def _runtimes(interrupt_ids: tuple[str, ...], envelope: SizeEnvelope) -> st.SearchStrategy[Runtime]:
    return _draw_runtime(interrupt_ids, envelope)


@st.composite
def _draw_runtime(
    draw: st.DrawFn, interrupt_ids: tuple[str, ...], envelope: SizeEnvelope
) -> Runtime:
    """The slot-set-then-values construction of :func:`runtimes`."""
    slots = draw(st.sets(st.sampled_from(RUNTIME_SLOTS), max_size=envelope.max_runtime_slots))
    gates = _distinct_subsets(interrupt_ids, envelope.max_interrupts).map(tuple)
    return Runtime(
        recursion_limit=(
            draw(st.builds(RecursionLimit, value=_counts(1, 1000), justification=_LABEL))
            if "recursion_limit" in slots
            else None
        ),
        interrupts=(
            draw(st.builds(Interrupts, before=st.none() | gates, after=st.none() | gates))
            if "interrupts" in slots
            else None
        ),
        checkpointer=(
            Checkpointer(present=draw(st.booleans())) if "checkpointer" in slots else None
        ),
    )


# ── The whole workflow ───────────────────────────────────────────────────────────────────


def workflow_irs(
    *,
    envelope: SizeEnvelope = DEFAULT_ENVELOPE,
    topology: st.SearchStrategy[Topology] | None = None,
    state: st.SearchStrategy[dict[str, str | StateField] | None] | None = None,
) -> st.SearchStrategy[WorkflowIR]:
    """A well-formed ``ir_version`` 1.0 workflow — the headline strategy of this module.

    The six-item well-formedness list in the module docstring is what every draw satisfies,
    and ``tests/testing/test_strategies.py`` holds this function to each item at scale rather
    than by inspection.

    Args:
        envelope: The size bounds (:class:`SizeEnvelope`).
        topology: A topology strategy to build around, when a caller has one —
          :func:`topologies` by default. This is the mutation seam: a suite can hand in a
          rewritten topology and get the rest of the document generated around it.
        state: The schema Σ to build around; by default ``st.none() | state_schemas(…)``,
          which draws absence, the empty schema and populated ones alike. A suite that needs
          Σ *populated* — most P-04 and P-09 work — passes one here rather than filtering
          whole workflows, e.g. ``state=state_schemas().filter(bool)``. The envelope carries
          only maxima, on purpose (that is what makes shrinking converge on one floor), so
          this parameter is where a minimum belongs.

    Returns:
        A strategy for :class:`~gebra.ir.WorkflowIR`.
    """
    return _workflow_irs(
        envelope,
        topology if topology is not None else topologies(envelope=envelope),
        state if state is not None else _optional_state(envelope),
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _optional_state(
    envelope: SizeEnvelope,
) -> st.SearchStrategy[dict[str, str | StateField] | None]:
    return st.none() | _state_schemas(envelope)


@lru_cache(maxsize=_CACHE_SIZE)
def _workflow_irs(
    envelope: SizeEnvelope,
    topology: st.SearchStrategy[Topology],
    state: st.SearchStrategy[dict[str, str | StateField] | None],
) -> st.SearchStrategy[WorkflowIR]:
    return _draw_workflow(envelope, topology, state)


@st.composite
def _draw_workflow(
    draw: st.DrawFn,
    envelope: SizeEnvelope,
    topology: st.SearchStrategy[Topology],
    states: st.SearchStrategy[dict[str, str | StateField] | None],
) -> WorkflowIR:
    """The topology, then Σ, then one contract per node, then ``runtime``."""
    graph = draw(topology)
    state = draw(states)
    keys = () if state is None else tuple(state)
    contracts = st.none() | _node_contracts(keys, graph.node_ids, envelope)
    node_models = tuple(Node(id=node_id, annotations=draw(contracts)) for node_id in graph.node_ids)
    runtime = draw(st.none() | _runtimes(graph.node_ids, envelope))
    return WorkflowIR(
        ir_version="1.0",
        entry=graph.entry,
        finish=graph.finish,
        state=state,
        nodes=node_models,
        edges=graph.edges,
        runtime=runtime,
    )
