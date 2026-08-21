"""Mini builder script for ``parallel-safety/positive-01-reducer-guarded-parallel-enrichment``.

Two concurrent writers of one key, guarded by a reducer. Its twin —
``negative-01-reducerless-shared-notes-fanout`` — is the *same topology and the same contracts*
with the reducer removed, so the two pairs together pin the reducer's presence in the extracted
Σ rather than merely its absence being tolerated.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "parallel-safety/positive-01-reducer-guarded-parallel-enrichment"


class TripState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    trip_context: str
    notes: Annotated[list, operator.add]  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    itinerary: str


class TripInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["trip_context"])
def plan_trip(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/positive-01.plan_trip")


@gebra.contract(pure=True, reads=["trip_context"], writes=["notes"])
def check_weather(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/positive-01.check_weather")


@gebra.contract(pure=True, reads=["trip_context"], writes=["notes"])
def check_calendar(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/positive-01.check_calendar")


@gebra.contract(pure=True, reads=["trip_context", "notes"], writes=["itinerary"])
def compose_itinerary(state: TripState) -> dict[str, Any]:
    trip("parallel-safety/positive-01.compose_itinerary")


def build() -> Any:
    """plan → {weather, calendar} → compose."""
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
