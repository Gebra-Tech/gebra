# Verify and interpret

[Contracts and annotations](contracts-and-annotations.md) ended with a graph whose every slot
was declared rather than guessed. This page is what that buys. It runs the five validators this
release implements over a real, fully-declared agent, and then reads what comes back — first a
report where everything passes, then five where something does not.

The question this page is written to answer is the one a reader of a failing build actually has:
**for any line in a verify report, what exactly is being claimed, and on what evidence?**
Every answer here is printed by code the CI run executes.

Nothing on this page runs a workflow. `gebra.extract()` reads the definition without invoking a
node, a router, a tool or a model, and a validator only ever reads the serialized IR that
extraction produced. The agent's node bodies raise if anything calls them, and CI checks that
nothing did.

!!! note "Section numbers, and where they point"

    `§` references are to **PROPERTY-CATALOG-SPEC** unless another specification is named;
    `§1.2`-style references to the run-level wrapper are **REPORT-FORMAT-SPEC**'s. Those are
    internal contract documents and are not published with this site — the numbers are here so
    a statement can be *checked* against them rather than taken on trust. The transcripts are
    not spec-derived: they are what this release printed.

!!! note "Following along"

    The agent below is `tests/sample_workflows/travel_booking.py` in this repository — the same
    definition the acceptance scenario verifies, so nothing here can drift from a copy. To run the
    examples yourself, clone the repository and put its root on `PYTHONPATH`. If you would
    rather work on your own graph, everything on this page applies unchanged; only the node
    names differ.

## One call, one report

`verify()` takes one IR and returns one **run report**. Not a boolean, not a list of strings: a
structured record with the subject it was run over, an outcome for every property in the
catalog, and a gate derived from those outcomes.

<!-- gebra:example id=one-run-report -->
```python
import gebra
from gebra.verify import PropertyReport, RunPolicy, SubjectRef, verify
from tests.sample_workflows.travel_booking import build_travel_booking_agent

extracted = gebra.extract(build_travel_booking_agent())
report = verify(
    extracted.ir,
    RunPolicy(
        subject=SubjectRef(
            source="tests.sample_workflows.travel_booking:build_travel_booking_agent",
            input_mode="extracted",
            extractor_version=gebra.__version__,
        )
    ),
)

subject, gate, counts = report.subject, report.gate, report.gate.counts
verdicts = [item for item in report.properties if isinstance(item, PropertyReport)]
markers = [item for item in report.properties if not isinstance(item, PropertyReport)]

print(f"report_format  {report.report_format}, tool {report.tool.name}")
print(f"subject        {subject.input_mode}, ir_version {subject.ir_version}")
print(f"digest         {subject.graph_version[:7]}… ({len(subject.graph_version)} characters)")
print(f"outcomes       {len(verdicts)} verdicts + {len(markers)} markers")
for outcome in verdicts:
    print(f"                 {outcome.property:22}{outcome.result}")
print(f"extraction     {len(extracted.warnings)} warning(s)")
print(f"gate           {gate.outcome}, exit {gate.exit_code}")
print(f"counts         {counts.fatal} fatal, {counts.error} error, {counts.warning} warning")
print(f"snapshot       {'eligible' if gate.snapshot_eligible else 'suppressed'}")
print(f"best_effort    {report.best_effort or '(empty — P-01 is clean)'}")
```

<!-- gebra:output id=one-run-report -->
```text
report_format  1.1, tool gebra
subject        extracted, ir_version 1.0
digest         sha256:… (71 characters)
outcomes       5 verdicts + 8 markers
                 graph-well-formed     pass
                 termination-witness   pass
                 dataflow-completeness pass
                 effect-safety         pass
                 determinism-replay    pass
extraction     0 warning(s)
gate           pass, exit 0
counts         0 fatal, 0 error, 0 warning
snapshot       eligible
best_effort    (empty — P-01 is clean)
```

Five things in that transcript are worth naming before anything else.

**Thirteen outcomes, five verdicts.** The catalog holds thirteen properties and this release
implements five; the other eight are outside Phase-0 scope (SOW §8) and answer with a structured
*not-implemented marker* rather than silence. A marker is not a pass, is never counted in a
passed tally, and takes no part in the exit code (REPORT-FORMAT-SPEC §2.2, §4.6 rule 5). A
property nobody has written never reports a quiet success.

**The subject is provenance, not a claim.** `input_mode`, the source label, `ir_version` and the
`graph_version` digest say *what was verified*. The label is a caller-supplied name and not a
locator to resolve — `verify()` never invents one — while the digest is computed from the IR
itself, so a run is attributed by the label and identified by the digest: the label is the
caller's word, the digest is the IR's (REPORT-FORMAT-SPEC §1.3). What that digest covers is
[the IR and graph_version](../concepts/ir-and-graph-version.md)'s subject; here it is only an
identity.

**The gate is derived, not decided per property.** A validator answers one question and never
sees a policy flag; the exit code, the outcome word, the severity tally and the snapshot
eligibility are all computed over the finished outcomes (§0.2; REPORT-FORMAT-SPEC §2.1–§2.5).
Nothing
in the per-property records moves when the gate does — a separation this page returns to under
[strict mode](#strict-mode-moves-the-gate-never-the-record).

**Snapshot eligibility is a signal, not an action.** `verify()` records nothing anywhere; the
field says whether a FATAL finding was present, and `gebra snapshot` is what reads it and
refuses (§0.2; REPORT-FORMAT-SPEC §2.5).

**Zero extraction warnings is the annotation tutorial's payoff.** Every node of this agent
declares its reads, writes and effects, so nothing was inferred or defaulted — which means the
contracts P-04 and P-06 read below are the ones the author wrote, not conservative defaults.

## A pass carries a witness

A passing property does not return a bit. It returns a **witness**: structured, re-checkable
evidence for the thing it just decided, plus any caveat its claim class requires (§0.3).
Witnesses and failures are values, never prose — display text appears only in fields marked
display-only.

That is worth reading rather than trusting, because a witness is where you find out *why* a
property passed — and, sometimes, that it passed for a reason you did not expect.

<!-- gebra:example id=five-witnesses -->
```python
import gebra
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.travel_booking import build_travel_booking_agent

report = verify(gebra.extract(build_travel_booking_agent()).ir)
witnesses = {
    outcome.property: outcome.witness
    for outcome in report.properties
    if isinstance(outcome, PropertyReport) and outcome.witness is not None
}

p01 = witnesses["graph-well-formed"]
print(f"P-01  witness kind {p01.kind}")
print(f"      reachable from START  {len(p01.reachable_from_start)} nodes")
print(f"      terminal nodes        {', '.join(p01.terminal_nodes)}")
print(f"      orphan nodes          {list(p01.orphan_nodes)}  <- evaluated, and empty")
print(f"      unresolved targets    {list(p01.unresolved_targets)}  <- evaluated, and empty")

p02 = witnesses["termination-witness"]
print(f"P-02  witness kind {p02.kind}")
for entry in p02.inventory:
    print(f"      inventory entry       form ({entry.form}) on node {entry.element.node}")
    print(f"        declared key        {entry.source.variant.key}")
    print(f"        declared measure    {entry.source.variant.measure}")
    print(f"        discharges          {entry.discharges}")
census = p02.cycles
print(f"      certificate           {len(p02.certificate)} vertices, last {p02.certificate[-1]}")
print(f"      cycle census          exhaustive={census.exhaustive}, {len(census.cycles)} cycles")
print(f"      notes                 {list(p02.notes)}")

p04 = witnesses["dataflow-completeness"]
print(f"P-04  witness kind {p04.kind}, {len(p04.coverage)} (reader, key) obligations:")
for entry in p04.coverage:
    if (entry.node, entry.key) in {("check_booking", "flight_id"), ("replan", "replan_budget")}:
        obligation = f"{entry.node} reads {entry.key}"
        print(f"      {obligation:37} covered by {', '.join(entry.satisfied_by)}")

p06 = witnesses["effect-safety"]
print(f"P-06  witness kind {p06.kind}, {len(p06.cycles)} cycle, {len(p06.effects)} tagged nodes")
for record in p06.effects:
    bound_to = record.key or record.hook
    print(f"      {record.node:21} {list(record.effect)}")
    print(f"        region {record.region}, protection {record.protection}: {bound_to}")

p08 = witnesses["determinism-replay"]
print(f"P-08  witness kind {p08.kind}, claim_class {p08.claim_class} carried in-band")
for claim in p08.claims:
    pinned = f"seed {claim.seed}, temperature {claim.temperature}"
    evidence = pinned if claim.llm_backed else claim.basis
    print(f"      {claim.node:21} llm_backed={claim.llm_backed!s:6}{evidence}")
print(f"      caveat                {p08.caveat}")
```

<!-- gebra:output id=five-witnesses -->
```text
P-01  witness kind well-formedness
      reachable from START  9 nodes
      terminal nodes        notify_traveler, release_hotel_hold
      orphan nodes          []  <- evaluated, and empty
      unresolved targets    []  <- evaluated, and empty
P-02  witness kind termination
      inventory entry       form (c) on node replan
        declared key        replan_budget
        declared measure    replan_budget strictly decreases each lap (one replanning attempt consumed)
        discharges          all-simple-cycles-through-element
      certificate           10 vertices, last END
      cycle census          exhaustive=True, 2 cycles
      notes                 []
P-04  witness kind dataflow, 18 (reader, key) obligations:
      check_booking reads flight_id         covered by book_flight
      replan reads replan_budget            covered by START
P-06  witness kind effect-safety, 1 cycle, 2 tagged nodes
      book_flight           ['irreversible', 'billable', 'network']
        region retry, protection idempotency_key: booking_request_id
      book_hotel            ['billable', 'network']
        region cycle, protection compensation_hook: release_hotel_hold
P-08  witness kind determinism, claim_class heuristic carried in-band
      classify_request      llm_backed=True  seed 42, temperature 0.0
      compile_itinerary     llm_backed=False pure-local-computation
      caveat                provider-seed-reproducibility-not-guaranteed
```

Read that transcript property by property; each one shows a different shape of evidence.

**P-01's two empty lists are not padding.** `orphan_nodes` and `unresolved_targets` being empty
is the re-checkable record that those conditions were *evaluated* and found clean. A pass bit
would have lost the difference between "checked and clean" and "not looked at".

**P-02's evidence is an inventory plus a certificate.** One entry, form (c): the `variant`
annotation on `replan`, its declared key, and the measure its author wrote. `discharges` says
what that entry covers — every simple cycle running through the carrier node — and both of this
graph's cycles do. The certificate is a topological order of the graph with the witnessed
elements removed, which any consumer can re-check in linear time without trusting the checker.
What the entry records is the **declaration**: the measure is attested by the author, and
recorded as attested. `notes` is empty here; it is where P-02 puts structured qualifications when
it has any, and one of its note kinds is promotable at the gate.

**P-04's coverage is one entry per obligation.** Eighteen `(reader, key)` pairs, each with the
writers that cover it on every path. `replan reads replan_budget` is `covered by START` because
`replan_budget` is one of this agent's four declared graph inputs, which §P-04 treats as written
at the boundary (the IR-level criterion is `state[key].optional == true`, §4.2). Seven of the
eighteen rows are covered that way; the other eleven name writer nodes. A pass here is only as
strong as the reads and writes the contracts declared — that is what DEFENSIBLE-A means, and the
next section makes it concrete.

**P-06 records both protection kinds, and where each node sits.** `book_flight` is
`irreversible` and `billable` inside a retry region, protected by an idempotency key that is
among its declared reads; `book_hotel` is `billable` in a cycle, protected by a compensation
hook naming an existing node. Protection is *binding*, not presence: a key that is not a
declared read, or a hook naming no node, is not protection, and the record names the key or the
hook it was satisfied by so you can check which one applied.

**P-08's witness carries its own claim class and a mandatory caveat.** Two claims: one LLM-backed
with `seed` and `temperature` pinned, one not LLM-backed and so under no pinning obligation. The
`caveat` field is required exactly when some claim is LLM-backed (§8.3) — a pinned seed is what
the *definition* declares, and what a provider returns on replay is not decidable from the
definition.

## A failure names a condition and a locus

The other half of the envelope. A failing property fills `failure` with a structured record: the
violated **condition ID**, the **location** it was found at, its **severity** and its **claim
class** — and, where the catalog gives one, display-only remediation prose (§0.3).

The five variants below are this repository's seeded-defect suite: the travel-booking agent with
exactly one thing broken in each, one per acceptance defect.

<!-- gebra:example id=reading-a-failure -->
```python
import gebra
from gebra.verify import Failure, PropertyReport, to_data, verify
from tests.sample_workflows.travel_booking_defects import DEFECTS

for variant in DEFECTS:
    report = verify(gebra.extract(variant.build()).ir)
    for outcome in report.properties:
        if not (isinstance(outcome, PropertyReport) and outcome.result == "fail"):
            continue
        failure = outcome.failure
        location = to_data(failure.location)
        print(f"defect {variant.number}  {outcome.property}")
        print(f"  condition     {failure.property_condition}")
        print(f"  severity      {failure.severity}, claim class {failure.claim_class}")
        print(f"  locus         anchored on a {location.pop('kind')}")
        for name, value in location.items():
            print(f"                {name:22} {value}")
        for name in type(failure).model_fields:
            value = getattr(failure, name)
            if name not in Failure.model_fields and value is not None:
                print(f"  extra field   {name} = {value}")
        print(f"  remediation   {'carried' if failure.remediation else 'none carried'}")
        co_findings = len(failure.co_failures or ())
        advisories = len(failure.advisories or ())
        print(f"  also on it    {co_findings} co-finding(s), {advisories} advisory(ies)")
```

<!-- gebra:output id=reading-a-failure -->
```text
defect 1  termination-witness
  condition     cycle-without-termination-witness
  severity      fatal, claim class defensible
  locus         anchored on a scc
                nodes                  ['availability_check', 'book_flight', 'book_hotel', 'check_booking', 'replan']
                representative_cycle   ['availability_check', 'book_flight', 'book_hotel', 'check_booking', 'replan']
                exhaustive             False
  remediation   none carried
  also on it    0 co-finding(s), 0 advisory(ies)
defect 2  effect-safety
  condition     unprotected-effect-in-retry-region
  severity      error, claim class defensible-a
  locus         anchored on a node
                node                   book_flight
                effect                 ['irreversible', 'billable', 'network']
                cycle                  ['availability_check', 'book_flight', 'book_hotel', 'check_booking', 'replan']
  remediation   none carried
  also on it    0 co-finding(s), 0 advisory(ies)
defect 3  determinism-replay
  condition     deterministic-llm-temperature-unpinned
  severity      warning, claim class heuristic
  locus         anchored on a node
                node                   classify_request
                annotation             deterministic
                seed                   42
  remediation   carried
  also on it    0 co-finding(s), 0 advisory(ies)
defect 4  dataflow-completeness
  condition     read-key-never-written-on-path
  severity      fatal, claim class defensible-a
  locus         anchored on a state-key
                key                    itinerary
                node                   notify_traveler
                path                   ['START', 'classify_request', 'availability_check', 'notify_traveler']
  extra field   writers_on_other_paths = ('compile_itinerary',)
  remediation   none carried
  also on it    0 co-finding(s), 0 advisory(ies)
defect 5  effect-safety
  condition     unprotected-effect-in-retry-region
  severity      error, claim class defensible-a
  locus         anchored on a node
                node                   book_leg
                effect                 ['billable', 'network']
                cycle                  ['availability_check', 'dispatch_bookings', 'book_leg', 'check_booking', 'replan']
                fanout                 send
  remediation   none carried
  also on it    0 co-finding(s), 0 advisory(ies)
```

**The locus is typed, and the type is information.** A location is one of six structural anchors
— node, edge, cycle, SCC, state-key, path — and which one a finding uses tells you what kind of
thing is wrong. Defect 1 anchors on an **SCC**, not a node: no single node is at fault. The
component named is what survived after every declared witness was removed, and the claim is that
at least one simple cycle inside it carries no declared witness — `representative_cycle` is that
cycle. Accounting is per simple cycle, never per component: a witnessed outer loop never
discharges an unwitnessed bypass cycle in the same component (DEC-05 D1; TERMINATION-WITNESS-SPEC
§5). Defect 4 anchors on a **state-key** with the node that reads it and one `START`-rooted path
on which nothing wrote it; the key, not the node, is the subject. Defects 2 and 5 anchor on the
offending **node**.

**Each anchor carries what its condition was decided from, plus the context that makes it
legible.** Defect 2's locus carries the node's full declared effect set and the cycle it sits in
— `network` is context, not an obligation: only `billable` and `irreversible` trigger P-06 at all
(§6.3). Defect 5's carries `fanout: send`, because reaching that node through a fan-out edge is
part of why it is inside a retry region; defect 3's carries the annotation that made the claim and
the seed that was pinned. Defect 1's `exhaustive: False` is a statement about the *report*, not
the graph: the finding carries one representative witness-free simple cycle per residual
component, and the component may hold more — so a re-run after a fix surfaces the next one, if
any. Nothing was enumerated to learn that; P-02's fail path never enumerates cycles (§2.3;
TERMINATION-WITNESS-SPEC §6.1, §6.4). The `exhaustive=True` on the earlier pass witness is a
different field — the optional cycle census, complete only because this graph's cycle count fell
under the census cap (§2.5; TERMINATION-WITNESS-SPEC §6.3). A location never names a vertex the
document does not carry.

**A property may extend the record with its own evidence field.** P-04's
`writers_on_other_paths` names `compile_itinerary` — a node that *does* write `itinerary`, just
not on the path in the locus. That single field is the difference between "you forgot to write
this key" and "you added a route that skips the node that writes it", which is exactly what this
defect did.

**Remediation is display-only prose, and optional.** Only defect 3 carries one. It is text for a
person; nothing parses it, and its absence is not a gap in the record — the condition ID is the
machine-readable half and it is always there.

**Findings are never dropped.** A property reports once, with the deterministically-first finding
in `failure` and every further same-property finding on `co_failures`; `advisories` carries
WARNING-class side findings from *other* properties. Each of those records carries its own
severity and claim class, so a side finding can never be read as the primary one. These variants
each seed exactly one defect, so `co_failures` is empty throughout. `advisories` is empty on every
run of this release for a different reason: `verify()` assembles no cross-property advisories,
because which host report a WARNING-grade finding rides is not fixed by any frozen spec
(REPORT-FORMAT-SPEC §3.2). Nothing is lost by that — carriage never removes the source record, and
the run report carries all thirteen outcomes.

## Where a claim class is actually written down

A claim class says what kind of evidence a verdict rests on: **DEFENSIBLE** is decidable over the
IR alone, **DEFENSIBLE-A** over the IR plus what the code declared about itself, and **HEURISTIC**
is advisory lint with no proof claim (§0.1). The full definitions are on
[what gebra checks](../concepts/what-gebra-checks.md); what matters when you are reading a report
is *where the class comes from*, and the answer is two frozen tables rather than the validator's
own opinion.

<!-- gebra:example id=claim-classes -->
```python
from gebra.verify import WEDGE_SLUGS, conditions_for, property_entry

print("the property table — what the catalog grades each property's verdicts as")
for slug in WEDGE_SLUGS:
    entry = property_entry(slug)
    classes = ", ".join(entry.claim_classes)
    severities = ", ".join(entry.severities)
    print(f"  {entry.property_id} {slug:22} {classes:13} severities: {severities}")

print()
print("the condition registry — what each finding is graded as")
registered = [entry for slug in WEDGE_SLUGS for entry in conditions_for(slug)]
for entry in registered:
    print(f"  {entry.id:39}{entry.severity:8}{entry.claim_class}")
emittable = [entry for entry in registered if entry.emittable]
print(f"  {len(emittable)} of those {len(registered)} strings may be emitted by this release")
```

<!-- gebra:output id=claim-classes -->
```text
the property table — what the catalog grades each property's verdicts as
  P-01 graph-well-formed      defensible    severities: fatal
  P-02 termination-witness    defensible    severities: fatal
  P-04 dataflow-completeness  defensible-a  severities: fatal
  P-06 effect-safety          defensible-a  severities: fatal, error
  P-08 determinism-replay     heuristic     severities: warning

the condition registry — what each finding is graded as
  node-unreachable-from-start            fatal   defensible
  dead-end-node-not-wired-to-end         fatal   defensible
  path-map-target-undefined              fatal   defensible
  orphan-node                            fatal   defensible
  edge-target-undefined                  fatal   defensible
  cycle-without-termination-witness      fatal   defensible
  counter-guard-without-exit-edge        fatal   defensible
  read-key-never-written-on-path         fatal   defensible-a
  unprotected-effect-in-cycle            error   defensible-a
  unprotected-effect-in-retry-region     error   defensible-a
  irreversible-with-keyless-idempotent   fatal   defensible-a
  deterministic-llm-seed-unpinned        warning heuristic
  deterministic-llm-temperature-unpinned warning heuristic
  13 of those 13 strings may be emitted by this release
```

All three classes appear in real reports on this page. **DEFENSIBLE** graded defect 1: a cycle
either carries a declared witness in the document or it does not, and reading the document settles
it — the topology, plus the declared bound wherever the author put it. **DEFENSIBLE-A** graded
defects 2, 4 and 5: each rests on the contracts the nodes
declared — the effect tags, the idempotency key, the reads and writes. gebra checks that those
declarations are coherent with the graph; it does not check that they are true of the function
body, exactly as a type annotation is trusted rather than proved (§0.1; ANNOTATION-API-SPEC §5).
**HEURISTIC** graded defect 3: an unpinned temperature beside a determinism claim is a lint, and
the catalog says so.

Three practical consequences of those tables:

- **A finding's grade is read off the registry, never restated by the validator.** The severity
  and the claim class in the transcripts above are the registry's cells for that condition ID.
  Two conditions of one property can differ: P-06's unprotected-effect conditions are ERROR, and
  its `irreversible` + keyless-`idempotent` contradiction is FATAL.
- **A passing report carries no per-record grade, so a pass is displayed under the property's
  catalog class** — the left-hand table. The one exception is P-08, whose witness carries
  `claim_class: heuristic` in-band, as the transcript in the previous section shows.
- **The condition-ID vocabulary is closed.** A validator may not emit a string absent from the
  registry, and adding, renaming or promoting one is a specification amendment with its own
  decision record. That is not housekeeping: these strings are the SARIF `rule.id` namespace
  (§0.5), and a downstream consumer's alert deduplication turns on the id being identical
  between analyses, so a string that drifted between releases would silently split one finding
  into two. The registry also holds names reserved for properties whose sections are not merged;
  those are held, not emittable (§0.4), which is why the count above is over the wedge's own
  entries rather than the whole table.

## Strict mode moves the gate, never the record

Defect 3 is a real defect — a node claiming determinism it has not pinned — and by default it
exits `0`. Whether that should fail a build is a policy question, and `--gebra-strict` is where
policy lives: bare, it promotes every WARNING in the run; with a slug list, only the named
properties' WARNINGs (§0.2). The same defect, under four policies:

<!-- gebra:example id=strict-mode -->
```python
import gebra
from gebra.verify import STRICT_ALL, STRICT_OFF, RunPolicy, StrictPolicy, verify
from tests.sample_workflows.travel_booking_defects import build_defect_3_false_determinism

ir = gebra.extract(build_defect_3_false_determinism()).ir
another = StrictPolicy(mode="per-property", properties=("effect-safety",))
this_one = StrictPolicy(mode="per-property", properties=("determinism-replay",))
policies = (
    ("(no flag)", STRICT_OFF),
    ("--gebra-strict", STRICT_ALL),
    ("--gebra-strict=effect-safety", another),
    ("--gebra-strict=determinism-replay", this_one),
)

records = set()
for label, strict in policies:
    report = verify(ir, RunPolicy(strict=strict))
    record = report.outcome_for("determinism-replay").failure
    gate = report.gate
    records.add(
        (record.property_condition, record.severity, record.claim_class, gate.counts.warning)
    )
    promoted = ", ".join(f"{item.property}/{item.origin}" for item in gate.promotions)
    print(f"{label:34} exit {gate.exit_code}  {gate.outcome:16} promoted: {promoted or 'nothing'}")

print()
print(f"distinct (condition, severity, claim class, warning tally): {len(records)}")
for record in records:
    print(f"  {record}")
```

<!-- gebra:output id=strict-mode -->
```text
(no flag)                          exit 0  pass-with-notes  promoted: nothing
--gebra-strict                     exit 1  fail             promoted: determinism-replay/failure
--gebra-strict=effect-safety       exit 0  pass-with-notes  promoted: nothing
--gebra-strict=determinism-replay  exit 1  fail             promoted: determinism-replay/failure

distinct (condition, severity, claim class, warning tally): 1
  ('deterministic-llm-temperature-unpinned', 'warning', 'heuristic', 1)
```

The exit code moved twice. The record moved never — and that is the point the last two lines
make mechanically rather than by assertion: the four runs produced **one** distinct
`(condition, severity, claim class, warning tally)` tuple between them. A promoted finding keeps
`severity: warning` and `claim_class: heuristic` where it stands, and the severity tally is
unchanged, because rewriting a HEURISTIC advisory into an ERROR would claim more than the check
supports (§0.2). Strictness is a statement about your pipeline, not about the evidence.

Two details the transcript shows in passing. The third row is the useful negative: a per-property
flag naming a *different* property promotes nothing, so a team can gate on one lint without
gating on all of them. And a `Promotion` is a **pointer**, not a second finding — it names the
owning property and where the promoted record was carried (here, `failure`), and carries no
severity or claim class of its own, because the record it points at still has both.

Promotion reaches WARNING-grade records wherever they surface, and the policy matches on the
record's **owning** property: WARNING failures, same-property co-findings, cross-property
advisories (matched on the advisory's own property, never its host's), and WARNING-grade witness
notes on either result path (§0.2; REPORT-FORMAT-SPEC §2.1, §2.3). The advisory row is the rule
rather than something a run here shows — this release assembles none (REPORT-FORMAT-SPEC §3.2).
The note row is the surprising case: a report where nothing failed can still gate `1` under a
strict flag naming the property whose witness carried the note, with the report, the witness and
the note all unchanged (§0.2; TERMINATION-WITNESS-SPEC §6.1).

## When P-01 fails, three reports become diagnostics

P-02, P-04 and P-06 all build the graph, and the specification defines their results **only over
P-01-clean topology**; where P-01 fails, their reports on that IR are best-effort diagnostics
rather than contract-bearing verdicts (§0.3). A run says so itself rather than leaving it to the
reader.

To see it, the example edits the extracted IR **document** rather than the agent — dropping
`release_hotel_hold` from the wired-to-`END` set leaves it a dead end — and hands the result
straight to `verify()`.

<!-- gebra:example id=p01-precondition -->
```python
import json

import gebra
from gebra.ir import WorkflowIR, dump_json, load_json
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.travel_booking import build_travel_booking_agent

document = json.loads(dump_json(gebra.extract(build_travel_booking_agent()).ir))
print("finish, as extracted:", document["finish"])
document["finish"] = ["notify_traveler"]
report = verify(load_json(WorkflowIR, json.dumps(document)))

for outcome in report.properties:
    if isinstance(outcome, PropertyReport) and outcome.result == "fail":
        failure = outcome.failure
        node = failure.location.node
        print(f"finding      {outcome.property} / {failure.property_condition}")
        print(f"             {failure.severity}, {failure.claim_class}, at node {node}")
print(f"gate         {report.gate.outcome}, exit {report.gate.exit_code}")
print(f"snapshot     {'eligible' if report.gate.snapshot_eligible else 'suppressed'}")
print(f"best_effort  {', '.join(report.best_effort)}")
for slug in report.best_effort:
    result = report.outcome_for(slug).result
    print(f"             {slug:22} says {result} — a diagnostic on this run")
```

<!-- gebra:output id=p01-precondition -->
```text
finish, as extracted: ['notify_traveler', 'release_hotel_hold']
finding      graph-well-formed / dead-end-node-not-wired-to-end
             fatal, defensible, at node release_hotel_hold
gate         fail, exit 1
snapshot     suppressed
best_effort  termination-witness, dataflow-completeness, effect-safety
             termination-witness    says pass — a diagnostic on this run
             dataflow-completeness  says pass — a diagnostic on this run
             effect-safety          says pass — a diagnostic on this run
```

Three passes that mean less than they look like. The three properties still ran and still
reported, but `best_effort` names them, and the honest reading of those rows is "no problem was
found while walking a graph that is not well-formed" — not "this graph satisfies the property".
Fix the P-01 finding and re-run before drawing any conclusion from them. The field is empty on
every P-01-clean run, including the very first transcript on this page.

Two other things happen at once here, both already familiar: the FATAL finding fails the gate,
and it makes the run ineligible for a snapshot (§0.2; REPORT-FORMAT-SPEC §2.5) — the only severity that does.

## The report a person reads

Everything so far has been the structured record. `gebra verify` renders that same record for a
terminal, and the rendering is a projection of the envelope, never a re-derivation of it: the
claim class is displayed with every verdict and every finding, and the tally, the exit code and
the promotion list are read off the gate rather than recounted.

The example below renders two of the seeded defects and prints three blocks of one and one of the
other, so the excerpts here are literally slices of the real output.

<!-- gebra:example id=the-rendered-report -->
```python
import gebra
from gebra.report import TerminalOptions, render_human
from gebra.verify import verify
from tests.sample_workflows.travel_booking_defects import (
    build_defect_1_unwitnessed_cycle,
    build_defect_3_false_determinism,
)

TERMINAL = TerminalOptions(color=False, width=100)


def block(rendering: str, heading: str) -> str:
    """One section of the rendered report — its blocks are separated by blank lines."""
    for section in rendering.split("\n\n"):
        if section.startswith(heading):
            return section
    raise LookupError(heading)


unwitnessed = render_human(verify(gebra.extract(build_defect_1_unwitnessed_cycle()).ir), TERMINAL)
print(block(unwitnessed, "P-01 graph-well-formed"))
print()
print(block(unwitnessed, "P-02 termination-witness"))
print()
print(block(unwitnessed, "summary"))
print()
unpinned = render_human(verify(gebra.extract(build_defect_3_false_determinism()).ir), TERMINAL)
print(block(unpinned, "P-08 determinism-replay"))
```

<!-- gebra:output id=the-rendered-report -->
```text
P-01 graph-well-formed — pass  [DEFENSIBLE]
  witness                 9 nodes reachable from START | 2 terminal nodes | no orphan nodes | no 
unresolved targets
    reachable from START    9 nodes: availability_check, book_flight, book_hotel, check_booking, 
classify_request, compile_itinerary, notify_traveler, release_hotel_hold, replan
    terminal nodes          notify_traveler, release_hotel_hold
    orphan check            evaluated — no node stands outside every edge
    reference check         evaluated — every edge and path_map target resolves

P-02 termination-witness — fail  (1 finding: 1 fatal)
  fatal: cycle-without-termination-witness  [P-02 termination-witness | DEFENSIBLE]
    component               availability_check, book_flight, book_hotel, check_booking, replan
    representative          availability_check -> book_flight -> book_hotel -> check_booking -> 
replan -> availability_check
    cycle list              not exhaustive — a re-run after a fix may surface another
    finding                 Simple cycle carries no declared termination witness

summary
  findings                1 fatal | 0 error | 0 warning
  notes                   0 carried (0 warning-grade)
  properties              5 reported | 8 produced no verdict
  strict                  off
  exit                    1 — a FATAL or ERROR finding is present, or a strict policy promoted a 
warning
  snapshot                not recorded for this run: a FATAL finding is present 
(PROPERTY-CATALOG-SPEC §0.2)


P-08 determinism-replay — fail  (1 finding: 1 warning)
  warning: deterministic-llm-temperature-unpinned  [P-08 determinism-replay | HEURISTIC]
    node                    classify_request
    declared                annotation deterministic | seed 42
    finding                 Determinism declared with a seed but no pinned temperature
    remediation             The claim is recorded. Replay divergence must be logged, never silently 
accepted. Keep the annotation if you accept approximate determinism; remove it if replay 
reproducibility should not be relied on.
```

Every field in those blocks came from a structure earlier on this page. `[DEFENSIBLE]` beside the
P-01 pass is the property table's class, because a pass carries no per-record grade;
`[P-02 termination-witness | DEFENSIBLE]` beside the FATAL finding is the record's own. The
`component` and `representative` lines are the SCC locus rendered; `cycle list` is that
`exhaustive: False` field, rendered as what it means. The summary's severity tally, exit code and
promotion list are read off `gate` rather than recounted. The width is the only thing set by hand
here — a real terminal supplies its own, and styling is the only thing that changes when one is
not available.

`--format json` writes the same run report losslessly, and `--format sarif` writes the
findings-only projection a code-scanning UI reads. Two things do not survive that projection:
pass-witnesses, because SARIF has no witness structure, and not-implemented markers, because a
rule with no result would advertise a check that did not run. So the envelope stays the source of
truth and SARIF is derived from it, never round-tripped.

## What a finding does not claim

This is the boundary the project is organised around, and it is a hard one (SOW §6). Four
statements, each of which the transcripts above show rather than assert.

**Witness presence, never semantic termination.** P-02 decides exactly one question: does every
simple cycle carry a declared termination witness? Presence of the declaration is decidable from
the document, and that is the whole claim. Whether a declared guard ever evaluates true at run
time, whether the counter it names is really advanced, whether the loop variant on `replan`
really decreases — all of that is trusted, never checked (TERMINATION-WITNESS-SPEC §1.1). Look at
the two P-02 transcripts on this page: the pass records *a declared measure* on a carrier node,
and the failure says *"Simple cycle carries no declared termination witness"*. Neither sentence
is about what a run does, and the stronger phrasings are banned by name in findings, docs and
marketing alike, with a lint in this repository enforcing the ban (TERMINATION-WITNESS-SPEC §7;
WA-06).

**A DEFENSIBLE-A pass is a statement about declarations.** P-04 and P-06 read the contracts the
nodes declared. `book_flight`'s P-06 record says an idempotency key is declared and bound to a
declared read — not that the booking call is idempotent. If the declaration is false, the finding
is still correct about the document and wrong about the world, and that is the trade the class
names openly.

**Some passes are vacuous, and the witness says which.** P-02 over an acyclic graph passes
because there was no cycle for a bound to be declared on, not because a bound was found. The
witness is what tells those two apart: it carries the inventory of declared witnesses beside the
acyclicity certificate, and an inventory entry whose carrier lies on no cycle is recorded as
discharging nothing — declared content, surfaced, with no finding of any severity following from
it. Read the inventory, not the verdict word.

**A pinned seed is a claim about the definition.** P-08's caveat,
`provider-seed-reproducibility-not-guaranteed`, is carried whenever any claim is LLM-backed. The
property checks that a determinism claim is *coherent* — an LLM-backed node pinning `seed`, with
`temperature` pinned at `0` (§8.2); it is HEURISTIC precisely because what a provider actually
returns on replay is not something reading a graph can settle.

## Where this page is checked

Every example above is executed in CI, in a child interpreter where compiling a graph, invoking a
runnable, resolving a hostname or opening a connection all raise, and where every node body in
the travel-booking agent and its defect variants records and raises if it is reached. The output
blocks are what those runs printed. If any of it stops behaving this way the build fails rather
than the page misleading a reader — [Executable examples](../contributing/executable-examples.md)
explains the mechanism.

Two of the per-validator pages are written and go further on their own property than this page
does: [P-01 `graph-well-formed`](../validators/p01-graph-well-formed.md) and
[P-02 `termination-witness`](../validators/p02-termination-witness.md). The other three are
still placeholders, and until they are written the frozen contract for those properties — what
each reads and what its records contain — is PROPERTY-CATALOG-SPEC §P-04, §P-06 and §P-08. The
validator modules under `gebra.verify.properties` and their tests are where that contract is
implemented and pinned, and are the closest description of it in this repository.
