"""Mini builder script for ``determinism-replay/positive-01-pinned-seed-zero-temp-classifier``.

Two constructs this pair adds: the object form of the determinism slot
(``deterministic: {seed: 42, temperature: 0}``) beside a two-tag ``effect`` list, and a Σ with
**no** graph-input key at all — ``input_schema=NoInput`` says the graph takes nothing from
outside, which is what the fixture's Σ (no ``optional: true`` anywhere) states and what its
``receive_request`` node, whose declared ``input`` is empty, is written for.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "determinism-replay/positive-01-pinned-seed-zero-temp-classifier"


class RequestState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    raw_request: str
    destination: str
    trip_dates: str
    itinerary: str


class NoInput(TypedDict):
    """The graph's input schema: empty, so no key of Σ is a graph input."""


@gebra.contract(pure=True, reads=[], writes=["raw_request"])
def receive_request(state: RequestState) -> dict[str, Any]:
    trip("determinism-replay/positive-01.receive_request")


@gebra.effect("network", "external")
@gebra.deterministic(seed=42, temperature=0)
@gebra.contract(reads=["raw_request"], writes=["destination", "trip_dates"])
def classify_request(state: RequestState) -> dict[str, Any]:
    trip("determinism-replay/positive-01.classify_request")


@gebra.contract(pure=True, reads=["destination", "trip_dates"], writes=["itinerary"])
def plan_itinerary(state: RequestState) -> dict[str, Any]:
    trip("determinism-replay/positive-01.plan_itinerary")


def build() -> Any:
    """receive → classify → plan."""
    builder = StateGraph(RequestState, input_schema=NoInput)
    builder.add_node("receive_request", receive_request)
    builder.add_node("classify_request", classify_request)
    builder.add_node("plan_itinerary", plan_itinerary)
    builder.add_edge(START, "receive_request")
    builder.add_edge("receive_request", "classify_request")
    builder.add_edge("classify_request", "plan_itinerary")
    builder.add_edge("plan_itinerary", END)
    return builder
