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

from typing import TYPE_CHECKING, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, Send

if TYPE_CHECKING:  # imported for typing only — never at runtime
    from collections.abc import Callable

    from langgraph.graph.state import CompiledStateGraph


class SentinelExecutedError(RuntimeError):
    """Raised by any sentinel node or router that gets invoked.

    Extraction must never cause this: a raise here means user code ran.
    """


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
    """A router whose `path_map` keys are not strings — an unruled ir 1.0 spelling."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step", raiser("route_plan"), {SentinelLabel("go"): "act_step"}
    )
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
    # Moved here from REFUSED_BUILDERS when the ruled `kind: dynamic` form landed (DEC-28,
    # 2026-08-09; EX-03). It extracts now, and it is the same object either way, so the WA-07
    # claim over it is unbroken across the change rather than re-established.
    "targetless_router": build_targetless_router_graph,
}

#: The §3 shapes that are refused at the object boundary, as (name, factory). The tripwire
#: runs these too: a refusal must also reach it without executing anything.
REFUSED_BUILDERS: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "nonstring_label": build_nonstring_label_graph,
    "unnamed_node": build_unnamed_node_graph,
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
