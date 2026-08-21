"""Compiled-level (§4) fixtures for the extraction tripwires (decisions D-018/D-023).

The companion to :mod:`tests.sample_workflows.sentinel_graph`, covering what only exists after
``compile()``: interrupt gates (including the ``All`` sentinel), checkpointer presence, folded
``set_node_defaults``, discovered subgraphs, the error-handler map, and the two shapes the
INTROSPECTION-SPEC §4.2 cross-check has to tell apart — a graph whose builder and compiled
readings agree, and ones where they do not.

Every node function and router here raises :class:`~tests.sample_workflows.sentinel_graph.SentinelExecutedError`
if it is ever called, so an extraction that invoked one fails the run instead of passing
quietly.

Import safety: importing this module **builds and compiles** the graphs. Compiling is the
fixture's own step, never extraction's — INTROSPECTION §1 rule 2 forbids ``extract()`` from
calling ``compile()`` on a builder handed to it, and the tripwire takes the method away before
the first extraction so the claim is checked rather than reviewed. Nothing here contacts an
external service or needs an API key.

**The armed objects are the point of this module's second half.** ``get_graph()`` is a bounded
symbolic execution of the Pregel loop, and at langgraph 1.2.10 that loop reaches user bodies by
five routes plus one that is not a body at all. There is one fixture per route, each recording
into :data:`TRIPPED` **before** it acts so a sentinel a ``try`` block swallowed still shows up:
:class:`ArmedChannel` (all six ``BaseChannel`` methods a drawing can touch), :class:`ArmedSaver`
(``get_next_version``), :func:`armed_cache_key`, :func:`armed_mapper`, :class:`ArmedRootValueType`
(a ``__root__`` channel's value type, which the drawing calls **as a constructor**), and
:class:`SocketOpeningPregel` — the ``RemoteGraph`` shape reduced to what makes it a hazard, an
object that implements the protocol §2 dispatches on and answers ``get_graph()`` over the
network. :class:`RecordingChannel` is the odd one out: it records and *returns*, because a
fixture that only ever raises can show that extraction stopped and never that it did not call.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.channels.base import BaseChannel
from langgraph.channels.last_value import LastValue
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import NodeBuilder, Pregel
from langgraph.pregel._write import ChannelWriteEntry
from langgraph.types import CachePolicy, RetryPolicy

from tests import substrate
from tests.sample_workflows.sentinel_graph import (
    SentinelExecutedError,
    SentinelState,
    act_step,
    plan_step,
    raiser,
    summarize_step,
)

#: Every guarded read a fixture here observes, recorded **before** it raises (or returns), so a
#: sentinel swallowed by an ``except`` block still fails the run. Cleared per test.
TRIPPED: list[str] = []


class ChannelSentinelError(BaseException):
    """Raised by a channel method extraction must never run.

    Derives from :class:`BaseException` rather than :class:`Exception` on purpose: the
    compiled path guards ``get_graph()`` with ``except Exception`` because a foreign object's
    250-step symbolic execution must cost a diagnostic rather than an extraction, and a
    sentinel that guard could swallow would prove nothing.
    """


class ArmedChannel(BaseChannel[str, str, str]):
    """A user-authored channel whose value methods are sentinels.

    ``ValueType`` records and answers, because that read *is* licensed — INTROSPECTION §3's
    state row names ``.channels`` as a source and the §3 Σ path reads it. ``get`` and
    ``update`` are what the Pregel loop would reach, and neither is on §1 rule 3's list.
    """

    @property
    def ValueType(self) -> Any:
        TRIPPED.append("ValueType")
        return str

    @property
    def UpdateType(self) -> Any:
        return str

    def checkpoint(self) -> str:
        return ""

    def from_checkpoint(self, checkpoint: str | None = None) -> ArmedChannel:
        # Reached *before* any `get()` — `channels_from_checkpoint` calls it on every channel —
        # so arming only the value methods would leave the first thing a drawing touches unarmed.
        TRIPPED.append("ArmedChannel.from_checkpoint")
        raise ChannelSentinelError("a channel's from_checkpoint() ran during extraction")

    def update(self, values: Any) -> bool:
        TRIPPED.append("ArmedChannel.update")
        raise ChannelSentinelError("a channel's update() ran during extraction")

    def get(self) -> str:
        TRIPPED.append("ArmedChannel.get")
        raise ChannelSentinelError("a channel's get() ran during extraction")

    def consume(self) -> bool:
        TRIPPED.append("ArmedChannel.consume")
        raise ChannelSentinelError("a channel's consume() ran during extraction")

    def finish(self) -> bool:
        TRIPPED.append("ArmedChannel.finish")
        raise ChannelSentinelError("a channel's finish() ran during extraction")

    def is_available(self) -> bool:
        TRIPPED.append("ArmedChannel.is_available")
        raise ChannelSentinelError("a channel's is_available() ran during extraction")


class ArmedRootValueType:
    """A ``__root__`` channel's value type that records and raises **from its constructor**.

    Route 5 of the six DEC-19 drawing routes, in its sharpest form: ``draw_graph`` reads
    ``specs["__root__"].ValueType`` **and calls the result** — ``specs["__root__"].ValueType()``
    (``pregel/_draw.py``) — so the value type is invoked as a constructor, which is the
    pydantic-validator hazard §1 rule 4 names first. Constructing the *channel* over this type
    never calls it (``LastValue`` stores the type; ``ValueType`` is a property returning it); only
    the drawing would, and :func:`gebra.extraction.compiled._drawing_hazard` declines every
    drawing over a ``__root__`` channel before the call. So a pass means this ``__init__`` never
    ran — recorded into :data:`TRIPPED` **before** it raises so a swallowed one still shows up.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        TRIPPED.append("ArmedRootValueType.__init__")
        raise ChannelSentinelError("a `__root__` channel's ValueType() ran as a constructor")


class RecordingChannel(LastValue[str]):
    """A user subclass of a stock channel, recording instead of raising.

    Used where the point is to *show* which methods a drawing reaches rather than to forbid
    them: the compiled-only path has no surface but ``get_graph()``, so the calls it makes are
    recorded and pinned instead of prevented. Extending ``LastValue`` rather than
    ``BaseChannel`` keeps the drawing working — which is the whole point, since a channel that
    raised would prove only that extraction stops.
    """

    def update(self, values: Any) -> bool:
        TRIPPED.append("RecordingChannel.update")
        return super().update(values)

    def get(self) -> str:
        TRIPPED.append("RecordingChannel.get")
        return super().get()


class ArmedState(TypedDict):
    """A state schema bound to a user-authored channel."""

    query: Annotated[str, ArmedChannel(str)]


class RecordingState(TypedDict):
    """The same, with the recording channel."""

    query: Annotated[str, RecordingChannel(str)]


class LegState(TypedDict):
    """The subgraph's own state — deliberately not the parent's, so §4's blind spot is real."""

    leg: str
    booked: str


def _linear(builder: StateGraph[Any], *names: str) -> StateGraph[Any]:
    """Wire ``names`` START → … → END, each node an armed raiser."""
    previous = START
    for name in names:
        builder.add_node(name, raiser(name))
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    return builder


# ── §4.1 compiled-level surfaces ─────────────────────────────────────────────────────────


def build_gated_graph() -> CompiledStateGraph[SentinelState]:
    """Interrupt gates on both sides, plus a checkpointer — the §4.1 mainstream case."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step)
    builder.add_node("summarize_step", summarize_step)
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", "act_step")
    builder.add_edge("act_step", "summarize_step")
    builder.add_edge("summarize_step", END)
    return builder.compile(
        interrupt_before=["act_step"],
        interrupt_after=["plan_step"],
        checkpointer=InMemorySaver(),
    )


def build_all_gates_graph() -> CompiledStateGraph[SentinelState]:
    """``interrupt_before="*"`` — the ``All`` sentinel §4.1 requires to be expanded."""
    builder = _linear(StateGraph(SentinelState), "plan_step", "act_step")
    return builder.compile(interrupt_before="*")


def build_ungated_graph() -> CompiledStateGraph[SentinelState]:
    """No gates at all — §4.1's "emits no ``interrupts`` object", and no checkpointer."""
    return _linear(StateGraph(SentinelState), "plan_step", "act_step").compile()


def build_folded_defaults_graph() -> CompiledStateGraph[SentinelState]:
    """One node inheriting the graph-level retry policy and one declaring its own.

    ``compile()`` folds ``set_node_defaults`` into the builder's own node specs, so the folded
    value reaches the IR through §3 like any authored one; which node *inherited* it is what
    §4.1 puts in provenance, and this fixture is the pair that makes the distinction visible.

    **Buildable only where the API is** — ``set_node_defaults`` arrived in langgraph 1.2.0, and
    two of the three frozen VERSION-COMPAT §3 pair cells sit below it. Reached through
    :data:`EXTRACTABLE_COMPILED`, which carries this fixture only on a substrate that has it,
    and named in :data:`UNAVAILABLE_COMPILED` on the ones that do not.
    """
    if not substrate.HAS_NODE_DEFAULTS:  # pragma: no cover - gated by every caller
        raise RuntimeError(substrate.NODE_DEFAULTS_REASON)
    builder = StateGraph(SentinelState)
    # `mypy` reads the *installed* builder, and the gate runs on every matrix cell — so on the
    # two below langgraph 1.2.0 this call has no attribute to resolve and the ignore is load-
    # bearing, while on 1.2+ it is unnecessary. `unused-ignore` is what lets one line be
    # correct on both, and is the reason the code is named rather than a bare `type: ignore`.
    builder.set_node_defaults(  # type: ignore[attr-defined, unused-ignore]
        retry_policy=RetryPolicy(max_attempts=5, retry_on=ValueError)
    )
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step, retry_policy=RetryPolicy(max_attempts=2))
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", "act_step")
    builder.add_edge("act_step", END)
    return builder.compile()


def build_subgraph_parent() -> CompiledStateGraph[SentinelState]:
    """A node whose bound object is itself a compiled graph — §4.1 subgraph discovery."""
    child = StateGraph(LegState)
    child.add_node("book_leg", raiser("book_leg"))
    child.add_node("confirm_leg", raiser("confirm_leg"))
    child.add_edge(START, "book_leg")
    child.add_edge("book_leg", "confirm_leg")
    child.add_edge("confirm_leg", END)

    parent: StateGraph[Any] = StateGraph(SentinelState)
    parent.add_node("plan_step", plan_step)
    parent.add_node("legs", child.compile())
    parent.add_node("summarize_step", summarize_step)
    parent.add_edge(START, "plan_step")
    parent.add_edge("plan_step", "legs")
    parent.add_edge("legs", "summarize_step")
    parent.add_edge("summarize_step", END)
    return parent.compile()


def build_error_handler_graph() -> CompiledStateGraph[SentinelState]:
    """A node with a declared error handler — §4.1's ``node_error_handler_map``.

    **Buildable only where the API is**, and here the guard is load-bearing rather than
    defensive: ``add_node`` takes ``**kwargs``, so a 1.0/1.1 builder *accepts* ``error_handler=``
    and drops it, leaving a plain node wearing this fixture's name. The keyword and the
    compiled ``node_error_handler_map`` both arrived in langgraph 1.2.0.
    """
    if not substrate.HAS_NODE_ERROR_HANDLER:  # pragma: no cover - gated by every caller
        raise RuntimeError(substrate.NODE_ERROR_HANDLER_REASON)
    builder = StateGraph(SentinelState)
    # As above: the keyword is not in the 1.0/1.1 overload set, so the ignore is load-bearing
    # on those cells' `mypy` gate and unnecessary on 1.2+.
    builder.add_node(  # type: ignore[call-overload, unused-ignore]
        "plan_step", plan_step, error_handler=raiser("recover")
    )
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)
    return builder.compile()


# ── §4.2/§4.3 the cross-check ────────────────────────────────────────────────────────────


def build_agreeing_graph() -> CompiledStateGraph[SentinelState]:
    """A declared router with a ``path_map`` — the two readings agree edge for edge."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step)
    builder.add_node("summarize_step", summarize_step)
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step",
        raiser("route_after_plan"),
        {"act": "act_step", "done": "summarize_step"},
    )
    builder.add_edge("act_step", "summarize_step")
    builder.add_edge("summarize_step", END)
    return builder.compile()


def build_seeded_divergence() -> CompiledStateGraph[SentinelState]:
    """The builder gains an edge **after** compilation — a divergence with a known answer.

    Exactly DEC-06's question ("which level is authoritative when they disagree?") made
    reproducible: the compiled object was built from one topology and its ``.builder``
    now declares another. §4.3 rule 3's answer is that the builder wins and the divergence is
    recorded, so the extracted IR must carry the *added* edge and the warning must name it as
    present in the builder reading and absent from the drawing.
    """
    compiled = _linear(StateGraph(SentinelState), "plan_step", "act_step").compile()
    compiled.builder.edges.add(("plan_step", "summarize_step"))
    compiled.builder.nodes["summarize_step"] = compiled.builder.nodes["act_step"]
    return compiled


def build_natural_divergence() -> CompiledStateGraph[SentinelState]:
    """A graph the drawing reads as terminating where the builder declares no END wiring.

    Not seeded: a router-only graph with no ``(x, END)`` edge extracts ``finish: []``, while
    the Pregel loop's drawing invents the implicit termination §4.2 warns about. This is the
    divergence a real workflow hits, and the reason the warning exists at all.
    """
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step)
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", raiser("route"), {"act": "act_step"})
    return builder.compile()


def build_router_to_end_graph() -> CompiledStateGraph[SentinelState]:
    """A router with an END label — the (m3) incidence on both sides of the comparison.

    The builder reading puts it in ``finish`` through a ``path_map`` label valued ``"END"``
    (DEC-18's forced spelling) while the drawing puts it in an ``__end__`` edge, so this is the
    shape that shows the two readings meeting in the same slot from different directions.
    """
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step)
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges(
        "plan_step", raiser("route_or_finish"), {"act": "act_step", "done": END}
    )
    builder.add_edge("act_step", END)
    return builder.compile()


def build_armed_channel_graph() -> CompiledStateGraph[ArmedState]:
    """A compiled graph bound to a user-authored channel — the cross-check must decline."""
    builder: StateGraph[Any] = StateGraph(ArmedState)
    builder.add_node("plan_step", plan_step)
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)
    return builder.compile()


def build_recording_channel_graph() -> CompiledStateGraph[RecordingState]:
    """A compiled graph bound to a user channel that would have answered harmlessly.

    The precondition is about the channel's *class*, not about whether its body misbehaves —
    extraction cannot know which it is without running it. This fixture is what makes that
    difference checkable: nothing here would raise, and the cross-check declines anyway.
    """
    builder: StateGraph[Any] = StateGraph(RecordingState)
    builder.add_node("plan_step", plan_step)
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)
    return builder.compile()


class ArmedSaver(InMemorySaver):
    """A user checkpointer whose ``get_next_version`` is a sentinel.

    ``draw_graph`` binds it when the object carries a ``BaseCheckpointSaver`` and calls it once
    per applied write (``_algo.py``'s ``apply_writes``). Overriding it is a documented extension
    point, and a saver is the object most likely to reach a database.
    """

    def get_next_version(self, current: Any, *args: Any, **kwargs: Any) -> Any:
        TRIPPED.append("ArmedSaver.get_next_version")
        raise ChannelSentinelError("a checkpointer's get_next_version() ran during extraction")


def armed_cache_key(value: Any) -> str:
    """A user cache key function — ``prepare_next_tasks`` calls it while preparing tasks."""
    TRIPPED.append("armed_cache_key")
    raise ChannelSentinelError("a cache key function ran during extraction")


def armed_mapper(value: Any) -> Any:
    """A user write mapper — ``ChannelWrite.invoke`` calls it per entry."""
    TRIPPED.append("armed_mapper")
    raise ChannelSentinelError("a write mapper ran during extraction")


def build_armed_checkpointer_graph() -> CompiledStateGraph[SentinelState]:
    """Route 2 of the drawing's five: a user checkpointer."""
    return _linear(StateGraph(SentinelState), "plan_step", "act_step").compile(
        checkpointer=ArmedSaver()
    )


def build_armed_cache_policy_graph() -> CompiledStateGraph[SentinelState]:
    """Route 3: a user cache key function, wired through the member §3 already names."""
    builder = StateGraph(SentinelState)
    builder.add_node("plan_step", plan_step, cache_policy=CachePolicy(key_func=armed_cache_key))
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)
    return builder.compile()


def build_armed_mapper_pregel() -> Pregel[Any, Any, Any, Any]:
    """Route 4: a user ``ChannelWrite`` mapper on a hand-built ``Pregel``.

    The population §4.3 rule 4 exists for — a ``Pregel`` assembled directly — is exactly where
    a write entry's ``mapper`` is the author's rather than LangGraph's.
    """
    node = (
        NodeBuilder()
        .subscribe_only("question")
        .do(pregel_step)
        .write_to(ChannelWriteEntry("answer", mapper=armed_mapper))
    )
    return Pregel(
        nodes={"pregel_step": node},
        channels={"question": LastValue(str), "answer": LastValue(str)},
        input_channels="question",
        output_channels="answer",
    )


def build_armed_root_pregel() -> Pregel[Any, Any, Any, Any]:
    """Route 5: a builderless ``Pregel`` whose ``__root__`` channel arms its value type.

    The compiled-only path's only surface is the gated drawing, and a ``__root__`` channel is
    the one route where the drawing *constructs* rather than merely reads — so this is the
    refusal fixture that proves the gate stands down before the constructor fires.
    ``ArmedRootValueType()`` records into :data:`TRIPPED` and raises; a pass is the empty record.
    """
    node = NodeBuilder().subscribe_only("__root__").do(pregel_step).write_to("__root__")
    return Pregel(
        nodes={"pregel_step": node},
        channels={"__root__": LastValue(ArmedRootValueType)},
        input_channels="__root__",
        output_channels="__root__",
    )


def build_armed_channel_subgraph_parent() -> CompiledStateGraph[SentinelState]:
    """A stock-channelled parent whose *subgraph* binds a user channel.

    ``xray`` draws each discovered subgraph with the same loop, so the precondition has to
    reach one level down or it is not a precondition at all.
    """
    child: StateGraph[Any] = StateGraph(ArmedState)
    child.add_node("book_leg", raiser("book_leg"))
    child.add_edge(START, "book_leg")
    child.add_edge("book_leg", END)

    parent: StateGraph[Any] = StateGraph(SentinelState)
    parent.add_node("plan_step", plan_step)
    parent.add_node("legs", child.compile())
    parent.add_edge(START, "plan_step")
    parent.add_edge("plan_step", "legs")
    parent.add_edge("legs", END)
    return parent.compile()


class RouterState(TypedDict):
    """State for the ``Command``-routing fixture below."""

    step: str


def command_router(state: RouterState) -> Any:
    raise SentinelExecutedError("node 'command_router' was invoked — extraction never calls nodes")


command_router.__annotations__["return"] = "Command[Literal['finish_step']]"


def build_command_routing_graph() -> CompiledStateGraph[RouterState]:
    """``destinations=`` routing — a conditional edge on both sides, drawn and declared."""
    builder = StateGraph(RouterState)
    builder.add_node("command_router", raiser("command_router"), destinations=("finish_step",))
    builder.add_node("finish_step", raiser("finish_step"))
    builder.add_edge(START, "command_router")
    builder.add_edge("finish_step", END)
    return builder.compile()


# ── §4.3 rule 4: builderless Pregel objects ──────────────────────────────────────────────


def pregel_step(value: Any) -> Any:
    raise SentinelExecutedError("Pregel node 'pregel_step' was invoked — extraction never calls")


def build_gated_pregel() -> Pregel[Any, Any, Any, Any]:
    """A hand-built ``Pregel`` with interrupt gates and a checkpointer.

    The compiled-level slots are **not** downgraded by §4.3 rule 4 — §7.1 rates them Full "at
    the compiled level only", and this object is that level — so a builderless extraction must
    still carry them.
    """
    from langgraph.channels.last_value import LastValue

    node = NodeBuilder().subscribe_only("question").do(pregel_step).write_to("answer")
    return Pregel(
        nodes={"pregel_step": node},
        channels={"question": LastValue(str), "answer": LastValue(str)},
        input_channels="question",
        output_channels="answer",
        interrupt_before_nodes=["pregel_step"],
        checkpointer=InMemorySaver(),
    )


def build_recording_channel_pregel() -> Pregel[Any, Any, Any, Any]:
    """A builderless Pregel bound to a user-authored channel that records what is asked of it.

    The fixture behind the one honest exposure this card records: on the compiled-only path
    ``get_graph()`` is the extraction surface §2 names, so it is called, and the drawing's loop
    asks the channel for its value.
    """
    node = NodeBuilder().subscribe_only("question").do(pregel_step).write_to("answer")
    return Pregel(
        nodes={"pregel_step": node},
        channels={"question": RecordingChannel(str), "answer": RecordingChannel(str)},
        input_channels="question",
        output_channels="answer",
    )


class UndrawablePregel:
    """A Pregel-protocol object whose ``get_graph`` is callable and yields nothing usable.

    §2's dispatch test is ``callable(get_graph)``, which this passes; the §4.3 rule-4 path then
    finds no drawing behind it. The object boundary is where that becomes an error (§2), and
    this is the shape that reaches it.
    """

    builder = None

    def get_graph(self, *args: Any, **kwargs: Any) -> None:
        return None


class NodelessPregel:
    """A drawable object whose drawing holds only the reserved sentinels.

    The IR requires at least one node (IR-SPEC §2.1), so this is the §2 boundary refusal for
    the compiled-only path — the counterpart of a builder with an empty ``.nodes`` dict.
    """

    builder = None

    def get_graph(self, *args: Any, **kwargs: Any) -> Any:
        return _EmptyDrawing()


class _EmptyDrawing:
    nodes: dict[str, Any] = {"__start__": None, "__end__": None}  # noqa: RUF012
    edges: tuple[Any, ...] = ()


# ── hand-rolled Pregel-protocol implementations ──────────────────────────────────────────
#
# Everything below models a *third-party* Pregel implementation rather than LangGraph's own.
# §2 defines the family by the runtime-checkable ``PregelProtocol``, so these shapes are in
# scope by the spec's own definition, and they are how the §4 path's guards get reached: a
# LangGraph object cannot produce a drawing with a reserved edge target or a node name with no
# representable id, and a build that only ever met LangGraph objects would carry those guards
# untested.


class DrawnEdge:
    """One edge of a hand-authored drawing, in the shape ``langchain_core``'s ``Edge`` has."""

    def __init__(
        self, source: str, target: str, *, data: Any = None, conditional: bool = False
    ) -> None:
        self.source = source
        self.target = target
        self.data = data
        self.conditional = conditional


class Drawing:
    """A hand-authored drawing: a node mapping and an edge sequence, and nothing else."""

    def __init__(self, nodes: Any, edges: Any) -> None:
        self.nodes = nodes
        self.edges = edges


class DrawnPregel:
    """A hand-rolled ``PregelProtocol`` implementation that answers with a drawing.

    **This is a refusal fixture, not an extraction one.** ``get_graph()`` on an arbitrary
    protocol implementation is arbitrary code — ``langgraph.pregel.remote.RemoteGraph`` is the
    first-party proof, since its getter issues an HTTP request — so the §4 path refuses to draw
    anything that is not a real ``langgraph.pregel.Pregel``. Authored drawings reach the reading
    code through :func:`drawn_pregel` and :func:`drawn_compiled` instead, which patch a *real*
    object's getter and so pass the gate.
    """

    def __init__(
        self,
        drawing: Any,
        *,
        builder: Any = None,
        interrupt_before_nodes: Any = (),
        interrupt_after_nodes: Any = (),
        checkpointer: Any = None,
        subgraphs: Any = (),
        error_handlers: Any = None,
        channels: Any = None,
    ) -> None:
        self.builder = builder
        # Stock channels by default: the §4.2 precondition asks whether any channel class is
        # user-authored, and an object that declares none has none.
        self.channels: Any = {"question": LastValue(str)} if channels is None else channels
        self._drawing = drawing
        self.interrupt_before_nodes = interrupt_before_nodes
        self.interrupt_after_nodes = interrupt_after_nodes
        self.checkpointer = checkpointer
        self._subgraphs = subgraphs
        if error_handlers is not None:
            self.node_error_handler_map = error_handlers

    def get_graph(self, *args: Any, **kwargs: Any) -> Any:
        return self._drawing

    def get_subgraphs(self, *args: Any, **kwargs: Any) -> Any:
        return self._subgraphs


class SubgraphlessPregel(DrawnPregel):
    """A drawable Pregel-protocol object exposing no ``get_subgraphs`` at all.

    A ``CompiledStateGraph`` always has the getter, so this is the third-party shape §4.1's
    discovery — and the cross-check's precondition scan — has to tolerate.
    """

    get_subgraphs = None  # type: ignore[assignment]


def build_two_node_builder() -> StateGraph[SentinelState]:
    """A plain two-node builder, for pairing with an authored drawing."""
    return _linear(StateGraph(SentinelState), "plan_step", "act_step")


class SocketOpeningPregel(DrawnPregel):
    """The ``RemoteGraph`` shape, reduced to what makes it a hazard.

    ``langgraph.pregel.remote.RemoteGraph`` implements ``PregelProtocol`` with no ``.builder``
    and answers ``get_graph()`` with ``GET /assistants/{id}/graph``. INTROSPECTION-SPEC §1
    rule 1 forbids opening a network connection outright, so this is the negative control for
    the compiled-only path's boundary gate: extraction must refuse *before* calling, and the
    socket below is what proves it did.
    """

    def get_graph(self, *args: Any, **kwargs: Any) -> Any:
        import socket

        TRIPPED.append("SocketOpeningPregel.get_graph")
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        raise ChannelSentinelError("a drawing opened a socket during extraction")


def drawn_pregel(drawing: Any, **attributes: Any) -> Pregel[Any, Any, Any, Any]:
    """A **real** builderless ``Pregel`` whose ``get_graph`` answers with ``drawing``.

    The object is genuine LangGraph — so it passes the §1 gate in front of the drawing — while
    the drawing itself is authored, which is the only way to reach the reading code's guards: a
    LangGraph drawing never carries an edge into a reserved sentinel or a node name with no
    representable id, and a build whose guards were never exercised would discover them on the
    first third-party substrate rather than here.
    """
    workflow = build_gated_pregel()
    workflow.interrupt_before_nodes = ()
    workflow.checkpointer = None
    for name, value in attributes.items():
        setattr(workflow, name, value)
    workflow.get_graph = lambda *args, **kwargs: drawing  # type: ignore[method-assign]
    return workflow


def drawn_compiled(drawing: Any) -> CompiledStateGraph[SentinelState]:
    """A **real** compiled two-node graph whose ``get_graph`` answers with ``drawing``.

    The cross-check's counterpart of :func:`drawn_pregel`: a known builder reading on one side
    and an authored compiled reading on the other, so each "modulo" rule of §4.3 rule 2 can be
    checked on its own instead of against whatever LangGraph happens to draw.
    """
    compiled = _linear(StateGraph(SentinelState), "plan_step", "act_step").compile()
    compiled.get_graph = lambda *args, **kwargs: drawing  # type: ignore[method-assign]
    return compiled


class UnreadableSubgraphsPregel(DrawnPregel):
    """One whose ``get_subgraphs`` raises — provenance degrades, extraction does not."""

    def get_subgraphs(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("subgraph discovery blew up")


def register_protocol_shims() -> None:
    """Register the hand-rolled shapes above as Pregel-protocol virtual subclasses.

    §2 defines ``is_pregel(x)`` as ``isinstance(x, PregelProtocol)`` — the runtime-checkable
    protocol LangGraph's own subgraph discovery keys on — so a third-party implementation
    reaches the §4 family by registration, which is what these two model.
    """
    from langgraph.pregel.protocol import PregelProtocol

    for shape in (
        UndrawablePregel,
        NodelessPregel,
        DrawnPregel,
        SubgraphlessPregel,
        UnreadableSubgraphsPregel,
    ):
        PregelProtocol.register(shape)


register_protocol_shims()


def build_empty_gates_graph() -> CompiledStateGraph[SentinelState]:
    """Gates declared as empty lists — §4.1's "an empty gate list emits no member"."""
    builder = _linear(StateGraph(SentinelState), "plan_step", "act_step")
    return builder.compile(interrupt_before=[], interrupt_after=["act_step"])


#: The fixtures whose construct arrived with a langgraph minor above some frozen matrix cell,
#: mapped to the reason a test that needs one skips. Empty on a substrate that has them all.
#:
#: This is the honest half of the version gate: :data:`EXTRACTABLE_COMPILED` below carries only
#: what the installed builder can build — so the WA-07 child, which compiles every entry, stays
#: armed on every cell — and this table says *which* shapes are missing and *why*, so a reduced
#: fixture set reads as a named skip with its cause rather than as coverage that quietly went
#: away (EX-17 / PD-038 Finding 2).
UNAVAILABLE_COMPILED: dict[str, str] = {}
if not substrate.HAS_NODE_DEFAULTS:
    UNAVAILABLE_COMPILED["folded-defaults"] = substrate.NODE_DEFAULTS_REASON
if not substrate.HAS_NODE_ERROR_HANDLER:
    UNAVAILABLE_COMPILED["error-handler"] = substrate.NODE_ERROR_HANDLER_REASON

#: Every compiled-family object this path extracts **on the installed substrate**, by name. The
#: WA-07 child quantifies over this table, so a shape added here joins the never-invokes claim
#: with it — and a shape the substrate cannot build is absent here and named in
#: :data:`UNAVAILABLE_COMPILED` instead, never silently unarmed.
EXTRACTABLE_COMPILED: dict[str, Any] = {
    "gated": build_gated_graph,
    "all-gates": build_all_gates_graph,
    "empty-gates": build_empty_gates_graph,
    "ungated": build_ungated_graph,
    "subgraph-parent": build_subgraph_parent,
    "agreeing": build_agreeing_graph,
    "router-to-end": build_router_to_end_graph,
    "seeded-divergence": build_seeded_divergence,
    "natural-divergence": build_natural_divergence,
    "armed-channel": build_armed_channel_graph,
    "armed-checkpointer": build_armed_checkpointer_graph,
    "armed-cache-policy": build_armed_cache_policy_graph,
    "recording-channel": build_recording_channel_graph,
    "armed-channel-subgraph": build_armed_channel_subgraph_parent,
    "command-routing": build_command_routing_graph,
    "gated-pregel": build_gated_pregel,
}
# The 1.2-era shapes, joined to the table only where their builder API exists. The two
# conditions are separate members of :mod:`tests.substrate` rather than one "is 1.2" flag, so
# a future minor that moves one of them moves only its own fixture.
if substrate.HAS_NODE_DEFAULTS:
    EXTRACTABLE_COMPILED["folded-defaults"] = build_folded_defaults_graph
if substrate.HAS_NODE_ERROR_HANDLER:
    EXTRACTABLE_COMPILED["error-handler"] = build_error_handler_graph

#: The compiled-family objects §2's error posture refuses at the object boundary.
REFUSED_COMPILED: dict[str, Any] = {
    "undrawable-pregel": UndrawablePregel,
    "nodeless-pregel": NodelessPregel,
    "socket-opening-pregel": lambda: SocketOpeningPregel(None),
    "armed-mapper-pregel": build_armed_mapper_pregel,
    "armed-root-pregel": build_armed_root_pregel,
    "recording-channel-pregel": build_recording_channel_pregel,
    "third-party-protocol-pregel": lambda: DrawnPregel(
        Drawing({"__start__": None, "n1": None}, [DrawnEdge("__start__", "n1")])
    ),
}

__all__ = [
    "EXTRACTABLE_COMPILED",
    "REFUSED_COMPILED",
    "TRIPPED",
    "UNAVAILABLE_COMPILED",
    "ArmedChannel",
    "ArmedRootValueType",
    "ArmedSaver",
    "ArmedState",
    "ChannelSentinelError",
    "Drawing",
    "DrawnEdge",
    "DrawnPregel",
    "LastValue",
    "LegState",
    "NodelessPregel",
    "RecordingChannel",
    "RecordingState",
    "RouterState",
    "SentinelExecutedError",
    "SocketOpeningPregel",
    "SubgraphlessPregel",
    "UndrawablePregel",
    "UnreadableSubgraphsPregel",
    "build_agreeing_graph",
    "build_all_gates_graph",
    "build_armed_cache_policy_graph",
    "build_armed_channel_graph",
    "build_armed_channel_subgraph_parent",
    "build_armed_checkpointer_graph",
    "build_armed_mapper_pregel",
    "build_armed_root_pregel",
    "build_command_routing_graph",
    "build_empty_gates_graph",
    "build_error_handler_graph",
    "build_folded_defaults_graph",
    "build_gated_graph",
    "build_gated_pregel",
    "build_natural_divergence",
    "build_recording_channel_graph",
    "build_recording_channel_pregel",
    "build_router_to_end_graph",
    "build_seeded_divergence",
    "build_subgraph_parent",
    "build_two_node_builder",
    "build_ungated_graph",
    "drawn_compiled",
    "drawn_pregel",
    "pregel_step",
]
