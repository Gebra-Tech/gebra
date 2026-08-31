# P-02 `termination-witness`

P-02 asks one question about a workflow definition: **does every loop declare a bound?**

Not *will this agent stop* — nothing in a document settles that, and P-02 never answers it.
What it answers is whether every simple cycle in the graph carries a declared **termination
witness**: a bounded counter in the state schema whose guard has a wired exit, a justified
`recursion_limit`, or an annotated loop variant. Witness presence is a fact about the document,
and it is the whole claim.

Every P-02 finding is **FATAL** and **DEFENSIBLE**. Fatal is a design-time grade rather than a
prediction: it fails the gate and suppresses snapshot recording for that run, because a loop
nobody wrote a bound for is the one that turns a retry into an invoice. Defensible because
reading the document settles whether the declaration is there — what it cannot settle is
whether the declaration is *true*, and that line is the subject of the last section on this
page. This page is about reading P-02's findings: what the validator checks, what each field of
its witness and its failure record means, and where the claim stops.

!!! note "Section numbers, and where they point"

    `§` references are to **PROPERTY-CATALOG-SPEC** — §2 is its P-02 section, §0 the shared
    report envelope — and `T-W §` references are to the **TERMINATION-WITNESS-SPEC**, which
    owns the witness semantics the catalog cites. Both are internal contract documents and are
    not published with this site; the numbers are here so a statement can be *checked* against
    them rather than taken on trust. The transcripts are not spec-derived: they are what this
    release printed.

!!! note "Following along"

    Six of the nine examples here run over the vendored property-fixture corpus in this
    repository, `tests/fixtures/properties/` — one YAML document per fixture, carrying an IR
    and the verdict the specification expects for it. Two write a small IR document by hand,
    and one reads no document at all: it asks the guard recognizer about condition strings. To
    run them yourself, clone the repository and put its root on `PYTHONPATH` — the corpus is
    located from `tests.__file__`, so an example works from any directory. Nothing here builds
    or compiles a LangGraph graph: a fixture is data, and the illustrative builder code some
    fixtures carry is an inert string that is never compiled or run.

## What P-02 checks

On P-01-clean topology, P-02 reads the same **sentinel-augmented, label-expanded** graph P-01
does: the document's nodes plus the implicit `START` and `END` vertices, with each `path_map` entry expanded into
its own edge and a label valued `"END"` pointing at the exit (§2.4; ledger §4). Expansion is a
prerequisite rather than a tidying step: a counter guard bounds *one* branch of a router, so a
witness has to be able to name one label's edge and leave the router's other labels alone.
Without expansion there would be no such thing to name.

Over that graph, three kinds of declaration count as a bound (T-W §2):

| Form | What you declare | Where you declare it | What it covers |
|---|---|---|---|
| **(a)** counter guard | a state key of declared type `int`, compared against an integer literal in a conditional edge's `condition`, where the comparison gates the branch that **stays in** the loop and some other label leaves it | `state` + `edges[].condition`/`path_map` | the gated label's edge — so every simple cycle running through that edge |
| **(b)** justified limit | `runtime.recursion_limit`, whose `value` is the step budget and whose `justification` says why that number | `runtime` | every cycle at once — a blanket over the whole graph |
| **(c)** loop variant | a `variant: {key, measure}` annotation whose `key` is in `state` | `nodes[].annotations` | the annotated node — so every simple cycle running through it |

The forms are ranked **(a) > (c) > (b)** by the strength of their evidence (T-W §2.4). Form (a)
is structure the document decides: the counter is in the schema, the comparison is in the guard,
the escape is wired. Form (c) is localized but attested — gebra records the measure you declared
and trusts it. Form (b) is a global step budget rather than a per-loop bound, which is why a
graph covered by it alone passes with a warning rather than silently; that case has
[its own section](#a-justified-limit-passes-and-strict-mode-is-where-it-bites) below.

**How coverage is decided.** Every declaration that names a piece of the graph becomes one — an
edge for each form (a), a node for each form (c). P-02 deletes them and asks whether anything
cyclic survives. Every simple cycle carries one of those **element** witnesses if and only if
what remains is acyclic (T-W §5, Lemma 1), so the verdict is one pass over the residual graph
and never an enumeration of cycles. (Form (b) names no element — it is a budget over the whole
graph, and it is layered on top of that test rather than taking part in it.) Two consequences a reader meets in reports. Granularity is per **simple cycle**, not
per strongly connected component: a witnessed outer loop does not cover an unwitnessed inner one
(DEC-05 D1), because deleting the outer loop's edge leaves the inner cycle standing. And the
check stays linear on graphs whose cycle count is astronomically large, because it never counts
them.

P-02 has two things to say when a document does not satisfy that, and they are different
defects:

| Condition | What it requires | Condition ID | Anchor |
|---|---|---|---|
| **cycle without a witness** | every simple cycle contains at least one declared witness element | `cycle-without-termination-witness` | the surviving component, with one representative cycle |
| **counter guard with no exit** | a recognized counter guard has some label leaving its loop, so the bound can take effect | `counter-guard-without-exit-edge` | one simple cycle through the guard |

Those two strings are the whole P-02 vocabulary. Both are in the frozen condition-ID registry
and emittable by this release (§0.4) — a validator may not emit a string the registry does not
hold, and [what gebra checks](../concepts/what-gebra-checks.md#the-diagnostic-vocabulary-is-frozen)
explains why that matters downstream. Strict mode adds no third string; it reuses the first,
as the last section shows.

## A pass carries an inventory and a certificate

A passing property does not return a bit. It returns a **witness**: structured, re-checkable
evidence, never prose (§0.3). P-02's is an inventory of what you declared plus a certificate
that it was enough — the form pinned by decision record DEC-11.

<!-- gebra:example id=a-pass-and-its-witness -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "termination-witness"

fixture = load_fixture(CORPUS / "positive-01-counter-guarded-retry-loop.yaml")
report = run_property("termination-witness", fixture.ir)
counter = fixture.ir.state["retry_count"]

print(f"fixture   {fixture.fixture_id}")
print(f"graph     {len(fixture.ir.nodes)} nodes, {len(fixture.ir.edges)} authored edges")
print(f"counter   retry_count declared {counter.type}, reducer {counter.reducer}")
print(f"guard     {fixture.ir.edges[-1].condition}")
print(f"result    {report.result} — the failure field is {report.failure}")
print("witness   serialized in the report profile:")
print(to_json(report.witness))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-pass-and-its-witness -->
```text
fixture   termination-witness/positive-01-counter-guarded-retry-loop.yaml
graph     4 nodes, 3 authored edges
counter   retry_count declared int, reducer operator.add
guard     'retry' if response is transient-failure and retry_count < 3 else 'done'
result    pass — the failure field is None
witness   serialized in the report profile:
{
  "kind": "termination",
  "inventory": [
    {
      "form": "a",
      "element": {
        "kind": "edge",
        "source": "check_response",
        "target": "call_service",
        "label": "retry"
      },
      "source": {
        "guard_edge": {
          "source": "check_response",
          "label": "retry"
        },
        "counter_key": "retry_count",
        "bound": 3
      },
      "discharges": "all-simple-cycles-through-element"
    }
  ],
  "certificate": [
    "START",
    "submit_request",
    "call_service",
    "check_response",
    "compile_result",
    "END"
  ],
  "notes": [],
  "cycles": {
    "exhaustive": true,
    "cycles": [
      [
        "call_service",
        "check_response"
      ]
    ]
  }
}
equals the fixture's own expected block: True
```

That is a retry loop: a service call, a check, and a router that either goes round again or
moves on. Its one cycle is `call_service → check_response → call_service`, and the router's
guard is where the bound is declared.

**`kind`** is the discriminator. The envelope's witness type is a union with one member per
property, and every consumer reads `kind` before anything else (§0.3).

**`inventory` is one entry per declared witness element**, and each entry answers three
questions: which form it is, which element of the graph it discharges, and what you wrote that
made it one.

* **`form`** is `"a"`, `"b"` or `"c"`, and it fixes the rest of the entry — the model refuses an
  entry whose parts disagree.
* **`element`** is what gets deleted from the graph. For form (a) that is an `edge` location
  naming the router (`source`), the label (`label`) and where it goes (`target`) — here the
  `retry` label, and *only* that label. The declared bound covers the branch its comparison
  gates, so the `done` branch is not a witness element and neither is any other label the router
  declares (T-W §3 R6, §4). For form (c) the element is the carrier node; form (b) has none at
  all, and the member is simply absent.
* **`source`** is the evidence, structured. Form (a) carries the `guard_edge` it was recognized
  on, the `counter_key` it compared and the `bound` it compared against; form (b) carries the
  `recursion_limit` declaration including its justification; form (c) carries the `variant`
  annotation including its `measure`.
* **`discharges`** says what the element covers: `all-simple-cycles-through-element` for
  (a) and (c), `blanket` for (b). It has a third value — an empty list — for a `variant`
  annotation on a node that lies on no cycle at all. Such an entry is vacuous rather than
  wrong: the declaration is surfaced, and by default no finding of any severity follows from it.

**`certificate` is the re-checkable half.** It is a topological order of what is left after the
witness set is deleted, carrying the display sentinels `START` and `END` like every other path
list in a report. A consumer verifies the whole verdict without trusting the checker: delete the
inventory's elements from the document's own graph and confirm the order is topological. If it
is, nothing cyclic survived, and by Lemma 1 that is exactly the property. Where a justified
limit is the only cover for some region, that check reads differently and the note below flags
exactly those regions: the witness set is then the blanket over every edge, so the graph being
ordered is edgeless and any order orders it.

**`notes`** carries structured advisories — five kinds, listed
[further down](#every-finding-and-every-near-miss-rides-one-record). It is empty here, and an
empty `notes` on a pass is a statement about the declarations the analysis could see: nothing
that derived the guard grammar missed qualifying, no `variant` named an unknown key, no region
is riding on a blanket limit alone, and the census below it is complete. What it does not cover
is a guard the grammar rejected outright — that case is silent by rule, and the
[recognizer section](#which-guard-strings-the-recognizer-accepts) is where it is met.

**`cycles` is optional, and its absence means the graph was too tangled to enumerate.** When a
census is present, `exhaustive` is `true` and `cycles` lists every simple cycle in the graph.
That is the only value `exhaustive` takes: enumeration stops at cycle 17, because the cap is
16 (DEC-11), and a run that hits the cap omits the list and leaves the `cycle-census-capped`
note instead. There is no partial census. The census is a convenience for reading a report, not
part of the verdict — the verdict was already decided by the certificate.

**The last line is the corpus's own claim, re-run.** `models_equivalent` is §0.3's comparison —
model equality, with multiset comparison on the fields the specification marks order-free. The
validator's output and the fixture's `expected:` block validate into the *same* class, so the
frozen example and the result type cannot drift apart.

!!! note "`run_property` versus `verify()`"

    `run_property` is the single-property dispatch, which is what a page about one validator
    wants. A whole run goes through `verify()`, which additionally derives the gate and answers
    for all thirteen catalog properties.
    [Verify and interpret](../tutorials/verify-and-interpret.md) works through a full run.

## Three ways to declare a bound

The corpus's `termination-witness/` directory is where the forms and the findings are pinned:
seven positives and five negatives. Running the validator over all twelve at once is the
shortest tour of what P-02 can say.

<!-- gebra:example id=three-forms -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_data

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "termination-witness"

fixtures = [load_fixture(path) for path in sorted(CORPUS.glob("*.yaml"))]
agreed = 0
for fixture in fixtures:
    report = run_property("termination-witness", fixture.ir)
    agreed += models_equivalent(report, fixture.expected_report())
    if report.result == "pass":
        witness = report.witness
        forms = "+".join(sorted(entry.form for entry in witness.inventory)) or "none"
        summary = f"forms {forms}"
        summary += "".join(f", note {note.kind}" for note in witness.notes)
    else:
        anchor = to_data(report.failure.location)
        summary = f"{report.failure.property_condition}"
        summary += f" ({len(anchor['nodes'])}-node {anchor['kind']})"
    print(f"{fixture.path.stem[:48]:50}{report.result:6}{summary}")

print(f"{agreed} of {len(fixtures)} reports equal the fixture's own expected block")
```

<!-- gebra:output id=three-forms -->
```text
negative-01-unwitnessed-reflection-loop           fail  cycle-without-termination-witness (3-node scc)
negative-02-nested-scc-outer-only-witness         fail  cycle-without-termination-witness (2-node scc)
negative-03-counter-guard-without-wired-exit      fail  counter-guard-without-exit-edge (3-node cycle)
negative-04-supervisor-delegation-scc-no-witness  fail  cycle-without-termination-witness (3-node scc)
negative-05-unwitnessed-self-loop                 fail  cycle-without-termination-witness (1-node scc)
positive-01-counter-guarded-retry-loop            pass  forms a
positive-02-justified-recursion-limit-refinement  pass  forms a+b
positive-03-shrinking-worklist-hotel-quotes       pass  forms c
positive-04-nested-scc-dual-counter-witnesses     pass  forms a+a
positive-05-recursion-limit-only-scc-note         pass  forms b, note scc-covered-only-by-recursion-limit
positive-06-cycle-census-capped-overflow          pass  forms c, note cycle-census-capped
positive-07-acyclic-graph-vacuous-empty-inventor  pass  forms none
12 of 12 reports equal the fixture's own expected block
```

Read down the pass column and the three forms are all there, each with the shape of loop it is
for.

**Form (a) is for a loop you count.** `positive-01` is the retry loop above. `positive-04`
carries two of them in one component, which is the next section. Both directions of comparison
are recognized: an increment counted up against a ceiling (`retry_count < 3`) and a budget
counted down against a floor (`remaining_steps > 2`, `positive-02`'s guard).

**Form (c) is for a loop you drain.** `positive-03` walks a shortlist of hotels one quote at a
time. There is no counter to compare — the loop ends when the list is empty — so what the
document declares is a `variant`: the key that shrinks and the measure that shrinks about it.
`positive-06` is the same shape on a graph with more cycles than the census cap allows, which is
why its line carries `cycle-census-capped` and its witness has no `cycles` member.

**Form (b) is for the loop you have not modelled yet.** `positive-02` declares a justified
`recursion_limit` *and* a counter guard, and both appear in the inventory: redundant coverage is
not an error. `positive-05` declares only the limit, which is the case that passes with the
WARNING-grade note.

**And one pass claims nothing at all.** `positive-07` is acyclic. Its inventory is empty, its
certificate is the whole graph, and the verdict is vacuous in the exact sense that there was no
obligation to discharge — which is the honest reading of a P-02 pass on a straight-line
pipeline.

Now read down the fail column, where the parenthetical is the shape of the region that survived.
`negative-05` is a **self-loop**: a node whose edge returns to itself is a simple cycle of
length one, so its component has exactly one node and needs a witness like any other.
`negative-04` is a supervisor delegating to two workers — one component, two simple cycles
through the shared supervisor, and still exactly one finding, because a finding carries one
representative cycle rather than a census. And `negative-03` is the only line anchored on a
`cycle` rather than an `scc`, which is the other condition ID and
[its own section](#a-counter-with-nowhere-to-go-is-a-different-defect) below.

The last line matters as much as the rest: every one of the twelve reports equals the fixture's
own `expected:` block. These are frozen examples the validator is held to in CI, not
illustrations written beside it.

## A failure names the region it could not discharge

The other half of the envelope. A failing property fills `failure` with a structured record: the
violated **condition ID**, the **location** it was found at, its **severity** and its **claim
class** (§0.3). The fixture below is a plan/act/reflect loop that exits on the model's own
judgement and on nothing else — a graph that is
[perfectly well-formed](p01-graph-well-formed.md#what-a-pass-does-not-claim), which is the same
point from the other side: wiring and bounds are different questions.

<!-- gebra:example id=a-failure-and-its-record -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "termination-witness"

fixture = load_fixture(CORPUS / "negative-01-unwitnessed-reflection-loop.yaml")
report = run_property("termination-witness", fixture.ir)

print(f"fixture   {fixture.fixture_id}")
print(f"guard     {fixture.ir.edges[-1].condition}")
print(f"result    {report.result} — the witness field is {report.witness}")
print("record    serialized in the report profile:")
print(to_json(report.failure))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-failure-and-its-record -->
```text
fixture   termination-witness/negative-01-unwitnessed-reflection-loop.yaml
guard     router decides 'continue' or 'done' from latest observations (LLM-influenced; no declared bound)
result    fail — the witness field is None
record    serialized in the report profile:
{
  "property_condition": "cycle-without-termination-witness",
  "location": {
    "kind": "scc",
    "nodes": [
      "act",
      "plan",
      "reflect"
    ],
    "representative_cycle": [
      "act",
      "reflect",
      "plan"
    ],
    "exhaustive": false
  },
  "severity": "fatal",
  "claim_class": "defensible"
}
equals the fixture's own expected block: True
```

Field by field, because every one of them is load-bearing.

**`property_condition`** is the machine-readable half of the finding: the stable string to key
on rather than parsing prose. It is a registry entry, frozen verbatim (§0.4).

**`location` is typed, and P-02 extends the type.** The envelope has six structural anchors —
node, edge, cycle, SCC, state-key and path — and this finding uses the **SCC** anchor: the
strongly connected component that survived the deletion. `nodes` is the component, sorted;
`representative_cycle` is *not* sorted, and the difference is the point. The component is a set
of nodes that can all reach each other; the representative cycle is one concrete round trip
through them, in traversal order and rotated to start at the lexicographically least id. It is
the counterexample you can walk with your finger.

**`exhaustive: false` is a statement about that cycle, and it is doing real work.** The finding
carries *one* witness-free cycle per surviving component, never a census of them: a component
can hold enormously many cycles, and enumerating them to report a defect would cost more than
the check itself. So the honest reading is "here is a cycle with no bound", not "here is the
only one". After you fix it, re-run — if the component still holds an uncovered cycle, the next
run surfaces it (T-W §6.1).

**`severity` and `claim_class` are read off the registry, not restated by the validator.** For
P-02 they are `fatal` and `defensible` on every finding, which is why a P-02 failure both fails
the gate and suppresses snapshot recording for that run (§0.2).

**The optional members are absent, not empty.** `remediation`, `co_failures`, `advisories`,
`subsumed_by` and `notes` are all unset on this record, and the report profile drops unset
members rather than writing nulls — so an omitted key and a validator that set nothing produce
the same document. Two of them move with the document: this graph has one unwitnessed region
and no near misses, so `co_failures` and `notes` have nothing to carry, and the
[record below](#every-finding-and-every-near-miss-rides-one-record) fills both. The other three
are not P-02's to fill at all: `advisories` carries *other* properties' side findings and never
the reporting property's own (§0.3), `remediation` is display-only prose this validator does
not write, and `subsumed_by` marks a finding another property owns — P-02's own subsumption
rule, below, works by not emitting the second finding rather than by labelling it.

## One witness per simple cycle, never one per component

The rule most likely to cost you a build: **a bound on the outer loop does not bound the inner
one.** The corpus pins it with a matched pair — the same shape twice, once with a counter on
each cycle and once with the inner counter and its guard removed.

<!-- gebra:example id=outer-bound-does-not-bound-inner -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import run_property, to_data

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "termination-witness"

for name in (
    "positive-04-nested-scc-dual-counter-witnesses.yaml",
    "negative-02-nested-scc-outer-only-witness.yaml",
):
    fixture = load_fixture(CORPUS / name)
    report = run_property("termination-witness", fixture.ir)
    print(f"{fixture.path.stem}  ->  {report.result}")
    if report.result == "pass":
        for entry in report.witness.inventory:
            element = entry.element
            print(f"   counter {entry.source.counter_key} bounds ", end="")
            print(f"{element.source} --{element.label}--> {element.target}")
        for cycle in report.witness.cycles.cycles:
            print(f"   cycle   {' -> '.join(cycle)} -> {cycle[0]}")
    else:
        anchor = to_data(report.failure.location)
        print(f"   {report.failure.property_condition}")
        print(f"   survives: {' -> '.join(anchor['representative_cycle'])}", end="")
        print(f" -> {anchor['representative_cycle'][0]}")
```

<!-- gebra:output id=outer-bound-does-not-bound-inner -->
```text
positive-04-nested-scc-dual-counter-witnesses  ->  pass
   counter quote_retry_count bounds validate_quote --requote--> quote_fares
   counter revision_round bounds assess_itinerary --revise--> draft_itinerary
   cycle   quote_fares -> validate_quote -> quote_fares
   cycle   assess_itinerary -> draft_itinerary -> quote_fares -> validate_quote -> assess_itinerary
negative-02-nested-scc-outer-only-witness  ->  fail
   cycle-without-termination-witness
   survives: judge_fare -> poll_fare -> judge_fare
```

Both graphs are five nodes with one strongly connected component holding two simple cycles: an
outer revision loop through `draft_itinerary`, and an inner fare loop between the two middle
nodes, which the two fixtures name differently. In the positive, each cycle has its own counter
and its own guarded exit, so deleting the two gated edges leaves nothing cyclic behind — and the
census confirms it, listing exactly the two cycles that had to be covered. In the negative the
inner counter and its guard are gone, and the inner cycle survives, even though the component it
sits in is, at component level, "witnessed".

That is why coverage is per simple cycle. Component-level accounting would have passed the
negative: there *is* a witness in that component. But the outer counter only ever increments at
`draft_itinerary`, which the inner cycle never visits, so nothing in the document bounds the
re-pricing inside a single outer lap. The residual test finds exactly that bypass, and it is
also what makes the pass
trustworthy: one shared element may legitimately cover many cycles, and the check does not care
how many, only that none survive.

## A counter with nowhere to go is a different defect

A bounded counter is not a witness on its own. The comparison has to gate a branch, and the
router has to have some branch that leaves the loop — otherwise the counter saturates with no
wired escape and the bound is vacuous. That defect gets its own condition ID, deliberately, so
the diagnostic points at the wiring rather than reporting a missing declaration you did in fact
make (DEC-05 D4).

<!-- gebra:example id=counter-guard-without-exit-edge -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "termination-witness"

fixture = load_fixture(CORPUS / "negative-03-counter-guard-without-wired-exit.yaml")
report = run_property("termination-witness", fixture.ir)
guard = fixture.ir.edges[-1]

print(f"fixture   {fixture.fixture_id}")
print(f"guard     {guard.condition}")
print(f"path_map  {dict(guard.path_map)}")
print(f"result    {report.result}, {len(report.failure.co_failures or ())} co-findings")
print("record    serialized in the report profile:")
print(to_json(report.failure))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=counter-guard-without-exit-edge -->
```text
fixture   termination-witness/negative-03-counter-guard-without-wired-exit.yaml
guard     'immediate' if refresh_count < 4 else 'delayed'
path_map  {'immediate': 'fetch_rates', 'delayed': 'fetch_rates'}
result    fail, 0 co-findings
record    serialized in the report profile:
{
  "property_condition": "counter-guard-without-exit-edge",
  "location": {
    "kind": "cycle",
    "nodes": [
      "evaluate_rates",
      "throttle_check",
      "fetch_rates"
    ],
    "counter_key": "refresh_count",
    "guard_edge": {
      "source": "throttle_check",
      "labels": [
        "immediate",
        "delayed"
      ]
    }
  },
  "severity": "fatal",
  "claim_class": "defensible"
}
equals the fixture's own expected block: True
```

Every ingredient of form (a) is present: `refresh_count` is an `int` in the state schema, the
node increments it, and the guard compares it against a literal. The bug is one label — the
`delayed` branch was meant to abandon the search and instead routes back into the loop, so the
counter selects the retry cadence and nothing else. This is the copy-paste defect the fixture
was written for, and it is the reason the check does not stop at "there is a counter here".

The record uses the **cycle** anchor rather than the SCC anchor, and carries two fields the SCC
anchor does not: **`counter_key`**, the key whose bound is inert, and **`guard_edge`**, naming
the router (`source`) and every label it declares (`labels`) — the two things you need in order
to see that no label leaves. `nodes` is one simple cycle running through the guard.

**No second finding rides along, and that is a rule rather than a coincidence.** This region is
also, strictly, a cycle with no witness — but reporting both would be reporting one root cause
twice, so the wiring finding subsumes the base condition for its own component (DEC-05 D2,
ratified in DEC-11). Fix the label and the guard becomes a witness; nothing else needed fixing.

**The exit test is relative to the loop, not to the component.** A guard inside a nested loop
discharges when some label leaves *its own* loop, even if every label stays inside the larger
component it is part of — which is what lets `positive-04`'s inner guard qualify above while
this one does not (DEC-23). On a loop with no single entry point the test widens back to the
component, which can only refuse a discharge, never grant one.

## Which guard strings the recognizer accepts

Form (a) reads the `condition` string a router declares, and it reads it as **syntax**: a
grammar match, never an evaluation. Nothing on this page — and nothing anywhere in gebra — runs
a guard. So the practical question is which strings the grammar accepts, and the recognizer will
answer it directly for any string you have.

<!-- gebra:example id=which-guards-are-recognized -->
```python
from gebra.verify import classify_guard

CONDITIONS = (
    "'retry' if response is transient-failure and retry_count < 3 else 'done'",
    "'again' if 3 > attempts else 'stop'",
    "'done' if attempts >= 3 else 'retry'",
    "retry_count < 3",
    "'retry' if retry_count < 3 or force else 'done'",
    "'quote' if len(hotel_shortlist) > 0 else 'rank'",
    "'retry' if attempts != 3 else 'done'",
)

for condition in CONDITIONS:
    found = classify_guard(condition)
    print(condition)
    if found.recognized:
        guard = found.guard
        print(f"   recognized: {guard.comparison.direction} bound {guard.bound} ", end="")
        print(f"on {guard.counter_key}, gating the {guard.then_label!r} label")
    else:
        print(f"   opaque ({found.rejected_by}): {found.reason}")
```

<!-- gebra:output id=which-guards-are-recognized -->
```text
'retry' if response is transient-failure and retry_count < 3 else 'done'
   recognized: upper bound 3 on retry_count, gating the 'retry' label
'again' if 3 > attempts else 'stop'
   recognized: upper bound 3 on attempts, gating the 'again' label
'done' if attempts >= 3 else 'retry'
   recognized: lower bound 3 on attempts, gating the 'done' label
retry_count < 3
   opaque (L0): L0 requires exactly one `if` token; found 0
'retry' if retry_count < 3 or force else 'done'
   opaque (L0): L0 rejects any `or` token (R4: disjunction and negation)
'quote' if len(hotel_shortlist) > 0 else 'rank'
   opaque (L0): L0 rejects parenthesis and bracket characters; found '('
'retry' if attempts != 3 else 'done'
   opaque (R1): R1 needs a `bounded-comparison` conjunct; `test` has none
```

The host shape is the router ternary LangGraph users already write: `'<label>' if <test> else
'<label>'`, where `<test>` is one bounded comparison, optionally joined by `and` to conditions
the grammar makes no attempt to read. That last part is the useful liberty — the first string
above pairs an opaque judgement about a response with a real bound, and it qualifies, because an
extra condition can only make the branch *rarer*, which is the safe direction.

Everything else is opaque, and opaque means "contributes no witness" rather than "is an error".
The rejections above are each a rule:

* **A bare comparison** with no labels is not a guard shape. Nothing in the string says which
  branch the comparison selects, so there is no branch to discharge.
* **`or` and `not`** are refused outright: a disjunct lets the loop continue whatever the
  counter says, so reading it as a bound would be unsound.
* **Parentheses and brackets** end the match. `len(hotel_shortlist) > 0` is a real loop bound to
  a human and none at all to a grammar — whether a list shrinks is not something a document
  settles. Declare a `variant` instead; that is the form for it, and `positive-03` is the shape.
* **`==` and `!=`** are not bounds. One skipped value defeats them.

There is no partial credit: a string the grammar rejects contributes nothing, even when a
perfectly good comparison is sitting inside it (T-W §3 R5). Every exclusion fails in that
direction on purpose — the recognizer would rather miss a bound you declared than read one you
did not. When a loop's real bound is not something a grammar can see, that is what form (c) is
for: declare the `variant` and its measure, and the cycle is covered by an attested witness
instead of an unrecognized one.

### Recognized is not the same as discharged

The third string above is the case worth dwelling on, because it is an ordinary way to write a
bounded retry router and it does not produce a witness. The comparison gates the **first** label
— the one selected when the test is true — and that is the only branch a bound can cover. Write
the router so the true-branch is the one that *leaves* the loop, and the counter bounds an edge
that was never part of a cycle: the guard is recognized, nothing is discharged, and the loop
fails as unwitnessed. Same graph, same counter, two orders:

<!-- gebra:example id=recognized-is-not-discharged -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import classify_guard, run_property

document = {
    "ir_version": "1.0",
    "entry": ["plan"],
    "finish": ["ship"],
    "state": {"brief": {"type": "str", "optional": True}, "attempts": {"type": "int"}},
    "nodes": [{"id": "plan"}, {"id": "check"}, {"id": "ship"}],
    "edges": [
        {"from": "plan", "to": "check"},
        {
            "from": "check",
            "kind": "conditional",
            "condition": "",
            "path_map": {"done": "ship", "retry": "plan"},
        },
    ],
}
targets = document["edges"][1]["path_map"]

for condition in ("'done' if attempts >= 3 else 'retry'", "'retry' if attempts < 3 else 'done'"):
    document["edges"][1]["condition"] = condition
    report = run_property("termination-witness", load_json(WorkflowIR, json.dumps(document)))
    gated = classify_guard(condition).guard.then_label
    notes = report.failure.notes if report.result == "fail" else report.witness.notes
    print(condition)
    print(f"   comparison gates {gated!r}, which goes to {targets[gated]}")
    print(f"   -> {report.result}, {len(notes or ())} note(s)")
```

<!-- gebra:output id=recognized-is-not-discharged -->
```text
'done' if attempts >= 3 else 'retry'
   comparison gates 'done', which goes to ship
   -> fail, 0 note(s)
'retry' if attempts < 3 else 'done'
   comparison gates 'retry', which goes to plan
   -> pass, 0 note(s)
```

The first router is bounded in every way a person means it. P-02 still fails it, and — this is
the part to know — **says nothing about why**: an exit-on-truth guard is an explicit
no-discharge, no-diagnostic case (T-W §4), so there is no note to read and the only signal is a
`cycle-without-termination-witness` on a loop you thought you had bounded. The repair is the
second line: put the comparison on the branch that goes round again. If your router fails P-02
with a counter that looks right, check which label the comparison selects before checking
anything else.

There is one near miss the report *does* speak up about — a recognized shape whose counter is
unusable — and that is the next section.

## Every finding and every near miss rides one record

One property reports once, however many things it found. The deterministically-first finding
fills `failure` and every further same-property finding rides `co_failures` (§0.3). And when a
declaration nearly qualified — a counter key misspelled, a variant naming a key that is not in
the schema — the record says so in `notes`, so a typo can never quietly shrink your coverage.

The document below has both: two loops with no bound between them, and a guard whose counter is
one letter away from the key it meant.

<!-- gebra:example id=two-regions-and-a-near-miss -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import run_property, to_json

document = {
    "ir_version": "1.0",
    "entry": ["draft"],
    "finish": [],
    "state": {
        "brief": {"type": "str", "optional": True},
        "draft_text": "str",
        "revision_count": {"type": "int"},
    },
    "nodes": [{"id": "draft"}, {"id": "review"}, {"id": "publish"}, {"id": "audit"}],
    "edges": [
        {"from": "draft", "to": "review"},
        {
            "from": "review",
            "kind": "conditional",
            "condition": "'revise' if revison_count < 3 else 'publish'",
            "path_map": {"revise": "draft", "publish": "publish"},
        },
        {"from": "publish", "to": "audit"},
        {
            "from": "audit",
            "kind": "conditional",
            "condition": "'amend' if the auditor flags an issue else 'done'",
            "path_map": {"amend": "publish", "done": "END"},
        },
    ],
}
ir = load_json(WorkflowIR, json.dumps(document))

print(f"P-01 first: {run_property('graph-well-formed', ir).result}")
report = run_property("termination-witness", ir)
print(f"P-02:       {report.result}")
print(to_json(report.failure))
```

<!-- gebra:output id=two-regions-and-a-near-miss -->
```text
P-01 first: pass
P-02:       fail
{
  "property_condition": "cycle-without-termination-witness",
  "location": {
    "kind": "scc",
    "nodes": [
      "audit",
      "publish"
    ],
    "representative_cycle": [
      "audit",
      "publish"
    ],
    "exhaustive": false
  },
  "severity": "fatal",
  "claim_class": "defensible",
  "co_failures": [
    {
      "property": "termination-witness",
      "property_condition": "cycle-without-termination-witness",
      "location": {
        "kind": "scc",
        "nodes": [
          "draft",
          "review"
        ],
        "representative_cycle": [
          "draft",
          "review"
        ],
        "exhaustive": false
      },
      "severity": "fatal",
      "claim_class": "defensible"
    }
  ],
  "notes": [
    {
      "kind": "counter-key-not-qualified",
      "guard_edge": {
        "source": "review",
        "label": "revise"
      },
      "identifier": "revison_count"
    }
  ]
}
```

**Two findings, one record, and the order is not the document's.** Both loops fail, and the
primary is the `audit`/`publish` one even though the misspelled guard appears first in the
document. Findings are ordered by the sorted node tuple of the component they anchor on, then by
condition ID (§2.3, DEC-11) — `("audit", "publish")` sorts before `("draft", "review")`. That
ordering is worth knowing for one practical reason: it is stable. The same document produces the
same primary finding on every run and every machine, which is what lets a CI baseline be a
baseline.

**`co_failures` carries the rest, and nothing is dropped.** Each entry names its own property,
condition, location, severity and claim class — a co-finding is a finding, not a footnote.

**`notes` is the near-miss channel.** The `review` router's guard *derives* the grammar — it is
a proper ternary with a bounded comparison — but `revison_count` is not a key of the state
schema, so the guard qualifies as nothing and the loop it gates is unwitnessed. Rather than let
that vanish into a plain "no witness here", the record carries a `counter-key-not-qualified`
note naming the `guard_edge` it was recognized on and the `identifier` that went unmatched. A
misspelled key never silently shrinks coverage (T-W §4).

The note vocabulary is closed — five kinds, and the evidence each one carries:

| `kind` | What it says | Payload |
|---|---|---|
| `counter-key-not-qualified` | a guard matched the grammar, but its counter is not an `int` key of the schema | `guard_edge`, `identifier`, and `declared_type` when the key exists but is typed wrong |
| `variant-key-not-in-state` | a `variant` annotation names a key the schema does not have | `node`, `key` |
| `recursion-limit-without-justification` | a limit was declared with no justification, so it is no witness | — |
| `cycle-census-capped` | the graph has more simple cycles than the census cap, so no list is reported | — |
| `scc-covered-only-by-recursion-limit` | a region is covered by the blanket limit alone | `locations`, and `severity: warning` |

Only the last one carries a `severity`, and that is what makes it the only promotable note — the
subject of the next section. The other four are diagnostics: they explain a verdict, and they
never change one. Notes ride the witness on a pass and the failure record on a fail, always
(DEC-23).

The third row is defence in depth rather than something a valid document produces:
`justification` is a required member of `runtime.recursion_limit`, so a document that declares
a limit without one does not load in the first place.

## A justified limit passes, and strict mode is where it bites

Form (b) is a step budget for the whole graph rather than a bound on any particular loop. It is
a real declaration — a `recursion_limit` with a justification is a person saying they have
thought about it — so a region covered by it alone is neither a silent pass nor a failure. It
passes, with the one WARNING-grade note, and a strict policy is where that becomes a gate
(DEC-11; T-W §6.1).

<!-- gebra:example id=blanket-limit-and-strict-mode -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import (
    STRICT_OFF,
    RunPolicy,
    StrictPolicy,
    run_property,
    strict_promotions,
    to_json,
    verify,
)

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "termination-witness"

fixture = load_fixture(CORPUS / "positive-05-recursion-limit-only-scc-note.yaml")
report = run_property("termination-witness", fixture.ir)
limit = report.witness.inventory[0].source.recursion_limit

print(f"result    {report.result}, inventory holds form (b) alone, limit {limit.value}")
print("note      the witness carries one, and it is the only kind that has a severity:")
print(to_json(report.witness.notes[0]))
for promotion in strict_promotions(report):
    print(f"promoted  as {promotion.property_condition}")

only_p02 = StrictPolicy(mode="per-property", properties=("termination-witness",))
for label, strict in (("(no flag)", STRICT_OFF), ("--gebra-strict=termination-witness", only_p02)):
    run = verify(fixture.ir, RunPolicy(strict=strict))
    carried = run.outcome_for("termination-witness")
    print(f"{label:34} exit {run.gate.exit_code}  {run.gate.outcome:16} ", end="")
    print(f"P-02 {carried.result}, note {carried.witness.notes[0].severity}")
```

<!-- gebra:output id=blanket-limit-and-strict-mode -->
```text
result    pass, inventory holds form (b) alone, limit 24
note      the witness carries one, and it is the only kind that has a severity:
{
  "kind": "scc-covered-only-by-recursion-limit",
  "severity": "warning",
  "locations": [
    {
      "kind": "scc",
      "nodes": [
        "research_specialist",
        "supervise"
      ],
      "representative_cycle": [
        "research_specialist",
        "supervise"
      ],
      "exhaustive": false,
      "blanket_only": true
    }
  ]
}
promoted  as cycle-without-termination-witness
(no flag)                          exit 0  pass-with-notes  P-02 pass, note warning
--gebra-strict=termination-witness exit 1  fail             P-02 pass, note warning
```

Each region the blanket covers alone gets **its own note**, carrying that region in `locations`
with its representative cycle and one extra field: **`blanket_only`**, `true`. A graph with two
such regions carries two notes, not one note listing two — worth knowing before you write
`witness.notes[0]`. That field is the whole mechanism: under a strict policy naming this
property the same region is promoted under `cycle-without-termination-witness` — the *same*
condition ID, distinguished by that flag — and no new string enters the vocabulary.

**The gate moved and the record did not.** The exit code goes from `0` to `1` between the two
runs; the property still passes, the note is still `severity: warning`, and every field of both
is byte-for-byte what it was. That is §0.2's rule and DEC-11's wording — promotion changes the
gate, never the record — and it is why a strict run needs no second analysis: the report already
carries exactly the regions the strict row reports, flagged.

Practically, this is the setting for a team that declares a limit as a stopgap. Default
profile: the build stays green and the report says which loops are riding on the budget. Strict:
the same report fails the build until each of those loops carries a bound of its own.
[Strict mode](../concepts/what-gebra-checks.md#strict-mode-changes-the-gate-never-the-record)
covers the flag itself, and
[verify and interpret](../tutorials/verify-and-interpret.md#strict-mode-moves-the-gate-never-the-record)
runs it over a whole agent.

## What P-02 reads

The topology, and three declaration slots. The topology is `entry`, `finish`, `nodes[].id` and
each edge's `kind`/`from`/`to`/`condition`/`path_map` — the graph itself, plus the guard strings
form (a) is recognized from. The declarations are `state` (whether a counter key exists and is
an `int`, and whether a variant key exists), `runtime.recursion_limit` (form (b)) and
`nodes[].annotations.variant` (form (c)) — §2.3's list exactly. Of the declared content in a
document, that is all: effects, idempotency keys, determinism claims, declared inputs and
outputs and every other annotation are read by other properties and not by this one.

Two boundaries at the edges of that list. P-02's results are defined over **P-01-clean**
topology (§0.3): a document with a dangling `path_map` target has a graph P-02 cannot trust, so
a run that fails P-01 names P-02 among its best-effort diagnostics — fix the wiring and re-run
before drawing conclusions. And a document using the `ir_version` 1.1 `dynamic` edge kind — a
router whose destinations are computed rather than declared — reaches
[no verdict at all](../tutorials/extract-your-first-ir.md#one-consequence-to-know-before-you-build-on-this),
exit `2`, rather than a P-02 answer.

## What a pass does not claim

A P-02 pass says that a workflow definition **carries a bound**. It says nothing about whether a
run halts — that would be a claim about executing opaque Python, and the boundary is drawn in
the specification itself (T-W §1.1, §7). Four specific things stay on the far side of it, and
each is something a passing witness records rather than checks:

* **Guard truth.** Whether `retry_count < 3` is ever false at runtime is not a question a
  document answers. The recognizer matched declared syntax.
* **Counter progress.** That the counter is actually incremented on each lap is not checked.
  What is checked is that the key exists, is an `int`, and sits in a recognized comparison on a
  guard with a wired escape.
* **Variant decrease.** Form (c) is attested outright: the measure you declared is recorded and
  trusted. Nothing verifies that it strictly decreases.
* **Step-budget adequacy.** Form (b)'s justification is human prose. It is recorded, never
  evaluated.

So the reading of a P-02 pass is "every simple cycle carries a declared bound", and the reading
of a failure is "this cycle carries none" — a statement about the definition in front of you,
not a prediction about a run. A graph that fails P-02 may well stop every time in practice; what
the finding says is that nothing in the document says why. That is the value of the check: a
loop with no declared bound is a loop nobody has had to reason about, and this is where that
shows up — at design time, before anything runs.

Two smaller limits worth keeping straight. **A pass is about cycles, not about the rest of the
graph** — the annotations P-02 trusts are exactly the ones it reads, and a `variant` measure
that is nonsense produces a pass here and is a matter for review, not for this check. And **an
absent census is not a weaker verdict**: `positive-06` above passes with no `cycles` member at
all, because the verdict came from the certificate and the census is a reading aid.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking
a runnable, resolving a hostname or opening a connection all raise. The output blocks are what
those runs printed, and four of them additionally re-check the whole report against the corpus's
own frozen `expected:` block — [executable examples](../contributing/executable-examples.md)
explains the mechanism.

The frozen contract behind this page is PROPERTY-CATALOG-SPEC §2 with the shared envelope of §0
and TERMINATION-WITNESS-SPEC for the witness semantics; the shapes it pins were ratified in
DEC-11 (the inventory-and-certificate witness, the representative-cycle failure, the census cap,
the blanket-limit reading) and amended in DEC-23 (the loop-relative exit test and the near-miss
note). `gebra.verify.properties.termination_witness`, `gebra.verify.guards` and their tests are
where that contract is implemented and pinned in this repository.
