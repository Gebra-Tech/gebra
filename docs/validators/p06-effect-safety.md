# P-06 `effect-safety`

P-06 asks one question about a workflow definition: **can this graph re-execute a node whose
declared effect is externally permanent or cost-bearing, with nothing declared to make the
re-execution safe?**

Two halves make that question decidable over a document. The first is structural: a node sits in a
**retry region** (the graph's re-entry decision puts the lap back on it), in a plain **cycle** (the
lap reaches it through intermediate work), or in neither. The second is declarative: a node in
either region discharges its obligation by declaring an **idempotency key** among the keys it
reads, or a **compensation hook** naming a node of the graph. One combination is refused outright
and without looking at the graph at all — `irreversible` together with a bare, keyless
`idempotent`, which is a safety claim gebra can tie to nothing.

Every P-06 finding is **DEFENSIBLE-A**: the effect, idempotency and compensation annotations are
*declared*, and their truthfulness is trusted the way a type annotation is (§6.2). Of the five
properties this release implements, P-06 is the only one whose **failure records** do not all carry
the same severity — the forbidden combination is FATAL, and an unprotected effect in either region
is ERROR. Both fail the gate; only FATAL additionally suppresses snapshot recording for that run
(§0.2). This page is about reading those findings: what the validator checks, what each field of
its witness and its failure record means, and where the claim stops.

!!! note "Section numbers, and where they point"

    `§` references are to **PROPERTY-CATALOG-SPEC** — §6 is its P-06 section, §0 the shared
    report envelope. That is an internal contract document and is not published with this site;
    the numbers are here so a statement can be *checked* against it rather than taken on trust.
    The transcripts are not spec-derived: they are what this release printed.

!!! note "Following along"

    Seven of the nine examples here run over the vendored property-fixture corpus in this
    repository, `tests/fixtures/properties/` — one YAML document per fixture, carrying an IR and
    the verdict the specification expects for it; three write a small IR document by hand, and one
    does both. To run them yourself, clone the repository and put its root on `PYTHONPATH` — the
    corpus is located from `tests.__file__`, so an example works from any directory. Nothing here
    builds or compiles a LangGraph graph: a fixture is data, and the illustrative builder code
    some fixtures carry is an inert string that is never compiled or run.

## What P-06 checks

On P-01-clean topology, P-06 runs over the same **sentinel-augmented, label-expanded** graph P-01,
P-02 and P-04 do: the document's nodes plus the implicit `START` and `END` vertices, with each
`path_map` entry expanded into its own edge and `send` edges carried with their kind intact. (§6.4
Phase 0 writes the expansion sentinel-free; the sentinels come from the graph model this release
shares across the topology-consuming validators, and on P-01-clean topology the two spellings give
the same components, the same anchors and the same regions.) Over that graph, four rules decide
what P-06 reports.

**The trigger set is exactly two tags.** A node raises a P-06 obligation when its declared
`annotations.effect` contains `billable` or `irreversible`. `network`, `external`, `audit` and any
tag you define yourself create **no** obligation — they still ride the `effect` tuples of records
and locations, which carry a node's *full declared set* as evidence context, never as an obligation
source (§6.3). `mixed/09`'s `book_segment` is tagged `["billable", "network"]`; the `billable` is
why it is checked, and the `network` is along for the ride.

**Two region flavors, distinguished by how the lap returns.** A **retry region** is re-entry
*as-is*: a router label points straight back at the node, or at a node from which `send` edges
alone reach it inside the same loop — a `Send` dispatcher and its targets re-run as one
re-dispatch unit — or the node declares a node-local `retry_policy` (§6.4 Phase 3, ratified by
decision record DEC-13). A plain **cycle** is everything else that loops: the lap passes through
intermediate recomputation before reaching the node again. The two carry different condition IDs at
the same severity, and [which one you get](#retry-region-plain-cycle-or-neither) is worth reading if
the distinction surprises you. A node in neither is `acyclic`, and raises no protection obligation
at all.

**Protection is checked for binding, not for presence.** A keyed `idempotent` declaration is
protection only when its key is among the node's declared `input`; a `compensation` hook is
protection only when it names a node that exists. Both halves are checked, both have a corpus
fixture, and [both have their own section](#protection-has-to-bind).

**One combination is refused without reference to the graph.** `irreversible` plus a boolean,
keyless `idempotent` is a design error wherever it sits — a bare "the provider deduplicates" claim
tied to no declared read (decision D-012). That scan is cycle-independent and runs before any cycle
analysis (§6.4 Phase 1), which is why its fixture is deliberately acyclic and why the finding
carries no cycle anchor.

Three things, then, that P-06 can say:

| Condition | What it requires | Condition ID | Anchor |
|---|---|---|---|
| **no unprotected effect where the lap returns as-is** | a `billable` or `irreversible` node in a retry region declares a binding idempotency key or an existing compensation hook | `unprotected-effect-in-retry-region` | the node, with its declared effect set and the anchor cycle when there is one |
| **no unprotected effect on a loop** | the same, for a node inside a plain cycle | `unprotected-effect-in-cycle` | the node, its declared effect set and the anchor cycle |
| **no irreversible effect claiming keyless idempotence** | a node tagged `irreversible` does not also declare a bare boolean `idempotent` — checked with no reference to the graph | `irreversible-with-keyless-idempotent` | the node, with `idempotent: keyless` as evidence |

Those three strings are the whole P-06 vocabulary. They are in the frozen condition-ID registry and
emittable by this release (§0.4) — a validator may not emit a string the registry does not hold, and
[what gebra checks](../concepts/what-gebra-checks.md#the-diagnostic-vocabulary-is-frozen) explains
why that matters downstream.

## A pass carries a protection ledger

A passing property does not return a bit. It returns a **witness**: structured, re-checkable
evidence, never prose (§0.3). P-06's is a ledger of the trigger-tagged nodes and how each one is
protected, in the form pinned by decision record DEC-11. The fixture below is the booking-retry
classic in its sanctioned form.

<!-- gebra:example id=a-pass-and-its-protection-ledger -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "effect-safety"

fixture = load_fixture(CORPUS / "positive-01-keyed-idempotent-billable-retry.yaml")
report = run_property("effect-safety", fixture.ir)
tagged = {
    node.id: list(node.annotations.effect)
    for node in fixture.ir.nodes
    if node.annotations and node.annotations.effect
}

print(f"fixture   {fixture.fixture_id}")
print(f"graph     {len(fixture.ir.nodes)} nodes, {len(fixture.ir.edges)} authored edges")
print(f"declared  effect tags: {tagged}")
print(f"result    {report.result} — the failure field is {report.failure}")
print("witness   serialized in the report profile:")
print(to_json(report.witness))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")
```

<!-- gebra:output id=a-pass-and-its-protection-ledger -->
```text
fixture   effect-safety/positive-01-keyed-idempotent-billable-retry.yaml
graph     4 nodes, 3 authored edges
declared  effect tags: {'book_hotel': ['billable']}
result    pass — the failure field is None
witness   serialized in the report profile:
{
  "kind": "effect-safety",
  "cycles": [
    [
      "book_hotel",
      "verify_hold"
    ]
  ],
  "effects": [
    {
      "node": "book_hotel",
      "effect": [
        "billable"
      ],
      "region": "retry",
      "cycle": [
        "book_hotel",
        "verify_hold"
      ],
      "protection": "idempotency_key",
      "key": "hotel_offer_id"
    }
  ]
}
equals the fixture's own expected block: True
```

`plan_stay` routes to `book_hotel`, which places the hold; `verify_hold` routes back to it on
failure and forward to `send_confirmation` otherwise. The hold is declared `billable`, and the node
declares `@gebra.idempotent(key="hotel_offer_id")` — a key it also declares it reads.

**`kind`** is the discriminator. The envelope's witness type is a union with one member per
property, and every consumer reads `kind` before anything else (§0.3).

**`cycles` says where the loops are, without enumerating them.** One entry per non-trivial strongly
connected component, each a single deterministic simple cycle through that component's least node
id, rotated so its least id comes first. It is a map of the re-executing regions of the graph, and
it is deliberately *not* a census: P-06 needs region membership plus one anchor, so it never
inherits P-02's cycle-enumeration cost (§6.5). A component contributes exactly one entry however
many cycles run through it.

**`effects` holds one record per trigger-tagged node**, in node-identifier order — not one per
finding and not one per cycle. A graph with no `billable` or `irreversible` node passes with an
empty list, which is a pass that checked something and found no obligation to discharge.

**`node` and `effect` are the obligation.** `effect` is the node's *full declared set*, so a record
can name tags that are not the reason it is there. The field is set-compared: a report that lists
the same tags in another order is the same value (§6.3).

**`region` is one of three values**, and it decides which question was asked. `retry` and `cycle`
both mean the definition offers a route that reaches the node again, and both demand protection;
`acyclic` means it offers none.

**`cycle` is the anchor**, present exactly when the node lies on one — so it is absent on an
`acyclic` record, and absent on a node whose region comes from a `retry_policy` alone with no loop
in the graph. It is *a* shortest simple cycle through the node inside its component, ties broken
deterministically so a re-run prints the same one; it is a place to look, not the set of laps that
reach the node.

**`protection` is the arm that discharged the obligation**, and `key` or `hook` names what did it.
`idempotency_key` sets `key`; `compensation_hook` sets `hook`; `none_required` sets neither and is
the encoding for an `acyclic` node. When a node declares both a binding key and a valid hook the key
wins — a fixed precedence, not a judgement about which is better (§6.4 Phase 4).

**The last line is the corpus's own claim, re-run.** `models_equivalent` is §0.3's comparison: model
equality, with set comparison on the fields the specification marks order-free. The validator's
output and the fixture's `expected:` block validate into the *same* class, so the frozen example and
the result type cannot drift apart.

!!! note "`run_property` versus `verify()`"

    `run_property` is the single-property dispatch, which is what a page about one validator wants.
    A whole run goes through `verify()`, which additionally derives the gate, answers for all
    thirteen catalog properties, and refuses a document whose `ir_version` this build's validators
    are not defined over — a tool error, exit `2`, no verdict (§0.2).
    [Verify and interpret](../tutorials/verify-and-interpret.md) works through a full run.

## A failure names a node, its effects and where it sits

The other half of the envelope. A failing property fills `failure` with a structured record: the
violated **condition ID**, the **location** it was found at, its **severity** and its **claim
class** (§0.3). The fixture below is the corpus's own counterpart to the one above, which its notes
describe as the same topology with the protection added.

<!-- gebra:example id=a-failure-and-its-record -->
```python
from pathlib import Path

import tests
from gebra.ir import IdempotentKey
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property, to_json

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "effect-safety"

fixture = load_fixture(CORPUS / "negative-01-billable-in-unguarded-retry.yaml")
report = run_property("effect-safety", fixture.ir)
failure = report.failure

print(f"fixture   {fixture.fixture_id}")
print(f"result    {report.result} — the witness field is {report.witness}")
print(f"findings  1 primary + {len(failure.co_failures or ())} same-property co-finding")
print("record    serialized in the report profile:")
print(to_json(failure))
expected = fixture.expected_report()
print(f"equals the fixture's own expected block: {models_equivalent(report, expected)}")

COUNTERPARTS = (
    ("positive-01", "positive-01-keyed-idempotent-billable-retry"),
    ("negative-01", "negative-01-billable-in-unguarded-retry"),
)

print("\nthe counterpart pair, effect node by effect node:")
for label, name in COUNTERPARTS:
    ir = load_fixture(CORPUS / f"{name}.yaml").ir
    verdict = run_property("effect-safety", ir).result
    for node in ir.nodes:
        declared = node.annotations
        if not (declared and declared.effect):
            continue
        key = declared.idempotent.key if isinstance(declared.idempotent, IdempotentKey) else None
        hook = declared.compensation.hook if declared.compensation else None
        print(f"  {label}  {node.id:16}effect {list(declared.effect)}")
        print(f"{'':15}reads {list(declared.input or ())}, key {key}, hook {hook} -> {verdict}")
```

<!-- gebra:output id=a-failure-and-its-record -->
```text
fixture   effect-safety/negative-01-billable-in-unguarded-retry.yaml
result    fail — the witness field is None
findings  1 primary + 0 same-property co-finding
record    serialized in the report profile:
{
  "property_condition": "unprotected-effect-in-retry-region",
  "location": {
    "kind": "node",
    "node": "book_flight",
    "effect": [
      "irreversible",
      "billable"
    ],
    "cycle": [
      "book_flight",
      "check_booking"
    ]
  },
  "severity": "error",
  "claim_class": "defensible-a"
}
equals the fixture's own expected block: True

the counterpart pair, effect node by effect node:
  positive-01  book_hotel      effect ['billable']
               reads ['hotel_offer_id'], key hotel_offer_id, hook None -> pass
  negative-01  book_flight     effect ['irreversible', 'billable']
               reads ['flight_id'], key None, hook None -> fail
```

Field by field, because every one of them is load-bearing.

**`property_condition`** is the machine-readable half of the finding: the stable string to key on
rather than parsing prose. It is a registry entry, frozen verbatim (§0.4).

**`location` is typed, and P-06 extends the type.** The envelope has six structural anchors — node,
edge, cycle, SCC, state-key and path — and P-06 uses the **node** anchor, so `kind` is `"node"` and
`node` names the node. Five evidence members ride on top of it. `effect` is always there: the full
declared set, set-compared, exactly as on a witness record. The other four appear only when they
have something to say — `cycle` is the anchor when the node lies on one, `idempotent` is the keyless
marker on the FATAL, `dangling_compensation_hook` carries a hook that names nothing, and `fanout` is
set to `"send"` when the node is the target of a `send` edge, the kind that instantiates a node once
per dispatched payload. `mixed/09` is the fixture that pins the last of those.

**`severity` and `claim_class` are read off the registry, not restated by the validator.** For P-06
that means `error` here and `fatal` on the forbidden combination, both `defensible-a`. Severity is
per condition, so a P-06 report can carry findings of two grades at once, and
[each is graded on its own account](#three-findings-one-record).

**The optional members are absent, not empty.** `co_failures`, `remediation`, `advisories`,
`subsumed_by` and `notes` are all unset on this record, and the report profile drops unset members
rather than writing nulls — so an omitted key and a validator that set nothing produce the same
document. `remediation` is display-only prose and is never parsed; `advisories` carries
cross-property WARNING-class side findings, which no P-06 finding in this release sets, since the
properties whose advisories the corpus records beside P-06 are not implemented here; `notes` carries
structured same-property notes that P-06 never emits, as its own vocabulary has no note kinds; and
`subsumed_by` states that a finding is owned upstream — [a field](#the-p-01-boundary) this release's
validators never set on a record.

**And the counterpart pair is the whole property in four lines.** `book_hotel` and `book_flight` sit
in the same shape of loop and both declare `billable` — `book_flight` declares `irreversible` too,
which changes what is at stake but not which check runs. One of them declares a key it also declares
it reads; the other declares neither key nor hook. That is what the two verdicts turn on. If you are
holding a P-06 finding, the repair is one of exactly three things: declare a key you actually read,
declare a hook that exists, or move the call out of the region.

## Every fixture in the corpus

The corpus's `effect-safety` directory is where the property is pinned: three positives and five
negatives, covering each condition ID, each protection arm and each region. (The specification's own
§6.6 tables three of each; the last two negatives — a `retry_policy` region with no cycle, and a
dangling hook — were authorized separately by decision record DEC-16, and the count here is the
directory's.) Running the validator over all eight at once is the shortest tour of what P-06 can
say.

<!-- gebra:example id=every-fixture-in-the-corpus -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import P06NodeLocation, models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "effect-safety"

EVIDENCE = tuple(
    name for name, field in P06NodeLocation.model_fields.items() if not field.is_required()
)


def render(name, value):
    return f"cycle {' -> '.join(value)}" if name == "cycle" else f"{name} {value}"


agreed = 0
fixtures = [load_fixture(path) for path in sorted(CORPUS.glob("*.yaml"))]
for fixture in fixtures:
    report = run_property("effect-safety", fixture.ir)
    agreed += models_equivalent(report, fixture.expected_report())
    print(fixture.path.stem)
    if report.result == "pass":
        for record in report.witness.effects:
            named = record.key or record.hook
            print(f"    pass  {record.node} [{', '.join(record.effect)}] region {record.region}")
            print(f"          protection {record.protection}{f' {named}' if named else ''}")
    else:
        location = report.failure.location
        set_here = [name for name in EVIDENCE if getattr(location, name)]
        evidence = [render(name, getattr(location, name)) for name in set_here]
        print(f"    fail  {report.failure.property_condition} at {location.node}")
        print(f"          evidence {'; '.join(evidence) or '(the anchor alone)'}")

print(f"\n{agreed} of {len(fixtures)} reports equal the fixture's own expected block")
```

<!-- gebra:output id=every-fixture-in-the-corpus -->
```text
negative-01-billable-in-unguarded-retry
    fail  unprotected-effect-in-retry-region at book_flight
          evidence cycle book_flight -> check_booking
negative-02-irreversible-in-refinement-cycle
    fail  unprotected-effect-in-cycle at submit_change_request
          evidence cycle assess_response -> propose_change -> submit_change_request
negative-03-keyless-idempotent-on-irreversible
    fail  irreversible-with-keyless-idempotent at charge_deposit
          evidence idempotent keyless
negative-04-retry-policy-annotation-no-cycle-unprotected
    fail  unprotected-effect-in-retry-region at capture_payment
          evidence (the anchor alone)
negative-05-dangling-compensation-hook
    fail  unprotected-effect-in-cycle at place_hotel_hold
          evidence cycle place_hotel_hold -> review_hold -> propose_dates; dangling_compensation_hook release_hotel_hold
positive-01-keyed-idempotent-billable-retry
    pass  book_hotel [billable] region retry
          protection idempotency_key hotel_offer_id
positive-02-irreversible-outside-cycle
    pass  charge_card [irreversible, billable] region acyclic
          protection none_required
positive-03-compensated-billable-hold-loop
    pass  place_hotel_hold [billable] region cycle
          protection compensation_hook release_hotel_hold

8 of 8 reports equal the fixture's own expected block
```

Three passes for three different reasons, and five failures for five.

**The three passes are the three ways to be clear.** `positive-01` protects with a key. `positive-03`
protects with a hook — a hold-and-release loop where `release_hotel_hold` sits on the loop-back path
and the annotation names it. `positive-02` is protected by nothing at all: its irreversible charge
sits on the acyclic tail after a polling loop, so the definition offers no route back to it and P-06
records `none_required`. That third one is why the property is a region analysis rather than a
blanket flag on every irreversible effect.

**The five failures split by which half of the check they trip.** `negative-01` and `negative-02`
are both region-and-no-protection, and the condition they carry differs by the flavor of region.
`negative-03` is the forbidden combination, on a graph with no cycle in it anywhere. `negative-04`
and `negative-05` are the two gap-fixture cases: a retry region with no loop to anchor on, and a
hook that names nothing.

**Note what the evidence line does and does not carry.** The example asks the location model which
of its members are optional rather than listing them, so the line enumerates every evidence field
P-06 can set and prints the ones actually set. `negative-04` reports "the anchor alone" because
there is no cycle to name; `negative-05` carries the unbound hook name so you can go and look for
the node that used to be there. No finding here sets `fanout`, because no fixture in this directory
uses a `send` edge — `mixed/09` does, and it is
[in the next section](#retry-region-plain-cycle-or-neither).

The last line matters as much as the rest: every one of the eight reports equals the fixture's own
`expected:` block. These are frozen examples the validator is held to in CI, not illustrations
written beside it.

## Retry region, plain cycle, or neither

The distinction between the two ERROR conditions is the subtlest thing on this page, and it is worth
getting right because it tells you what kind of re-execution you are looking at. A retry region is
re-entry **as-is** — the lap comes back to the node with nothing recomputed in between. A plain cycle
is refinement — something is redone before the node is reached again. Four cases pin the rule.

<!-- gebra:example id=retry-region-plain-cycle-or-neither -->
```python
from pathlib import Path

import tests
from gebra.testing import load_fixture
from gebra.verify import run_property

PROPERTIES = Path(tests.__file__).parent / "fixtures" / "properties"

CASES = (
    ("negative-01", "effect-safety/negative-01-billable-in-unguarded-retry"),
    ("negative-02", "effect-safety/negative-02-irreversible-in-refinement-cycle"),
    ("mixed/09", "mixed/09-send-fanout-billable-no-idempotency-in-retry"),
    ("negative-04", "effect-safety/negative-04-retry-policy-annotation-no-cycle-unprotected"),
)

for label, relative in CASES:
    fixture = load_fixture(PROPERTIES / f"{relative}.yaml")
    report = run_property("effect-safety", fixture.ir)
    location = report.failure.location
    node = next(n for n in fixture.ir.nodes if n.id == location.node)
    loop = set(location.cycle or ())

    reentry = [
        f"{edge.from_} -{name}-> {target}"
        for edge in fixture.ir.edges
        for name, target in (getattr(edge, "path_map", None) or {}).items()
        if target in loop
    ]
    sends = [
        f"{edge.from_} -> {edge.to}"
        for edge in fixture.ir.edges
        if edge.kind == "send" and {edge.from_, edge.to} <= loop
    ]

    anchor = " -> ".join(location.cycle) if location.cycle else "absent"
    print(f"{label:12} {location.node} -> {report.failure.property_condition}")
    print(f"    anchor cycle          {anchor}")
    print(f"    labels back into it   {'; '.join(reentry) or 'none'}")
    print(f"    send edges inside it  {'; '.join(sends) or 'none'}")
    print(f"    retry_policy on node  {'declared' if node.annotations.retry_policy else 'none'}")
```

<!-- gebra:output id=retry-region-plain-cycle-or-neither -->
```text
negative-01  book_flight -> unprotected-effect-in-retry-region
    anchor cycle          book_flight -> check_booking
    labels back into it   check_booking -retry-> book_flight
    send edges inside it  none
    retry_policy on node  none
negative-02  submit_change_request -> unprotected-effect-in-cycle
    anchor cycle          assess_response -> propose_change -> submit_change_request
    labels back into it   assess_response -revise-> propose_change
    send edges inside it  none
    retry_policy on node  none
mixed/09     book_segment -> unprotected-effect-in-retry-region
    anchor cycle          book_segment -> check_bookings -> dispatch_bookings
    labels back into it   check_bookings -retry-> dispatch_bookings
    send edges inside it  dispatch_bookings -> book_segment
    retry_policy on node  none
negative-04  capture_payment -> unprotected-effect-in-retry-region
    anchor cycle          absent
    labels back into it   none
    send edges inside it  none
    retry_policy on node  declared
```

Read the third line of each block and the rule falls out.

**`negative-01`: the router points at the effect node.** `check_booking -retry-> book_flight` lands
on `book_flight` itself, so the route back reaches the effect node with nothing recomputed in
between. That is re-entry as-is, and the condition is the retry-region one.

**`negative-02`: the router points somewhere else on the loop.** `assess_response -revise->
propose_change` lands on the drafting node, so the lap passes through it before reaching
`submit_change_request` again. The effect node is in the loop but is not what the decision
re-enters, so this is a plain cycle. The finding is no less serious — nothing in the definition
stands between a second lap and a second filed change order — but it describes a different shape
of defect.

**`mixed/09`: one `send` hop past the re-entry target still counts.** The label lands on
`dispatch_bookings`, and `dispatch_bookings -> book_segment` is a `send` edge, so the dispatcher and
its targets re-run as one re-dispatch unit and `book_segment` is inside the retry region. Restricting
that reach to `send` edges is exactly what keeps `negative-02` a plain cycle: an intervening
`normal` edge is refinement carriage, not retry. Both halves of the rule are load-bearing, and both
are ratified verbatim by decision record DEC-13.

**`negative-04`: a retry region with no loop at all.** `capture_payment` declares a node-local
`retry_policy` — a declaration of re-execution that does not depend on the graph routing back — so
the region is `retry` and the record carries no cycle anchor, because there is no cycle to anchor
on. Only presence of the annotation is read; `max_attempts` and `retry_on` are not.

!!! note "`mixed/` fixtures answer for more than one property"

    The `expected:` block of a `mixed/` fixture records the whole-run verdict across several
    properties, and `mixed/09`'s names a P-07 co-failure and a P-09 advisory beside the P-06
    primary. Neither of those properties is implemented in this release, so a P-06-scoped run
    answers for P-06 alone and is not the same object as that block. That is why the equality check
    in the previous section covers the eight single-property fixtures and not these.

## Protection has to bind

The objection every reader of a P-06 finding has is "but I *did* declare idempotency". Two fixtures
answer it, and they are the reason the check is about binding rather than presence: a key that names
something the node does not read cannot stabilise anything, and a hook that names no node cannot
undo anything.

<!-- gebra:example id=protection-has-to-bind -->
```python
from pathlib import Path

import tests
from gebra.ir import IdempotentKey
from gebra.testing import load_fixture
from gebra.verify import run_property

PROPERTIES = Path(tests.__file__).parent / "fixtures" / "properties"

CASES = (
    ("positive-01", "effect-safety/positive-01-keyed-idempotent-billable-retry", "book_hotel"),
    ("mixed/06", "mixed/06-irreversible-cycle-idempotency-key-not-read", "issue_refund"),
    ("positive-03", "effect-safety/positive-03-compensated-billable-hold-loop", "place_hotel_hold"),
    ("negative-05", "effect-safety/negative-05-dangling-compensation-hook", "place_hotel_hold"),
)

for label, relative, node_id in CASES:
    fixture = load_fixture(PROPERTIES / f"{relative}.yaml")
    report = run_property("effect-safety", fixture.ir)
    declared = next(n for n in fixture.ir.nodes if n.id == node_id).annotations
    node_ids = {n.id for n in fixture.ir.nodes}

    print(f"{label:12} {node_id}")
    if isinstance(declared.idempotent, IdempotentKey):
        key = declared.idempotent.key
        reads = list(declared.input or ())
        print(f"    declares     idempotent key {key!r}; declared reads {reads}")
        print(f"    binds?       {key!r} among the declared reads: {key in reads}")
    else:
        hook = declared.compensation.hook
        print(f"    declares     compensation hook {hook!r}")
        print(f"    binds?       {hook!r} is a node of this graph: {hook in node_ids}")
    if report.result == "pass":
        record = next(r for r in report.witness.effects if r.node == node_id)
        print(f"    verdict      pass, protection {record.protection}")
    else:
        location = report.failure.location
        dangling = location.dangling_compensation_hook or "absent"
        print(f"    verdict      fail, {report.failure.property_condition}")
        print(f"    evidence     dangling_compensation_hook {dangling}")
```

<!-- gebra:output id=protection-has-to-bind -->
```text
positive-01  book_hotel
    declares     idempotent key 'hotel_offer_id'; declared reads ['hotel_offer_id']
    binds?       'hotel_offer_id' among the declared reads: True
    verdict      pass, protection idempotency_key
mixed/06     issue_refund
    declares     idempotent key 'refund_ref'; declared reads ['order_id', 'amount']
    binds?       'refund_ref' among the declared reads: False
    verdict      fail, unprotected-effect-in-retry-region
    evidence     dangling_compensation_hook absent
positive-03  place_hotel_hold
    declares     compensation hook 'release_hotel_hold'
    binds?       'release_hotel_hold' is a node of this graph: True
    verdict      pass, protection compensation_hook
negative-05  place_hotel_hold
    declares     compensation hook 'release_hotel_hold'
    binds?       'release_hotel_hold' is a node of this graph: False
    verdict      fail, unprotected-effect-in-cycle
    evidence     dangling_compensation_hook release_hotel_hold
```

**A key must be among the node's declared reads.** `mixed/06`'s `issue_refund` declares
`@gebra.idempotent(key="refund_ref")`, and `refund_ref` is the node's own declared *output* — a
reference the node says it produces rather than one it says it consumes. A key the node does not
declare it reads ties an attempt to nothing that preceded it. The side condition is mechanical: the
key must appear in `input`. It is checked against the declared reads and never against the declared
writes, which is what makes it a real test rather than a spelling check.

**A hook must name a node of the graph.** `negative-05` is `positive-03`'s date-negotiation loop
after a careless refactor: the release node was dropped from the graph and the annotation still
names it. A hook naming nothing is not protection (decision record DEC-05 D7, confirmed by
DEC-13), so the node falls through to the ordinary unprotected-effect condition and the unbound name
rides along as `dangling_compensation_hook`. No new condition ID is minted for it — the §0.4 registry
stays closed, and the evidence field is how the finding tells you *which* kind of gap it is.

**Note where the diagnostic for the bad key itself lives.** P-06 owns effect-class protection; the
placement of an idempotency key is P-07 `retry-coherence`'s question, and its condition ID is held
RESERVED in the registry — registered, not emittable by this release (§0.4). So a node with a key
that does not bind reports as unprotected, and that is P-06's finding, made on P-06's own account.
`mixed/06`'s own `expected:` block packages the same P-06 finding as a co-failure under P-07's
primary — the corpus's picture of a run in which both properties answer, which is not the run this
release performs.

## The FATAL is decided without the graph

`irreversible` plus a keyless `idempotent` is the one thing P-06 refuses outright. The scan for it
runs before any cycle analysis, which has two visible consequences: the finding fires on graphs with
no loop in them, and it carries no cycle anchor even when there is one.

<!-- gebra:example id=the-fatal-is-decided-without-the-graph -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import WorkflowIR, load_json
from gebra.testing import load_fixture
from gebra.verify import run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "effect-safety"

fixture = load_fixture(CORPUS / "negative-03-keyless-idempotent-on-irreversible.yaml")
failure = run_property("effect-safety", fixture.ir).failure
print(f"negative-03  {failure.location.node}, on a deliberately acyclic graph")
print(f"    condition   {failure.property_condition}")
print(f"    severity    {failure.severity}")
print(f"    evidence    idempotent {failure.location.idempotent}")
print(f"    cycle       {failure.location.cycle or 'absent'}")

document = {
    "ir_version": "1.0",
    "entry": ["quote_rental"],
    "finish": ["issue_receipt"],
    "state": {
        "rental_quote": {"type": "str", "optional": True},
        "deposit_ref": "str",
        "charge_status": "str",
        "receipt": "str",
        "attempt": {"type": "int", "reducer": "operator.add"},
    },
    "nodes": [
        {"id": "quote_rental", "annotations": {"pure": True, "input": ["rental_quote"]}},
        {
            "id": "charge_deposit",
            "annotations": {
                "effect": ["irreversible", "billable"],
                "idempotent": True,
                "input": ["rental_quote"],
                "output": ["deposit_ref", "charge_status", "attempt"],
            },
        },
        {
            "id": "check_charge",
            "annotations": {"pure": True, "input": ["charge_status", "attempt"]},
        },
        {"id": "issue_receipt", "annotations": {"input": ["deposit_ref"], "output": ["receipt"]}},
    ],
    "edges": [
        {"from": "quote_rental", "to": "charge_deposit"},
        {"from": "charge_deposit", "to": "check_charge"},
        {
            "from": "check_charge",
            "kind": "conditional",
            "condition": "'retry' if charge_status == 'failed' and attempt < 3 else 'ok'",
            "path_map": {"retry": "charge_deposit", "ok": "issue_receipt"},
        },
    ],
}

print("\nthe same node, this time inside a retry loop:")
for label, keyless in (("idempotent: true kept", True), ("idempotent removed", False)):
    nodes = json.loads(json.dumps(document["nodes"]))
    if not keyless:
        next(n for n in nodes if n["id"] == "charge_deposit")["annotations"].pop("idempotent")
    report = run_property(
        "effect-safety", load_json(WorkflowIR, json.dumps({**document, "nodes": nodes}))
    )
    primary = report.failure
    anchor = " -> ".join(primary.location.cycle) if primary.location.cycle else "absent"
    print(f"    {label:24}{report.result}, {1 + len(primary.co_failures or ())} finding")
    print(f"{'':28}{primary.property_condition} ({primary.severity}), cycle {anchor}")
```

<!-- gebra:output id=the-fatal-is-decided-without-the-graph -->
```text
negative-03  charge_deposit, on a deliberately acyclic graph
    condition   irreversible-with-keyless-idempotent
    severity    fatal
    evidence    idempotent keyless
    cycle       absent

the same node, this time inside a retry loop:
    idempotent: true kept   fail, 1 finding
                            irreversible-with-keyless-idempotent (fatal), cycle absent
    idempotent removed      fail, 1 finding
                            unprotected-effect-in-retry-region (error), cycle charge_deposit -> check_charge
```

Three readings follow.

**The boolean form is the only one that fires.** `idempotent: true` is a claim tied to nothing;
`idempotent: {key: …}` is a claim pinned to a named key, and whether that key *binds* is the other
check's question entirely. Writing `@gebra.idempotent` with no key on an `irreversible` node is the
error; writing it with one is not.

**A FATAL on a looping node is still anchor-free.** The `idempotent: true kept` row names no cycle
even though `charge_deposit` sits in one, because the scan that produced it never consults the graph.
If you are looking for the loop, it is in the graph, not in this record.

**One node, one report.** In that same row the node is *both* in a retry region *and* unprotected,
which would ordinarily be an ERROR — and no second finding is emitted. The FATAL owns the root cause,
and a second record would report the consequence of a combination the first one rejects outright
(decision record DEC-05 D2). Remove the keyless declaration and the ERROR appears, with its anchor,
because now that is the whole of what is wrong.

## Three findings, one record

One property reports once. When several nodes fail, the deterministically-first finding fills
`failure` and every further same-property finding rides `co_failures`, so nothing is dropped (§0.3).
No corpus fixture violates more than one P-06 obligation, so here is a small document written by hand
that violates three — a booking flow that charges on the way in and settles on the way out.

<!-- gebra:example id=three-findings-one-record -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import run_property, to_json

document = {
    "ir_version": "1.0",
    "entry": ["intake"],
    "finish": ["settle"],
    "state": {
        "booking_request": {"type": "str", "optional": True},
        "room_ref": "str",
        "invoice_ref": "str",
        "review": "str",
        "refund_ref": "str",
        "round": {"type": "int", "reducer": "operator.add"},
    },
    "nodes": [
        {"id": "intake", "annotations": {"input": ["booking_request"], "output": ["review"]}},
        {
            "id": "book_room",
            "annotations": {
                "effect": ["billable"],
                "input": ["booking_request"],
                "output": ["room_ref"],
            },
        },
        {
            "id": "send_invoice",
            "annotations": {
                "effect": ["billable"],
                "input": ["room_ref"],
                "output": ["invoice_ref"],
            },
        },
        {
            "id": "confirm",
            "annotations": {"input": ["invoice_ref", "round"], "output": ["review", "round"]},
        },
        {
            "id": "settle",
            "annotations": {
                "effect": ["irreversible", "billable"],
                "idempotent": True,
                "input": ["invoice_ref"],
                "output": ["refund_ref"],
            },
        },
    ],
    "edges": [
        {"from": "intake", "to": "book_room"},
        {"from": "book_room", "to": "send_invoice"},
        {"from": "send_invoice", "to": "confirm"},
        {
            "from": "confirm",
            "kind": "conditional",
            "condition": "'again' if review == 'changed' and round < 2 else 'done'",
            "path_map": {"again": "book_room", "done": "settle"},
        },
    ],
}

report = run_property("effect-safety", load_json(WorkflowIR, json.dumps(document)))
failure = report.failure
print(f"result    {report.result}")
print(f"findings  1 primary + {len(failure.co_failures)} same-property co-findings")
print(to_json(failure))
```

<!-- gebra:output id=three-findings-one-record -->
```text
result    fail
findings  1 primary + 2 same-property co-findings
{
  "property_condition": "irreversible-with-keyless-idempotent",
  "location": {
    "kind": "node",
    "node": "settle",
    "effect": [
      "irreversible",
      "billable"
    ],
    "idempotent": "keyless"
  },
  "severity": "fatal",
  "claim_class": "defensible-a",
  "co_failures": [
    {
      "property": "effect-safety",
      "property_condition": "unprotected-effect-in-retry-region",
      "location": {
        "kind": "node",
        "node": "book_room",
        "effect": [
          "billable"
        ],
        "cycle": [
          "book_room",
          "send_invoice",
          "confirm"
        ]
      },
      "severity": "error",
      "claim_class": "defensible-a"
    },
    {
      "property": "effect-safety",
      "property_condition": "unprotected-effect-in-cycle",
      "location": {
        "kind": "node",
        "node": "send_invoice",
        "effect": [
          "billable"
        ],
        "cycle": [
          "book_room",
          "send_invoice",
          "confirm"
        ]
      },
      "severity": "error",
      "claim_class": "defensible-a"
    }
  ]
}
```

All three condition IDs, in one record, on one graph.

**Which finding is primary is determined, not chosen.** The order is severity first — FATAL before
ERROR — then the node identifier in UTF-16 code-unit order, then the condition ID (§6.4 Phase 5). By
node identifier alone `book_room` would lead; severity puts `settle` in front of it, and the two
ERRORs then follow in identifier order. If you triage by reading the primary only, you are reading
the most severe finding, which is the point of ordering it that way.

**A co-failure carries its own property, condition, location, severity and claim class** — enough to
act on, and each graded on its own account rather than inheriting the primary's. All three findings
here are `effect-safety`'s: same-property co-findings name their own property, which is what
distinguishes them from the cross-property advisories that share the field's neighbourhood.

**The two ERRORs differ, and the difference is the loop.** `book_room` is where the router lands, so
it is a retry region; `send_invoice` is reached only after the room is re-booked, so it is a plain
cycle. Same loop, same missing declaration, two conditions — which is the distinction from
[the region section](#retry-region-plain-cycle-or-neither) showing up inside a single record.

## The P-01 boundary

**P-06's results are defined over P-01-clean topology** (§0.3), and on a graph that fails P-01 its
answer is a best-effort diagnostic rather than a verdict. That is not a formality here, because
P-06's own degradation convention is to **skip** an edge whose target does not resolve — and a
skipped edge can be the edge that closed the loop.

<!-- gebra:example id=a-pass-on-a-broken-graph -->
```python
import json

from gebra.ir import WorkflowIR, load_json
from gebra.verify import verify

document = {
    "ir_version": "1.0",
    "entry": ["plan_trip"],
    "finish": ["send_confirmation"],
    "state": {
        "flight_id": {"type": "str", "optional": True},
        "booking_ref": "str",
        "booking_status": "str",
        "confirmation": "str",
        "retry_count": {"type": "int", "reducer": "operator.add"},
    },
    "nodes": [
        {"id": "plan_trip", "annotations": {"pure": True, "input": ["flight_id"]}},
        {
            "id": "book_flight",
            "annotations": {
                "effect": ["irreversible", "billable"],
                "input": ["flight_id"],
                "output": ["booking_ref", "booking_status", "retry_count"],
            },
        },
        {
            "id": "check_booking",
            "annotations": {"pure": True, "input": ["booking_status", "retry_count"]},
        },
        {
            "id": "send_confirmation",
            "annotations": {"input": ["booking_ref"], "output": ["confirmation"]},
        },
    ],
    "edges": [
        {"from": "plan_trip", "to": "book_flight"},
        {"from": "book_flight", "to": "check_booking"},
        {
            "from": "check_booking",
            "kind": "conditional",
            "condition": "'retry' if booking_status == 'failed' and retry_count < 2 else 'ok'",
            "path_map": {"retry": "book_flight", "ok": "send_confirmation"},
        },
    ],
}

for target in ("book_flght", "book_flight"):
    edges = json.loads(json.dumps(document["edges"]))
    next(e for e in edges if e.get("kind") == "conditional")["path_map"]["retry"] = target
    report = verify(load_json(WorkflowIR, json.dumps({**document, "edges": edges})))

    print(f"the retry label points at {target!r}")
    print(f"    gate         {report.gate.outcome}, exit {report.gate.exit_code}")
    print(f"    best_effort  {list(report.best_effort)}")
    for slug in ("graph-well-formed", "effect-safety"):
        outcome = report.outcome_for(slug)
        if outcome.result == "fail":
            print(f"    {slug:19}fail  {outcome.failure.property_condition}")
        elif slug == "effect-safety":
            for record in outcome.witness.effects:
                detail = f"{record.node} region {record.region}, {record.protection}"
                print(f"    {slug:19}pass  {detail}")
        else:
            print(f"    {slug:19}pass")
```

<!-- gebra:output id=a-pass-on-a-broken-graph -->
```text
the retry label points at 'book_flght'
    gate         fail, exit 1
    best_effort  ['termination-witness', 'dataflow-completeness', 'effect-safety']
    graph-well-formed  fail  path-map-target-undefined
    effect-safety      pass  book_flight region acyclic, none_required
the retry label points at 'book_flight'
    gate         fail, exit 1
    best_effort  []
    graph-well-formed  pass
    effect-safety      fail  unprotected-effect-in-retry-region
```

One typo in a `path_map` label, and P-06 hands back a clean protection ledger. The reason is exactly
the documented convention: the label resolves to no node, P-06 drops the edge rather than carrying a
placeholder for it, and with that edge gone `book_flight` lies on no cycle and needs no protection.
Fix the label — restoring the loop the author meant to wire — and the same document produces the
ERROR.

A run says so rather than leaving you to remember it: `best_effort` lists the properties whose
answers are diagnostics on this topology, `effect-safety` among them, and the gate fails on P-01's
own FATAL regardless of what they say. The reading is short: **a P-06 pass on a run that failed
P-01 is not a pass.** Fix the wiring, re-run, and read the report you get then.

Two smaller notes on the same boundary. Each topology-consuming property degrades in its *own*
documented way — P-04 carries the missing vertex as a contract-free placeholder where P-06 drops
the edge — and §0.3 is explicit that cross-validator agreement on ill-formed input is not promised,
so two properties disagreeing about a broken graph is licensed rather than a defect. And
`subsumed_by` is the envelope's field for saying on a record that a finding is owned upstream
(`subsumed_by: "P-01"`); **no validator in this release sets it**, so the qualification a run
actually hands you is the `best_effort` list above, not a flag on the record. Do not write a
consumer that waits for one.

## What P-06 reads

`nodes[].id`; five annotation slots — `effect`, `idempotent`, `compensation`, `retry_policy` and
`input` (for the key side condition); and each edge's `from`/`to`/`kind`/`path_map`. That is the
whole list. In particular the state schema is **not** read at all, and neither is
`annotations.pure`, which was delisted as a P-06 reader by decision record DEC-13.

One difference between that list and the specification's is worth naming rather than leaving for a
reader to trip over: §6.3's field enumeration also includes each edge's `condition`, and **no phase
of the decision procedure consumes it** — §6.4 keys the region rule on edge kind, and §6.5's cost
argument never reaches the guard. This release does not read it for any P-06 purpose either, and
the round trip below is where that shows. Worth checking rather than believing:

<!-- gebra:example id=what-p06-reads -->
```python
import json
from pathlib import Path

import tests
from gebra.ir import WorkflowIR, dump_json, load_json
from gebra.testing import load_fixture
from gebra.verify import models_equivalent, run_property

CORPUS = Path(tests.__file__).parent / "fixtures" / "properties" / "effect-safety"

fixture = load_fixture(CORPUS / "positive-01-keyed-idempotent-billable-retry.yaml")
document = json.loads(dump_json(fixture.ir))

changed = [f'every state field rewritten to "object" ({len(document["state"])} keys)']
for key in document["state"]:
    document["state"][key] = {"type": "object"}
for node in document["nodes"]:
    for member in ("pure", "output", "deterministic", "variant"):
        if node["annotations"].pop(member, None) is not None:
            changed.append(f"{node['id']}.annotations.{member}")
for edge in document["edges"]:
    if edge.pop("condition", None) is not None:
        changed.append(f"{edge['from']}.condition (the router expression)")

before = run_property("effect-safety", fixture.ir)
after = run_property("effect-safety", load_json(WorkflowIR, json.dumps(document)))

print(f"changed   {len(changed)} things P-06 does not read:")
for member in changed:
    print(f"            {member}")
print("kept      nodes[].id, annotations.effect/idempotent/compensation/retry_policy/input,")
print("          and every edge's from/to/kind/path_map")
print(f"verdicts  {before.result} before, {after.result} after")
print(f"reports equal: {models_equivalent(before, after)}")

narrowed = json.loads(json.dumps(document))
for node in narrowed["nodes"]:
    if node["id"] == "book_hotel":
        node["annotations"]["input"] = []
verdict = run_property("effect-safety", load_json(WorkflowIR, json.dumps(narrowed)))
print(f"\nnow drop book_hotel's declared input, keeping its idempotency key: {verdict.result}")
print(f"    {verdict.failure.property_condition} at {verdict.failure.location.node}")
```

<!-- gebra:output id=what-p06-reads -->
```text
changed   8 things P-06 does not read:
            every state field rewritten to "object" (5 keys)
            plan_stay.annotations.pure
            plan_stay.annotations.output
            book_hotel.annotations.output
            verify_hold.annotations.pure
            verify_hold.annotations.output
            send_confirmation.annotations.output
            verify_hold.condition (the router expression)
kept      nodes[].id, annotations.effect/idempotent/compensation/retry_policy/input,
          and every edge's from/to/kind/path_map
verdicts  pass before, pass after
reports equal: True

now drop book_hotel's declared input, keeping its idempotency key: fail
    unprotected-effect-in-retry-region at book_hotel
```

Every declared type and reducer replaced, every purity declaration dropped, every declared write
removed, the router's condition string deleted — and the report is the same value, anchor cycle and
idempotency key included. Four things follow.

**The state schema is not P-06's business.** This property asks where effects sit and what is
declared about them; what the channels hold, and whether a reducer makes concurrent writes
well-defined, belong to other properties. The cost of the check is independent of the schema's size
for the same reason (§6.5).

**The router's guard string is never evaluated, and no P-06 decision reads it.** This is the
enumeration gap above, demonstrated: the region rule keys on edge *kind* — is this a conditional
label-edge, is this a `send` edge — and not on what the condition says. A guard that "can never fire
in practice" is still an edge, and P-06 will still count the loop it closes.

**`pure` is not read either.** Decision record DEC-13 delisted it as a P-06 reader, and the module
follows: a node declaring both `pure: true` and a `billable` tag is a contradiction, but it is not
P-06's to catch, and P-06's answer does not change when it is present.

**But `input` is read, and the last line shows the boundary.** Drop `book_hotel`'s declared reads
while leaving its idempotency key exactly as it was, and the same graph fails: the key no longer
appears among the reads, so it no longer binds, so the node is unprotected. This is the same check
`mixed/06` fails, arrived at from the other direction — and it is a good reason to look at the
extraction warnings before rewiring a graph, since an `input` slot that was inferred or defaulted
rather than declared can produce this finding on a node that is genuinely safe.
[Contracts and annotations](../tutorials/contracts-and-annotations.md) is where those declarations
come from, in code or in a sidecar.

## What a pass does not claim

A P-06 pass says that every node declaring a trigger effect either lies outside every re-executing
region of the definition, or declares a protection that binds — a statement about the declarations
in a document and the shape of its wiring, and about nothing else. Six things stay on the far side
of that line.

* **A declared effect is what P-06 sees, and an undeclared one is invisible.** A node that charges a
  card and carries no `effect` annotation raises no obligation and appears in no record. The pass
  says nothing about it, because nothing in the document said there was anything to say.
* **A declared idempotency key is not idempotent behaviour.** gebra records that a key was declared
  and that it names a key the node declares it reads. Whether the provider deduplicates on it, and
  whether the value is stable across laps, are runtime facts gebra never observes — the whole of the
  `-A` in DEFENSIBLE-A.
* **A declared compensation hook is not a compensation.** The check is that the hook names a node of
  the graph. That the node undoes the effect, that it runs before the next attempt, and that it
  succeeds when it runs are all outside what a definition can settle.
* **`none_required` is about this definition's topology, not about how often the node runs.** A node
  the graph never routes back to can still be re-executed by something the document does not
  describe: a caller loop, an external scheduler, a runtime retry a `retry_policy` annotation does
  not record. What the record claims is that *this graph* offers no route back.
* **A pass is scoped to P-01-clean topology.** The [boundary section](#the-p-01-boundary) above is
  the whole of that story, and it is the one qualification that can turn a clean-looking ledger into
  no information at all.
* **The neighbouring questions belong to properties this release does not implement.** Whether a
  re-enterable node is coherently pure or idempotent is P-07's; whether concurrent writers are safe
  is P-09's. Neither is implemented here, and a run answers for both with a structured
  not-implemented marker rather than a silent pass. One known contract gap between the two is
  recorded in the specification rather than papered over: P-07's letter asks a re-enterable node to
  be pure or idempotent and does not recognise a compensation hook, so P-06's hook arm and P-07's
  rule do not agree about a node like `positive-03`'s (decision record DEC-05 D7). Nothing about a
  run today turns on it, and the disagreement is filed rather than resolved.

So the reading of a P-06 pass is "every declared effect this graph can reach again carries a
protection declaration that binds", and the reading of a failure is "here is a node this graph can
reach again, and here is what it does not declare" — a statement about the definition in front of
you, not
a prediction about a run. That is the value of the check: double-charging is the defect nobody can
reproduce on demand, and a region analysis names the node where nothing declared stands between one
attempt and the next, before anything runs.

One further limit worth keeping straight: a document using the `ir_version` 1.1 `dynamic` edge kind —
a router whose destinations are computed rather than declared — reaches
[no verdict at all](../tutorials/extract-your-first-ir.md#one-consequence-to-know-before-you-build-on-this),
exit `2`, rather than a P-06 answer.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking a
runnable, resolving a hostname or opening a connection all raise. The output blocks are what those
runs printed, and three of them additionally re-check the whole report against the corpus's own
frozen `expected:` block — [executable examples](../contributing/executable-examples.md) explains
the mechanism.

The frozen contract behind this page is PROPERTY-CATALOG-SPEC §6 with the shared envelope of §0; the
shapes it pins were ratified in decision records DEC-11 (the witness and failure forms) and DEC-05
(compensation as protection, and one root cause one report), with DEC-13 ratifying the retry-region
rule and the handling of a dangling hook, and DEC-16 authorizing the two gap fixtures.
`gebra.verify.properties.effect_safety` and its tests are where that contract is implemented and
pinned in this repository. The other written explainers are
[P-01 `graph-well-formed`](p01-graph-well-formed.md),
[P-02 `termination-witness`](p02-termination-witness.md),
[P-04 `dataflow-completeness`](p04-dataflow-completeness.md) and
[P-08 `determinism-replay`](p08-determinism-replay.md).
