"""Subgraph-bearing fixtures for the extraction disclosure (INTROSPECTION-SPEC §8; DEC-36).

The workflows the ``subgraph-read-as-one-node`` disclosure is tested over: one per way a
compiled subgraph can sit under a node, crossed with the one property of the child that decides
which read can see it — ``checkpointer=False``, which LangGraph's own discovery skips. Which read
sees which shape (DEC-36 §3.6, measured on these fixtures by ``tests/extraction/test_disclosures.py``):

* a **direct mount** (the node's bound object is the compiled child): the builder's direct-mount
  read and ``get_subgraphs()`` both;
* a direct mount compiled with ``checkpointer=False``: the direct-mount read only;
* a **reached** child (the node's body holds it in a closure): ``get_subgraphs()`` only, so an
  uncompiled builder — which has no getter — sees nothing;
* a reached child compiled with ``checkpointer=False``: **no read at all** — the remainder the
  lower-bound sentence of every disclosure names;
* a builderless ``Pregel`` whose node binds a compiled child: ``get_subgraphs()`` only (the
  compiled-only path), and nothing when that child is compiled with ``checkpointer=False``.

Every node body — parent, child and closure alike — raises
:class:`~tests.sample_workflows.sentinel_graph.SentinelExecutedError` if it ever runs, and
constructing that exception records into ``sentinel_graph.TRIPPED`` first, so a sentinel some
``except`` swallowed still shows. A closure fires its sentinel through a call (:func:`_fire`)
before the line that reaches its child, so the body raises before the child could run, while
LangGraph's discovery still finds the child through the closure.

:class:`ArmedPregel` is the never-invokes half: a compiled graph mounted directly in an
uncompiled builder that records every attribute read of it into :data:`MOUNT_READS` and whose
execution and drawing entry points raise. It is extracted on the builder path only — compiling
its parent would have the substrate inspect it, and the compiled path's drawing gate reads every
level's channels by design. :class:`ClassLiar` pins the part of the ruled read's residual that
reaches the object itself: the ``isinstance`` DEC-36 rules reads ``__class__`` through the
object's own attribute access. The part that reaches ``abc`` hooks outside the object is pinned by
classes the test defines for itself.

Import safety: importing this module builds and compiles nothing; each factory builds when it is
called, and the ``compile()`` it calls on a child is the fixture's step, never extraction's. Nothing
here contacts an external service or needs an API key.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.channels.last_value import LastValue
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import NodeBuilder, Pregel

from tests.sample_workflows.sentinel_graph import (
    SentinelExecutedError,
    SentinelState,
    plan_step,
    raiser,
    summarize_step,
)

#: Every attribute read of an :class:`ArmedPregel`, in order — recorded before it is answered.
MOUNT_READS: list[str] = []

#: The surfaces of a mounted compiled graph whose read would mean extraction looked inside it or
#: ran it: its topology and compile-time members, its drawing and discovery getters, and its
#: execution entry points. The direct-mount read reads none of them — its ``isinstance`` reads
#: ``__class__`` and nothing else of the object — and neither does anything else on the builder
#: path.
INTERIOR_SURFACES: frozenset[str] = frozenset(
    {
        "builder",
        "nodes",
        "channels",
        "checkpointer",
        "config",
        "input_channels",
        "output_channels",
        "stream_channels",
        "interrupt_before_nodes",
        "interrupt_after_nodes",
        "get_graph",
        "aget_graph",
        "get_subgraphs",
        "aget_subgraphs",
        "get_state",
        "invoke",
        "ainvoke",
        "stream",
        "astream",
        "batch",
        "abatch",
        "with_config",
        "copy",
        "get_input_jsonschema",
        "get_output_jsonschema",
        "get_input_schema",
        "get_output_schema",
    }
)


class LegState(TypedDict):
    """The child's own state — deliberately not the parent's, as in a real mounted subgraph."""

    leg: str
    booked: str


def build_leg_child() -> StateGraph[LegState]:
    """The child graph every mount below compiles: two armed nodes, START → book → confirm → END."""
    child: StateGraph[LegState] = StateGraph(LegState)
    child.add_node("book_leg", raiser("book_leg"))
    child.add_node("confirm_leg", raiser("confirm_leg"))
    child.add_edge(START, "book_leg")
    child.add_edge("book_leg", "confirm_leg")
    child.add_edge("confirm_leg", END)
    return child


def compiled_leg_child(*, checkpointer: bool | None = None) -> CompiledStateGraph[LegState]:
    """The child, compiled — with ``checkpointer=False`` when the shape needs discovery to skip it."""
    return build_leg_child().compile(checkpointer=checkpointer)


def _fire(label: str) -> None:
    """Raise the sentinel for ``label``, which records into ``sentinel_graph.TRIPPED`` first."""
    raise SentinelExecutedError(f"{label!r} was invoked — extraction must never call it")


def reaching(label: str, child: CompiledStateGraph[LegState]) -> Callable[..., Any]:
    """A node body that reaches ``child`` from inside itself — the closure shape.

    LangGraph's ``find_subgraph_pregel`` finds such a child at compile time through the body's
    closure and source. The body fires its sentinel through :func:`_fire` first, so it raises
    before it could reach the child.
    """

    def body(state: Any) -> Any:
        _fire(label)
        return child.invoke(state)

    body.__name__ = label
    body.__qualname__ = label
    return body


def _parent(*mounts: tuple[str, Any]) -> StateGraph[SentinelState]:
    """A parent START → plan_step → each mount, in the order given → summarize_step → END."""
    parent: StateGraph[SentinelState] = StateGraph(SentinelState)
    parent.add_node("plan_step", plan_step)
    previous = "plan_step"
    for name, bound in mounts:
        parent.add_node(name, bound)
        parent.add_edge(previous, name)
        previous = name
    parent.add_node("summarize_step", summarize_step)
    parent.add_edge(START, "plan_step")
    parent.add_edge(previous, "summarize_step")
    parent.add_edge("summarize_step", END)
    return parent


# ── The four mount shapes, each an uncompiled parent ─────────────────────────────────────


def build_direct_mount_parent() -> StateGraph[SentinelState]:
    """``legs`` is bound to the compiled child itself — seen by both reads."""
    return _parent(("legs", compiled_leg_child()))


def build_unchecked_direct_mount_parent() -> StateGraph[SentinelState]:
    """``legs`` is bound to a child compiled with ``checkpointer=False`` — direct-mount read only."""
    return _parent(("legs", compiled_leg_child(checkpointer=False)))


def build_reached_mount_parent() -> StateGraph[SentinelState]:
    """``legs`` reaches the child from inside its body — ``get_subgraphs()`` only."""
    return _parent(("legs", reaching("legs", compiled_leg_child())))


def build_unchecked_reached_mount_parent() -> StateGraph[SentinelState]:
    """``legs`` reaches a ``checkpointer=False`` child from inside its body — no read sees it."""
    return _parent(("legs", reaching("legs", compiled_leg_child(checkpointer=False))))


def build_every_mount_parent() -> StateGraph[SentinelState]:
    """All four shapes in one graph, added out of node-id order, for the §8 ordering rule."""
    return _parent(
        ("zeta_direct", compiled_leg_child()),
        ("mid_reached", reaching("mid_reached", compiled_leg_child())),
        ("alpha_unchecked_direct", compiled_leg_child(checkpointer=False)),
        (
            "beta_unchecked_reached",
            reaching("beta_unchecked_reached", compiled_leg_child(checkpointer=False)),
        ),
    )


#: Two node names whose code-point order and UTF-16 code-unit order disagree: U+FF21 sorts first
#: by code point, U+1F600 — a surrogate pair in UTF-16, lead unit 0xD83D — sorts first by code
#: unit, which is the ledger §6 comparator node-id order means.
HIGH_BMP_NAME = "Ａ"
BEYOND_BMP_NAME = "\U0001f600"


def build_unicode_mounts_parent() -> StateGraph[SentinelState]:
    """Two direct mounts named so that only the ledger §6 comparator orders them right."""
    return _parent(
        (HIGH_BMP_NAME, compiled_leg_child()),
        (BEYOND_BMP_NAME, compiled_leg_child()),
    )


# ── The compiled-only path: a builderless Pregel whose node binds a compiled child ───────


def build_mounted_pregel(*, checkpointer: bool | None = None) -> Pregel[Any, Any, Any, Any]:
    """A hand-built ``Pregel`` (no ``.builder``) whose one node is bound to a compiled child.

    §4.3 rule 4's path: the drawing is the topology surface and ``get_subgraphs()`` the only
    subgraph read, so the child is disclosed exactly when the getter reports it — never when it
    was compiled with ``checkpointer=False``.
    """
    node = (
        NodeBuilder()
        .subscribe_only("question")
        .do(compiled_leg_child(checkpointer=checkpointer))
        .write_to("answer")
    )
    return Pregel(
        nodes={"pregel_step": node},
        channels={"question": LastValue(str), "answer": LastValue(str)},
        input_channels="question",
        output_channels="answer",
    )


# ── The armed mount ─────────────────────────────────────────────────────────────────────


class ArmedPregel(Pregel[Any, Any, Any, Any]):
    """A compiled graph whose every attribute read is recorded and whose entry points raise.

    The record is written before the attribute is answered, into :data:`MOUNT_READS`. The four
    sync entry points a reader could run it or look inside it through — ``invoke``, ``stream``,
    ``get_graph``, ``get_subgraphs`` — raise :class:`SentinelExecutedError`, which records into
    ``sentinel_graph.TRIPPED`` as it is built. The direct-mount read's ``isinstance`` records
    one read here, ``__class__`` — the part of its residual that reaches the object itself —
    and runs none of the four.
    """

    def __getattribute__(self, name: str) -> Any:
        MOUNT_READS.append(name)
        return object.__getattribute__(self, name)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise SentinelExecutedError("ArmedPregel.invoke ran — extraction never runs a subgraph")

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        raise SentinelExecutedError("ArmedPregel.stream ran — extraction never runs a subgraph")

    def get_graph(self, *args: Any, **kwargs: Any) -> Any:
        raise SentinelExecutedError("ArmedPregel.get_graph ran — a mounted graph is not drawn")

    def get_subgraphs(self, *args: Any, **kwargs: Any) -> Any:
        raise SentinelExecutedError("ArmedPregel.get_subgraphs ran — no read looks inside it")


def build_armed_mount_parent() -> StateGraph[SentinelState]:
    """``legs`` is bound directly to an :class:`ArmedPregel` — for the builder path only."""
    armed = ArmedPregel(
        nodes={
            "armed_step": NodeBuilder()
            .subscribe_only("question")
            .do(raiser("armed_step"))
            .write_to("answer")
        },
        channels={"question": LastValue(str), "answer": LastValue(str)},
        input_channels="question",
        output_channels="answer",
    )
    return _parent(("legs", armed))


class ClassLiar:
    """An object whose ``__class__`` claims ``Pregel`` and whose every attribute read records.

    Not a node of any fixture: the direct-mount read's unit tests apply the read to it directly,
    to pin the part of the residual INTROSPECTION-SPEC §3 row (iv) names for every
    ``isinstance`` on a bound object — the ruled check reads ``__class__`` through the object's
    own attribute access, so the object's ``__getattribute__`` and its ``__class__`` property
    run, and the check believes the answer.
    """

    def __getattribute__(self, name: str) -> Any:
        MOUNT_READS.append(name)
        return object.__getattribute__(self, name)

    @property  # type: ignore[misc]
    def __class__(self) -> type[Any]:
        MOUNT_READS.append("ClassLiar.__class__")
        return Pregel


#: The uncompiled parents, by name. Each is extracted as handed (the builder path) and compiled
#: (the builder-primary compiled path); the guarded child compiles before it arms.
PARENTS: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "direct": build_direct_mount_parent,
    "unchecked-direct": build_unchecked_direct_mount_parent,
    "reached": build_reached_mount_parent,
    "unchecked-reached": build_unchecked_reached_mount_parent,
    "every-mount": build_every_mount_parent,
    "unicode-names": build_unicode_mounts_parent,
}

#: The builderless objects, by name — the compiled-only path.
PREGELS: dict[str, Callable[[], Pregel[Any, Any, Any, Any]]] = {
    "mounted-pregel": build_mounted_pregel,
    "unchecked-mounted-pregel": lambda: build_mounted_pregel(checkpointer=False),
}

#: The parents extracted on the builder path only.
BUILDER_ONLY: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "armed-mount": build_armed_mount_parent,
}

__all__ = [
    "BEYOND_BMP_NAME",
    "BUILDER_ONLY",
    "HIGH_BMP_NAME",
    "INTERIOR_SURFACES",
    "MOUNT_READS",
    "PARENTS",
    "PREGELS",
    "ArmedPregel",
    "ClassLiar",
    "LegState",
    "build_armed_mount_parent",
    "build_direct_mount_parent",
    "build_every_mount_parent",
    "build_leg_child",
    "build_mounted_pregel",
    "build_reached_mount_parent",
    "build_unchecked_direct_mount_parent",
    "build_unchecked_reached_mount_parent",
    "build_unicode_mounts_parent",
    "compiled_leg_child",
    "reaching",
]
