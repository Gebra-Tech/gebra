"""The travel-booking agent — the shared end-to-end substrate, committed for TE-05.

A live LangGraph ``StateGraph`` re-expressing the ``07-AI-Agent-Orchestration`` tutorial
agent the SOW's Phase-0 Definition of Done is written about (SOW §2 criterion 1). It is
routed, stateful, contract-annotated with the decorator surface, sentinel-guarded so that any
body which runs fails the test that ran it, and extractable to the Gebra IR — and at **v1** it
is clean on the wedge five.

**A note on section references.** This module cites four frozen specs, so every ``§`` below
carries its spec name. Bare ``§`` numbers are ambiguous across them — ``§4.2`` is P-04's
agent-graph interpretation in one and the START/END sentinel equivalence in another — and
this file is read by six downstream cards.

**Why "clean at v1" is the whole point.** The tutorial agent is quoted in four frozen
passages, and each quotes it in its *broken* state — the passages are the catalog's failure
examples:

* PROPERTY-CATALOG-SPEC §2.2 — ``book_flight → check_booking_status →`` a conditional edge
  back to ``book_flight`` on ``"retry"``, with no counter in ``TravelState`` and no justified
  ``recursion_limit`` (P-02).
* PROPERTY-CATALOG-SPEC §6.2 — ``book_flight`` is
  ``@gebra.effect("irreversible", "billable")`` sitting in that booking cycle, with the two
  admitted remedies named: ``@gebra.idempotent(key=…)`` and a compensation hook, "the
  ``release_hotel_hold`` pattern" (P-06).
* PROPERTY-CATALOG-SPEC §4.2 — an ``"express"`` branch routes ``availability_check`` straight
  to ``send_confirmation``, skipping both booking nodes, so ``booking_id`` is never written on
  that path (P-04).
* PROPERTY-CATALOG-SPEC §8.2 — ``classify_request`` is declared
  ``@gebra.deterministic(seed=42)`` while its effects include ``external`` and ``temperature``
  is unpinned (P-08).

Seeding those defects is **SD-09's** card ("the five seeded-defect variants exist"), not this
one. So this module carries the same graph in the state each passage describes as the fix:
the cycle is witnessed, both effect nodes are protected, and the determinism claim is
coherent.

**What "the same graph" does and does not mean, stated rather than implied.** Three of the
four passages transfer node for node, and their defect is one annotation edit away from this
file: §2.2's cycle (drop ``replan``'s ``variant``), §6.2's unprotected effect (drop a
protection slot), §8.2's incoherent claim (drop ``temperature``). The fourth does not. Two
names are re-spelled here — §2.2's ``check_booking_status`` is ``check_booking`` and §4.2's
``send_confirmation`` is ``notify_traveler`` — and §4.2's defect is a **topology** edit (a new
``"express"`` label) against a key, ``booking_id``, that this Σ does not carry: the bookings
write ``flight_id`` and ``hotel_id`` separately, so the analogue of that defect has a target
choice to make and more than one finding available. SD-09 inherits that choice rather than
finding it.

**Which level is the subject** (PD-023 asks TE-05 and SD-08 to choose explicitly, because a
compiled travel-booking agent carries ``runtime.checkpointer`` and therefore a different
``graph_version``): the **builder** is v1's subject. Two reasons, both about what the digest
should mean. ``runtime.checkpointer`` and ``runtime.interrupts`` (IR-SPEC §3.7) are
compile-time surfaces — INTROSPECTION-SPEC §3's closing line lists them under "Not present at
builder level: … those are compile-time surfaces", and its §7.1 rates them "Full at compiled
level; absent, never guessed, at builder level" — so they say what compiling this definition
configured, not what the definition is. The wedge five read neither. (At this fixture's shape
only ``checkpointer`` actually lands: an empty ``interrupts`` is omit-normalized away by
IR-SPEC §6.3.) :func:`compile_travel_booking_agent` is here for the cards that want the
INTROSPECTION-SPEC §4 surface, and PD-023 D4's ruling stands over it: the builder document
and the compiled document of one workflow are different documents by design.

**Why the cycle carries a form-(c) witness and not a form-(a) counter guard.** P-02's three
witness forms are not equally reachable from a *live* object, and the reason is in what
extraction can see rather than in the spec. Form (a) is a guard grammar over
``edges[].condition`` (TERMINATION-WITNESS-SPEC §3), and IR-SPEC §2.4 says where that string
comes from: it is "taken from gebra annotations/config — declared IR content, never extracted
opaque Python". On the extraction path there is no such declaration to take, so
INTROSPECTION-SPEC §3's ``.branches`` row fills the slot with "the declared branch name"
(``path.name or "condition"``), restated at its §6 — an ordinary Python identifier, which the
grammar's **L0** lexical gate rejects wholesale (it requires exactly one ``if`` token and
exactly one ``else`` token) before any derivation is attempted. That is a fact about the
declaration forms an author actually writes, not a structural impossibility: ``condition`` is
an unconstrained ``str`` in the model, and LangGraph takes the branch name off the router's
``__name__``. Form (b) is ``runtime.recursion_limit``, which
:mod:`gebra.extraction.builder` records as absent at builder level and
:mod:`gebra.extraction.compiled` leaves ``None`` on the compiled path — those two modules,
not a claim about every conceivable carrier: INTROSPECTION-SPEC §7.1 designates
annotation/sidecar as the slot's source, and a sidecar carrier landing later would change
this paragraph and nothing else. Form (c) — the ``variant`` annotation slot — is a decorator,
so it is the one form an author of a live graph can actually declare, and
TERMINATION-WITNESS-SPEC §2.3 makes it discharge the **carrier node**: every simple cycle
here runs through ``replan``, so one carrier covers both.

None of that is a defect in either spec: an *authored* IR document carries whatever
``condition`` string its author wrote, which is why the corpus has form-(a) fixtures. It is a
fact about live extraction, and it is what makes the variant slot the right instrument here.

**Why Σ declares a narrower input schema.** PD-021 D1: ``StateGraph(S)`` leaves
``input_schema`` equal to ``S``, so every key extracts ``optional: true``
(INTROSPECTION-SPEC §3's state row), IR-SPEC §2.2 reads that as "written at START", and P-04
has nothing to report on the whole graph. Declaring ``input_schema=`` is the author-side
recovery the ruling names, and this fixture takes it — without it a P-04 pass here would be
vacuous and the DoD's seeded read-key defect would be uncatchable. That is demonstrated
rather than asserted: :func:`build_travel_booking_agent` takes a ``narrow_input_schema``
flag whose only purpose is to build the counterfactual, and
``test_the_dataflow_pass_is_not_vacuous`` runs P-04 over both. (PD-021 D1 attributes the
seeded defect to SD-08 and the board gives it to SD-09; the ruling binds either way, and the
attribution is not this card's to settle.)

**Never-invokes posture (WA-07).** Every node function and every router in this module
records itself in :data:`TRIPPED` and then raises :class:`TravelBookingSentinelError`, a
``BaseException`` subclass so that no ``except Exception`` guard on an extraction path can
swallow one into a warning. ``tests/testing/test_travel_booking.py`` asserts the ledger is
empty on entry to *and* exit from every test — entry as well as exit, because a module-scoped
extraction runs before the first test's own setup and a clear-then-check fixture would erase
exactly the evidence this ledger exists to keep — and it *fires* every body, because a
tripwire nobody trips proves nothing. This module adds no extraction path — every path it
reaches already carries its own tripwire suite (``tests/never_invokes_audit.md`` §1) — so the
arming here is a guard over the fixture, not a replacement for those.

Import safety: importing this module defines callables and constants only. No graph is built,
nothing is compiled, no external service is contacted, and no API key is needed.

No ``from __future__ import annotations`` here, on purpose, for the reason
``conformance.py`` states: the ANNOTATION §4 inference patterns read a node's *evaluated*
parameter annotation, and the futures form would turn every annotation in the module into a
string — a different, degraded surface. Nothing in this module relies on inference (every
slot it needs is declared), but the fixture is the one downstream cards extract, so it pins
the mainstream form.
"""

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

import gebra

__all__ = [
    "AVAILABILITY_LABELS",
    "BOOKING_LABELS",
    "NODE_IDS",
    "TRIPPED",
    "TravelBookingSentinelError",
    "TravelRequest",
    "TravelState",
    "build_travel_booking_agent",
    "compile_travel_booking_agent",
    "route_availability",
    "route_booking",
]

#: Every sentinel that was reached, recorded **before** it raises, so a raise that something
#: swallowed is still visible. The suite clears and checks this per test.
TRIPPED: list[str] = []


class TravelBookingSentinelError(BaseException):
    """Raised by any node or router body in this module that gets invoked.

    ``BaseException`` rather than ``Exception``, for the reason ``conformance.py`` records:
    an ``except Exception`` guard on an extraction path must not be able to swallow this into
    a warning. Extraction — or a test — reaching a body here fails the run.
    """


def _trip(label: str) -> Any:
    """Record ``label`` and raise — the body of every invokable thing in this module."""
    TRIPPED.append(label)
    raise TravelBookingSentinelError(f"{label!r} was invoked — nothing here may ever run")


# ── Σ: the state schema and its graph-input projection ───────────────────────────────────


class TravelState(TypedDict):
    """The agent's full state channel set — Σ of the extracted IR.

    Eleven keys. Which of them are *graph inputs* is :class:`TravelRequest`'s question, and
    the split is load-bearing rather than cosmetic: see the module docstring on PD-021 D1.
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
    itinerary: str
    confirmation: str


class TravelRequest(TypedDict):
    """The graph-input projection — what the caller supplies, and nothing else.

    These four keys extract ``optional: true`` (INTROSPECTION-SPEC §3's state row —
    "``optional: true`` for graph-input/defaulted keys" — under PD-021 D1) and are therefore
    P-04's boundary set $I_0$, since IR-SPEC §2.2 reads an optional key as written at START.
    The other seven are internal and must be written by some node on every path that reads
    them, which is the obligation this fixture exists to satisfy non-vacuously.

    ``booking_request_id`` is the caller-supplied idempotency key ``book_flight`` pins its
    retry safety to. Its being a graph input is the honest shape: a key the *agent* minted
    inside the retry region could not identify the same booking attempt across laps.
    """

    request: str
    traveler_id: str
    booking_request_id: str
    replan_budget: int


# ── The nodes ────────────────────────────────────────────────────────────────────────────
#
# Every node declares `reads`, `writes` and `effects` explicitly. Leaving any of the three to
# ANNOTATION-API-SPEC §4 inference would put the fixture outside the warning-free strict-mode
# bar INTROSPECTION-SPEC §8 states and PROPERTY-CATALOG-SPEC §0.2 owns (EX-11's finding). The
# cost is not only a warning: ANNOTATION-API-SPEC §5 grades a slot declared **iff** no
# `contract-inferred`/`contract-defaulted` record names the (node, slot) pair, so one defaulted
# slot would quietly demote this substrate's DEFENSIBLE-A claims to heuristic grade for every
# consuming card.


@gebra.contract(
    reads=("request",),
    writes=("request_kind",),
    effects=("external", "network"),
)
@gebra.deterministic(seed=42, temperature=0.0)
def classify_request(state: TravelState) -> dict[str, str]:
    """Classify the traveller's request with an LLM — PROPERTY-CATALOG-SPEC §8.2's node.

    The catalog's P-08 failure example is this node declared ``@gebra.deterministic(seed=42)``
    with ``external`` among its effects and ``temperature`` unpinned. Here the claim is the
    **coherent** object form: seed pinned, ``temperature`` pinned at 0. PROPERTY-CATALOG-SPEC
    §8.2's coherence rule is exactly "object form with ``seed`` pinned and ``temperature = 0``"
    for an LLM-backed node, and LLM-backed is evidenced there by
    ``effect ∩ {network, external} ≠ ∅``. (§8.3 is the I/O contract — the models and the
    condition IDs — not the rule.)

    What the pinned claim does *not* say is PROPERTY-CATALOG-SPEC §8.1's boundary and is worth
    restating where the annotation is: determinism of an external provider is not decidable
    from the IR — it is a claim about the world, not about the graph. P-08
    checks the claim's coherence; the witness carries the
    ``provider-seed-reproducibility-not-guaranteed`` caveat precisely because the pinning is
    a claim about the world.
    """
    return _trip("travel-booking.classify_request")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("request_kind", "traveler_id"),
    writes=("availability",),
    effects=("network",),
)
def availability_check(state: TravelState) -> dict[str, str]:
    """Query the supplier for flight/hotel availability — the tutorial's fan-out point.

    Carries a ``retry_policy`` (declared at the ``add_node`` call site — the projection is
    INTROSPECTION-SPEC §3's ``StateNodeSpec.retry_policy`` row, the slot shape is IR-SPEC
    §3.2) so the fixture exercises it. The node is deliberately **not** trigger-tagged:
    ``network`` creates no P-06 obligation, because PROPERTY-CATALOG-SPEC §6.3 fixes the
    trigger set at exactly ``{billable, irreversible}`` and says the other tags "still appear
    inside the ``effect`` tuples … never as an obligation source". So the node-local retry
    region here is one P-06 reads and correctly says nothing about.
    """
    return _trip("travel-booking.availability_check")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "replan_budget"),
    writes=("request_kind", "replan_budget"),
    effects=("external", "network"),
)
@gebra.variant(
    key="replan_budget",
    measure="replan_budget strictly decreases each lap (one replanning attempt consumed)",
)
def replan(state: TravelState) -> dict[str, Any]:
    """Revise the plan when availability or booking disappoints — the P-02 witness carrier.

    Form (c) of P-02 (TERMINATION-WITNESS-SPEC §2.3): the ``variant`` slot attests a
    well-founded measure over ``replan_budget`` that strictly decreases on every execution of
    this node, and §2.3 discharges the **carrier node** — "any cycle through $n$ executes $n$
    once per iteration, so every cycle through the carrier is (attestedly) bounded".

    Both of this graph's simple cycles run through here, which is why one carrier suffices:
    the short lap ``availability_check → replan → availability_check`` and the long lap
    ``availability_check → book_flight → book_hotel → check_booking → replan →
    availability_check``. One shared element covering several simple cycles is TERMINATION-
    WITNESS-SPEC §5's own reading of DEC-05 D1, which is a Lemma-1 coverage condition and not
    a cardinality one. Remove this annotation and the residual is the whole five-node SCC —
    the same failure *class* as PROPERTY-CATALOG-SPEC §2.2 (whose instance is a specific
    ``check_booking_status → book_flight`` wiring), and the DoD's defect 1.

    TERMINATION-WITNESS-SPEC §1.1's boundary, restated at the carrier: the decrease is
    **attested**, never checked. Gebra records that the definition names a bound; it says
    nothing about whether a run halts.
    """
    return _trip("travel-booking.replan")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "booking_request_id"),
    writes=("flight_id",),
    effects=("irreversible", "billable", "network"),
)
@gebra.idempotent(key="booking_request_id")
def book_flight(state: TravelState) -> dict[str, str]:
    """Book the flight — PROPERTY-CATALOG-SPEC §6.2's node, in its protected state.

    The catalog's P-06 failure example is this node ``irreversible``+``billable`` inside the
    booking cycle with nothing protecting it. The first of the two remedies
    PROPERTY-CATALOG-SPEC §6.2 admits is ``@gebra.idempotent(key=…)``, "pinning retry safety
    to a declared read" — so the key is ``booking_request_id``, and it is a member of this
    node's declared ``input`` because §6.3 makes protection a matter of **binding**, not
    presence: "a keyed declaration whose key is not among declared ``input`` is NOT
    protection".

    **The ``reads`` tuple above is therefore load-bearing twice over** — and, corrected at
    the 2026-08-12 post-landing review: extraction DOES say so. Dropping
    ``booking_request_id`` from ``reads`` trips ``IDEMPOTENT_KEY_NOT_IN_INPUT``
    (``gebra.annotations.resolve``, landed EX-11) and the extraction carries an
    ``annotation-invalid`` warning — this docstring's original "extraction still
    warning-free" claim was empirically false at this card's own commit. The seed is
    therefore MORE detectable than first written: the warning fires at extraction AND P-06
    fails error-grade at verify. Still a fine P-06 seed for the DoD suite (SD-09) — but a
    variant suite must expect the warning, never assert warning-free extraction on it.

    Keyless ``@gebra.idempotent`` on an ``irreversible`` node would be the FATAL D-012
    contradiction (``irreversible-with-keyless-idempotent``), cycle-independently — a
    one-token edit. Anything seeding it should know it moves more than the P-06 verdict:
    PROPERTY-CATALOG-SPEC §0.2 makes FATAL alone suppress snapshot recording, so a variant
    seeded that way also takes the snapshot path with it.
    """
    return _trip("travel-booking.book_flight")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("availability", "booking_request_id"),
    writes=("hotel_id",),
    effects=("billable", "network"),
)
@gebra.compensation(hook="release_hotel_hold")
def book_hotel(state: TravelState) -> dict[str, str]:
    """Hold the hotel room — the second of PROPERTY-CATALOG-SPEC §6.2's admitted remedies.

    DEC-05 D7, restated normatively at §6.1: **compensation IS protection**, discharging the
    P-06 obligation exactly as a keyed idempotency declaration does. §6.2 names this shape by
    name — "the ``release_hotel_hold`` pattern of ``positive-03``" — and the ratified carrier
    is the ``compensation: {hook}`` slot, superseding the free-form ``compensated_by:``
    effect-tag encoding.

    The hook's side condition is **existence** — "``hook`` MUST name an existing node of the
    graph" (§6.1, DEC-05 D7) — and that alone is what :func:`release_hotel_hold` has to
    satisfy for this to be protection. It is *also* reachable and terminating, which is a
    separate obligation belonging to P-01, and the two should not be run together when
    reasoning about a dangling-hook variant.

    Carrying a different remedy from :func:`book_flight` is deliberate — the P-06 witness
    then contains one ``P06EffectRecord`` of each ``protection`` kind, so a consumer reading
    this substrate sees both forms rather than one twice.

    **A known contract gap rides this choice**, named at §6.1/DEC-05 D7 and deliberately left
    open there: P-07's pure-or-idempotent letter does not recognize compensation as
    protection, so this node is expected to co-fail P-07 when that validator lands. v1 is
    clean today because P-07 is outside the wedge; a card that widens the property set should
    read the §P-07 merge note rather than treat the new finding as a regression here.
    """
    return _trip("travel-booking.book_hotel")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("flight_id", "hotel_id"),
    writes=("booking_status",),
    effects=("network",),
)
def check_booking(state: TravelState) -> dict[str, str]:
    """Confirm both bookings with the suppliers — the tutorial's ``check_booking_status``.

    PROPERTY-CATALOG-SPEC §2.2's re-entry decision lives on this node's router: the tutorial
    routes back on ``"retry"``. Here the re-entry label is ``"revise"`` and it goes through
    :func:`replan`, which is what carries the bound.
    """
    return _trip("travel-booking.check_booking")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("flight_id", "hotel_id", "booking_status"),
    writes=("itinerary",),
    effects=(),
)
@gebra.deterministic
def compile_itinerary(state: TravelState) -> dict[str, str]:
    """Assemble the itinerary document from the confirmed bookings.

    The bare-boolean determinism claim on a node with **no** LLM evidence, which
    PROPERTY-CATALOG-SPEC §8.2 calls trivially coherent (pure local computation carries no
    pinning obligation). It is here so the P-08 witness of this fixture carries both claim
    shapes: one LLM-backed and pinned (:func:`classify_request`), one non-LLM with
    ``basis: pure-local-computation`` and ``pinning_required: false``. On
    :func:`classify_request` the identical bare form would be
    ``deterministic-llm-seed-unpinned``; what separates them is the effect set, not the
    annotation.

    **Declared with ``effects=()`` rather than ``@gebra.pure``, for two reasons.** The first
    is that the empty tuple is the narrower statement this node needs: ``pure`` is a distinct
    slot that P-06 was delisted from reading (DEC-13), and whose only prospective reader is
    P-07 — a property INTROSPECTION-SPEC §7.2 lists it under with that section's own caveat
    that the entry is derived from a catalog statement and re-verified when P-07 is drafted.
    The second is mechanical and is what keeps acceptance box 1 true: ANNOTATION-API-SPEC §3
    counts a slot set when it is not ``None``, so the empty tuple occupies ``effect`` and
    keeps the D-011 conservative default (``effect: ["write"]`` for a writer, plus a
    ``contract-defaulted`` record) out.

    What it does **not** put in the document is worth knowing before reading a snapshot:
    IR-SPEC §6.3 omits empty optional arrays, so the canonical bytes and the ``graph_version``
    carry no ``effect`` member here at all — byte-identical to an undeclared slot. The
    declaration is observable as the *absence* of a ``contract-defaulted`` record, not as an
    ``effect: []`` member.
    """
    return _trip("travel-booking.compile_itinerary")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("itinerary", "traveler_id"),
    writes=("confirmation",),
    effects=("external", "network"),
)
def notify_traveler(state: TravelState) -> dict[str, str]:
    """Send the traveller their itinerary — one of the two ``finish`` nodes."""
    return _trip("travel-booking.notify_traveler")  # type: ignore[no-any-return]


@gebra.contract(
    reads=("hotel_id", "booking_request_id"),
    writes=("booking_status",),
    effects=("external", "network"),
)
def release_hotel_hold(state: TravelState) -> dict[str, str]:
    """Release the hotel hold when the booking is abandoned — :func:`book_hotel`'s hook.

    Its being a **declared node of the graph** is what the ``compensation`` slot's side
    condition asks for and all it asks for. That it is additionally reachable (the ``"abort"``
    label of :func:`route_booking`) and terminating (then END) is what keeps P-01 clean — a
    different obligation, satisfied here by the same wiring.
    """
    return _trip("travel-booking.release_hotel_hold")  # type: ignore[no-any-return]


# ── The routers ──────────────────────────────────────────────────────────────────────────
#
# A router's *name* is the extracted edge's `condition` string (INTROSPECTION-SPEC §3's
# `.branches` row; its §6: "Guards are opaque references"). The body is never read, and the
# declared return hint is what §6 classifies on — neither of these names a `Send`, so both
# edges are `kind: conditional`.


def route_availability(state: TravelState) -> str:
    """Book, or go back and revise — the short lap's re-entry decision."""
    return _trip("travel-booking.route_availability")  # type: ignore[no-any-return]


def route_booking(state: TravelState) -> str:
    """Confirm, revise, or abandon — the long lap's re-entry decision (the catalog's
    ``"retry"``)."""
    return _trip("travel-booking.route_booking")  # type: ignore[no-any-return]


# ── The graph ────────────────────────────────────────────────────────────────────────────

#: :func:`route_availability`'s declared labels, in **builder-declaration** order — not the
#: serialized order. ``path_map`` is a JSON object, so IR-SPEC §6.2's canonicalization sorts
#: its member names: a consumer reading the canonical bytes or a snapshot sees them sorted,
#: and comparing this constant against that order will mismatch. Label *membership* is the
#: portable claim; the order here is what the builder declares.
AVAILABILITY_LABELS: Final[tuple[str, ...]] = ("available", "revise")

#: :func:`route_booking`'s declared labels, in builder-declaration order. The canonical bytes
#: sort these to ``abort, confirmed, revise`` — see :data:`AVAILABILITY_LABELS`.
BOOKING_LABELS: Final[tuple[str, ...]] = ("confirmed", "revise", "abort")

#: Every node id the built graph carries, in declaration order (the IR emits them in the
#: IR-SPEC §6.2 comparator's order instead). Held to the built object by the suite, so a node
#: added or renamed here without the fixture's consumers being told fails rather than drifts.
NODE_IDS: Final[tuple[str, ...]] = (
    "classify_request",
    "availability_check",
    "replan",
    "book_flight",
    "book_hotel",
    "check_booking",
    "compile_itinerary",
    "notify_traveler",
    "release_hotel_hold",
)


def build_travel_booking_agent(*, narrow_input_schema: bool = True) -> Any:
    """Build — never compile, never invoke — the travel-booking agent at v1.

    The topology, with the two re-entry decisions the tutorial is written around::

        START → classify_request → availability_check
        availability_check --route_availability--> {available: book_flight, revise: replan}
        replan → availability_check
        book_flight → book_hotel → check_booking
        check_booking --route_booking--> {confirmed: compile_itinerary,
                                          revise: replan, abort: release_hotel_hold}
        compile_itinerary → notify_traveler → END
        release_hotel_hold → END

    One non-trivial SCC — ``{availability_check, replan, book_flight, book_hotel,
    check_booking}`` — holding two simple cycles, both through :func:`replan`. Two nodes are
    wired to END, so ``finish`` extracts as a list: IR-SPEC §6.3's representation
    normalization spells the wired set as a scalar iff it is a singleton.

    Args:
        narrow_input_schema: **v1 is the default, ``True``.** Passing ``False`` builds the
            PD-021 D1 *counterfactual* — the identical graph declared ``StateGraph(S)``
            instead of ``StateGraph(S, input_schema=I)`` — which is not a version of this
            agent and must not be snapshotted, extracted into a golden, or handed to a
            consuming card as the substrate. It exists so the ruling's cost is demonstrated
            on this graph rather than described: under it every key of Σ extracts
            ``optional: true``, IR-SPEC §2.2 reads all of them as written at START, and P-04
            passes with nothing left to check. ``test_the_dataflow_pass_is_not_vacuous`` runs
            both and compares.

    Returns:
        The builder. Compilation is :func:`compile_travel_booking_agent`'s, and the builder
        is v1's extraction subject (see the module docstring on PD-023). Typed ``Any`` for
        the reason ``conformance.py::build_surface`` is: a narrowed ``input_schema=``
        parameterizes ``StateGraph`` on four type arguments whose arity is the installed
        substrate's, and this fixture is extracted on every cell of the frozen VERSION-COMPAT
        matrix.
    """
    builder = (
        StateGraph(TravelState, input_schema=TravelRequest)
        if narrow_input_schema
        else StateGraph(TravelState)
    )

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


def compile_travel_booking_agent() -> Any:
    """Compile the agent on demand — the §4 surface, for the cards that want it.

    ``compile()`` is graph construction rather than execution, but it stays behind a function
    for the reason ``sentinel_graph.py`` states: importing a fixture module should do the
    minimum. **The compiled object is a different document by design** (PD-023 D4): §3.7's
    ``runtime`` sub-slots are read only here, so a compiled extraction of this agent carries
    a ``runtime`` block the builder extraction does not, and therefore a different
    ``graph_version``. v1's subject is the builder.

    Returns:
        The compiled graph. Typed ``Any`` because ``CompiledStateGraph`` is a substrate class
        this module would otherwise have to import at runtime for a return annotation alone.
    """
    return build_travel_booking_agent().compile()
