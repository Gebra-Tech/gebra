"""Mini builder script for ``signature-soundness/negative-01-read-key-absent-from-sigma``.

Two constructs this pair adds. The first is a Σ value that is **not** a builtin scalar —
``user: UserProfile`` — which pins the closed type renderer: the class is named through
``type.__qualname__`` and never through ``repr``. The second is the fixture's P-03 defect
itself: ``send_confirmation`` declares a read of ``user_email``, which is not a key of Σ, and
extraction carries the declaration as written rather than dropping or repairing it.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "signature-soundness/negative-01-read-key-absent-from-sigma"


class UserProfile:
    """The Σ value type of the ``user`` key — named in the IR, never constructed here."""


class ConfirmState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    request: str
    user: UserProfile
    booking_id: str
    confirmation: str


class ConfirmInput(TypedDict):
    """The graph's input schema — exactly the fixture's two ``optional: true`` keys."""

    request: str
    user: UserProfile


@gebra.effect("network")
@gebra.idempotent(key="request")
@gebra.contract(reads=["request"], writes=["booking_id"])
def lookup_booking(state: ConfirmState) -> dict[str, Any]:
    trip("signature-soundness/negative-01.lookup_booking")


@gebra.effect("network")
@gebra.contract(reads=["booking_id", "user_email"], writes=["confirmation"])
def send_confirmation(state: ConfirmState) -> dict[str, Any]:
    trip("signature-soundness/negative-01.send_confirmation")


def build() -> Any:
    """lookup → confirm."""
    builder = StateGraph(ConfirmState, input_schema=ConfirmInput)
    builder.add_node("lookup_booking", lookup_booking)
    builder.add_node("send_confirmation", send_confirmation)
    builder.add_edge(START, "lookup_booking")
    builder.add_edge("lookup_booking", "send_confirmation")
    builder.add_edge("send_confirmation", END)
    return builder
