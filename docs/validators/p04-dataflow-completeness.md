# P-04 `dataflow-completeness`

P-04 asks one question about a workflow definition: **can any routing of this graph reach a node
whose declared read has never been supplied?**

The quantifier is the whole property. For every node and every key that node declares it reads,
*every* path from `START` to it must contain a **predecessor** that declares it writes that key —
or the key must be a declared graph input, which counts as written at `START` (§4). The node's own
declaration does not count, and one covered path is not enough. The branch that skips the declared
writer is the branch nobody exercised, and it is the one P-04 is looking for.

Every P-04 finding is **FATAL** and **DEFENSIBLE-A**. Fatal is a design-time grade: it fails the
gate and suppresses snapshot recording for that run, because a definition that admits a route to a
node without the key that node declares it needs is unfit to run on that route. Defensible-**A**
rather than plain defensible because the reads and writes P-04 reasons over are the *declared*
`input`/`output` annotations, and their truthfulness is trusted the way a type annotation is
(§4.2). What P-04 settles is whether the declarations line up along every path; what it cannot
settle is whether a node that declares a write performs one. This page is about reading those
findings — what the validator checks, what each field of its witness and its failure record means,
and where the claim stops.

!!! note "Section numbers, and where they point"

    `§` references are to **PROPERTY-CATALOG-SPEC** — §4 is its P-04 section, §0 the shared
    report envelope. That is an internal contract document and is not published with this site;
    the numbers are here so a statement can be *checked* against it rather than taken on trust.
    The transcripts are not spec-derived: they are what this release printed.

!!! note "Following along"

    Six of the eight examples here run over the vendored property-fixture corpus in this
    repository, `tests/fixtures/properties/` — one YAML document per fixture, carrying an IR and
    the verdict the specification expects for it; the other two write a small IR document by
    hand. To run them yourself, clone the repository and put its root on `PYTHONPATH` — the
    corpus is located from `tests.__file__`, so an example works from any directory. Nothing here
    builds or compiles a LangGraph graph: a fixture is data, and the illustrative builder code
    some fixtures carry is an inert string that is never compiled or run.

## What P-04 checks

On P-01-clean topology, P-04 runs over the same **sentinel-augmented, label-expanded** graph P-01
and P-02 do: the document's nodes plus the implicit `START` and `END` vertices, with `entry` wiring
`START` to its members, `finish` wiring its members to `END`, and each `path_map` entry expanded
into its own edge. A `send` edge — the fan-out kind — contributes its edge like a plain one
(§4.4 Step 0; ledger §4). Over that graph, four interpretation rules decide what a path means, and
each of them is visible in a report (§4.2).

**Routing is conservative.** Every `path_map` label is one edge, and P-04 admits every labelled
successor as a route a run could take. Which label a router actually fires is P-05's question, not
this one — so "that branch only fires for pre-held bookings" is not an answer to a P-04 finding.
It is a description of the path the finding names.

**Graph inputs are written at `START`.** A state key declared `optional: true` — meaning the key
is a graph input *or carries a default* (IR-SPEC §2) — is supplied before any node runs, so it is
treated as written at `START`. A witness row reading `satisfied_by: ["START"]` is that rule, and
nothing else.

**Reads and writes are the declared annotations.** `annotations.input` and `annotations.output`,
exactly; an absent annotation is an empty set rather than an unknown one.
[Contracts and annotations](../tutorials/contracts-and-annotations.md) is where those declarations
come from, in code or in a sidecar.

**A node's own write never satisfies its own read.** The state P-04 decides a node's reads against
is the state *before* that node runs, which is the runtime fact that a first arrival sees only
what its predecessors left. On a loop that is the difference between a pass and a fail, and it has
[its own section](#a-loop-is-decided-at-its-first-arrival) below.

One scope rule follows, and it is why a P-04 report can be quieter than you expect: **the
quantification is over `START`-paths only.** A node no path from `START` reaches raises no P-04
obligation at all — its reads are P-01's finding and not this property's (§4.1; decision record
DEC-05). That has [its own section](#the-p-01-boundary) too.

P-04 has exactly one thing to say when a document does not satisfy the rule:

| Condition | What it requires | Condition ID | Anchor |
|---|---|---|---|
| **write before read, on every path** | for every reachable node and every key it declares it reads, every `START`-path to that node contains a declared writer of the key — unless the key is a graph input | `read-key-never-written-on-path` | the reading node and the key, with one offending path |

That one string is the whole P-04 vocabulary. It is in the frozen condition-ID registry and
emittable by this release (§0.4) — a validator may not emit a string the registry does not hold,
and [what gebra checks](../concepts/what-gebra-checks.md#the-diagnostic-vocabulary-is-frozen)
explains why that matters downstream.

## A pass carries a coverage map

A passing property does not return a bit. It returns a **witness**: structured, re-checkable
evidence, never prose (§0.3). P-04's is a coverage map — one row per obligation the validator
discharged — in the form pinned by decision record DEC-11. The fixture below is a booking router
whose two alternative branches both write the key their merge point reads.

<!-- gebra:example id=a-pass-and-its-coverage-map -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "dataflow-completeness"

fixture = load_fixture(CORPUS / "positive-02-conditional-both-branches-write.yaml")
report = run_property("dataflow-completeness", fixture.ir)
inputs = [key for key, field in fixture.ir.state.items() if getattr(field, "optional", None)]

print(f"fixture   {fixture.fixture_id}")
print(f"graph     {len(fixture.ir.nodes)} nodes, {len(fixture.ir.edges)} authored edges")
print(f"state     {len(fixture.ir.state)} keys, of which graph inputs: {inputs}")
print(f"result    {report.result} — the failure field is {report.failure}")
print("witness   serialized in the report profile:")
print(to_json(report.witness))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-pass-and-its-coverage-map -->
```text
fixture   dataflow-completeness/positive-02-conditional-both-branches-write.yaml
graph     4 nodes, 3 authored edges
state     4 keys, of which graph inputs: ['request']
result    pass — the failure field is None
witness   serialized in the report profile:
{
  "kind": "dataflow",
  "coverage": [
    {
      "node": "check_availability",
      "key": "request",
      "satisfied_by": [
        "START"
      ]
    },
    {
      "node": "reserve_flight",
      "key": "availability",
      "satisfied_by": [
        "check_availability"
      ]
    },
    {
      "node": "reserve_flight",
      "key": "request",
      "satisfied_by": [
        "START"
      ]
    },
    {
      "node": "reserve_package",
      "key": "availability",
      "satisfied_by": [
        "check_availability"
      ]
    },
    {
      "node": "reserve_package",
      "key": "request",
      "satisfied_by": [
        "START"
      ]
    },
    {
      "node": "send_summary",
      "key": "reservation_id",
      "satisfied_by": [
        "reserve_flight",
        "reserve_package"
      ]
    }
  ]
}
equals the fixture's own expected block: True
```

`check_availability` routes to `reserve_flight` or to `reserve_package`; both write
`reservation_id`; both converge on `send_summary`, which reads it. The three authored edges become
four once the router's two labels are expanded, and the sentinel wiring adds two more.

**`kind`** is the discriminator. The envelope's witness type is a union with one member per
property, and every consumer reads `kind` before anything else (§0.3).

**`coverage` holds one row per discharged obligation** — per *(reachable reader, read key)* pair,
not per node and not per key. `reserve_flight` reads two keys and so contributes two rows;
`request` is read by three nodes and so appears three times. Six rows for a four-node graph is
what a complete map looks like — but **an absent row is not evidence of anything**. Three
different things put a reader outside the map: it declares no reads, it is
[not reachable from `START`](#the-p-01-boundary), or the key it reads is not in the state schema
at all, which is P-03's question and never raises a P-04 obligation (§4.4).

**`node` and `key` are the obligation.** Together they are the question P-04 asked: *when control
arrives here, has this key been supplied?*

**`satisfied_by` is a set of alternatives, not a single writer.** This is the field most likely to
be misread. `send_summary`'s row names *both* branch writers, and exactly one of them runs on any
given execution — what the row claims is that every `START`-path to `send_summary` contains at
least one of them, which is precisely the every-path rule discharged. A single name in the list
means only that there happened to be one such writer, never that the writer dominates by some
stronger argument.

**`START` in `satisfied_by` means the graph-input rule.** `request` is the one key this fixture
declares `optional: true`, so it is covered before any node runs. The sentinel is a display
spelling in the report, never a node id you could route to.

**The order of `coverage` is not part of the shape — but the order inside a row is compared.**
The rows above are sorted; the fixture's own `expected:` block lists `reserve_flight`'s two keys
the other way round, and the last line is still `True`, because §4.3 declares the row order
non-normative and §0.3's comparison then treats `coverage` as a set. `satisfied_by` is *not*
marked that way: §4.3 fixes no order for it, so this release emits it in the same node-identifier
order every other list in a report uses, and an equality check against a witness compares it
position by position. Sort your own list the same way, or compare it as a set yourself.

**The last line is the corpus's own claim, re-run.** `models_equivalent` is §0.3's comparison:
model equality, with multiset comparison on the fields the specification marks order-free. The
validator's output and the fixture's `expected:` block validate into the *same* class, so the
frozen example and the result type cannot drift apart.

!!! note "`run_property` versus `verify()`"

    `run_property` is the single-property dispatch, which is what a page about one validator
    wants. A whole run goes through `verify()`, which additionally derives the gate, answers for
    all thirteen catalog properties, and refuses a document whose `ir_version` this build's
    validators are not defined over — a tool error, exit `2`, no verdict (§0.2).
    [Verify and interpret](../tutorials/verify-and-interpret.md) works through a full run.

## A failure names a reader, a key and a path

The other half of the envelope. A failing property fills `failure` with a structured record: the
violated **condition ID**, the **location** it was found at, its **severity** and its **claim
class** (§0.3). The fixture below is the catalog's own P-04 example — a booking agent that grew an
`"express"` label routing pre-held requests straight past the node that writes `booking_id`.

<!-- gebra:example id=a-failure-and-its-record -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "dataflow-completeness"

fixture = load_fixture(CORPUS / "negative-01-express-path-skips-writer.yaml")
report = run_property("dataflow-completeness", fixture.ir)
failure = report.failure

print(f"fixture   {fixture.fixture_id}")
print(f"result    {report.result} — the witness field is {report.witness}")
print(f"findings  1 primary + {len(failure.co_failures or ())} same-property co-finding")
print("record    serialized in the report profile:")
print(to_json(failure))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-failure-and-its-record -->
```text
fixture   dataflow-completeness/negative-01-express-path-skips-writer.yaml
result    fail — the witness field is None
findings  1 primary + 0 same-property co-finding
record    serialized in the report profile:
{
  "property_condition": "read-key-never-written-on-path",
  "location": {
    "kind": "state-key",
    "key": "booking_id",
    "node": "send_confirmation",
    "path": [
      "START",
      "check_availability",
      "send_confirmation"
    ]
  },
  "severity": "fatal",
  "claim_class": "defensible-a",
  "writers_on_other_paths": [
    "book_flight"
  ]
}
equals the fixture's own expected block: True
```

Field by field, because every one of them is load-bearing.

**`property_condition`** is the machine-readable half of the finding: the stable string to key on
rather than parsing prose. It is a registry entry, frozen verbatim (§0.4).

**`location` is typed, and P-04 extends the type.** The envelope has six structural anchors — node,
edge, cycle, SCC, state-key and path — and P-04 uses the **state-key** anchor: `key` names the
channel, and P-04 adds two members of its own. `node` is optional on the anchor and required here,
because a dataflow finding always names the reader that would have been surprised. `path` is the
new evidence: a shortest `START`-to-reader route on which the key is never written, with ties
broken deterministically so a re-run prints the same one. Here it is the express route, three
vertices long, and it is what you go and look at.

**`severity` and `claim_class` are read off the registry, not restated by the validator.** For
P-04 they are `fatal` and `defensible-a` on every finding, which is why a P-04 failure both fails
the gate and suppresses snapshot recording for that run (§0.2).

**`writers_on_other_paths` is the answer to "but I do write that key".** `book_flight` declares
`booking_id` as an output and is upstream of the reader — on the standard route. The diagnostic
names the writers that cover *some* path so a reader is not left doubting the report, and it is
the clearest signal that a declared writer for the key exists somewhere and the gap is on this
route. It is an optional
member kept by DEC-11, emitted only when non-empty, and it is never part of the verdict: a finding
carrying it and a finding without it are equally FATAL.

**One path, not all of them.** The express route is *a* shortest route on which the key is
unwritten; there may be others, and the record does not enumerate them. It is a place to look, not
a census.

**The optional members are absent, not empty.** `co_failures`, `downstream_writers`,
`remediation`, `advisories`, `subsumed_by` and `notes` are all unset on this record, and the report
profile drops unset members rather than writing nulls — so an omitted key and a validator that set
nothing produce the same document. `remediation` is display-only prose and is never parsed;
`advisories` carries cross-property WARNING-class side findings; `notes` carries structured
same-property notes that P-04 never emits, since its own vocabulary is one condition and no note
kinds; and `subsumed_by` is [the P-01 interaction](#the-p-01-boundary) below — a field this
release's validators never set on a record.

## Every obligation in the corpus

The corpus's P-04 directory is where the property is pinned: four positives and four negatives,
each negative a different way for a path to arrive without a key. (The specification's own §4.6
tables three of each; the cycle-entry pair below was authorized separately, by decision record
DEC-16, and the count here is the directory's.) Running the validator over all eight at once is
the shortest tour of what P-04 can say.

<!-- gebra:example id=every-obligation-in-the-corpus -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "dataflow-completeness"

fixtures = [load_fixture(path) for path in sorted(CORPUS.glob("*.yaml"))]
agreed = 0
for fixture in fixtures:
    report = run_property("dataflow-completeness", fixture.ir)
    agreed += models_equivalent(report, fixture.expected_report())
    if report.result == "pass":
        coverage = report.witness.coverage
        at_start = sum("START" in entry.satisfied_by for entry in coverage)
        summary = f"{len(coverage)} obligations, {at_start} covered at START"
    else:
        summary = f"{report.failure.location.node} reads {report.failure.location.key}"
    print(f"{fixture.path.stem:45}{report.result:6}{summary}")
    if report.result == "fail":
        failure = report.failure
        print(f"    unwritten on {' -> '.join(failure.location.path)}")
        found = [
            f"{name} {', '.join(getattr(failure, name))}"
            for name in ("writers_on_other_paths", "downstream_writers")
            if getattr(failure, name)
        ]
        print(f"    {'; '.join(found)}")

print(f"\n{agreed} of {len(fixtures)} reports equal the fixture's own expected block")
```

<!-- gebra:output id=every-obligation-in-the-corpus -->
```text
negative-01-express-path-skips-writer        fail  send_confirmation reads booking_id
    unwritten on START -> check_availability -> send_confirmation
    writers_on_other_paths book_flight
negative-02-writer-downstream-of-reader      fail  notify_traveler reads itinerary_url
    unwritten on START -> compile_itinerary -> notify_traveler
    downstream_writers publish_itinerary
negative-03-fan-in-missing-branch-writer     fail  price_quote reads loyalty_tier
    unwritten on START -> identify_traveler -> create_guest_profile -> price_quote
    writers_on_other_paths fetch_loyalty_profile
negative-04-cycle-entry-at-reader            fail  review_quote reads quote
    unwritten on START -> prepare_search -> review_quote
    writers_on_other_paths fetch_fare_quote; downstream_writers fetch_fare_quote
positive-01-linear-itinerary-pipeline        pass  5 obligations, 2 covered at START
positive-02-conditional-both-branches-write  pass  6 obligations, 3 covered at START
positive-03-parallel-fanout-reduced-results  pass  5 obligations, 2 covered at START
positive-04-cycle-entry-at-writer            pass  5 obligations, 1 covered at START

8 of 8 reports equal the fixture's own expected block
```

Four failures, one condition ID, four different repairs — which is why the diagnostics are worth
reading before you decide what to change.

**A branch that skips ahead** (`negative-01`). The express label routes past the only writer. The
repair is routing: either the express branch also passes through a writer, or the key becomes a
graph input with a caller-supplied value.

**A branch that writes the wrong keys** (`negative-03`). Both branches do real work — one fetches a
loyalty profile, the other creates a guest profile — and only one writes the key the merge point
reads. Nothing skips ahead here; the repair is to make the guest branch supply a default, or to
declare the key optional.

**A writer on the wrong side of the reader** (`negative-02`). `publish_itinerary` writes
`itinerary_url`, and it is wired *after* the node that reads it. The write-before-read closure is
ordered, so a writer downstream contributes nothing to a reader upstream — and this is exactly
what `downstream_writers` is for. When you see that field and not the other one, the graph almost
certainly has two edges in the wrong order.

**A loop entered at its reader** (`negative-04`) fills *both* diagnostics with the same node, which
is a shape only a cycle produces: `fetch_fare_quote` is upstream of `review_quote` by the back
edge and downstream of it by the forward edge. It gets [the next section](#a-loop-is-decided-at-its-first-arrival)
to itself.

Two things about the passes are worth keeping. `positive-03` covers a fan-in read with two
*concurrent* writers whose channel declares a reducer, and `positive-02` covers one with two
*alternative* writers; P-04 treats them identically, because the every-path rule does not count
writers — it asks only whether some path avoids all of them. And whether concurrent writes to one
channel are safe is P-09's question, not this one.

The last line matters as much as the rest: every one of the eight reports equals the fixture's own
`expected:` block. These are frozen examples the validator is held to in CI, not illustrations
written beside it.

## A loop is decided at its first arrival

The rule most likely to surprise on a cyclic graph: a node's own write never satisfies its own
read, and neither does a write that happens later in the loop. What P-04 decides a read against is
the state *before* the node runs — which is the runtime fact that iteration one sees only what
preceded it. The corpus pins that with two fixtures that are the same loop with the entry moved
one node.

<!-- gebra:example id=a-loop-is-decided-at-its-first-arrival -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "dataflow-completeness"


def wiring(ir):
    for edge in ir.edges:
        labelled = getattr(edge, "path_map", None)
        if labelled is None:
            yield f"{edge.from_} -> {edge.to}"
        else:
            for label, target in labelled.items():
                yield f"{edge.from_} -{label}-> {target}"


for name in ("positive-04-cycle-entry-at-writer", "negative-04-cycle-entry-at-reader"):
    fixture = load_fixture(CORPUS / f"{name}.yaml")
    report = run_property("dataflow-completeness", fixture.ir)
    print(f"{name}   entry {fixture.ir.entry}")
    for step in wiring(fixture.ir):
        print(f"    {step}")
    if report.result == "pass":
        covered = next(
            entry
            for entry in report.witness.coverage
            if (entry.node, entry.key) == ("review_quote", "quote")
        )
        print(f"    pass  review_quote reads quote, satisfied_by {', '.join(covered.satisfied_by)}")
    else:
        location = report.failure.location
        print(f"    fail  {location.node} reads {location.key}, unwritten on ", end="")
        print(" -> ".join(location.path))
```

<!-- gebra:output id=a-loop-is-decided-at-its-first-arrival -->
```text
positive-04-cycle-entry-at-writer   entry prepare_search
    prepare_search -> fetch_fare_quote
    fetch_fare_quote -> review_quote
    review_quote -refresh-> fetch_fare_quote
    review_quote -book-> book_trip
    pass  review_quote reads quote, satisfied_by fetch_fare_quote
negative-04-cycle-entry-at-reader   entry prepare_search
    prepare_search -> review_quote
    review_quote -> fetch_fare_quote
    fetch_fare_quote -again-> review_quote
    fetch_fare_quote -book-> book_trip
    fail  review_quote reads quote, unwritten on START -> prepare_search -> review_quote
```

The same four nodes, the same fare-refresh loop, the same two members in the cycle — and opposite
verdicts. In the first the loop is entered at its writer, so every route to `review_quote` passes
through `fetch_fare_quote` and the quote is declared written before the read. In the second a
refactor moved the entry one node later, onto the reader: "assess first, fetch only when it is
stale". From the second lap onward a writer has run, and it is the *first* lap that arrives
without one — which is the offending path the record names, three vertices long and traversing no
edge of the cycle at all: it reaches the loop only at its final vertex, the reader.

Two consequences follow for anyone reading a P-04 report on a cyclic graph.

**A writer inside the loop is not automatically a cover.** Being in the same strongly connected
component as the reader says nothing on its own; what matters is whether some `START`-path reaches
the reader without passing through a writer first. Both fixtures above have a writer in the
component, and only one of them passes. Collapsing the loop into a single vertex with the writes of
all its members unioned would produce the same answer for both — and the wrong one for
`negative-04`, which is why the validator does no such collapse (§4.1).

**The repair for an entry-at-reader loop is usually the entry.** Point `START` at the writer, or
seed the key as a graph input; changing the loop body does not move the first arrival.

## Two findings, one record

One property reports once. When several obligations fail, the deterministically-first finding
fills `failure` and every further same-property finding rides `co_failures`, so nothing is dropped
(§0.3). The corpus's negatives each violate exactly one obligation, so here is a small document
written by hand that violates two — a booking flow whose `book` step was wired last.

<!-- gebra:example id=two-findings-one-record -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import run_property, to_json

document = {
    "ir_version": "1.0",
    "entry": ["intake"],
    "finish": ["book"],
    "state": {
        "request": {"type": "str", "optional": True},
        "plan": "str",
        "booking_id": "str",
        "confirmation_ref": "str",
        "receipt": "str",
    },
    "nodes": [
        {"id": "intake", "annotations": {"input": ["request"], "output": ["plan"]}},
        {"id": "charge", "annotations": {"input": ["booking_id", "plan"], "output": ["receipt"]}},
        {"id": "notify", "annotations": {"input": ["confirmation_ref", "receipt"], "output": []}},
        {
            "id": "book",
            "annotations": {"input": ["plan"], "output": ["booking_id", "confirmation_ref"]},
        },
    ],
    "edges": [
        {"from": "intake", "to": "charge"},
        {"from": "charge", "to": "notify"},
        {"from": "notify", "to": "book"},
    ],
}

report = run_property("dataflow-completeness", load_json(WorkflowIR, json.dumps(document)))
print(f"result    {report.result}")
print(f"findings  1 primary + {len(report.failure.co_failures)} same-property co-finding")
print(to_json(report.failure))
```

<!-- gebra:output id=two-findings-one-record -->
```text
result    fail
findings  1 primary + 1 same-property co-finding
{
  "property_condition": "read-key-never-written-on-path",
  "location": {
    "kind": "state-key",
    "key": "booking_id",
    "node": "charge",
    "path": [
      "START",
      "intake",
      "charge"
    ]
  },
  "severity": "fatal",
  "claim_class": "defensible-a",
  "co_failures": [
    {
      "property": "dataflow-completeness",
      "property_condition": "read-key-never-written-on-path",
      "location": {
        "kind": "state-key",
        "key": "confirmation_ref",
        "node": "notify",
        "path": [
          "START",
          "intake",
          "charge",
          "notify"
        ]
      },
      "severity": "fatal",
      "claim_class": "defensible-a"
    }
  ],
  "downstream_writers": [
    "book"
  ]
}
```

Both findings trace to one mistake — `book` belongs before `charge` — and both are reported.

**Which finding is primary is determined, not chosen.** Obligations are enumerated node by node in
the IR's own UTF-16 code-unit order over node identifiers, then key by key within a node, and the
first violated one becomes the primary (§4.4). Here that puts the nodes in the order `book`,
`charge`, `intake`, `notify` — nothing like the order they were authored in — so `charge`'s
missing `booking_id` leads and `notify`'s missing `confirmation_ref` follows.

**A co-failure carries its own property, condition, location, severity and claim class** — enough
to act on, and each is graded on its own account rather than inheriting the primary's.

**A co-failure does not carry the two diagnostics.** `downstream_writers` names `book` on the
primary; `notify`'s finding would have named `book` too, and the co-failure model has no field for
it and admits no extras (§0.3). If you are triaging from the co-failures alone, the diagnostics are on
the primary or nowhere.

## The P-01 boundary

P-04 and P-01 both walk the topology, and where they meet there is one rule and one caveat.

The rule is scope: **a node no path from `START` reaches raises no P-04 obligation.** Its reads are
owned by P-01's unreachable-node finding — one root cause, one report, no double-blame (§4.1;
DEC-05). The document below is that rule from both sides: a compliance node that reads a key nobody
writes, first with nothing routing to it and then with one edge added.

<!-- gebra:example id=an-unreachable-reader-is-p-01s -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import run_property, to_data

document = {
    "ir_version": "1.0",
    "entry": ["intake"],
    "finish": ["close"],
    "state": {
        "ticket": {"type": "str", "optional": True},
        "resolution": "str",
        "audit_ref": "str",
    },
    "nodes": [
        {"id": "intake", "annotations": {"input": ["ticket"], "output": ["resolution"]}},
        {"id": "close", "annotations": {"input": ["resolution"], "output": []}},
        {"id": "audit_log", "annotations": {"input": ["audit_ref"], "output": []}},
    ],
    "edges": [
        {"from": "intake", "to": "close"},
        {"from": "audit_log", "to": "close"},
    ],
}

for label, edges in (
    ("nothing routes to audit_log", document["edges"]),
    ("intake -> audit_log added", [*document["edges"], {"from": "intake", "to": "audit_log"}]),
):
    ir = load_json(WorkflowIR, json.dumps({**document, "edges": edges}))
    print(label)
    for slug in ("graph-well-formed", "dataflow-completeness"):
        report = run_property(slug, ir)
        if report.result == "pass" and slug == "dataflow-completeness":
            obligations = [f"{e.node}/{e.key}" for e in report.witness.coverage]
            print(f"    {slug:22}pass  obligations {', '.join(obligations)}")
        elif report.result == "pass":
            print(f"    {slug:22}pass")
        else:
            anchor = to_data(report.failure.location)
            site = anchor.get("node", "?")
            key = f"/{anchor['key']}" if "key" in anchor else ""
            print(f"    {slug:22}fail  {report.failure.property_condition} at {site}{key}")
```

<!-- gebra:output id=an-unreachable-reader-is-p-01s -->
```text
nothing routes to audit_log
    graph-well-formed     fail  node-unreachable-from-start at audit_log
    dataflow-completeness pass  obligations close/resolution, intake/ticket
intake -> audit_log added
    graph-well-formed     pass
    dataflow-completeness fail  read-key-never-written-on-path at audit_log/audit_ref
```

`audit_log` reads `audit_ref`, which no node in either document writes. In the first it is
unreachable, and P-04's coverage map does not mention it at all — the obligation is never raised,
so there is nothing to report and nothing to suppress. Wire it up and the same read becomes a
FATAL finding. Two readings follow. A P-04 pass covers the reachable graph and says nothing about
the rest of the document; and if a P-04 report is quieter than a graph deserves, look for a P-01
unreachable-node finding first, because the read behind it may well be uncovered and is simply not
this property's to file. (Note which verdict is contract-bearing here: the first document fails
P-01, so its P-04 pass is a best-effort diagnostic by the rule below. The one to trust is the
second, where the graph is clean and the finding is real.)

`subsumed_by` is the envelope's field for stating that relationship explicitly on a record —
`subsumed_by: "P-01"`, meaning "this finding is owned upstream" (§0.3; DEC-05) — and the corpus
fixture `mixed/04` is where the specification pins the shape. **No validator in this release sets
it.** The field is part of the envelope and is read by the renderers, but the qualification a run
actually hands you is the `best_effort` list in the next example, not a flag on the record. Do not
write a consumer that waits for one.

The caveat is the other direction. **P-04's results are defined over P-01-clean topology** (§0.3),
and a run that fails P-01 says so rather than leaving you to remember it:

<!-- gebra:example id=best-effort-on-a-broken-graph -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import to_data, verify

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "mixed"

fixture = load_fixture(CORPUS / "04-dangling-path-map-target-orphans-downstream-reader.yaml")
report = verify(fixture.ir)

print(f"fixture      {fixture.fixture_id}")
print(f"gate         {report.gate.outcome}, exit {report.gate.exit_code}")
print(f"best_effort  {list(report.best_effort)}")
for slug in ("graph-well-formed", "dataflow-completeness"):
    failure = report.outcome_for(slug).failure
    anchor = to_data(failure.location)
    site = anchor.get("node") or f"{anchor['source']}/{anchor['label']}"
    print(f"{slug:22} fail  {failure.property_condition} at {site}")

path = report.outcome_for("dataflow-completeness").failure.location.path
authored = set()
for edge in fixture.ir.edges:
    labelled = getattr(edge, "path_map", None)
    if labelled is None:
        authored.add((edge.from_, edge.to))
    else:
        authored.update((edge.from_, target) for target in labelled.values())
gaps = [step for step in zip(path, path[1:]) if step not in authored and step[0] != "START"]

print(f"offending path         {' -> '.join(path)}")
print(f"steps of it the document does not author: {gaps}")
```

<!-- gebra:output id=best-effort-on-a-broken-graph -->
```text
fixture      mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml
gate         fail, exit 1
best_effort  ['termination-witness', 'dataflow-completeness', 'effect-safety']
graph-well-formed      fail  path-map-target-undefined at triage/legal
dataflow-completeness  fail  read-key-never-written-on-path at compliance_log
offending path         START -> intake -> triage -> compliance_log
steps of it the document does not author: [('triage', 'compliance_log')]
```

One typo — a `path_map` label pointing at a node that was renamed away — and the run reports P-01's
dangling reference, lists three properties as best-effort diagnostics, and hands back a P-04 record
whose path contains a step the document does not author. That is not a defect in the record: on
ill-formed topology each validator degrades in its own documented way, and P-04's is to keep the
missing vertex as a placeholder with no declared reads or writes so that the reads *behind* it are
still analysed. The placeholder is then removed from the emitted path, because no location field
may name a vertex the document does not carry (§0.3; decision record DEC-26).

It also means P-04 and the corpus can disagree here, and the disagreement is recorded rather than
hidden: `mixed/04` files the same read as a `subsumed_by: P-01` co-failure — no independent gap —
while the validator, on its own carried graph, finds `compliance_log` *reachable* and raises the
obligation for real. DEC-05's subsumption is keyed on unreachability, and under P-04's own
degradation convention this reader is reachable. §0.3 is explicit that these conventions are local
and that cross-validator agreement on ill-formed input is not promised. What it all means for a
reader is simple: **a P-04 finding on a run that failed P-01 is a lead, not a verdict.** Fix the
wiring, re-run, and read the report you get then.

## What P-04 reads

`entry`, `finish`, the **keys** of `state` and each key's `optional` flag, `nodes[].id`, each
node's `annotations.input` and `annotations.output`, and each edge's `from`/`to`/`kind`/`path_map`
(§4.3). That is the whole list, and everything else in a document is read by some other property or
by none. Worth checking rather than believing:

<!-- gebra:example id=what-p04-reads -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import WorkflowIR, dump_json, load_json
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "dataflow-completeness"

fixture = load_fixture(CORPUS / "negative-04-cycle-entry-at-reader.yaml")
document = json.loads(dump_json(fixture.ir))

reducers = []
for key, field in document["state"].items():
    if isinstance(field, str):
        document["state"][key] = "object"
    else:
        field["type"] = "object"
        if field.pop("reducer", None) is not None:
            reducers.append(key)
changed = [
    f'every declared type rewritten to "object" ({len(document["state"])} keys)',
    f"every declared reducer removed (on {', '.join(reducers)})",
]
for node in document["nodes"]:
    for member in ("effect", "idempotent", "pure", "deterministic", "variant", "retry_policy"):
        if node["annotations"].pop(member, None) is not None:
            changed.append(f"{node['id']}.annotations.{member}")
for edge in document["edges"]:
    if edge.pop("condition", None) is not None:
        changed.append(f"{edge['from']}.condition (the router expression)")

rewritten = load_json(WorkflowIR, json.dumps(document))
before = run_property("dataflow-completeness", fixture.ir)
after = run_property("dataflow-completeness", rewritten)

print(f"changed   {len(changed)} things P-04 does not read:")
for member in changed:
    print(f"            {member}")
print("kept      entry, finish, the state keys and their optional flags, nodes[].id,")
print("          annotations.input/output, and every edge's from/to/kind/path_map")
print(f"verdicts  {before.result} before, {after.result} after")
print(f"reports equal: {models_equivalent(before, after)}")
```

<!-- gebra:output id=what-p04-reads -->
```text
changed   9 things P-04 does not read:
            every declared type rewritten to "object" (6 keys)
            every declared reducer removed (on refresh_round)
            prepare_search.annotations.pure
            review_quote.annotations.pure
            fetch_fare_quote.annotations.effect
            fetch_fare_quote.annotations.idempotent
            book_trip.annotations.effect
            book_trip.annotations.idempotent
            fetch_fare_quote.condition (the router expression)
kept      entry, finish, the state keys and their optional flags, nodes[].id,
          annotations.input/output, and every edge's from/to/kind/path_map
verdicts  fail before, fail after
reports equal: True
```

Every declared type replaced with a placeholder, every reducer dropped, every effect and
idempotency declaration removed, the router's condition string deleted — and the report is the same
value, offending path and diagnostics included. Three things follow. **A state key's declared type
is not P-04's business**: this property asks whether a key was supplied, never what shape the value
has. (It is somebody's: P-03 checks a read against the schema, and P-02 requires a bounded
counter's key to be declared `int`. So the rewrite above is safe for *this* property and would
move a P-02 verdict on the same document — `refresh_round` is that fixture's counter.) **The
router's guard string is not read here** either, which is what makes the conservative-routing rule
real rather than aspirational: P-04 could not favour one label over another even if it wanted to.
And what is invariant is the *type* of every key, not the number of them — the state schema's size
is in P-04's cost, in both of the bounds the specification gives it (§4.5).

The reverse also holds, and is the reason the annotations matter so much:
`annotations.input`/`output` are the only place P-04 looks for reads and writes, and an absent
declaration reads as an empty set rather than as an unknown. A node missing its `input` raises no
obligation of its own, so a real gap goes unmentioned; a node missing its `output` covers nothing
for the nodes after it, so a covered read is reported as a gap. Both directions are why extraction
warns on every slot it had to infer or default, and why
[what inference will never do for you](../tutorials/contracts-and-annotations.md#what-inference-will-never-do-for-you)
is worth reading beside a P-04 report of either colour.

## What a pass does not claim

A P-04 pass says that on **every** `START`-path to every reachable reader, some earlier node
**declares** that it writes the key — a statement about the declarations in a document, and about
nothing else. Five things stay on the far side of that line, and the second of them is about a
failure rather than a pass, because the same trust runs in both directions.

* **A declared write is not a write.** This is the whole of the `-A` in DEFENSIBLE-A. A node
  annotated `output: ["booking_id"]` whose body returns an empty dict passes P-04 and fails at
  run time. gebra never executes the node, so the annotation is trusted the way a type annotation
  is — and like a type annotation, it is worth being accurate about.
* **And a finding is a finding about declarations too.** The mirror matters more, because it is
  FATAL and it blocks a gate: a node that really does write the key, but whose `output` slot was
  inferred, defaulted or never declared, produces exactly the finding on this page. Before you
  rewire a graph on P-04's say-so, check the extraction warnings for a `contract-inferred` or
  `contract-defaulted` entry naming that node — the repair may be a declaration rather than an
  edge.
* **A covered read is not a good value.** P-04 asks whether the key was supplied before the read,
  never whether the value is correct, current, or of the declared type. A stale value written three
  nodes ago covers the obligation exactly as well as a fresh one.
* **The path is possible, not predicted.** Every labelled successor counts as a route, so a
  finding on the express branch does not claim that the express branch is ever taken. Whether a
  router's labels are exhaustive and reachable is P-05's question, and this release does not
  implement P-05 — a run answers for it with a structured not-implemented marker, never a silent
  pass.
* **A key outside the state schema is P-03's finding.** A node declaring a read of a key that
  `state` does not carry raises no P-04 obligation; the mismatch is a schema-membership question,
  and P-03 is likewise not implemented in this release.

So the reading of a P-04 pass is "every declared read is covered by a declared write on every route
that can reach it", and the reading of a failure is "here is a route on which one is not" — a
statement about the definition in front of you, not a prediction about a run. That is the value of
the check: the branch nobody exercised is exactly the branch a per-path rule reaches, and it
reaches it before anything runs.

Two smaller limits worth keeping straight. **A pass is about reachable readers** — the
[boundary section](#the-p-01-boundary) above is the whole of that story. And a document using the
`ir_version` 1.1 `dynamic` edge kind — a router whose destinations are computed rather than
declared — reaches
[no verdict at all](../tutorials/extract-your-first-ir.md#one-consequence-to-know-before-you-build-on-this),
exit `2`, rather than a P-04 answer.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking a
runnable, resolving a hostname or opening a connection all raise. The output blocks are what those
runs printed, and three of them additionally re-check the whole report against the corpus's own
frozen `expected:` block — [executable examples](../contributing/executable-examples.md) explains
the mechanism.

The frozen contract behind this page is PROPERTY-CATALOG-SPEC §4 with the shared envelope of §0;
the shapes it pins were ratified in decision records DEC-11 (the coverage-map witness and the two
kept diagnostics) and DEC-05 (the `START`-path scope), with DEC-26 fixing what a location may name
on ill-formed topology. `gebra.verify.properties.dataflow_completeness` and its tests are where
that contract is implemented and pinned in this repository. The other written explainers are
[P-01 `graph-well-formed`](p01-graph-well-formed.md),
[P-02 `termination-witness`](p02-termination-witness.md) and
[P-06 `effect-safety`](p06-effect-safety.md).
