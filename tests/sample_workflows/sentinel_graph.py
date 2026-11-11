"""Sentinel workflow for the never-invokes tripwire tests (decisions D-018/D-023).

Every node function and router in this module raises ``SentinelExecutedError``
if it is ever called. ``gebra.extract()`` must be able to introspect the graph
built here without tripping a single sentinel — extraction imports and
inspects, full stop.

Import safety: importing this module BUILDS the ``StateGraph`` (registering
node callables never calls them) but never compiles or invokes it, contacts no
external service, and requires no API keys. ``compile()`` is guarded behind
``compile_sentinel_graph()``.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, Send

if TYPE_CHECKING:  # imported for typing only — never at runtime
    from collections.abc import Callable, Hashable, Iterator

    from langgraph.graph.state import CompiledStateGraph


#: Every sentinel in this family that fired, newest last. Recorded by the exception below
#: rather than by each raise site, so the ledger covers every sentinel in this module *and*
#: in every module that reuses :class:`SentinelExecutedError` — ``sentinel_routing``,
#: ``sentinel_state``, ``sentinel_lcel``, ``sentinel_compiled``, ``sentinel_routing_futures``.
TRIPPED: list[str] = []


class SentinelExecutedError(RuntimeError):
    """Raised by any sentinel node or router that gets invoked.

    Extraction must never cause this: a raise here means user code ran.

    Constructing one appends its message to :data:`TRIPPED` **before** it is raised, so a
    sentinel that a ``try`` block swallowed still shows up — the record-before-raise
    discipline ``travel_booking`` and ``sentinel_lcel`` keep at each raise site, kept here
    once instead. A caller that only wants to *check* the ledger is unaffected: nothing but
    constructing this exception writes to it.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        TRIPPED.append(str(args[0]) if args else type(self).__name__)


class SentinelState(TypedDict):
    query: str
    plan: str
    answer: str


def plan_step(state: SentinelState) -> dict[str, str]:
    raise SentinelExecutedError("node 'plan_step' was invoked — extraction must never call nodes")


def act_step(state: SentinelState) -> dict[str, str]:
    raise SentinelExecutedError("node 'act_step' was invoked — extraction must never call nodes")


def summarize_step(state: SentinelState) -> dict[str, str]:
    raise SentinelExecutedError(
        "node 'summarize_step' was invoked — extraction must never call nodes"
    )


def route_after_plan(state: SentinelState) -> str:
    raise SentinelExecutedError(
        "router 'route_after_plan' was invoked — extraction must never call routers"
    )


def build_sentinel_graph() -> StateGraph[SentinelState]:
    """Build (but never compile or invoke) the sentinel StateGraph."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step)
    builder.add_node("summarize_step", summarize_step)
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step",
        route_after_plan,
        {"act": "act_step", "done": "summarize_step"},
    )
    builder.add_edge("act_step", "summarize_step")
    builder.add_edge("summarize_step", END)
    return builder


# ── §3 shape fixtures for the builder extraction path ────────────────────────────────────
#
# One builder per INTROSPECTION-SPEC §3 shape the extraction path has to read. Every node
# function and router below is `raiser(...)` or one of the module-level sentinels, so the
# whole set is armed: extracting any of them must trip nothing. They are factories rather
# than module-level constants so that importing this module stays "build one graph", and so
# that the shapes that *refuse* can be built without the import raising.


def raiser(label: str) -> Callable[..., Any]:
    """A node/router that raises if it is ever called — the tripwire, per shape.

    Typed ``Callable[..., Any]`` on both ends, and both halves of that are deliberate. The
    parameters are open because the substrate calls a node with a state, a router with a
    state, and either with a config or a runtime depending on its signature — and this
    function stands in for all of those. The return is open because a node returns a state
    update while a router returns a label, and a signature that named one would make the
    other a type error at the ``add_node``/``add_conditional_edges`` call site. Neither
    weakens anything real: the body's only statement is ``raise``.
    """

    def _sentinel(*args: Any, **kwargs: Any) -> Any:
        raise SentinelExecutedError(f"{label!r} was invoked — extraction must never call it")

    _sentinel.__name__ = label
    _sentinel.__qualname__ = label
    return _sentinel


def build_router_terminated_graph() -> StateGraph[SentinelState]:
    """Terminates only through router `path_map` labels — the D2 `finish: []` shape.

    Idiomatic and well-formed: END is reached, but through (m3) labels rather than any
    `(x, END)` edge, so `finish` is empty and nothing about the graph is undeclared.
    """
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step", raiser("route_plan"), {"act": "act_step", "done": END}
    )
    builder.add_conditional_edges(
        "act_step", raiser("route_act"), {"again": "plan_step", "stop": END}
    )
    return builder


def build_unwired_graph() -> StateGraph[SentinelState]:
    """A node and nothing else — the §2 degenerate-input shape, warned on both sentinels."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    return builder


def build_conditional_entry_graph(*, declared: bool) -> StateGraph[SentinelState]:
    """`set_conditional_entry_point`, with declared targets or without.

    With a `path_map` the targets *are* the entry; without one, `BranchSpec.ends is None`
    and §3 emits `entry: []` plus the dynamic-entry warning.
    """
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    router = raiser("route_entry")
    if declared:
        builder.set_conditional_entry_point(router, path_map={"a": "plan_step", "b": "act_step"})
    else:
        builder.set_conditional_entry_point(router)
    builder.add_edge("plan_step", END)
    builder.add_edge("act_step", END)
    return builder


def build_barrier_graph() -> StateGraph[SentinelState]:
    """Two `waiting_edges` groups — the all-of barrier §3 flattens, one warning each."""
    builder = StateGraph(SentinelState)
    for name in ("plan_step", "act_step", "summarize_step", "review_step"):
        builder.add_node(name, raiser(name))
    builder.add_edge(START, "plan_step")
    builder.add_edge(START, "act_step")
    builder.add_edge(["plan_step", "act_step"], "summarize_step")
    builder.add_edge(["plan_step", "act_step"], "review_step")
    builder.add_edge("summarize_step", END)
    builder.add_edge("review_step", END)
    return builder


def build_retry_graph() -> StateGraph[SentinelState]:
    """The three `retry_policy` shapes §3 projects: declared types, callable, sequence."""
    builder = StateGraph(SentinelState)
    builder.add_node(
        "declared_step",
        raiser("declared_step"),
        retry_policy=RetryPolicy(max_attempts=4, retry_on=(ValueError, KeyError)),
    )
    builder.add_node(
        "defaulted_step",
        raiser("defaulted_step"),
        retry_policy=RetryPolicy(max_attempts=3),
    )
    builder.add_node(
        "sequenced_step",
        raiser("sequenced_step"),
        retry_policy=[
            RetryPolicy(max_attempts=2, retry_on=TimeoutError),
            RetryPolicy(max_attempts=7, retry_on=OSError),
        ],
    )
    builder.add_node("plain_step", raiser("plain_step"))
    builder.add_edge(START, "declared_step")
    builder.add_edge("declared_step", "defaulted_step")
    builder.add_edge("defaulted_step", "sequenced_step")
    builder.add_edge("sequenced_step", "plain_step")
    builder.add_edge("plain_step", END)
    return builder


def build_escaped_names_graph() -> StateGraph[SentinelState]:
    """Node names carrying the two characters the ledger §5 grammar escapes."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan/step", raiser("plan_slash_step"))
    builder.add_node("act%step", raiser("act_percent_step"))
    builder.add_edge(START, "plan/step")
    builder.add_edge("plan/step", "act%step")
    builder.add_edge("act%step", END)
    return builder


def build_start_to_end_graph() -> StateGraph[SentinelState]:
    """A direct START→END edge — a sentinel incidence ir 1.0 has no carrier for."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)
    builder.add_edge(START, END)
    return builder


def build_targetless_router_graph() -> StateGraph[SentinelState]:
    """A router declaring no targets — §6's targetless form, `kind: dynamic` (DEC-28)."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", raiser("route_dynamically"))
    builder.add_edge("act_step", END)
    return builder


def build_destinations_graph() -> StateGraph[SentinelState]:
    """`StateNodeSpec.ends`, in both shapes the substrate produces.

    `destinations=` supplies it directly — as a tuple from a sequence argument, as a dict
    from a mapping one — and a `Command[Literal[...]]` **return annotation** supplies it with
    no argument at the call site at all, which is why this member cannot be refused without
    refusing the whole `Command`-routing idiom.
    """

    def commander(state: SentinelState) -> Command[Literal["act_step"]]:
        raise SentinelExecutedError("'commander' was invoked — extraction must never call it")

    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"), destinations=("act_step", "review_step"))
    builder.add_node("act_step", raiser("act_step"), destinations={"review_step": "go review"})
    builder.add_node("command_step", commander)
    builder.add_node("review_step", raiser("review_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge("review_step", "command_step")
    builder.add_edge("command_step", END)
    return builder


def build_unnamed_node_graph() -> StateGraph[SentinelState]:
    """A node named ``""`` — accepted by the substrate, and not a node id under any grammar."""
    builder = StateGraph(SentinelState)
    builder.add_node("", raiser("empty_name_step"))
    builder.add_edge(START, "")
    builder.add_edge("", END)
    return builder


def build_send_hinted_router_graph() -> StateGraph[SentinelState]:
    """A router hinted `-> list[Send]` — §6 would classify it `send`; §3 alone cannot.

    The pin for the refinement boundary the builder path documents: the declared targets are
    read, the kind is the conservative one, and the card that reads return-type hints is the
    one that changes it.
    """

    def route_legs(state: SentinelState) -> list[Send]:
        raise SentinelExecutedError("'route_legs' was invoked — extraction must never call it")

    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("book_leg", raiser("book_leg"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", route_legs, ["book_leg"])
    builder.add_edge("book_leg", END)
    return builder


class SentinelLabel:
    """A routing label that is not a string and screams if anything tries to make it one.

    ``StateGraph.add_conditional_edges`` types its ``path_map`` keys ``Hashable``, so this is
    an in-contract call. Every dunder that would let extraction *coerce* the label raises, so
    a path that reached for ``str(label)`` — arbitrary user code, and a value that would land
    inside ``graph_version`` — fails the tripwire instead of passing silently.
    """

    def __init__(self, key: str) -> None:
        self.key = key

    def __hash__(self) -> int:
        return hash(self.key)  # the substrate hashes it as a dict key; that much is expected

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SentinelLabel) and other.key == self.key

    def __str__(self) -> str:
        raise SentinelExecutedError("__str__ ran on a routing label — extraction must not coerce")

    def __repr__(self) -> str:
        raise SentinelExecutedError("__repr__ ran on a routing label — extraction must not coerce")


class SentinelTrigger:
    """A ``retry_on`` member that is not an exception type and raises if coerced.

    ``RetryPolicy`` is a ``NamedTuple`` with no runtime validation, so an out-of-contract
    member constructs fine. Projecting it by ``str()`` would run this class's code *and* put
    an ``object.__repr__`` memory address into the content hash, so a builder carrying one
    would digest differently in every process.
    """

    def __str__(self) -> str:
        raise SentinelExecutedError("__str__ ran on a retry trigger — extraction must not coerce")

    def __repr__(self) -> str:
        raise SentinelExecutedError("__repr__ ran on a retry trigger — extraction must not coerce")


def build_nonstring_label_graph() -> StateGraph[SentinelState]:
    """A router whose `path_map` keys are not strings — refused per DEC-32 (ruled)."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step", raiser("route_plan"), {SentinelLabel("go"): "act_step"}
    )
    builder.add_edge("act_step", END)
    return builder


def build_nfc_collision_label_graph() -> StateGraph[SentinelState]:
    """Two distinct authored labels sharing one NFC normal form — a DEC-32 collision.

    ``café`` spelled composed (U+00E9) and decomposed (``e`` + U+0301): two different
    Python strings the substrate holds side by side, one ``path_map`` key after the
    IR's NFC normalization.
    """
    composed = "caf\u00e9"
    decomposed = "cafe\u0301"
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_node("check_step", raiser("check_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step",
        raiser("route_plan"),
        {composed: "act_step", decomposed: "check_step", "other": END},
    )
    builder.add_edge("act_step", END)
    builder.add_edge("check_step", END)
    return builder


def build_str_mixin_enum_label_graph() -> StateGraph[SentinelState]:
    """A string-mixin enum label — IS a ``str``, carries its verbatim value (DEC-32).

    The member's ``str()`` render and its ``.name`` both differ from its value; the IR
    must carry the value, reading neither.
    """

    class Colour(str, enum.Enum):
        RED = "crimson"

        def __str__(self) -> str:  # the render a coercion would leak
            raise AssertionError("str() was called on a routing label")

    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", raiser("route_plan"), {Colour.RED: "act_step"})
    builder.add_edge("act_step", END)
    return builder


def build_reserved_routing_target_graph() -> StateGraph[SentinelState]:
    """A `path_map` label targeting START — accepted by the substrate, uncarriable in ir 1.0."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step", raiser("route_plan"), {"restart": START, "go": "act_step"}
    )
    builder.add_edge("act_step", END)
    return builder


def build_non_nfc_label_graph() -> StateGraph[SentinelState]:
    """A routing label authored in NFD — canonicalization refuses anything but NFC."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    # "cafe" + U+0301 COMBINING ACUTE — equal to "café" only after NFC.
    builder.add_conditional_edges("plan_step", raiser("route_plan"), {"café": "act_step"})
    builder.add_edge("act_step", END)
    return builder


def build_foreign_trigger_graph() -> StateGraph[SentinelState]:
    """A `retry_on` list mixing a real exception type with a value that is not one."""
    builder = StateGraph(SentinelState)
    builder.add_node(
        "plan_step",
        raiser("plan_step"),
        retry_policy=RetryPolicy(max_attempts=5, retry_on=[ValueError, SentinelTrigger()]),  # type: ignore[list-item]
    )
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)
    return builder


# ── §6 enum routing labels and non-string routing targets (DEC-38; EX-27) ────────────────
#
# INTROSPECTION-SPEC §6, as DEC-38 amended it, admits one non-string routing label: a plain
# `Enum` member whose stored value is an exact `str`, spelled as that value and read from the
# member's own instance dictionary through unbound accessors. Every other non-string label, and
# every non-string routing *target*, is refused at the boundary. The fixtures below are armed in
# two ways. What a coercion would reach raises `SentinelExecutedError`, which records itself in
# `TRIPPED` before it is raised. What the ruled read must never touch records itself in
# `LABEL_READS` — a member's `__getattribute__`, a routing mapping's own methods, a planted
# member dictionary's own methods — so a test asserts that ledger empty after `extract()`
# rather than trusting that no raise was swallowed. Both are written at *build* time too (the
# substrate copies a `path_map`; putting a member in a dict hashes it, which reads `_name_`), so a
# test clears `LABEL_READS` after building and before extracting.

#: Every read the label and target path must never make, newest last: ``"<recorder>.<what>"``.
LABEL_READS: list[str] = []

#: The reads `typing.get_type_hints()` makes on a `StringlyDecision` member while evaluating a
#: string annotation — INTROSPECTION-SPEC §1 rule 3's licensed evaluation, kept apart from
#: `LABEL_READS` so that ledger can be asserted empty across every fixture in this module.
EVALUATED_READS: list[str] = []


class AgentDecision(enum.Enum):
    """The field case's routing label — ``TOOL = "tool"``, ``END = "finished"`` — armed.

    The field case DEC-38 rules on: a plain ``Enum`` keying ``path_map`` whose names and values
    differ (``END`` / ``"finished"``). Everything a coercion could reach raises: the three
    rendering dunders, and class-body ``name``/``value`` properties shadowing the enum
    machinery's own getters (a descriptor is not a member, so the machinery accepts them).
    Extraction spells each member by its stored value without reaching any of them.
    """

    TOOL = "tool"
    END = "finished"

    def __str__(self) -> str:
        raise SentinelExecutedError("__str__ ran on an enum routing label — never coerce one")

    def __repr__(self) -> str:
        raise SentinelExecutedError("__repr__ ran on an enum routing label — never coerce one")

    def __format__(self, format_spec: str) -> str:
        raise SentinelExecutedError("__format__ ran on an enum routing label — never coerce one")

    @property
    def name(self) -> str:  # the class-body getter shadowing the machinery's is the fixture
        raise SentinelExecutedError("the class-body `name` ran on an enum routing label")

    @property
    def value(self) -> str:  # the class-body getter shadowing the machinery's is the fixture
        raise SentinelExecutedError("the class-body `value` ran on an enum routing label")


class AgentDecisionStr(str, enum.Enum):
    """``AgentDecision``'s string-mixin twin with equal values — a ``str``, read as one (DEC-32)."""

    TOOL = "tool"
    END = "finished"

    def __str__(self) -> str:
        raise SentinelExecutedError("__str__ ran on a string-mixin routing label")

    def __repr__(self) -> str:
        raise SentinelExecutedError("__repr__ ran on a string-mixin routing label")

    def __format__(self, format_spec: str) -> str:
        raise SentinelExecutedError("__format__ ran on a string-mixin routing label")


class RecordingDecision(enum.Enum):
    """A plain ``Enum`` label recording every attribute read made on one of its members.

    The DEC-38 regression fixture: ``isinstance(member, str)`` — the gate the label path used
    before EX-27 — reads ``__class__`` through this hook, and so do ``typing.get_origin`` and
    ``get_args`` applied to the member; the ruled read reaches it not once.
    """

    TOOL = "tool"
    END = "finished"
    WAIT = "waiting"

    def __getattribute__(self, name: str) -> Any:
        LABEL_READS.append(f"RecordingDecision.__getattribute__:{name}")
        return object.__getattribute__(self, name)


class StringlyDecision(enum.Enum):
    """``RecordingDecision``'s twin for the string-annotation route, recording to its own ledger."""

    TOOL = "tool"
    END = "finished"
    WAIT = "waiting"

    def __getattribute__(self, name: str) -> Any:
        EVALUATED_READS.append(name)
        return object.__getattribute__(self, name)


class RecordingMemberDict(dict[str, object]):
    """A ``dict`` subclass planted as an enum member's ``__dict__``, recording its own methods.

    DEC-38 §3.2, §5 row 8c: a mixin ``__new__`` can assign one before storing an exact-``str``
    ``_value_`` in it, and the machinery's own C-level writes land in it unnoticed — so a bound
    ``d.items()`` or ``list(d)`` would run this code at extraction while the member is admitted.
    The ruled read iterates ``dict.items(d)`` and reaches none of it.
    """

    def items(self) -> Any:
        LABEL_READS.append("RecordingMemberDict.items")
        return dict.items(self)

    def keys(self) -> Any:
        LABEL_READS.append("RecordingMemberDict.keys")
        return dict.keys(self)

    def values(self) -> Any:
        LABEL_READS.append("RecordingMemberDict.values")
        return dict.values(self)

    def get(self, key: str, default: object = None) -> object:
        LABEL_READS.append("RecordingMemberDict.get")
        return dict.get(self, key, default)

    def __iter__(self) -> Iterator[str]:
        LABEL_READS.append("RecordingMemberDict.__iter__")
        return dict.__iter__(self)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingMemberDict.__len__")
        return dict.__len__(self)

    def __contains__(self, key: object) -> bool:
        LABEL_READS.append("RecordingMemberDict.__contains__")
        return dict.__contains__(self, key)

    def __getitem__(self, key: str) -> object:
        LABEL_READS.append("RecordingMemberDict.__getitem__")
        return dict.__getitem__(self, key)


class _PlantedDictMember:
    """A mixin whose ``__new__`` plants a :class:`RecordingMemberDict` as each member's dict."""

    def __new__(cls, value: str) -> Any:
        member = object.__new__(cls)
        object.__setattr__(member, "__dict__", RecordingMemberDict())
        object.__setattr__(member, "_value_", value)
        return member


class PlantedDecision(_PlantedDictMember, enum.Enum):
    """Members whose instance dictionary is a recording ``dict`` subclass — admitted, read unbound."""

    TOOL = "tool"
    END = "finished"


class RecordingEnds(dict[Any, Any]):
    """A ``dict`` subclass declared as routing targets, recording every method of its own that runs.

    Passed as a ``path_map`` it reaches ``BranchSpec.ends`` through the substrate's own
    ``path_map.copy()``, which is this class's ``copy`` — so the router's mapping *is* one of
    these; passed as ``destinations=`` it is stored as handed. The extractor reads both through
    ``issubclass(type(ends), dict)`` and ``dict.items(ends)`` and must leave this ledger empty.
    """

    def copy(self) -> RecordingEnds:
        LABEL_READS.append("RecordingEnds.copy")
        return RecordingEnds(dict.items(self))

    def items(self) -> Any:
        LABEL_READS.append("RecordingEnds.items")
        return dict.items(self)

    def keys(self) -> Any:
        LABEL_READS.append("RecordingEnds.keys")
        return dict.keys(self)

    def values(self) -> Any:
        LABEL_READS.append("RecordingEnds.values")
        return dict.values(self)

    def get(self, key: Hashable, default: object = None) -> object:
        LABEL_READS.append("RecordingEnds.get")
        return dict.get(self, key, default)

    def __iter__(self) -> Iterator[Hashable]:
        LABEL_READS.append("RecordingEnds.__iter__")
        return dict.__iter__(self)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingEnds.__len__")
        return dict.__len__(self)

    def __bool__(self) -> bool:
        LABEL_READS.append("RecordingEnds.__bool__")
        return dict.__len__(self) > 0

    def __contains__(self, key: object) -> bool:
        LABEL_READS.append("RecordingEnds.__contains__")
        return dict.__contains__(self, key)

    def __getitem__(self, key: Hashable) -> object:
        LABEL_READS.append("RecordingEnds.__getitem__")
        return dict.__getitem__(self, key)


def build_enum_label_graph(
    tool: Hashable = AgentDecision.TOOL, end: Hashable = AgentDecision.END
) -> StateGraph[SentinelState]:
    """A reason-act router — ``path_map`` keyed by ``AgentDecision`` members (DEC-38).

    ``gebra 0.1.1`` refused this shape; it extracts now with the labels spelled as the stored
    values, ``"tool"`` and ``"finished"``. ``tests/extraction/test_builder.py`` passes the
    string-mixin twin and plain strings through the same factory to show that the three
    extract byte-identical.
    """
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", raiser("conditional_edge"), {tool: "tool", end: END})
    builder.add_edge("tool", "agent")
    return builder


def build_recorded_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by ``RecordingDecision`` members on an unhinted router — zero reads."""
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        raiser("route_agent"),
        {
            RecordingDecision.TOOL: "tool",
            RecordingDecision.END: END,
            RecordingDecision.WAIT: "agent",
        },
    )
    builder.add_edge("tool", "agent")
    return builder


def build_literal_hinted_enum_label_graph(*, stringly: bool = False) -> StateGraph[SentinelState]:
    """An enum-keyed ``path_map`` beside a wider ``Literal`` return hint — the codomain read.

    The hint declares three members and the ``path_map`` two, so §6's codomain-capture rule
    records the hint in provenance — spelled by the same dispatch as the keys (DEC-38 §3.6).
    The annotations are set explicitly so that both forms are what they say on every
    interpreter this module runs under (it is written ``from __future__ import annotations``):
    with ``stringly=False`` the return hint is an evaluated ``Literal`` object, which nothing
    evaluates at extraction; with ``stringly=True`` it is the string ``typing.get_type_hints()``
    must evaluate, over ``StringlyDecision`` members, whose evaluation reads are the standard
    library's (§1 rule 3) and go to ``EVALUATED_READS``.
    """

    def route_decision(state: SentinelState) -> Any:
        raise SentinelExecutedError("'route_decision' was invoked — extraction must never call it")

    decisions: type[RecordingDecision | StringlyDecision]
    if stringly:
        decisions = StringlyDecision
        route_decision.__annotations__ = {
            "state": "SentinelState",
            "return": "Literal[StringlyDecision.TOOL, StringlyDecision.END, StringlyDecision.WAIT]",
        }
    else:
        decisions = RecordingDecision
        route_decision.__annotations__ = {
            "state": SentinelState,
            "return": Literal[
                RecordingDecision.TOOL, RecordingDecision.END, RecordingDecision.WAIT
            ],
        }
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route_decision, {decisions.TOOL: "tool", decisions.END: END}
    )
    builder.add_edge("tool", "agent")
    return builder


def build_planted_dict_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by members whose ``__dict__`` is a recording ``dict`` subclass."""
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", raiser("route_agent"), {PlantedDecision.TOOL: "tool", PlantedDecision.END: END}
    )
    builder.add_edge("tool", "agent")
    return builder


def build_recording_ends_graph() -> StateGraph[SentinelState]:
    """The three target-reading sites, each declared through a :class:`RecordingEnds` mapping.

    The conditional entry keys its one target with an enum member; the router mixes an enum
    label with a string one; and the node declaration is a ``destinations=`` dict in the
    orientation the substrate documents — keys are targets, values are labels — with one label
    an enum member (PD-067 §5's route (ii), a *label* once the orientation is read right).
    """
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node(
        "tool",
        raiser("tool"),
        destinations=RecordingEnds(
            {"review": RecordingDecision.WAIT, "agent": "back to the agent"}
        ),
    )
    builder.add_node("review", raiser("review"))
    builder.set_conditional_entry_point(
        raiser("route_entry"), RecordingEnds({RecordingDecision.TOOL: "agent"})
    )
    builder.add_conditional_edges(
        "agent", raiser("route_agent"), RecordingEnds({RecordingDecision.TOOL: "tool", "done": END})
    )
    builder.add_edge("review", END)
    return builder


class IntDecision(enum.IntEnum):
    """An ``IntEnum`` label — its stored value is an ``int``, so it has no spelling (DEC-38 §3.4).

    Armed like ``RecordingDecision``: every attribute read on a member records, so the refusal
    is shown to read nothing of it.
    """

    TOOL = 1
    END = 2

    def __getattribute__(self, name: str) -> Any:
        LABEL_READS.append(f"IntDecision.__getattribute__:{name}")
        return object.__getattribute__(self, name)


class IntValuedDecision(enum.Enum):
    """A plain ``Enum`` whose stored values are ``int`` — refused: the value is not a ``str``."""

    TOOL = 1
    END = 2

    def __getattribute__(self, name: str) -> Any:
        LABEL_READS.append(f"IntValuedDecision.__getattribute__:{name}")
        return object.__getattribute__(self, name)


class _LabelString(str):
    """A ``str`` subclass stored as an enum value — refused by the exact-type test (DEC-38 §3.4).

    Every hook a rendering, a hash or a comparison of the stored value would reach records (the
    enum machinery hashes the value at class creation, which is why these record rather than
    raise).
    """

    __slots__ = ()

    def __hash__(self) -> int:
        LABEL_READS.append("_LabelString.__hash__")
        return str.__hash__(self)

    def __eq__(self, other: object) -> bool:
        LABEL_READS.append("_LabelString.__eq__")
        return str.__eq__(self, other)

    def __str__(self) -> str:
        LABEL_READS.append("_LabelString.__str__")
        return str.__str__(self)

    def __repr__(self) -> str:
        LABEL_READS.append("_LabelString.__repr__")
        return str.__repr__(self)

    def __format__(self, format_spec: str) -> str:
        LABEL_READS.append("_LabelString.__format__")
        return str.__format__(self, format_spec)


class SubclassValuedDecision(enum.Enum):
    """A plain ``Enum`` whose stored values are a ``str`` subclass — refused, never joined."""

    TOOL = _LabelString("tool")
    END = _LabelString("finished")


class _ArmedValue:
    """A stored enum value that is no string at all; its renderings, hash and comparison record."""

    def __hash__(self) -> int:
        LABEL_READS.append("_ArmedValue.__hash__")
        return object.__hash__(self)

    def __eq__(self, other: object) -> bool:
        LABEL_READS.append("_ArmedValue.__eq__")
        return self is other

    def __str__(self) -> str:
        LABEL_READS.append("_ArmedValue.__str__")
        return "armed"

    def __repr__(self) -> str:
        LABEL_READS.append("_ArmedValue.__repr__")
        return "armed"

    def __format__(self, format_spec: str) -> str:
        LABEL_READS.append("_ArmedValue.__format__")
        return "armed"


class ObjectValuedDecision(enum.Enum):
    """A plain ``Enum`` whose stored value is an arbitrary object — refused, nothing of it read."""

    TOOL = _ArmedValue()


class _ShadowedValue:
    """A mixin base defining ``_value_`` itself, which leaves the member's own dictionary without
    one: ``.value`` then answers this definition, and the label refuses (MRO-shadowed)."""

    @property
    def _value_(self) -> str:
        LABEL_READS.append("_ShadowedValue._value_")
        return "shadow"


class ShadowedDecision(_ShadowedValue, enum.Enum):  # type: ignore[override]  # the fixture
    """A member whose ``_value_`` is a mixin's property — the shape DEC-38 §3.2 rule (iii) refuses.

    One member only: the property answers every member alike, so a second would be an alias.
    """

    TOOL = "tool"


def _decision_router_graph(path_map: dict[Hashable, Any]) -> StateGraph[SentinelState]:
    """The two-node agent loop with the given ``path_map`` on its router."""
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", raiser("route_agent"), path_map)
    builder.add_edge("tool", "agent")
    return builder


def build_int_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by ``IntEnum`` members — refused (``construct-not-carried``)."""
    return _decision_router_graph({IntDecision.TOOL: "tool", IntDecision.END: END})


def build_int_valued_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by an ``int``-valued plain ``Enum`` — refused."""
    return _decision_router_graph({IntValuedDecision.TOOL: "tool", IntValuedDecision.END: END})


def build_subclass_valued_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by an enum storing a ``str`` subclass — refused (exact ``str`` only)."""
    return _decision_router_graph(
        {SubclassValuedDecision.TOOL: "tool", SubclassValuedDecision.END: END}
    )


def build_shadowed_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by members with an MRO-shadowed ``_value_`` — refused."""
    return _decision_router_graph({ShadowedDecision.TOOL: "tool", "done": END})


def build_object_valued_enum_label_graph() -> StateGraph[SentinelState]:
    """``path_map`` keyed by an enum whose stored value is an arbitrary object — refused."""
    return _decision_router_graph({ObjectValuedDecision.TOOL: "tool", "done": END})


def build_enum_string_collision_graph() -> StateGraph[SentinelState]:
    """An admitted member's stored value meeting a string label — a collision after projection.

    The substrate keeps ``{AgentDecision.TOOL: …, "tool": …}`` as two keys (an enum member
    hashes by its name and equals only itself), so extraction sees both and refuses the merge
    (DEC-32 ruling 2, its reach restated at DEC-38).
    """
    return _decision_router_graph({AgentDecision.TOOL: "tool", "tool": END})


def build_enum_classes_collision_graph() -> StateGraph[SentinelState]:
    """Members of two enum classes with one stored value — a collision after projection."""
    return _decision_router_graph({AgentDecision.TOOL: "tool", RecordingDecision.TOOL: END})


def build_enum_router_target_graph() -> StateGraph[SentinelState]:
    """A router hinted ``-> Literal[RecordingDecision.TOOL]`` and no ``path_map``: a member target.

    The substrate fills ``ends`` from the hint as ``{member: member}`` (A1 §2) — the label is
    admitted, and the *target* is the member, which no node is named. Refused at the router's
    target guard (``unrepresentable-node-id``) before ``== END``, the reserved-segment test or the
    escaping can run one of its methods. The annotation is set as an evaluated object so that
    extraction itself evaluates nothing.
    """

    def route_to_member(state: SentinelState) -> Any:
        raise SentinelExecutedError("'route_to_member' was invoked — extraction must never call it")

    route_to_member.__annotations__ = {
        "state": SentinelState,
        "return": Literal[RecordingDecision.TOOL],
    }
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_to_member)
    builder.add_edge("tool", END)
    return builder


def build_enum_node_target_graph() -> StateGraph[SentinelState]:
    """A node routing declaration naming a member as its target — refused at that site's guard."""
    builder = StateGraph(SentinelState)
    builder.add_node(
        "agent",
        raiser("agent"),
        destinations=(RecordingDecision.TOOL,),  # type: ignore[arg-type]  # the fixture
    )
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_edge("tool", END)
    return builder


def build_enum_entry_target_graph() -> StateGraph[SentinelState]:
    """A conditional entry naming a member as its target — refused at the entry's own guard.

    The entry reads its targets without the shared target helper, so it carries the guard
    itself; before EX-27 this shape escaped ``extract()`` as a raw ``TypeError`` from node-id
    escaping, after the reserved-segment test had hashed the member (PD-067's re-probe).
    """
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"))
    builder.set_conditional_entry_point(
        raiser("route_entry"),
        {"go": RecordingDecision.TOOL},  # type: ignore[dict-item]  # the fixture
    )
    builder.add_edge("agent", END)
    return builder


class RecordingName(str):
    """A ``str``-subclass target name whose own hash, comparison and renderings record."""

    __slots__ = ()

    def __hash__(self) -> int:
        LABEL_READS.append("RecordingName.__hash__")
        return str.__hash__(self)

    def __eq__(self, other: object) -> bool:
        LABEL_READS.append("RecordingName.__eq__")
        return str.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        LABEL_READS.append("RecordingName.__ne__")
        return str.__ne__(self, other)

    def __repr__(self) -> str:
        LABEL_READS.append("RecordingName.__repr__")
        return str.__repr__(self)

    def __str__(self) -> str:
        LABEL_READS.append("RecordingName.__str__")
        return str.__str__(self)

    def __format__(self, format_spec: str) -> str:
        LABEL_READS.append("RecordingName.__format__")
        return str.__format__(self, format_spec)


class RecordingTuple(tuple[Any, ...]):
    """A ``tuple`` subclass declared as ``destinations=``; its own container methods record."""

    __slots__ = ()

    def __iter__(self) -> Iterator[Any]:
        LABEL_READS.append("RecordingTuple.__iter__")
        return tuple.__iter__(self)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingTuple.__len__")
        return tuple.__len__(self)

    def __bool__(self) -> bool:
        LABEL_READS.append("RecordingTuple.__bool__")
        return tuple.__len__(self) > 0

    def __contains__(self, item: object) -> bool:
        LABEL_READS.append("RecordingTuple.__contains__")
        return tuple.__contains__(self, item)

    def __getitem__(self, index: Any) -> Any:
        LABEL_READS.append("RecordingTuple.__getitem__")
        return tuple.__getitem__(self, index)


class RecordingList(list[Any]):
    """A ``list`` subclass declared as ``destinations=``; its own container methods record."""

    def __iter__(self) -> Iterator[Any]:
        LABEL_READS.append("RecordingList.__iter__")
        return list.__iter__(self)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingList.__len__")
        return list.__len__(self)

    def __bool__(self) -> bool:
        LABEL_READS.append("RecordingList.__bool__")
        return list.__len__(self) > 0

    def __contains__(self, item: object) -> bool:
        LABEL_READS.append("RecordingList.__contains__")
        return list.__contains__(self, item)

    def __getitem__(self, index: Any) -> Any:
        LABEL_READS.append("RecordingList.__getitem__")
        return list.__getitem__(self, index)


class RecordingSet(set[Any]):
    """A ``set`` subclass declared as ``destinations=``; its own container methods record."""

    def __iter__(self) -> Iterator[Any]:
        LABEL_READS.append("RecordingSet.__iter__")
        return set.__iter__(self)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingSet.__len__")
        return set.__len__(self)

    def __bool__(self) -> bool:
        LABEL_READS.append("RecordingSet.__bool__")
        return set.__len__(self) > 0

    def __contains__(self, item: object) -> bool:
        LABEL_READS.append("RecordingSet.__contains__")
        return set.__contains__(self, item)


class RecordingFrozenset(frozenset[Any]):
    """A ``frozenset`` subclass declared as ``destinations=``; its own container methods record."""

    __slots__ = ()

    def __iter__(self) -> Iterator[Any]:
        LABEL_READS.append("RecordingFrozenset.__iter__")
        return frozenset.__iter__(self)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingFrozenset.__len__")
        return frozenset.__len__(self)

    def __bool__(self) -> bool:
        LABEL_READS.append("RecordingFrozenset.__bool__")
        return frozenset.__len__(self) > 0

    def __contains__(self, item: object) -> bool:
        LABEL_READS.append("RecordingFrozenset.__contains__")
        return frozenset.__contains__(self, item)


class RecordingMapping(Mapping[str, Any]):
    """A mapping that is not a ``dict`` — every method of its own records; extraction calls none.

    Declared as ``destinations=`` it is stored as handed; returned by a ``path_map``'s own
    ``copy()`` it becomes a router's ``ends``. Either way it is warned as unreadable
    (``routing-declaration-unreadable``) and never iterated.
    """

    _data: dict[str, Any]

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        LABEL_READS.append("RecordingMapping.__getitem__")
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        LABEL_READS.append("RecordingMapping.__iter__")
        return iter(self._data)

    def __len__(self) -> int:
        LABEL_READS.append("RecordingMapping.__len__")
        return len(self._data)

    def __bool__(self) -> bool:
        LABEL_READS.append("RecordingMapping.__bool__")
        return bool(self._data)

    def __contains__(self, key: object) -> bool:
        LABEL_READS.append("RecordingMapping.__contains__")
        return key in self._data

    def items(self) -> Any:
        LABEL_READS.append("RecordingMapping.items")
        return self._data.items()

    def keys(self) -> Any:
        LABEL_READS.append("RecordingMapping.keys")
        return self._data.keys()

    def values(self) -> Any:
        LABEL_READS.append("RecordingMapping.values")
        return self._data.values()

    def get(self, key: str, default: Any = None) -> Any:
        LABEL_READS.append("RecordingMapping.get")
        return self._data.get(key, default)


class _MappingCopy(dict[Any, Any]):
    """A ``path_map`` whose own ``copy()`` hands the substrate a :class:`RecordingMapping`."""

    def copy(self) -> Any:
        return RecordingMapping(dict(dict.items(self)))


def build_recording_sequences_graph() -> StateGraph[SentinelState]:
    """Every sequence shape a node's ``destinations=`` can take, each a recording subclass.

    A ``tuple`` (holding a :class:`RecordingName` target, which is projected to a built-in
    ``str`` before anything compares it), a ``list``, a ``set`` and a ``frozenset`` — each read
    through the built-in type's own ``__iter__`` — and two mappings that are not a ``dict``, one
    as ``destinations=`` and one as a router's ``ends`` (the ``path_map``'s own ``copy()``
    returned it), both warned and never iterated. Extraction must leave ``LABEL_READS`` empty.
    """
    # The containers are subclasses, or outside the substrate's declared `dict | tuple`, so
    # the declared type cannot name them; each is typed `Any` for the call.
    as_tuple: Any = RecordingTuple(("act", RecordingName("review")))
    as_list: Any = RecordingList(["review", "plan"])
    as_set: Any = RecordingSet({"check"})
    as_frozenset: Any = RecordingFrozenset({"plan", "act"})
    as_mapping: Any = RecordingMapping({"plan": "go"})
    builder = StateGraph(SentinelState)
    builder.add_node("plan", raiser("plan"), destinations=as_tuple)
    builder.add_node("act", raiser("act"), destinations=as_list)
    builder.add_node("review", raiser("review"), destinations=as_set)
    builder.add_node("check", raiser("check"), destinations=as_frozenset)
    builder.add_node("idle", raiser("idle"), destinations=as_mapping)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("idle", raiser("route_idle"), _MappingCopy({"go": "plan"}))
    builder.add_edge("review", END)
    return builder


def build_set_target_graph() -> StateGraph[SentinelState]:
    """A ``destinations=`` set holding a non-string member — refused whole, before any read.

    A set's iteration order is the string-hash seed, so reading its members as labels in that
    order would let the seed decide whether the refusal is a label's or a target's; the whole
    declaration is refused as a target set instead (``unrepresentable-node-id``).
    """
    mixed: Any = {"tool", RecordingDecision.TOOL}  # outside the declared type: the fixture
    builder = StateGraph(SentinelState)
    builder.add_node("agent", raiser("agent"), destinations=mixed)
    builder.add_node("tool", raiser("tool"))
    builder.add_edge(START, "agent")
    builder.add_edge("tool", END)
    return builder


#: Every §3 shape that extracts, as (name, factory). The tripwire runs the whole list, so a
#: shape added here is a shape the never-invokes claim covers from that commit on.
EXTRACTABLE_BUILDERS: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "sentinel": build_sentinel_graph,
    "router_terminated": build_router_terminated_graph,
    "unwired": build_unwired_graph,
    "conditional_entry_declared": lambda: build_conditional_entry_graph(declared=True),
    "conditional_entry_dynamic": lambda: build_conditional_entry_graph(declared=False),
    "barrier": build_barrier_graph,
    "retry": build_retry_graph,
    "escaped_names": build_escaped_names_graph,
    "start_to_end": build_start_to_end_graph,
    "send_hinted_router": build_send_hinted_router_graph,
    "foreign_trigger": build_foreign_trigger_graph,
    "destinations": build_destinations_graph,
    "reserved_routing_target": build_reserved_routing_target_graph,
    "non_nfc_label": build_non_nfc_label_graph,
    "str_mixin_enum_label": build_str_mixin_enum_label_graph,
    # Moved here from REFUSED_BUILDERS when the ruled `kind: dynamic` form landed (DEC-28,
    # 2026-08-09; EX-03). It extracts now, and it is the same object either way, so the WA-07
    # claim over it is unbroken across the change rather than re-established.
    "targetless_router": build_targetless_router_graph,
    # The DEC-38 admission (EX-27): a plain `Enum` label whose stored value is an exact `str`.
    # Uncompiled on purpose — the substrate itself calls `str()` on every branch label at
    # `compile()` (DEC-38 §3.10), so the armed `AgentDecision` could be compiled by no one.
    "enum_label": build_enum_label_graph,
    "enum_label_recorded": build_recorded_enum_label_graph,
    "enum_label_literal_hinted": build_literal_hinted_enum_label_graph,
    "enum_label_literal_hinted_stringly": lambda: build_literal_hinted_enum_label_graph(
        stringly=True
    ),
    "enum_label_planted_dict": build_planted_dict_enum_label_graph,
    "recording_ends": build_recording_ends_graph,
    "recording_sequences": build_recording_sequences_graph,
}

#: The §3 shapes that are refused at the object boundary, as (name, factory). The tripwire
#: runs these too: a refusal must also reach it without executing anything.
REFUSED_BUILDERS: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "nonstring_label": build_nonstring_label_graph,
    "nfc_collision_label": build_nfc_collision_label_graph,
    "unnamed_node": build_unnamed_node_graph,
    # DEC-38's forms still refused (EX-27), and one non-string *target* per target-reading
    # site: the router, the node routing declaration, and the conditional entry.
    "int_enum_label": build_int_enum_label_graph,
    "int_valued_enum_label": build_int_valued_enum_label_graph,
    "subclass_valued_enum_label": build_subclass_valued_enum_label_graph,
    "shadowed_enum_label": build_shadowed_enum_label_graph,
    "object_valued_enum_label": build_object_valued_enum_label_graph,
    "enum_string_collision": build_enum_string_collision_graph,
    "enum_classes_collision": build_enum_classes_collision_graph,
    "enum_router_target": build_enum_router_target_graph,
    "enum_node_target": build_enum_node_target_graph,
    "enum_entry_target": build_enum_entry_target_graph,
    "set_target": build_set_target_graph,
}


def compile_sentinel_graph() -> CompiledStateGraph[SentinelState]:
    """Compile the sentinel graph on demand.

    compile() is graph construction, not execution, but it stays guarded
    behind this function so that importing the module does the minimum:
    build only.
    """
    return build_sentinel_graph().compile()


# Built at import time — import-safe by construction (see module docstring).
SENTINEL_GRAPH: StateGraph[SentinelState] = build_sentinel_graph()
