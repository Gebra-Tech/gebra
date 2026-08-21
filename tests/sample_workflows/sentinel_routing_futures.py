"""Routing declarations whose annotations are **strings** — ``from __future__ import annotations``.

A separate module because the future import is per-module: everything here has string
annotations, which is exactly the branch of :mod:`gebra.extraction.routing` that has to call
``typing.get_type_hints()`` and therefore *evaluate* something. INTROSPECTION-SPEC §1 rule 3
licenses that evaluation and rule 4 names it as a hazard needing a tripwire; this module is the
fixture half of that tripwire.

**One substrate fact frames all of it, and it is not gebra's** (verified on the pinned
substrate): LangGraph evaluates a routing callable's annotations *itself*, while the graph is
being built — ``StateGraph.add_conditional_edges`` calls ``get_type_hints`` through
``BranchSpec.from_path``'s schema inference, and ``add_node`` does the same for a node's input
schema. So an annotation expression that **raises** cannot reach extraction at all: the builder
refuses to accept the router or the node in the first place, and no ``StateGraph`` carrying one
can exist. The shapes below are therefore split by what a builder can actually hold.

Reachable through a real builder:

* :func:`route_send_stringly` / :func:`route_literal_stringly` — resolvable string hints.
  Evaluation is *necessary* here: the raw annotation is the string ``"list[Send]"``, and reading
  it without evaluating would mean not reading it at all.
* :func:`node_unresolvable_hint` — a string hint naming nothing, on the **node** surface, which
  the substrate's own inference tolerates (it evaluates and moves on). §1 rule 3's degradation
  rule is what extraction owes it: "degrade any evaluation failure to an unknown hint (never
  abort, never execute repair logic)".
* :func:`route_arming_hint` — an annotation expression that **succeeds** while recording that it
  ran. This is §1 rule 3's residue with nothing hidden: "arbitrary annotation expressions run at
  extraction time", and here is one running. It is a *declared* residue, not a defect — the rule
  states it, §6 names ``get_type_hints`` as the mechanism, and the alternative is not reading
  declared hints at all.

Not reachable through a real builder, and covered at the unit level instead:

* :func:`route_armed_annotation` — an annotation expression that raises. The substrate stops it
  first (above), so extraction's degradation on it is defence in depth; it is still tested,
  because "the substrate happens to check first" is not a property gebra controls.
* :func:`route_unresolvable` — the same shape on the router surface, where the substrate refuses
  it outright.

Importing this module evaluates nothing (that is what the future import buys) and builds no
graph.
"""

from __future__ import annotations

from typing import Literal

from langgraph.types import Send

from tests.sample_workflows.sentinel_graph import SentinelExecutedError, SentinelState

__all__ = [
    "TRIPPED",
    "arm_annotation",
    "arming_hint",
    "node_unresolvable_hint",
    "route_armed_annotation",
    "route_arming_hint",
    "route_literal_stringly",
    "route_send_stringly",
    "route_unresolvable",
]

#: Every sentinel that was reached, recorded **before** it raises, so a ``try: … except: pass``
#: anywhere on the path cannot hide the trip (the ``sentinel_digests`` convention).
TRIPPED: list[str] = []


def arm_annotation() -> type:
    """Record, then raise — an annotation expression that runs code and fails when evaluated."""
    TRIPPED.append("annotation-expression-raised")
    raise SentinelExecutedError("an annotation expression was evaluated")


def arming_hint() -> object:
    """Record, then answer ``list[Send]`` — an annotation expression that runs and succeeds.

    The honest shape of §1 rule 3's residue: nothing raises, so nothing is refused anywhere on
    the path, and the only evidence that user code ran is this record.
    """
    TRIPPED.append("annotation-expression-ran")
    return list[Send]


def route_send_stringly(state: SentinelState) -> list[Send]:
    """`-> list[Send]` as a string, resolvable in this module's globals: classifies `send`."""
    TRIPPED.append("route_send_stringly")
    raise SentinelExecutedError("'route_send_stringly' was invoked")


def route_literal_stringly(state: SentinelState) -> Literal["act_step"]:
    """`-> Literal["act_step"]` as a string: classifies `conditional`, codomain readable."""
    TRIPPED.append("route_literal_stringly")
    raise SentinelExecutedError("'route_literal_stringly' was invoked")


def route_arming_hint(state: SentinelState) -> arming_hint():  # type: ignore[valid-type]
    """A string hint that is a call which succeeds: `list[Send]`, with the call recorded."""
    TRIPPED.append("route_arming_hint")
    raise SentinelExecutedError("'route_arming_hint' was invoked")


def node_unresolvable_hint(state: SentinelState) -> NoSuchNameAnywhere:  # type: ignore[name-defined] # noqa: F821
    """A node whose string hint names nothing: `NameError`, degraded to no hint."""
    TRIPPED.append("node_unresolvable_hint")
    raise SentinelExecutedError("'node_unresolvable_hint' was invoked")


def route_unresolvable(state: SentinelState) -> NoSuchNameAnywhere:  # type: ignore[name-defined] # noqa: F821
    """The same unresolvable hint on the router surface, which the substrate refuses outright."""
    TRIPPED.append("route_unresolvable")
    raise SentinelExecutedError("'route_unresolvable' was invoked")


def route_armed_annotation(state: SentinelState) -> arm_annotation():  # type: ignore[valid-type]
    """A string hint that is a call which raises — unattachable, covered at the unit level."""
    TRIPPED.append("route_armed_annotation")
    raise SentinelExecutedError("'route_armed_annotation' was invoked")
