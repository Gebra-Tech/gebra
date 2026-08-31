# What gebra checks

!!! note "Spec-derived page"

    The vocabulary on this page — the claim classes, the severity ladder, the exit codes and
    strict mode — is transcribed from **PROPERTY-CATALOG-SPEC §0**, the frozen specification
    the validators are written against, and every statement names the section it came from.
    That specification set is an internal contract document and is not published with this
    site; the section numbers are here so that a claim can be *checked* against it rather
    than taken on trust.

    The two examples below are not spec-derived. They are executed in CI and print what this
    release actually does — see [Executable examples](../contributing/executable-examples.md).

## What is under test

gebra reads a workflow **definition** and answers questions about it. `gebra.extract()`
imports and inspects a `StateGraph` builder, a compiled graph or an LCEL `Runnable` — it never
invokes one: no node function, router, tool or model is called, and no connection is opened —
and emits the Gebra IR; the validators read that IR. gebra verifies definitions; LangGraph
runs them (SOW §1).

Everything below follows from that one fact. A finding is a statement about the document that
was extracted — its topology, its state schema, and the contracts its nodes declare — and
about nothing else. Two consequences are worth stating before the tables, because they are
what makes the tables readable:

- a **pass** carries a structured *witness* and a **fail** carries a structured *failure*
  naming the violated condition and its locus; both are values, never prose (§0);
- no wording in a report may claim more than the property's **claim class** licenses (§0) —
  which is why every finding carries its class, and why this page starts there.

## Claim classes

A claim class says what kind of evidence a finding rests on. The catalog carries exactly
three (§0.1):

| Claim class | Serialized value | Meaning |
|---|---|---|
| **DEFENSIBLE** | `defensible` | Decidable over the IR alone. |
| **DEFENSIBLE-A** | `defensible-a` | Decidable over IR + declared annotations; annotation truthfulness is trusted, like type annotations. |
| **HEURISTIC** | `heuristic` | Advisory lint; no proof claim. |

Read the middle row carefully, because it is the one an evaluator most often reads as
stronger than it is. A DEFENSIBLE-A finding is decided over the IR *plus what the code
declared about itself* — a `@gebra.contract`'s reads and writes, an effect tag, an
idempotency key. Those declarations are trusted the way a type annotation is trusted: gebra
checks that they are coherent with the graph, not that they are true of the function body
(§0.1; ANNOTATION-API-SPEC §5, the DEFENSIBLE-A trust model).

Every failure-side record carries its own class — the primary failure, every co-failure and
every advisory — so a HEURISTIC advisory riding along with a report can never be mistaken for
a proof-backed finding (§0.1, §0.3).

A fourth class, ESTIMATED, exists elsewhere in the wider Gebra design for stochastic model
outputs. It is **out of catalog scope**: it never appears in a `gebra verify` report, and the
envelope's claim-class type has exactly three members (§0.1).

## Severity, and what it does to the gate

Severity says how bad a finding is for the definition, and what the gate should do about it
(§0.2):

| Severity | Serialized value | Design-time meaning | Gate effect |
|---|---|---|---|
| **FATAL** | `fatal` | The definition is unfit to run — it would crash, dead-end, or loop without bound. | `gebra verify` fails; **no snapshot is recorded**. |
| **ERROR** | `error` | A contract or policy violation. | `gebra verify` fails; CI gate blocks; snapshot recorded. |
| **WARNING** | `warning` | Advisory. | `gebra verify` **passes with notes**. |

The two are separate axes: severity is fixed per condition, and a claim class can span more
than one of them — a DEFENSIBLE-A property reports both ERROR and FATAL findings depending on
which condition fired (§0.4's registry assigns a severity and a claim class to each entry
independently). The combination is what a reader should act on: *how confident is this, and
how bad is it.*

## Exit codes

The exit code belongs to the run, not to any one finding — it is derived from all of them
(§0.2):

| Exit code | Condition |
|---|---|
| `0` | Verify pass: zero FATAL/ERROR findings. WARNING findings may be present; they are rendered as notes and do not affect the code. |
| `1` | Verify fail: at least one FATAL or ERROR finding — or a WARNING promoted under strict mode. FATAL additionally suppresses snapshot recording. |
| `2` | Tool error: extraction or IR validation failed before any property ran. No verdict was reached; exit 2 is never a verification result. |

That last row is the one CI authors should read twice. Exit `2` does not mean "the workflow
failed verification"; it means no verdict exists to report (§0.2). A pipeline that treats any
non-zero code as a verification failure will mislabel its own broken input.

### The ladder, executed

All five properties this release implements run against each of the five seeded-defect
variants of the travel-booking agent used for acceptance — one deliberately broken variant per
seeded defect. The defects target four of the five properties (`effect-safety` twice, and no
variant seeds a `graph-well-formed` defect: they are all P-01-clean by construction), so what
follows is one finding per variant plus the gate that follows from it:

<!-- gebra:example id=severity-and-the-gate -->
```python
import gebra
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.travel_booking_defects import DEFECTS

for variant in DEFECTS:
    report = verify(gebra.extract(variant.build()).ir)
    for outcome in report.properties:
        if isinstance(outcome, PropertyReport) and outcome.result == "fail":
            failure = outcome.failure
            print(
                f"defect {variant.number}  {outcome.property:21} "
                f"{failure.property_condition:38} "
                f"{failure.severity:8}{failure.claim_class}"
            )
    gate = report.gate
    print(
        f"{'':10}gate {gate.outcome:16}exit {gate.exit_code}   "
        f"snapshot {'recorded' if gate.snapshot_eligible else 'suppressed'}"
    )
```

<!-- gebra:output id=severity-and-the-gate -->
```text
defect 1  termination-witness   cycle-without-termination-witness      fatal   defensible
          gate fail            exit 1   snapshot suppressed
defect 2  effect-safety         unprotected-effect-in-retry-region     error   defensible-a
          gate fail            exit 1   snapshot recorded
defect 3  determinism-replay    deterministic-llm-temperature-unpinned warning heuristic
          gate pass-with-notes exit 0   snapshot recorded
defect 4  dataflow-completeness read-key-never-written-on-path         fatal   defensible-a
          gate fail            exit 1   snapshot suppressed
defect 5  effect-safety         unprotected-effect-in-retry-region     error   defensible-a
          gate fail            exit 1   snapshot recorded
```

All three severities and all three claim classes appear in that transcript, and each row is
the ladder acting: the two FATAL rows leave the run ineligible for a snapshot, the two ERROR
rows fail the gate while staying eligible for one, and the WARNING row passes with a note and
exits `0`. (Eligibility is a signal on the report, not an action: `verify()` records nothing —
`gebra snapshot` is what reads it and refuses.)

The last point is the one to sit with. Defect 3 is a real defect — a node claiming
determinism it has not pinned — and by default it does **not** fail the build. Whether it
should is a policy question, and policy is what strict mode is for.

## Strict mode changes the gate, never the record

`--gebra-strict` promotes WARNING findings to gate failures, in two forms (§0.2):

- **bare** — `--gebra-strict` promotes every WARNING in the run;
- **per-property** — `--gebra-strict=<slug>[,<slug>…]`, e.g.
  `--gebra-strict=determinism-replay`, promotes only the named properties' WARNINGs, while
  every other WARNING keeps its pass-with-notes semantics.

Promotion reaches WARNING-grade findings wherever they surface — failures, co-findings and
WARNING-grade witness notes on a pass-with-notes report (§0.2), and cross-property advisories,
which §0.3 fixes at WARNING severity and which are promoted under their own owning property.

What it does *not* do is re-grade anything. A promoted finding keeps its own `severity:
warning` and its own claim class in the report; strictness is a CI policy choice, and
rewriting a HEURISTIC advisory into an ERROR would be exactly the overstatement the claim
classes exist to prevent (§0.2). The same defect 3, run twice:

<!-- gebra:example id=strict-changes-the-gate -->
```python
import gebra
from gebra.verify import RunPolicy, StrictPolicy, verify
from tests.sample_workflows.travel_booking_defects import build_defect_3_false_determinism

ir = gebra.extract(build_defect_3_false_determinism()).ir
policy = RunPolicy(strict=StrictPolicy(mode="per-property", properties=("determinism-replay",)))

for label, report in (("default", verify(ir)), ("strict", verify(ir, policy))):
    record = report.outcome_for("determinism-replay").failure
    print(f"{label:8}exit {report.gate.exit_code}  gate {report.gate.outcome}")
    print(f"{'':8}the record: severity {record.severity}, claim class {record.claim_class}")
    for promotion in report.gate.promotions:
        print(f"{'':8}promoted at the gate: {promotion.property_condition}")
```

<!-- gebra:output id=strict-changes-the-gate -->
```text
default exit 0  gate pass-with-notes
        the record: severity warning, claim class heuristic
strict  exit 1  gate fail
        the record: severity warning, claim class heuristic
        promoted at the gate: deterministic-llm-temperature-unpinned
```

The exit code moved; the two lines describing the record did not. That is the whole design:
a team can decide that unpinned determinism claims block their pipeline without gebra ever
claiming to have found something stronger than it did.

## The five properties this release implements

The catalog holds thirteen properties. Five are implemented here; the other eight are out of
scope for this phase (SOW §8) and are answered in every run by a structured not-implemented
marker. The gate is derived from findings only, so a marker takes no part in the exit code
(REPORT-FORMAT-SPEC §2.2), and the copy rules forbid rendering one as a pass or counting it in
a "checks passed" tally (§4.6 rule 5) — a property nobody has written never reports a silent
pass.

| Property | What it decides | Claim class | Severity |
|---|---|---|---|
| P-01 `graph-well-formed` | Every node reachable from `START`; no dead ends; no orphan nodes; every edge target and every `path_map` value names a node that exists (§P-01). | DEFENSIBLE | FATAL |
| P-02 `termination-witness` | Every cycle carries a declared termination witness — a bounded counter with a conditional exit, a justified `recursion_limit`, or an annotated loop variant (§P-02). | DEFENSIBLE (witness presence) | FATAL |
| P-04 `dataflow-completeness` | For every key a node reads, some predecessor writes it on **every** path from `START` to that node — or the key is a declared graph input, treated as written at `START` (§P-04). Unreachable nodes raise no obligation here; P-01 owns them (§P-04 Scope). | DEFENSIBLE-A | FATAL |
| P-06 `effect-safety` | No node tagged `irreversible` or `billable` sits in a cycle or retry region without an idempotency key or compensation hook; `irreversible` + keyless `idempotent` is a design error outright (§P-06). | DEFENSIBLE-A | FATAL for the irreversible + keyless-idempotent contradiction; ERROR for an unprotected irreversible/billable effect in a cycle or retry region |
| P-08 `determinism-replay` | A node declaring `@gebra.deterministic(seed=…)` around an LLM call pins both `seed` and `temperature` (§P-08). | HEURISTIC | WARNING |

Two of the per-validator pages are written — [P-01 `graph-well-formed`](../validators/p01-graph-well-formed.md)
and [P-02 `termination-witness`](../validators/p02-termination-witness.md) — and the other
three are still placeholders. Where a page is not yet written, the authority on what that
property's witness and failure records actually contain is the validator modules under
`gebra.verify.properties` and their tests.

## What a finding does not claim

This is the boundary the whole project is organised around, and it is a hard one (SOW §6).

**Witness presence, never semantic termination.** P-02 decides one question: does every simple
cycle carry a termination witness? Witness *presence* is decidable and provable. Whether a
declared guard ever evaluates true at run time, whether a bounded counter is actually
advanced, whether a declared loop variant really decreases — all of that lies permanently
outside the boundary and is trusted, never checked (TERMINATION-WITNESS-SPEC §1.1). Every
claim P-02 makes has the shape "the definition carries a bound", never "the run halts". The
spec bans the stronger phrasings by name in findings, docs and marketing alike, and a lint in
this repository enforces the ban (TERMINATION-WITNESS-SPEC §7; WA-06).

**A pass is about the definition as written.** It says the structure and the declared
contracts satisfy the property. Where a node declared no contract, extraction applies the
conservative default and records a `contract-defaulted` warning (ANNOTATION-API-SPEC §4) — so
part of such a pass is a statement about a default rather than about a declaration, and the
warning is what keeps that visible.

**Some passes are vacuous, and that is worth reading.** An acyclic graph passes
`termination-witness` because there was no cycle for a bound to be declared on, not because a
bound was found — the property quantifies over the cycles of the graph (§P-02), and over none
it is satisfied. The witness records which of those two happened: it carries an inventory of
the declared witnesses and an acyclicity certificate, and an element that lies on no cycle
stays in the inventory marked as discharging nothing (TERMINATION-WITNESS-SPEC §6.2).

**When P-01 fails, three reports become diagnostics.** P-02, P-04 and P-06 all build the
graph, and the specification defines their results only over P-01-clean topology; where P-01
fails, their reports on that IR are best-effort diagnostics rather than contract-bearing
verdicts (§0.3). A run whose P-01 findings are FATAL says so in the report itself, naming
those three properties, so the distinction survives into the artifact instead of living only
in the spec.

## The diagnostic vocabulary is frozen

`property_condition` — the `cycle-without-termination-witness` and
`unprotected-effect-in-retry-region` strings in the transcripts above — comes from a closed
registry (§0.4). The strings are frozen kebab-case identifiers; a validator may never emit one
that is not in the registry, and adding, renaming or promoting an entry is a specification
amendment with its own decision record, never a local change.

That discipline is not housekeeping. Condition IDs map verbatim onto the SARIF `rule.id`
namespace (§0.5), and a downstream consumer's alert deduplication turns on a result's
`ruleId` being identical across analyses (§0.4) — so a string that drifted between releases
would silently split one finding into two.

## Where this page is checked

Both examples on this page are executed in CI, in a child interpreter where compiling a
graph, invoking a runnable, resolving a hostname or opening a connection all raise, and where
every node body in the sample workflows records and raises if it is reached. The printed
output above is what that run produced. If either example stops behaving this way, the build
fails rather than the page misleading a reader —
[Executable examples](../contributing/executable-examples.md) explains the mechanism.
