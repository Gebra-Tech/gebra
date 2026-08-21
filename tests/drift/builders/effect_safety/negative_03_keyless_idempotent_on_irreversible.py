"""Mini builder script for ``effect-safety/negative-03-keyless-idempotent-on-irreversible``.

The construct this pair adds: the **bare** idempotence declaration (``idempotent: true``, no
key) on a node whose effects are ``irreversible`` and ``billable`` — the fixture's P-06 defect.
``@gebra.idempotent`` bare and ``@gebra.idempotent(key=…)`` are two different IR values and this
pair pins the first, since a resolver that normalized one into the other would move the digest.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "effect-safety/negative-03-keyless-idempotent-on-irreversible"


class DepositState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    rental_quote: str
    payment_method: str
    deposit_ref: str
    receipt: str


class DepositInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    rental_quote: str


@gebra.contract(pure=True, reads=["rental_quote"], writes=["payment_method"])
def collect_payment_method(state: DepositState) -> dict[str, Any]:
    trip("effect-safety/negative-03.collect_payment_method")


@gebra.effect("irreversible", "billable")
@gebra.idempotent
@gebra.contract(reads=["payment_method"], writes=["deposit_ref"])
def charge_deposit(state: DepositState) -> dict[str, Any]:
    trip("effect-safety/negative-03.charge_deposit")


@gebra.contract(effects=[], reads=["deposit_ref"], writes=["receipt"])
def issue_receipt(state: DepositState) -> dict[str, Any]:
    trip("effect-safety/negative-03.issue_receipt")


def build() -> Any:
    """collect → charge → receipt."""
    builder = StateGraph(DepositState, input_schema=DepositInput)
    builder.add_node("collect_payment_method", collect_payment_method)
    builder.add_node("charge_deposit", charge_deposit)
    builder.add_node("issue_receipt", issue_receipt)
    builder.add_edge(START, "collect_payment_method")
    builder.add_edge("collect_payment_method", "charge_deposit")
    builder.add_edge("charge_deposit", "issue_receipt")
    builder.add_edge("issue_receipt", END)
    return builder
