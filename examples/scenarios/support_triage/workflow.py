"""A triage path that reads what nothing wrote — the P-04 scenario (card REL-06).

A support ticket is classified and routed: an FAQ is summarised and answered automatically,
and the automatic reply hands over to a human when the model is not confident; anything
that is not an FAQ goes to the human queue directly. ``escalate`` reads ``summary`` — a key
only ``summarize`` writes, and ``summarize`` is on one of the two paths to it, not both.
Every key *is* written by some node, which is exactly why a reviewer misses this shape; P-04
asks the stronger question — is the key written on **every** path that reaches the reader —
and reports a FATAL ``read-key-never-written-on-path`` at the reader and the key, with the
path that arrives without it and the writer that covers the other one.

The fix is a wiring change rather than an annotation: ``build_support_triage_summary_first``
summarises before routing, so both paths to ``escalate`` write ``summary``. The node bodies
are unchanged. P-04 reads ``StateGraph(..., input_schema=TicketIn)``'s declared input — the
one key the caller supplies — as written at START; without that declaration every key of the
state would count as an input and the property would have nothing to check.

Every node body and router here records itself in ``TRIPPED`` and raises. gebra reads the
definition and never runs it, and the ledger is how this scenario's tests and its page hold
that claim rather than state it (WA-07). Run as a script, this file extracts and verifies the
seeded graph and prints the verdict; imported, it defines the graph and nothing runs.
"""

from typing import Any, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from gebra.verify import DataflowLocation, P04Failure, PropertyReport, verify

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


class TriageState(TypedDict):
    ticket: str
    category: str
    summary: str
    reply: str
    assignee: str


class TicketIn(TypedDict):
    """The graph input — the one key the caller supplies."""

    ticket: str


@gebra.contract(reads=("ticket",), writes=("category",), effects=("external", "network"))
def classify(state: TriageState) -> dict[str, str]:
    """Ask the model which kind of ticket this is."""
    _trip("classify")


@gebra.contract(reads=("ticket",), writes=("summary",), effects=("external", "network"))
def summarize(state: TriageState) -> dict[str, str]:
    """Ask the model for a one-paragraph summary of the ticket."""
    _trip("summarize")


@gebra.contract(reads=("category", "summary"), writes=("reply",), effects=("external", "network"))
def auto_reply(state: TriageState) -> dict[str, str]:
    """Draft the automatic reply — and send it, or hand over if the model is not confident."""
    _trip("auto_reply")


@gebra.contract(
    reads=("category", "summary"), writes=("assignee",), effects=("external", "network")
)
def escalate(state: TriageState) -> dict[str, str]:
    """Open the ticket in the human queue, summary attached."""
    _trip("escalate")


def route_ticket(state: TriageState) -> str:
    """``faq`` for the automatic path, ``human`` for the escalation."""
    _trip("route_ticket")


def route_reply(state: TriageState) -> str:
    """``sent`` when the reply went out, ``unsure`` to hand the ticket to a human."""
    _trip("route_reply")


def _builder() -> Any:
    builder = StateGraph(TriageState, input_schema=TicketIn)
    builder.add_node("classify", classify)
    builder.add_node("summarize", summarize)
    builder.add_node("auto_reply", auto_reply)
    builder.add_node("escalate", escalate)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("auto_reply", route_reply, {"sent": END, "unsure": "escalate"})
    builder.add_edge("escalate", END)
    return builder


def build_support_triage() -> Any:
    """The seeded scenario: the ``human`` label skips the summariser."""
    builder = _builder()
    builder.add_conditional_edges(
        "classify", route_ticket, {"faq": "summarize", "human": "escalate"}
    )
    builder.add_edge("summarize", "auto_reply")
    return builder


def build_support_triage_summary_first() -> Any:
    """The fix: summarise first, then route — every path to ``escalate`` writes ``summary``."""
    builder = _builder()
    builder.add_edge("classify", "summarize")
    builder.add_conditional_edges(
        "summarize", route_ticket, {"faq": "auto_reply", "human": "escalate"}
    )
    return builder


def main() -> None:
    """Extract and verify the seeded graph, print the verdict, and show that nothing ran."""
    report = verify(gebra.extract(build_support_triage()).ir)
    gate = report.gate
    print(f"gate             {gate.outcome} — exit {gate.exit_code}")

    outcome = report.outcome_for("dataflow-completeness")
    assert isinstance(outcome, PropertyReport) and isinstance(outcome.failure, P04Failure)
    failure = outcome.failure
    location = failure.location
    assert isinstance(location, DataflowLocation)
    print(
        f"finding          {failure.severity.upper()} {failure.property_condition} "
        f"[{failure.claim_class}] on {outcome.property}"
    )
    print(f"reader           {location.node} reads {location.key!r}")
    print(f"path             {' -> '.join(location.path)}")
    print(f"other paths      written by {', '.join(failure.writers_on_other_paths or ())}")

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
