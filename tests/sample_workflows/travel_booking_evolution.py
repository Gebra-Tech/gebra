"""The travel-booking evolution sequence — SD-08's N ≥ 5 versions, with their expectations.

Brief D-11's W9 milestone evolves the TE-05 agent "through N ≥ 5 versions, including the
canonical breaking cases (read-key removal, termination-witness removal, effect-class
escalation) and safe extensions", and PD-006 R4 (owner-signed 2026-07-24) fixes what
"classified correctly" means for Phase 0: **structural V.S.F.E classes only** — every
version-pair diff yields exactly the expected S (topology) / F (node/contract) / E (state
schema) bump classes recorded with the scenario, the diff carries the deferred-P-12 marker,
and no output makes a safe/breaking claim (PHASE-0-DOD-CHECKLIST §S2). This module is that
sequence and that record: eight builder-level versions of the one agent, each a live
``StateGraph`` like ``tests/sample_workflows/travel_booking.py``'s v1, plus
:data:`EVOLUTION` — the expected label and bump class per stage, which
``tests/evolution/test_travel_booking_evolution.py`` holds the engines to.

**The sequence.** Each stage edits its predecessor and nothing is ever reverted, so between
any two stages the moved components are the union of the steps between them — which is what
lets the regression test assert every pair, not only neighbours::

    v1  1.0.0.0  the TE-05 baseline
    v2  1.0.0.1  E    Σ gains the optional graph-input key `seat_preference`
    v3  1.1.1.1  S,F  contracted node `join_waitlist`, a new `waitlist` label on
                      route_booking, and a widened finish set
    v4  1.2.1.1  S    a second `waitlist` label, on route_availability, to the existing node
    v5  1.2.1.2  E    Σ drops `itinerary`; two contracts still declare it
    v6  1.2.1.3  E    `availability` redeclared `list[str]`; four contracts still read it
    v7  1.2.2.3  F    `replan` loses its `variant` annotation — the witness carrier
    v8  1.2.3.3  F    `check_booking`'s effects gain `billable`

Stages v2–v4 are brief D-11's three safe-extension shapes in order — a new optional state
key, a new node, a new guarded edge. Stages v5–v8 are the three canonical breaking cases the
card names, with the read-key case in both of its spellings (removal *and* retype). The
exact sequence and the safe-extension choices are this card's ``decisions_to_implementer``;
the categories and the N ≥ 5 floor are the brief's.

**Why the evolved stages carry their own node and router functions.** The substrate merges
every ``TypedDict``-annotated callable parameter into the builder's channel set:
``StateGraph.add_node`` and ``add_conditional_edges`` both register the callable's evaluated
first-parameter annotation as a schema, and ``builder.channels`` — the source
INTROSPECTION-SPEC §3's state row names first — is the union over *all* registered schemas,
the two declared ones included. Measured on the pinned substrate while building this module:
reusing v1's ``TravelState``-annotated functions in a ``StateGraph(TravelStateV5)`` puts
``itinerary`` right back into Σ, so v5's removal would extract as no change at all. The
stages therefore differ **only by their declared schema pair**, and every body here takes
``state: Any`` — an annotation the substrate registers nothing for — with its
contract carried where a contract lives, in the decorators, byte-for-byte v1's where the
stage story says "unchanged" (the regression test's v1→v2 diff asserts exactly that: an
empty contracts delta across the function swap). The routers keep v1's ``__name__``s —
``route_availability`` and ``route_booking`` — because the extracted ``condition`` string is
the declared branch name, and the sequence's topology diffs must be about labels, never
about a renamed guard.

**What the breaking cases are structurally, stated where they are authored.**

* *Read-key removal (v5) / retype (v6).* Σ moves while the contracts that read the key stay
  exactly as they were — v5 keeps ``compile_itinerary``'s declared write of ``itinerary``
  and ``notify_traveler``'s declared read of it; v6 keeps the four declared reads of
  ``availability``. Both diffs are E alone: nothing about the topology or any contract
  changed. D-11's own witness example for this class is "removed key ``return_date`` still
  read by ``book_flight``".
* *Termination-witness removal (v7).* The ``variant`` slot leaves ``replan`` — the
  TERMINATION-WITNESS-SPEC §2.3 form-(c) carrier both of this graph's simple cycles run
  through, so after v7 the five-node SCC carries no witness in any of the three forms. A
  witness in form (c) is a node-annotation slot, so its removal is F (contract), not S —
  SD-02's disposition (``FIELD_COMPONENTS`` puts ``nodes[].annotations`` under F), shown
  at SD-05 and here on the live agent.
* *Effect-class escalation (v8).* ``check_booking`` goes from ``("network",)`` to
  ``("network", "billable")`` — entering the obligation trigger set PROPERTY-CATALOG-SPEC
  §6.3 fixes at exactly ``{billable, irreversible}`` — with no protection slot added, inside
  the booking cycle. An ``effect`` slot value moved, so the diff is F alone.

**What this module deliberately does not carry.** No safe/breaking vocabulary in any value
a test would render (stage names and summaries are structural); no per-version re-verify or
audit-export legs (those are SD-09's DoD scenario, per PD-006 R5's job description); and no
seeded-defect variants — SD-09's five defects are separate constructions over v1, not
members of this sequence.

**The eligibility boundary, measured and recorded for SD-09.** v1–v6 verify clean and
snapshot-eligible — including the two read-key cases, and for the catalog's own reason:
P-04 skips a read of a key outside Σ before any supply computation (PROPERTY-CATALOG-SPEC
§4.4 step 4 — "Σ-membership is P-03's finding", and P-03 is among SOW §8's eight non-wedge
validators), and no wedge property reads a key's declared type, so a Σ-side removal or
retype raises nothing in the wedge; the property that would grade those *pairs* is P-12,
deferred by the same §8, which is why they are diff-classification cases at all. v7 and v8
carry the catalog's FATAL
``cycle-without-termination-witness`` on the five-node SCC (the SOW §2 defect-1 condition),
and PROPERTY-CATALOG-SPEC §0.2 makes a FATAL alone suppress snapshot recording — so a
recorder handed an eligibility report stores v1–v6 and refuses v7–v8. The sequence is
therefore recorded the way this module's regression test records it: with **no eligibility
report handed to the recorder**, the engine's documented handed-none-records posture
(SD-03), which is what lets "every version is snapshotted and re-verified" (PD-006 R4) hold
with both halves true — all eight stored, all eight verified, and the two facts joined by
the caller rather than gated into contradiction. SD-09's evolve leg inherits exactly this
boundary, pinned by test rather than prose.

**Which level is the subject.** The builder, at every stage — PD-023 D4's choice, made for
v1 by TE-05 and inherited by the whole sequence: one level, so every version-pair diff is
about the definition and never about what compiling configured. Nothing here compiles.

**Never-invokes posture (WA-07).** Every node body and router in this module follows
``travel_booking.py``'s discipline exactly: each records itself in the **same**
:data:`~tests.sample_workflows.travel_booking.TRIPPED` ledger and raises
:class:`~tests.sample_workflows.travel_booking.TravelBookingSentinelError` (a
``BaseException`` subclass), so one ledger covers the whole fixture family and any body an
extraction or a test reaches fails the run. The arming test fires every body reachable from
any evolved stage's built graph — the superseded twins included. Importing this module
defines callables, TypedDicts and constants only: no graph is built at import time, nothing
is compiled, no connection is opened. :data:`TRIPPED` binds that shared ledger under this
module's own name, for the reason stated where it is bound.

No ``from __future__ import annotations`` here, on purpose, for the reason
``travel_booking.py`` states: the fixture family pins the mainstream evaluated-annotation
form. (In this module the bodies' parameters are ``Any``, which the substrate registers
nothing for whether evaluated or stringized — each stage's Σ is carried entirely by the
schema classes handed to ``StateGraph``.)
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

import gebra
from gebra.versioning import Component
from tests.sample_workflows import travel_booking as tb

__all__ = [
    "EVOLUTION",
    "TRIPPED",
    "EvolutionStage",
    "TravelRequestV2",
    "TravelStateV2",
    "TravelStateV5",
    "TravelStateV6",
    "build_travel_booking_v2",
    "build_travel_booking_v3",
    "build_travel_booking_v4",
    "build_travel_booking_v5",
    "build_travel_booking_v6",
    "build_travel_booking_v7",
    "build_travel_booking_v8",
    "check_booking_metered",
    "join_waitlist",
    "replan_unwitnessed",
]


#: The shared family ledger under this module's own name — the *same list object* as
#: :data:`tests.sample_workflows.travel_booking.TRIPPED`, not a second one, because
#: :func:`_trip` records into that list. Bound here for the reason
#: ``travel_booking_defects.py`` records at its own binding: the documentation harness's
#: fail-closed sweep (``tools/docs_examples.py``) asks each imported sample workflow for its
#: own ``TRIPPED`` and refuses a module that has none — correctly, since it cannot tell
#: "records elsewhere" from "records nowhere".
TRIPPED: Final[list[str]] = tb.TRIPPED


def _trip(label: str) -> Any:
    """Record ``label`` in the shared ledger and raise — one ledger for the whole family."""
    tb.TRIPPED.append(label)
    raise tb.TravelBookingSentinelError(f"{label!r} was invoked — nothing here may ever run")


# ── The evolved state schemas ─────────────────────────────────────────────────────────────
#
# TypedDict inheritance can only add keys (PEP 589 forbids overriding or removing), so the
# v2 schemas extend v1's and the v5/v6 schemas are full redeclarations.


class TravelStateV2(tb.TravelState):
    """Σ from v2 through v4: v1's eleven keys plus ``seat_preference``."""

    seat_preference: str


class TravelRequestV2(tb.TravelRequest):
    """The graph-input projection from v2 onward: the caller may also send a seat wish.

    Being in the input schema is what makes the new key extract ``optional: true``
    (INTROSPECTION-SPEC §3's state row under PD-021 D1) — D-11's "new optional state keys"
    safe-extension shape, landed as declared rather than asserted.
    """

    seat_preference: str


class TravelStateV5(TypedDict):
    """Σ at v5: ``itinerary`` is gone; every other key of v2's schema persists.

    The evolved builders register no schema beyond the declared pair (module docstring), so
    this declaration alone is the removal: ``compile_itinerary`` still declares
    ``writes=("itinerary",)`` and ``notify_traveler`` still declares
    ``reads=("itinerary", …)`` — the read-key-*removal* canonical case is exactly that the
    schema moved and the contracts did not.
    """

    request: str
    traveler_id: str
    booking_request_id: str
    replan_budget: int
    request_kind: str
    availability: str
    flight_id: str
    hotel_id: str
    booking_status: str
    confirmation: str
    seat_preference: str


class TravelStateV6(TypedDict):
    """Σ from v6 onward: ``availability`` is redeclared ``list[str]``.

    The read-key-*retype* canonical case: same key set as v5, one declared type moved, and
    the four contracts reading ``availability`` (``replan``, ``book_flight``, ``book_hotel``,
    ``join_waitlist``) are untouched. Extraction renders the parameterized form as the opaque
    type-name string ``"list[str]"`` (IR-SPEC §2.2 — no type algebra in ir 1.0), so the E
    delta reports a retype and nothing else.
    """

    request: str
    traveler_id: str
    booking_request_id: str
    replan_budget: int
    request_kind: str
    availability: list[str]
    flight_id: str
    hotel_id: str
    booking_status: str
    confirmation: str
    seat_preference: str


# ── The evolved bodies ────────────────────────────────────────────────────────────────────
#
# Contracts byte-for-byte v1's (the regression test's v1→v2 diff holds the whole set equal
# by asserting an empty contracts delta); parameters schema-neutral (module docstring); and
# every body records itself in the shared ledger before raising. The two exceptions with
# stories of their own — `replan_unwitnessed`, `check_booking_metered` — sit at the end.


@gebra.contract(
    reads=("request",),
    writes=("request_kind",),
    effects=("external", "network"),
)
@gebra.deterministic(seed=42, temperature=0.0)
def classify_request(state: Any) -> dict[str, str]:
    """v1's ``classify_request`` — same contract, same coherent pinned-determinism claim."""
    return _trip("travel-booking-evolution.classify_request")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("request_kind", "traveler_id"),
    writes=("availability",),
    effects=("network",),
)
def availability_check(state: Any) -> dict[str, str]:
    """v1's ``availability_check`` — the ``retry_policy`` rides the ``add_node`` call."""
    return _trip("travel-booking-evolution.availability_check")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "replan_budget"),
    writes=("request_kind", "replan_budget"),
    effects=("external", "network"),
)
@gebra.variant(
    key="replan_budget",
    measure="replan_budget strictly decreases each lap (one replanning attempt consumed)",
)
def replan(state: Any) -> dict[str, Any]:
    """v1's ``replan`` — the P-02 form-(c) witness carrier, measure string verbatim."""
    return _trip("travel-booking-evolution.replan")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "booking_request_id"),
    writes=("flight_id",),
    effects=("irreversible", "billable", "network"),
)
@gebra.idempotent(key="booking_request_id")
def book_flight(state: Any) -> dict[str, str]:
    """v1's ``book_flight`` — keyed idempotency bound to a declared read, unchanged."""
    return _trip("travel-booking-evolution.book_flight")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "booking_request_id"),
    writes=("hotel_id",),
    effects=("billable", "network"),
)
@gebra.compensation(hook="release_hotel_hold")
def book_hotel(state: Any) -> dict[str, str]:
    """v1's ``book_hotel`` — the compensation-hook protection form, unchanged."""
    return _trip("travel-booking-evolution.book_hotel")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("flight_id", "hotel_id"),
    writes=("booking_status",),
    effects=("network",),
)
def check_booking(state: Any) -> dict[str, str]:
    """v1's ``check_booking`` — the confirmation poll before v8 meters it."""
    return _trip("travel-booking-evolution.check_booking")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("flight_id", "hotel_id", "booking_status"),
    writes=("itinerary",),
    effects=(),
)
@gebra.deterministic
def compile_itinerary(state: Any) -> dict[str, str]:
    """v1's ``compile_itinerary`` — writes the key v5's schema drops, contract untouched."""
    return _trip("travel-booking-evolution.compile_itinerary")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("itinerary", "traveler_id"),
    writes=("confirmation",),
    effects=("external", "network"),
)
def notify_traveler(state: Any) -> dict[str, str]:
    """v1's ``notify_traveler`` — reads the key v5's schema drops, contract untouched."""
    return _trip("travel-booking-evolution.notify_traveler")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("hotel_id", "booking_request_id"),
    writes=("booking_status",),
    effects=("external", "network"),
)
def release_hotel_hold(state: Any) -> dict[str, str]:
    """v1's ``release_hotel_hold`` — ``book_hotel``'s hook, a declared node throughout."""
    return _trip("travel-booking-evolution.release_hotel_hold")  # type: ignore[no-any-return]


def route_availability(state: Any) -> str:
    """v1's availability router — the ``__name__`` is the extracted ``condition`` string."""
    return _trip("travel-booking-evolution.route_availability")  # type: ignore[no-any-return]


def route_booking(state: Any) -> str:
    """v1's booking router — same ``__name__``, whatever labels a stage's ``path_map`` adds."""
    return _trip("travel-booking-evolution.route_booking")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("traveler_id", "availability"),
    writes=("booking_status",),
    effects=("external", "network"),
)
def join_waitlist(state: Any) -> dict[str, str]:
    """Put the traveller on the supplier's waitlist — v3's new node.

    Declares all three slots explicitly, like every node in this family (leaving one to
    ANNOTATION-API-SPEC §4 inference would demote the fixture's grades and cost the
    strict-mode warning-free bar — the reason ``travel_booking.py`` records). Both reads are
    supplied on every path that reaches it: ``traveler_id`` is a graph input and
    ``availability`` is written by ``availability_check``, which every route to this node
    passes through. Wired straight to END, so it joins no cycle and needs no witness;
    ``external``/``network`` create no P-06 obligation (PROPERTY-CATALOG-SPEC §6.3 fixes the
    trigger set at ``{billable, irreversible}``).
    """
    return _trip("travel-booking-evolution.join_waitlist")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "replan_budget"),
    writes=("request_kind", "replan_budget"),
    effects=("external", "network"),
)
def replan_unwitnessed(state: Any) -> dict[str, Any]:
    """``replan`` with the ``variant`` annotation removed — v7's carrier, witness gone.

    The contract tuple is byte-for-byte :func:`replan`'s (same reads, writes and effects),
    so the only annotation-level difference between v6 and v7 is the missing ``variant``
    slot: the diff must report exactly one changed contract with exactly one departed slot,
    and F alone. The node id stays ``"replan"`` — the *node* persists; its witness leaves.

    What the removal means is TERMINATION-WITNESS-SPEC §1.1's boundary read in reverse: v6
    *attested* a bound and v7 attests none, so P-02 has no witness to find in any of the
    three forms — form (a) needs a guard grammar string no live extraction carries here,
    form (b) needs ``runtime.recursion_limit``, absent at builder level, and form (c) was
    this slot. Witness presence is the only claim in reach either way.
    """
    return _trip("travel-booking-evolution.replan_unwitnessed")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("flight_id", "hotel_id"),
    writes=("booking_status",),
    effects=("network", "billable"),
)
def check_booking_metered(state: Any) -> dict[str, str]:
    """``check_booking`` after the supplier starts charging per confirmation call — v8.

    The effect tuple gains ``billable`` and keeps ``network``: an escalation *into*
    PROPERTY-CATALOG-SPEC §6.3's obligation trigger set, on a node inside the booking cycle,
    with no protection slot added beside it. Reads and writes are byte-for-byte
    :func:`check_booking`'s, so the diff is one changed contract, one changed slot, F alone.
    """
    return _trip("travel-booking-evolution.check_booking_metered")  # type: ignore[no-any-return]


# ── The builders, v2 through v8 ───────────────────────────────────────────────────────────
#
# Each is written out in full, like v1, so that "what changed between two stages" is the
# diff of two adjacent functions — the module is the sequence's source of truth and the
# regression test pins every delta, so a copy that drifted would fail loudly rather than
# silently.


def build_travel_booking_v2() -> Any:
    """v2 — Σ gains the optional graph-input key ``seat_preference``. Expected: E, 1.0.0.1.

    The wiring and every contract are v1's; the only declared difference is the schema pair
    (:class:`TravelStateV2`, :class:`TravelRequestV2`). Nothing reads or writes the new key
    yet — a key the caller may send and nothing consumes, which is D-11's "new optional
    state keys" extension at its smallest.
    """
    builder = StateGraph(TravelStateV2, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)

    return builder


def build_travel_booking_v3() -> Any:
    """v3 — the contracted ``join_waitlist`` node lands, wired. Expected: S+F, 1.1.1.1.

    Three authored edits over v2, one new-node extension: the node itself (F: a contract
    arrives), ``route_booking``'s ``path_map`` gains ``"waitlist"`` targeting it (S: a new
    conditional edge under the same router, hence the same ``condition`` string), and
    ``join_waitlist → END`` (S: the finish set widens to three). D-11's "new nodes" and "new
    guarded edges" shapes land together because an unwired node would be a P-01 finding, not
    an extension.
    """
    builder = StateGraph(TravelStateV2, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)
    builder.add_node("join_waitlist", join_waitlist)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
            "waitlist": "join_waitlist",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)
    builder.add_edge("join_waitlist", END)

    return builder


def build_travel_booking_v4() -> Any:
    """v4 — a ``waitlist`` label on ``route_availability`` too. Expected: S, 1.2.1.1.

    One authored edit over v3: the availability router's ``path_map`` gains
    ``"waitlist" → join_waitlist``, so a sold-out search can waitlist without first
    attempting a booking. Both endpoints already exist and no contract and no schema moves —
    the guarded-edge extension in isolation, which is what makes this stage's class S alone
    rather than v3's S+F.
    """
    builder = StateGraph(TravelStateV2, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)
    builder.add_node("join_waitlist", join_waitlist)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan", "waitlist": "join_waitlist"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
            "waitlist": "join_waitlist",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)
    builder.add_edge("join_waitlist", END)

    return builder


def build_travel_booking_v5() -> Any:
    """v5 — Σ drops ``itinerary``; the contracts do not. Expected: E, 1.2.1.2.

    One authored edit over v4: the state schema becomes :class:`TravelStateV5`. The nodes
    are v4's own objects, so ``compile_itinerary`` still declares the write and
    ``notify_traveler`` still declares the read — the read-key-removal canonical case. It
    is a *pair* fact for the deferred P-12, not the DoD's P-04 seed: that defect is an
    unsupplied read of a key still in Σ, while a departed key's read is skipped by P-04
    itself (PROPERTY-CATALOG-SPEC §4.4 step 4 — Σ-membership is P-03's finding, non-wedge
    per SOW §8).
    """
    builder = StateGraph(TravelStateV5, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)
    builder.add_node("join_waitlist", join_waitlist)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan", "waitlist": "join_waitlist"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
            "waitlist": "join_waitlist",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)
    builder.add_edge("join_waitlist", END)

    return builder


def build_travel_booking_v6() -> Any:
    """v6 — ``availability`` is redeclared ``list[str]``. Expected: E, 1.2.1.3.

    One authored edit over v5: the state schema becomes :class:`TravelStateV6`. Same key
    set, one declared type moved, contracts untouched — the read-key-retype canonical case.
    """
    builder = StateGraph(TravelStateV6, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)
    builder.add_node("join_waitlist", join_waitlist)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan", "waitlist": "join_waitlist"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
            "waitlist": "join_waitlist",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)
    builder.add_edge("join_waitlist", END)

    return builder


def build_travel_booking_v7() -> Any:
    """v7 — the witness leaves its carrier. Expected: F, 1.2.2.3.

    One authored edit over v6: the ``"replan"`` node is built from
    :func:`replan_unwitnessed`, whose contract is :func:`replan`'s minus the ``variant``
    slot. The topology and Σ are untouched; the SCC both cycles share is now carrier-less.
    """
    builder = StateGraph(TravelStateV6, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan_unwitnessed)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)
    builder.add_node("join_waitlist", join_waitlist)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan", "waitlist": "join_waitlist"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
            "waitlist": "join_waitlist",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)
    builder.add_edge("join_waitlist", END)

    return builder


def build_travel_booking_v8() -> Any:
    """v8 — the confirmation endpoint is metered. Expected: F, 1.2.3.3.

    One authored edit over v7: the ``"check_booking"`` node is built from
    :func:`check_booking_metered`, whose effect tuple gains ``billable``. Everything else,
    v7's witness removal included, persists.
    """
    builder = StateGraph(TravelStateV6, input_schema=TravelRequestV2)

    builder.add_node("classify_request", classify_request)
    builder.add_node(
        "availability_check",
        availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan_unwitnessed)
    builder.add_node("book_flight", book_flight)
    builder.add_node("book_hotel", book_hotel)
    builder.add_node("check_booking", check_booking_metered)
    builder.add_node("compile_itinerary", compile_itinerary)
    builder.add_node("notify_traveler", notify_traveler)
    builder.add_node("release_hotel_hold", release_hotel_hold)
    builder.add_node("join_waitlist", join_waitlist)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        route_availability,
        {"available": "book_flight", "revise": "replan", "waitlist": "join_waitlist"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        route_booking,
        {
            "confirmed": "compile_itinerary",
            "revise": "replan",
            "abort": "release_hotel_hold",
            "waitlist": "join_waitlist",
        },
    )
    builder.add_edge("compile_itinerary", "notify_traveler")
    builder.add_edge("notify_traveler", END)
    builder.add_edge("release_hotel_hold", END)
    builder.add_edge("join_waitlist", END)

    return builder


# ── The recorded expectations ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvolutionStage:
    """One version of the sequence, with the expectations the regression test enforces.

    Attributes:
        name: A stable, structural stage name (no category vocabulary — the categories live
            in the builders' docstrings as brief citations, never in rendered values).
        build: The stage's builder — a fresh, independent ``StateGraph`` per call, so a
            consumer re-running the sequence never shares live objects between stages.
        expected_version: The V.S.F.E label ``gebra.snapshot`` must assign this stage when
            the sequence is recorded in order into one store, v1 first.
        expected_bump: The bump class the diff against the *previous* stage must derive —
            empty for v1, which has no predecessor. PD-006 R4's "expected S/F/E classes
            recorded with the scenario" is this member.
        summary: One structural line for a human reading a table.
    """

    name: str
    build: Callable[[], Any]
    expected_version: str
    expected_bump: frozenset[Component]
    summary: str


#: The sequence, in evolution order. ``EVOLUTION[0]`` is TE-05's v1 baseline; every later
#: stage edits its predecessor and no edit is ever reverted, so for any i < j the moved
#: components between stages i and j are the union of the steps between them.
EVOLUTION: Final[tuple[EvolutionStage, ...]] = (
    EvolutionStage(
        name="v1-baseline",
        build=tb.build_travel_booking_agent,
        expected_version="1.0.0.0",
        expected_bump=frozenset(),
        summary="the TE-05 baseline: nine nodes, two routers, the witnessed booking cycle",
    ),
    EvolutionStage(
        name="v2-seat-preference",
        build=build_travel_booking_v2,
        expected_version="1.0.0.1",
        expected_bump=frozenset({Component.E}),
        summary="Σ gains the optional graph-input key seat_preference; nothing consumes it",
    ),
    EvolutionStage(
        name="v3-waitlist-node",
        build=build_travel_booking_v3,
        expected_version="1.1.1.1",
        expected_bump=frozenset({Component.S, Component.F}),
        summary="contracted join_waitlist node, a waitlist label on route_booking, END wiring",
    ),
    EvolutionStage(
        name="v4-waitlist-shortcut",
        build=build_travel_booking_v4,
        expected_version="1.2.1.1",
        expected_bump=frozenset({Component.S}),
        summary="route_availability gains a waitlist label to the existing join_waitlist node",
    ),
    EvolutionStage(
        name="v5-itinerary-dropped",
        build=build_travel_booking_v5,
        expected_version="1.2.1.2",
        expected_bump=frozenset({Component.E}),
        summary="Σ drops itinerary while two contracts still declare the write and the read",
    ),
    EvolutionStage(
        name="v6-availability-retyped",
        build=build_travel_booking_v6,
        expected_version="1.2.1.3",
        expected_bump=frozenset({Component.E}),
        summary="availability is redeclared list[str] while four contracts still read it",
    ),
    EvolutionStage(
        name="v7-witness-removed",
        build=build_travel_booking_v7,
        expected_version="1.2.2.3",
        expected_bump=frozenset({Component.F}),
        summary="replan loses its variant annotation, the carrier both cycles run through",
    ),
    EvolutionStage(
        name="v8-billable-confirmation",
        build=build_travel_booking_v8,
        expected_version="1.2.3.3",
        expected_bump=frozenset({Component.F}),
        summary="check_booking's effects gain billable, entering the P-06 trigger set",
    ),
)
