"""Routing declarations covering INTROSPECTION-SPEC §6's classification table.

Two tables, at the two levels §6 decides things at:

* :data:`HINT_CASES` — one row per **declared return-hint form**, against the classification the
  spec's own sentence gives it. This is the level the rule is stated at ("bare ``Send``,
  ``list[Send]``/``Sequence[Send]``, or a ``Union``/``Command`` form admitting one" → ``send``;
  "a ``Literal[...]`` label hint, a plain ``str`` hint, ``path_map`` alone, ``destinations=``
  without a ``Send`` hint, or no hint at all" → ``conditional``), so it is the level the table
  is written at, declaratively, rather than as one test per form.
* :data:`ROUTING_BUILDERS` — one graph per **emission** rule: what a classified declaration
  turns into, including the three shapes with no ir carrier (a relabelled send template, a send
  template naming END, a codomain distinct from ``path_map``) and the two targetless forms.

Every callable here raises when called, and records itself in :data:`TRIPPED` **before**
raising, so a swallowed trip is still visible. Nothing in this module is ever invoked by
extraction: §6 reads *declarations*, and a router body is exactly what it never reads.

Importing this module builds nothing and evaluates nothing — the graphs are built by the
factories, on demand, the same discipline ``sentinel_graph`` follows.
"""

from collections.abc import Callable, Sequence
from typing import Literal, Optional, Union

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from tests.sample_workflows import sentinel_routing_futures as futures
from tests.sample_workflows.sentinel_graph import (
    SentinelExecutedError,
    SentinelState,
    raiser,
)

__all__ = [
    "HINT_CASES",
    "ROUTING_BUILDERS",
    "TRIPPED",
    "build_async_send_router_graph",
    "build_codomain_distinct_graph",
    "build_dynamic_send_hinted_graph",
    "build_lambda_send_router_graph",
    "build_node_destinations_send_graph",
    "build_send_forms_graph",
    "build_send_to_end_graph",
    "build_stringly_annotated_graph",
]

#: Every sentinel that was reached, recorded **before** it raises.
TRIPPED: list[str] = []


def _trip(what: str) -> None:
    """Record, then let the caller raise — so a swallowed trip is still visible."""
    TRIPPED.append(what)


# ── §6's classification table, one callable per declared hint form ────────────────────────


def route_send_bare(state: SentinelState) -> Send:
    """§6: "bare ``Send``"."""
    _trip("route_send_bare")
    raise SentinelExecutedError("'route_send_bare' was invoked")


def route_send_list(state: SentinelState) -> list[Send]:
    """§6: "``list[Send]``"."""
    _trip("route_send_list")
    raise SentinelExecutedError("'route_send_list' was invoked")


def route_send_sequence(state: SentinelState) -> Sequence[Send]:
    """§6: "``Sequence[Send]``"."""
    _trip("route_send_sequence")
    raise SentinelExecutedError("'route_send_sequence' was invoked")


def route_send_union(state: SentinelState) -> Send | str:
    """§6: "a ``Union`` … form admitting one", in the PEP 604 spelling (``types.UnionType``)."""
    _trip("route_send_union")
    raise SentinelExecutedError("'route_send_union' was invoked")


def route_send_typing_union(state: SentinelState) -> Union[Send, str]:  # noqa: UP007
    """The same form in the ``typing.Union`` spelling, which is a **different runtime object**.

    ``Send | str`` is a ``types.UnionType`` and ``Union[Send, str]`` is a
    ``typing._UnionGenericAlias``; the classification walks a type expression through
    ``typing.get_args``, which answers for both, and this is the fixture that says so rather
    than assuming it. The lint's PEP 604 preference is suppressed here for exactly that reason —
    the older spelling is still what plenty of workflow code is written in.
    """
    _trip("route_send_typing_union")
    raise SentinelExecutedError("'route_send_typing_union' was invoked")


def route_send_optional(state: SentinelState) -> Optional[list[Send]]:  # noqa: UP045
    """``Optional[list[Send]]`` — a ``Union`` form, in the spelling authors reach for."""
    _trip("route_send_optional")
    raise SentinelExecutedError("'route_send_optional' was invoked")


def route_send_pep604(state: SentinelState) -> Command[Literal["act_step"]] | list[Send]:
    """§6: "a ``Union``/``Command`` form admitting one" — a ``Command`` form that does."""
    _trip("route_send_pep604")
    raise SentinelExecutedError("'route_send_pep604' was invoked")


def route_literal(state: SentinelState) -> Literal["act_step"]:
    """§6: "a ``Literal[...]`` label hint" → ``conditional``."""
    _trip("route_literal")
    raise SentinelExecutedError("'route_literal' was invoked")


def route_literal_wider(state: SentinelState) -> Literal["act_step", "plan_step"]:
    """A two-label codomain — the §6 codomain-capture rule's input."""
    _trip("route_literal_wider")
    raise SentinelExecutedError("'route_literal_wider' was invoked")


def route_str(state: SentinelState) -> str:
    """§6: "a plain ``str`` hint" → ``conditional``."""
    _trip("route_str")
    raise SentinelExecutedError("'route_str' was invoked")


def route_command_literal(state: SentinelState) -> Command[Literal["act_step"]]:
    """A ``Command`` form naming no ``Send`` → ``conditional``. The mainstream Command idiom."""
    _trip("route_command_literal")
    raise SentinelExecutedError("'route_command_literal' was invoked")


def route_no_hint(state):  # type: ignore[no-untyped-def]  # the point of the fixture
    """§6: "or no hint at all" → ``conditional``."""
    _trip("route_no_hint")
    raise SentinelExecutedError("'route_no_hint' was invoked")


def route_none_hint(state: SentinelState) -> None:
    """A declared hint that names nothing routable → ``conditional``, and *declared*."""
    _trip("route_none_hint")
    raise SentinelExecutedError("'route_none_hint' was invoked")


async def route_async_send(state: SentinelState) -> list[Send]:
    """An ``async def`` router: the substrate leaves ``RunnableCallable.func`` empty."""
    _trip("route_async_send")
    raise SentinelExecutedError("'route_async_send' was invoked")


def node_sends(state: SentinelState) -> list[Send]:
    """A **node** function hinted ``-> list[Send]``, for the ``destinations=`` surface."""
    _trip("node_sends")
    raise SentinelExecutedError("'node_sends' was invoked")


#: §6's classification table as data: (label, callable, expected kind, expected codomain).
#:
#: The expected kind is §6's own sentence applied to the row, and the codomain column is the
#: codomain-capture rule's input on the same read — one table rather than two, because both come
#: off one hint.
HINT_CASES: tuple[tuple[str, Callable[..., object], str, tuple[str, ...]], ...] = (
    ("bare Send", route_send_bare, "send", ()),
    ("list[Send]", route_send_list, "send", ()),
    ("Sequence[Send]", route_send_sequence, "send", ()),
    ("Send | str", route_send_union, "send", ()),
    ("Union[Send, str]", route_send_typing_union, "send", ()),
    ("Optional[list[Send]]", route_send_optional, "send", ()),
    ("Command[...] | list[Send]", route_send_pep604, "send", ("act_step",)),
    ("Literal[one]", route_literal, "conditional", ("act_step",)),
    ("Literal[two]", route_literal_wider, "conditional", ("act_step", "plan_step")),
    ("str", route_str, "conditional", ()),
    ("Command[Literal[...]]", route_command_literal, "conditional", ("act_step",)),
    ("no hint", route_no_hint, "conditional", ()),
    ("None", route_none_hint, "conditional", ()),
    ("async list[Send]", route_async_send, "send", ()),
    ("node -> list[Send]", node_sends, "send", ()),
    # The string-annotated module: the branch that has to evaluate. Same table, because §6 does
    # not distinguish how an annotation was spelled — only what it names.
    ("stringly list[Send]", futures.route_send_stringly, "send", ()),
    ("stringly Literal", futures.route_literal_stringly, "conditional", ("act_step",)),
    ("stringly unresolvable", futures.route_unresolvable, "conditional", ()),
    ("stringly armed", futures.route_armed_annotation, "conditional", ()),
    ("stringly arming", futures.route_arming_hint, "send", ()),
    ("stringly unresolvable node", futures.node_unresolvable_hint, "conditional", ()),
)

#: The rows whose hint could not be read at all — §1 rule 3's degradation, as data.
#:
#: Kept beside :data:`HINT_CASES` rather than derived from it, so that "these two and only these
#: two degrade" is an assertion rather than a consequence of whatever the reader happens to do.
DEGRADING_CASES: frozenset[str] = frozenset(
    {"stringly unresolvable", "stringly armed", "stringly unresolvable node"}
)


# ── the emission rules, one graph each ───────────────────────────────────────────────────


def _two_node_builder() -> StateGraph[SentinelState]:
    """``plan_step`` → ``act_step`` → END, with nothing routed yet."""
    builder: StateGraph[SentinelState] = StateGraph(SentinelState)
    builder.add_node("plan_step", raiser("plan_step"))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge("act_step", END)
    return builder


#: Every hint form §6 licenses ``kind: send`` for, as callables — the ``build_send_forms_graph``
#: router set, named so a test can quantify over the same list the graph was built from.
SEND_ROUTERS: tuple[Callable[..., object], ...] = (
    route_send_bare,
    route_send_list,
    route_send_sequence,
    route_send_union,
    route_send_typing_union,
    route_send_optional,
    route_send_pep604,
)


def build_send_forms_graph() -> StateGraph[SentinelState]:
    """Every ``Send``-licensing hint form on one node, each with its own declared target.

    One router per form on ``plan_step``, so the classification is exercised per branch name and
    the ``(from, condition)`` group identity is what keeps the edges apart.
    """
    builder = _two_node_builder()
    for route in SEND_ROUTERS:
        builder.add_conditional_edges("plan_step", route, ["act_step"])
    return builder


def build_conditional_forms_graph() -> StateGraph[SentinelState]:
    """Every hint form §6 sends to ``conditional``, each declaring the same single target.

    ``route_literal`` declares its target through the hint alone — §6's second static source,
    which the substrate reads into ``BranchSpec.ends`` for a ``Literal`` and, verified on the
    pinned substrate, *not* for a ``Command[Literal[...]]``: that form supplies targets on the
    node surface (``StateNodeSpec.ends``), not on the router surface, so it is given an explicit
    ``path_map`` here and gets its targetless case in
    :func:`build_dynamic_command_router_graph`.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", route_literal)
    builder.add_conditional_edges("plan_step", route_str, ["act_step"])
    builder.add_conditional_edges("plan_step", route_command_literal, ["act_step"])
    builder.add_conditional_edges("plan_step", route_no_hint, ["act_step"])
    builder.add_conditional_edges("plan_step", route_none_hint, ["act_step"])
    return builder


def build_dynamic_command_router_graph() -> StateGraph[SentinelState]:
    """A ``Command[Literal[...]]``-hinted **router** with no ``path_map``: the ``dynamic`` form.

    Not a corner: the hint declares targets on the node surface and the author may reasonably
    expect it to do so here too, but ``BranchSpec.ends`` stays ``None`` (§6's three static
    sources, read against the pinned substrate), so there is nothing declared to route over.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", route_command_literal)
    return builder


def build_dynamic_send_hinted_graph() -> StateGraph[SentinelState]:
    """§6's bare-``Send`` map-reduce: a ``Send``-hinted router with no declared targets.

    "Classification licenses the kind only — emitting ``send`` edges additionally requires
    declared targets", and there are none, so this is the ``dynamic`` form (DEC-28) rather than a
    send template with an invented target.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", route_send_list)
    return builder


def build_relabelled_send_graph() -> StateGraph[SentinelState]:
    """A send-classified router whose ``path_map`` label is not its own target.

    The label has no carrier on a send template, so it is dropped with a warning — unlike the
    identity map a list declaration produces, where nothing is lost and nothing is warned.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", route_send_list, {"leg": "act_step"})
    return builder


def build_send_to_end_graph() -> StateGraph[SentinelState]:
    """A send-classified router declaring END: no carrier, since ``to`` is a node id.

    The other label is its own target, so the label-drop rule stays quiet and this fixture
    isolates the END rule.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges(
        "plan_step", route_send_bare, {"done": END, "act_step": "act_step"}
    )
    return builder


def build_codomain_distinct_graph() -> StateGraph[SentinelState]:
    """A ``Literal`` codomain declared *beside* a ``path_map`` — §6's codomain-capture case.

    The substrate gives ``path_map`` precedence, so the hint never reaches ``BranchSpec.ends``;
    §6 has extraction read it anyway and record it in provenance, never merged into ``path_map``.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", route_literal_wider, {"go": "act_step"})
    return builder


def build_async_send_router_graph() -> StateGraph[SentinelState]:
    """An ``async def`` router: the hint lives on ``afunc``, ``func`` being empty."""
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", route_async_send, ["act_step"])
    return builder


def build_lambda_send_router_graph() -> StateGraph[SentinelState]:
    """A router handed in as a ``RunnableLambda`` — one more wrapper for §6's walk to pass."""
    builder = _two_node_builder()
    # The substrate types the `path` argument as an async router; a `RunnableLambda` over a sync
    # one is an in-contract call it accepts, and it is the shape a user reaches for when they
    # want a router with a `with_config`/`with_retry` wrapper on it.
    builder.add_conditional_edges(
        "plan_step",
        RunnableLambda(route_send_list),  # type: ignore[arg-type]
        ["act_step"],
    )
    return builder


def build_node_destinations_send_graph() -> StateGraph[SentinelState]:
    """``StateNodeSpec.ends`` from ``destinations=`` on a ``Send``-hinted node function.

    The other surface §6 covers, and the one EX-02 emitted uniformly as ``conditional``: the
    node's *own* return hint is what classifies it, and there is no ``BranchSpec`` behind it, so
    the edge carries no ``condition``.
    """
    builder: StateGraph[SentinelState] = StateGraph(SentinelState)
    builder.add_node("plan_step", node_sends, destinations=("act_step",))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge("act_step", END)
    return builder


def build_stringly_annotated_graph() -> StateGraph[SentinelState]:
    """The string-annotation shapes a builder can hold: two resolvable hints.

    Evaluation is unavoidable here and that is the point — the raw annotations are strings, so
    §6's named mechanism is what reads them. Neither expression runs any user code, so this
    graph's extraction must leave both sentinel ledgers empty.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", futures.route_send_stringly, ["act_step"])
    builder.add_conditional_edges("plan_step", futures.route_literal_stringly, ["act_step"])
    return builder


def build_arming_annotation_graph() -> StateGraph[SentinelState]:
    """A router whose annotation expression **runs** — §1 rule 3's residue, as a graph.

    Kept apart from every other fixture precisely because its extraction is *expected* to run
    something: a test can then assert the trip here and its absence everywhere else, instead of
    a blanket "nothing ever ran" that would have to be weakened for this one shape.
    """
    builder = _two_node_builder()
    builder.add_conditional_edges("plan_step", futures.route_arming_hint, ["act_step"])
    return builder


def build_unevaluable_node_hint_graph() -> StateGraph[SentinelState]:
    """A **node** whose return hint cannot be evaluated, with ``destinations=`` declared.

    The one shape a real builder can hold on which §1 rule 3's degradation actually fires:
    ``add_node``'s own schema inference evaluates the hint, gets a ``NameError`` and carries on,
    so the node reaches extraction with a declared-but-unreadable return type. The edge must
    still be emitted, over the declared targets, at the conservative kind.
    """
    builder: StateGraph[SentinelState] = StateGraph(SentinelState)
    builder.add_node("plan_step", futures.node_unresolvable_hint, destinations=("act_step",))
    builder.add_node("act_step", raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge("act_step", END)
    return builder


#: Every §6 shape that extracts, as (name, factory) — joined to the WA-07 guarded child, so a
#: shape added here is a shape the never-invokes claim covers from that commit on.
ROUTING_BUILDERS: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "send_forms": build_send_forms_graph,
    "conditional_forms": build_conditional_forms_graph,
    "dynamic_send_hinted": build_dynamic_send_hinted_graph,
    "dynamic_command_router": build_dynamic_command_router_graph,
    "relabelled_send": build_relabelled_send_graph,
    "send_to_end": build_send_to_end_graph,
    "codomain_distinct": build_codomain_distinct_graph,
    "async_send": build_async_send_router_graph,
    "lambda_send": build_lambda_send_router_graph,
    "node_destinations_send": build_node_destinations_send_graph,
    "stringly_annotated": build_stringly_annotated_graph,
    "unevaluable_node_hint": build_unevaluable_node_hint_graph,
}

#: The one fixture whose extraction is expected to run an annotation expression (§1 rule 3),
#: kept out of :data:`ROUTING_BUILDERS` so the blanket "nothing ran" claim over that table stays
#: unqualified. Its own test is what covers it.
ARMING_BUILDERS: dict[str, Callable[[], StateGraph[SentinelState]]] = {
    "arming_annotation": build_arming_annotation_graph,
}
