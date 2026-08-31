# Extract your first IR

`gebra.extract()` reads a LangGraph workflow **definition** and writes out a document — the
Gebra IR. This page takes one small `StateGraph` through that step, reads the document field
by field, then reads the other half of what extraction hands back — the warnings that say how
it read your code — and ends at the boundary of what reading a definition can know at all.

Nothing on this page runs a workflow. Extraction **imports and inspects; it never invokes** —
no node function, router, tool or model is called, and no connection is opened
(INTROSPECTION-SPEC §1). The node bodies in both examples raise if anything calls them, and
CI checks that nothing did, so that sentence is held rather than repeated.

You need `gebra` installed and about fifteen minutes. If you want the concepts underneath
first, [The IR, node identity and `graph_version`](../concepts/ir-and-graph-version.md) is the
reference this page keeps pointing back to.

## A workflow, and its first extraction

Here is a research assistant: it plans a search, loops while it wants more notes, and writes
an answer. The example writes that file out and then extracts from it, so the transcript below
is what gebra produces from a module on disk — which is how it will read yours. Where the
definition lives is not incidental: extraction locates a node's source the way any Python tool
does, and what it can read there is part of what ends up in the document.

<!-- gebra:example id=your-first-ir -->
```python
from pathlib import Path

import gebra
from gebra.ir import dump_yaml

# The file you would have written yourself. Save these lines as research_agent.py and the
# rest of this page reproduces exactly.
AGENT = '''\
"""A small research assistant: plan a search, gather notes, write an answer."""

import operator
from typing import Annotated, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph


class ResearchState(TypedDict):
    question: str
    notes: Annotated[list[str], operator.add]
    answer: str


class Notes(TypedDict):
    notes: list[str]


class Answer(TypedDict):
    answer: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    """Record that a node body was entered, then refuse to run it.

    gebra reads a definition and never runs it, and this first line of every body lets CI
    hold that claim on this page: reaching one records the node in TRIPPED before anything
    else can go wrong, and the example fails. The real body under each call is what gebra
    reads; nothing here ever executes it.
    """
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def plan(state: ResearchState) -> Notes:
    unreached("plan")
    return {"notes": ["search for: " + state["question"]]}


def search(state: ResearchState) -> Notes:
    unreached("search")
    return {"notes": ["a result for " + state["question"]]}


def summarize(state: ResearchState) -> Answer:
    unreached("summarize")
    return {"answer": " ".join(state["notes"])}


def enough_notes(state: ResearchState) -> str:
    unreached("enough_notes")
    return "done" if len(state["notes"]) > 3 else "more"


workflow = StateGraph(ResearchState)
workflow.add_node("plan", plan)
workflow.add_node("search", search)
workflow.add_node("summarize", summarize)
workflow.add_edge(START, "plan")
workflow.add_edge("plan", "search")
workflow.add_conditional_edges("search", enough_notes, {"more": "search", "done": "summarize"})
workflow.add_edge("summarize", END)
'''

Path("research_agent.py").write_text(AGENT, encoding="utf-8")

import research_agent

envelope = gebra.extract(research_agent.workflow)

print(dump_yaml(envelope.ir))
print("warnings")
for warning in envelope.warnings:
    print(f"  {warning.code.value:19} {warning.node:10} {', '.join(warning.slots)}")

first = envelope.warnings[0]
print()
print("one record in full")
print("  code   ", first.code.value)
print("  node   ", first.node)
print("  slots  ", ", ".join(first.slots))
print("  message", first.message)
print("  detail ", first.detail)
```

<!-- gebra:output id=your-first-ir -->
```text
ir_version: '1.0'
entry: plan
finish: summarize
state:
  question:
    type: str
    optional: true
  notes:
    type: list[str]
    reducer: _operator.add
    optional: true
  answer:
    type: str
    optional: true
nodes:
- id: plan
  annotations:
    effect:
    - write
    input:
    - question
    output:
    - notes
- id: search
  annotations:
    effect:
    - write
    input:
    - question
    output:
    - notes
- id: summarize
  annotations:
    effect:
    - write
    input:
    - notes
    output:
    - answer
edges:
- kind: normal
  from: plan
  to: search
- kind: conditional
  from: search
  condition: enough_notes
  path_map:
    more: search
    done: summarize

warnings
  contract-inferred   plan       input, output
  contract-defaulted  plan       effect
  contract-inferred   search     input, output
  contract-defaulted  search     effect
  contract-inferred   summarize  input, output
  contract-defaulted  summarize  effect

one record in full
  code    contract-inferred
  node    plan
  slots   input, output
  message input and output inferred from the closed ANNOTATION-API-SPEC §4 patterns rather than declared; the claim is heuristic-grade and no other slot was upgraded
  detail  {'surface': 'inference', 'patterns': {'input': {'question': 'state-access'}, 'output': {'notes': 'return-annotation-keys'}}, 'claims_not_upgraded': ('idempotent', 'deterministic', 'variant', 'compensation', 'args_schema'), 'depth': 'shallow-only (DEC-08)'}
```

That is your first IR. `gebra.extract()` returned an **extraction envelope** with three
members: `envelope.ir` is the document, `envelope.warnings` is extraction's account of how it
read your code, and `envelope.extracted_from` is the provenance record — where the object came
from, and what the compiled level added when there was one, which matters at the end of this
page. The transcript shows the first two, and the next two sections read them in order.

That is not the same envelope as the one on the
[concepts page](../concepts/ir-and-graph-version.md#what-the-ir-is): that one is what
`gebra snapshot` wraps *around* a document when it records it.

## Reading the document

### `entry`, `finish`, and the sentinels that are not nodes

`entry: plan` because you wired `START` to `plan`; `finish: summarize` because you wired
`summarize` to `END`. Neither `START` nor `END` appears in `nodes[]` — the document encodes
their incidences positionally instead, which is one of the two IR shapes worth knowing before
anything else (the other is that a `conditional` edge is one edge per label). Both are
[explained here](../concepts/ir-and-graph-version.md#what-the-ir-is).

Both fields are lists that collapse to a scalar when only one node is wired. Written
`entry: [plan]` this document would be byte-identical after canonicalization, and would carry
the same `graph_version`.

A third form is worth recognising before you meet it. Where there is no statically known
entry — `START` never wired, or an entry router that declares no targets — the field is the
empty list `entry: []` rather than a guess, and a warning comes with it either way, though not
the same one: undeclared wiring and run-time dispatch are different facts about your graph.
`finish` behaves symmetrically, with one asymmetry worth knowing: a graph that reaches `END`
only through router labels rather than through a plain edge extracts `finish: []`
**warning-free**, because nothing about it is undeclared (INTROSPECTION-SPEC §2, §3). Whether
an entry-less graph is well formed is a question for verification and not for extraction —
`extract()` records what the definition says and passes no judgement on it.

### `state`

Three keys, each with the type LangGraph's channel machinery declares. Two things in that
block are worth a second look.

`notes` carries `reducer: _operator.add`. You wrote `Annotated[list[str], operator.add]`; the
IR records where that function actually lives, and `operator.add` is a re-export of the C
implementation in `_operator`. The reducer is recorded as a reference, not as behaviour — the
IR never carries a function body.

Every key is `optional: true`. That is not a claim that your state keys are optional in the
Python sense: it means the key is a **graph-input or defaulted key** — one a caller can supply
at `START`, or one the schema gives a default. The whole `ResearchState` is this graph's input
schema, so all three qualify on the first half alone, and the dataflow validator reads
`optional` as "written at `START`" when it asks whether a key is written before it is read
(INTROSPECTION-SPEC §3).

### `nodes`

One entry per `add_node`, keyed by the name you gave it. The ids here are single segments
because these are top-level nodes; nesting adds segments — an LCEL fragment inside a node
mounts under it, while subgraph children are a different case that the end of this page comes
back to. [Node identity](../concepts/ir-and-graph-version.md#node-identity) has the grammar.

Each node's `annotations` is its **resolved contract** — what it reads, what it writes, what
effects it has, and whether it is pure, idempotent or deterministic. Nothing in
`research_agent.py` declared any of that, and three of those slots — `effect`, `input`,
`output` — have values anyway. Where those values came from is exactly what the warnings say,
so read the two together and never one without the other. The slots that stayed empty stayed
empty on purpose: an absent `idempotent` is the document declining to answer, not a `false`.

### `edges`

Two of them, and they are different kinds of thing.

The `normal` edge `plan → search` is the whole story of that edge. The `conditional` edge is
not: it records `condition: enough_notes` and a `path_map`, and the `condition` is the
**declared branch name**, not the router's logic. LangGraph names a branch after its path
callable, gebra records that name, and the body of `enough_notes` never enters the document at
all (INTROSPECTION-SPEC §6). Two branches on different source nodes may share a name, so the
pair `(from, condition)` is what identifies an edge group — never `condition` alone
(INTROSPECTION-SPEC §3).

The `path_map` is where the targets come from, and each of its labels becomes its own directed
edge before any analysis runs. So `more: search` is a real edge from `search` back to itself —
a cycle in this workflow, and the kind of shape the property validators have questions about
([what gebra checks](../concepts/what-gebra-checks.md)).

## Reading the warnings

An extraction warning is not an error. The extraction above succeeded; every warning it
carries is a statement about **how a value got into the document**. They ride in the
provenance envelope rather than in the IR, outside the hash scope, so a warning never moves
your `graph_version` (INTROSPECTION-SPEC §8).

Six warnings, two codes, and together they account for every heuristic slot in the document:

- **`contract-inferred`** — extraction filled `input` and `output` from the closed table of
  licensed patterns, and the record names which pattern licensed which key. For `plan` the
  full record shows `input` came from `state-access` (the literal `state["question"]` read in
  the body) and `output` from `return-annotation-keys` (the `-> Notes` `TypedDict`). The
  detail also carries `claims_not_upgraded`: inference never reaches `idempotent`,
  `deterministic`, `variant`, `compensation` or `args_schema`. That is the rule the whole
  class rests on — **inference never upgrades a claim** (INTROSPECTION-SPEC §0).
- **`contract-defaulted`** — `effect` is never inferred at all: the closed §4 pattern table
  covers `input` and `output` and nothing else, so an undeclared `effect` falls to the
  conservative default, and a node that writes state is recorded as having a `write` effect. A
  default is the floor, never an upgrade.

Two things about that pair are worth carrying away.

**Inference reads the node's own body and nothing further.** A literal `state["question"]` in
`plan` licenses `input: [question]`; a helper that `plan` called and that read three more keys
would license nothing, because following calls is not what shallow inference does. This is why
the inferred contract is a floor and not a survey.

**A warning is a structured record, not a sentence.** The `message` field is there for people
and is display-only; everything a tool should branch on is in `code`, `node`, `slots` and
`detail`. That gives you a precise rule for reading any extracted document:

> A **contract** slot on a node — one of the nine an author can declare — is **declared**
> exactly when no `contract-inferred` or `contract-defaulted` warning in the envelope names
> that `(node, slot)` pair (ANNOTATION-API-SPEC §5).

The rule is quantified over those nine and no further. `retry_policy` is projected off the
builder, and `prompt_digest`/`config_digest` are computed by the extractor, so no contract
warning ever names them and the rule says nothing about them.

Which is how you would clear these six: declare the contracts, with the `@gebra.contract`
decorator or a `gebra.toml` sidecar, and the warnings that named those slots stop being
emitted. That is the annotation surface, and it has its own tutorial —
[Contracts and annotations](contracts-and-annotations.md).

The full vocabulary is ten codes, fixed jointly by INTROSPECTION-SPEC §8 and
ANNOTATION-API-SPEC §4, which states the relationship outright: its annotation-surface rows
*are* part of the single §8 taxonomy. This page shows four of them. The other six cover an
opaque LCEL lambda body, a disagreement between a compiled graph and its builder, a compiled
object extracted with no builder to read, and three that only the declaration surfaces raise —
a decorator and a sidecar setting one slot to different values, a sidecar entry naming a node
that is not in the graph, and a resolved contract that breaks an invariant no single surface
broke. One property of that vocabulary matters even when you never read a warning: a
**warning-free** extraction is part of what strict mode asks for (§8), so warnings are a gate
input and not just commentary.

## What extraction can know: the four knowability classes

Every field in the IR arrives with a class attached — how much trust it needs. The four are
fixed by INTROSPECTION-SPEC §0 and used throughout that specification, and they are the
vocabulary for everything above.

| Class | What it means |
|---|---|
| **Full** | Recoverable from the object graph alone; no trust required. |
| **Declared-trusted** | Present iff an author declared it (decorator, sidecar, `path_map`, type hint); truthfulness trusted, per the DEFENSIBLE-A discipline. |
| **Inferred-warned** | Extraction may infer it; a warning always accompanies it; inference never upgrades a claim. |
| **Runtime-only** | Not statically knowable; the IR models its absence honestly, never guesses. |

Those four cells are the specification's own, with two things left out and nothing else
changed: the cross-references in them point at documents this site does not publish, and the
specification's RFC-2119 keywords are addressed to whoever implements an extractor rather than
to you. What DEFENSIBLE-A means, and why a declaration is trusted rather than checked, is on
[what gebra checks](../concepts/what-gebra-checks.md).

Here is the same assistant grown a little, chosen so that all four appear in one extraction: a
triage router that decides at run time which search to dispatch, two searches that join, and
one node whose contract is declared rather than read.

<!-- gebra:example id=knowability-classes -->
```python
from pathlib import Path

import gebra
from gebra.verify import verify

AGENT = '''\
"""The research assistant, grown: a triage router and two searches that join."""

import operator
from typing import Annotated, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class ResearchState(TypedDict):
    question: str
    notes: Annotated[list[str], operator.add]
    answer: str


class Notes(TypedDict):
    notes: list[str]


class Answer(TypedDict):
    answer: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def triage(state: ResearchState) -> Notes:
    unreached("triage")
    return {"notes": ["triaged: " + state["question"]]}


@gebra.contract(reads=["question"], writes=["notes"], effects=["network"])
def search_web(state: ResearchState) -> Notes:
    unreached("search_web")
    return {"notes": ["a web result"]}


def search_docs(state: ResearchState) -> Notes:
    unreached("search_docs")
    return {"notes": ["a docs result"]}


def merge(state: ResearchState) -> Notes:
    unreached("merge")
    return {"notes": sorted(state["notes"])}


def summarize(state: ResearchState) -> Answer:
    unreached("summarize")
    return {"answer": " ".join(state["notes"])}


def pick_a_source(state: ResearchState) -> str:
    """Decide at run time which search to dispatch. Nothing declares its targets."""
    unreached("pick_a_source")
    return "search_web" if "code" in state["question"] else "search_docs"


def enough_notes(state: ResearchState) -> str:
    unreached("enough_notes")
    return "done" if len(state["notes"]) > 3 else "more"


workflow = StateGraph(ResearchState)
for name, body in (
    ("triage", triage),
    ("search_web", search_web),
    ("search_docs", search_docs),
    ("merge", merge),
    ("summarize", summarize),
):
    workflow.add_node(name, body)
workflow.add_edge(START, "triage")
workflow.add_conditional_edges("triage", pick_a_source)
workflow.add_edge(["search_web", "search_docs"], "merge")
workflow.add_conditional_edges("merge", enough_notes, {"more": "triage", "done": "summarize"})
workflow.add_edge("summarize", END)
'''

Path("research_agent.py").write_text(AGENT, encoding="utf-8")

import research_agent

envelope = gebra.extract(research_agent.workflow)

ir = envelope.ir
node = {entry.id: entry for entry in ir.nodes}
warned = {(w.node, w.code.value): ", ".join(w.slots) for w in envelope.warnings}


def contract(node_id: str) -> str:
    """The node's resolved contract, one slot per column."""
    slots = node[node_id].annotations.model_dump(exclude_none=True)
    return "  ".join(f"{name}={list(value)}" for name, value in slots.items())


print("ir_version:", ir.ir_version)
print()
print("Full — recovered from the object graph, no trust required")
print("  nodes     ", ", ".join(sorted(node)))
for key, value in ir.state.items():
    reducer = f"  reducer={value.reducer}" if value.reducer else ""
    print(f"  state      {key}: {value.type}{reducer}")
print()
print("Declared-trusted — present because an author declared it")
print("  search_web", contract("search_web"))
for edge in ir.edges:
    if edge.kind == "conditional":
        print(f"  path_map   on {edge.from_}: {edge.path_map}")
print()
print("Inferred-warned — extraction filled it in, and said so")
print("  merge     ", contract("merge"))
print("  warned     contract-inferred:", warned[("merge", "contract-inferred")])
print("             contract-defaulted:", warned[("merge", "contract-defaulted")])
print()
print("Runtime-only — the definition does not say, so neither does the IR")
for edge in ir.edges:
    if edge.kind == "dynamic":
        print("  targets   ", edge.model_dump(mode="json", exclude_none=True, by_alias=True))
print("  runtime   ", ir.runtime)
print()
print("warnings about the shape of the graph")
for warning in envelope.warnings:
    detail = warning.detail
    if warning.code.value == "barrier-flattened":
        print(
            f"  barrier-flattened      {list(detail['sources'])} -> {detail['target']}, "
            f"expanded to {detail['edges_expanded']} normal edges"
        )
    if warning.code.value == "unsupported-construct":
        print(
            f"  unsupported-construct  {warning.node}: {detail['construct']} "
            f"(the IR is partial there: {detail['ir_partial']})"
        )

gate = verify(ir).gate
print()
print("verifying a 1.1 document in this release")
print("  gate      ", gate.outcome, "| exit", gate.exit_code)
```

<!-- gebra:output id=knowability-classes -->
```text
ir_version: 1.1

Full — recovered from the object graph, no trust required
  nodes      merge, search_docs, search_web, summarize, triage
  state      question: str
  state      notes: list[str]  reducer=_operator.add
  state      answer: str

Declared-trusted — present because an author declared it
  search_web effect=['network']  input=['question']  output=['notes']
  path_map   on merge: {'more': 'triage', 'done': 'summarize'}

Inferred-warned — extraction filled it in, and said so
  merge      effect=['write']  input=['notes']  output=['notes']
  warned     contract-inferred: input, output
             contract-defaulted: effect

Runtime-only — the definition does not say, so neither does the IR
  targets    {'kind': 'dynamic', 'from': 'triage', 'condition': 'pick_a_source'}
  runtime    None

warnings about the shape of the graph
  barrier-flattened      ['search_web', 'search_docs'] -> merge, expanded to 2 normal edges
  unsupported-construct  triage: router-without-declared-targets (the IR is partial there: True)

verifying a 1.1 document in this release
  gate       tool-error | exit 2
```

Reading the four blocks in order:

**Full.** Node ids, the normal edges, and the state keys with their types and reducer come off
the builder itself. Nothing was trusted and nothing was guessed; extracting the same source
again produces the same values.

**Declared-trusted.** `search_web` carries a `@gebra.contract` declaration, so its `network`
effect is in the document because its author put it there. gebra checks that a declaration is
coherent with the graph — it does not check the body against the declaration, which is what
"trusted" means here and what the DEFENSIBLE-A claim class exists to label
([what gebra checks](../concepts/what-gebra-checks.md)). The `path_map` on `merge` is the same
class for a different reason: those two targets are known because the author wrote them in the
call, and a router with no such declaration is the next block.

**Inferred-warned.** `merge` declared nothing, so its `input` and `output` were inferred and
its `effect` defaulted — and the two warnings naming `(merge, …)` are what keep those values
readable as heuristic rather than as declared. This is the class that would be invisible
without the warnings, which is why the class and the warning are one thing.

**Runtime-only.** `pick_a_source` is a router with no `path_map`, no `Literal` return hint and
no `destinations=`, so which node runs after `triage` is decided when the workflow runs. The
IR says so: the edge is `kind: dynamic` and carries **no target fields at all** rather than a
guessed set (INTROSPECTION-SPEC §6). And `runtime` is absent entirely, which is the next
section.

### The two warnings about shape

`barrier-flattened` is emitted because `add_edge(["search_web", "search_docs"], "merge")`
declares an all-of barrier — `merge` waits for both — and the IR edge vocabulary has no way to
say "waits for both" in this format version. Extraction expands it into two plain edges and
records the flattening, which makes analyses over the result conservative in a stated
direction: they may over-report, never under-report. The missing carrier is a recorded gap with
a candidate edge kind for a later version, not an oversight (INTROSPECTION-SPEC §3, §7.3).

`unsupported-construct` is the code for a construct extraction cannot map, and its record says
where and whether the IR is partial there — here, `ir_partial: True` at `triage`. It is worth
knowing that this warning covers a family, not one situation: a bare `Send` computed inside a
callable, a conditional entry with no declared targets, missing `START`/`END` wiring,
self-referential composition, a version outside the supported range, and more
(INTROSPECTION-SPEC §8).

### One consequence to know before you build on this

A `dynamic` edge has a consequence downstream, and it is better met here than in a pipeline.
The document extracts, and stamps itself `ir_version: 1.1` because it uses the 1.1
edge kind — and verifying it reaches **no verdict**: the gate is `tool-error` and the exit
code is `2`. That code means "no verdict was reached", never "the workflow failed": the
[exit-code ladder](../concepts/what-gebra-checks.md#exit-codes) keeps those two apart on
purpose. The first agent on this page, whose router has a `path_map`, is a 1.0 document and
does not hit this.

Declaring the router's targets is what moves an edge out of this class — a `path_map`, a
`Literal[...]` return hint, or `destinations=` on the node. That is a declaration, so it is
trusted rather than checked; it buys a target set the analysis can see, and nothing more.

## What a builder cannot know — and one thing nothing can

`runtime` came back `None` above, and that is the never-guess rule in action. Interrupt gates
and whether you attached a checkpointer are **compile-time** facts: they exist on the compiled
graph, not on the builder you handed to `extract()`. Rather than assume a default, extraction
leaves the slot out. Hand it `workflow.compile()` instead and both become known — though a
graph with no gates emits no `interrupts` member at all, while checkpointer presence is
recorded explicitly either way, `true` or `false`, because at that level it is a fact rather
than an absence (INTROSPECTION-SPEC §4.1, §7.1). The two are genuinely different documents,
with different `graph_version`s.

The third member of `runtime` is absent for a different reason. `recursion_limit` is
invoke-time configuration and is not on either object, so no level of extraction produces it:
it is there only if you declare it.

The compiled level is also where subgraphs are discovered, and it carries a limitation the
specification names and accepts rather than papers over.

!!! warning "Subgraphs compiled with `checkpointer=False` are invisible"

    A node whose body is a compiled subgraph is found by walking the compiled graph's own
    subgraph discovery. **A subgraph compiled with `checkpointer=False` does not appear in
    that walk** (INTROSPECTION-SPEC §4.1, citing the pinned LangGraph introspection survey).

    Two consequences, and they are worth stating plainly:

    - The recorded set of subgraph-bearing nodes is a **lower bound**, not a census. It is
      provenance — `extracted_from.compiled.subgraphs` — and a node missing from it may still
      hold a subgraph.
    - **No warning is emitted for the ones that are missed.** Extraction cannot warn about
      what it cannot see, so this paragraph is the warning. If your workflow compiles
      subgraphs with `checkpointer=False`, do not read an empty or short list as evidence that
      there are none.

    What this does *not* change: the parent node itself is still a node of the parent graph
    and is extracted like any other, with its own contract and its own edges. And in
    `ir_version` 1.0 and 1.1 a discovered subgraph is carried as its **parent node only** —
    child nodes, child edges and the child's own `entry`, `finish` and state schema are not
    emitted for *any* subgraph, visible or not. That unexpansion is a deliberate scope line
    rather than a failure: such a document is **complete**, carries no warning for it, and
    reaches the strict-mode bar like any other. Child expansion is a recorded design item for a
    later format version; it is described in this repository's
    `docs/governance/EXTRACTOR-API-FREEZE.md` and is not part of this release.

The honest summary is the one INTROSPECTION-SPEC §0 gives the whole extraction contract: where
something is not statically knowable, the IR models its absence rather than guessing — and
where the absence itself cannot be detected, the specification text is the disclosure.

## Where to go next

- [The IR, node identity and `graph_version`](../concepts/ir-and-graph-version.md) — the
  document format in depth: the hash scope, the id grammar, and what does and does not move a
  version.
- [Contracts and annotations](contracts-and-annotations.md) — declaring the contracts those
  warnings are about: the decorator family, the `gebra.toml` sidecar, the precedence chain
  between them, and what inference will never fill in for you.
- [What gebra checks](../concepts/what-gebra-checks.md) — claim classes, severity, exit codes,
  and what a finding does and does not claim, which is what you need before reading a report
  over the document you just extracted.
- The repository `README.md` quickstart runs `gebra verify` over a workflow module from the
  command line, end to end, if you would rather meet the CLI first than the library.

## Where this page is checked

Both examples are executed in CI, in a child interpreter where compiling a graph, invoking a
runnable, resolving a hostname or opening a connection all raise, and the transcripts above are
what those runs printed — [Executable examples](../contributing/executable-examples.md)
explains the harness. The first line of every node body records that node in a `TRIPPED` ledger
before anything else can happen, and the harness sweeps the module each example wrote: a node
call that some `try` block swallowed would still fail the example rather than passing silently,
and a written module keeping no ledger fails it too, rather than reading as clean.

Both examples take the **builder** path — they extract the uncompiled `StateGraph` — because
the harness does not admit an example that compiles a graph. So the compiled-level paragraphs
above are not shown by a transcript here. What gebra itself does at that level *is* held by the
extractor's conformance tests in this repository: `runtime.checkpointer` emitted either way,
and a discovered subgraph carried as its parent node.

The `checkpointer=False` blind spot is the one claim on this page with no test behind it
anywhere, and it cannot have one: it is a property of LangGraph's own subgraph discovery, and
extraction cannot observe what it cannot see. INTROSPECTION-SPEC §4.1 is the whole of the
evidence, which is why the box above says so in those words.
