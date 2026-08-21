"""Mini builder script for ``determinism-replay/positive-02-pure-fare-normalizer``.

The construct this pair adds: one node carrying ``pure`` and ``deterministic`` together — two
independent slots on the same contract, which the §1 consistency rules allow and which a
resolver that treated purity as implying determinism (or the reverse) would collapse.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "determinism-replay/positive-02-pure-fare-normalizer"


class FareState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    route: str
    raw_quotes: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    normalized_quotes: list  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    best_offer: str


class FareInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    route: str


@gebra.effect("network")
@gebra.idempotent(key="route")
@gebra.contract(reads=["route"], writes=["raw_quotes"])
def request_quotes(state: FareState) -> dict[str, Any]:
    trip("determinism-replay/positive-02.request_quotes")


@gebra.deterministic
@gebra.contract(pure=True, reads=["raw_quotes"], writes=["normalized_quotes"])
def normalize_fares(state: FareState) -> dict[str, Any]:
    trip("determinism-replay/positive-02.normalize_fares")


@gebra.contract(pure=True, reads=["normalized_quotes"], writes=["best_offer"])
def select_offer(state: FareState) -> dict[str, Any]:
    trip("determinism-replay/positive-02.select_offer")


def build() -> Any:
    """request → normalize → select."""
    builder = StateGraph(FareState, input_schema=FareInput)
    builder.add_node("request_quotes", request_quotes)
    builder.add_node("normalize_fares", normalize_fares)
    builder.add_node("select_offer", select_offer)
    builder.add_edge(START, "request_quotes")
    builder.add_edge("request_quotes", "normalize_fares")
    builder.add_edge("normalize_fares", "select_offer")
    builder.add_edge("select_offer", END)
    return builder
