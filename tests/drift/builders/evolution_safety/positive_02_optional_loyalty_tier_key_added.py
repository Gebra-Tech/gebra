"""Mini builder script for ``evolution-safety/positive-02-optional-loyalty-tier-key-added``.

The one **evolution pair** in the designated set, and therefore the one module carrying two
factories: an ``ir_before`` and an ``ir_after`` that differ by exactly the change the fixture is
about — an optional ``loyalty_tier`` key added to Σ and read by ``send_confirmation``.

Two scripts rather than one parametrized script, because the two IR blocks are two documents:
the ``before`` graph declares **no** input schema members at all (no key of its Σ is
``optional: true``) while the ``after`` graph declares exactly ``loyalty_tier``, so the
before/after difference lands in ``input_schema=`` as well as in Σ. A single factory taking a
flag would hide that in a branch; two factories put it side by side.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "evolution-safety/positive-02-optional-loyalty-tier-key-added"


class BookingStateBefore(TypedDict):
    """Σ before the change."""

    request: str
    flight_option: str
    booking_ref: str
    confirmation: str


class BookingStateAfter(TypedDict):
    """Σ after the change — one optional key more."""

    request: str
    flight_option: str
    booking_ref: str
    loyalty_tier: str
    confirmation: str


class NoInput(TypedDict):
    """The ``before`` graph's input schema: empty, so no key of Σ is a graph input."""


class LoyaltyInput(TypedDict):
    """The ``after`` graph's input schema — the fixture's one ``optional: true`` key."""

    loyalty_tier: str


@gebra.contract(pure=True, reads=[], writes=["request"])
def classify_request(state: BookingStateBefore) -> dict[str, Any]:
    trip("evolution-safety/positive-02.classify_request")


@gebra.contract(pure=True, reads=["request"], writes=["flight_option"])
def search_flights(state: BookingStateBefore) -> dict[str, Any]:
    trip("evolution-safety/positive-02.search_flights")


@gebra.effect("billable")
@gebra.idempotent(key="flight_option")
@gebra.contract(reads=["flight_option"], writes=["booking_ref"])
def book_flight(state: BookingStateBefore) -> dict[str, Any]:
    trip("evolution-safety/positive-02.book_flight")


@gebra.contract(effects=[], reads=["booking_ref"], writes=["confirmation"])
def send_confirmation_before(state: BookingStateBefore) -> dict[str, Any]:
    trip("evolution-safety/positive-02.send_confirmation_before")


@gebra.contract(effects=[], reads=["booking_ref", "loyalty_tier"], writes=["confirmation"])
def send_confirmation_after(state: BookingStateAfter) -> dict[str, Any]:
    trip("evolution-safety/positive-02.send_confirmation_after")


def build_before() -> Any:
    """classify → search → book → confirm, before the loyalty key exists."""
    builder = StateGraph(BookingStateBefore, input_schema=NoInput)
    builder.add_node("classify_request", classify_request)
    builder.add_node("search_flights", search_flights)
    builder.add_node("book_flight", book_flight)
    builder.add_node("send_confirmation", send_confirmation_before)
    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "search_flights")
    builder.add_edge("search_flights", "book_flight")
    builder.add_edge("book_flight", "send_confirmation")
    builder.add_edge("send_confirmation", END)
    return builder


def build_after() -> Any:
    """The same four nodes, with ``loyalty_tier`` in Σ and read by the confirmation node."""
    builder = StateGraph(BookingStateAfter, input_schema=LoyaltyInput)
    builder.add_node("classify_request", classify_request)
    builder.add_node("search_flights", search_flights)
    builder.add_node("book_flight", book_flight)
    builder.add_node("send_confirmation", send_confirmation_after)
    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "search_flights")
    builder.add_edge("search_flights", "book_flight")
    builder.add_edge("book_flight", "send_confirmation")
    builder.add_edge("send_confirmation", END)
    return builder
