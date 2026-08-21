"""The version-drift fixture set — VERSION-COMPAT §3 tests 1-6, committed for GOV-05.

Each entry in :data:`CASES` is one **live drift fixture**: the minimal workflow the §3 table
names for its test, paired with a golden canonical serialization and digest under
``tests/version_drift/golden/``. The suite (``tests/version_drift/test_version_drift.py``)
drives each fixture through ``gebra.extract()`` and holds the §3 golden-equality contract —
canonical core-IR bytes **byte-identical** to the committed golden, ``graph_version``
**string-equal** to the committed digest — beside each test's hard surface-shape
preconditions and its paired soft exact-set assertion.

**This module is deliberately self-contained.** It imports no other ``sentinel_*`` or
``conformance`` fixture module: those sets are other cards' evidence surfaces, and a shared
fixture edit must never be able to move a drift golden as a side effect (the same isolation
the conformance set states for itself).

**Version portability is the composition rule, not a per-case gate.** Every golden here must
hold byte-identically on every frozen VERSION-COMPAT §3 matrix cell and every tested Python —
a drift golden that legitimately moves with the substrate could not tell drift from schedule.
So the set is composed around EX-17's two bisected version-sensitive surfaces:

* no fixture touches the langgraph-1.2-only builder APIs (``set_node_defaults``,
  ``add_node(..., error_handler=...)``, ``timeout=``), and
* no fixture carries a ``BaseChatModel`` or ``bind()`` wrapper — a model's
  ``config_digest`` projects the *installed* core's ``model_fields``
  (INTROSPECTION-SPEC §7.4 (c)), which moves with core releases (§7.4 (e)), so a model
  carrier cannot sit under a cross-cell byte golden. This is the GOV-05 card note and the
  EX-17 → GOV-drift handoff, honored by composition; adding one later is a WA-03 event.

The node-spec ``metadata=`` kwarg is passed on the test-1 fixture (a §2 surface, present
across the range); ``cache_policy`` is asserted as a *field* of ``StateNodeSpec`` (the §3
row's ⊇ set) and never passed as a kwarg — the row's claim is about the spec's shape, and a
kwarg the older builders might route differently would put a portability bet inside a
fixture that exists to detect substrate movement, not to gamble on it.

**Never-invokes posture (WA-07).** Every node function and router here records itself in
:data:`TRIPPED` and then raises :class:`DriftSentinelError` — a ``BaseException`` subclass,
so no ``except Exception`` guard can swallow one silently. The suite asserts the ledger is
empty after every test and *fires* every body to prove the arming is live. Test 4
additionally calls ``compiled.get_graph(xray=True)`` — a substrate introspection call the
spec row itself names — under the same ledger: a substrate release whose drawing started
invoking node bodies would trip the sentinels and fail the run loudly. ``compile()`` is
graph construction, not execution (INTROSPECTION-SPEC §4), and happens only inside the
test-4 factories, never at import time. This suite adds **no extraction path** — it calls
``gebra.extract()`` and reads substrate attributes — so no new tripwire is owed under
WA-07's per-path rule; the arming here is a redundant guard on top of the per-path tripwire
suites, not their replacement.

Import safety: importing this module defines factories only — no graph is built, nothing is
compiled, no external service is contacted, and no API key is needed.

No ``from __future__ import annotations`` here, on purpose (the conformance set's rule,
inherited): §4 inference reads a node's *evaluated* parameter annotation, and the futures
form would turn every annotation in the module into a string — a different extraction
surface than the mainstream one these goldens pin.
"""

import operator
from dataclasses import dataclass
from typing import Annotated, Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

#: Every sentinel that was reached, recorded **before** it raises, so a raise something
#: swallowed is still visible. The suite clears and checks this per test.
TRIPPED: list[str] = []


class DriftSentinelError(BaseException):
    """Raised by any drift fixture body that gets invoked.

    ``BaseException`` so that an ``except Exception`` guard on an extraction path — or
    inside a substrate drawing routine — cannot swallow it into a warning: anything
    reaching a body here must fail the run.
    """


def _trip(label: str) -> Any:
    """Record ``label`` and raise — the body of every invokable thing in this module."""
    TRIPPED.append(label)
    raise DriftSentinelError(f"{label!r} was invoked — the drift suite must never run it")


# ── nodes-spec (§3 test 1) ───────────────────────────────────────────────────────────────


class BriefState(TypedDict):
    topic: str
    summary: str


def _summarize(state: BriefState) -> dict[str, str]:
    return _trip("nodes-spec.summarize")  # type: ignore[no-any-return]


def build_nodes_spec() -> StateGraph[BriefState]:
    """One plain node wearing ``metadata`` and a retry policy — the §3 row-1 fixture."""
    builder = StateGraph(BriefState)
    builder.add_node(
        "summarize",
        _summarize,
        metadata={"team": "governance"},
        retry_policy=RetryPolicy(max_attempts=3, retry_on=(ValueError,)),
    )
    builder.add_edge(START, "summarize")
    builder.add_edge("summarize", END)
    return builder


# ── branches (§3 test 2) ─────────────────────────────────────────────────────────────────


class TicketState(TypedDict):
    ticket: str
    queue: str


def _classify(state: TicketState) -> dict[str, str]:
    return _trip("branches.classify")  # type: ignore[no-any-return]


def _escalate(state: TicketState) -> dict[str, str]:
    return _trip("branches.escalate")  # type: ignore[no-any-return]


def _resolve(state: TicketState) -> dict[str, str]:
    return _trip("branches.resolve")  # type: ignore[no-any-return]


def route_ticket(state: TicketState) -> str:
    """The conditional router — its name is the edge's declared ``condition`` string."""
    return _trip("branches.route_ticket")  # type: ignore[no-any-return]


def build_branches() -> StateGraph[TicketState]:
    """One conditional edge with a ``path_map`` — the §3 row-2 fixture."""
    builder = StateGraph(TicketState)
    builder.add_node("classify", _classify)
    builder.add_node("escalate", _escalate)
    builder.add_node("resolve", _resolve)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route_ticket, {"hot": "escalate", "cold": "resolve"})
    builder.add_edge("escalate", END)
    builder.add_edge("resolve", END)
    return builder


# ── waiting-edges (§3 test 3) ────────────────────────────────────────────────────────────


class QuoteState(TypedDict):
    order: str
    quote: str


def _check_stock(state: QuoteState) -> dict[str, str]:
    return _trip("waiting-edges.check_stock")  # type: ignore[no-any-return]


def _check_price(state: QuoteState) -> dict[str, str]:
    return _trip("waiting-edges.check_price")  # type: ignore[no-any-return]


def build_waiting_edges() -> StateGraph[QuoteState]:
    """The multi-source join ``add_edge([a, b], END)`` — the §3 row-3 fixture, sentinel
    target and all: the join group must land in ``.waiting_edges``, never in ``.edges``."""
    builder = StateGraph(QuoteState)
    builder.add_node("check_stock", _check_stock)
    builder.add_node("check_price", _check_price)
    builder.add_edge(START, "check_stock")
    builder.add_edge(START, "check_price")
    builder.add_edge(["check_stock", "check_price"], END)
    return builder


# ── drawable-fidelity (§3 test 4) ────────────────────────────────────────────────────────


class EditorialState(TypedDict):
    draft: str
    verdict: str


def _polish(state: EditorialState) -> dict[str, str]:
    return _trip("drawable-fidelity.polish")  # type: ignore[no-any-return]


def _publish(state: EditorialState) -> dict[str, str]:
    return _trip("drawable-fidelity.publish")  # type: ignore[no-any-return]


def _draft_step(state: EditorialState) -> dict[str, str]:
    return _trip("drawable-fidelity.draft_step")  # type: ignore[no-any-return]


def _review(state: EditorialState) -> dict[str, str]:
    return _trip("drawable-fidelity.review")  # type: ignore[no-any-return]


def route_review(state: EditorialState) -> str:
    """The cycle-closing router: ``revise`` re-enters the loop, ``ship`` leaves it."""
    return _trip("drawable-fidelity.route_review")  # type: ignore[no-any-return]


def build_editorial_child() -> StateGraph[EditorialState]:
    """The subgraph's own builder — two linear nodes, exposed for the armed-control walk."""
    child = StateGraph(EditorialState)
    child.add_node("polish", _polish)
    child.add_node("publish", _publish)
    child.add_edge(START, "polish")
    child.add_edge("polish", "publish")
    child.add_edge("publish", END)
    return child


def build_drawable() -> StateGraph[EditorialState]:
    """Cycle + conditional + subgraph — the §3 row-4 canonical fixture, at builder level.

    The cycle is ``draft_step → review → (revise) → draft_step``; the conditional carries a
    ``path_map``; ``finalize`` is a compiled child graph, which ir 1.0 carries as its parent
    node only (DEC-19). ``compile()`` on the child is graph construction (INTROSPECTION-SPEC
    §4) and happens here, inside the factory — importing the module compiles nothing.
    """
    parent = StateGraph(EditorialState)
    parent.add_node("draft_step", _draft_step)
    parent.add_node("review", _review)
    parent.add_node("finalize", build_editorial_child().compile())
    parent.add_edge(START, "draft_step")
    parent.add_edge("draft_step", "review")
    parent.add_conditional_edges(
        "review", route_review, {"revise": "draft_step", "ship": "finalize"}
    )
    parent.add_edge("finalize", END)
    return parent


def build_drawable_compiled() -> Any:
    """The same fixture, compiled — the object the §3 row-4 drawing is taken from."""
    return build_drawable().compile()


# ── send-signature (§3 test 5) ───────────────────────────────────────────────────────────


class ItineraryState(TypedDict):
    legs: list[str]
    booked: Annotated[list[str], operator.add]


def _plan_legs(state: ItineraryState) -> dict[str, Any]:
    return _trip("send-signature.plan_legs")  # type: ignore[no-any-return]


def _book_leg(state: ItineraryState) -> dict[str, Any]:
    return _trip("send-signature.book_leg")  # type: ignore[no-any-return]


def _confirm(state: ItineraryState) -> dict[str, Any]:
    return _trip("send-signature.confirm")  # type: ignore[no-any-return]


def fan_out_legs(state: ItineraryState) -> list[Send]:
    """Hinted ``-> list[Send]`` with a declared target — §6 classifies the wiring ``send``."""
    return _trip("send-signature.fan_out_legs")  # type: ignore[no-any-return]


def build_send_signature() -> StateGraph[ItineraryState]:
    """A ``Send``-returning branch fanning out to a worker, then a join — map-reduce."""
    builder = StateGraph(ItineraryState)
    builder.add_node("plan_legs", _plan_legs)
    builder.add_node("book_leg", _book_leg)
    builder.add_node("confirm", _confirm)
    builder.add_edge(START, "plan_legs")
    builder.add_conditional_edges("plan_legs", fan_out_legs, ["book_leg"])
    builder.add_edge("book_leg", "confirm")
    builder.add_edge("confirm", END)
    return builder


# ── retry-policy (§3 test 6) ─────────────────────────────────────────────────────────────


class FetchState(TypedDict):
    job: str
    payload: str


def _fetch_with_backoff(state: FetchState) -> dict[str, str]:
    return _trip("retry-policy.fetch_with_backoff")  # type: ignore[no-any-return]


def build_retry_policy() -> StateGraph[FetchState]:
    """One node carrying a two-policy sequence — the §3 row-6 fixture.

    The substrate accepts the sequence (first-match semantics); ir 1.0 projects the first
    policy with the ``retry-policy-sequence-flattened`` envelope warning (DEC-18) — the
    golden pins the projection, and the warning rides outside hash scope.
    """
    builder = StateGraph(FetchState)
    builder.add_node(
        "fetch_with_backoff",
        _fetch_with_backoff,
        retry_policy=[
            RetryPolicy(max_attempts=2, retry_on=(ValueError,)),
            RetryPolicy(max_attempts=5, retry_on=(KeyError,)),
        ],
    )
    builder.add_edge(START, "fetch_with_backoff")
    builder.add_edge("fetch_with_backoff", END)
    return builder


# ── The registry ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftCase:
    """One live drift fixture: the §3 test it serves and its workflow factory."""

    test: str
    """The VERSION-COMPAT §3 test name this case's golden belongs to."""
    build: Any
    """Zero-argument factory for the object handed to ``extract()``. Never called at import."""


CASES: Final[dict[str, DriftCase]] = {
    "nodes-spec": DriftCase(test="test_drift_builder_nodes_spec_shape", build=build_nodes_spec),
    "branches": DriftCase(test="test_drift_builder_branches_shape", build=build_branches),
    "waiting-edges": DriftCase(
        test="test_drift_builder_edges_waiting_edges", build=build_waiting_edges
    ),
    "drawable-fidelity": DriftCase(
        test="test_drift_get_graph_drawable_fidelity", build=build_drawable
    ),
    "send-signature": DriftCase(test="test_drift_send_signature", build=build_send_signature),
    "retry-policy": DriftCase(test="test_drift_retry_policy_fields", build=build_retry_policy),
}
