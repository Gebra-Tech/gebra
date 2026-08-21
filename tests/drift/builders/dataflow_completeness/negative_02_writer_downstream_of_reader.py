"""Mini builder script for ``dataflow-completeness/negative-02-writer-downstream-of-reader``.

A **negative** fixture reproduced faithfully: ``notify_traveler`` reads ``itinerary_url`` that
its downstream ``publish_itinerary`` writes. A drift pair reproduces the fixture's IR whatever
the fixture's verdict is — the pair asserts corpus↔extractor coherence, never that the graph is
well designed, and a corpus whose negatives could not be built would be a corpus of shapes no
extractor ever sees.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "dataflow-completeness/negative-02-writer-downstream-of-reader"


class NotifyState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    itinerary: str
    itinerary_url: str
    notify_status: str


class NotifyInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["itinerary"])
def compile_itinerary(state: NotifyState) -> dict[str, Any]:
    trip("dataflow-completeness/negative-02.compile_itinerary")


@gebra.effect("network")
@gebra.idempotent(key="itinerary")
@gebra.contract(reads=["itinerary", "itinerary_url"], writes=["notify_status"])
def notify_traveler(state: NotifyState) -> dict[str, Any]:
    trip("dataflow-completeness/negative-02.notify_traveler")


@gebra.effect("network")
@gebra.idempotent(key="itinerary")
@gebra.contract(reads=["itinerary"], writes=["itinerary_url"])
def publish_itinerary(state: NotifyState) -> dict[str, Any]:
    trip("dataflow-completeness/negative-02.publish_itinerary")


def build() -> Any:
    """compile → notify → publish, with the URL written after it is read."""
    builder = StateGraph(NotifyState, input_schema=NotifyInput)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("publish_itinerary", publish_itinerary)
    builder.add_edge(START, "compile_itinerary")
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", "publish_itinerary")
    builder.add_edge("publish_itinerary", END)
    return builder
