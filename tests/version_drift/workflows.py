"""The version-drift fixture set — VERSION-COMPAT §3 tests 1-12 (1-6 GOV-05; 7-12 GOV-06).

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

* no **golden-bearing** fixture touches a langgraph-1.2-only builder API
  (``set_node_defaults``, ``add_node(..., error_handler=...)``, ``timeout=``) or the beta
  ``DeltaChannel``, and
* no fixture carries a ``BaseChatModel`` or ``bind()`` wrapper — a model's
  ``config_digest`` projects the *installed* core's ``model_fields``
  (INTROSPECTION-SPEC §7.4 (c)), which moves with core releases (§7.4 (e)), so a model
  carrier cannot sit under a cross-cell byte golden. This is the GOV-05/GOV-06 card note
  and the EX-17 → GOV-drift handoff, honored by composition; adding one later is a WA-03
  event.

Two **line-gated probe factories** are the deliberate, non-golden exceptions — §3 rows 9
and 10 name 1.2-line surfaces outright, so the probes exist exactly where the surface does:

* :func:`build_node_metadata_enriched` (row 10) builds the ``timeout=`` +
  ``error_handler=`` twin of the golden-bearing plain fixture. It is asserted at surface
  level and **never extracted into a golden**; callers gate on
  :data:`tests.substrate.HAS_NODE_TIMEOUT`/:data:`~tests.substrate.HAS_NODE_ERROR_HANDLER`
  because the 1.0/1.1 ``add_node`` *swallows* both keywords through ``**kwargs``, and the
  factory self-checks that the enrichment took, so a swallowing line can never hand back a
  plain graph wearing the enriched name.
* :func:`build_channel_reducer_delta` (row 9's beta variant) binds one key to the beta
  ``DeltaChannel``; the import lives inside the factory, so this module imports cleanly on
  the 1.0/1.1 lines where ``langgraph.channels.delta`` does not exist. Its consuming test
  is ``xfail(strict=False)`` per §3 — beta never blocks any cell.

The node-spec ``metadata=`` kwarg is passed on the test-1 fixture (a §2 surface, present
across the range); ``cache_policy`` is asserted as a *field* of ``StateNodeSpec`` (the §3
row's ⊇ set) and never passed as a kwarg — the row's claim is about the spec's shape, and a
kwarg the older builders might route differently would put a portability bet inside a
fixture that exists to detect substrate movement, not to gamble on it. The test-7 state
schema is declared with ``typing_extensions.TypedDict``, the one place this set needs it:
the row's own assertion calls the jsonschema getters, and pydantic (2.13, pinned on every
cell) refuses to render a ``typing.TypedDict`` on Python < 3.12 — the portable spelling is
what lets the same fixture render the same schema document on every tested Python.

**Never-invokes posture (WA-07).** Every node function, router, reducer and LCEL step here
records itself in :data:`TRIPPED` and then raises :class:`DriftSentinelError` — a
``BaseException`` subclass, so no ``except Exception`` guard can swallow one silently. The
suite asserts the ledger is empty after every test and *fires* every body to prove the
arming is live (the one ``async`` body via a single ``send(None)``, which executes it to
its immediate raise). Test 4 additionally calls ``compiled.get_graph(xray=True)`` — a
substrate introspection call the spec row itself names — under the same ledger: a substrate
release whose drawing started invoking node bodies would trip the sentinels and fail the
run loudly. ``compile()`` is graph construction, not execution (INTROSPECTION-SPEC §4), and
happens only inside factories and tests, never at import time. Test 12's registry fixture
is a **compiled** graph — §3 row 12 reads the P-13 carriers, which exist only at the
compiled level — so this set does hand a compiled object to ``extract()``; extraction of a
compiled object is an already-tripwired EX path (its §4.2 cross-check draws under the
extractor's own hazard rules), and every body it could conceivably reach is armed here.
This suite adds **no extraction path** — it calls ``gebra.extract()`` and reads substrate
attributes — so no new tripwire is owed under WA-07's per-path rule; the arming here is a
redundant guard on top of the per-path tripwire suites, not their replacement.

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

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send
from typing_extensions import TypedDict as PortableTypedDict

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


# ── schema-getters (§3 test 7) ───────────────────────────────────────────────────────────


# The typed state the row-7 getters render — three keys, three JSON Schema types.
# ``typing_extensions.TypedDict`` by necessity, not preference: pydantic (2.13, the pin on
# every cell) raises on rendering a ``typing.TypedDict`` under Python < 3.12, and this is
# the one fixture whose row calls the renderer. A comment rather than a docstring, also by
# necessity: a class docstring becomes the rendered schema's `description`, putting prose
# inside the drift surface.
class ResearchBrief(PortableTypedDict):
    topic: str
    attempts: int
    sources: list[str]


def _plan_research(state: ResearchBrief) -> dict[str, str]:
    return _trip("schema-getters.plan_research")  # type: ignore[no-any-return]


def build_schema_getters() -> StateGraph[ResearchBrief]:
    """One node over the typed state schema — the §3 row-7 fixture."""
    builder = StateGraph(ResearchBrief)
    builder.add_node("plan", _plan_research)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", END)
    return builder


# ── context-schema (§3 test 8) ───────────────────────────────────────────────────────────


class GateState(TypedDict):
    ticket: str


class ReviewContext(TypedDict):
    """The context schema both row-8 constructions carry (modern and legacy spelling)."""

    tenant: str


def _triage(state: GateState) -> dict[str, str]:
    return _trip("context-schema.triage")  # type: ignore[no-any-return]


def build_context_schema() -> StateGraph[GateState, ReviewContext]:
    """The modern spelling: ``context_schema=`` at construction — the §3 row-8 fixture."""
    builder = StateGraph(GateState, context_schema=ReviewContext)
    builder.add_node("triage", _triage)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", END)
    return builder


def build_context_schema_legacy() -> StateGraph[GateState]:
    """The legacy spelling: ``config_schema=`` — same graph, deprecated constructor kwarg.

    Constructing this **emits the substrate's deprecation warning** (that emission is the
    row-8 surface under test), so callers run it under ``warnings.catch_warnings`` — the
    test reaches it only through :func:`~tests.version_drift.review.classify_config_schema_probe`,
    which captures the warning and classifies the outcome. On a substrate that has removed
    the kwarg this raises ``TypeError``, which is the §3 row-8 2.0-ceiling signal.
    """
    # The deprecated spelling is deliberately not in the typed constructor signature at the
    # pinned substrate (it routes through the deprecation shim); passing it IS this
    # fixture's purpose, so the one suppressed error is the call-arg on this line.
    builder = StateGraph(GateState, config_schema=ReviewContext)  # type: ignore[call-arg]
    builder.add_node("triage", _triage)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", END)
    return builder


# ── channel-reducer (§3 test 9) ──────────────────────────────────────────────────────────


class EvidenceLedger(TypedDict):
    log: Annotated[list[str], operator.add]
    latest: str


def _track(state: EvidenceLedger) -> dict[str, str]:
    return _trip("channel-reducer.track")  # type: ignore[no-any-return]


def build_channel_reducer() -> StateGraph[EvidenceLedger]:
    """Reducer-annotated state beside a plain key — the §3 row-9 main fixture.

    ``log`` binds to a ``BinaryOperatorAggregate`` (the reducer channel), ``latest`` to a
    ``LastValue`` — between them the two channel classes whose semantics ir 1.0 carries.
    """
    builder = StateGraph(EvidenceLedger)
    builder.add_node("track", _track)
    builder.add_edge(START, "track")
    builder.add_edge("track", END)
    return builder


def merge_delta(current: list[str], updates: Any) -> list[str]:
    """The armed reducer the beta ``DeltaChannel`` carries — never invoked.

    Public (like the routers) because the armed-control test fires it directly on every
    cell: the graph that holds it only builds where ``langgraph.channels.delta`` exists.
    """
    return _trip("channel-reducer-delta.merge_delta")  # type: ignore[no-any-return]


def track_delta(state: Any) -> dict[str, str]:
    """The delta variant's node body — public for the same direct-fire reason."""
    return _trip("channel-reducer-delta.track_delta")  # type: ignore[no-any-return]


def build_channel_reducer_delta() -> StateGraph[Any]:
    """The separate beta variant: one key bound to a ``DeltaChannel`` instance (§3 row 9).

    The import and the state class live inside the factory: ``langgraph.channels.delta``
    does not exist on the 1.0/1.1 lines, and the ``Annotated`` metadata holds a channel
    *instance*, which would otherwise be constructed at module import. The consuming test
    is ``xfail(strict=False)`` — on the pre-1.2 lines this factory raises
    ``ModuleNotFoundError``, which is that xfail firing, not an error to hide.
    """
    from langgraph.channels.delta import DeltaChannel

    class DeltaLedger(TypedDict):
        log: Annotated[list[str], DeltaChannel(merge_delta, list[str])]
        latest: str

    builder = StateGraph(DeltaLedger)
    builder.add_node("track", track_delta)
    builder.add_edge(START, "track")
    builder.add_edge("track", END)
    return builder


# ── node-metadata-additive (§3 test 10) ──────────────────────────────────────────────────


class IngestState(TypedDict):
    job: str
    output: str


#: The pre-1.2 node declaration both row-10 twins carry, verbatim — the fields whose
#: "undisturbed" the row asserts. One source so the twins cannot drift apart in what they
#: pass.
INGEST_METADATA: Final = {"team": "governance"}


def ingest_retry_policy() -> RetryPolicy:
    """The twins' shared retry policy — built per call because a policy is a value."""
    return RetryPolicy(max_attempts=4, retry_on=(ValueError,))


def _ingest(state: IngestState) -> dict[str, str]:
    return _trip("node-metadata-additive.ingest")  # type: ignore[no-any-return]


async def ingest_enriched(state: IngestState) -> dict[str, str]:
    """The enriched twin's body — ``async`` because the substrate's own compile-time
    validation admits ``timeout=`` on async nodes only; armed exactly like every sync body
    (the control test drives it to its immediate raise with one ``send(None)``). Public,
    like the delta pair, for the control's line-independent direct fire."""
    return _trip("node-metadata-additive.ingest_enriched")  # type: ignore[no-any-return]


def recover_ingest(state: IngestState) -> dict[str, str]:
    """The enriched twin's error handler — public for the direct fire and the identity
    assertion (the test holds the synthesized handler node to this exact function)."""
    return _trip("node-metadata-additive.recover_ingest")  # type: ignore[no-any-return]


def build_node_metadata() -> StateGraph[IngestState]:
    """The plain twin: the pre-1.2 declaration only — the §3 row-10 golden carrier.

    This is the fixture whose extracted core IR is the cross-cell golden; the additive
    kwargs live on the enriched twin below, which exists only where the substrate has them.
    """
    builder = StateGraph(IngestState)
    builder.add_node(
        "ingest", _ingest, metadata=dict(INGEST_METADATA), retry_policy=ingest_retry_policy()
    )
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", END)
    return builder


def build_node_metadata_enriched() -> StateGraph[IngestState]:
    """The enriched twin: the same declaration plus ``timeout=`` + ``error_handler=``.

    Callers gate on :data:`tests.substrate.HAS_NODE_TIMEOUT` /
    :data:`~tests.substrate.HAS_NODE_ERROR_HANDLER` — the 1.0/1.1 ``add_node`` swallows
    both keywords through ``**kwargs``, so this factory additionally **self-checks that the
    enrichment took**: a substrate that accepted-and-dropped either kwarg hands back a
    graph this factory refuses to return. Never extracted into a golden — the synthesized
    handler node is part of the built graph, which is a 1.2-line node set by construction.
    """
    builder = StateGraph(IngestState)
    builder.add_node(
        "ingest",
        ingest_enriched,
        metadata=dict(INGEST_METADATA),
        retry_policy=ingest_retry_policy(),
        timeout=30.5,
        error_handler=recover_ingest,
    )
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", END)
    spec = builder.nodes["ingest"]
    if getattr(spec, "timeout", None) is None or not getattr(spec, "error_handler_node", None):
        raise RuntimeError(
            "the installed builder accepted and dropped the 1.2-era add_node kwargs — "
            "this factory is gated on tests.substrate.HAS_NODE_TIMEOUT/HAS_NODE_ERROR_HANDLER"
        )
    return builder


# ── lcel-fragment (§3 test 11) ───────────────────────────────────────────────────────────


def _gather_context(request: dict[str, Any]) -> dict[str, Any]:
    return _trip("lcel-fragment.gather_context")  # type: ignore[no-any-return]


def _fetch_docs(request: dict[str, Any]) -> list[str]:
    return _trip("lcel-fragment.fetch_docs")  # type: ignore[no-any-return]


def _fetch_meta(request: dict[str, Any]) -> dict[str, Any]:
    return _trip("lcel-fragment.fetch_meta")  # type: ignore[no-any-return]


def build_lcel_fragment() -> Any:
    """The composed LCEL chain — the §3 row-11 fixture, built fresh per call.

    A ``RunnableSequence`` whose middle is a dict-keyed ``RunnableParallel`` and whose last
    step is an **unnamed lambda** (its drawn name is the anonymous ``Lambda``), exactly the
    row's composition. The pipe operator coerces the dict and the lambda; the lambda's body
    is armed inline. Construction wires runnables together and invokes nothing.
    """
    return (
        RunnableLambda(_gather_context)
        | {"docs": _fetch_docs, "meta": _fetch_meta}
        | (lambda merged: _trip("lcel-fragment.merge_lambda"))
    )


# ── interrupt-checkpointer (§3 test 12) ──────────────────────────────────────────────────


class PressState(TypedDict):
    draft: str
    published: str


def _draft_release(state: PressState) -> dict[str, str]:
    return _trip("interrupt-checkpointer.draft_release")  # type: ignore[no-any-return]


def _publish_release(state: PressState) -> dict[str, str]:
    return _trip("interrupt-checkpointer.publish_release")  # type: ignore[no-any-return]


def build_interrupt_checkpointer() -> StateGraph[PressState]:
    """The two-node builder under the row-12 compiled fixture — exposed for the armed walk."""
    builder = StateGraph(PressState)
    builder.add_node("draft", _draft_release)
    builder.add_node("publish", _publish_release)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "publish")
    builder.add_edge("publish", END)
    return builder


def build_interrupt_checkpointer_compiled() -> Any:
    """Compiled with both interrupt gates and an in-memory checkpointer — the §3 row-12
    fixture. The P-13 carriers (``runtime.interrupts``/``runtime.checkpointer``) exist only
    at the compiled level, so this case's registry factory is the compiled object;
    ``compile()`` is graph construction, and ``InMemorySaver()`` is an inert in-process
    store from the substrate itself."""
    return build_interrupt_checkpointer().compile(
        checkpointer=InMemorySaver(),
        interrupt_before=["publish"],
        interrupt_after=["draft"],
    )


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
    "schema-getters": DriftCase(
        test="test_drift_schema_getters_jsonschema", build=build_schema_getters
    ),
    "context-schema": DriftCase(
        test="test_drift_context_schema_surface", build=build_context_schema
    ),
    "channel-reducer": DriftCase(
        test="test_drift_channel_reducer_repr", build=build_channel_reducer
    ),
    "node-metadata-additive": DriftCase(
        test="test_drift_node_metadata_additive", build=build_node_metadata
    ),
    "lcel-fragment": DriftCase(test="test_drift_lcel_fragment_identity", build=build_lcel_fragment),
    "interrupt-checkpointer": DriftCase(
        test="test_drift_compiled_interrupt_checkpointer",
        build=build_interrupt_checkpointer_compiled,
    ),
}
