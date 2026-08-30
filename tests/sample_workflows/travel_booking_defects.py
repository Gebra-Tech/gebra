"""The five seeded-defect variants of the travel-booking agent — SD-09's constructions.

SOW §2 criterion 1 names five defects; PD-006 R1 (owner-signed 2026-07-24, lifted verbatim
into PHASE-0-DOD-CHECKLIST §C1) freezes what each must be caught *as*: the named property
failing with the expected condition ID at the seeded locus, gating exit 1 — for defect 3
under the per-property strict promotion, with the stored record still warning/heuristic.
Construction details are this card's latitude **within that table**; this module is those
constructions, each a builder-level variant of the TE-05 v1 agent
(``tests/sample_workflows/travel_booking.py``) carrying exactly one seeded defect, plus
:data:`DEFECTS` — the per-defect expectations ``tests/dod/`` holds the harness to.

The five variants, each one edit over v1:

1. **Cycle without a termination witness (P-02).** ``replan`` — the TERMINATION-WITNESS-SPEC
   §2.3 form-(c) carrier both of v1's simple cycles run through — loses its ``variant``
   annotation. The residual is the whole five-node SCC with no witness in any of the three
   forms: the catalog's FATAL ``cycle-without-termination-witness``
   (PROPERTY-CATALOG-SPEC §2.2's failure class, whose quoted instance is this same booking
   cycle under its tutorial spellings).
2. **Unsafe retry around ``book_flight`` (P-06).** ``book_flight`` — ``irreversible`` and
   ``billable``, PROPERTY-CATALOG-SPEC §6.2's own failure example — loses its
   ``@gebra.idempotent(key="booking_request_id")`` protection. The node is a conditional
   re-entry target inside the booking SCC (the ``available`` label), which is §6.4's
   structural retry region, so the finding is the ERROR
   ``unprotected-effect-in-retry-region`` anchored on ``book_flight`` — the first of the two
   condition IDs the C1 table admits for this defect.
3. **False determinism claim on an LLM node (P-08).** ``classify_request`` keeps its
   ``external``/``network`` effects but its claim degrades from the coherent object form to
   ``@gebra.deterministic(seed=42)`` — seed pinned, ``temperature`` unpinned — which is
   PROPERTY-CATALOG-SPEC §8.2's second canonical incoherence:
   ``deterministic-llm-temperature-unpinned``, WARNING/HEURISTIC always (§8). The catch is
   R2's: the finding is present at the node either way, and the run gates exit 1 under the
   ``determinism-replay`` per-property promotion while the record keeps
   ``severity: warning`` and ``claim_class: heuristic``.
4. **A node reads state no upstream node supplies (P-04).** ``route_availability`` gains an
   ``express`` label straight to ``notify_traveler`` — the PROPERTY-CATALOG-SPEC §4.2
   topology edit re-spelled onto this graph (v1's module docstring hands this variant the
   target choice, since v1 carries no ``booking_id``). On the express path nothing writes
   ``itinerary``, and ``notify_traveler`` declares the read: FATAL
   ``read-key-never-written-on-path`` at the ``(notify_traveler, itinerary)`` locus.
5. **Unsafe parallel fan-out (P-01/P-06 at Phase-0 level).** The serial bookings are
   replaced by a dispatcher and a fanned-out worker: ``dispatch_bookings`` routes through a
   ``Send``-hinted router (INTROSPECTION-SPEC §6 — the declared return-type hint licenses
   ``kind: send``; the list-form declared targets keep it warning-free per PD-044 D3) to
   ``book_leg``, which is ``billable`` with no protection. The conditional re-entry into the
   SCC reaches the worker through the send edge — §6.4's send closure — so the finding is
   the ERROR ``unprotected-effect-in-retry-region`` anchored on ``book_leg`` with
   ``fanout: send`` evidence: the ``mixed/09`` reference pattern PD-006 R1's rider names,
   re-authored as a live graph. Both condition ID and property are RATIFIED wedge entries —
   no RESERVED or PROPOSED string is emitted or required (the rider's constraint) — and the
   locus is distinct from defect 2's, as the rider requires.

**What the variants deliberately hold fixed.** Every variant keeps v1's declared schema pair
(``StateGraph(TravelState, input_schema=TravelRequest)``) — the PD-021 D1 narrowing that
makes P-04 non-vacuous — v1's router ``__name__``s (the extracted ``condition`` strings),
and v1's contracts byte-for-byte everywhere the defect story says "unchanged". The DoD
harness holds each variant to that by diffing it against v1 and pinning the delta to the
seeded edit, and by asserting the named property is the *only* wedge property that moves
(defect 5's construction swaps two nodes for two, so its topology delta is larger, but its
verify delta is still exactly the one finding).

**Why the changed bodies are twins with ``state: Any``.** The substrate registers every
TypedDict-annotated callable parameter as a schema and unions all registered schemas into
``builder.channels`` — the evolution module measured it — so a variant body annotated with a
schema would put schema identity where only the seeded edit should be. The twins register
nothing; Σ is carried entirely by the declared pair, and the unchanged nodes are v1's own
functions, so their contracts cannot drift from v1's.

**Never-invokes posture (WA-07).** Every twin records itself in the **same**
:data:`~tests.sample_workflows.travel_booking.TRIPPED` ledger as the rest of the family and
raises :class:`~tests.sample_workflows.travel_booking.TravelBookingSentinelError` (a
``BaseException`` subclass — no ``except Exception`` on an extraction path can swallow one).
``tests/dod/test_dod_guard.py`` fires every body reachable from any variant's built graph —
the reused v1 bodies included — and re-runs the whole five-variant extract → verify pipeline
in a fresh interpreter where name resolution, connection opening, socket construction and
``StateGraph.compile`` all raise. Importing this module defines callables and constants
only: no graph is built at import time, nothing is compiled, no connection is opened.

No ``from __future__ import annotations`` here, on purpose, for the reason
``travel_booking.py`` states — and with an extra stake in this module: defect 5's
classification *is* the evaluated return-type hint of :func:`route_legs`
(``typing.get_type_hints``, INTROSPECTION-SPEC §6), so this file pins the mainstream
evaluated form on the one surface where the hint is load-bearing.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

import gebra
from gebra.verify import ConditionId, PropertySlug
from tests.sample_workflows import travel_booking as tb

__all__ = [
    "DEFECTS",
    "TRIPPED",
    "DefectVariant",
    "book_flight_unprotected",
    "book_leg",
    "build_defect_1_unwitnessed_cycle",
    "build_defect_2_unprotected_retry",
    "build_defect_3_false_determinism",
    "build_defect_4_unsupplied_read",
    "build_defect_5_fanout",
    "classify_request_temperature_unpinned",
    "dispatch_bookings",
    "replan_unwitnessed",
    "route_legs",
]


#: The shared family ledger under this module's own name — the *same list object* as
#: :data:`tests.sample_workflows.travel_booking.TRIPPED`, not a second one, because
#: :func:`_trip` records into that list. It is bound here because a sweep that asks each
#: imported sample workflow for its own ``TRIPPED`` (the documentation harness's fail-closed
#: sweep, ``tools/docs_examples.py``) otherwise reads this module as keeping no ledger and
#: refuses it — correctly, since it cannot tell "records elsewhere" from "records nowhere".
TRIPPED: Final[list[str]] = tb.TRIPPED


def _trip(label: str) -> Any:
    """Record ``label`` in the shared family ledger and raise — every twin's body."""
    tb.TRIPPED.append(label)
    raise tb.TravelBookingSentinelError(f"{label!r} was invoked — nothing here may ever run")


# ── The twins — v1's contracts byte-for-byte, minus exactly the seeded slot ──────────────


@gebra.contract(
    reads=("availability", "replan_budget"),
    writes=("request_kind", "replan_budget"),
    effects=("external", "network"),
)
def replan_unwitnessed(state: Any) -> dict[str, Any]:
    """Defect 1's carrier: v1's ``replan`` contract with the ``variant`` slot gone.

    The one-annotation edit v1's module docstring names as "the same failure *class* as
    PROPERTY-CATALOG-SPEC §2.2 … and the DoD's defect 1": with the form-(c) carrier
    undeclared, no cycle through the five-node SCC carries a witness in any of
    TERMINATION-WITNESS-SPEC §2's three forms. What P-02 then reports is witness *absence*
    (T-W-SPEC §1.1's boundary) — a fact about the declaration, never about whether a run
    halts.
    """
    return _trip("travel-booking-defects.replan_unwitnessed")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "booking_request_id"),
    writes=("flight_id",),
    effects=("irreversible", "billable", "network"),
)
def book_flight_unprotected(state: Any) -> dict[str, str]:
    """Defect 2's node: v1's ``book_flight`` with ``@gebra.idempotent`` dropped.

    PROPERTY-CATALOG-SPEC §6.2's failure example in its own words — this node,
    ``irreversible`` + ``billable``, inside the booking cycle, "with nothing protecting it".
    The declared read of ``booking_request_id`` stays: the defect is the missing protection
    slot, not a contract edit, so extraction stays warning-free (the
    ``IDEMPOTENT_KEY_NOT_IN_INPUT`` hazard v1's docstring records needs a keyed declaration
    to trip, and there is none here).
    """
    return _trip("travel-booking-defects.book_flight_unprotected")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("request",),
    writes=("request_kind",),
    effects=("external", "network"),
)
@gebra.deterministic(seed=42)
def classify_request_temperature_unpinned(state: Any) -> dict[str, str]:
    """Defect 3's node: v1's ``classify_request`` claim minus its ``temperature`` pin.

    The object form with ``seed`` pinned and ``temperature`` unpinned on a node whose
    effects include ``external`` — PROPERTY-CATALOG-SPEC §8.2's incoherence for exactly this
    shape, ``deterministic-llm-temperature-unpinned``. §8 fixes every P-08 condition at
    WARNING/HEURISTIC always, which is why the C1 catch for this defect is R2's strict
    promotion rather than a severity: the gate moves, the record never does.
    """
    return _trip("travel-booking-defects.classify_request_temperature_unpinned")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability",),
    writes=(),
    effects=(),
)
def dispatch_bookings(state: Any) -> dict[str, str]:
    """Defect 5's dispatcher: plans the booking legs the router fans out.

    Declares all three slots explicitly — the empty tuples occupy ``output`` and ``effect``
    (ANNOTATION-API-SPEC §3 counts a slot set when it is not ``None``), keeping the D-011
    conservative default and its ``contract-defaulted`` demotion out, the
    ``compile_itinerary`` precedent.
    """
    return _trip("travel-booking-defects.dispatch_bookings")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "booking_request_id"),
    writes=("flight_id", "hotel_id"),
    effects=("billable", "network"),
)
def book_leg(state: Any) -> dict[str, str]:
    """Defect 5's worker: one booking leg, ``billable``, deliberately unprotected.

    The ``mixed/09`` worker shape (``book_segment``: billable, no ``idempotent``, no
    ``compensation``, no ``retry_policy``) re-authored onto this agent. It writes both
    booking keys so the seeded defect is the fan-out safety alone — every downstream read
    (``check_booking``, ``release_hotel_hold``) stays supplied and P-04 stays clean.
    """
    return _trip("travel-booking-defects.book_leg")  # type: ignore[no-any-return]


def route_legs(state: Any) -> list[Send]:
    """Defect 5's fan-out router — the declared ``Send`` hint is the classification.

    INTROSPECTION-SPEC §6: extraction classifies a routing declaration as ``kind: send`` iff
    a declared return-type hint licenses it, read via ``typing.get_type_hints()`` and never
    via body inspection; the body here records itself and raises like every other sentinel.
    The router's ``__name__`` becomes the send edges' ``condition`` string (PD-044 D1).
    """
    return _trip("travel-booking-defects.route_legs")  # type: ignore[no-any-return]


# ── The five variant builders — v1's wiring with exactly the seeded edit ─────────────────


def _base_builder() -> Any:
    """v1's declared schema pair — every variant's starting point.

    ``input_schema=TravelRequest`` is the PD-021 D1 narrowing v1 takes; without it every key
    of Σ extracts ``optional: true`` and defect 4 would be uncatchable — the ruling makes
    the declared ``input_schema=`` the condition for the seeded P-04 defect to be catchable
    at all, and v1's module docstring carries its application (including the SD-08/SD-09
    attribution wrinkle, which binds either way).
    """
    return StateGraph(tb.TravelState, input_schema=tb.TravelRequest)


def build_defect_1_unwitnessed_cycle() -> Any:
    """v1 with :func:`replan_unwitnessed` in ``replan``'s place — defect 1 (P-02).

    Topology, Σ and every other contract are v1's; the only moved content is the departed
    ``variant`` slot. Expected: FATAL ``cycle-without-termination-witness`` anchored on the
    residual five-node SCC; exit 1; snapshot eligibility withdrawn (PROPERTY-CATALOG-SPEC
    §0.2 — a FATAL alone suppresses recording).
    """
    builder = _base_builder()

    builder.add_node("classify_request", tb.classify_request)
    builder.add_node(
        "availability_check",
        tb.availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", replan_unwitnessed)
    builder.add_node("book_flight", tb.book_flight)
    builder.add_node("book_hotel", tb.book_hotel)
    builder.add_node("check_booking", tb.check_booking)
    builder.add_node("compile_itinerary", tb.compile_itinerary)
    builder.add_node("notify_traveler", tb.notify_traveler)
    builder.add_node("release_hotel_hold", tb.release_hotel_hold)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        tb.route_availability,
        {"available": "book_flight", "revise": "replan"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        tb.route_booking,
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


def build_defect_2_unprotected_retry() -> Any:
    """v1 with :func:`book_flight_unprotected` in ``book_flight``'s place — defect 2 (P-06).

    ``book_flight`` is a conditional re-entry target inside the SCC (the ``available``
    label), so §6.4's structural arm makes its region *retry* rather than plain cycle — the
    C1 table's primary condition ID for this defect. ``book_hotel``'s compensation and the
    witness carrier are untouched, so the ERROR at ``book_flight`` is the run's only
    finding. ERROR blocks the gate (exit 1) but withdraws no snapshot eligibility — §0.2
    reserves that to FATAL — which the harness asserts rather than assumes.
    """
    builder = _base_builder()

    builder.add_node("classify_request", tb.classify_request)
    builder.add_node(
        "availability_check",
        tb.availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", tb.replan)
    builder.add_node("book_flight", book_flight_unprotected)
    builder.add_node("book_hotel", tb.book_hotel)
    builder.add_node("check_booking", tb.check_booking)
    builder.add_node("compile_itinerary", tb.compile_itinerary)
    builder.add_node("notify_traveler", tb.notify_traveler)
    builder.add_node("release_hotel_hold", tb.release_hotel_hold)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        tb.route_availability,
        {"available": "book_flight", "revise": "replan"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        tb.route_booking,
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


def build_defect_3_false_determinism() -> Any:
    """v1 with :func:`classify_request_temperature_unpinned` — defect 3 (P-08).

    Everything else is v1's, so the default-policy run stays exit 0 (``pass-with-notes``)
    with the WARNING finding present at the node — and flips to exit 1 exactly under the
    ``determinism-replay`` per-property promotion, the R2 catch.
    """
    builder = _base_builder()

    builder.add_node("classify_request", classify_request_temperature_unpinned)
    builder.add_node(
        "availability_check",
        tb.availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", tb.replan)
    builder.add_node("book_flight", tb.book_flight)
    builder.add_node("book_hotel", tb.book_hotel)
    builder.add_node("check_booking", tb.check_booking)
    builder.add_node("compile_itinerary", tb.compile_itinerary)
    builder.add_node("notify_traveler", tb.notify_traveler)
    builder.add_node("release_hotel_hold", tb.release_hotel_hold)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        tb.route_availability,
        {"available": "book_flight", "revise": "replan"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        tb.route_booking,
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


def build_defect_4_unsupplied_read() -> Any:
    """v1 with an ``express`` label from availability straight to notification — defect 4.

    The §4.2 topology edit: the new label skips every node that writes ``itinerary``, and
    ``notify_traveler`` declares the read, so P-04's path analysis reports the FATAL
    ``read-key-never-written-on-path`` at that ``(node, key)`` locus. Bodies, contracts and
    Σ are all v1's — the router function too, so the ``condition`` string never moves; the
    seeded edit is one ``path_map`` entry.
    """
    builder = _base_builder()

    builder.add_node("classify_request", tb.classify_request)
    builder.add_node(
        "availability_check",
        tb.availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", tb.replan)
    builder.add_node("book_flight", tb.book_flight)
    builder.add_node("book_hotel", tb.book_hotel)
    builder.add_node("check_booking", tb.check_booking)
    builder.add_node("compile_itinerary", tb.compile_itinerary)
    builder.add_node("notify_traveler", tb.notify_traveler)
    builder.add_node("release_hotel_hold", tb.release_hotel_hold)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        tb.route_availability,
        {
            "available": "book_flight",
            "revise": "replan",
            "express": "notify_traveler",
        },
    )
    builder.add_edge("replan", "availability_check")
    builder.add_edge("book_flight", "book_hotel")
    builder.add_edge("book_hotel", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        tb.route_booking,
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


def build_defect_5_fanout() -> Any:
    """The parallel-booking variant: a ``Send`` fan-out with an unprotected billable worker.

    Defect 5 — SOW §2 c.1's "unsafe parallel fan-out", caught at Phase-0 level via the
    wedge's topology + effect checks. The serial ``book_flight → book_hotel`` chain becomes
    ``dispatch_bookings --route_legs--> book_leg`` (one ``kind: send`` template edge; the
    list-form declared target keeps extraction warning-free, PD-044 D3) with the fan-in
    wired explicitly to ``check_booking`` — never ``Send`` → END, PD-044 D15's trap. The
    booking SCC persists (five nodes, both re-entries still through the witnessed
    ``replan``), the conditional ``available`` re-entry seeds §6.4's retry region, and the
    send closure carries the region one hop to the worker: ``book_leg`` is billable there
    with no protection — ``unprotected-effect-in-retry-region`` with ``fanout: send``
    evidence, ERROR, exit 1, at a locus distinct from defect 2's as PD-006 R1's rider
    requires.
    """
    builder = _base_builder()

    builder.add_node("classify_request", tb.classify_request)
    builder.add_node(
        "availability_check",
        tb.availability_check,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=TimeoutError),
    )
    builder.add_node("replan", tb.replan)
    builder.add_node("dispatch_bookings", dispatch_bookings)
    builder.add_node("book_leg", book_leg)
    builder.add_node("check_booking", tb.check_booking)
    builder.add_node("compile_itinerary", tb.compile_itinerary)
    builder.add_node("notify_traveler", tb.notify_traveler)
    builder.add_node("release_hotel_hold", tb.release_hotel_hold)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "availability_check")
    builder.add_conditional_edges(
        "availability_check",
        tb.route_availability,
        {"available": "dispatch_bookings", "revise": "replan"},
    )
    builder.add_edge("replan", "availability_check")
    builder.add_conditional_edges("dispatch_bookings", route_legs, ["book_leg"])
    builder.add_edge("book_leg", "check_booking")
    builder.add_conditional_edges(
        "check_booking",
        tb.route_booking,
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


# ── The recorded expectations — PD-006 C1's table, as data the harness enforces ──────────


@dataclass(frozen=True)
class DefectVariant:
    """One seeded defect with the C1-frozen expectations the DoD harness asserts.

    Attributes:
        number: The SOW §2 criterion-1 defect number (1–5).
        name: A stable, structural variant name (no category vocabulary in rendered values).
        build: The variant's builder — a fresh, independent ``StateGraph`` per call.
        property: The named property's catalog slug — C1's "the named property failing".
        condition: The expected condition ID — a RATIFIED §0.4 registry entry, never
            RESERVED or PROPOSED (the defect-5 rider, held for all five).
        severity: The registry severity of that condition (``fatal | error | warning``).
        locus_nodes: The node ids the finding's location must anchor — one entry for a
            node-anchored finding, the whole residual SCC for defect 1's scc anchor.
        state_key: The Σ key a state-key-anchored locus must name (defect 4), else ``None``.
        fanout_send: Whether the locus must carry the ``fanout: send`` evidence (defect 5).
        strict_slug: The per-property promotion the catch needs (defect 3's
            ``determinism-replay``), else ``None`` — R2's ruling, not a construction choice.
        default_exit: ``verify()``'s exit code under the default policy — 1 for the
            FATAL/ERROR defects, 0 for defect 3, whose catch is the strict leg.
        summary: One structural line for a human reading a table.
    """

    number: int
    name: str
    build: Callable[[], Any]
    property: PropertySlug
    condition: ConditionId
    severity: str
    locus_nodes: tuple[str, ...]
    state_key: str | None
    fanout_send: bool
    strict_slug: str | None
    default_exit: int
    summary: str


#: The booking SCC of v1's topology — defect 1's residual, PROPERTY-CATALOG-SPEC §2.2's
#: five nodes under this fixture's spellings.
BOOKING_SCC: Final[tuple[str, ...]] = (
    "availability_check",
    "book_flight",
    "book_hotel",
    "check_booking",
    "replan",
)

#: The five defects in SOW §2 criterion-1 order. Expectations are PD-006 C1's rows; the
#: construction behind each is this module's latitude within them.
DEFECTS: Final[tuple[DefectVariant, ...]] = (
    DefectVariant(
        number=1,
        name="defect-1-cycle-without-witness",
        build=build_defect_1_unwitnessed_cycle,
        property="termination-witness",
        condition="cycle-without-termination-witness",
        severity="fatal",
        locus_nodes=BOOKING_SCC,
        state_key=None,
        fanout_send=False,
        strict_slug=None,
        default_exit=1,
        summary="replan loses its variant slot; the five-node SCC carries no witness form",
    ),
    DefectVariant(
        number=2,
        name="defect-2-unprotected-retry",
        build=build_defect_2_unprotected_retry,
        property="effect-safety",
        condition="unprotected-effect-in-retry-region",
        severity="error",
        locus_nodes=("book_flight",),
        state_key=None,
        fanout_send=False,
        strict_slug=None,
        default_exit=1,
        summary="book_flight loses @gebra.idempotent inside the booking retry region",
    ),
    DefectVariant(
        number=3,
        name="defect-3-false-determinism",
        build=build_defect_3_false_determinism,
        property="determinism-replay",
        condition="deterministic-llm-temperature-unpinned",
        severity="warning",
        locus_nodes=("classify_request",),
        state_key=None,
        fanout_send=False,
        strict_slug="determinism-replay",
        default_exit=0,
        summary="classify_request claims seed-only determinism with external among effects",
    ),
    DefectVariant(
        number=4,
        name="defect-4-unsupplied-read",
        build=build_defect_4_unsupplied_read,
        property="dataflow-completeness",
        condition="read-key-never-written-on-path",
        severity="fatal",
        locus_nodes=("notify_traveler",),
        state_key="itinerary",
        fanout_send=False,
        strict_slug=None,
        default_exit=1,
        summary="an express label skips both bookings; notify_traveler reads itinerary",
    ),
    DefectVariant(
        number=5,
        name="defect-5-unprotected-fanout",
        build=build_defect_5_fanout,
        property="effect-safety",
        condition="unprotected-effect-in-retry-region",
        severity="error",
        locus_nodes=("book_leg",),
        state_key=None,
        fanout_send=True,
        strict_slug=None,
        default_exit=1,
        summary="a send fan-out worker books billable legs unprotected in the retry region",
    ),
)
