"""The consolidated never-invokes adversarial suite (WA-07; INTROSPECTION-SPEC §1 rule 4).

INTROSPECTION-SPEC §1 rule 4 names four hazards a conforming extractor must trap, over and
above node/router/tool bodies: **pydantic validator execution**, **``__init_subclass__``
hooks**, **decorator side effects**, and **string / forward-reference annotation evaluation**
(``typing.get_type_hints()``, rule 3). Each is covered in depth by the path whose reads reach
it — the state path (:mod:`tests.extraction.test_state`), the routing path
(:mod:`tests.extraction.test_routing`), the contract-resolution path
(:mod:`tests.extraction.test_contracts`) and the decorator surface
(:mod:`tests.annotations.test_decorators`) — each with its own guarded subprocess and armed
controls.

This module is the *consolidated* surface the card (EX-13) merges: one deliberately hostile
workflow that carries all four hazards **at once**, extracted through the public
``gebra.extract()`` for both the builder (§3) and the compiled (§4) family, asserting the one
shared record :data:`FIRED` stays empty. A single workflow packing every hazard is a stronger
statement than four separate ones, because a regression that armed one path by disarming a
shared read would still have to keep this one green.

Every fixture here is import-safe: importing the module builds nothing that runs, and the one
side effect a decorator legitimately has — firing **once, at decoration time** — is recorded so
the tests can assert extraction adds nothing to it. Nothing here contacts a network, an LLM, or
a node body; the seeded-execution test at the bottom is what proves the invariant these tests
rest on is not vacuous — a sentinel that *does* run turns the record non-empty and fails the
suite.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError, field_validator, model_validator

import gebra
from tests.sample_workflows import sentinel_graph as sg

#: Every hazard a fixture here would fire, recorded **before** it does anything else. The suite's
#: whole claim is that this list is empty after extraction; the seeded-execution test proves a
#: non-empty list is what fails the suite.
FIRED: list[str] = []


class HostileState(BaseModel):
    """A pydantic state whose validators and ``__init_subclass__`` are all sentinels.

    Two of §1 rule 4's four hazards live here. Constructing or validating an instance runs the
    field and model validators; subclassing the type runs ``__init_subclass__``. Extraction reads
    ``model_fields`` — class-level metadata — and does neither, which is what keeps :data:`FIRED`
    empty.
    """

    query: str
    note: str = "none"

    @field_validator("query")
    @classmethod
    def _never_validates_field(cls, value: str) -> str:
        FIRED.append("pydantic-field-validator")
        raise AssertionError("a pydantic field validator ran during extraction")

    @model_validator(mode="after")
    def _never_validates_model(self) -> HostileState:
        FIRED.append("pydantic-model-validator")
        raise AssertionError("a pydantic model validator ran during extraction")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        FIRED.append("__init_subclass__")
        super().__init_subclass__(**kwargs)


def _side_effecting(function: Callable[..., Any]) -> Callable[..., Any]:
    """A decorator with a side effect at application, and another if the wrapper is ever called.

    The application side effect fires **once**, when this module is imported and the node below is
    defined — that is what "decorator side effects at import" means, and it is unavoidable and
    correct: decoration happens when the author writes the workflow, long before ``extract()``
    sees it. The hazard extraction owns is *re-running* it, or calling the wrapped body; neither
    happens, so the ``decorated-body`` entry never appears.
    """
    FIRED.append(f"decorator-applied:{function.__name__}")

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        FIRED.append(f"decorated-body:{function.__name__}")
        return function(*args, **kwargs)

    return wrapper


@_side_effecting
def plan_step(state: HostileState) -> dict[str, str]:
    raise sg.SentinelExecutedError("node 'plan_step' was invoked — extraction never calls nodes")


def act_step(state: HostileState) -> dict[str, str]:
    raise sg.SentinelExecutedError("node 'act_step' was invoked — extraction never calls nodes")


def route_with_string_hint(state: HostileState) -> str:
    raise sg.SentinelExecutedError("router was invoked — extraction never calls routers")


# `from __future__ import annotations` makes every annotation in this module a *string* at
# runtime, so the router's `-> str` return hint is stored as the forward reference `"str"` that
# `get_type_hints()` must evaluate — §1 rule 3's fourth hazard. Extraction reads the hint to
# classify the edge (EX-03) and never calls the body, which is the honest boundary: annotation
# *expressions* may be evaluated (rule 3 licenses it, in module namespace, degrading failures),
# node/router *bodies* never.
DECORATION_AT_IMPORT = ("decorator-applied:plan_step",)


def build_hostile_builder() -> StateGraph[HostileState]:
    """One §3 builder carrying all four §1 rule 4 hazards at once."""
    builder: StateGraph[HostileState] = StateGraph(HostileState)
    builder.add_node("plan_step", plan_step)
    builder.add_node("act_step", act_step)
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", route_with_string_hint, {"go": "act_step"})
    builder.add_edge("act_step", END)
    return builder


@pytest.fixture(autouse=True)
def _reset_fired() -> Any:
    """Start each test from the import-time record so every test's assertions stand on their own.

    The control tests below *deliberately* fire a hazard to prove it is armed, so the record is
    reset per test rather than asserted at teardown; the end-to-end and seeded tests make the
    ``FIRED == list(DECORATION_AT_IMPORT)`` assertion explicitly, where it is the claim.
    """
    FIRED.clear()
    FIRED.extend(DECORATION_AT_IMPORT)
    yield


def test_the_import_time_decoration_is_the_only_side_effect() -> None:
    """Baseline: defining the workflow fires the decorator once and nothing else."""
    assert FIRED == list(DECORATION_AT_IMPORT)


@pytest.mark.parametrize("family", ["builder", "compiled"])
def test_the_named_four_hazards_never_fire_end_to_end(family: str) -> None:
    """Extracting the hostile workflow fires none of §1 rule 4's four hazards.

    Both families, because §3 reads the builder's declarative record and §4 additionally draws
    the compiled graph symbolically — different reads, the same invariant. A pass is the empty
    record: no validator ran, the state was never subclassed, the decorator was never re-applied
    or its body called, and evaluating the router's string return hint reached no body.
    """
    workflow: object = build_hostile_builder()
    if family == "compiled":
        workflow = build_hostile_builder().compile()

    envelope = gebra.extract(workflow)

    assert [node.id for node in envelope.ir.nodes] == ["act_step", "plan_step"]
    assert envelope.graph_version().startswith("sha256:")
    assert FIRED == list(DECORATION_AT_IMPORT), FIRED


def test_extraction_reads_the_string_return_hint_without_running_the_router() -> None:
    """The string/forward-ref vector, on the surface that reads it: EX-03 edge classification.

    The router's ``-> "str"`` is a forward reference; extraction resolves it to classify the
    conditional edge and never calls the router. So the hint is read (the edge is classified) and
    the body is not (the record stays empty) — rule 3's licensed evaluation and its forbidden
    invocation, told apart.
    """
    from gebra.ir.models import ConditionalEdge

    envelope = gebra.extract(build_hostile_builder())

    conditional = [edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)]
    assert conditional and conditional[0].from_ == "plan_step"
    assert FIRED == list(DECORATION_AT_IMPORT)


# ── the vectors are armed: each seed fires when exercised directly ────────────────────────


def test_the_pydantic_validators_are_armed() -> None:
    """Validating the state runs a validator — so "extraction never validates" is a real claim."""
    with pytest.raises(ValidationError):
        HostileState(query="x")
    assert any(entry.startswith("pydantic-") for entry in FIRED), FIRED


def test_the_init_subclass_hook_is_armed() -> None:
    """Subclassing the state runs ``__init_subclass__`` — so "extraction never subclasses" is real."""

    class _Probe(HostileState):
        pass

    assert "__init_subclass__" in FIRED


def test_the_decorated_body_is_armed() -> None:
    """Calling the decorated node runs the wrapper's side effect and then the sentinel body."""
    with pytest.raises(sg.SentinelExecutedError):
        plan_step(HostileState.model_construct())
    assert "decorated-body:plan_step" in FIRED


def test_the_router_body_is_armed() -> None:
    """Calling the router runs its sentinel — the body extraction reads the hint off but never runs."""
    with pytest.raises(sg.SentinelExecutedError):
        route_with_string_hint(HostileState.model_construct())


# ── the seeded-execution test: a sentinel that runs fails the suite ───────────────────────


def test_a_seeded_execution_is_caught_by_the_invariant() -> None:
    """Acceptance box 3, consolidated: if a sentinel executes, the suite's invariant fails.

    The invariant every test above rests on is ``FIRED == list(DECORATION_AT_IMPORT)``. This
    seeds an execution — it calls a body the way a regressed extractor would have — and shows the
    invariant is exactly what catches it: the record is no longer the import-time baseline. A
    tripwire nobody can trip proves nothing, and this is the proof this suite's can be tripped.

    It is the in-process, consolidated counterpart of the per-path guarded children, each of
    which seeds an execution in a fresh interpreter and asserts a non-zero exit
    (``tests/extraction/test_compiled.py::test_each_raiser_is_armed`` and its siblings).
    """
    baseline = list(DECORATION_AT_IMPORT)
    assert FIRED == baseline  # the invariant holds before the seed

    # Seed an execution through a body that records: the decorated node's wrapper appends before
    # it raises, which is exactly the trace a regressed extractor calling it would leave.
    with pytest.raises(sg.SentinelExecutedError):
        plan_step(HostileState.model_construct())

    # The seed ran, so the invariant the suite asserts would now fail — which is the whole point.
    assert FIRED != baseline
    assert "decorated-body:plan_step" in FIRED
