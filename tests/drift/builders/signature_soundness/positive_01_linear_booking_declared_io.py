"""Mini builder script for ``signature-soundness/positive-01-linear-booking-declared-io``.

A three-node booking chain whose every read and write is declared. The construct this pair adds:
a two-tag ``effect`` list (``irreversible``, ``billable``) with a keyed ``idempotent`` beside it,
and a node carrying ``effect`` with no idempotence at all.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "signature-soundness/positive-01-linear-booking-declared-io"


class BookingState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    itinerary: str
    booking_id: str
    confirmation: str


class BookingInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    request: str


@gebra.contract(pure=True, reads=["request"], writes=["itinerary"])
def parse_request(state: BookingState) -> dict[str, Any]:
    trip("signature-soundness/positive-01.parse_request")


@gebra.effect("irreversible", "billable")
@gebra.idempotent(key="itinerary")
@gebra.contract(reads=["itinerary"], writes=["booking_id"])
def book_flight(state: BookingState) -> dict[str, Any]:
    trip("signature-soundness/positive-01.book_flight")


@gebra.effect("network")
@gebra.contract(reads=["booking_id"], writes=["confirmation"])
def send_confirmation(state: BookingState) -> dict[str, Any]:
    trip("signature-soundness/positive-01.send_confirmation")


def build() -> Any:
    """parse → book → confirm."""
    builder = StateGraph(BookingState, input_schema=BookingInput)
    builder.add_node("parse_request", parse_request)
    builder.add_node("book_flight", book_flight)
    builder.add_node("send_confirmation", send_confirmation)
    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", "book_flight")
    builder.add_edge("book_flight", "send_confirmation")
    builder.add_edge("send_confirmation", END)
    return builder
