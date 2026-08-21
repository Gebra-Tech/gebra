"""Mini builder script for ``dataflow-completeness/positive-01-linear-itinerary-pipeline``.

A linear four-node itinerary pipeline. The construct this pair adds to the set is a bare
``list`` Σ value beside the ``str`` ones, and a node whose declared ``input`` names two keys.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "dataflow-completeness/positive-01-linear-itinerary-pipeline"


class ItineraryState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    search_query: str
    flight_options: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    selected_flight: str
    itinerary: str


class ItineraryInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["search_query"])
def parse_request(state: ItineraryState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-01.parse_request")


@gebra.effect("network")
@gebra.idempotent(key="search_query")
@gebra.contract(reads=["search_query"], writes=["flight_options"])
def search_flights(state: ItineraryState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-01.search_flights")


@gebra.contract(pure=True, reads=["flight_options"], writes=["selected_flight"])
def select_flight(state: ItineraryState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-01.select_flight")


@gebra.contract(pure=True, reads=["selected_flight", "request"], writes=["itinerary"])
def draft_itinerary(state: ItineraryState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-01.draft_itinerary")


def build() -> Any:
    """parse → search → select → draft."""
    builder = StateGraph(ItineraryState, input_schema=ItineraryInput)
    builder.add_node("parse_request", parse_request)
    builder.add_node("search_flights", search_flights)
    builder.add_node("select_flight", select_flight)
    builder.add_node("draft_itinerary", draft_itinerary)
    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", "search_flights")
    builder.add_edge("search_flights", "select_flight")
    builder.add_edge("select_flight", "draft_itinerary")
    builder.add_edge("draft_itinerary", END)
    return builder
