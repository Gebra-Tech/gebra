"""A research loop with no declared bound — the P-02 scenario (card REL-06).

Search, draft, reflect, and go round again until the reflection is satisfied: the shape most
research agents take, and the shape PROPERTY-CATALOG-SPEC §2.2 uses for P-02's own failure
example. The router decides ``revise`` or ``done`` from the model's judgement, and nothing in
the definition declares a bound on that loop — no loop-variant annotation, no justified
``recursion_limit``, no counter guard on the router's declared condition. P-02 reports
**witness absence**: a FATAL ``cycle-without-termination-witness`` on the three-node
component. It does not say the loop fails to terminate; that is not a question reading the
definition can answer.

The fix is one annotation. ``reflect_bounded`` is the same node carrying
``@gebra.variant(key="budget", measure=...)`` — form (c) of TERMINATION-WITNESS-SPEC §2: the
author attests a well-founded measure over ``budget`` that strictly decreases on every
execution of the carrier, and every simple cycle through the carrier is discharged by it.
Attested, never checked: gebra records that the definition names a bound.

Every node body and router here records itself in ``TRIPPED`` and raises. gebra reads the
definition and never runs it, and the ledger is how this scenario's tests and its page hold
that claim rather than state it (WA-07). Run as a script, this file extracts and verifies the
seeded graph and prints the verdict; imported, it defines the graph and nothing runs.
"""

from typing import Any, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from gebra.verify import P02SccLocation, PropertyReport, verify

#: Every body that was reached, recorded before it raises — the never-invokes ledger.
TRIPPED: list[str] = []


class ScenarioSentinelError(BaseException):
    """Raised by any node or router body here that gets invoked.

    ``BaseException`` rather than ``Exception``, so that no ``except Exception`` guard on the
    way can swallow it into a warning: a body here that runs fails whatever ran it.
    """


def _trip(label: str) -> NoReturn:
    """Record ``label`` in the ledger and raise — the whole body of every callable below."""
    TRIPPED.append(label)
    raise ScenarioSentinelError(f"{label!r} was invoked — nothing in this scenario may run")


class ResearchState(TypedDict):
    question: str
    budget: int
    notes: str
    draft: str
    answer: str


class ResearchRequest(TypedDict):
    """The graph input — what the caller supplies. Declared, so P-04 has something to check."""

    question: str
    budget: int


@gebra.contract(reads=("question",), writes=("notes",), effects=("network",))
def search(state: ResearchState) -> dict[str, str]:
    """Query the search backend for material on the question."""
    _trip("search")


@gebra.contract(reads=("question", "notes"), writes=("draft",), effects=("external", "network"))
def draft(state: ResearchState) -> dict[str, str]:
    """Ask the model for a draft answer over the notes."""
    _trip("draft")


@gebra.contract(reads=("draft", "budget"), writes=("budget",), effects=("external", "network"))
def reflect(state: ResearchState) -> dict[str, int]:
    """Ask the model whether the draft is good enough — the loop's re-entry decision."""
    _trip("reflect")


@gebra.contract(reads=("draft", "budget"), writes=("budget",), effects=("external", "network"))
@gebra.variant(key="budget", measure="budget strictly decreases on every reflection")
def reflect_bounded(state: ResearchState) -> dict[str, int]:
    """The same node carrying the loop variant — the fix."""
    _trip("reflect_bounded")


@gebra.contract(reads=("draft",), writes=("answer",), effects=())
def finalize(state: ResearchState) -> dict[str, str]:
    """Publish the draft as the answer."""
    _trip("finalize")


def route_reflection(state: ResearchState) -> str:
    """``revise`` to search again or ``done`` to finalize, on the model's judgement."""
    _trip("route_reflection")


def _wire(builder: Any, reflection: Any) -> Any:
    """The loop: search -> draft -> reflect, and round again on ``revise``."""
    builder.add_node("search", search)
    builder.add_node("draft", draft)
    builder.add_node("reflect", reflection)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "search")
    builder.add_edge("search", "draft")
    builder.add_edge("draft", "reflect")
    builder.add_conditional_edges(
        "reflect", route_reflection, {"revise": "search", "done": "finalize"}
    )
    builder.add_edge("finalize", END)
    return builder


def build_research_loop() -> Any:
    """The seeded scenario: the loop with no declared bound."""
    return _wire(StateGraph(ResearchState, input_schema=ResearchRequest), reflect)


def build_research_loop_bounded() -> Any:
    """The fix: the same wiring, with the variant-carrying node in ``reflect``'s place."""
    return _wire(StateGraph(ResearchState, input_schema=ResearchRequest), reflect_bounded)


def main() -> None:
    """Extract and verify the seeded graph, print the verdict, and show that nothing ran."""
    report = verify(gebra.extract(build_research_loop()).ir)
    gate = report.gate
    print(f"gate             {gate.outcome} — exit {gate.exit_code}")

    outcome = report.outcome_for("termination-witness")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    location = failure.location
    assert isinstance(location, P02SccLocation)
    print(
        f"finding          {failure.severity.upper()} {failure.property_condition} "
        f"[{failure.claim_class}] on {outcome.property}"
    )
    print(f"component        {', '.join(location.nodes)}")
    print(f"one cycle        {' -> '.join(location.representative_cycle)}")

    passing = [
        f"{other.property} {other.result}"
        for other in report.properties
        if isinstance(other, PropertyReport) and other is not outcome
    ]
    print(f"other verdicts   {' · '.join(passing)}")
    print(f"snapshot         {'eligible' if gate.snapshot_eligible else 'not eligible'}")

    assert TRIPPED == [], TRIPPED
    print(f"node bodies run  {TRIPPED}")


if __name__ == "__main__":
    main()
