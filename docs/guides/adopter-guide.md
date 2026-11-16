# Adopter guide: loop bounds, mounted subgraphs, payload reads, enum routers and approval gates

This guide is for running gebra over an agent that already exists — one written without gebra in
mind. Five shapes such agents use need something from you before a report says what you want to
know, and each section below takes one of them: what gebra reads, what it reports, and what to
write.

1. [A loop bounded only by the recursion limit](#a-loop-bounded-only-by-the-recursion-limit) —
   P-02 asks every loop for a declared bound, and the limit a run is given is not in the
   definition until you declare it, with the reason for the number.
2. [A compiled graph mounted as a node](#a-compiled-graph-mounted-as-a-node) — read as that one
   node, and the run report's extraction notes say so.
3. [A key a `Send` hands its target](#a-key-a-send-hands-its-target) — P-04 does not decide a read
   that arrives in a payload and names the reader instead of failing it, once the router's
   declared targets and its `Send` return hint make the fan-out a `send` edge.
4. [A router keyed by an `Enum`](#a-router-keyed-by-an-enum) — a plain `Enum` whose values are
   strings extracts, spelled by those values, like a `str`-mixin `Enum`; the other enum forms
   are refused, with the way round.
5. [An approval gate in front of a write](#an-approval-gate-in-front-of-a-write) — gebra does not
   check gate ordering as a rule of its own; a token the gate writes and the write reads turns a
   route around the gate into a P-04 finding, within limits the section's last box names.

Nothing here runs an agent. Every node body and router in the examples records its name in a
module-level `TRIPPED` list and raises; each example ends by printing that list, empty.

!!! note "Following along"

    Each example writes a small agent module into its working directory, imports it and hands
    it to gebra, the way your own code would — extraction reads a node's source from its file,
    so the module is a real file rather than a string. The examples hand gebra the **builder**:
    they run under a guard that refuses `StateGraph.compile()`, described in the last section
    of this page. A compiled graph is read through that same builder, plus what only the
    compiled object has — a `runtime` block with `checkpointer` and any interrupts, LangGraph's
    own subgraph discovery, a recursion limit bound with `with_config`, and LangGraph's drawing
    of the graph, which extraction cross-checks against the builder; where one of those changes
    what a section shows, the section says so.

    One more thing about the examples' graphs. P-04 counts a graph input as written before any
    node runs, and `StateGraph(S)` makes every key of `S` an input — so on such a graph P-04 has
    nothing to report. The examples declare a narrower input schema,
    `StateGraph(S, input_schema=I)`, so that the keys P-04 decides are the ones a caller does not
    supply: the shape of an agent that takes a request and builds the rest itself.

!!! note "Which release"

    The first four sections use surfaces merged after `gebra 0.1.1`: the declaration call and
    the `[runtime]` table, the subgraph disclosure in the run report, P-04's reading of a
    `send` edge, and the admission of `Enum` labels. An installed `0.1.1` has none of them; to
    follow them, upgrade to `0.2.0`, the release that carries them (`pip install --upgrade
    gebra`), or [install from a checkout](install-and-compatibility.md#from-a-checkout) of this
    repository. The fifth section uses only what `0.1.1` already has.

## A loop bounded only by the recursion limit

LangGraph stops a run that takes more supersteps than its recursion limit, and for an agent whose
model calls tools until it decides it is done, that limit may be the only bound its loop has. P-02
`termination-witness` asks whether every simple cycle in the definition carries a declared bound
(a **termination witness**), and the limit a run is given is not part of the definition:
LangGraph's default limit and a limit passed when the graph is invoked are never read. Until it
is declared, the loop has no witness.

<!-- gebra:example id=a-loop-with-no-declared-bound -->
```python
from pathlib import Path

import gebra
from gebra.verify import RunPolicy, StrictPolicy, verify

AGENT = '''\
"""A tool-calling agent: the model decides, a tool runs, the model decides again."""

from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class AgentState(TypedDict):
    question: str
    messages: list[str]
    answer: str


class AgentInput(TypedDict):
    question: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    """Record that a body was entered, then refuse to run it."""
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


@gebra.contract(reads=["question"], writes=["messages", "answer"], effects=["network"])
def call_model(state):
    unreached("call_model")


@gebra.contract(reads=["messages"], writes=["messages"], effects=["network"])
def run_tools(state):
    unreached("run_tools")


def should_continue(state) -> str:
    unreached("should_continue")


def build_agent() -> StateGraph:
    workflow = StateGraph(AgentState, input_schema=AgentInput)
    workflow.add_node("call_model", call_model)
    workflow.add_node("run_tools", run_tools)
    workflow.add_edge(START, "call_model")
    workflow.add_conditional_edges(
        "call_model", should_continue, {"tools": "run_tools", "done": END}
    )
    workflow.add_edge("run_tools", "call_model")
    return workflow


workflow = build_agent()
'''

Path("tool_agent.py").write_text(AGENT, encoding="utf-8")

import tool_agent

before = verify(gebra.extract(tool_agent.workflow).ir)
failure = before.outcome_for("termination-witness").failure
print(f"undeclared  gate {before.gate.outcome}, exit {before.gate.exit_code}")
print(f"  P-02 {failure.property_condition} on {' -> '.join(failure.location.nodes)}")

gebra.recursion_limit(
    tool_agent.workflow,
    11,
    justification="at most five tool rounds of two steps each, then the answer",
)
envelope = gebra.extract(tool_agent.workflow)
declared = envelope.ir.runtime.recursion_limit
after = verify(envelope.ir)
p02 = after.outcome_for("termination-witness")
print(f"declared    runtime.recursion_limit = {declared.value}")
print(f"  justification {declared.justification!r}")
forms = " ".join(f"({entry.form})" for entry in p02.witness.inventory)
print(f"  P-02 {p02.result} by form {forms}, with {len(p02.witness.notes)} note:")
for note in p02.witness.notes:
    print(f"    {note.kind}, severity {note.severity}")
print(f"  gate {after.gate.outcome}, exit {after.gate.exit_code}")

only_p02 = StrictPolicy(mode="per-property", properties=("termination-witness",))
strict = verify(envelope.ir, RunPolicy(strict=only_p02))
print(f"  --strict=termination-witness: gate {strict.gate.outcome}, exit {strict.gate.exit_code}")

for graph, justification in ((tool_agent.workflow, "again"), (tool_agent.build_agent(), " ")):
    try:
        gebra.recursion_limit(graph, 11, justification=justification)
    except gebra.GebraContractError as error:
        print(f"refused     {error.reason.value}")

print("nodes run:", tool_agent.TRIPPED)
```

<!-- gebra:output id=a-loop-with-no-declared-bound -->
```text
undeclared  gate fail, exit 1
  P-02 cycle-without-termination-witness on call_model -> run_tools
declared    runtime.recursion_limit = 11
  justification 'at most five tool rounds of two steps each, then the answer'
  P-02 pass by form (b), with 1 note:
    scc-covered-only-by-recursion-limit, severity warning
  gate pass-with-notes, exit 0
  --strict=termination-witness: gate fail, exit 1
refused     duplicate-slot
refused     slot-value-invalid
nodes run: []
```

**The undeclared loop fails, and the finding names the region.** `call_model` and `run_tools`
form one strongly connected region with no counter guard, no loop variant and no declared limit,
so P-02 reports `cycle-without-termination-witness` over it — FATAL, claim class DEFENSIBLE
(witness presence), which fails the gate. The
[P-02 page](../validators/p02-termination-witness.md#a-failure-names-the-region-it-could-not-discharge)
reads that record field by field.

**`gebra.recursion_limit` declares the step budget and the reason for it, together.** The call
writes `runtime.recursion_limit` — `value` and `justification` — and P-02 reads it as witness
**form (b)**, a blanket over every cycle of the graph at once (TERMINATION-WITNESS-SPEC §2.2). Both
members are required: the justification is your statement of why that number, and the number is
the one you justified, so no surface takes the value from anywhere else. The call returns the
object it was given, so it can wrap the builder where your module builds it —
`workflow = gebra.recursion_limit(build_agent(), 11, justification="…")` — and it puts the
declaration on the builder, which every graph compiled from it shares: compile before or after
the call, and the compiled graph carries the same declaration. Handed a compiled graph, it puts
the declaration on that graph's builder, or on the graph itself when it has none.

**It is refused, not ignored, when it cannot be what it says.** The last lines are the call-time
rules at work: a builder takes one declaration (a second call is an error, the same value
included — `duplicate-slot`), and the value must be an integer from `1` to `2**53 - 1`, not a
`bool`, with a justification that is not blank (`slot-value-invalid`). Both raise
`GebraContractError` when the call runs, before any extraction.

**Declaring the limit to gebra does not set it for LangGraph.** The declaration is a record in
the definition; it configures no run. Pass the same number where your code runs the graph — in
the `config` of the call that invokes it, or by binding it with `with_config(recursion_limit=11)`,
which extraction of the compiled graph then compares with the declaration (the last part of this
section).

**A pass by the step budget alone is a pass with a warning.** Form (b) bounds the total number of
steps, not any particular loop, so it is the weakest of P-02's three forms (TERMINATION-WITNESS-SPEC
§2.4): a region covered by it and by nothing else passes with the WARNING-grade note
`scc-covered-only-by-recursion-limit`, and the gate reads `pass-with-notes`, exit `0`. A strict
policy naming P-02 promotes that note, and the gate fails with exit `1` while the record stays
the same — the
[P-02 page's strict-mode section](../validators/p02-termination-witness.md#a-justified-limit-passes-and-strict-mode-is-where-it-bites)
shows the promotion in full. So a team can declare the limit to get a first green build and keep
the report telling it which loops ride on the budget. A loop variant declared on a node of the
loop — `@gebra.variant(key=…, measure=…)`, with `key` a state key — takes that loop off the list.
A counter guard would too, but P-02 reads one off a router's *declared* condition, and extraction
fills that slot with the router's name rather than its body, so a counter tested inside
`should_continue` is not visible to it.

**What the pass records, and what it does not.** P-02 records the number and the justification
and evaluates neither: whether five tool rounds is really the most this agent takes, and whether
11 steps really covers them, is what you wrote, not something gebra checked. A declared limit is a
recorded bound, not a statement that the loop halts — the claim P-02 makes is that the
definition carries a bound, and the
[P-02 page](../validators/p02-termination-witness.md#what-a-pass-does-not-claim) draws that line
in full.

### Declaring the limit for a graph you cannot edit

A graph from a package you install, or one built in a file you do not own, can take the
declaration from your code that imports it — the second half of the example below does that —
or from a `gebra.toml` sidecar, which needs no code of yours at all: a run that names the graph
by import reference, `gebra verify package.module:workflow --sidecar gebra.toml`, reads it. The
declaration is a `[runtime]` table, not keyed by a node, holding one key — `recursion_limit` —
with the slot's own two members.

<!-- gebra:example id=the-runtime-table -->
```python
from pathlib import Path

import gebra
from gebra.extraction import ExtractionWarningCode
from gebra.verify import verify

VENDORED = '''\
"""A drafting loop from a package we install but do not edit."""

from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph


class DraftState(TypedDict):
    topic: str
    draft: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def write_draft(state):
    unreached("write_draft")


def review(state) -> str:
    unreached("review")


workflow = StateGraph(DraftState)
workflow.add_node("write_draft", write_draft)
workflow.add_edge(START, "write_draft")
workflow.add_conditional_edges("write_draft", review, {"revise": "write_draft", "done": END})
'''

SIDECAR = """\
schema = "gebra-sidecar-v1"

[runtime]
recursion_limit = { value = 8, justification = "a first draft and at most seven revisions" }
"""

Path("drafting.py").write_text(VENDORED, encoding="utf-8")
Path("gebra.toml").write_text(SIDECAR, encoding="utf-8")

import drafting

envelope = gebra.extract(drafting.workflow, sidecar="gebra.toml")
limit = envelope.ir.runtime.recursion_limit
p02 = verify(envelope.ir).outcome_for("termination-witness")
print(f"from the sidecar  {limit.value}: {limit.justification!r}")
print(f"  P-02 {p02.result} by form ({p02.witness.inventory[0].form})")

gebra.recursion_limit(drafting.workflow, 6, justification="our runs revise at most five times")
envelope = gebra.extract(drafting.workflow, sidecar="gebra.toml")
[conflict] = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT)
print(f"both surfaces     {envelope.ir.runtime.recursion_limit.value} is kept")
print(f"  {conflict.code.value}: {conflict.detail['surfaces']}")

print("nodes run:", drafting.TRIPPED)
```

<!-- gebra:output id=the-runtime-table -->
```text
from the sidecar  8: 'a first draft and at most seven revisions'
  P-02 pass by form (b)
both surfaces     6 is kept
  annotation-conflict: {'kept': 'graph-level', 'discarded': 'sidecar'}
nodes run: []
```

**The table fills the same slot.** The `[runtime]` table is read on every path a graph takes — a
builder, a compiled graph and a compiled graph with no builder — and it fills the slot the call
fills, so the same number and justification make the same document either way. The schema tag
is unchanged (`gebra-sidecar-v1`), and a file can carry
`[runtime]` beside its `[nodes.<id>]` tables. As with every sidecar input, the declaration is
inside the `graph_version` hash scope, so pass `sidecar=` (or `--sidecar` on the CLI) explicitly
wherever the digest has to be reproducible; the
[contracts tutorial](../tutorials/contracts-and-annotations.md#declaring-beside-the-code) covers
discovery.

**Code wins over the sidecar, and says so.** The second half of the example declares in code as
well — on the graph object, from the code that imports it — with a different number. When both
surfaces declare the slot, the declaration in code is kept
whole and the sidecar's is not used — never merged member by member — and an
`annotation-conflict` warning names both surfaces and both values. Identical declarations are not
a conflict. An extraction warning never moves an exit code; it is how a stale sidecar shows up.

**A table the slot cannot carry declares nothing.** A `[runtime]` table with no justification, a
blank one, or a value that is not an integer from `1` to `2**53 - 1` (a TOML boolean included) is
reported as
`annotation-invalid` naming the file, the key and the rule, and the slot stays **absent** — never
filled with LangGraph's default and never with a bound value — so P-02 fails as it would with no
table at all. Any other key in `[runtime]` is reported the same way and ignored.

### A limit bound with `with_config`, and the managed `RemainingSteps`

Two things a compiled agent may already carry are related to the declaration and are not it.

**A binding is recorded beside the declaration, and never replaces it.** A compiled graph that
`with_config(recursion_limit=N)` returned carries `N` on the object, and extraction of the
compiled graph records it — without filling the slot, because a binding carries no justification.
Beside a declaration with the same value it corroborates it; beside a different one the
declaration is kept and `annotation-conflict` names both values; with no declaration at all it is
recorded as the `recursion-limit-bound-without-justification` extraction disclosure and P-02
fails as before. The examples here hand gebra the builder, which has no binding, so this is
described rather than shown — `tests/extraction/test_runtime.py` holds each of the three outcomes.

**A loop whose exit tests LangGraph's managed `RemainingSteps` takes the same declaration.** That
value is computed at run time from the recursion limit in force, and in this release a managed
key is not part of the extracted state — so a counter guard comparing it does not qualify as a
witness, and a loop variant declared on it is reported `variant-key-not-in-state` and discharges
nothing. The
declared limit is the witness P-02 reads for such a loop, as form (b) is for every cycle, and its
justification is where to say how the loop's exit relates to the limit. The declaration records
that limit; it does not set the one a run is given.

## A compiled graph mounted as a node

A LangGraph agent can mount another compiled graph as one of its nodes — a search or a booking
flow built and tested on its own. In this release the document carries such a node as **that one
node**: the mounted graph's nodes, edges, entry, finish and state are not read, so no property
checks anything inside it. Extraction says so rather than leaving it to be noticed: the node gets a
`subgraph-read-as-one-node` **disclosure**, and every run that extracts the workflow reports it.

<!-- gebra:example id=a-mounted-graph-is-disclosed -->
```python
import contextlib
import io
import json
from pathlib import Path

from gebra.cli import main

AGENT = '''\
"""A trip planner whose flight search is a compiled graph of its own, mounted as one node."""

from typing import NoReturn, TypedDict

from langgraph.channels import LastValue
from langgraph.graph import END, START, StateGraph
from langgraph.pregel import NodeBuilder, Pregel

import gebra


class TripState(TypedDict):
    request: str
    itinerary: str
    summary: str


class TripInput(TypedDict):
    request: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def search_flights(request):
    unreached("search_flights")


flight_search = Pregel(
    nodes={
        "search_flights": NodeBuilder()
        .subscribe_only("request")
        .do(search_flights)
        .write_to("itinerary"),
    },
    channels={"request": LastValue(str), "itinerary": LastValue(str)},
    input_channels="request",
    output_channels="itinerary",
)


@gebra.contract(reads=["itinerary"], writes=["summary"], pure=True)
def summarize(state):
    unreached("summarize")


workflow = StateGraph(TripState, input_schema=TripInput)
workflow.add_node("flight_search", flight_search)
workflow.add_node("summarize", summarize)
workflow.add_edge(START, "flight_search")
workflow.add_edge("flight_search", "summarize")
workflow.add_edge("summarize", END)
'''

SIDECAR = """\
schema = "gebra-sidecar-v1"

[nodes.flight_search]
reads   = ["request"]
writes  = ["itinerary"]
effects = ["network"]
"""

Path("trip_agent.py").write_text(AGENT, encoding="utf-8")
Path("gebra.toml").write_text(SIDECAR, encoding="utf-8")
target = ["verify", "trip_agent:workflow", "--sidecar", "gebra.toml"]

with contextlib.redirect_stderr(io.StringIO()) as stderr:
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        default = main(target)
        strict = main([*target, "--strict"])
    main([*target, "--format", "json", "--output", "report.json"])

print("stderr:", stderr.getvalue().splitlines()[0].split(": ", 1)[0])
human = stdout.getvalue()
start = human.index("extraction notes")
for line in human[start : human.index("\n\n", start)].splitlines():
    print(line.rstrip())
print(f"exit {default}; with --strict, exit {strict}")

[note] = json.loads(Path("report.json").read_text(encoding="utf-8"))["extraction_notes"]
print(f"json: {note['code']} at {note['node']}, seen by {note['detail']['seen_by']}")

import trip_agent

print("nodes run:", trip_agent.TRIPPED)
```

<!-- gebra:output id=a-mounted-graph-is-disclosed -->
```text
stderr: extraction disclosure [subgraph-read-as-one-node]
extraction notes — what extraction recorded while reading this subject; not
findings, and not the witness notes the summary counts: no exit code, count or
strict promotion turns on them, and the native JSON report carries each record
whole
  extraction disclosure [subgraph-read-as-one-node]  [node flight_search]
    message                 node `flight_search` mounts or reaches a compiled
subgraph that this document carries as one node; its interior (child nodes,
edges, entry, finish and state) was not read — child expansion is the named ir
1.x feature of DEC-19's design register, not performed in ir_version 1.0/1.1
output. The set of mounts this document knows of is a lower bound, not a census:
a subgraph compiled with `checkpointer=False` and reached only from inside a
node body is invisible, and on the compiled-only path (INTROSPECTION-SPEC §4.3
rule 4), where no builder-level direct-mount read exists, every
`checkpointer=False` child is. On an uncompiled builder no `get_subgraphs()`
read exists, so a subgraph that is not itself a node's bound object is invisible
here whatever its checkpointer.
exit 0; with --strict, exit 0
json: subgraph-read-as-one-node at flight_search, seen by ['direct-mount']
nodes run: []
```

!!! note "Why the mounted graph here is built with `Pregel`"

    In your code the mounted graph is most likely `search_builder.compile()`. The examples on
    this site run under a guard that refuses `compile()`, so this one builds its graph with
    LangGraph's `Pregel` class directly. A compiled `StateGraph` is a `Pregel` too, and that
    class is what the read that found this node tests for; the repository's extraction tests
    run the same read over graphs compiled from a `StateGraph`.

**Where the disclosure appears.** `gebra verify` writes it to stderr after any extraction
warnings, under its own label — `extraction disclosure`, never the warning prefix, so a log
searched for warnings does not count it. The run report carries the same record in its extraction
notes: the human report shows it in the block above, under the subject line; `--format json`
carries it whole in `extraction_notes` (`code`, `message`, `node`, `detail`); `--format sarif`
carries it as a tool notification at level `note`; and the pytest plugin's closing report prints
it — the [CI-gating guide](pytest-plugin-and-ci-gating.md#assert-against-the-extracted-graph-yourself)
shows where `gebra_verification.extraction_notes` sits.
`detail.seen_by` names the reads that found the node: on a builder, the check of each node's
bound object (`direct-mount`); on a compiled graph with a builder, also LangGraph's own subgraph
discovery (`get-subgraphs`) when that finds it; on one with no builder, that discovery alone.

**A disclosure is not a finding.** It moves no exit code, enters no count, and no strict flag
promotes it — the two exit codes above are equal. That is deliberate (decision record DEC-36): a
mounted graph is a construct LangGraph supports, not a defect. The price is stated rather than
left to be inferred: **a strict run does not fail because a mounted graph's interior was not
checked.** The notes are where you are told.

**What to do with it.** Three things, each available in this release:

* **Declare the mounted node's contract** — what it reads from the parent's state and what it
  writes back — as the example does in `gebra.toml`, keyed by the node id. The parent's
  properties then decide the reads and writes around that node like any other: here P-04 covers
  `summarize`'s read of `itinerary` with `flight_search`'s declared write.
* **Check the mounted graph as a subject of its own.** Hand its builder to `gebra verify` (or
  `gebra.extract()`), and its own loops, reads and effects are checked at its own level.
* **Read the list as a lower bound.** The disclosed set is the nodes extraction found, never a
  census. A graph compiled with `checkpointer=False` and reached only from inside a node body is
  found by neither read, and on a builder handed in uncompiled only a node whose bound object *is*
  a compiled graph is found. An empty notes block is not evidence that no graph is mounted — the
  [extraction tutorial's subgraph box](../tutorials/extract-your-first-ir.md#what-a-builder-cannot-know-and-one-thing-nothing-can)
  lists each read and what it misses.

## A key a `Send` hands its target

A map-reduce agent fans out with `Send`: a router returns one `Send("book_leg", {...})` per item,
and LangGraph runs `book_leg` once per `Send`, with that payload as its input — not the graph
state. P-04 `dataflow-completeness` asks whether every key a node declares it reads has been
written on every path that reaches it, and a key that only ever arrives in a payload is written by
no node. Read as a state read, it is a missing write on every path.

P-04 does not read it that way when the fan-out is in the document as a `send` edge. Along a
`send` edge the target reads the payload the edge hands it, which the IR does not carry, so P-04
raises no obligation for those reads, decides nothing about them, and names the node on the
report's `payload_readers` instead (decision record DEC-37). What it takes for the fan-out to be
a `send` edge is the difference between the two graphs below: the same router, with and without
its return type hint.

<!-- gebra:example id=a-payload-read -->
```python
from pathlib import Path

import gebra
from gebra.verify import verify

AGENT = '''\
"""Plan a trip, book every leg in parallel, confirm the itinerary."""

import operator
from typing import Annotated, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import gebra


class TripState(TypedDict):
    request: str
    search_plan: str
    leg_id: str
    bookings: Annotated[list[str], operator.add]


class TripInput(TypedDict):
    request: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


@gebra.contract(reads=["request"], writes=["search_plan"], pure=True)
def plan_legs(state):
    unreached("plan_legs")


@gebra.contract(reads=["search_plan", "leg_id"], writes=["bookings"], effects=["network"])
def book_leg(state):
    unreached("book_leg")


@gebra.contract(reads=["bookings"], writes=[], pure=True)
def confirm_itinerary(state):
    unreached("confirm_itinerary")


def route_legs(state) -> list[Send]:
    unreached("route_legs")


def route_legs_unhinted(state):
    unreached("route_legs_unhinted")


def build(router) -> StateGraph:
    workflow = StateGraph(TripState, input_schema=TripInput)
    workflow.add_node("plan_legs", plan_legs)
    workflow.add_node("book_leg", book_leg)
    workflow.add_node("confirm_itinerary", confirm_itinerary)
    workflow.add_edge(START, "plan_legs")
    workflow.add_conditional_edges("plan_legs", router, ["book_leg"])
    workflow.add_edge("book_leg", "confirm_itinerary")
    workflow.add_edge("confirm_itinerary", END)
    return workflow
'''

Path("fan_out.py").write_text(AGENT, encoding="utf-8")

import fan_out

for router in (fan_out.route_legs, fan_out.route_legs_unhinted):
    envelope = gebra.extract(fan_out.build(router))
    [edge] = [edge for edge in envelope.ir.edges if edge.from_ == "plan_legs"]
    p04 = verify(envelope.ir).outcome_for("dataflow-completeness")
    print(f"{router.__name__}: plan_legs -> book_leg is a {edge.kind} edge")
    if p04.result == "pass":
        print(f"  P-04 pass, payload_readers {list(p04.witness.payload_readers)}")
    else:
        where = p04.failure.location
        route = " -> ".join(where.path)
        print(f"  P-04 fail: {where.node} reads {where.key}, unwritten on {route}")

print("nodes run:", fan_out.TRIPPED)
```

<!-- gebra:output id=a-payload-read -->
```text
route_legs: plan_legs -> book_leg is a send edge
  P-04 pass, payload_readers ['book_leg']
route_legs_unhinted: plan_legs -> book_leg is a conditional edge
  P-04 fail: book_leg reads leg_id, unwritten on START -> plan_legs -> book_leg
nodes run: []
```

**What makes a fan-out a `send` edge.** Two declarations on the router, both true ones: its
targets — here the list `["book_leg"]` handed to `add_conditional_edges`, or a `path_map` — and a
`Send` return type hint, `def route_legs(state) -> list[Send]:`. With the targets and no hint the
router is an ordinary conditional edge, which P-04 reads as handing `book_leg` the graph state,
and then `leg_id` is a read nothing wrote, as the second run reports — P-04's
`read-key-never-written-on-path`, FATAL, claim class DEFENSIBLE-A. With the hint and no
declared targets the router is a `dynamic` edge, which contributes no path at all: a target
nothing else wires is then outside P-04's reach and named on `outside_static_coverage` instead.
So when a P-04 finding
names a key that a `Send` hands its target, the fix to make is the hint and the targets on the
router, not a declaration that some node writes the key — that would be false, and P-04 would
then trust it.

**`payload_readers` means "not decided".** A pass with `book_leg` on that list says that P-04 did
not check `book_leg`'s reads along the `send` edge: whether the router actually puts `leg_id` in
every `Send` is in the router's body, which gebra never reads. It is never a finding: whether a
node is on the list moves no verdict and no exit code.

**A payload is not a state write.** `book_leg`'s own declared writes still count — `bookings`
reaches `confirm_itinerary` through its reducer like any write — but `leg_id` does not: a node
after `book_leg` that read `leg_id` from the state would fail on the path through it. And a node
entered both through the `send` edge and through an ordinary edge has its reads decided along the
ordinary one. The
[P-04 page's payload section](../validators/p04-dataflow-completeness.md#a-send-target-reads-its-payload)
runs both shapes.

## A router keyed by an `Enum`

A router's `path_map` maps each label the router can return to the node it routes to, and some
agent code keys it with an enumeration rather than with strings — `AgentDecision.TOOL` and
`AgentDecision.END` rather than `"tool"` and `"finished"`. A label enters the IR, and so the
`graph_version`, as a string, and gebra never spells a label by calling the label's own code: no
`str()`, no `repr()`, no `.name` and no `.value`, any of which a class can override. A `str`-mixin
member (`class Decision(str, Enum)`, or `StrEnum`) is a string and is read as one. One more enum
form has a spelling gebra can read without any of that: a **plain `Enum` member whose stored value
is a `str`**. It is admitted, and spelled as that value (decision record DEC-38).

<!-- gebra:example id=an-enum-keyed-router -->
```python
from pathlib import Path

import gebra

AGENT = '''\
"""A ReAct-style agent whose router answers with an enumeration."""

from enum import Enum
from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class AgentDecision(Enum):
    TOOL = "tool"
    END = "finished"


class StrDecision(str, Enum):
    TOOL = "tool"
    END = "finished"


class AgentState(TypedDict):
    question: str
    scratchpad: list[str]
    answer: str


class AgentInput(TypedDict):
    question: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


@gebra.contract(reads=["question"], writes=["scratchpad", "answer"], effects=["network"])
def agent(state):
    unreached("agent")


@gebra.contract(reads=["scratchpad"], writes=["scratchpad"], effects=["network"])
def tool(state):
    unreached("tool")


def decide(state) -> AgentDecision:
    unreached("decide")


def build(tool_label, end_label) -> StateGraph:
    workflow = StateGraph(AgentState, input_schema=AgentInput)
    workflow.add_node("agent", agent)
    workflow.add_node("tool", tool)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", decide, {tool_label: "tool", end_label: END})
    workflow.add_edge("tool", "agent")
    return workflow
'''

Path("react_agent.py").write_text(AGENT, encoding="utf-8")

import react_agent
from react_agent import AgentDecision, StrDecision

envelope = gebra.extract(react_agent.build(AgentDecision.TOOL, AgentDecision.END))
[router] = [edge for edge in envelope.ir.edges if edge.kind == "conditional"]
print("path_map:", router.path_map)


def graph_version(tool_label, end_label):
    return gebra.extract(react_agent.build(tool_label, end_label)).graph_version()


versions = {
    graph_version(AgentDecision.TOOL, AgentDecision.END),
    graph_version(StrDecision.TOOL, StrDecision.END),
    graph_version("tool", "finished"),
}
print("plain Enum, str-mixin Enum, plain strings:", len(versions), "graph_version")

print("nodes run:", react_agent.TRIPPED)
```

<!-- gebra:output id=an-enum-keyed-router -->
```text
path_map: {'tool': 'tool', 'finished': 'END'}
plain Enum, str-mixin Enum, plain strings: 1 graph_version
nodes run: []
```

**Labels are the values, not the names.** `AgentDecision.END` has the name `END` and the value
`"finished"`, and the label in the IR is `finished`: the value is what the class body says the
member stands for, and it is the spelling a `str`-mixin member already had — so a plain `Enum`,
a `str`-mixin `Enum` with the same values and plain strings produce one document and one
`graph_version`, as the last line shows. The value is read from the member's own stored data
without calling anything on the member or its class; overriding `__str__`, `name` or `value` on
the class does not change the label gebra writes. The `END` on the right of the `path_map` is
LangGraph's own `END`, which the IR writes as `END`.

**A compiled graph is spelled the same way.** A graph compiled from a `StateGraph` is read
through its builder, so its labels are the same values.

### The enum forms that are still refused

Every other non-string label is refused at extraction, with an error naming the label's type and
the way round. No spelling is guessed: a label the IR cannot spell faithfully would put a wrong
string inside `graph_version`.

<!-- gebra:example id=enum-forms-still-refused -->
```python
import textwrap
from pathlib import Path

from langgraph.graph import END

import gebra
from gebra.extraction import ExtractionError

LABELS = '''\
"""Four enumerations whose members have no string value of their own, and one that has."""

from enum import Enum, Flag, IntEnum
from typing import NoReturn, TypedDict

from langgraph.graph import START, StateGraph


class AgentDecision(Enum):
    TOOL = "tool"
    END = "finished"


class Priority(IntEnum):
    TOOL = 1
    END = 2


class Coded(Enum):
    TOOL = 1
    END = 2


class Paired(Enum):
    TOOL = ("tool", 1)
    END = ("finished", 2)


class Mode(Flag):
    TOOL = 1
    END = 2


class State(TypedDict):
    question: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def agent(state):
    unreached("agent")


def tool(state):
    unreached("tool")


def decide(state):
    unreached("decide")


def build(path_map) -> StateGraph:
    workflow = StateGraph(State)
    workflow.add_node("agent", agent)
    workflow.add_node("tool", tool)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", decide, path_map)
    workflow.add_edge("tool", "agent")
    return workflow
'''

Path("refused_labels.py").write_text(LABELS, encoding="utf-8")

import refused_labels
from refused_labels import AgentDecision, Coded, Mode, Paired, Priority

cases = {}
for labels in (Priority, Coded, Paired, Mode):
    cases[labels.__name__] = {labels.TOOL: "tool", labels.END: END}
cases["AgentDecision.TOOL beside 'tool'"] = {AgentDecision.TOOL: "tool", "tool": "tool"}
cases["AgentDecision.TOOL as a target"] = {"tool": AgentDecision.TOOL, "finished": END}
refusals = {}
for name, path_map in cases.items():
    try:
        gebra.extract(refused_labels.build(path_map))
    except ExtractionError as error:
        refusals[name] = error
        print(f"{name:32} refused: {error.reason.value}")

print()
print(textwrap.fill(str(refusals["Priority"]), 92))
print("nodes run:", refused_labels.TRIPPED)
```

<!-- gebra:output id=enum-forms-still-refused -->
```text
Priority                         refused: construct-not-carried
Coded                            refused: construct-not-carried
Paired                           refused: construct-not-carried
Mode                             refused: construct-not-carried
AgentDecision.TOOL beside 'tool' refused: label-collision
AgentDecision.TOOL as a target   refused: unrepresentable-node-id

the router 'decide' on node 'agent' declares the non-string routing label of type
refused_labels:Priority, which ir cannot spell: its stored value is not exactly a str. A
path_map key is a string, or a plain Enum member whose stored value is a str, spelled as
that value (INTROSPECTION-SPEC §6; DEC-32 as amended by DEC-38); every other key is refused
rather than coerced, because a coerced spelling would land inside graph_version. Use string
labels, or a str-valued Enum (plain or string-mixin), with the router returning the same
members or strings (e.g. 'yes'/'no' instead of True/False)
nodes run: []
```

The forms refused: an `IntEnum`, `IntFlag` or `Flag` member, a composite flag included
(its stored value is an `int`); a plain `Enum` whose stored value is not exactly a `str` — an
`int`, a `tuple`, `None`, a `bool`, or a `str` *subclass*, written in the class body or stored by
a custom `__new__`; an enum one of whose classes defines `_value_` itself — a mixin base with a
`_value_` property, say — where what `.value` answers and what the member stored can differ; and
every other object that is not a string — a `bool` and an `int` among them. A routing **target**
— the right-hand side of a `path_map` — is a node name or `END`, so an enum member there is
refused too unless it is a `str`-mixin member, which is read as the string it is.

**The way round** is in the message: use string labels, or an `Enum` whose values are strings —
plain, as in the section's first example, or a `str` mixin (`class Decision(str, Enum)`, or
`StrEnum` from Python 3.11) — with the router returning the same members or strings. A
`str`-mixin member's label is its own string content, which is its value unless a custom
`__new__` stored a different one.

**Two labels that spell the same are refused too.** The fifth case keys one `path_map` with
`AgentDecision.TOOL` and the string `"tool"`. LangGraph keeps both keys, but spelled by value they
are one label, so the declaration is refused as a label collision — whatever the two targets are —
as two strings that normalize to the same text always were. The last case puts a member where a
node name goes, and is refused as a target with no node id (`unrepresentable-node-id`).

## An approval gate in front of a write

An agent that proposes an action — a payment, a deletion, a message to a customer — may put a
policy check between the proposal and the node that performs it, and route to the performing
node only from the check's allow branch. **gebra does not check gate ordering as a rule of its
own**: no property this release checks says "every path to this write passes through that gate's
allow branch", and a graph with a route around its gate can pass every check this release runs.

What you can do with what is there is make the gate leave a **token** — a state key the allow
branch writes — and declare it as a read of the guarded write. A route that reaches the write
without passing the allow branch is then a route on which the write reads a key nothing on that
route wrote, and that is a P-04 finding, `read-key-never-written-on-path`, with the route as its
evidence. Three conditions make it work:

1. **The token is not a graph input.** The graph's input schema leaves it out, and the state
   schema gives it no default: P-04 counts an input or a defaulted key as written at `START`,
   so a token a caller could supply would cover every route.
2. **The guarded write declares the token as a read** — `reads=[..., "approval"]` on the node
   that performs the action.
3. **The token is written on the allow branch alone.** The node the allow label routes to is the
   only node that declares writing it, and the allow label's edge is the only edge into that node.

<!-- gebra:example id=a-gate-as-a-token -->
```python
from pathlib import Path

import gebra
from gebra.verify import verify

AGENT = '''\
"""Propose a payment, check it against policy, record the approval, execute it."""

from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class PaymentState(TypedDict):
    request: str
    proposal: str
    approval: str
    receipt: str


class PaymentInput(TypedDict):
    request: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


@gebra.contract(reads=["request"], writes=["proposal"], effects=["network"])
def propose_payment(state):
    unreached("propose_payment")


@gebra.contract(reads=["request"], writes=["proposal", "approval"], effects=["network"])
def propose_and_approve(state):
    unreached("propose_and_approve")


@gebra.contract(reads=["proposal"], writes=["approval"], pure=True)
def record_approval(state):
    unreached("record_approval")


@gebra.contract(reads=["proposal"], writes=["proposal"], effects=["network"])
def revise_proposal(state):
    unreached("revise_proposal")


@gebra.contract(
    reads=["proposal", "approval"], writes=["receipt"], effects=["network", "irreversible"]
)
def execute_payment(state):
    unreached("execute_payment")


def check_policy(state) -> str:
    unreached("check_policy")


GATED = {"allow": "record_approval", "deny": END}
BYPASS = {"allow": "record_approval", "small": "execute_payment", "deny": END}


def build(*, proposer=propose_payment, routes=GATED, revise=False) -> StateGraph:
    workflow = StateGraph(PaymentState, input_schema=PaymentInput)
    workflow.add_node("propose_payment", proposer)
    workflow.add_node("record_approval", record_approval)
    workflow.add_node("execute_payment", execute_payment)
    workflow.add_edge(START, "propose_payment")
    workflow.add_conditional_edges("propose_payment", check_policy, routes)
    if revise:
        workflow.add_node("revise_proposal", revise_proposal)
        workflow.add_edge("record_approval", "revise_proposal")
        workflow.add_edge("revise_proposal", "execute_payment")
    else:
        workflow.add_edge("record_approval", "execute_payment")
    workflow.add_edge("execute_payment", END)
    return workflow
'''

Path("payments.py").write_text(AGENT, encoding="utf-8")

import payments

graphs = {
    "gated": payments.build(),
    "a route around the gate": payments.build(routes=payments.BYPASS),
    "the same route, token written early": payments.build(
        proposer=payments.propose_and_approve, routes=payments.BYPASS
    ),
    "gated, proposal revised after it": payments.build(revise=True),
}
for label, graph in graphs.items():
    p04 = verify(gebra.extract(graph).ir).outcome_for("dataflow-completeness")
    print(f"{label}: P-04 {p04.result}")
    if p04.result == "fail":
        where = p04.failure.location
        print(f"  {where.node} reads {where.key}, unwritten on {' -> '.join(where.path)}")
    else:
        [row] = [row for row in p04.witness.coverage if row.key == "approval"]
        print(f"  {row.node} reads approval, written by {', '.join(row.satisfied_by)}")

print("nodes run:", payments.TRIPPED)
```

<!-- gebra:output id=a-gate-as-a-token -->
```text
gated: P-04 pass
  execute_payment reads approval, written by record_approval
a route around the gate: P-04 fail
  execute_payment reads approval, unwritten on START -> propose_payment -> execute_payment
the same route, token written early: P-04 pass
  execute_payment reads approval, written by propose_payment, record_approval
gated, proposal revised after it: P-04 pass
  execute_payment reads approval, written by record_approval
nodes run: []
```

**The first two runs are the pattern working.** On the gated graph every route to
`execute_payment` passes `record_approval`, so its read of `approval` is covered. Add one router
label that skips the approval — `small` straight to `execute_payment` — and that route is a route
on which `approval` was never written: P-04 fails, FATAL, claim class DEFENSIBLE-A, and the
finding's path is the route around the gate. P-04 admits every label a router declares as a
route a run could take, so this holds whatever `check_policy` would return at run time.

**The last two runs are the pattern's limits,** and they pass.

!!! warning "What a pass does not show"

    A P-04 pass on a graph built this way says that on every declared route to the guarded
    write, some earlier node declares that it writes the token. Two kinds of route are outside
    that statement: a route through a router with no declared targets, which P-04 does not
    count as a route at all (a write reached only that way is named on
    `outside_static_coverage`), and a route that enters the write through a `send` edge, which
    P-04 does not decide (the write is named on `payload_readers` instead — DEC-37's reading,
    merged after `0.1.1`). Nor does a pass show that the gate was obeyed; two failure modes pass
    it:

    * **The token written before the gate.** If a node before the gate declares writing the
      token — here the proposer, `propose_and_approve` — every route through that node already
      carries it when it reaches the gate, and a route around the gate from there passes, as the
      third run does. The same happens if the token is a graph input or has a default
      (condition 1).
    * **The proposal changed after the allow branch.** P-04 asks whether the token was written,
      never whether what the gate approved is what the write performs. A node after the allow
      branch that rewrites the proposal — `revise_proposal` in the fourth run — leaves every read
      covered, and the graph passes, though at run time the write could perform a proposal the
      policy check never saw.

    And, as for every P-04 pass, a declared write is trusted rather than checked: if the allow
    node's body does not write the token it declares, nothing here notices. gebra does not check
    gate ordering as a rule of its own; the token pattern borrows P-04's every-path rule, and the
    pass is that rule's pass and nothing more.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking a
runnable, resolving a hostname or opening a connection all raise. The modules the examples write
keep a `TRIPPED` ledger that every node body and router records into before raising, and the
harness reads each ledger after the example finishes, so a body that ran fails the example even
if a `try` block swallowed its error; `tests/docs/test_doc_examples.py` fires one of each module's
bodies to show the ledger is read. The output blocks are what those runs printed, and the same
examples run in every cell of the compatibility matrix — [executable
examples](../contributing/executable-examples.md) explains the mechanism.

The frozen contracts behind the first four sections are three decision records: DEC-36 (the
`recursion_limit` declaration surfaces, the binding and the subgraph disclosure),
DEC-37 (P-04's reading of a `send` edge) and DEC-38 (the `Enum` labels and the forms still
refused), with TERMINATION-WITNESS-SPEC §2.2 for form (b). The fifth section is a use of P-04 as
PROPERTY-CATALOG-SPEC §4 states it, and has no record of its own.
`tests/docs/test_adopter_guide.py` holds the page's structure and its claims about each section to
the text.
