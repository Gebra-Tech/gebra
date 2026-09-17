# Use cases: three seeded defects and their verdicts

One scenario is a demonstration; a small portfolio is what lets a reader recognise their own
workflow in one. This page adds three scenarios to the one the
[CI-gating guide](pytest-plugin-and-ci-gating.md) walks through. Each is a small LangGraph
definition in the shape an adopting repository has it, carrying exactly one seeded defect from
the five properties this release checks — and none of them is that guide's own P-06 defect. For
each, the page shows the definition, the verdict gebra reaches on it, what that verdict claims
and does not claim, and the fix, executed.

!!! note "Following along"

    The scenarios are `examples/scenarios/` in this repository — `research_loop/`,
    `support_triage/` and `pipeline_replay/`, each four files: `workflow.py` (the definition,
    which prints its own verdict when run as a script), `test_verdict.py` (that verdict asserted
    through the pytest plugin's fixtures, and the fix gated), a `README.md` and an `__init__.py`.
    Every `workflow.py` and `test_verdict.py` below is the file, byte for byte — held equal by
    `tests/docs/test_use_cases.py` — and each `workflow.py` block is *executed* here: what it
    prints is what its output block shows. CI runs the scenarios a second way too, as a pytest
    suite — `python -m pytest examples/scenarios -q`, a step of the `pip-editable` job.

## How to read a scenario

Every node body and router in these files is one line: it records the node's name in a
module-level `TRIPPED` list and raises. That is not a stub standing in for a body that would go
there; it is the point. gebra reads the definition — the nodes, the edges, the contract each node
declares — and runs none of it, and a ledger that is still empty after extraction and
verification is how the tests and this page hold that claim rather than make it. Every executed
block below ends by asserting the ledger empty and printing it.

The verdicts are read off the run report the same way the
[pytest plugin](pytest-plugin-and-ci-gating.md) and the CLI read it: the gate's outcome and exit
code; the finding with its severity, its condition ID and its claim class; the location the
finding anchors on; and the other properties' verdicts — so "one seeded defect" is a printed fact
rather than a description. Run as a script, each `workflow.py` prints exactly the block shown
under it.

## A research loop with no declared bound

*P-02 `termination-witness` — `cycle-without-termination-witness`, FATAL, claim class
DEFENSIBLE.*

Search, draft, reflect, and go round again until the reflection is satisfied: the shape most
research agents take. The router decides `revise` or `done` from the model's own judgement, and
nothing in the definition says how many laps that can take — no loop-variant annotation, no
justified recursion limit, no counter guard on a declared condition. LangGraph stops a loop the
model never leaves at its recursion limit, and every lap before that is a model call.

<!-- gebra:example id=research-loop-workflow -->
```python
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
```

<!-- gebra:output id=research-loop-workflow -->
```text
gate             fail — exit 1
finding          FATAL cycle-without-termination-witness [defensible] on termination-witness
component        draft, reflect, search
one cycle        draft -> reflect -> search
other verdicts   graph-well-formed pass · dataflow-completeness pass · effect-safety pass · determinism-replay pass
snapshot         not eligible
node bodies run  []
```

**What the verdict says.** P-02 found a strongly connected component — `draft`, `reflect`,
`search` — with no termination witness in any of the three forms the property recognises, and
reports one representative cycle through it. The finding is FATAL, so the gate exits `1` and the
run is not eligible to be snapshotted. Its claim class is DEFENSIBLE: the verdict was decided over
the extracted document alone, with no trusted declaration in the chain. The other four properties
pass, so this is the run's only finding.

**What it does not say.** It does not say the loop fails to terminate. P-02 reports witness
*presence* or *absence* — whether the definition declares a bound — and never whether a run halts,
which is not a question reading the definition can answer. A model that always says `done` after
one lap has the same definition and gets the same finding, and that is the right answer: the
bound exists nowhere gebra can see it.

**The fix.** One annotation on the node the loop runs through. `reflect_bounded` is the same node
carrying `@gebra.variant(key="budget", measure=...)`: an attestation that a measure over the
`budget` key strictly decreases on every execution of that node, which discharges every simple
cycle through it. gebra records the attestation and trusts it — it does not check that `reflect`
really decrements `budget` — and the pass witness says exactly that: the form, the carrier, the
declared measure, and what it discharges.

<!-- gebra:example id=research-loop-fix -->
```python
import gebra
from gebra.verify import PropertyReport, TerminationWitness, VariantSource, verify
from examples.scenarios.research_loop import workflow

report = verify(gebra.extract(workflow.build_research_loop_bounded()).ir)
print(f"gate             {report.gate.outcome} — exit {report.gate.exit_code}")

outcome = report.outcome_for("termination-witness")
assert isinstance(outcome, PropertyReport) and isinstance(outcome.witness, TerminationWitness)
for entry in outcome.witness.inventory:
    assert isinstance(entry.source, VariantSource)
    carrier, variant = entry.element.node, entry.source.variant
    print(f"witness          form ({entry.form}) on {carrier}: variant over {variant.key!r}")
    print(f"measure          {variant.measure!r} — attested, never checked")
    print(f"discharges       {entry.discharges}")
for cycle in outcome.witness.cycles.cycles:
    print(f"cycle            {' -> '.join(cycle)}")

assert workflow.TRIPPED == [], workflow.TRIPPED
print(f"node bodies run  {workflow.TRIPPED}")
```

<!-- gebra:output id=research-loop-fix -->
```text
gate             pass — exit 0
witness          form (c) on reflect: variant over 'budget'
measure          'budget strictly decreases on every reflection' — attested, never checked
discharges       all-simple-cycles-through-element
cycle            draft -> reflect -> search
node bodies run  []
```

**What the tests assert.** `test_verdict.py` overrides `gebra_workflow` with the seeded graph,
so `gebra_verification` is the run above. It asserts the finding's condition, severity, claim
class and anchor; that it is the run's only finding, with no extraction warning; and that the
bounded variant passes with the witness shown — then marks the bounded variant with
`@pytest.mark.gebra`, so the fix is gated the way CI gates it. Nothing is marked red on purpose,
which is what keeps `pytest examples/scenarios` green as a suite.

```python
"""The seeded finding, asserted through the plugin's fixtures — and the fix, gated green.

Override ``gebra_workflow`` and ``gebra_verification`` is the whole verification run over
the scenario's graph. The tests below assert what the use-cases page prints: P-02 reports the
loop's component with no witness, it is the run's only finding, and the same wiring with the
variant-carrying node clears the gate. Nothing here is red on purpose — the seeded graph is
verified through the fixture and asserted to fail, and only the bounded variant is marked —
so ``python -m pytest examples/scenarios -q`` is green as a suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from examples.scenarios.research_loop.workflow import (
    build_research_loop,
    build_research_loop_bounded,
)
from gebra.pytest_plugin import TargetVerification, findings_for, verify_target
from gebra.verify import (
    NodeLocation,
    P02SccLocation,
    PropertyReport,
    TerminationWitness,
    VariantSource,
)


@pytest.fixture
def gebra_workflow() -> Any:
    """The scenario's seeded graph — in your repository, your own builder."""
    return build_research_loop()


def test_the_loop_carries_no_termination_witness(gebra_verification: TargetVerification) -> None:
    """FATAL, DEFENSIBLE, on the three-node component — witness absence, nothing more."""
    report = gebra_verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.snapshot_eligible is False

    outcome = report.outcome_for("termination-witness")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    assert failure.property_condition == "cycle-without-termination-witness"
    assert (failure.severity, failure.claim_class) == ("fatal", "defensible")
    assert isinstance(failure.location, P02SccLocation)
    assert failure.location.nodes == ("draft", "reflect", "search")
    assert failure.location.representative_cycle == ("draft", "reflect", "search")


def test_the_missing_witness_is_the_only_finding(gebra_verification: TargetVerification) -> None:
    """One seeded defect, one finding: every other property passes, warning-free."""
    report = gebra_verification.report
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (1, 0, 0)
    for slug in ("graph-well-formed", "dataflow-completeness", "effect-safety"):
        assert findings_for(report, slug) == (), slug
    assert findings_for(report, "determinism-replay") == ()
    assert gebra_verification.extraction_notes == ()


def test_the_bounded_variant_clears_the_gate() -> None:
    """The fix: one variant on ``reflect`` discharges every simple cycle through it."""
    verification = verify_target(
        build_research_loop_bounded(), name="research_loop_bounded", source=__name__
    )
    report = verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")

    outcome = report.outcome_for("termination-witness")
    assert isinstance(outcome, PropertyReport)
    assert isinstance(outcome.witness, TerminationWitness)
    (entry,) = outcome.witness.inventory
    assert entry.form == "c"
    assert isinstance(entry.element, NodeLocation) and entry.element.node == "reflect"
    assert isinstance(entry.source, VariantSource) and entry.source.variant.key == "budget"
    assert entry.discharges == "all-simple-cycles-through-element"


@pytest.mark.gebra(name="research_loop_bounded")
def test_gebra() -> Any:
    """The fix, gated the way CI gates it: one green item per checked property."""
    return build_research_loop_bounded()
```

## A triage path that reads what nothing wrote

*P-04 `dataflow-completeness` — `read-key-never-written-on-path`, FATAL, claim class
DEFENSIBLE-A.*

A support ticket is classified and routed: an FAQ is summarised and answered automatically, and
the automatic reply hands over to a human when the model is not confident; anything that is not
an FAQ goes to the human queue directly. The escalation node reads the summary. Every key here
*is* written by some node — `summarize` writes `summary` — which is exactly why a review misses
this shape. At run time the `human` label reaches `escalate` with no `summary` in the state, and
what happens next is up to the body: a `KeyError`, or a ticket escalated with nothing attached.

<!-- gebra:example id=support-triage-workflow -->
```python
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
```

<!-- gebra:output id=support-triage-workflow -->
```text
gate             fail — exit 1
finding          FATAL read-key-never-written-on-path [defensible-a] on dataflow-completeness
reader           escalate reads 'summary'
path             START -> classify -> escalate
other paths      written by summarize
other verdicts   graph-well-formed pass · termination-witness pass · effect-safety pass · determinism-replay pass
snapshot         not eligible
node bodies run  []
```

**What the verdict says.** P-04 asks the stronger question — is the key written on *every* path
that reaches the reader — and names the reader, the key, a shortest path that arrives without it
(`START -> classify -> escalate`), and the writer that covers the other path (`summarize`), so
"but I do write that key" is answered on the record. The finding is FATAL, so the gate exits `1`
and the run is not eligible to be snapshotted. Its claim class is DEFENSIBLE-A: the verdict rests
on the reads and writes each node *declares* in its `@gebra.contract` — trusted the way a type
annotation is trusted. gebra checks that the declared reads are covered by declared writes on
every path; it does not check that a body reads or writes what its contract says.

**What it does not say.** Nothing about the FAQ path, where the read is covered. And nothing
about what `escalate` would do with a missing key: the finding is that the definition lets a path
arrive there without it.

**The fix.** A wiring change rather than an annotation: summarise first, then route, so both paths
to `escalate` pass through `summarize`. The node bodies and contracts are unchanged. The pass
witness is a coverage map, one entry per reachable (reader, key) pair naming the writers that
cover it; the two entries for `escalate` are printed.

<!-- gebra:example id=support-triage-fix -->
```python
import gebra
from gebra.verify import DataflowWitness, PropertyReport, verify
from examples.scenarios.support_triage import workflow

report = verify(gebra.extract(workflow.build_support_triage_summary_first()).ir)
print(f"gate             {report.gate.outcome} — exit {report.gate.exit_code}")

outcome = report.outcome_for("dataflow-completeness")
assert isinstance(outcome, PropertyReport) and isinstance(outcome.witness, DataflowWitness)
for entry in outcome.witness.coverage:
    if entry.node == "escalate":
        writers = ", ".join(entry.satisfied_by)
        print(f"covered          {entry.node} reads {entry.key!r} — written by {writers}")

assert workflow.TRIPPED == [], workflow.TRIPPED
print(f"node bodies run  {workflow.TRIPPED}")
```

<!-- gebra:output id=support-triage-fix -->
```text
gate             pass — exit 0
covered          escalate reads 'category' — written by classify
covered          escalate reads 'summary' — written by summarize
node bodies run  []
```

**What the tests assert.** The same shape as the first scenario's: the finding's condition,
severity, claim class, reader, key, path and other-path writer through `gebra_verification`; that
it is the run's only finding; that summarising first passes with both of `escalate`'s reads
covered; and the fixed wiring marked and gated.

```python
"""The seeded finding, asserted through the plugin's fixtures — and the fix, gated green.

Override ``gebra_workflow`` and ``gebra_verification`` is the whole verification run over
the scenario's graph. The tests below assert what the use-cases page prints: P-04 names the
reader, the key and the path that arrives without it, it is the run's only finding, and the
wiring that summarises before routing clears the gate. Nothing here is red on purpose — the
seeded graph is verified through the fixture and asserted to fail, and only the fixed wiring
is marked — so ``python -m pytest examples/scenarios -q`` is green as a suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from examples.scenarios.support_triage.workflow import (
    build_support_triage,
    build_support_triage_summary_first,
)
from gebra.pytest_plugin import TargetVerification, findings_for, verify_target
from gebra.verify import DataflowLocation, DataflowWitness, P04Failure, PropertyReport


@pytest.fixture
def gebra_workflow() -> Any:
    """The scenario's seeded graph — in your repository, your own builder."""
    return build_support_triage()


def test_the_escalation_reads_a_key_its_path_never_writes(
    gebra_verification: TargetVerification,
) -> None:
    """FATAL, DEFENSIBLE-A, at the reader and the key, with the path and the other writer."""
    report = gebra_verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.snapshot_eligible is False

    outcome = report.outcome_for("dataflow-completeness")
    assert isinstance(outcome, PropertyReport) and isinstance(outcome.failure, P04Failure)
    failure = outcome.failure
    assert failure.property_condition == "read-key-never-written-on-path"
    assert (failure.severity, failure.claim_class) == ("fatal", "defensible-a")
    assert isinstance(failure.location, DataflowLocation)
    assert (failure.location.node, failure.location.key) == ("escalate", "summary")
    assert failure.location.path == ("START", "classify", "escalate")
    assert failure.writers_on_other_paths == ("summarize",)


def test_the_unwritten_read_is_the_only_finding(gebra_verification: TargetVerification) -> None:
    """One seeded defect, one finding: every other property passes, warning-free."""
    report = gebra_verification.report
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (1, 0, 0)
    for slug in ("graph-well-formed", "termination-witness", "effect-safety"):
        assert findings_for(report, slug) == (), slug
    assert findings_for(report, "determinism-replay") == ()
    assert gebra_verification.extraction_notes == ()


def test_summarising_first_clears_the_gate() -> None:
    """The fix: every path to ``escalate`` now passes through ``summarize``."""
    verification = verify_target(
        build_support_triage_summary_first(), name="support_triage_summary_first", source=__name__
    )
    report = verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")

    outcome = report.outcome_for("dataflow-completeness")
    assert isinstance(outcome, PropertyReport)
    assert isinstance(outcome.witness, DataflowWitness)
    covered = {
        (entry.node, entry.key): entry.satisfied_by
        for entry in outcome.witness.coverage
        if entry.node == "escalate"
    }
    assert covered == {
        ("escalate", "category"): ("classify",),
        ("escalate", "summary"): ("summarize",),
    }


@pytest.mark.gebra(name="support_triage_summary_first")
def test_gebra() -> Any:
    """The fix, gated the way CI gates it: one green item per checked property."""
    return build_support_triage_summary_first()
```

## A determinism claim the definition cannot back

*P-08 `determinism-replay` — `deterministic-llm-temperature-unpinned`, WARNING, claim class
HEURISTIC.*

A document pipeline: an LLM extracts the fields, a local check validates them, a store records
them. The extraction node is declared `@gebra.deterministic(seed=7)` — the kind of claim a replay
harness or a regression suite leans on — with `external` and `network` among its effects and the
temperature left unpinned. An LLM-backed claim is coherent only in the object form with the seed
pinned *and* the temperature pinned at zero; this one pins half. A replay that relies on it may
see divergence the definition gives it no way to explain.

<!-- gebra:example id=pipeline-replay-workflow -->
```python
"""A determinism claim the definition cannot back — the P-08 scenario (card REL-06).

A document pipeline: an LLM extracts the fields, a local check validates them, a store
records them. The extraction node is declared ``@gebra.deterministic(seed=7)`` — a claim a
replay harness or a regression suite would lean on — with ``external`` and ``network`` among
its effects and the temperature left unpinned. PROPERTY-CATALOG-SPEC §8.2 calls that shape
incoherent: an LLM-backed claim is coherent only in the object form with the seed pinned
*and* ``temperature = 0``. P-08 reports ``deterministic-llm-temperature-unpinned``.

Two things about that finding are the scenario. It is a **WARNING** from a **HEURISTIC**
property, so by default the run exits ``0`` (``pass-with-notes``) and records its snapshot;
``--gebra-strict=determinism-replay`` promotes it and the run exits ``1`` — and the record
itself is unchanged under promotion, still ``warning`` and still ``heuristic``. The fix,
``extract_fields_pinned``, adds ``temperature=0.0``; the pass witness it earns carries a
caveat, because a pinned seed and a pinned temperature are what the *definition* declares
and a provider is free to return something else on replay.

Every node body here records itself in ``TRIPPED`` and raises. gebra reads the definition
and never runs it, and the ledger is how this scenario's tests and its page hold that claim
rather than state it (WA-07). Run as a script, this file extracts and verifies the seeded
graph under both policies and prints the verdicts; imported, it defines the graph and
nothing runs.
"""

from typing import Any, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from gebra.verify import DeterminismNodeLocation, PropertyReport, RunPolicy, StrictPolicy, verify

#: Every body that was reached, recorded before it raises — the never-invokes ledger.
TRIPPED: list[str] = []


class ScenarioSentinelError(BaseException):
    """Raised by any node body here that gets invoked.

    ``BaseException`` rather than ``Exception``, so that no ``except Exception`` guard on the
    way can swallow it into a warning: a body here that runs fails whatever ran it.
    """


def _trip(label: str) -> NoReturn:
    """Record ``label`` in the ledger and raise — the whole body of every callable below."""
    TRIPPED.append(label)
    raise ScenarioSentinelError(f"{label!r} was invoked — nothing in this scenario may run")


class PipelineState(TypedDict):
    document: str
    fields: str
    valid: bool
    record_id: str


class DocumentIn(TypedDict):
    """The graph input — the one key the caller supplies."""

    document: str


@gebra.contract(reads=("document",), writes=("fields",), effects=("external", "network"))
@gebra.deterministic(seed=7)
def extract_fields(state: PipelineState) -> dict[str, str]:
    """Ask the model for the document's fields — claiming seed-only determinism."""
    _trip("extract_fields")


@gebra.contract(reads=("document",), writes=("fields",), effects=("external", "network"))
@gebra.deterministic(seed=7, temperature=0.0)
def extract_fields_pinned(state: PipelineState) -> dict[str, str]:
    """The same node with the temperature pinned — the fix."""
    _trip("extract_fields_pinned")


@gebra.contract(reads=("fields",), writes=("valid",), effects=())
@gebra.deterministic
def validate_fields(state: PipelineState) -> dict[str, bool]:
    """Check the fields locally — a bare claim on a node with no LLM behind it."""
    _trip("validate_fields")


@gebra.contract(reads=("fields", "valid"), writes=("record_id",), effects=("write", "network"))
def store_record(state: PipelineState) -> dict[str, str]:
    """Write the record to the store."""
    _trip("store_record")


def _wire(builder: Any, extraction: Any) -> Any:
    """The pipeline: extract -> validate -> store, straight through."""
    builder.add_node("extract_fields", extraction)
    builder.add_node("validate_fields", validate_fields)
    builder.add_node("store_record", store_record)
    builder.add_edge(START, "extract_fields")
    builder.add_edge("extract_fields", "validate_fields")
    builder.add_edge("validate_fields", "store_record")
    builder.add_edge("store_record", END)
    return builder


def build_pipeline_replay() -> Any:
    """The seeded scenario: the LLM node claims determinism with its temperature unpinned."""
    return _wire(StateGraph(PipelineState, input_schema=DocumentIn), extract_fields)


def build_pipeline_replay_pinned() -> Any:
    """The fix: the same wiring, with the pinned node in ``extract_fields``'s place."""
    return _wire(StateGraph(PipelineState, input_schema=DocumentIn), extract_fields_pinned)


#: What ``--gebra-strict=determinism-replay`` hands ``verify()``: promote this property only.
STRICT_ON_P08 = StrictPolicy(mode="per-property", properties=("determinism-replay",))


def main() -> None:
    """Verify the seeded graph under both policies, print both verdicts, show nothing ran."""
    ir = gebra.extract(build_pipeline_replay()).ir
    default = verify(ir)
    strict = verify(ir, RunPolicy(strict=STRICT_ON_P08))

    gate = default.gate
    print(f"default policy   {gate.outcome} — exit {gate.exit_code}")
    outcome = default.outcome_for("determinism-replay")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    location = failure.location
    assert isinstance(location, DeterminismNodeLocation)
    print(
        f"finding          {failure.severity.upper()} {failure.property_condition} "
        f"[{failure.claim_class}] on {outcome.property}"
    )
    print(f"node             {location.node} — seed {location.seed}, temperature unpinned")
    print(f"remediation      {failure.remediation}")
    print(f"snapshot         {'eligible' if gate.snapshot_eligible else 'not eligible'}")

    promoted = strict.gate.promotions
    print(f"strict policy    {strict.gate.outcome} — exit {strict.gate.exit_code}")
    print(f"promoted         {', '.join(f'{p.property}/{p.origin}' for p in promoted)}")
    record = strict.outcome_for("determinism-replay")
    assert isinstance(record, PropertyReport) and record.failure is not None
    print(f"record under it  {record.failure.severity} [{record.failure.claim_class}] — unchanged")

    passing = [
        f"{other.property} {other.result}"
        for other in default.properties
        if isinstance(other, PropertyReport) and other is not outcome
    ]
    print(f"other verdicts   {' · '.join(passing)}")

    assert TRIPPED == [], TRIPPED
    print(f"node bodies run  {TRIPPED}")


if __name__ == "__main__":
    main()
```

<!-- gebra:output id=pipeline-replay-workflow -->
```text
default policy   pass-with-notes — exit 0
finding          WARNING deterministic-llm-temperature-unpinned [heuristic] on determinism-replay
node             extract_fields — seed 7, temperature unpinned
remediation      The claim is recorded. Replay divergence must be logged, never silently accepted. Keep the annotation if you accept approximate determinism; remove it if replay reproducibility should not be relied on.
snapshot         eligible
strict policy    fail — exit 1
promoted         determinism-replay/failure
record under it  warning [heuristic] — unchanged
other verdicts   graph-well-formed pass · termination-witness pass · dataflow-completeness pass · effect-safety pass
node bodies run  []
```

**What the verdict says.** Two things, and the second is the one that surprises people. The
finding names the node, the seed it pinned and the temperature it did not, and carries the
specification's own remediation paragraph. And it is a WARNING from a HEURISTIC property, so under
the default policy the gate exits `0` — `pass-with-notes`, the finding on record, the snapshot
still eligible. `--gebra-strict=determinism-replay`, the plugin's per-property strict form, is
what turns it into a gate: the same run exits `1` with one promotion, and the record under the
promotion is unchanged — still `warning`, still `heuristic`. Strict mode moves the gate, never
the record.

**What it does not say.** It does not say the node is non-deterministic, and a pinned claim
would not say it is. Determinism of an external provider is not decidable from a definition;
P-08 checks that a claim is *coherent* — that the declaration says what a reproducible call would
need it to say — which is why every P-08 finding is HEURISTIC.

**The fix.** Pin the temperature: `@gebra.deterministic(seed=7, temperature=0.0)`. The pinned
variant passes under both policies, and its witness is a ledger of claims — the LLM-backed one
with both pins and a logged divergence policy, the local one with no pinning required — carrying
a caveat that is the honest-claims boundary in one line: what a provider returns on replay is not
something the definition can promise.

<!-- gebra:example id=pipeline-replay-fix -->
```python
import gebra
from gebra.verify import DeterminismWitness, PropertyReport, RunPolicy, verify
from examples.scenarios.pipeline_replay import workflow

ir = gebra.extract(workflow.build_pipeline_replay_pinned()).ir
default = verify(ir)
strict = verify(ir, RunPolicy(strict=workflow.STRICT_ON_P08))
gate = strict.gate
print(f"default policy   {default.gate.outcome} — exit {default.gate.exit_code}")
print(f"strict policy    {gate.outcome} — exit {gate.exit_code}, promoted {len(gate.promotions)}")

outcome = default.outcome_for("determinism-replay")
assert isinstance(outcome, PropertyReport) and isinstance(outcome.witness, DeterminismWitness)
for claim in outcome.witness.claims:
    if claim.llm_backed:
        pins = f"seed {claim.seed}, temperature {claim.temperature}"
        pins += f", divergence {claim.divergence_handling}"
    else:
        pins = f"{claim.basis}, pinning required {claim.pinning_required}"
    print(f"claim            {claim.node}: {pins}")
print(f"caveat           {outcome.witness.caveat}")

assert workflow.TRIPPED == [], workflow.TRIPPED
print(f"node bodies run  {workflow.TRIPPED}")
```

<!-- gebra:output id=pipeline-replay-fix -->
```text
default policy   pass — exit 0
strict policy    pass — exit 0, promoted 0
claim            extract_fields: seed 7, temperature 0.0, divergence logged
claim            validate_fields: pure-local-computation, pinning required False
caveat           provider-seed-reproducibility-not-guaranteed
node bodies run  []
```

**What the tests assert.** This module reads both fixtures: `gebra_graph` is the extracted IR and
`gebra_verification` the run under the session's policy. It asserts the WARNING finding and the
green default gate; that it is the run's only finding; that a strict policy naming this property
— run in-process over `gebra_graph`, so the suite stays green without a flag — exits `1` with one
promotion and an unchanged record; and that the pinned variant passes under both policies with
the caveat on its witness, then gates it.

```python
"""The seeded finding under both policies, through the plugin's fixtures — and the fix.

Override ``gebra_workflow`` and ``gebra_graph`` is the extracted IR, ``gebra_verification``
the whole verification run over it under the session's policy. The tests below assert what
the use-cases page prints: P-08 reports the unpinned temperature as a WARNING from a
HEURISTIC property, the default gate stays green with the finding on record, a strict policy
naming this property turns the gate red and leaves the record exactly as it was, and the
pinned variant passes with the provider caveat on its witness. The strict leg is run
in-process over ``gebra_graph`` rather than with ``--gebra-strict`` on the command line, so
``python -m pytest examples/scenarios -q`` — the command CI runs — is green as a suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from examples.scenarios.pipeline_replay.workflow import (
    STRICT_ON_P08,
    build_pipeline_replay,
    build_pipeline_replay_pinned,
)
from gebra.ir import WorkflowIR
from gebra.pytest_plugin import TargetVerification, findings_for, verify_target
from gebra.verify import (
    DeterminismNodeLocation,
    DeterminismWitness,
    PropertyReport,
    RunPolicy,
    verify,
)


@pytest.fixture
def gebra_workflow() -> Any:
    """The scenario's seeded graph — in your repository, your own builder."""
    return build_pipeline_replay()


def test_the_claim_is_reported_and_the_default_gate_stays_green(
    gebra_verification: TargetVerification,
) -> None:
    """WARNING, HEURISTIC: exit 0, ``pass-with-notes``, snapshot still eligible."""
    report = gebra_verification.report
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass-with-notes")
    assert report.gate.snapshot_eligible is True
    assert report.gate.promotions == ()

    outcome = report.outcome_for("determinism-replay")
    assert isinstance(outcome, PropertyReport) and outcome.failure is not None
    failure = outcome.failure
    assert failure.property_condition == "deterministic-llm-temperature-unpinned"
    assert (failure.severity, failure.claim_class) == ("warning", "heuristic")
    assert isinstance(failure.location, DeterminismNodeLocation)
    assert failure.location.node == "extract_fields"
    assert (failure.location.seed, failure.location.temperature) == (7, None)


def test_the_unpinned_claim_is_the_only_finding(gebra_verification: TargetVerification) -> None:
    """One seeded defect, one finding: every other property passes, warning-free."""
    report = gebra_verification.report
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (0, 0, 1)
    for slug in ("graph-well-formed", "termination-witness", "dataflow-completeness"):
        assert findings_for(report, slug) == (), slug
    assert findings_for(report, "effect-safety") == ()
    assert gebra_verification.extraction_notes == ()


def test_a_strict_policy_moves_the_gate_and_not_the_record(
    gebra_graph: WorkflowIR, gebra_verification: TargetVerification
) -> None:
    """``--gebra-strict=determinism-replay``: exit 1, one promotion, the record unchanged."""
    strict = verify(gebra_graph, RunPolicy(strict=STRICT_ON_P08))
    assert (strict.gate.exit_code, strict.gate.outcome) == (1, "fail")
    (promotion,) = strict.gate.promotions
    assert (promotion.property, promotion.origin) == ("determinism-replay", "failure")

    default = gebra_verification.report
    assert strict.gate.counts == default.gate.counts
    assert strict.outcome_for("determinism-replay") == default.outcome_for("determinism-replay")


def test_pinning_the_temperature_clears_the_gate_with_the_caveat() -> None:
    """The fix passes under both policies, and its witness says what a pinned seed is not."""
    name = "pipeline_replay_pinned"
    default = verify_target(build_pipeline_replay_pinned(), name=name, source=__name__)
    strict = verify_target(
        build_pipeline_replay_pinned(), name=name, source=__name__, strict=STRICT_ON_P08
    )
    assert (default.report.gate.exit_code, default.report.gate.outcome) == (0, "pass")
    assert (strict.report.gate.exit_code, strict.report.gate.promotions) == (0, ())

    outcome = default.report.outcome_for("determinism-replay")
    assert isinstance(outcome, PropertyReport)
    assert isinstance(outcome.witness, DeterminismWitness)
    assert outcome.witness.caveat == "provider-seed-reproducibility-not-guaranteed"
    claims = {
        claim.node: (claim.llm_backed, claim.seed, claim.temperature)
        for claim in outcome.witness.claims
    }
    assert claims == {"extract_fields": (True, 7, 0.0), "validate_fields": (False, None, None)}


@pytest.mark.gebra(name="pipeline_replay_pinned")
def test_gebra() -> Any:
    """The fix, gated the way CI gates it: one green item per checked property."""
    return build_pipeline_replay_pinned()
```

## What these verdicts claim, and what they do not

Three findings, three claim classes, and the class is part of the finding for a reason.

**DEFENSIBLE** (the research loop): decided over the extracted document alone. The component is
there and no witness form is declared on it; nothing was trusted to reach that answer.

**DEFENSIBLE-A** (the triage path): decided over the document plus what the nodes declared about
themselves. Annotation truthfulness is trusted — a node whose contract omits a read it performs
would not be found, and a node whose contract lists a write it never performs would cover a
read it does not really cover. The verdict is exactly as good as the declarations.

**HEURISTIC** (the pipeline): advisory. P-08 checks that a claim is coherent, not that the world
honours it, and every one of its findings is a WARNING for that reason; a team decides whether
to make it gate by naming the property under `--gebra-strict`.

None of the three is a statement about behaviour at run time. Nothing was executed — the last
line of every block above is the ledger — and a green gate on any of the fixed variants means
the *definition* satisfied the checked property on the evidence that property reads, and nothing
more than that; [what gebra checks](../concepts/what-gebra-checks.md) draws the boundary in full.

## Where this page is checked

Every Python block marked as an example above runs in CI through the
[executable-examples harness](../contributing/executable-examples.md), in a child interpreter
where opening a connection, compiling a graph and invoking a runnable all raise, and its printed
output is compared against what this page shows. The three `workflow.py` blocks run as scripts —
which is what makes their output blocks the files' own verdicts — and arm their own node bodies
through the module-level ledger the harness sweeps; the three fix blocks import the scenario
modules, which that sweep does not reach, so each asserts and prints the ledger itself.

`tests/docs/test_use_cases.py` holds every `workflow.py` and `test_verdict.py` block byte-equal to
its file under `examples/scenarios/`; asserts, by running `verify()` over each builder, that the
three seeded defects are what this page names — one finding each, three distinct condition IDs
from three properties, none of them the CI-gating guide's — and that each fix passes; runs the
suite CI runs (`python -m pytest examples/scenarios -q`) in a child process and checks it is
green with exactly the fixed variants marked; fires a scenario body on both paths to show that
the ledgers catch it; and runs the honest-claims lint over this page and the scenario sources.
