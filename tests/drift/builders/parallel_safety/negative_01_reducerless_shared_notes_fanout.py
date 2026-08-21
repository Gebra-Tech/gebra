"""Mini builder script for ``parallel-safety/negative-01-reducerless-shared-notes-fanout``.

The reducerless twin of ``positive-01-reducer-guarded-parallel-enrichment``: same four nodes,
same four edges, same contracts, and ``notes`` declared as a bare ``list``. The two pairs differ
in exactly one Σ value, so between them they hold the extractor to *emitting* a declared reducer
and to *not inventing* one.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "parallel-safety/negative-01-reducerless-shared-notes-fanout"


class TripState(TypedDict):
    """Σ — the whole state schema the fixture declares, with ``notes`` unreduced."""

    request: str
    trip_context: str
    notes: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    itinerary: str


class TripInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["trip_context"])
def plan_trip(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/negative-01.plan_trip")


@gebra.contract(pure=True, reads=["trip_context"], writes=["notes"])
def check_weather(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/negative-01.check_weather")


@gebra.contract(pure=True, reads=["trip_context"], writes=["notes"])
def check_calendar(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/negative-01.check_calendar")


@gebra.contract(pure=True, reads=["trip_context", "notes"], writes=["itinerary"])
def compose_itinerary(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/negative-01.compose_itinerary")


def build() -> Any:
    """plan → {weather, calendar} → compose, with no reducer on the shared key."""
    builder = StateGraph(TripState, input_schema=TripInput)
    builder.add_node("plan_trip", plan_trip)
    builder.add_node("check_weather", check_weather)
    builder.add_node("check_calendar", check_calendar)
    builder.add_node("compose_itinerary", compose_itinerary)
    builder.add_edge(START, "plan_trip")
    builder.add_edge("plan_trip", "check_weather")
    builder.add_edge("plan_trip", "check_calendar")
    builder.add_edge("check_weather", "compose_itinerary")
    builder.add_edge("check_calendar", "compose_itinerary")
    builder.add_edge("compose_itinerary", END)
    return builder
