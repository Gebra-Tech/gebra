"""Mini builder script for ``signature-soundness/negative-03-args-schema-type-mismatch``.

The construct this pair adds: the ``args_schema`` slot — a JSON Schema object carried into the
IR and into the digest verbatim. The fixture's P-03 defect is inside it (``passenger_count`` is
``int`` in Σ and ``"string"`` in the schema), so the pair also holds the extractor to carrying
the object **as declared** rather than reconciling it against Σ.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "signature-soundness/negative-03-args-schema-type-mismatch"

#: The fixture's ``args_schema`` block, verbatim — JSON data, never a pydantic model.
BOOK_FLIGHT_ARGS: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "itinerary": {"type": "string"},
        "passenger_count": {"type": "string"},
    },
}


class TravelState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    passenger_count: int
    itinerary: str
    booking_id: str
    confirmation: str


class TravelInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["passenger_count", "itinerary"])
def collect_travel_details(state: TravelState) -> dict[str, Any]:
    trip("signature-soundness/negative-03.collect_travel_details")


@gebra.effect("irreversible", "billable")
@gebra.idempotent(key="itinerary")
@gebra.contract(
    reads=["itinerary", "passenger_count"],
    writes=["booking_id"],
    args_schema=BOOK_FLIGHT_ARGS,
)
def book_flight(state: TravelState) -> dict[str, Any]:
    trip("signature-soundness/negative-03.book_flight")


@gebra.effect("network")
@gebra.contract(reads=["booking_id"], writes=["confirmation"])
def send_confirmation(state: TravelState) -> dict[str, Any]:
    trip("signature-soundness/negative-03.send_confirmation")


def build() -> Any:
    """collect → book → confirm."""
    builder = StateGraph(TravelState, input_schema=TravelInput)
    builder.add_node("collect_travel_details", collect_travel_details)
    builder.add_node("book_flight", book_flight)
    builder.add_node("send_confirmation", send_confirmation)
    builder.add_edge(START, "collect_travel_details")
    builder.add_edge("collect_travel_details", "book_flight")
    builder.add_edge("book_flight", "send_confirmation")
    builder.add_edge("send_confirmation", END)
    return builder
