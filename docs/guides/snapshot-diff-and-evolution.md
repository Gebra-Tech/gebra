# Snapshot, diff and evolution

An agent definition changes every week: a node is added, a state key is retired, a retry
policy is tightened, a prompt is rewritten. This page is about keeping a record of those
changes and reading it — the `.gebra/` store, the V.S.F.E label a stored version carries, the
`graph_version` digest underneath it, and the structural diff between any two versions.

It is written to answer the question a reviewer actually has in front of a pull request:
**what moved, and is this change safe to ship?** gebra answers the first half exactly and
declines the second: classifying an evolution step as safe or breaking is property P-12
`evolution-safety`, which is outside this release's scope, and every diff says so in the slot
where that verdict would go. So the reviewer makes the call, and the point of this page is to
show what the report gives them to make it with — including the two changes below that carry
the *same* label bump and could not be more different.

!!! note "Following along"

    Every transcript here is produced by the code block above it, executed in CI. The agent
    is `tests/sample_workflows/travel_booking.py` and its eight-stage evolution in
    `tests/sample_workflows/travel_booking_evolution.py` — the same sequence the acceptance
    scenario evolves. In your repository those imports are your own builders and nothing else
    changes. The examples pin `extracted_at` so a stored timestamp is a function of the
    example rather than of the clock; leave it out and the store records the extraction's own
    instant.

## A snapshot, and where it goes

A snapshot is one workflow's extracted IR plus three envelope fields: the V.S.F.E `version`
label, the `extracted_from` provenance, and the `graph_version` content digest. Recording one
extracts the definition, assigns the label, and writes the file:

<!-- gebra:example id=a-first-snapshot -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows import travel_booking

store = SnapshotStore(Path(".gebra"))
outcome = snapshot(
    travel_booking.build_travel_booking_agent(),
    store=store,
    source="travel_booking:build_travel_booking_agent",
    extracted_at=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
)

print("action        ", outcome.action.value)
print("version       ", outcome.version)
print("graph_version ", outcome.graph_version)
print("file          ", outcome.path)
print("previous      ", outcome.previous)
print("node bodies run", travel_booking.TRIPPED)
print()
for path in sorted(store.path.rglob("*")):
    print(path)
print()
print(store.meta_path.read_text(encoding="utf-8"), end="")
```

<!-- gebra:output id=a-first-snapshot -->
```text
action         recorded
version        1.0.0.0
graph_version  sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
file           .gebra/snapshots/1.0.0.0.yaml
previous       None
node bodies run []

.gebra/meta.yaml
.gebra/reports
.gebra/snapshots
.gebra/snapshots/1.0.0.0.yaml

store_version: '1.0'
current: 1.0.0.0
history:
- version: 1.0.0.0
  graph_version: sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
  created_at: '2026-09-01T09:00:00Z'
```

Three things about that tree are worth naming before anything is diffed.

**`snapshots/` is one file per version, and the file name is the label.** That is what makes
the store git-friendly: a new version is a new file rather than an edit, so a pull request
that snapshots shows up as an addition, and the YAML inside it is emitted deterministically —
one key order, one formatting — so two versions of the same workflow diff cleanly under plain
`git diff` as well. (Deterministic, not *canonical*: the canonical form is the JSON the digest
is taken over, and these files are not it.)

**`meta.yaml` is the index**, and the only file `gebra snapshot` rewrites. It holds `current`, the
history in append order, and each version's digest and timestamp. Nothing else in the store
has to be read to answer "what versions exist".

**`reports/` is created empty** and filled by the audit export, which is a separate step
covered further down. A store with no reports is a store nobody has exported yet, not a broken
one.

The last line of the transcript is the one this page is quietly built on: the agent's node
bodies record themselves and raise if anything calls them, and the ledger is empty. Extraction
imports and inspects a definition; it never runs one, and neither does anything else on this
page.

## `graph_version` is the identity; the label is the story

The label is assigned by the store. The digest is computed from the document. Only one of them
is an identity, and confusing the two is the first way a snapshot store goes wrong:

<!-- gebra:example id=the-same-definition-twice -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.ir import graph_version
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows import travel_booking

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def record():
    return snapshot(
        travel_booking.build_travel_booking_agent(),
        store=store,
        source="travel_booking:build_travel_booking_agent",
        extracted_at=pinned,
    )


first = record()
again = record()

print("first    ", first.action.value, first.version)
print("again    ", again.action.value, again.version, "recorded:", again.recorded)
print("identical", again.diff.identical)
print("versions ", [path.name for path in sorted(store.snapshots_dir.iterdir())])
print()

stored = store.read("1.0.0.0")
print("digest on the envelope", stored.graph_version)
print("digest recomputed     ", graph_version(stored.ir))
print(
    "the envelope is outside its own hash scope:", stored.graph_version == graph_version(stored.ir)
)
```

<!-- gebra:output id=the-same-definition-twice -->
```text
first     recorded 1.0.0.0
again     unchanged 1.0.0.0 recorded: False
identical True
versions  ['1.0.0.0.yaml']

digest on the envelope sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
digest recomputed      sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
the envelope is outside its own hash scope: True
```

A second call on an unchanged definition records nothing and reports the version the store
already holds. That is the policy, not a coincidence: the label counts *changes*, so a
definition that did not change does not get a new one, and CI can call `snapshot` on every
build without growing a store of duplicates.

The digest is a content hash of the core IR and of nothing else — the envelope that carries
the label and the provenance is outside the scope, which is why the recomputed digest above
equals the stored one. Two snapshots with one `graph_version` hold documents with one
canonical form. Per-node prompt and config digests are *inside* that scope, so wherever the
extractor could compute one — a node bound directly to a prompt template or a model — two
versions that differ only in prompt text are two versions rather than a collision. Where it
could not, the slot is absent and there is nothing there for such an edit to move.
[The IR, node identity and `graph_version`](../concepts/ir-and-graph-version.md) works the
digest through in full.

## V.S.F.E: what the four counters count

`1.2.1.3` is four independent counters, not a semantic version. **S** counts topology changes,
**F** node and contract changes, **E** state-schema changes; **V** is yours, and nothing in
gebra ever moves it. The mapping is a table over the IR's own field vocabulary — several of
whose rows are dispositions this build had to take where the frozen text stops short. The diff
engine does not consult it: it derives its bump class from its own deltas, and the two are held
equal by property test, which is the stronger arrangement of the two available.

<!-- gebra:example id=what-the-counters-count -->
```python
from gebra.versioning import FIELD_COMPONENTS, Component

for path, components in FIELD_COMPONENTS.items():
    moved = " ".join(part.value for part in Component if part in components)
    print(f"{'.'.join(path):20} {moved or '— no component'}")
```

<!-- gebra:output id=what-the-counters-count -->
```text
ir_version           — no component
entry                S
finish               S
edges                S
nodes                S F
nodes.id             S F
nodes.annotations    F
state                E
runtime              F
```

Four rows repay a second look.

**`nodes` moves S *and* F.** A node's id is its presence in the topology and the key its
contract hangs from, so adding, removing or renaming one moves both counters. A rename is the
same case as a removal plus an addition, because a renamed node is a new identity — there is no
similarity matching anywhere in this engine.

**`edges` covers the routing, guards included.** A conditional edge's declared `condition` and
its branch labels both sit under `edges`, so renaming a branch, or changing which guard an edge
names, moves S and not F.

**`runtime` is F.** The graph-level block — `recursion_limit`, `interrupts`, `checkpointer` —
is declared or extracted configuration one level up from a node, and it lands with the rest of
the contract content. One consequence is worth carrying: P-02's three witness forms do not
share a counter. A bounded-counter guard lives in `edges[].condition` and moves S; a
`recursion_limit` and a node's `variant` annotation both live under F. No single counter can be
read as "the witnesses moved".

**`ir_version` moves nothing.** A change to the IR *format* is a different kind of migration
from a change to a workflow, and a V.S.F.E label counts the second.

Two rules follow from the counters being independent. Bumps do not reset anything to their
right: `1.4.2.0` with a topology change and a schema change becomes `1.5.2.1`. And the
comparison is by canonical content, so a reordered `nodes` list or a state value written in its
long form is not a change — exactly as it is not a `graph_version` change.

## Eight versions of one agent

Here is the whole thing at once: the travel-booking agent evolved through eight stages, each
extracted and recorded into one store, in order.

<!-- gebra:example id=eight-versions-one-store -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.versioning import Component
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)

for stage in EVOLUTION:
    outcome = snapshot(
        stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned
    )
    moved = outcome.diff.bump_class if outcome.diff else frozenset()
    counters = " ".join(part.value for part in Component if part in moved)
    print(f"{outcome.version:9}  {counters or '—':5}  {stage.summary}")

print()
for path in sorted(store.path.rglob("*")):
    print(path)
```

<!-- gebra:output id=eight-versions-one-store -->
```text
1.0.0.0    —      the TE-05 baseline: nine nodes, two routers, the witnessed booking cycle
1.0.0.1    E      Σ gains the optional graph-input key seat_preference; nothing consumes it
1.1.1.1    S F    contracted join_waitlist node, a waitlist label on route_booking, END wiring
1.2.1.1    S      route_availability gains a waitlist label to the existing join_waitlist node
1.2.1.2    E      Σ drops itinerary while two contracts still declare the write and the read
1.2.1.3    E      availability is redeclared list[str] while three contracts still read it
1.2.2.3    F      replan loses its variant annotation, the carrier both cycles run through
1.2.3.3    F      check_booking's effects gain billable, entering the P-06 trigger set

.gebra/meta.yaml
.gebra/reports
.gebra/snapshots
.gebra/snapshots/1.0.0.0.yaml
.gebra/snapshots/1.0.0.1.yaml
.gebra/snapshots/1.1.1.1.yaml
.gebra/snapshots/1.2.1.1.yaml
.gebra/snapshots/1.2.1.2.yaml
.gebra/snapshots/1.2.1.3.yaml
.gebra/snapshots/1.2.2.3.yaml
.gebra/snapshots/1.2.3.3.yaml
```

That is a real `.gebra/` tree, written by the code above, in the directory CI ran it from.
Everything below reads versions out of a store built exactly this way.

The sequence is deliberately not a tour of one kind of change. Stages 2 to 4 are the three
shapes of additive change — a new optional state key, a new node, a new guarded edge to an
existing node. Stages 5 to 8 are four shapes a reviewer would want to stop on: a state key
removed while contracts still declare it, a state key retyped under contracts that still read
it, a loop bound's carrier removed, and an effect class escalated. Reading the labels alone,
you cannot tell which stage was which — `1.0.0.1` and `1.2.1.2` are both a single E bump. That
is the subject of the rest of this page.

Two words are worth fixing before they are used. **Safe extension** and **breaking change** are
the vocabulary this kind of review is conducted in, and two headings below use the second of
them — but they are the *reviewer's* words, and mine. Nothing gebra prints on this page applies
either to a change, for the reason the lede gives.

## Reading a diff report

`gebra diff` takes two sides. Each can be a stored label, an IR document or an import
reference, and they mix freely; two stored labels is the common case in review.

<!-- gebra:example id=a-diff-report -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.cli import main
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

exit_code = main(["diff", "--store", ".gebra", "1.2.1.1", "1.2.1.2"])
print(f"exit {exit_code}")
```

<!-- gebra:output id=a-diff-report -->
```text
workflow diff
  before                  1.2.1.1  sha256:286652a3dc55d067...
  after                   1.2.1.2  sha256:fafd89ddc8199092...
  bump class              E
  P-12 evolution-safety   not checked [deferred-to-phase-1]
                          the bump class names moved counters, never safety

state schema
  - key itinerary: str
exit 0
```

Six lines of header, then the body. The header is the same on every diff:

- **`before` and `after`** name each side by its recomputed digest, and by its label when the
  side came from a snapshot. Recomputed, not trusted: a stored snapshot whose digest disagrees
  with its own IR is refused rather than diffed under a wrong anchor.
- **`bump class`** is which of S, F and E this change moves — derived from the body below it,
  not asserted beside it.
- **The `P-12 evolution-safety` line** is the deferred marker, and the line under it is the
  sentence it exists to prevent: the bump class names counters that moved, never risk.

The body is one section per counter that moved, one line per entry, with `+` added, `-`
removed and `~` changed. Here a single key left the state schema, so there is one section and
one line. Contract and runtime values are printed as canonical JSON — what the digest saw —
and the section says so, because the authored spelling and the canonical form are not the same
text and a report must not caption one as the other.

The exit code is `0`: the comparison completed. `gebra diff` does not fail a build for having
found a difference unless you ask it to with `--exit-code`, and even then the `1` is a
difference signal carrying no claim about whether that difference is a problem. A `2` means no
comparison was made at all — a side that would not resolve, or a snapshot that failed its
digest check.

## A breaking change: the loop bound's carrier leaves

Stage 7 removes the `variant` annotation from `replan`. That annotation is one of the three
witness forms P-02 accepts, and it is the carrier both of this agent's cycles run through.
Structurally it is one slot on one node, so the diff is F alone:

<!-- gebra:example id=the-loop-bounds-carrier-leaves -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.diff import workflow_diff
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.verify import PropertyReport, verify
from gebra.versioning import Component
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

before, after = store.read("1.2.1.3"), store.read("1.2.2.3")
diff = workflow_diff(before, after)

print("bump class", " ".join(part.value for part in Component if part in diff.bump_class))
print("topology  ", "moved" if diff.topology.has_changes else "unchanged")
print("state     ", "moved" if diff.state else "unchanged")
for changed in diff.contracts.changed:
    for slot in changed.slots:
        movement = "added" if slot.added else "removed" if slot.removed else "changed"
        print(f"contract   {changed.node}.{slot.slot} {movement}")
        print(f"             was {slot.before}")

print()
for label, snapshot_ in (("1.2.1.3", before), ("1.2.2.3", after)):
    report = verify(snapshot_.ir)
    findings = [
        f"{outcome.property} {outcome.failure.property_condition} "
        f"[{outcome.failure.severity} · {outcome.failure.claim_class}]"
        for outcome in report.properties
        if isinstance(outcome, PropertyReport) and outcome.failure is not None
    ]
    print(f"{label}  gate {report.gate.outcome:4} exit {report.gate.exit_code}")
    for finding in findings:
        print(f"           {finding}")
```

<!-- gebra:output id=the-loop-bounds-carrier-leaves -->
```text
bump class F
topology   unchanged
state      unchanged
contract   replan.variant removed
             was {"key":"replan_budget","measure":"replan_budget strictly decreases each lap (one replanning attempt consumed)"}

1.2.1.3  gate pass exit 0
1.2.2.3  gate fail exit 1
           termination-witness cycle-without-termination-witness [fatal · defensible]
```

Two surfaces, two different answers, and both are needed.

The **diff** says a declared slot left a node and shows the value that left. It does not say
which cycles that slot was covering, because it never looked at a cycle: the diff compares two
documents field by field.

**Verification** is what looks at the cycles, and it moves — from a pass to a FATAL
`cycle-without-termination-witness`, claim class DEFENSIBLE. What that finding says is that no
declared witness covers this strongly-connected component; it says nothing about what the loop
does when it runs, and there is no reading of it under which it could.
[P-02 termination-witness](../validators/p02-termination-witness.md) draws that boundary in
full. Re-verifying the new version is therefore not optional after reading a diff; it is the
second half of the same review.

(The comprehension above prints one line per property, which is each finding's *primary*. A
property that finds more than one thing packs the rest onto that record's `co_failures`, and a
loop meant for a real report reads them too.)

There is a practical consequence in the store. Snapshot eligibility turns on FATAL findings and
on whether a verdict was reached at all — an ERROR fails the gate and the version is still
eligible — so a recorder handed *this* version's report refuses to write it. The example above
hands no report, which the engine states plainly rather than defaults around: a caller who ran
no validators has established nothing for it to apply. That is what lets this page store all
eight stages and verify all eight honestly. Pass the report instead and the store stops before
the first version carrying a FATAL, which is a narrower promise than "everything in here
verified clean" and worth reading as the narrower one.

## A breaking change: an effect class escalates

Stage 8 gives `check_booking` a `billable` effect tag beside its existing `network` one, with
no idempotency key or compensation hook added, inside the booking cycle. One slot value moved,
so again the diff is F — and here is the whole report a reviewer gets:

<!-- gebra:example id=an-effect-class-escalates -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.cli import main
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

exit_code = main(["diff", "--store", ".gebra", "1.2.2.3", "1.2.3.3"])
print(f"exit {exit_code}")
```

<!-- gebra:output id=an-effect-class-escalates -->
```text
workflow diff
  before                  1.2.2.3  sha256:003959bfed0dfe7e...
  after                   1.2.3.3  sha256:7e6584a57ef85ae6...
  bump class              F
  P-12 evolution-safety   not checked [deferred-to-phase-1]
                          the bump class names moved counters, never safety

contracts
  values shown            canonical JSON — what the digest saw, never the source
  ~ node contract check_booking:
      ~ effect: ["network"] -> ["billable","network"]
exit 0
```

`billable` is one of the two tags that raise a protection obligation, so this is a change a
reviewer should stop on — and the report shows exactly what changed and no more. The bump
class is `F`, the marker line says `not checked [deferred-to-phase-1]`, and nothing anywhere in
that output calls the change safe or breaking. Re-verification is again the other half:
[P-06 effect-safety](../validators/p06-effect-safety.md) is the property that raises the
`unprotected-effect-in-cycle` finding on this version, and it is what turns "an effect tag
moved" into a finding with a location, a severity, and the claim class DEFENSIBLE-A — the
class that records that the effect tags themselves are declarations gebra trusts rather than
facts it checked.

## Two changes, one counter

This is the pattern that makes the bump class insufficient on its own. Stage 2 adds an optional
state key nothing consumes. Stage 5 removes a key that two node contracts still declare. Both
are a single `E`:

<!-- gebra:example id=two-changes-one-counter -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.diff import workflow_diff
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.verify import verify
from gebra.versioning import Component
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

for before_label, after_label in (("1.0.0.0", "1.0.0.1"), ("1.2.1.1", "1.2.1.2")):
    after = store.read(after_label)
    diff = workflow_diff(store.read(before_label), after)
    counters = " ".join(part.value for part in Component if part in diff.bump_class)
    print(f"{before_label} -> {after_label}   bump class {counters}")
    for key in diff.state.added:
        print(f"    + {key.key}: {key.declaration.type}")
    for key in diff.state.removed:
        print(f"    - {key.key}: {key.declaration.type}")
    print(f"    P-12 {diff.evolution_safety.property}: {diff.evolution_safety.status}")
    print(f"    gate on {after_label}: {verify(after.ir).gate.outcome}")

readers = [
    node.id
    for node in store.read("1.2.1.2").ir.nodes
    if node.annotations is not None
    and "itinerary" in (*(node.annotations.input or ()), *(node.annotations.output or ()))
]
print()
print("contracts still declaring 'itinerary' at 1.2.1.2:", readers)
```

<!-- gebra:output id=two-changes-one-counter -->
```text
1.0.0.0 -> 1.0.0.1   bump class E
    + seat_preference: str
    P-12 evolution-safety: deferred-to-phase-1
    gate on 1.0.0.1: pass
1.2.1.1 -> 1.2.1.2   bump class E
    - itinerary: str
    P-12 evolution-safety: deferred-to-phase-1
    gate on 1.2.1.2: pass

contracts still declaring 'itinerary' at 1.2.1.2: ['compile_itinerary', 'notify_traveler']
```

Same counter, same marker status, same gate — and the second change is the one that leaves two
node contracts declaring a key the state schema no longer has. The difference is visible in the
diff body (`+` against `-`) and nowhere else, and the cross-reference in the last two lines —
*which* contracts still name the removed key — is something the reader assembles, not something
the report hands over. Wiring a read to a key outside Σ is P-03 `signature-soundness`, which is
outside this release along with P-12; the wedge validators leave it alone, and this transcript
is what that looks like from a reviewer's chair.

The lesson generalizes. **A bump class is a routing decision — which section of the diff to
read — never a risk grade.**

## The whole sequence, and where verification moves with it

Put every step beside its verdict and the shape of the review becomes clear:

<!-- gebra:example id=every-step-and-its-verdict -->
```python
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path

from gebra.lineage import compare
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.verify import PropertyReport, verify
from gebra.versioning import Component
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
labels = [
    snapshot(
        stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned
    ).version
    for stage in EVOLUTION
]

print(f"{'step':20} {'moved':6} gate")
for before_label, after_label in pairwise(labels):
    diff = compare(store, before_label, after_label)
    counters = " ".join(part.value for part in Component if part in diff.bump_class)
    report = verify(store.read(after_label).ir)
    print(f"{before_label} -> {after_label:9} {counters:6} {report.gate.outcome}")
    for outcome in report.properties:
        if isinstance(outcome, PropertyReport) and outcome.failure is not None:
            failure = outcome.failure
            print(
                f"{'':21}{failure.property_condition} [{failure.severity} · {failure.claim_class}]"
            )
```

<!-- gebra:output id=every-step-and-its-verdict -->
```text
step                 moved  gate
1.0.0.0 -> 1.0.0.1   E      pass
1.0.0.1 -> 1.1.1.1   S F    pass
1.1.1.1 -> 1.2.1.1   S      pass
1.2.1.1 -> 1.2.1.2   E      pass
1.2.1.2 -> 1.2.1.3   E      pass
1.2.1.3 -> 1.2.2.3   F      fail
                     cycle-without-termination-witness [fatal · defensible]
1.2.2.3 -> 1.2.3.3   F      fail
                     cycle-without-termination-witness [fatal · defensible]
                     unprotected-effect-in-cycle [error · defensible-a]
```

Five of the seven steps leave the gate green, and two of those five are among the four shapes
the walkthrough flagged. That is not a gap being papered over: the properties that
would grade a *pair* of versions (P-12) and a read of a key outside the schema (P-03) are both
outside this release, and the registry answers for them with a structured not-implemented
marker rather than a pass. What the five implemented validators check is
[what gebra checks](../concepts/what-gebra-checks.md); what they do not is the reason the diff
body, not the gate, is where a schema change gets reviewed.

The two steps that *do* move the gate are worth the opposite observation: verification is not
redundant with the diff. Neither of those runs knows a version came before it — a validator
reads one document — and each still names its problem with a location, a severity and a claim
class: a strongly-connected component carrying no declared witness, and a trigger-tagged node
inside a cycle with no protection declared.

## "Not checked" is not a pass

The marker is one object, and it turns up in every surface that could otherwise be mistaken for
a verdict:

<!-- gebra:example id=not-checked-is-not-a-pass -->
```python
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from gebra.audit import export_version
from gebra.diff import EVOLUTION_SAFETY_DEFERRED, workflow_diff
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION[:3]:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

marker = EVOLUTION_SAFETY_DEFERRED
print("kind    ", marker.kind)
print("property", marker.property_id, marker.property)
print("status  ", marker.status)
print("detail")
for line in textwrap.wrap(marker.detail, width=84):
    print("   ", line)
print()

diff = workflow_diff(store.read("1.0.0.1"), store.read("1.1.1.1"))
outcome = snapshot(
    EVOLUTION[3].build(), store=store, source="travel_booking:v4", extracted_at=pinned
)
document = json.loads(export_version(store, "1.1.1.1").path.read_text(encoding="utf-8"))
exported = next(
    entry for entry in document["properties"] if entry["property"] == "evolution-safety"
)

print("on a diff         ", diff.evolution_safety is marker)
print("on a snapshot     ", outcome.diff.evolution_safety is marker)
print("in an audit report", {key: exported[key] for key in ("kind", "property_id", "status")})
print("result key present", "result" in exported)
```

<!-- gebra:output id=not-checked-is-not-a-pass -->
```text
kind     not-implemented
property P-12 evolution-safety
status   deferred-to-phase-1
detail
    P-12 evolution-safety is outside the Phase-0 wedge (SOW §8) and has no validator in
    this release; the catalog contract is PROPERTY-CATALOG-SPEC §P-12 (stub;
    Verification-Properties §2 authoritative). No verdict was reached — this is not a
    pass.

on a diff          True
on a snapshot      True
in an audit report {'kind': 'not-implemented', 'property_id': 'P-12', 'status': 'deferred-to-phase-1'}
result key present False
```

One object, three surfaces, one vocabulary — the same *kind* of structured not-implemented
marker the property registry returns for every property outside this release, each carrying its
own id and detail, as the export's eight below show. It carries no `result`, because it is not a
result: `deferred-to-phase-1` says a question was not asked. A tool that rendered it as a check
mark, or omitted it, would be telling a reader that a safe/breaking classification happened.

## The per-version audit report

Every stored version can be exported as a JSON run report next to the snapshot it describes —
one file per version, at `reports/<version>.report.json`:

<!-- gebra:example id=the-audit-export -->
```python
import json
from datetime import datetime, timezone
from pathlib import Path

from gebra.audit import export_store
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

for exported in export_store(store):
    print(f"{exported.path.name:24} gate exit {exported.report.gate.exit_code}")

document = json.loads((store.reports_dir / "1.2.2.3.report.json").read_text(encoding="utf-8"))
print()
print("top-level keys", sorted(document))
print("subject       ", {key: document["subject"][key] for key in ("input_mode", "version")})
answered = [entry for entry in document["properties"] if "result" in entry]
deferred = [entry for entry in document["properties"] if entry.get("kind") == "not-implemented"]
print(
    f"properties     {len(document['properties'])} — {len(answered)} answered, {len(deferred)} deferred"
)
print("deferred      ", [entry["property_id"] for entry in deferred])
```

<!-- gebra:output id=the-audit-export -->
```text
1.0.0.0.report.json      gate exit 0
1.0.0.1.report.json      gate exit 0
1.1.1.1.report.json      gate exit 0
1.2.1.1.report.json      gate exit 0
1.2.1.2.report.json      gate exit 0
1.2.1.3.report.json      gate exit 0
1.2.2.3.report.json      gate exit 1
1.2.3.3.report.json      gate exit 1

top-level keys ['best_effort', 'gate', 'properties', 'report_format', 'subject', 'tool']
subject        {'input_mode': 'snapshot', 'version': '1.2.2.3'}
properties     13 — 5 answered, 8 deferred
deferred       ['P-03', 'P-05', 'P-07', 'P-09', 'P-10', 'P-11', 'P-12', 'P-13']
```

The report is a verification run over the stored IR, in the report format's snapshot profile,
with the version and the digest on the subject. Thirteen catalog properties are listed, five
answered and eight carrying their deferral — a per-version record that says what was checked
*and* what was not, which is the property that makes it usable as an audit trail rather than a
summary.

Exporting is a separate call from snapshotting on purpose: a snapshot is a definition, a report
is a verdict about one, and the store keeps them in separate directories so that re-exporting
after a validator changes does not rewrite a single snapshot.

## Has the store kept up?

The failure mode a snapshot store has is silence: the definition moves, nobody records it, and
the store quietly describes last month's agent. The freshness check compares the working
definition's digest against the snapshot the store currently points at:

<!-- gebra:example id=has-the-store-kept-up -->
```python
from datetime import datetime, timezone
from pathlib import Path

import gebra
from gebra.audit import freshness
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION[:6]:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

for stage in (EVOLUTION[5], EVOLUTION[6]):
    outcome = freshness(gebra.extract(stage.build()).ir, store=store)
    print(f"working definition: {stage.name}")
    print(
        f"  {outcome.state.value:5} fresh={outcome.fresh} moved={[part.value for part in outcome.moved]}"
    )
    print(f"  {outcome.summary().splitlines()[0]}")
```

<!-- gebra:output id=has-the-store-kept-up -->
```text
working definition: v6-availability-retyped
  fresh fresh=True moved=[]
  the store's current snapshot is the working definition
working definition: v7-witness-removed
  stale fresh=False moved=['F']
  the working definition is not the snapshot the store holds — it changed and was not re-snapshotted
```

It answers in three states rather than two — fresh, stale, and a store holding nothing at all,
which is a different event and does not want the same words. A stale outcome names which of S,
F and E moved and stops there; it grades nothing.

In CI this runs through the pytest plugin as `@pytest.mark.gebra_freshness`, which fails its
item when the store has fallen behind, or as the `gebra_freshness` fixture when you would rather
assert on the outcome yourself. [The pytest plugin and CI gating](pytest-plugin-and-ci-gating.md)
is where that marker sits in a workflow.

## The history, and the two questions it answers

`gebra history` lists what the store holds, oldest first, with the step between each
neighbouring pair:

<!-- gebra:example id=reading-the-history -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.cli import main
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

exit_code = main(["history", "--store", ".gebra"])
print(f"exit {exit_code}")
```

<!-- gebra:output id=reading-the-history -->
```text
history of .gebra — 8 versions; current 1.2.3.3

  #  version  graph_version     created               step
  0  1.0.0.0  sha256:b310b9...  2026-09-01T09:00:00Z  n/a (oldest version)
  1  1.0.0.1  sha256:833c15...  2026-09-01T09:00:00Z  +E, content changed
  2  1.1.1.1  sha256:e64137...  2026-09-01T09:00:00Z  +S +F, content changed
  3  1.2.1.1  sha256:286652...  2026-09-01T09:00:00Z  +S, content changed
  4  1.2.1.2  sha256:fafd89...  2026-09-01T09:00:00Z  +E, content changed
  5  1.2.1.3  sha256:e01c03...  2026-09-01T09:00:00Z  +E, content changed
  6  1.2.2.3  sha256:003959...  2026-09-01T09:00:00Z  +F, content changed
* 7  1.2.3.3  sha256:7e6584...  2026-09-01T09:00:00Z  +F, content changed
exit 0
```

A listing reads `meta.yaml` and no snapshot file, so it is cheap and it reports what the index
records. `*` marks `current`. `--format json` is the same rows as a machine-readable document,
and `--limit`, `--since` and `--until` window the listing while keeping the absolute index and
the omitted counts on every row.

The `step` column is where the two questions separate. `+F, content changed` is two independent
facts: the **labels** say F moved, and the **content** says the two digests differ. The label
arithmetic comes from the index; the content comparison comes from reading both snapshots. They
can disagree — nothing in a store makes a label describe what changed — and neither is quietly
preferred over the other. When you need the content answer in full, that is `gebra diff` on the
same pair.

## How to read a diff before you approve it

Everything above, as the order of operations a reviewer can follow:

1. **Read the header, not for the verdict but for the anchors.** Confirm you are comparing the
   two versions you meant to. The digests are recomputed, so a stored side that has been edited
   underneath its label is refused rather than reported.
2. **Use the bump class to decide which section matters**, then read that section's lines. The
   class routes; the lines inform.
3. **In the `state schema` section, treat `-` and `~` as questions.** A removed or retyped key
   raises one question per contract that still declares it, and neither the diff nor the five
   implemented validators asks it. The IR carries every node's declared `input` and `output`,
   so the cross-reference is available to you — the example above is one way to write it.
4. **In the `contracts` section, watch three slots in particular.** `variant` and
   `recursion_limit` are two of P-02's three witness carriers, so their departure is a P-02
   question; `effect` gaining `billable` or `irreversible` is a P-06 question; and because a
   node's prompt digest lives here where the extractor could compute one, an F bump on an
   otherwise untouched node can mean a rewritten prompt.
5. **In the `topology` section, separate the additions from the rest.** A `+` line adds a
   vertex or a route; a `-` line takes one away, and `~ node X — its edges moved` says a route
   changed while the node stayed. The last two are the entries that alter a path something
   already depended on — but do not skip the `+` lines either: an added edge can close a cycle
   through nodes that were never in one, which is a new P-02 obligation for that cycle and a new
   P-06 one for any effect-tagged node now inside it, with no `-` or `~` line anywhere in the
   diff.
6. **Then verify the new version.** The diff and the validators answer different questions, and
   two of the four changes this page calls out only become findings on the second one.
7. **Take the classification yourself, and write it down where a human will read it** — in the
   pull request. gebra records what moved; the judgment is not in the store.

## What a diff does not say

The diff is structural, over two extracted documents. It compares fields: nodes, edges,
START/END wiring, the declared contracts, the state schema. What a node body contributes to
those documents is its contract, plus a prompt or config digest where the extractor could
compute one; what a router contributes is its declared branch labels and the name of its guard,
never an evaluated expression and never a digest of one. The bodies themselves are not in the
IR, so they are not in the diff. A diff that reports nothing is therefore a statement about the
fields it compares — the two anchor digests on its header are the stricter answer — and never a
statement that the two agents behave alike.

It also does not classify. P-12 `evolution-safety` — safe-extension versus breaking-change over
a pair of versions — is outside this release, and the marker every diff carries is the honest
form of that: `not checked`, with a status, in the slot where a classification would be. No
output on this page, from any surface, calls a change safe or breaking, and none should be read
as if it had.

## Where this page is checked

Every transcript above is produced by the code block above it, executed in a fresh interpreter
in CI, and compared byte for byte against what the page shows — the mechanism is
[executable examples](../contributing/executable-examples.md). Beyond that,
`tests/docs/test_snapshot_guide.py` holds the page's prose to its sources: the V.S.F.E table
against `FIELD_COMPONENTS`, the store's directory and file names against the store module's own
constants, both rendered diff reports re-run through the verb and compared byte for byte, every
step's bump class and gate verdict re-derived from a store the test builds, each condition id
against the registry with its severity and claim class, the documented exit codes against real
invocations, and the sentences that carry the honest-claims boundary against a scan of the page.
A statement here that stopped being true fails the build rather than aging quietly.
