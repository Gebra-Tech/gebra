# Travel booking, end to end

This is the whole pipeline over one agent: **extract → verify → snapshot → evolve → diff →
report**. A travel-booking `StateGraph` is read into an IR and verified clean; five seeded
defects are each caught by the property that owns them; the healthy version is recorded into a
`.gebra/` store; the agent evolves through seven more versions — three additive, four a
reviewer would stop on — with every step diffed and classified; and the store ends holding an
audit report for every version it keeps.

It is also this repository's acceptance scenario. The same sequence, over the same three
fixture modules, runs as a dedicated CI job on every push, and the release is judged against
it. This page adds no assets of its own on top of that scenario — every graph below is
imported from the modules the CI job runs, so the tutorial and the scenario cannot drift
apart: there is nothing here to drift.

Nothing on this page executes a workflow. `gebra.extract()` imports and inspects a
definition without calling a node, a router, a tool or a model, and everything downstream of
extraction reads serialized IR. The agent's node bodies record themselves and raise if
anything calls them, and the last line of the first transcript below — an empty ledger — is
CI checking exactly that.

!!! note "Following along"

    The assets are three modules in this repository: `tests/sample_workflows/travel_booking.py`
    (the agent), `travel_booking_defects.py` (the five seeded-defect variants and the `DEFECTS`
    expectation table) and `travel_booking_evolution.py` (the eight-stage evolution and the
    `EVOLUTION` table). They are the same modules `tests/dod/` — the acceptance job — imports.
    To run the examples yourself, clone the repository and put its root on `PYTHONPATH`; each
    example is self-contained and rebuilds what it needs. The store-writing examples pin
    `extracted_at` so a stored timestamp is a function of the example rather than of the clock.
    On your own agent, everything here applies unchanged; only the imports differ.

## The agent

The subject is a routed, stateful booking agent: classify the traveller's request, check
availability, book a flight and a hotel, confirm both, and either compile and send the
itinerary or unwind the hotel hold. Two decisions can put it back on an earlier node:

```text
START → classify_request → availability_check
availability_check --route_availability--> {available: book_flight, revise: replan}
replan → availability_check
book_flight → book_hotel → check_booking
check_booking --route_booking--> {confirmed: compile_itinerary,
                                  revise: replan, abort: release_hotel_hold}
compile_itinerary → notify_traveler → END
release_hotel_hold → END
```

Those two re-entry decisions give the graph one non-trivial strongly-connected component —
`{availability_check, replan, book_flight, book_hotel, check_booking}` — holding two simple
cycles, both through `replan`. That component is where most of this page happens: it is where
P-02 wants every simple cycle witnessed, and it is the region P-06 grades effects in. Every node declares
its reads, writes and effects with the [contract decorators](contracts-and-annotations.md),
`replan` carries a `variant` annotation attesting a loop bound, and both billable nodes
declare a protection — one an idempotency key, one a compensation hook.

Extraction turns the builder into a document:

<!-- gebra:example id=meeting-the-agent -->
```python
import gebra
from tests.sample_workflows.travel_booking import TRIPPED, build_travel_booking_agent

envelope = gebra.extract(build_travel_booking_agent())

print(
    "extracted from",
    envelope.extracted_from.source,
    f"at {envelope.extracted_from.family.value} level",
)
print("ir_version    ", envelope.ir.ir_version)
print("nodes         ", len(envelope.ir.nodes))
print("graph_version ", envelope.graph_version())
print("warnings      ", list(envelope.warnings))
print("bodies run    ", TRIPPED)
```

<!-- gebra:output id=meeting-the-agent -->
```text
extracted from langgraph:StateGraph at builder level
ir_version     1.0
nodes          9
graph_version  sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
warnings       []
bodies run     []
```

Zero warnings means nothing was inferred or defaulted — the contracts every validator reads
below are the ones the author wrote. The digest is the document's content identity — the
envelope around it, label and provenance and timestamp, sits outside the hash — and it
returns at every later step: the verify report carries it, the snapshot stores it, the diff
anchors on it. [Extract your first IR](extract-your-first-ir.md) reads the document itself;
this page moves on to what is done with it.

## Verify: five verdicts, eight markers

`verify()` answers for every property in the catalog — the five this release implements with
a verdict, the eight it does not with a structured marker:

<!-- gebra:example id=the-wedge-five-at-v1 -->
```python
import gebra
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.travel_booking import build_travel_booking_agent

report = verify(gebra.extract(build_travel_booking_agent()).ir)
verdicts = [item for item in report.properties if isinstance(item, PropertyReport)]
markers = [item for item in report.properties if not isinstance(item, PropertyReport)]

for outcome in verdicts:
    print(f"{outcome.property:22} {outcome.result}")
print(f"+ {len(markers)} catalog properties outside this release, each answering")
print(f"  {markers[0].kind}: {markers[0].status}")
print(
    f"gate {report.gate.outcome}, exit {report.gate.exit_code}; snapshot",
    "eligible" if report.gate.snapshot_eligible else "suppressed",
)
```

<!-- gebra:output id=the-wedge-five-at-v1 -->
```text
graph-well-formed      pass
termination-witness    pass
dataflow-completeness  pass
effect-safety          pass
determinism-replay     pass
+ 8 catalog properties outside this release, each answering
  not-implemented: deferred-to-phase-1
gate pass, exit 0; snapshot eligible
```

Each pass carries a structured witness — the P-02 one, for instance, records the `variant`
annotation on `replan` and the fact that both simple cycles run through that carrier. What a
witness contains, per property, is [Verify and interpret](verify-and-interpret.md)'s subject;
what matters for this page is the last line. The gate passed and the run is
**snapshot-eligible**, which is the hand-off the snapshot step below turns on. A marker,
meanwhile, is not a pass: `not-implemented` says a question was not asked, and it is never
counted as if it had been answered.

## Five defects, five catches

The acceptance criterion this scenario exists for names five defects and requires each to be
caught by a named property, under a named condition, at the seeded location. The five
variants live beside the agent, each built from v1 with exactly one edit, and `DEFECTS`
records what the catch must look like — the same table the CI harness enforces. Running the
five:

<!-- gebra:example id=five-defects-five-catches -->
```python
import gebra
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.travel_booking_defects import DEFECTS

for defect in DEFECTS:
    report = verify(gebra.extract(defect.build()).ir)
    [finding] = [
        outcome
        for outcome in report.properties
        if isinstance(outcome, PropertyReport) and outcome.failure is not None
    ]
    failure, location = finding.failure, finding.failure.location
    if location.kind == "scc":
        where = f"the {len(location.nodes)}-node component"
    elif location.kind == "state-key":
        where = f"key {location.key!r} read by {location.node}"
    else:
        where = f"node {location.node}"
    if getattr(location, "fanout", None):
        where += f", fanout {location.fanout}"
    print(f"defect {defect.number} — {defect.summary}")
    print(
        f"  {finding.property}: {failure.property_condition} [{failure.severity} · {failure.claim_class}]"
    )
    print(f"  at {where}; exit {report.gate.exit_code}")
```

<!-- gebra:output id=five-defects-five-catches -->
```text
defect 1 — replan loses its variant slot; the five-node SCC carries no witness form
  termination-witness: cycle-without-termination-witness [fatal · defensible]
  at the 5-node component; exit 1
defect 2 — book_flight loses @gebra.idempotent inside the booking retry region
  effect-safety: unprotected-effect-in-retry-region [error · defensible-a]
  at node book_flight; exit 1
defect 3 — classify_request claims seed-only determinism with external among effects
  determinism-replay: deterministic-llm-temperature-unpinned [warning · heuristic]
  at node classify_request; exit 0
defect 4 — an express label skips both bookings; notify_traveler reads itinerary
  dataflow-completeness: read-key-never-written-on-path [fatal · defensible-a]
  at key 'itinerary' read by notify_traveler; exit 1
defect 5 — a send fan-out worker books billable legs unprotected in the retry region
  effect-safety: unprotected-effect-in-retry-region [error · defensible-a]
  at node book_leg, fanout send; exit 1
```

The destructuring in the loop — `[finding] = [...]` — is not a shortcut, it is a claim: one
seeded edit produces exactly one finding, so the example crashes if any variant ever raises a
second signal or none. The CI harness asserts the same fact the heavier way, per variant and
negative-tested.

Reading down the five: **defect 1** removes the `variant` annotation from `replan`, and with
it the only declared witness covering the booking component — what
[P-02](../validators/p02-termination-witness.md) then reports is witness *absence*, a fact
about the declaration and never a statement about whether a run halts. **Defect 2** strips
the idempotency key from `book_flight`, an `irreversible`-and-`billable` node that the
`available` label re-enters as-is — a retry region, where
[P-06](../validators/p06-effect-safety.md) requires a declared protection and now finds none.
**Defect 3** degrades the determinism claim on the LLM-backed `classify_request` to a seed
with no pinned temperature; [P-08](../validators/p08-determinism-replay.md) records the
incoherence as a WARNING and the default gate stays open — the next section is about that
exit `0`. **Defect 4** adds an `express` label that routes availability straight to
notification, so no node on that path writes the `itinerary` that `notify_traveler` declares
it reads — [P-04](../validators/p04-dataflow-completeness.md)'s path analysis names the path.
**Defect 5** replaces the serial bookings with a `Send` fan-out whose billable worker is
unprotected inside the same retry region; the finding is defect 2's condition at a different
node, with the fan-out named in the location — the evidence that the lap re-dispatches the
worker.

Note what the bracketed pairs add: every finding carries its **claim class** beside its
severity. The two P-06 findings are `defensible-a` — decided over declared effect tags gebra
trusts rather than facts it checked — and the P-08 finding is `heuristic`, an advisory the
severity ladder never lets past WARNING. [What gebra checks](../concepts/what-gebra-checks.md)
defines the ladder and the classes.

## The catch that needs strict mode

Defect 3 exits `0` under the default policy because its finding is a WARNING, and a WARNING
does not block a gate. Its catch is a policy decision: promote `determinism-replay` and the
same finding fails the build —

<!-- gebra:example id=the-catch-that-needs-strict -->
```python
import gebra
from gebra.verify import PropertyReport, RunPolicy, StrictPolicy, verify
from tests.sample_workflows.travel_booking_defects import DEFECTS

variant = next(defect for defect in DEFECTS if defect.strict_slug is not None)
envelope = gebra.extract(variant.build())
promotion = RunPolicy(strict=StrictPolicy(mode="per-property", properties=(variant.strict_slug,)))

default_run = verify(envelope.ir)
strict_run = verify(envelope.ir, promotion)
records = [
    next(
        outcome
        for outcome in run.properties
        if isinstance(outcome, PropertyReport) and outcome.property == variant.property
    )
    for run in (default_run, strict_run)
]

print(f"defect {variant.number} — {variant.summary}")
print("default  gate", default_run.gate.outcome, "exit", default_run.gate.exit_code)
print("strict   gate", strict_run.gate.outcome, "exit", strict_run.gate.exit_code)
promoted = strict_run.gate.promotions[0]
print(f"promoted {promoted.property}: {promoted.property_condition}")
print(
    f"the record: [{records[1].failure.severity} · {records[1].failure.claim_class}]",
    "— model-equal across both runs:",
    records[0] == records[1],
)
```

<!-- gebra:output id=the-catch-that-needs-strict -->
```text
defect 3 — classify_request claims seed-only determinism with external among effects
default  gate pass-with-notes exit 0
strict   gate fail exit 1
promoted determinism-replay: deterministic-llm-temperature-unpinned
the record: [warning · heuristic] — model-equal across both runs: True
```

The last line is the distinction this scenario is required to demonstrate: the promotion
moves the **gate** and never the **record**. The finding is model-equal across both runs —
same severity, same claim class — and the gate names what it promoted, so a report never
pretends a policy decision was a property's own grade. On the command line and in the pytest
plugin the same promotion is spelled `--strict=determinism-replay` and
`--gebra-strict=determinism-replay`; the rollout from report-only to gate to strict is
[the CI-gating guide](../guides/pytest-plugin-and-ci-gating.md)'s subject.

## Snapshot: v1 through the eligibility gate

The healthy agent goes into the store. The scenario does this the way a pipeline should: one
extraction feeds the verify gate *and* the recorder, so the digest the gate ruled on is —
verifiably — the digest the store wrote:

<!-- gebra:example id=v1-through-the-gate -->
```python
from datetime import datetime, timezone
from pathlib import Path

import gebra
from gebra.snapshot import record
from gebra.store import SnapshotStore
from gebra.verify import verify
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
v1 = EVOLUTION[0]

envelope = gebra.extract(v1.build())
report = verify(envelope.ir)
outcome = record(
    envelope,
    store=store,
    source=f"travel_booking:{v1.name}",
    extracted_at=datetime(2026, 9, 1, 9, 0, 0, tzinfo=timezone.utc),
    eligibility=report,
)

print(
    "gate                  ",
    report.gate.outcome,
    "— snapshot",
    "eligible" if report.gate.snapshot_eligible else "suppressed",
)
print("digest the gate saw   ", report.subject.graph_version)
print("digest the store wrote", outcome.graph_version)
print("recorded              ", outcome.version, "->", outcome.path)
```

<!-- gebra:output id=v1-through-the-gate -->
```text
gate                   pass — snapshot eligible
digest the gate saw    sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
digest the store wrote sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
recorded               1.0.0.0 -> .gebra/snapshots/1.0.0.0.yaml
```

`record()` takes the extraction envelope rather than the live object, which is what makes the
one-resolution flow possible; handing it the run report makes the recording conditional on
eligibility. `v1` here is the first row of `EVOLUTION` — the same table the next step walks —
and its label is `1.0.0.0`: the store's version scheme starts counting from the first thing
it is given. What the four counters count, and everything else about the store, is
[the snapshot guide](../guides/snapshot-diff-and-evolution.md)'s ground; this page uses it
and moves on.

## Evolve: seven more versions

The agent now changes seven times, and no edit is ever reverted. Stages v2–v4 are the three
additive shapes — a new optional state key, a new node, a new guarded edge to an existing
node. Stages v5–v8 are the four a reviewer would stop on: a state key removed while two
contracts still declare it, a key retyped under four readers, the loop bound's carrier
removed, and an effect escalated into the protection-obligation set. Each stage is extracted,
verified, and offered to the recorder with its report:

<!-- gebra:example id=seven-more-versions -->
```python
from datetime import datetime, timezone
from pathlib import Path

import gebra
from gebra.snapshot import SnapshotError, record
from gebra.store import SnapshotStore
from gebra.verify import verify
from gebra.versioning import Component
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))

for index, stage in enumerate(EVOLUTION):
    envelope = gebra.extract(stage.build())
    report = verify(envelope.ir)
    when = datetime(2026, 9, 1, 9, 0, index, tzinfo=timezone.utc)
    source = f"travel_booking:{stage.name}"
    try:
        outcome = record(
            envelope, store=store, source=source, extracted_at=when, eligibility=report
        )
        how = "through the gate"
    except SnapshotError as refusal:
        print(f"          {stage.name}: refused with its report — {refusal.reason.value}")
        outcome = record(envelope, store=store, source=source, extracted_at=when, eligibility=None)
        how = "handed no report"
    moved = outcome.diff.bump_class if outcome.diff else frozenset()
    counters = " ".join(part.value for part in Component if part in moved)
    print(f"{outcome.version:9} {counters or '—':4} {how:17} {stage.summary}")
```

<!-- gebra:output id=seven-more-versions -->
```text
1.0.0.0   —    through the gate  the TE-05 baseline: nine nodes, two routers, the witnessed booking cycle
1.0.0.1   E    through the gate  Σ gains the optional graph-input key seat_preference; nothing consumes it
1.1.1.1   S F  through the gate  contracted join_waitlist node, a waitlist label on route_booking, END wiring
1.2.1.1   S    through the gate  route_availability gains a waitlist label to the existing join_waitlist node
1.2.1.2   E    through the gate  Σ drops itinerary while two contracts still declare the write and the read
1.2.1.3   E    through the gate  availability is redeclared list[str] while four contracts still read it
          v7-witness-removed: refused with its report — not-snapshot-eligible
1.2.2.3   F    handed no report  replan loses its variant annotation, the carrier both cycles run through
          v8-billable-confirmation: refused with its report — not-snapshot-eligible
1.2.3.3   F    handed no report  check_booking's effects gain billable, entering the P-06 trigger set
```

Two refusals interrupt the sequence, and they are the eligibility rule doing its job: v7 and
v8 verify with a FATAL finding, a FATAL alone withdraws snapshot eligibility, and a recorder
handed such a report refuses to write. Note that the first six stages went through the gate —
including v5 and v6, whose schema edits raise nothing in the five implemented properties, for
reasons worth knowing rather than assuming: grading a *pair* of versions is P-12's question
and a departed key's read is P-03's — both outside this release — and no implemented property
reads a key's declared type, which is all v6 changed. That is why those two are
diff-classification cases rather than verify findings.

The scenario still stores v7 and v8, by recording them with **no report handed in** — the
recorder's documented posture for a caller who has established nothing for it to apply. That
choice is worth stating in full: all eight versions are stored *and* all eight are verified,
and the joining of those two facts is the caller's, visible in the transcript rather than
silently defaulted. A store built only through the gate makes a narrower and stronger
promise — it stops before the first FATAL-bearing version — and which posture a pipeline
wants is a decision this page shows both sides of.

## Diff: every breaking case, classified

The store now holds the whole history, so every step can be re-derived from its files alone.
Here are the four steps a reviewer would stop on — the two schema edits, the witness removal,
the effect escalation — each as `gebra diff` reports it:

<!-- gebra:example id=every-breaking-case-classified -->
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

for before, after in (
    ("1.2.1.1", "1.2.1.2"),
    ("1.2.1.2", "1.2.1.3"),
    ("1.2.1.3", "1.2.2.3"),
    ("1.2.2.3", "1.2.3.3"),
):
    main(["diff", "--store", ".gebra", before, after])
    print()
```

<!-- gebra:output id=every-breaking-case-classified -->
```text
workflow diff
  before                  1.2.1.1  sha256:286652a3dc55d067...
  after                   1.2.1.2  sha256:fafd89ddc8199092...
  bump class              E
  P-12 evolution-safety   not checked [deferred-to-phase-1]
                          the bump class names moved counters, never safety

state schema
  - key itinerary: str

workflow diff
  before                  1.2.1.2  sha256:fafd89ddc8199092...
  after                   1.2.1.3  sha256:e01c03b8157eda8f...
  bump class              E
  P-12 evolution-safety   not checked [deferred-to-phase-1]
                          the bump class names moved counters, never safety

state schema
  ~ key availability: type str -> list[str]

workflow diff
  before                  1.2.1.3  sha256:e01c03b8157eda8f...
  after                   1.2.2.3  sha256:003959bfed0dfe7e...
  bump class              F
  P-12 evolution-safety   not checked [deferred-to-phase-1]
                          the bump class names moved counters, never safety

contracts
  values shown            canonical JSON — what the digest saw, never the source
  ~ node contract replan:
      - variant = {"key":"replan_budget","measure":"replan_budget strictly 
decreases each lap (one replanning attempt consumed)"}

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
```

Each report's classification is two lines read together. The **bump class** says which of
the store's counters this step moved — `E` for the two schema edits, `F` for the two
contract edits — and routes you to the section below it. The **`P-12 evolution-safety`**
line is the classification gebra deliberately does not make: grading a change safe or
breaking over a pair of versions is a property outside this release, the marker says `not
checked` in the slot where that verdict would go, and the line under it is the caption that
keeps a bump class from being read as a risk grade.

So the body is where the reviewer's information is. `- key itinerary: str` beside the fact
that two contracts still declare that key; `~ key availability` retyped under four
readers; one `variant` slot leaving `replan`, shown with the full annotation value that
left (wrapped here by the terminal renderer at its default width — the canonical value is
one line, since a raw newline can never sit inside a canonical JSON string); one `effect`
tuple gaining `billable`. The diff hands over what moved, exactly and
completely — the judgment is the reviewer's, and the next step is what gebra contributes to
it.

## What verification adds to a diff

A diff compares two documents; it never looks at a cycle. Verification looks at one document
at a time and does — so the second half of reviewing an evolution step is re-verifying the
new version. Over the stored history, the two steps that edited an existing contract are the
two whose gate moves:

<!-- gebra:example id=what-verification-adds -->
```python
from datetime import datetime, timezone
from pathlib import Path

from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

for label in ("1.2.1.3", "1.2.2.3", "1.2.3.3"):
    report = verify(store.read(label).ir)
    print(f"{label}  gate {report.gate.outcome:4}  exit {report.gate.exit_code}")
    for outcome in report.properties:
        if isinstance(outcome, PropertyReport) and outcome.failure is not None:
            failure = outcome.failure
            print(
                f"         {failure.property_condition} [{failure.severity} · {failure.claim_class}]"
            )
```

<!-- gebra:output id=what-verification-adds -->
```text
1.2.1.3  gate pass  exit 0
1.2.2.3  gate fail  exit 1
         cycle-without-termination-witness [fatal · defensible]
1.2.3.3  gate fail  exit 1
         cycle-without-termination-witness [fatal · defensible]
         unprotected-effect-in-cycle [error · defensible-a]
```

At v7 the diff showed one slot leaving one node; verification names the consequence — the
five-node component no longer carries a declared witness in any form, the same condition the
seeded defect 1 was caught under, reached here by evolution rather than by seeding. At v8
the escalated `check_booking` draws the *plain-cycle* condition rather than defect 2's
retry-region one: the lap re-enters this component at `book_flight` or `replan` and
recomputes on its way back around, and `check_booking` is not itself a re-entry target — the
[P-06 page](../validators/p06-effect-safety.md#retry-region-plain-cycle-or-neither) draws
that line precisely. Same component, different node, different condition: a diff could never
tell you that, and a validator run does.

## Report: the audit trail

The last leg writes the record an auditor reads without a `gebra` installation: one JSON run
report per stored version, the lineage document beside them, and a freshness check that the
store still describes the working definition:

<!-- gebra:example id=the-audit-trail -->
```python
import json
from datetime import datetime, timezone
from pathlib import Path

import gebra
from gebra.audit import export_store, freshness
from gebra.lineage import dump_lineage, lineage
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
for stage in EVOLUTION:
    snapshot(stage.build(), store=store, source=f"travel_booking:{stage.name}", extracted_at=pinned)

for exported in export_store(store):
    print(f"{exported.path.name:24} gate exit {exported.report.gate.exit_code}")

lineage_path = store.reports_dir / "lineage.json"
lineage_path.write_text(dump_lineage(lineage(store)), encoding="utf-8")
document = json.loads(lineage_path.read_text(encoding="utf-8"))
print()
print(
    "lineage.json  ",
    f"lineage_version {document['lineage_version']},",
    f"{document['total']} versions, current {document['current']}",
)
step = document["entries"][6]["step"]
print(
    "entry 1.2.2.3 ",
    f"from {step['previous']}: bump {step['bump_class']},",
    f"content_changed {step['content_changed']}",
)
print()
outcome = freshness(gebra.extract(EVOLUTION[-1].build()).ir, store=store)
print("freshness     ", outcome.state.value, "—", outcome.summary().splitlines()[0])
```

<!-- gebra:output id=the-audit-trail -->
```text
1.0.0.0.report.json      gate exit 0
1.0.0.1.report.json      gate exit 0
1.1.1.1.report.json      gate exit 0
1.2.1.1.report.json      gate exit 0
1.2.1.2.report.json      gate exit 0
1.2.1.3.report.json      gate exit 0
1.2.2.3.report.json      gate exit 1
1.2.3.3.report.json      gate exit 1

lineage.json   lineage_version 1.0, 8 versions, current 1.2.3.3
entry 1.2.2.3  from 1.2.1.3: bump ['F'], content_changed True

freshness      fresh — the store's current snapshot is the working definition
```

Each per-version report lists all thirteen catalog properties — five answered, eight with
their not-implemented markers — so the audit record says what was checked *and* what was
not. The lineage document is the version history as data: every version with its digest and
timestamp, and each step's bump class, in a version-locked vocabulary of its own
(`lineage_version 1.0`). Together the two files answer "what did each version verify as, and
what changed between versions" from the store alone. The names cannot collide: a per-version
report always ends `.report.json`. And the freshness check is the CI end of the story — in a
test suite it runs as the `gebra_freshness` marker and fails when the definition moved
without a new snapshot; here it confirms the store's `current` is the working definition.

## The whole scenario in one run

Everything above, in one pass and one process — the six legs in the order the acceptance
job runs them, each line derived from the objects it reports on:

<!-- gebra:example id=the-dod-scenario-in-one-run -->
```python
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path

import gebra
from gebra.audit import export_store, freshness
from gebra.lineage import compare, dump_lineage, lineage
from gebra.snapshot import SnapshotError, record
from gebra.store import SnapshotStore
from gebra.verify import PropertyReport, RunPolicy, StrictPolicy, verify
from gebra.versioning import Component
from tests.sample_workflows.travel_booking_defects import DEFECTS
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

store = SnapshotStore(Path(".gebra"))

stages = [gebra.extract(stage.build()) for stage in EVOLUTION]
variants = {defect: gebra.extract(defect.build()) for defect in DEFECTS}
warnings = sum(len(envelope.warnings) for envelope in (*stages, *variants.values()))
print(
    f"extract   {len(stages)} stages + {len(variants)} defect variants, {warnings} extraction warnings"
)

reports = [verify(envelope.ir) for envelope in stages]
caught = 0
for defect, envelope in variants.items():
    caught += any(
        isinstance(outcome, PropertyReport)
        and outcome.property == defect.property
        and outcome.failure is not None
        and outcome.failure.property_condition == defect.condition
        for outcome in verify(envelope.ir).properties
    )
strict_defect = next(defect for defect in DEFECTS if defect.strict_slug is not None)
promotion = RunPolicy(
    strict=StrictPolicy(mode="per-property", properties=(strict_defect.strict_slug,))
)
strict_exit = verify(variants[strict_defect].ir, promotion).gate.exit_code
print(
    f"verify    v1 gate {reports[0].gate.outcome}; {caught}/5 defects caught;",
    f"defect {strict_defect.number} exit {strict_exit} under its promotion",
)

versions, refused = [], []
for index, (stage, envelope, report) in enumerate(zip(EVOLUTION, stages, reports)):
    when = datetime(2026, 9, 1, 9, 0, index, tzinfo=timezone.utc)
    source = f"travel_booking:{stage.name}"
    try:
        outcome = record(
            envelope, store=store, source=source, extracted_at=when, eligibility=report
        )
    except SnapshotError:
        refused.append(stage.name)
        outcome = record(envelope, store=store, source=source, extracted_at=when, eligibility=None)
    versions.append(outcome.version)
print(f"snapshot  {versions[0]} recorded through the eligibility gate")
print(
    f"evolve    {len(versions) - 1} more versions; {len(refused)} refused with a report, recorded handed none"
)

steps, markers = [], set()
for before, after in pairwise(versions):
    diff = compare(store, before, after)
    steps.append("+".join(part.value for part in Component if part in diff.bump_class))
    markers.add(f"{diff.evolution_safety.property_id} {diff.evolution_safety.status}")
print(
    f"diff      {len(steps)} steps: {', '.join(steps)}; every diff carries {', '.join(sorted(markers))}"
)

exports = export_store(store)
(store.reports_dir / "lineage.json").write_text(dump_lineage(lineage(store)), encoding="utf-8")
state = freshness(stages[-1].ir, store=store).state.value
print(f"report    {len(exports)} audit reports + lineage.json in the store; freshness {state}")
```

<!-- gebra:output id=the-dod-scenario-in-one-run -->
```text
extract   8 stages + 5 defect variants, 0 extraction warnings
verify    v1 gate pass; 5/5 defects caught; defect 3 exit 1 under its promotion
snapshot  1.0.0.0 recorded through the eligibility gate
evolve    7 more versions; 2 refused with a report, recorded handed none
diff      7 steps: E, S+F, S, E, E, F, F; every diff carries P-12 deferred-to-phase-1
report    8 audit reports + lineage.json in the store; freshness fresh
```

Thirteen extractions, fourteen verify runs (one of them under the promotion), eight recorded
versions, seven diffs re-derived from the store's files, eight audit reports and a lineage
document — and every number on those six lines is computed by the code above it, in a child
interpreter where any executed node body would have failed the run.

## The same assets gate this repository

This sequence is not written for this page and demonstrated in CI as a courtesy — it is the
repository's Definition-of-Done scenario, and the dependency points the other way. A
dedicated CI job (`dod` in `.github/workflows/ci.yml`) runs `pytest tests/dod
tests/evolution -q` on every push, on the designated matrix cell (py3.13 / cell 3), under a
five-minute `timeout-minutes` budget. That harness imports the same `DEFECTS` and
`EVOLUTION` tables the examples above loop over, asserts every catch this page shows —
property, condition, location and gate, negative-tested so an uncaught defect fails the
harness — and re-derives every label, bump class and refusal.

This page adds no assets on top of that. No example above builds a graph of its own; every
subject is imported from the three fixture modules the acceptance job runs, and the
transcripts are produced by executing the shown code in CI. If a defect construction, an
evolution stage or a classification ever changed, the acceptance harness and this page would
fail together, on the same commit — which is the sense in which this tutorial cannot drift
from the behavior it narrates.

## What this scenario does not claim

Three boundaries, kept everywhere above and worth restating in one place.

**A witness is presence, not a proof of behavior.** v1's P-02 pass records that a bound is
*declared* — the `variant` annotation on `replan` — and the v7 finding records that no such
declaration covers the component. Neither is a statement about whether any run halts; the
measure is attested by the author and trusted, never checked.

**No output grades a change.** The bump classes route a reader to the right section of a
diff body; the safe-or-breaking classification of a version pair is P-12, outside this
release, and every diff above carries its `not checked` marker in the slot where that
verdict would go. The words "additive", "breaking case" and "a reviewer would stop on" in
this page's prose are editorial framing of the sequence — mine, not any tool's.

**A marker is not a pass.** Eight catalog properties answer `not-implemented:
deferred-to-phase-1` in every verify run and every audit report on this page. They are never
counted as passed, and a question that was not asked is reported as exactly that.

## Where this page is checked

Every transcript above is produced by the code block above it, executed in a fresh, guarded
child interpreter in CI and compared byte for byte against the page — the mechanism is
[executable examples](../contributing/executable-examples.md). Beyond that,
`tests/docs/test_travel_booking_tutorial.py` pins the page to the scenario's own sources:
every defect fact to the `DEFECTS` table and to a fresh verify run per variant, the
evolution labels and bump classes to `EVOLUTION`, the four rendered diffs byte for byte
against the verb, the refusal reason to the recorder's own vocabulary, the CI-job facts to
the workflow file, and the boundary sentences above to the page's text — while asserting
that no example here constructs a graph of its own, which is what keeps "same assets as the
scenario" true by mechanism rather than by intention. A statement on this page that stopped
being true fails the build rather than aging quietly.
