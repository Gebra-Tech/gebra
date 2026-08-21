"""Mini builder script for ``parallel-safety/negative-02-send-fanout-reducerless-findings``.

The one **send-edge** pair in the designated set, and the reason it can be one is a distinction
INTROSPECTION-SPEC §6 draws between the two surfaces a `send` edge reaches the IR from. A
``BranchSpec`` — an ``add_conditional_edges`` router — has a declared branch *name*, and the edge
carries it as ``condition``. ``StateNodeSpec.ends``, from ``destinations=`` on a ``Send``-hinted
node function, has no ``BranchSpec`` behind it and therefore no name, so the edge carries **no**
``condition`` (``gebra.extraction.builder`` emits it with ``condition=None``; pinned by
``tests/extraction/test_routing.py::test_a_node_hinted_send_classifies_its_declared_destinations``).
That is exactly the shape this fixture declares, so the second surface is the one the script uses.

**No ``from __future__ import annotations`` here, on purpose.** §6 classifies the edge from the
node function's own *evaluated* return hint, and the futures form would make every annotation in
this module a string — a different, degraded read, which is the same reason
``tests/sample_workflows/conformance.py`` and ``sentinel_routing.py`` both omit it. Every other
script in this package declares its contracts in full, so no hint of theirs is ever read; this
one's is load-bearing.
"""

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "parallel-safety/negative-02-send-fanout-reducerless-findings"


class FanoutState(TypedDict):
    """Σ — the whole state schema the fixture declares, with ``findings`` unreduced."""

    request: str
    destinations: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    findings: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    report: str


class FanoutInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["destinations"])
def plan_destinations(state: FanoutState) -> list[Send]:
    """The fan-out node. Its ``-> list[Send]`` hint is what makes its edge ``kind: send``."""
    trip("parallel-safety/negative-02.plan_destinations")


@gebra.contract(pure=True, reads=["destinations"], writes=["findings"])
def research_destination(state: FanoutState) -> dict[str, Any]:
    trip("parallel-safety/negative-02.research_destination")


@gebra.contract(pure=True, reads=["findings"], writes=["report"])
def compile_report(state: FanoutState) -> dict[str, Any]:
    trip("parallel-safety/negative-02.compile_report")


def build() -> Any:
    """plan --send--> research → compile."""
    builder = StateGraph(FanoutState, input_schema=FanoutInput)
    builder.add_node("plan_destinations", plan_destinations, destinations=("research_destination",))
    builder.add_node("research_destination", research_destination)
    builder.add_node("compile_report", compile_report)
    builder.add_edge(START, "plan_destinations")
    builder.add_edge("research_destination", "compile_report")
    builder.add_edge("compile_report", END)
    return builder
