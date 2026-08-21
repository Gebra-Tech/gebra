"""Mini builder script for ``determinism-replay/negative-01-seedless-deterministic-llm-classifier``.

The **bare** determinism declaration (``deterministic: true``) beside an ``external`` effect —
the fixture's P-08 defect, reproduced as authored. ``compose_response`` declares ``effects=[]``:
its fixture node carries neither ``effect`` nor ``pure``, which is a declaration of nothing on
that slot rather than an invitation to infer one.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "determinism-replay/negative-01-seedless-deterministic-llm-classifier"


class MessageState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    message: str
    intent: str
    response: str


class NoInput(TypedDict):
    """The graph's input schema: empty, so no key of Σ is a graph input."""


@gebra.contract(pure=True, reads=[], writes=["message"])
def receive_message(state: MessageState) -> dict[str, Any]:
    trip("determinism-replay/negative-01.receive_message")


@gebra.effect("network", "external")
@gebra.deterministic
@gebra.contract(reads=["message"], writes=["intent"])
def classify_intent(state: MessageState) -> dict[str, Any]:
    trip("determinism-replay/negative-01.classify_intent")


@gebra.contract(effects=[], reads=["intent"], writes=["response"])
def compose_response(state: MessageState) -> dict[str, Any]:
    trip("determinism-replay/negative-01.compose_response")


def build() -> Any:
    """receive → classify → compose."""
    builder = StateGraph(MessageState, input_schema=NoInput)
    builder.add_node("receive_message", receive_message)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("compose_response", compose_response)
    builder.add_edge(START, "receive_message")
    builder.add_edge("receive_message", "classify_intent")
    builder.add_edge("classify_intent", "compose_response")
    builder.add_edge("compose_response", END)
    return builder
