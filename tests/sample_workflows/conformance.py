"""The extractor-conformance workflow set — IR-SPEC §1.3 layer 2, committed for EX-14.

Each entry in :data:`CASES` is one **live extraction fixture**: a LangGraph/LCEL source
program paired with a golden canonical serialization and digest under
``tests/extraction/golden/conformance/``. The suite (``tests/extraction/test_conformance.py``)
extracts each workflow and requires the §1.2 extractor-conformance operation to hold —
canonical bytes **byte-identical** to the committed golden, ``graph_version``
**string-equal** to the committed digest. One differing byte is non-conformance.

**This module is deliberately self-contained.** It imports no other ``sentinel_*`` fixture
module: those tables are per-card working fixtures that later cards edit freely, while the
conformance set is a published evidence surface (SOW §2 criterion 3) whose goldens change
only under the WA-05 lifecycle. A shared fixture edit must never be able to move a
conformance golden as a side effect.

**Composition** (the EX-14 ``decisions_to_implementer`` call). Eight workflows spanning the
three INTROSPECTION-SPEC §2 object families plus annotation resolution:

* ``builder-linear`` — the minimal builder: normal edges, scalar ``entry``/``finish``, and
  the PD-021 D1 Σ reading of a single-schema graph (every key a graph input, so every
  value carries ``optional: true``).
* ``builder-surface`` — the rich cell-stable §2/§3 surface in one graph: a conditional
  router with ``condition`` + ``path_map``, ``retry_policy``, an ``Annotated[T, reducer]``
  key and a ``NotRequired`` key in Σ, an escaped node name, and list-form
  ``entry``/``finish``.
* ``builder-send`` — a ``-> list[Send]``-hinted router with declared targets: ``send``
  edges, one per declared target (INTROSPECTION-SPEC §6, DEC-28 lineage).
* ``builder-dynamic`` — a ``Send``-hinted router declaring **no** targets: the ruled
  ``kind: dynamic`` edge, so this golden is an ``ir_version`` ``"1.1"`` document (DEC-28).
* ``compiled-runtime`` — the §4 compiled path: interrupt gates and checkpointer presence
  land on ``runtime`` (§3.7), which the builder path never carries.
* ``lcel-composite`` — a model-free stock composition covering six of the seven §5.2
  synthetic kinds (``seq``, ``map``, ``lambda`` with a captured dep, ``branch``, ``retry``,
  ``bind`` via ``with_config``) plus a ``prompt_digest``-carrying leaf and plain leaves.
* ``lcel-tool-bound`` — ``prompt | model.bind(tools=[…])``, the EX-16 admission shape:
  the model node carries a ``config_digest`` whose ``"bound"`` member reflects the tool
  overlay. Golden-gated by substrate version — see :data:`TOOL_BOUND_GATE`.
* ``annotations-resolved`` — one builder whose nodes cover the ANNOTATION-API-SPEC §3
  resolution tiers: decorator (with ``deterministic``), sidecar (reads/writes/effects,
  ``idempotent.key``, ``compensation.hook`` — via :data:`RESOLVED_SIDECAR`), tool-carried
  ``args_schema``, shallow inference, the opaque-body floor, and the undeclared default.

**Version portability.** EX-17 bisected exactly two surfaces that vary across the frozen
VERSION-COMPAT §3 matrix, and this set is composed around them: no workflow here touches the
langgraph-1.2-only builder APIs, and exactly one (``lcel-tool-bound``) carries a
``BaseChatModel``, whose ``config_digest`` projects the *installed* core's ``model_fields``
(INTROSPECTION-SPEC §7.4 (c)) — including, from core 1.4.7, a ``metadata.lc_versions``
member holding the installed core's own version string, so that digest legitimately moves
with every core release (§7.4 (e)). That one workflow's golden comparison is therefore
gated on **exact equality with the core release it was taken at** (see
:data:`TOOL_BOUND_GATE`); every other golden must hold byte-identically on every cell of
the matrix and on every Python.

**Never-invokes posture (WA-07).** Every node function, router, branch condition, tool
implementation and model method here records itself in :data:`TRIPPED` and then raises
:class:`ConformanceSentinelError` — a ``BaseException`` subclass, so no ``except Exception``
guard can swallow one silently — and the suite both asserts the ledger is empty after every
test and *fires* every body to prove the arming is live. The two declared reducers are the
stock ``operator.add``, which this ledger cannot see: a reducer is named during Σ
extraction, never called, and the arming for that claim lives with the state path's own
tripwires (``tests/extraction/test_state.py``). This card adds no new extraction path
(tripwires land with paths, and every path this set reaches already carries its own), so
the arming here is a redundant guard on top of the per-path tripwire suites, not their
replacement.

Import safety: importing this module defines factories only — no graph is built, nothing is
compiled, no external service is contacted, and no API key is needed.

No ``from __future__ import annotations`` here, on purpose: the §4 inference pattern (a)
reads a node's *evaluated* parameter annotation to find a state projection, and the futures
form would turn every annotation in the module into a string — a different (degraded)
extraction surface that ``tests/sample_workflows/sentinel_inference_futures.py`` covers
deliberately. The conformance set pins the mainstream form.
"""

import operator
from dataclasses import dataclass
from typing import Annotated, Any, Final, TypedDict

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.outputs import ChatResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    Runnable,
    RunnableBranch,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send
from pydantic import BaseModel

import gebra
from tests import substrate

#: Every sentinel that was reached, recorded **before** it raises, so a raise something
#: swallowed is still visible. The suite clears and checks this per test.
TRIPPED: list[str] = []


class ConformanceSentinelError(BaseException):
    """Raised by any conformance fixture body that gets invoked.

    ``BaseException`` so that an ``except Exception`` guard on an extraction path cannot
    swallow it into a warning: extraction reaching a body here must fail the run.
    """


def _trip(label: str) -> Any:
    """Record ``label`` and raise — the body of every invokable thing in this module."""
    TRIPPED.append(label)
    raise ConformanceSentinelError(f"{label!r} was invoked — extraction must never run it")


# ── builder-linear ───────────────────────────────────────────────────────────────────────


class LinearState(TypedDict):
    query: str
    answer: str


def _gather(state: LinearState) -> dict[str, str]:
    return _trip("builder-linear.gather")  # type: ignore[no-any-return]


def _respond(state: LinearState) -> dict[str, str]:
    return _trip("builder-linear.respond")  # type: ignore[no-any-return]


def build_linear() -> StateGraph[LinearState]:
    """Two nodes, normal edges only, singleton entry and finish."""
    builder = StateGraph(LinearState)
    builder.add_node("gather", _gather)
    builder.add_node("respond", _respond)
    builder.add_edge(START, "gather")
    builder.add_edge("gather", "respond")
    builder.add_edge("respond", END)
    return builder


# ── builder-surface ──────────────────────────────────────────────────────────────────────


class SurfaceState(TypedDict):
    query: str
    notes: Annotated[list[str], operator.add]
    audit: str


class SurfaceInput(TypedDict):
    """The graph-input projection — what makes Σ carry all three §6.3 value forms.

    With ``input_schema`` narrower than the state, ``query`` (graph input) carries
    ``optional: true``, ``notes`` (reducer, not input) is the object form without the flag,
    and ``audit`` (no reducer, not input, no default) collapses to the bare type string —
    the §7.1 sources as PD-021 D1 reads them.
    """

    query: str


def _surface_node(label: str) -> Any:
    """An armed node callable named ``label`` — the per-shape tripwire."""

    def _step(state: SurfaceState) -> dict[str, Any]:
        return _trip(label)  # type: ignore[no-any-return]

    _step.__name__ = label
    _step.__qualname__ = label
    return _step


def route_verdict(state: SurfaceState) -> str:
    """The conditional router — its name is the edge's declared ``condition`` string."""
    return _trip("builder-surface.route_verdict")  # type: ignore[no-any-return]


def build_surface() -> Any:
    """The rich cell-stable builder surface: router, retry, Σ shapes, escaping, lists.

    Two START edges make ``entry`` a list; two END edges make ``finish`` a list.
    ``review/step`` carries the ``/`` the §5.1 grammar escapes. The router contributes a
    ``conditional`` edge with a ``condition`` string and a ``path_map``; the retried node
    carries the §3.2 ``retry_policy`` projection.
    """
    builder = StateGraph(SurfaceState, input_schema=SurfaceInput)
    builder.add_node("triage", _surface_node("builder-surface.triage"))
    builder.add_node("archive", _surface_node("builder-surface.archive"))
    builder.add_node("review/step", _surface_node("builder-surface.review_step"))
    builder.add_node(
        "retry_fetch",
        _surface_node("builder-surface.retry_fetch"),
        retry_policy=RetryPolicy(max_attempts=4, retry_on=(ValueError, KeyError)),
    )
    builder.add_edge(START, "triage")
    builder.add_edge(START, "archive")
    builder.add_conditional_edges(
        "triage",
        route_verdict,
        {"deep": "review/step", "shallow": "retry_fetch"},
    )
    builder.add_edge("review/step", "retry_fetch")
    builder.add_edge("retry_fetch", END)
    builder.add_edge("archive", END)
    return builder


# ── builder-send ─────────────────────────────────────────────────────────────────────────


class FanState(TypedDict):
    legs: list[str]
    booked: Annotated[list[str], operator.add]


def _plan_legs(state: FanState) -> dict[str, Any]:
    return _trip("builder-send.plan_legs")  # type: ignore[no-any-return]


def _book_leg(state: FanState) -> dict[str, Any]:
    return _trip("builder-send.book_leg")  # type: ignore[no-any-return]


def _confirm(state: FanState) -> dict[str, Any]:
    return _trip("builder-send.confirm")  # type: ignore[no-any-return]


def route_legs(state: FanState) -> list[Send]:
    """Hinted ``-> list[Send]`` with declared targets — §6 classifies the wiring ``send``."""
    return _trip("builder-send.route_legs")  # type: ignore[no-any-return]


def build_send() -> StateGraph[FanState]:
    builder = StateGraph(FanState)
    builder.add_node("plan_legs", _plan_legs)
    builder.add_node("book_leg", _book_leg)
    builder.add_node("confirm", _confirm)
    builder.add_edge(START, "plan_legs")
    builder.add_conditional_edges("plan_legs", route_legs, ["book_leg", "confirm"])
    builder.add_edge("book_leg", "confirm")
    builder.add_edge("confirm", END)
    return builder


# ── builder-dynamic ──────────────────────────────────────────────────────────────────────


def dispatch_legs(state: FanState) -> Send:
    """Hinted ``-> Send`` and declaring no targets — the ruled ``kind: dynamic`` (DEC-28)."""
    return _trip("builder-dynamic.dispatch_legs")  # type: ignore[no-any-return]


def build_dynamic() -> StateGraph[FanState]:
    """An ``ir_version`` ``"1.1"`` document: the one edge kind outside the 1.0 vocabulary."""
    builder = StateGraph(FanState)
    builder.add_node("plan_legs", _plan_legs)
    builder.add_node("book_leg", _book_leg)
    builder.add_edge(START, "plan_legs")
    builder.add_conditional_edges("plan_legs", dispatch_legs)
    builder.add_edge("book_leg", END)
    return builder


# ── compiled-runtime ─────────────────────────────────────────────────────────────────────


def build_gated() -> Any:
    """A compiled graph with interrupt gates and a checkpointer — the §3.7 runtime block.

    ``compile()`` is graph construction, not execution (INTROSPECTION-SPEC §4), and it is
    called inside this factory only — importing the module compiles nothing.
    """

    class GatedState(TypedDict):
        query: str
        answer: str

    def _triage(state: GatedState) -> dict[str, str]:
        return _trip("compiled-runtime.triage")  # type: ignore[no-any-return]

    def _execute(state: GatedState) -> dict[str, str]:
        return _trip("compiled-runtime.execute")  # type: ignore[no-any-return]

    def _report(state: GatedState) -> dict[str, str]:
        return _trip("compiled-runtime.report")  # type: ignore[no-any-return]

    builder = StateGraph(GatedState)
    builder.add_node("triage", _triage)
    builder.add_node("execute", _execute)
    builder.add_node("report", _report)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", "execute")
    builder.add_edge("execute", "report")
    builder.add_edge("report", END)
    return builder.compile(
        interrupt_before=["execute"],
        interrupt_after=["triage"],
        checkpointer=InMemorySaver(),
    )


# ── lcel-composite ───────────────────────────────────────────────────────────────────────

#: The runnable a lambda body names — the §5 ``deps`` walk resolves this module-global
#: reference without ever calling anything.
CAPTURED_FORMATTER: Final[Runnable[Any, Any]] = RunnableLambda(
    lambda value: _trip("lcel-composite.captured_formatter")
)


def _digest_topic(value: Any) -> Any:
    _trip("lcel-composite.digest_topic")
    return CAPTURED_FORMATTER.invoke(value)


def _wants_prose(value: Any) -> bool:
    """A ``RunnableBranch`` condition — an opaque guard, never a fragment child (§6)."""
    return _trip("lcel-composite.wants_prose")  # type: ignore[no-any-return]


def build_composite() -> Runnable[Any, Any]:
    """A model-free stock composition: seq, map, lambda + dep, branch, retry, bind.

    The prompt leaf carries the one digest slot that is stable across every matrix cell
    (``prompt_digest`` — the (b) projection reads template content, not ``model_fields``).
    """
    prompt = ChatPromptTemplate.from_messages(
        [("system", "Summarize {topic} in one paragraph."), ("human", "{topic}")]
    )
    fanout: Runnable[Any, Any] = RunnableParallel(
        digest=RunnableLambda(_digest_topic),
        verbatim=RunnablePassthrough(),
        prose=RunnableBranch(
            (_wants_prose, StrOutputParser()),
            RunnablePassthrough(),
        ),
        tagged=StrOutputParser().with_config({"tags": ["conformance"]}),
    )
    finisher: Runnable[Any, Any] = StrOutputParser().with_retry(stop_after_attempt=3)
    chain: Runnable[Any, Any] = prompt | fanout
    return chain | finisher


# ── lcel-tool-bound ──────────────────────────────────────────────────────────────────────


class ConformanceChatModel(BaseChatModel):
    """A chat model whose declared fields are the config surface and whose every
    invokable member raises — mirror of the digest suite's armed-model posture.

    The §7.4 (c) projection reads ``model_fields`` values and nothing else; the inherited
    ``BaseChatModel`` fields ride along, which is exactly why this workflow's golden is
    substrate-version-gated (§7.4 (e)).
    """

    temperature: float = 0.2
    seed: int = 7

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _trip("lcel-tool-bound.model._generate")  # type: ignore[no-any-return]

    def _stream(self, *args: Any, **kwargs: Any) -> Any:
        return _trip("lcel-tool-bound.model._stream")

    @property
    def _llm_type(self) -> str:
        return _trip("lcel-tool-bound.model._llm_type")  # type: ignore[no-any-return]

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return _trip("lcel-tool-bound.model._identifying_params")  # type: ignore[no-any-return]

    @property
    def lc_attributes(self) -> dict[str, Any]:
        return _trip("lcel-tool-bound.model.lc_attributes")  # type: ignore[no-any-return]

    @property
    def lc_secrets(self) -> dict[str, str]:
        return _trip("lcel-tool-bound.model.lc_secrets")  # type: ignore[no-any-return]


#: The bound tool, as the JSON-schema dict a provider's ``bind_tools`` produces — the
#: mainstream shape, digested member for member (DEC-21 coercion K).
BOOKING_TOOL_SCHEMA: Final[dict[str, Any]] = {
    "type": "function",
    "function": {
        "name": "book_flight",
        "description": "Book one flight leg.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["origin", "destination"],
        },
    },
}


def build_tool_bound() -> Runnable[Any, Any]:
    """``prompt | model.bind(tools=[…])`` — the EX-16 admission, golden-gated by substrate."""
    prompt = ChatPromptTemplate.from_messages(
        [("system", "You are a terse booking agent."), ("human", "{request}")]
    )
    model = ConformanceChatModel()
    return prompt | model.bind(tools=[BOOKING_TOOL_SCHEMA])


# ── annotations-resolved ─────────────────────────────────────────────────────────────────


class ResolvedState(TypedDict):
    query: str
    plan: str
    ledger: list[str]
    summary: str


class TopicOnly(TypedDict):
    """A projection of :class:`ResolvedState` — §4's licensed ``input`` pattern (a)."""

    query: str


@gebra.contract(reads=["query"], writes=["plan"], effects=["network"], deterministic={"seed": 11})
def _declared_step(state: ResolvedState) -> dict[str, Any]:
    """Tier 1: the decorator declaration, four slots strong."""
    return _trip("annotations-resolved.declared_step")  # type: ignore[no-any-return]


def _filed_step(state: ResolvedState) -> dict[str, Any]:
    """Tier 3: every slot here comes from :data:`RESOLVED_SIDECAR`."""
    return _trip("annotations-resolved.filed_step")  # type: ignore[no-any-return]


def _inferred_step(state: TopicOnly) -> dict[str, Any]:
    """Tier 4: a projection annotation and a literal dict return — both licensed by §4."""
    _trip("annotations-resolved.inferred_step")
    return {"summary": "…"}


def _opaque_body(value: Any) -> Any:
    return _trip("annotations-resolved.opaque_body")


# Written without a docstring on purpose: pydantic serializes one into the JSON Schema as
# `description`, and this class's schema lands in a committed golden (WA-05).
class LookupArgs(BaseModel):
    key: str
    limit: int = 3


def _lookup_impl(key: str, limit: int = 3) -> str:
    """The tool's implementation — a tool is read, never invoked (§1)."""
    return _trip("annotations-resolved.search_tool.impl")  # type: ignore[no-any-return]


def _search_tool() -> StructuredTool:
    """Tier 2: an author-written ``args_schema``, read by pydantic introspection only."""
    return StructuredTool(
        name="search_tool",
        description="Lookup. Never invoked.",
        args_schema=LookupArgs,
        func=_lookup_impl,
    )


def _plain_step(state: ResolvedState) -> dict[str, Any]:
    """The undeclared default: no declaration, and the return site is a helper call."""
    return _trip("annotations-resolved.plain_step")  # type: ignore[no-any-return]


#: The sidecar for ``annotations-resolved``, written to a temporary directory by the suite
#: and handed to ``extract(..., sidecar=...)`` — never discovered ambiently.
RESOLVED_SIDECAR: Final = """\
schema = "gebra-sidecar-v1"

[nodes.filed_step]
reads        = ["query"]
writes       = ["ledger"]
effects      = ["write"]
idempotent   = { key = "query" }
compensation = { hook = "declared_step" }
"""


def build_resolved() -> StateGraph[ResolvedState]:
    builder = StateGraph(ResolvedState)
    builder.add_node("declared_step", _declared_step)
    builder.add_node("filed_step", _filed_step)
    builder.add_node("inferred_step", _inferred_step)
    builder.add_node("opaque_step", RunnableLambda(_opaque_body))
    builder.add_node("search_tool", _search_tool())  # type: ignore[type-var]
    builder.add_node("plain_step", _plain_step)
    builder.add_edge(START, "declared_step")
    builder.add_edge("declared_step", "filed_step")
    builder.add_edge("filed_step", "inferred_step")
    builder.add_edge("inferred_step", "opaque_step")
    builder.add_edge("opaque_step", "search_tool")
    builder.add_edge("search_tool", "plain_step")
    builder.add_edge("plain_step", END)
    return builder


# ── The registry ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubstrateGate:
    """Why one golden comparison is version-gated, in EX-17's named-skip discipline."""

    available: bool
    reason: str


#: The exact langchain-core release the ``lcel-tool-bound`` golden was taken at — the
#: locked development pin. A lock bump that moves langchain-core retakes that golden in the
#: same commit (the WA-05 justification is the bump itself; see the golden README).
TOOL_BOUND_CORE_PIN: Final = (
    1,
    5,
    3,
)  # cell 3's ruled pin (PD-030 §C3); aligned at PD-049's lock regen

#: The one gate in the set. The tool-bound chain's canonical bytes contain the model's
#: ``config_digest``, which projects the installed core's ``model_fields`` (§7.4 (c)) —
#: and from core 1.4.7 the ``metadata`` field is filled at construction with
#: ``lc_versions``, **the installed core's own version string** (merged in even over an
#: explicitly passed ``metadata``). Every core release therefore moves this digest, which
#: is §7.4 (e)'s ruled substrate-version movement observed at its sharpest. A byte golden
#: can hold only at the exact release it was taken at, so the gate is equality with the
#: locked development pin — not a floor. VERSION-COMPAT cell 3 deliberately floats
#: ("1.2.latest", re-resolved per PD-030 Q2), so on a matrix cell ahead of the lock this
#: comparison skips by name; the extraction *capability* for tool-bound chains stays tested
#: on every cell by ``tests/extraction/test_digests.py``/``test_stock.py``, which compute
#: their expectations from the installed substrate rather than from committed bytes.
TOOL_BOUND_GATE: Final = SubstrateGate(
    available=substrate.LANGCHAIN_CORE_VERSION == TOOL_BOUND_CORE_PIN,
    reason=(
        "this golden's config_digest embeds metadata.lc_versions — the installed "
        "langchain-core's own version string, filled at construction from core 1.4.7 — so "
        "the committed bytes hold only at the exact release they were taken at: "
        f"langchain-core {'.'.join(map(str, TOOL_BOUND_CORE_PIN))}, the locked development "
        "pin; installed langchain-core is "
        f"{'.'.join(map(str, substrate.LANGCHAIN_CORE_VERSION))}"
    ),
)


@dataclass(frozen=True)
class ConformanceCase:
    """One live extraction fixture: a source program plus what the suite needs to run it."""

    family: str
    """The INTROSPECTION-SPEC §2 object family: ``builder`` | ``compiled`` | ``lcel``."""
    build: Any
    """Zero-argument factory for the workflow object. Never called at import time."""
    sidecar: str | None = None
    """``gebra.toml`` text to write and pass explicitly, or ``None`` for no sidecar."""
    gate: SubstrateGate | None = None
    """A substrate gate on the *golden comparison*, or ``None`` when it holds everywhere."""


CASES: Final[dict[str, ConformanceCase]] = {
    "builder-linear": ConformanceCase(family="builder", build=build_linear),
    "builder-surface": ConformanceCase(family="builder", build=build_surface),
    "builder-send": ConformanceCase(family="builder", build=build_send),
    "builder-dynamic": ConformanceCase(family="builder", build=build_dynamic),
    "compiled-runtime": ConformanceCase(family="compiled", build=build_gated),
    "lcel-composite": ConformanceCase(family="lcel", build=build_composite),
    "lcel-tool-bound": ConformanceCase(family="lcel", build=build_tool_bound, gate=TOOL_BOUND_GATE),
    "annotations-resolved": ConformanceCase(
        family="builder", build=build_resolved, sidecar=RESOLVED_SIDECAR
    ),
}
