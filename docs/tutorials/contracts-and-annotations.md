# Contracts and annotations

[Extract your first IR](extract-your-first-ir.md) ended its first extraction with six warnings
and one sentence about clearing them: *declare the contracts*. This page is that sentence
worked out. It takes the same research assistant through the two surfaces you write by hand —
the `@gebra.contract` decorator family and the `gebra.toml` sidecar — then through the chain
that decides which declaration wins when two of them disagree, and ends at the line inference
will not cross on your behalf.

The question this page is written to answer is narrow and practical: **for any slot on any
node, which surface set it, and how would you know?** Everything else follows from that.

Nothing here runs a workflow. Declaring a contract attaches metadata and returns your function
unchanged — the decorator never wraps, reorders or invokes it (ANNOTATION-API-SPEC §1) — and
extraction reads the definition without executing it. The node bodies in every example raise if
anything calls them, and CI checks that nothing did.

You need `gebra` installed, about twenty minutes, and ideally the previous tutorial behind you.

## What a contract is

A node's contract is what the IR calls its `annotations`: what the node reads, what it writes,
what it does to the world, and which of a few properties its author is willing to declare about
it. **Nine slots** are settable, and §1 closes the set — the decorator surface and the sidecar
share it byte for byte:

| Slot | Declares | Decorator |
|---|---|---|
| `input` | the state keys the node reads | `contract(reads=[…])` |
| `output` | the state keys it writes | `contract(writes=[…])` |
| `effect` | what it does to the world, from the closed vocabulary `network`, `write`, `external`, `irreversible`, `billable` | `contract(effects=[…])` · `@gebra.effect(…)` |
| `pure` | that it has no effects at all | `contract(pure=True)` · `@gebra.pure` |
| `idempotent` | that running it twice is running it once — plainly, or keyed on a state key | `contract(idempotent=…)` · `@gebra.idempotent` · `@gebra.idempotent(key=…)` |
| `deterministic` | that it replays — plainly, or with a seed and optionally a temperature | `contract(deterministic=…)` · `@gebra.deterministic` · `@gebra.deterministic(seed=…, temperature=…)` |
| `args_schema` | a JSON Schema for the node's arguments | `contract(args_schema={…})` |
| `variant` | a loop variant: a state key and a measure over it | `@gebra.variant(key=…, measure=…)` |
| `compensation` | the node id of a compensating hook for this node | `@gebra.compensation(hook=…)` |

Four of those decorators — `@gebra.pure`, `@gebra.effect`, `@gebra.idempotent`,
`@gebra.deterministic` — are shorthand for a single `contract` keyword. The last two are not:
`variant` and `compensation` have no `contract(...)` keyword and are settable only through
their own decorators. All of them stack, with each other and with `@gebra.contract`, subject to
one rule this page comes back to: each slot is settable once.

Those last two are also slots this page records rather than explains. What measures a `variant`
may use, and what a declared one has to discharge, belong to the termination-witness
specification; `compensation` is a slot the IR carries and whose consuming semantics are
deferred. Neither value is interpreted by the annotation surface — both are stored as written.

Other things a node contract can carry are **not** on that list, and no surface on this page
sets them: `retry_policy` is projected off the builder, `prompt_digest` and `config_digest` are
computed by the extractor, and `source`/`map` belong to a parked track with no surface in this
specification at all. Interrupt gates and checkpointer presence are not node contracts to begin
with — they are `compile()` arguments, extracted rather than annotated. §1 states the line
once: those are *extracted or computed, never annotated*.

What each slot unlocks downstream is the validators' business, and
[what gebra checks](../concepts/what-gebra-checks.md) is where that story is. This page is
about how a value gets into a slot in the first place.

## Declaring in code

Here is the research assistant from the previous tutorial with its contracts declared. The
example writes the module to a file and imports it, exactly as before: extraction locates a
node's source the way any Python tool does, and what it can read there is part of the result.

<!-- gebra:example id=declaring-contracts -->
```python
from pathlib import Path

import gebra

AGENT = '''\
"""The research assistant, with its contracts declared."""

import operator
from typing import Annotated, NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class ResearchState(TypedDict):
    question: str
    notes: Annotated[list[str], operator.add]
    answer: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    """Record that a body was entered, then refuse to run it — see the previous tutorial."""
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


@gebra.contract(reads=["question"], writes=["notes"], effects=["write"])
def plan(state):
    unreached("plan")
    return {"notes": ["search for: " + state["question"]]}


@gebra.contract(reads=["question"], writes=["notes"])
@gebra.effect("network")
@gebra.idempotent(key="question")
def search(state):
    unreached("search")
    return {"notes": ["a result"]}


@gebra.contract(reads=["notes"], writes=["answer"])
@gebra.effect("network", "billable")
@gebra.deterministic(seed=7, temperature=0.0)
def summarize(state):
    unreached("summarize")
    return {"answer": " ".join(state["notes"])}


def enough_notes(state) -> str:
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

for node in envelope.ir.nodes:
    print(node.id)
    for slot, value in node.annotations.model_dump(exclude_none=True).items():
        print(f"  {slot:14} {value}")

print()
print("warnings:", [warning.code.value for warning in envelope.warnings])
print("the declaration rides on the function object, which is otherwise unchanged:")
print("  ", [name for name in vars(research_agent.search) if name.startswith("__gebra")])
```

<!-- gebra:output id=declaring-contracts -->
```text
plan
  effect         ('write',)
  input          ('question',)
  output         ('notes',)
search
  effect         ('network',)
  idempotent     {'key': 'question'}
  input          ('question',)
  output         ('notes',)
summarize
  effect         ('network', 'billable')
  deterministic  {'seed': 7, 'temperature': 0.0}
  input          ('notes',)
  output         ('answer',)

warnings: []
the declaration rides on the function object, which is otherwise unchanged:
   ['__gebra_contract__']
```

Read the transcript against the module and three things stand out.

**The warning list is empty.** The six warnings the previous tutorial's extraction carried are
gone, because every slot they were about is now declared. Be precise about what that buys:
extraction warnings are not findings and **never move an exit code** — `gebra verify` renders
them and gates on properties. What declaring changed is the *grade* of these values. A
validator reading `effect` on `search` is now reading an author's statement rather than a
heuristic, and that distinction is what the last section of this page is about.

**Stacked decorators compose into one contract.** `search` and `summarize` carry three
decorators each and one contract came out of each stack. A shorthand fills exactly the slot it
names — `@gebra.idempotent(key="question")` is `idempotent`, and nothing else — while
`@gebra.contract` fills whichever slots you pass it. What stacking does *not* do is merge:
setting one slot twice is an error, which the next section fires.

**The function came back unchanged.** `@gebra.contract` attaches a single namespaced attribute,
`__gebra_contract__`, and returns the same function object — it is not a wrapper. That is what
lets a declaration survive what LangGraph does to a node callable afterwards, since there is no
Gebra wrapper for anything to replace. The last part of this section is about a way it can
still be lost.

### The rules that fire at import

Four consistency rules are checked when the decorator runs — that is, when your module is
imported, before a graph exists and long before extraction. They raise `GebraContractError`,
and §1's word for why they live there is *cheap, early*.

<!-- gebra:example id=decoration-time-rules -->
```python
import gebra
from gebra.annotations import GebraContractError

TRIPPED = []


def unreached(name):
    """A decorator reads its target and returns it; nothing here is ever called."""
    TRIPPED.append(name)
    raise AssertionError("gebra does not run the callables it annotates")


class VendoredStep:
    """A callable object from elsewhere, defined with __slots__ — it carries no attributes."""

    __slots__ = ()

    def __call__(self, state):
        unreached("VendoredStep")


def refused(label, declare):
    """Apply a declaration that will be refused, and show what it says."""

    def target(state):  # a fresh one each time: the attribute is attached in place
        unreached("target")

    try:
        declare(target)
    except GebraContractError as error:
        print(f"{label}\n  reason: {error.reason.value}\n  slot:   {error.slot}\n  {error}\n")
    else:
        print(f"{label}\n  accepted\n")


refused(
    "pure together with an effect",
    lambda fn: gebra.contract(pure=True, effects=["network"])(fn),
)
refused(
    "an effect tag outside the closed vocabulary",
    lambda fn: gebra.effect("expensive")(fn),
)
refused(
    "the deterministic object form without a seed",
    lambda fn: gebra.deterministic(temperature=0.0)(fn),
)
refused(
    "one slot set twice in a stack",
    lambda fn: gebra.effect("network")(gebra.contract(effects=["network"])(fn)),
)
refused(
    "a target that cannot carry the attribute",
    lambda fn: gebra.effect("network")(VendoredStep()),
)
```

<!-- gebra:output id=decoration-time-rules -->
```text
pure together with an effect
  reason: pure-effect-exclusive
  slot:   pure
  this stack declares pure=True together with the effects ['network']; the two are mutually exclusive (decision D-011, ANNOTATION-API-SPEC §1). A node that touches the world is not pure — drop whichever of the two is not true of it (reached at @gebra.contract)

an effect tag outside the closed vocabulary
  reason: unknown-effect-tag
  slot:   effect
  'expensive' is not an effect tag. The decision D-011 vocabulary is closed: billable, external, irreversible, network, write (ANNOTATION-API-SPEC §1)

the deterministic object form without a seed
  reason: deterministic-seed-required
  slot:   deterministic
  @gebra.deterministic(temperature=...) without seed= declares nothing replayable: the object form requires seed (ANNOTATION-API-SPEC §1; the frozen ledger §3 shape is {"seed": <int>, "temperature"?: <number>})

one slot set twice in a stack
  reason: duplicate-slot
  slot:   effect
  @gebra.effect sets 'effect' to ('network',), but a decorator below it in this stack already set it to ('network',). A slot is settable at most once across a decorator stack, and a duplicate is an error rather than a merge — identical values included, because one author's stack has no drift to excuse (ANNOTATION-API-SPEC §1). Declare the slot once.

a target that cannot carry the attribute
  reason: attachment-impossible
  slot:   None
  @gebra.effect cannot attach __gebra_contract__ to a __main__:VendoredStep ('VendoredStep' object has no attribute '__gebra_contract__' and no __dict__ for setting new attributes); for a target that cannot carry attributes — a slotted or frozen object, a bound method of one, a remote tool — the gebra.toml sidecar is the designated fallback (ANNOTATION-API-SPEC §6)
```

The first four are §1's consistency rules. The duplicate is worth a second look: the two values
are *identical*, and it is still an error. §1 is deliberate about this — "a single author's
stack has no drift to excuse" — and it is stricter than the cross-surface rule further down
this page, where identical values are not a conflict at all.

The fifth is not a consistency rule but a shape the surface does not have. An object defined
with `__slots__` has nowhere to put an attribute, so the contract could not be attached, and
the decorator refuses rather than dropping it silently. Its message names the answer: for a
callable you cannot attach anything to — a slotted or frozen object, a bound method of one, a
remote tool — the sidecar is the designated fallback, which is the next section.

Two checks you might expect here are deliberately absent. Whether an idempotency key is
actually among the node's inputs, and whether an `irreversible` node also declares the keyless
`idempotent=True`, are questions about the *resolved* contract — the one assembled from every
surface — so they cannot be answered by a decorator in isolation. They run at extraction, and
they warn rather than raise, because extraction stays total. Note the second one's shape: it is
the keyless form that is rejected beside `irreversible`, not idempotence as such. A keyed
`idempotent = { key = … }` on an irreversible node is the intended pattern, and the sidecar
below declares exactly that.

### A declaration that never arrives

There is one way to write a well-formed declaration that gebra never sees, and it is worth
meeting deliberately rather than in a report you do not understand. Extraction finds the
contract by walking inward from the callable LangGraph holds, following `functools.wraps`
chains and the wrapper attributes LangGraph and LangChain use. A decorator of yours sitting
between `@gebra.contract` and the function that does **not** apply `functools.wraps` breaks
that walk (§6).

<!-- gebra:example id=wrapped-declarations -->
```python
from pathlib import Path

import gebra

AGENT = '''\
"""One declaration, written twice — and only one of them arrives."""

import functools
from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class State(TypedDict):
    query: str
    hits: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def timed(fn):
    """An ordinary decorator of your own that forgets functools.wraps."""

    def inner(state):
        return fn(state)

    return inner


def timed_carefully(fn):
    """The same decorator, one line longer."""

    @functools.wraps(fn)
    def inner(state):
        return fn(state)

    return inner


@timed
@gebra.contract(reads=["query"], writes=["hits"], effects=["network"])
def lost(state):
    unreached("lost")
    return {"hits": "a result"}


@timed_carefully
@gebra.contract(reads=["query"], writes=["hits"], effects=["network"])
def kept(state):
    unreached("kept")
    return {"hits": "a result"}


workflow = StateGraph(State)
workflow.add_node("lost", lost)
workflow.add_node("kept", kept)
workflow.add_edge(START, "lost")
workflow.add_edge("lost", "kept")
workflow.add_edge("kept", END)
'''

Path("wrapped_agent.py").write_text(AGENT, encoding="utf-8")

import wrapped_agent

envelope = gebra.extract(wrapped_agent.workflow)

for node in envelope.ir.nodes:
    print(node.id, node.annotations.model_dump(exclude_none=True))
print()
for warning in envelope.warnings:
    print(f"{warning.code.value:19} {warning.node:6} {', '.join(warning.slots)}")
```

<!-- gebra:output id=wrapped-declarations -->
```text
kept {'effect': ('network',), 'input': ('query',), 'output': ('hits',)}
lost {'pure': True}

contract-defaulted  lost   pure
```

`lost` and `kept` carry the same declaration and resolve differently. Through the unwrapped
decorator gebra never reaches the attribute, so the node reads as **never annotated**, and
what it falls back to is inference over the body it can see — which is now `inner`, whose
`return fn(state)` matches no pattern at all. The declared `network` effect is not merely
missing: the node ends up recorded as `pure: true`, the opposite claim, at defaulted grade.

The failure is silent by construction: nothing distinguishes "the author declared nothing" from
"the author declared something a wrapper hid", so there is no warning to emit and the
`contract-defaulted` record is the only trace. Two habits close it: apply `functools.wraps` in
your own decorators, and read the warning list per *slot*. A decorated node in that list is
ordinary — it means some slot it did not declare was filled by inference. A slot you know you
declared showing up in a `contract-inferred` or `contract-defaulted` record is this bug.

## Declaring beside the code

Some node callables are not yours to decorate: a vendored function, a third-party tool, a
bound method of a class you do not own. For those, the same nine slots live in a `gebra.toml`
sidecar keyed by **IR node id** (§2).

<!-- gebra:example id=the-sidecar -->
```python
from pathlib import Path

import gebra
from gebra.extraction import ExtractionWarningCode

AGENT = '''\
"""A booking step from a library we do not own, and a step of our own."""

from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph


class TripState(TypedDict):
    itinerary: str
    budget: int
    booking_ref: str
    notes: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


def book_flight(state):
    """Vendored: we cannot put a decorator in this file."""
    unreached("book_flight")
    return {"booking_ref": "PNR-1"}


def confirm(state):
    unreached("confirm")
    return {"notes": "confirmed " + state["booking_ref"]}


workflow = StateGraph(TripState)
workflow.add_node("book_flight", book_flight)
workflow.add_node("confirm", confirm)
workflow.add_edge(START, "book_flight")
workflow.add_edge("book_flight", "confirm")
workflow.add_edge("confirm", END)
'''

SIDECAR = """\
schema = "gebra-sidecar-v1"

[nodes.book_flight]
reads      = ["itinerary", "budget", "booking_ref"]
writes     = ["booking_ref"]
effects    = ["network", "billable", "irreversible"]
idempotent = { key = "booking_ref" }

[nodes.reserve_car]
effects = ["network"]
"""

Path("trip_agent.py").write_text(AGENT, encoding="utf-8")
Path("gebra.toml").write_text(SIDECAR, encoding="utf-8")

import trip_agent

envelope = gebra.extract(trip_agent.workflow, sidecar="gebra.toml")

for node in envelope.ir.nodes:
    print(node.id)
    for slot, value in node.annotations.model_dump(exclude_none=True).items():
        print(f"  {slot:11} {envelope.slot_grade(node.id, slot).value:9} {value}")

print()
print("sidecar recorded in provenance:", Path(envelope.extracted_from.sidecar).name)
print()
for warning in envelope.warnings:
    where = warning.node or "(the file itself)"
    print(f"{warning.code.value:23} {where:18} {', '.join(warning.slots) or '—'}")

stale = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE)[0]
print()
print("the stale entry, in full")
print("  key    ", stale.detail["key"])
print("  file   ", Path(stale.detail["file"]).name)
print("  message", stale.message)
```

<!-- gebra:output id=the-sidecar -->
```text
book_flight
  effect      declared  ('network', 'billable', 'irreversible')
  idempotent  declared  {'key': 'booking_ref'}
  input       declared  ('itinerary', 'budget', 'booking_ref')
  output      declared  ('booking_ref',)
confirm
  effect      defaulted ('write',)
  input       inferred  ('booking_ref',)
  output      inferred  ('notes',)

sidecar recorded in provenance: gebra.toml

contract-inferred       confirm            input, output
contract-defaulted      confirm            effect
annotation-unknown-node (the file itself)  —

the stale entry, in full
  key     reserve_car
  file    gebra.toml
  message the sidecar entry 'reserve_car' matches no extracted node id; a renamed node is a new identity (ir-field-ledger §5), so a stale key annotates nothing
```

Four things about that file are load-bearing.

**The `schema` line is not decoration.** A sidecar missing it, or carrying any other value, is
not loaded at all: extraction proceeds sidecar-less and says so with an `annotation-invalid`
warning naming the file and the value it found. That is the pattern for the whole file —
every sidecar validation failure is warning-grade, because the sidecar is configuration and
extraction stays total. A stale config degrades visibly; it does not brick anything.

**The key is a node id, byte for byte.** `book_flight` is a single-segment id, so it can be a
bare TOML key. A multi-segment id must be quoted, because `/` is not a bare-key character:
`[nodes."research/tools/web_search"]`. And a literal `/` inside a source name arrives already
percent-escaped, so it is written `[nodes."summarize%2Fmerge"]` — quote, never double-escape.
Matching is exact byte equality, case-sensitive.

**A key that matches nothing annotates nothing — and says so.** `reserve_car` is not a node of
this graph, and the `annotation-unknown-node` record names the file and the key. That is
deliberate:
[renaming a node produces a new identity](../concepts/ir-and-graph-version.md#node-identity),
so a rename leaves the old entry annotating nothing — silent config rot is exactly what the
warning exists to catch.

**Where the file comes from affects your digest.** The example passed `sidecar="gebra.toml"`
explicitly. Without it, discovery walks up from the *current working directory* to the
repository root — the nearest ancestor holding a `.git` entry, or the filesystem root if there
is none — and takes the first `gebra.toml` it finds: one file per extraction, never merged
across directories. Sidecar-filled annotations are inside the `graph_version` hash
scope, so a discovered-by-CWD sidecar makes your digest depend on where you ran the command.
Reproducible and CI extraction should pass `sidecar=` explicitly, and the envelope records the
absolute path it used — or its absence — so a digest that diverges can be diagnosed.

One limit of the format is worth knowing before you meet it. TOML has no null, so an
`args_schema` containing JSON `null` anywhere — a `default: null`, a null-bearing `enum`, a
`type: "null"` — cannot be written in a sidecar at all and has to go through the decorator.
Every other slot value transliterates one-to-one.

One line of that entry is also not arbitrary. `booking_ref` appears in `reads` because an
idempotency key has to be among the node's resolved inputs — a node cannot deduplicate on
something it does not look at. That is one of the two checks the previous section said the
decorator surface cannot make: it needs the resolved contract, so it runs at extraction and
warns rather than raises. Drop `booking_ref` from `reads` and this extraction gains an
`annotation-invalid` naming the key, the resolved input set and the rule.

Notice also what the grades say: `book_flight`'s four slots are **declared**, exactly like a
decorated node's. The sidecar is a declaration surface, not a form of guessing. `confirm`, which
declares nothing anywhere, is the inference case — and the last section of this page is about
what that costs.

## The precedence chain

When two surfaces speak about the same slot, resolution is **per-slot and strict**, in one
fixed order (§3):

1. **Decorator** — `@gebra.contract` and the shorthands.
2. **Tool-carried** — a LangChain `BaseTool`'s author-written `args_schema`; `args_schema` is
   the only slot with a source at this tier. It outranks the sidecar because the schema lives
   on the tool class and moves with the code.
3. **Sidecar** — `gebra.toml` fills slots the tiers above left unset.
4. **Inference** — shallow static analysis fills what remains, always warned.

Two clarifications carry most of the surprises. "Set" means **not `None`**: an explicit
`pure=False` is a declaration that occupies its slot and blocks the tiers below it exactly as a
positive value would. And a lower tier that disagrees does not silently lose — it produces an
`annotation-conflict` warning naming the slot, both values and both surfaces.

The booking agent again, now with all four tiers in play:

<!-- gebra:example id=precedence -->
```python
from pathlib import Path

import gebra

AGENT = '''\
"""One graph, four sources of contract."""

from typing import NoReturn, TypedDict

from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

import gebra


class TripState(TypedDict):
    itinerary: str
    budget: int
    booking_ref: str
    notes: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


class HotelArgs(BaseModel):
    destination: str
    nights: int = 1


def _find_hotels(destination: str, nights: int = 1) -> str:
    unreached("find_hotels.impl")
    return ""


# A third-party tool: its args_schema is author-written, so it is a declaration too.
find_hotels = StructuredTool(
    name="find_hotels",
    description="A tool we did not write. Never invoked.",
    args_schema=HotelArgs,
    func=_find_hotels,
)


@gebra.contract(reads=["itinerary"], effects=["network"])
def price_flight(state):
    unreached("price_flight")
    return {"notes": "priced"}


@gebra.contract(pure=False)
def notify(state):
    unreached("notify")
    return {"notes": "sent"}


@gebra.pure
def summarize(state):
    unreached("summarize")
    return {"notes": state["booking_ref"]}


def book_flight(state):
    unreached("book_flight")
    return {"booking_ref": "PNR-1"}


workflow = StateGraph(TripState)
for name, body in (
    ("find_hotels", find_hotels),
    ("price_flight", price_flight),
    ("book_flight", book_flight),
    ("notify", notify),
    ("summarize", summarize),
):
    workflow.add_node(name, body)
workflow.add_edge(START, "find_hotels")
workflow.add_edge("find_hotels", "price_flight")
workflow.add_edge("price_flight", "book_flight")
workflow.add_edge("book_flight", "notify")
workflow.add_edge("notify", "summarize")
workflow.add_edge("summarize", END)
'''

SIDECAR = """\
schema = "gebra-sidecar-v1"

[nodes.price_flight]
reads   = ["itinerary"]        # identical to the decorator's
effects = ["write"]            # and this one disagrees with it

[nodes.book_flight]
reads   = ["itinerary", "budget"]
writes  = ["booking_ref"]
effects = ["network", "billable"]

[nodes.notify]
pure = true                    # the decorator declared pure = false

[nodes.summarize]
effects = ["external"]         # the decorator declared @gebra.pure

[nodes.find_hotels.args_schema]
type  = "object"
title = "written in config"
"""

Path("booking_agent.py").write_text(AGENT, encoding="utf-8")
Path("gebra.toml").write_text(SIDECAR, encoding="utf-8")

import booking_agent


envelope = gebra.extract(booking_agent.workflow, sidecar="gebra.toml")


def shown(slot, value):
    """args_schema is a whole JSON Schema; show enough of it to tell the two apart."""
    if slot == "args_schema":
        return f"title={value['title']!r} properties={sorted(value['properties'])}"
    return value


def warning_on(node, code):
    """The one warning of that code naming that node."""
    return [item for item in envelope.warnings_for(node) if item.code.value == code][0]


print("resolved contracts")
for node in envelope.ir.nodes:
    for slot, value in node.annotations.model_dump(exclude_none=True).items():
        grade = envelope.slot_grade(node.id, slot).value
        print(f"  {node.id:13} {slot:11} {grade:9} {shown(slot, value)}")

print()
print("warnings")
for warning in envelope.warnings:
    print(f"  {warning.code.value:23} {warning.node:13} {', '.join(warning.slots)}")

print()
print("the conflict on price_flight, in full")
detail = warning_on("price_flight", "annotation-conflict").detail
print("  slot     ", detail["slot"])
print("  kept     ", detail["surfaces"]["kept"], detail["values"]["kept"])
print("  discarded", detail["surfaces"]["discarded"], detail["values"]["discarded"])

print()
print("the resolved contract that no single surface authored")
invalid = warning_on("summarize", "annotation-invalid")
print("  rule     ", invalid.detail["rule"])
print("  surfaces ", invalid.detail["surfaces"])
print("  values   ", invalid.detail["values"])
print("  message  ", invalid.message)
```

<!-- gebra:output id=precedence -->
```text
resolved contracts
  book_flight   effect      declared  ('network', 'billable')
  book_flight   input       declared  ('itinerary', 'budget')
  book_flight   output      declared  ('booking_ref',)
  find_hotels   pure        defaulted True
  find_hotels   args_schema declared  title='HotelArgs' properties=['destination', 'nights']
  notify        pure        declared  False
  notify        output      inferred  ('notes',)
  price_flight  effect      declared  ('network',)
  price_flight  input       declared  ('itinerary',)
  price_flight  output      inferred  ('notes',)
  summarize     pure        declared  True
  summarize     input       inferred  ('booking_ref',)
  summarize     output      inferred  ('notes',)

warnings
  annotation-conflict     find_hotels   args_schema
  contract-defaulted      find_hotels   pure
  annotation-conflict     notify        pure
  contract-inferred       notify        output
  annotation-conflict     price_flight  effect
  contract-inferred       price_flight  output
  annotation-invalid      summarize     pure, effect
  contract-inferred       summarize     input, output

the conflict on price_flight, in full
  slot      effect
  kept      decorator ('network',)
  discarded sidecar ('write',)

the resolved contract that no single surface authored
  rule      pure-effect-exclusive
  surfaces  {'pure': 'decorator', 'effect': 'sidecar'}
  values    {'pure': True, 'effect': ('external',)}
  message   the resolved contract declares pure=true together with the effects ['external']; decision D-011 makes the two mutually exclusive (ANNOTATION-API-SPEC §1/§3)
```

That transcript is the whole chain in one run. Read it node by node.

**`price_flight` — the conflict, and the non-conflict.** The sidecar sets two slots on it. On
`input` it says exactly what the decorator says, and nothing is reported: identical values are
not a conflict. On `effect` it disagrees, so the decorator's `network` is kept, the sidecar's
`write` is discarded, and `annotation-conflict` names both. The ruling behind that is not a
tie-break: a decorator lives next to the function and moves with it through refactors, while a
TOML file silently rots (§3, ratified as DEC-07). A sidecar can never override a decorator; it
fills gaps.

"Identical" there is decided structurally, not textually — two values are the same when their
canonical serializations are byte-equal — which is what makes the rule well defined for
structured values like an `args_schema` object.

**`find_hotels` — the tier most people would not guess.** The tool's own pydantic
`args_schema` is an author declaration, so it outranks the sidecar's, and the conflict record
labels the two surfaces `tool` and `sidecar`. The tool node also shows what happens on the
other side of the boundary: nothing declared its effects and its body is not a state function
extraction can read, so `pure` arrives from the conservative default with a
`contract-defaulted` warning on it. For a body nobody could read, *no write evidence* means
exactly that — no evidence — and the warning is the only thing marking the difference.

**`notify` — a negative declaration is a declaration.** `pure=False` occupies the slot, so the
sidecar's `pure = true` is a conflict rather than a gap-fill, and `False` survives into the
serialized IR and into the `graph_version`. Only `None` — the slot left alone — leaves room for
a lower tier.

**`book_flight` — the sidecar doing its job.** No decorator anywhere near it, so all three
slots it names are filled at the sidecar tier and graded `declared`.

**`summarize` — a contract no single surface authored.** The decorator says `pure`, the sidecar
adds an `external` effect. Neither surface set a slot twice, so this is not a conflict — and
yet the resolved contract violates the exclusivity rule that the decorator surface would have
refused outright. Extraction validates the *resolved* contract, and the repair rule is
mechanical: the contribution from the lower-precedence tier is discarded, the higher tier
stands, and `annotation-invalid` names the node, the slots, both surfaces, both values and the
rule. Warning, never error — the same posture as everywhere else on this surface.

So the answer to "which annotation wins" is: the highest tier that set the slot, per slot,
with a warning whenever a lower tier had something different to say. And the answer to "how
would I know" is that the envelope's warnings say so — with the one exception this page has
already met. A declaration hidden by a wrapper is a declaration gebra never received, so no
tier disagreed with anything and there is nothing for a conflict record to report.

## What inference will never do for you

Everything left unset after those three tiers falls to inference, and inference is
deliberately shallow. It reads the node callable's own AST and the state schema — nothing else,
no imports followed, no code evaluated — and applies a **closed** table of patterns that covers
`input` and `output` and nothing more:

| Slot | What licenses a key |
|---|---|
| `input` | a `TypedDict`/pydantic *projection* annotation on the state parameter, or a literal `state["k"]` / `state.k` access in the body |
| `output` | a literal dict in a `return`, a `TypedDict` return annotation, or a literal `Command(update={…})` |

Anything else is out: computed keys, `dict(**kwargs)`, a dict assembled in a helper, or a key
that only appears inside a function the node calls. Those nodes fall to the conservative
defaults with a warning — a node that writes state is recorded as having a `write` effect, and
a node with no write evidence resolves to `pure: true`.

The rule that matters most, though, is about the slots that are *not* in that table:

!!! warning "Inference never upgrades a claim"

    Inference never yields `idempotent`, `deterministic`, `variant` or `compensation`
    (ANNOTATION-API-SPEC §4). Those slots unlock retry, memoisation, termination-witness and
    compensation reasoning, and they must be opted into by an explicit declaration. No amount
    of obviously-retry-safe-looking code will produce one.

<!-- gebra:example id=never-silent-upgrade -->
```python
from pathlib import Path

import gebra

AGENT = '''\
"""Three nodes: two that look obvious, and one that says so."""

from typing import NoReturn, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class State(TypedDict):
    query: str
    hits: str


TRIPPED: list[str] = []


def unreached(node: str) -> NoReturn:
    TRIPPED.append(node)
    raise AssertionError("gebra does not run nodes")


CACHE = {"weather": "fine"}


def lookup(state):
    """A dictionary read: same input, same output, no world touched. Nothing is declared."""
    unreached("lookup")
    return {"hits": CACHE[state["query"]]}


def audit(state):
    """Reads state, writes nothing, declares nothing."""
    unreached("audit")
    record(state["hits"])


@gebra.contract(reads=["hits"], pure=True)
def declared_audit(state):
    """The same shape as `audit`, said out loud."""
    unreached("declared_audit")
    record(state["hits"])


def record(value):
    return None


workflow = StateGraph(State)
for name, body in (("lookup", lookup), ("audit", audit), ("declared_audit", declared_audit)):
    workflow.add_node(name, body)
workflow.add_edge(START, "lookup")
workflow.add_edge("lookup", "audit")
workflow.add_edge("audit", "declared_audit")
workflow.add_edge("declared_audit", END)
'''

Path("cache_agent.py").write_text(AGENT, encoding="utf-8")

import cache_agent

envelope = gebra.extract(cache_agent.workflow)
annotations = {node.id: node.annotations for node in envelope.ir.nodes}


def warning_on(node, code):
    """The one warning of that code naming that node."""
    return [item for item in envelope.warnings_for(node) if item.code.value == code][0]


print("what inference produced for `lookup`")
for slot, value in annotations["lookup"].model_dump(exclude_none=True).items():
    print(f"  {slot:11} {envelope.slot_grade('lookup', slot).value:9} {value}")

inferred = warning_on("lookup", "contract-inferred")
print("  patterns  ", inferred.detail["patterns"])
print("  never     ", inferred.detail["claims_not_upgraded"])
print("  depth     ", inferred.detail["depth"])

print()
print("two nodes of the same shape, one document, two grades")
for node in ("audit", "declared_audit"):
    contract = annotations[node].model_dump(exclude_none=True)
    grades = {slot: envelope.slot_grade(node, slot).value for slot in contract}
    print(f"  {node:15} {contract}")
    print(f"  {'':15} {grades}")

defaulted = warning_on("audit", "contract-defaulted")
print("  the default that produced one of them:", defaulted.detail["rule"])
```

<!-- gebra:output id=never-silent-upgrade -->
```text
what inference produced for `lookup`
  effect      defaulted ('write',)
  input       inferred  ('query',)
  output      inferred  ('hits',)
  patterns   {'input': {'query': 'state-access'}, 'output': {'hits': 'return-literal'}}
  never      ('idempotent', 'deterministic', 'variant', 'compensation', 'args_schema')
  depth      shallow-only (DEC-08)

two nodes of the same shape, one document, two grades
  audit           {'pure': True, 'input': ('hits',)}
                  {'pure': 'defaulted', 'input': 'inferred'}
  declared_audit  {'pure': True, 'input': ('hits',)}
                  {'pure': 'declared', 'input': 'declared'}
  the default that produced one of them: no-write-evidence
```

`lookup` is as idempotent and as deterministic as a node gets — it reads a module-level dict
and returns what it found — and extraction declares neither. It filled `input` and `output`
from the two patterns it was licensed to use, defaulted `effect`, and listed in
`claims_not_upgraded` what it did not touch: the four claim slots above, plus `args_schema`,
which is never inferred either because the closed table has no pattern for it. That list rides
on every inference record, which is the rule made visible rather than asserted.

The second half of the transcript is the same rule from the other side. `audit` and
`declared_audit` have the same body shape and resolve to the *same contract* —
`{'pure': True, 'input': ('hits',)}` on both — and the serialized IR gives you no way to tell
them apart. That is deliberate: per-slot provenance is not part of what a `graph_version` is a
digest of. The distinction lives in the envelope, and §5 states the lookup normatively:

> a slot on node *n* is declared-grade **iff** no `contract-inferred`/`contract-defaulted`
> warning in the extraction envelope names the (node id, slot) pair; otherwise it is
> heuristic-grade.

That is what `envelope.slot_grade(node, slot)` computes, and it is the same rule the previous
tutorial gave for reading warnings — here with the two heuristic origins kept apart, because
"a pattern licensed this" and "nothing was found, so the default applied" are different
statements about your code.

The rule has a corollary §4 spells out. A declared `pure` implies idempotence semantically, and
a property validator may reason from that — but only from a **declared** one. A `pure: true` of
inference or default grade never feeds the implication, because that would be inference
yielding idempotence through the back door, which is the upgrade the rule forbids. In this
release nothing exercises that corollary: no implemented property validator reads `pure` at
all. It lives in the specification and in the grade lookup, waiting for the one that will.
(Extraction's own resolved-contract validation does read `pure` — that is the exclusivity check
this page fired twice — but that is extraction checking a contract's coherence, not a validator
reasoning from it.)

Which leaves a short answer to the question this page opened with. Declare what you know;
read the warnings for everything you did not; and treat a heuristic slot as the floor it is —
the shallow analysis that produced it cannot see past the node's own body, and it never
promotes a guess into a claim.

## Where to go next

- [Extract your first IR](extract-your-first-ir.md) — the document these contracts land in,
  field by field, and the four knowability classes the grades above belong to.
- [What gebra checks](../concepts/what-gebra-checks.md) — claim classes and what a declaration
  buys you: gebra checks that declarations are coherent with the graph and with each other, and
  trusts that they are true of your code, the way a type annotation is trusted. A false
  declaration yields a false result, and that is the same failure mode as a wrong type hint.
- [The IR, node identity and `graph_version`](../concepts/ir-and-graph-version.md) — why a
  sidecar-filled slot moves your digest and a warning does not.

## Where this page is checked

Every example on this page is executed in CI, in a child interpreter where compiling a graph,
invoking a runnable, resolving a hostname or opening a connection all raise, and the
transcripts are what those runs printed —
[Executable examples](../contributing/executable-examples.md) explains the harness. The first
statement of every node body records that node in a `TRIPPED` ledger before anything else can
happen, and the harness sweeps the module each example wrote, so a body call that some `try`
block swallowed would still fail the example rather than passing silently. The third-party
tool in the precedence example is read for its schema and never invoked; its implementation is
armed like every other body here, and a control fires it to keep that ledger from being
vacuous.

Every example takes the **builder** path, because the harness does not admit an example that
compiles a graph. §6's requirement that annotations survive `.compile()` — extracting the same
workflow before and after compilation yields identical resolved contracts — is therefore not
shown by a transcript here; it is held by the extractor's builder/compiled parity tests in this
repository.
