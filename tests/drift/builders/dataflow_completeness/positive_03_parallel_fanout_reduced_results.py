"""Mini builder script for ``dataflow-completeness/positive-03-parallel-fanout-reduced-results``.

A fan-out/fan-in diamond whose shared key carries a reducer. Two constructs this pair adds:
the ``Annotated[list, operator.add]`` Σ value — the reducer is *named* during Σ extraction and
never called — and a topology with two edges out of one node and two into another.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "dataflow-completeness/positive-03-parallel-fanout-reduced-results"


class SearchState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    search_plan: str
    results: Annotated[list, operator.add]  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    ranked: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing


class SearchInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["search_plan"])
def plan_search(state: SearchState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-03.plan_search")


@gebra.effect("network")
@gebra.idempotent(key="search_plan")
@gebra.contract(reads=["search_plan"], writes=["results"])
def search_flights(state: SearchState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-03.search_flights")


@gebra.effect("network")
@gebra.idempotent(key="search_plan")
@gebra.contract(reads=["search_plan"], writes=["results"])
def search_hotels(state: SearchState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-03.search_hotels")


@gebra.contract(pure=True, reads=["results", "request"], writes=["ranked"])
def rank_options(state: SearchState) -> dict[str, Any]:
    trip("dataflow-completeness/positive-03.rank_options")


def build() -> Any:
    """plan → {flights, hotels} → rank."""
    builder = StateGraph(SearchState, input_schema=SearchInput)
    builder.add_node("plan_search", plan_search)
    builder.add_node("search_flights", search_flights)
    builder.add_node("search_hotels", search_hotels)
    builder.add_node("rank_options", rank_options)
    builder.add_edge(START, "plan_search")
    builder.add_edge("plan_search", "search_flights")
    builder.add_edge("plan_search", "search_hotels")
    builder.add_edge("search_flights", "rank_options")
    builder.add_edge("search_hotels", "rank_options")
    builder.add_edge("rank_options", END)
    return builder
