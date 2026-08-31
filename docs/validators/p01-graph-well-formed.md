# P-01 `graph-well-formed`

P-01 answers one question about a workflow definition: **is the graph wired up?** Every node
reachable from `START`, every node with nowhere left to go wired to `END`, no node standing
outside every edge, and every reference naming a node that exists.

It is the property with the narrowest claim and the sharpest consequence. Every P-01 finding is
**FATAL** and **DEFENSIBLE**: fatal because a dangling target or an unwired sink strands
execution and an unreachable node is definition mass no run can exercise, so the *definition* is
unfit to run; defensible because reading the document settles it, with no annotation trusted
and nothing executed (§1; §0.1). This page is about reading those findings — what the validator
checks, what each field of its witness and its failure record means, and where the claim stops.

!!! note "Section numbers, and where they point"

    `§` references are to **PROPERTY-CATALOG-SPEC** — §1 is its P-01 section, §0 the shared
    report envelope. That is an internal contract document and is not published with this
    site; the numbers are here so a statement can be *checked* against it rather than taken on
    trust. The transcripts are not spec-derived: they are what this release printed.

!!! note "Following along"

    Five of the six examples here run over the vendored property-fixture corpus in this
    repository, `tests/fixtures/properties/` — one YAML document per fixture, carrying an IR
    and the verdict the specification expects for it; the sixth writes a one-node IR document by
    hand. To run them yourself, clone the repository and put its root on `PYTHONPATH` — the
    corpus is located from `tests.__file__`, so an example works from any directory. Nothing
    here builds or compiles a LangGraph graph: a fixture is data, and the illustrative builder
    code some fixtures carry is an inert string that is never compiled or run.

## What P-01 checks

P-01 runs over the **sentinel-augmented graph**: the document's nodes plus the two implicit
vertices `START` and `END`. `entry` wires `START` to its members, `finish` wires its members to
`END`, and a conditional edge is expanded label by label — each `path_map` entry is one logical
edge, and a label valued `"END"` targets the exit (§1.3; IR-SPEC §4.2). Then four conditions,
which are the catalog's, numbered as it numbers them:

| Condition | What it requires | Condition ID | Anchor |
|---|---|---|---|
| **(i)** | every node is reachable from `START` | `node-unreachable-from-start` | the node |
| **(ii)** | every node has somewhere to go — an outgoing edge, or membership in `finish` | `dead-end-node-not-wired-to-end` | the node |
| **(iii)** | every node participates in at least one edge | `orphan-node` | the node |
| **(iv)** | every reference names a node that exists | `path-map-target-undefined` for a `path_map` value; `edge-target-undefined` for an `entry` id, a `finish` id, an edge's `from`, or a `normal`/`send` edge's `to` | the edge |

Those five strings are the whole P-01 vocabulary. All of them are in the frozen condition-ID
registry and emittable by this release (§0.4) — a validator may not emit a string the registry
does not hold, and [what gebra checks](../concepts/what-gebra-checks.md) explains why that
matters downstream.

## A pass carries a five-key witness

A passing property does not return a bit. It returns a **witness**: structured, re-checkable
evidence, never prose (§0.3). P-01's is the five-key form pinned by decision record DEC-11 —
the fixture below is one of the corpus positives that pin it.

<!-- gebra:example id=a-pass-and-its-witness -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "graph-well-formed"

fixture = load_fixture(CORPUS / "positive-02-support-triage-branching.yaml")
report = run_property("graph-well-formed", fixture.ir)

print(f"fixture   {fixture.fixture_id}")
print(f"graph     {len(fixture.ir.nodes)} nodes, {len(fixture.ir.edges)} authored edges")
print(f"wiring    entry {fixture.ir.entry}, finish {fixture.ir.finish}")
print(f"result    {report.result} — the failure field is {report.failure}")
print("witness   serialized in the report profile:")
print(to_json(report.witness))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-pass-and-its-witness -->
```text
fixture   graph-well-formed/positive-02-support-triage-branching.yaml
graph     5 nodes, 4 authored edges
wiring    entry classify_ticket, finish send_reply
result    pass — the failure field is None
witness   serialized in the report profile:
{
  "kind": "well-formedness",
  "reachable_from_start": [
    "classify_ticket",
    "handle_billing",
    "handle_general",
    "handle_technical",
    "send_reply"
  ],
  "terminal_nodes": [
    "send_reply"
  ],
  "orphan_nodes": [],
  "unresolved_targets": []
}
equals the fixture's own expected block: True
```

That is a support-triage agent: one router fanning out to three handlers, all three converging
on a reply. The four authored edges become six once the router's three labels are expanded, and
the sentinel wiring adds two more; the witness is what the check over that graph leaves behind.

**`kind`** is the discriminator. The envelope's witness type is a union with one member per
property, and every consumer reads `kind` before anything else (§0.3).

**`reachable_from_start`** is every node in the document. On a pass it always is — that is what
condition (i) means — sorted in the IR's own UTF-16 code-unit order, which is why
`handle_general` precedes `handle_technical` here rather than the order the fixture authored.
This is the re-checkable half of the witness: walk the document's edges yourself and compare.

**`terminal_nodes`** names the predecessors of `END` in the augmented graph: the nodes listed in
`finish`, plus any router with a `path_map` label valued `"END"` (§1.4). No fixture on this page
routes a label to `END`, so here the list is exactly the `finish` node, `send_reply`.

**`orphan_nodes` and `unresolved_targets` are empty by construction.** A non-empty one would
have filled `failure` instead, so they carry no per-run information. What they carry is *shape*:
conditions (iii) and (iv) are part of this one verdict rather than a separate report. DEC-11
pinned this five-key form over both a compact four-key variant and a bare pass bit, on the
ground that the compact forms lose the orphan and unresolved-reference tuples that make a pass
witness re-checkable at all.

**The last line is the corpus's own claim, re-run.** `models_equivalent` is §0.3's comparison —
model equality, with multiset comparison on the fields the specification marks order-free. The
validator's output and the fixture's `expected:` block validate into the *same* class, so the
frozen example and the result type cannot drift apart.

!!! note "`run_property` versus `verify()`"

    `run_property` is the single-property dispatch, which is what a page about one validator
    wants. A whole run goes through `verify()`, which additionally derives the gate, answers for
    all thirteen catalog properties, and refuses a document whose `ir_version` this build's
    validators are not defined over — a tool error, exit `2`, no verdict (§0.2).
    [Verify and interpret](../tutorials/verify-and-interpret.md) works through a full run.

## A failure names a condition and a locus

The other half of the envelope. A failing property fills `failure` with a structured record: the
violated **condition ID**, the **location** it was found at, its **severity** and its **claim
class** (§0.3). The fixture below is the catalog's own P-01 example — a router mapping the
`confirm` label to `send_confirmatoin`, a typo naming no node, which LangGraph may not surface
until that branch is taken in production.

<!-- gebra:example id=a-failure-and-its-record -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "graph-well-formed"

fixture = load_fixture(CORPUS / "negative-03-path-map-typo-dangling-target.yaml")
report = run_property("graph-well-formed", fixture.ir)
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
fixture   graph-well-formed/negative-03-path-map-typo-dangling-target.yaml
result    fail — the witness field is None
findings  1 primary + 1 same-property co-finding
record    serialized in the report profile:
{
  "property_condition": "path-map-target-undefined",
  "location": {
    "kind": "edge",
    "source": "review_booking",
    "label": "confirm",
    "undefined_target": "send_confirmatoin"
  },
  "severity": "fatal",
  "claim_class": "defensible",
  "co_failures": [
    {
      "property": "graph-well-formed",
      "property_condition": "node-unreachable-from-start",
      "location": {
        "kind": "node",
        "node": "send_confirmation"
      },
      "severity": "fatal",
      "claim_class": "defensible"
    }
  ]
}
equals the fixture's own expected block: True
```

Field by field, because every one of them is load-bearing.

**`property_condition`** is the machine-readable half of the finding: the stable string to key
on rather than parsing prose. It is a registry entry, frozen verbatim (§0.4).

**`location` is typed, and P-01 extends the type.** The envelope has six structural anchors —
node, edge, cycle, SCC, state-key, path — and P-01 uses two of them. Here it is the **edge**
anchor: `source` is the router you would edit and `label` says which `path_map` entry, both
§0.3's own fields, plus P-01's one addition, `undefined_target` — the string that resolved to
nothing. The anchor's `target` field is deliberately *absent*: there is no node to point at, and
§0.3 has a dangling reference omit it rather than invent one. A location never names a vertex the
document does not carry.

**`severity` and `claim_class` are read off the registry, not restated by the validator.** For
P-01 they are `fatal` and `defensible` on every finding, which is why a P-01 failure both fails
the gate and suppresses snapshot recording for that run (§0.2).

**The primary finding is the root cause.** Findings are ordered (iv) → (iii) → (i) → (ii), so a
reference that resolves to nothing is reported ahead of the consequences it causes; within (iv),
findings whose anchor itself resolves — an existing node, or `START` — come first, so the primary
stays at a site you can edit (§1.4; DEC-12). Here that puts the typo first and the node it
stranded second.

**`co_failures` carries the rest, and nothing is dropped.** `send_confirmation` exists, and being
listed in `finish` it is even wired to `END` — but the label meant to reach it names something
else, so nothing routes to it and condition (i) fires too. One property reports once: the
deterministically-first finding fills `failure` and every further same-property finding rides
`co_failures`, each with its own severity and claim class (§0.3).
Both entries trace to the one typo: correct the label and the target resolves, which is also
what puts the node it stranded back on a path from `START`.

**The optional members are absent, not empty.** `remediation`, `advisories`, `subsumed_by` and
`notes` are all unset on this record, and the report profile drops unset members rather than
writing nulls — so an omitted key and a validator that set nothing produce the same document.

## The four conditions, one fixture each

The corpus's P-01 directory is where the conditions are pinned: three positives and four
negatives, each negative pinning one condition as its primary finding. Running the validator over
all seven at once is the shortest tour of what P-01 can say.

<!-- gebra:example id=four-conditions -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_data

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "graph-well-formed"

CONDITION = {
    "node-unreachable-from-start": "i",
    "dead-end-node-not-wired-to-end": "ii",
    "orphan-node": "iii",
    "path-map-target-undefined": "iv",
    "edge-target-undefined": "iv",
}

fixtures = [load_fixture(path) for path in sorted(CORPUS.glob("*.yaml"))]
agreed = 0
for fixture in fixtures:
    report = run_property("graph-well-formed", fixture.ir)
    agreed += models_equivalent(report, fixture.expected_report())
    if report.result == "pass":
        witness = report.witness
        summary = f"{len(witness.reachable_from_start)} reachable, "
        summary += f"{len(witness.terminal_nodes)} wired to END"
    else:
        failure = report.failure
        anchor = to_data(failure.location)
        site = anchor.get("node") or f"{anchor['source']}/{anchor['label']}"
        more = f" (+{len(failure.co_failures)} more)" if failure.co_failures else ""
        summary = f"({CONDITION[failure.property_condition]}) {failure.property_condition}"
        summary += f" at {site}{more}"
    print(f"{fixture.path.stem[:41]:43}{report.result:6}{summary}")

print(f"{agreed} of {len(fixtures)} reports equal the fixture's own expected block")
```

<!-- gebra:output id=four-conditions -->
```text
negative-01-unreachable-escalation-node    fail  (i) node-unreachable-from-start at escalate_to_human
negative-02-dead-end-review-branch         fail  (ii) dead-end-node-not-wired-to-end at flag_for_review
negative-03-path-map-typo-dangling-target  fail  (iv) path-map-target-undefined at review_booking/confirm (+1 more)
negative-04-unwired-orphan-node            fail  (iii) orphan-node at search_hotels (+2 more)
positive-01-linear-document-pipeline       pass  4 reachable, 1 wired to END
positive-02-support-triage-branching       pass  5 reachable, 1 wired to END
positive-03-travel-parent-graph-with-book  pass  3 reachable, 1 wired to END
7 of 7 reports equal the fixture's own expected block
```

Three distinctions are worth keeping straight, and the negatives are where they come apart.

**Unreachable is not orphaned.** `escalate_to_human` in `negative-01` is a stranded handler: it
has an outgoing edge, so it participates in the topology and is no orphan — nothing routes *to*
it, so condition (i) fires and only condition (i). The repair is a router label, not an edge out.

**Orphaned is all three at once.** `search_hotels` in `negative-04` was added to the builder and
never wired: no edge in, no edge out, in neither `entry` nor `finish`. A node with zero
participation is necessarily also unreachable and also a dead end, so the report carries the
orphan as the primary with the other two as co-findings — the root-cause order doing its job.

**A dead end is about outgoing edges, not about reaching the end of your workflow.**
`flag_for_review` in `negative-02` is reachable and participating; it simply has nowhere to go.
The repair is to give it somewhere to go: an edge onward, or a place in `finish` — which is what
`add_edge("flag_for_review", END)` becomes in the document once a builder is extracted, and the
subject of the next section.

The last line matters as much as the rest: every one of the seven reports equals the fixture's
own `expected:` block. These are frozen examples the validator is held to in CI, not
illustrations written beside it.

## Wired by a sentinel is still wired

The P-01 rule most likely to surprise: **membership in `entry` or `finish` counts as edge
participation.** A node listed in `finish` carries the implicit edge to `END` and is therefore
not an orphan, even with no explicit edge anywhere in the document. That reading — "Reading A" —
was ratified in DEC-11 over the stricter alternative that counts only authored `edges[]`, and the
case that separates them is the smallest graph there is: one node, no edges.

<!-- gebra:example id=sentinel-wiring -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import run_property, to_data

document = {
    "ir_version": "1.0",
    "entry": ["n"],
    "finish": ["n"],
    "nodes": [{"id": "n"}],
    "edges": [],
}

for label, wiring in (("entry + finish", ["n"]), ("neither", [])):
    document["entry"] = wiring
    document["finish"] = wiring
    report = run_property("graph-well-formed", load_json(WorkflowIR, json.dumps(document)))
    print(f"n listed in {label:15}-> {report.result}")
    if report.result == "pass":
        witness = report.witness
        print(f"   terminal_nodes {list(witness.terminal_nodes)}")
        print(f"   orphan_nodes   {list(witness.orphan_nodes)}")
    else:
        failure = report.failure
        found = [failure.property_condition]
        found += [entry.property_condition for entry in failure.co_failures or ()]
        print(f"   at node {to_data(failure.location)['node']}: {', '.join(found)}")
```

<!-- gebra:output id=sentinel-wiring -->
```text
n listed in entry + finish -> pass
   terminal_nodes ['n']
   orphan_nodes   []
n listed in neither        -> fail
   at node n: orphan-node, node-unreachable-from-start, dead-end-node-not-wired-to-end
```

Same node, same zero edges, opposite verdicts — the difference is entirely the sentinel wiring.
Under the rejected reading the first graph would have failed as an orphan too, even though the
implicit `START → n` and `n → END` wiring is real topology. Practically: if a report calls a
node an orphan, the fix is to wire it *or* to declare it an entry or a finish; and a terminal
handler you reach by a router but never wire onward needs to be in `finish`, or condition (ii)
will say so.

## What P-01 reads

P-01 is topology-only. It reads `entry`, `finish`, `nodes[].id` and each edge's
`from`/`to`/`kind`/`path_map`, and it reads nothing else — not the state schema, not node
annotations, not the runtime block, not the router's condition string (§1.3). That is a claim
about the code, so it is worth checking rather than believing:

<!-- gebra:example id=topology-only -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import WorkflowIR, dump_json, load_json
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "graph-well-formed"

fixture = load_fixture(CORPUS / "positive-02-support-triage-branching.yaml")
document = json.loads(dump_json(fixture.ir))

removed = [f"state ({len(document.pop('state'))} keys)"]
for node in document["nodes"]:
    if node.pop("annotations", None) is not None:
        removed.append(f"{node['id']}.annotations")
for edge in document["edges"]:
    if edge.pop("condition", None) is not None:
        removed.append(f"{edge['from']}.condition (the router expression)")

stripped = load_json(WorkflowIR, json.dumps(document))
before = run_property("graph-well-formed", fixture.ir)
after = run_property("graph-well-formed", stripped)

print(f"removed   {len(removed)} members that P-01 does not read:")
for member in removed:
    print(f"            {member}")
print("kept      entry, finish, nodes[].id, edges[].from/to/kind/path_map")
print(f"verdicts  {before.result} before, {after.result} after")
print(f"reports equal: {models_equivalent(before, after)}")
```

<!-- gebra:output id=topology-only -->
```text
removed   7 members that P-01 does not read:
            state (4 keys)
            classify_ticket.annotations
            handle_billing.annotations
            handle_technical.annotations
            handle_general.annotations
            send_reply.annotations
            classify_ticket.condition (the router expression)
kept      entry, finish, nodes[].id, edges[].from/to/kind/path_map
verdicts  pass before, pass after
reports equal: True
```

Every contract and the whole state schema removed, and the report is the same value. Three
things follow. Annotating a node — or getting an annotation wrong — never moves a P-01 verdict;
that is P-04's and P-06's territory, and
[contracts and annotations](../tutorials/contracts-and-annotations.md) is where declarations get
read. A P-01 pass is correspondingly narrow: it says the wiring holds, and nothing about whether
the nodes agree on the data they pass. And P-01's cost is set by the graph alone — the
specification's bound is independent of how large the state schema is (§1.5).

## What a pass does not claim

**Well-formedness says nothing about cycles.** P-01 is cycle-agnostic: it never enumerates
cycles, and a cycle is neither a finding nor an exemption here (§1.1). The corpus makes the gap
visible, because a fixture authored to fail P-02 passes P-01 outright:

<!-- gebra:example id=well-formed-is-not-well-behaved -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import run_property, to_data

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties"
LOOP = CORPUS / "termination-witness" / "negative-01-unwitnessed-reflection-loop.yaml"

fixture = load_fixture(LOOP)
print(f"fixture   {fixture.fixture_id}")
for slug in ("graph-well-formed", "termination-witness"):
    report = run_property(slug, fixture.ir)
    if report.result == "pass":
        witness = report.witness
        reached = len(witness.reachable_from_start)
        print(f"{slug:22}pass  {reached} nodes reachable, no orphan, every reference resolves")
    else:
        failure = report.failure
        anchor = to_data(failure.location)
        print(f"{slug:22}fail  {failure.severity}: {failure.property_condition}")
        print(f"{'':22}      at {anchor['kind']} {', '.join(anchor['nodes'])}")
```

<!-- gebra:output id=well-formed-is-not-well-behaved -->
```text
fixture   termination-witness/negative-01-unwitnessed-reflection-loop.yaml
graph-well-formed     pass  4 nodes reachable, no orphan, every reference resolves
termination-witness   fail  fatal: cycle-without-termination-witness
                            at scc act, plan, reflect
```

A plan/act/reflect loop with no declared bound is perfectly well-formed. Whether a cycle carries
a declared termination witness is P-02's question, and a P-01 pass settles nothing about it.

**Condition (ii) is about sinks, and only sinks.** A component whose members all have outgoing
edges but from which `END` cannot be reached is not a P-01 finding. That is the catalog's
condition read literally, and the wider reading was considered and left out so that
cycle-adjacent defects stay P-02's — one root cause, one report. The limit is recorded as an
open item in the specification (§1.7), not closed quietly here.

**A mounted subgraph is one opaque node.** `positive-03` in the sweep above passes on its parent
topology; the interior of a compiled subgraph is P-10's subject, and this release does not
implement P-10 — a run answers for it with a structured not-implemented marker, never a silent
pass.

**When P-01 fails, three other reports become diagnostics.** P-02, P-04 and P-06 all reason over
the same topology, and the specification defines their results only over P-01-clean graphs
(§0.3). A run that fails P-01 names them in its `best_effort` list, and the honest reading of a
pass there is "no problem was found while walking a graph that is not well-formed" — fix the
P-01 finding and re-run before drawing any conclusion from them.
[Verify and interpret](../tutorials/verify-and-interpret.md#when-p-01-fails-three-reports-become-diagnostics)
shows that on a real run, along with the gate and the suppressed snapshot that come with it.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking
a runnable, resolving a hostname or opening a connection all raise. The output blocks are what
those runs printed, and three of them additionally re-check the whole report against the
corpus's own frozen `expected:` block —
[Executable examples](../contributing/executable-examples.md) explains the mechanism.

The frozen contract behind this page is PROPERTY-CATALOG-SPEC §1 with the shared envelope of
§0, and the shapes it pins were ratified in decision records DEC-11 (the five-key witness, the
orphan reading) and DEC-12 (`edge-target-undefined`'s scope and the ordering of condition-(iv)
findings). `gebra.verify.properties.graph_well_formed` and its tests are where that contract is
implemented and pinned in this repository.
