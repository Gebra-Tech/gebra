# Architecture overview

gebra reads a workflow **definition** and answers questions about it. It never runs one.
Everything below follows from that one commitment: the extractor reads a `StateGraph`
builder, a compiled graph or an LCEL `Runnable` by introspection rather than by execution;
what it produces is a document; and every other package in the system consumes that document
rather than the object it came from.

This page is the as-built map — what the packages are, which direction they depend in, where
the frozen surfaces sit, and what a change to one costs. It describes what is merged and
tested in this repository. The last section is the appendix the extractor's freeze record
carries: the shapes ir 1.0/1.1 has no slot for, each waiting on a decision record before
anything may emit it.

## The shape of the system

One direction of flow, six stages, and one artifact that joins them:

```text
  your LangGraph agent            (never invoked)
          │
          │  gebra.extract()                              gebra.extraction
          ▼                                               gebra.annotations
  ┌─────────────────┐
  │ ExtractionEnvelope                                    the IR, its provenance
  │   .ir  .extracted_from  .warnings                     and the warnings taxonomy
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐   canonical_bytes() → graph_version()
  │  WorkflowIR     │────────────────────────────────────▶ "sha256:…"   gebra.ir
  └────────┬────────┘                                          │
           │                                                   │  the content identity
    ┌──────┴──────┐                                            │  every later stage compares on
    ▼             ▼                                            ▼
 verify(ir)   snapshot(agent)                            ┌───────────┐
    │             │                                      │  .gebra/  │      gebra.store
    ▼             ▼                                      └─────┬─────┘      gebra.snapshot
 RunReport    SnapshotRecord ──────────────────────────────────┘
    │  gebra.verify                │  V.S.F.E label            │
    │                              ▼                           ▼
    │                        gebra.versioning            compare(a, b)      gebra.lineage
    │                                                          │            gebra.diff
    ▼                                                          ▼
 gebra.report ─── human · JSON · SARIF               WorkflowDiff + bump class
    │                                                          │
    └──────────────────────┬───────────────────────────────────┘
                           ▼
        gebra.cli · the pytest plugin · gebra.testing · gebra.display
```

Read it as a pipeline with one join. Extraction produces a document; `graph_version` turns
that document into a content identity; and everything downstream — verification, the store,
the diff — is a function of the document, never of the live object. That is why the IR
freeze gates the rest of the system: the digests, the stored labels and the diffs are all
functions of the canonical form, so a change to it that moved any bytes would move all
three at once. That is what the freeze's major/minor rule is about, and why an
additive-optional minor is admitted only on the condition that it moves none of them.

## The packages

Sixteen public packages. The first five are frozen (see [What is frozen](#what-is-frozen-and-what-changing-one-costs));
the rest are supported surfaces that the pages listed beside them document.

<!-- gebra:example id=the-public-packages -->
```python
import gebra
import gebra.annotations
import gebra.audit
import gebra.cli
import gebra.diff
import gebra.display
import gebra.extraction
import gebra.ir
import gebra.lineage
import gebra.pytest_plugin
import gebra.report
import gebra.snapshot
import gebra.store
import gebra.testing
import gebra.verify
import gebra.versioning

PACKAGES = [
    gebra,
    gebra.extraction,
    gebra.annotations,
    gebra.ir,
    gebra.verify,
    gebra.snapshot,
    gebra.store,
    gebra.versioning,
    gebra.lineage,
    gebra.diff,
    gebra.audit,
    gebra.report,
    gebra.display,
    gebra.testing,
    gebra.pytest_plugin,
    gebra.cli,
]

for package in PACKAGES:
    print(f"{package.__name__:22}{len(package.__all__):4}")
print(f"{'':22}{'':->4}")
print(f"{'exported names':22}{sum(len(p.__all__) for p in PACKAGES):4}")
```

<!-- gebra:output id=the-public-packages -->
```text
gebra                   10
gebra.extraction        72
gebra.annotations       55
gebra.ir                68
gebra.verify           162
gebra.snapshot           7
gebra.store             31
gebra.versioning        13
gebra.lineage           11
gebra.diff              33
gebra.audit             11
gebra.report            31
gebra.display            4
gebra.testing           29
gebra.pytest_plugin     33
gebra.cli                2
                      ----
exported names         572
```

| Package | What it owns | Where it is documented |
|---|---|---|
| `gebra` | The ten top-level entry points, resolved lazily. | [API reference](api.md#gebra) |
| `gebra.extraction` | Dispatch, the provenance envelope, the warnings taxonomy, the version check. | [API reference](api.md#gebraextraction) · [Extract your first IR](../tutorials/extract-your-first-ir.md) |
| `gebra.annotations` | The decorator family, the `gebra.toml` sidecar, inference, and the four-tier per-slot precedence. | [API reference](api.md#gebraannotations) · [Contracts and annotations](../tutorials/contracts-and-annotations.md) |
| `gebra.ir` | The models, node identity, the canonical form and `graph_version`, the loaders. | [API reference](api.md#gebrair) · [The IR, node identity and graph_version](../concepts/ir-and-graph-version.md) |
| `gebra.verify` | The result envelope, the condition-ID registry, the five validators, `verify()`. | [API reference](api.md#gebraverify) · [Verify and interpret](../tutorials/verify-and-interpret.md) |
| `gebra.snapshot` | The wiring from a live workflow to a stored snapshot. | [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md) |
| `gebra.store` | The `.gebra/` layout: snapshots, reports, metadata, atomic writes. | [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md) |
| `gebra.versioning` | V.S.F.E labels: which field path moves which counter, and the next label. | [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md) |
| `gebra.lineage` | Comparing two stored versions, and the freshness check over a store. | [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md) |
| `gebra.diff` | The structural diff itself: topology, state and contracts. | [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md) |
| `gebra.audit` | Per-version audit exports and the lineage export. | [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md) |
| `gebra.report` | The three surfaces of one run report: a human rendering, the report itself as JSON, a findings-only SARIF projection. | [CLI reference](cli.md) |
| `gebra.display` | A definition as Mermaid text. | [CLI reference](cli.md#gebra-display) |
| `gebra.testing` | The golden-fixture harness and the assertion helpers tests build on. | [The pytest plugin and CI gating](../guides/pytest-plugin-and-ci-gating.md) |
| `gebra.pytest_plugin` | The pytest plugin: markers, fixtures, severity gating. | [The pytest plugin and CI gating](../guides/pytest-plugin-and-ci-gating.md) |
| `gebra.cli` | The five verbs, their flags and their exit codes. | [CLI reference](cli.md) |

## Stage by stage

**1 — Extraction (`gebra.extraction`, `gebra.annotations`).** `gebra.extract()` dispatches on
what it was handed and reads it: a builder's node and edge tables, a compiled graph's
resolved surfaces, or an LCEL fragment's structure. Node contracts are resolved **slot by
slot**, in a fixed four-tier precedence — a `@gebra.contract` decorator, then a `BaseTool`'s
own `args_schema` (the one tool-carried slot in ir 1.0), then a `gebra.toml` sidecar entry,
then shallow inference over the node's source — and every place a value was inferred or
defaulted rather than declared is recorded as a structured warning rather than passed off as
a declaration. What comes back is an `ExtractionEnvelope`: the IR, where it came from, and
those warnings.

**2 — The IR (`gebra.ir`).** The document. Its models are strict and frozen
(`extra="forbid"`), its node identities follow one grammar, and its canonical form is RFC
8785 JSON — from which `graph_version()` derives the `sha256:…` content identity. The
envelope around a document is deliberately *outside* that identity: where a document came
from and when is provenance, not content. A document written to YAML or JSON reloads equal to
itself — model equality, not byte-level fidelity, because the canonical form is what is
hashed and surface bytes never are — which is what lets every later stage work off a file
rather than off a live object.

**3 — Verification (`gebra.verify`).** A registry maps thirteen property slugs to what
answers for them. Five are implemented — the wedge five — and the other eight answer through
the same registry with a structured not-implemented marker, so a report never shows silence
where a property was not run. `verify(ir)` runs them P-01 first, then in catalog order, and
does not stop when P-01 fails: it returns one `RunReport` carrying each property's outcome,
the severity counts, the gate and its exit code, plus `best_effort` — the properties whose
outcomes this run offers as diagnostics rather than as contract-bearing verdicts, because
they read a topology P-01 found ill-formed. A finding is a model, not a string: the same
model the golden harness asserts on.

**4 — Snapshot and version (`gebra.snapshot`, `gebra.store`, `gebra.versioning`).**
`snapshot()` extracts, then records into a `.gebra/` store whose files are keyed by the
V.S.F.E **label**; `graph_version` is what decides whether the definition moved at all, so
the store writes atomically and is a no-op when it did not. The label itself is computed from
*which* field paths moved between the previous version and this one, which is what makes it a
description of the change rather than a counter someone remembered to increment.

**5 — Diff and lineage (`gebra.diff`, `gebra.lineage`, `gebra.audit`).** The structural diff
compares two documents across three sections — topology, state and contracts, with the
graph-level `runtime` block compared alongside the contracts — and reports the bump class
those changes imply. It is the evidence, not the judgement: the diff says a state key left
while two node contracts still declared it; whether that is safe to ship is the reviewer's
call. Every diff carries the same structured not-implemented marker for P-12
`evolution-safety` that a run report carries for a property it did not run, so the artifact
says *not checked* rather than implying a clean bill. `gebra.audit` writes the per-version
exports and the lineage export a review trail needs.

**6 — Surfaces (`gebra.cli`, `gebra.report`, `gebra.display`, `gebra.testing`, the pytest
plugin).** Five verbs on the command line, three surfaces of one report (a human rendering,
the report itself as JSON, a lossy findings-only SARIF projection — pass witnesses do not
appear in SARIF at all), a Mermaid rendering of a topology, a fixture harness, and a pytest
plugin that turns a run report into test outcomes with severity gating. None of them
introduces a verification semantic of its own: each renders, or gates on, what a stage above
it already decided.

## The whole pipeline in one run

Extraction, identity, verification, two recorded versions and the diff between them — the
six stages above, in one process, over a sample agent this repository ships.

<!-- gebra:example id=the-pipeline-in-one-run -->
```python
from datetime import datetime, timezone
from pathlib import Path

import gebra
from gebra.ir import graph_version
from gebra.lineage import compare
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.verify import verify
from gebra.versioning import Component
from tests.sample_workflows import travel_booking
from tests.sample_workflows.travel_booking_evolution import EVOLUTION

envelope = gebra.extract(travel_booking.build_travel_booking_agent())
print("1  extract   ", len(envelope.ir.nodes), "nodes,", len(envelope.warnings), "warnings")
print("2  identity  ", graph_version(envelope.ir))

report = verify(envelope.ir)
counts = report.gate.counts
print(
    "3  verify    ", report.gate.outcome, f"(exit {report.gate.exit_code})", counts.fatal, "fatal"
)

store = SnapshotStore(Path(".gebra"))
pinned = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
first, second = EVOLUTION[0], EVOLUTION[1]
before = snapshot(first.build(), store=store, source=first.name, extracted_at=pinned)
after = snapshot(second.build(), store=store, source=second.name, extracted_at=pinned)
print("4  snapshot  ", before.version, "->", after.version)

difference = compare(store, before.version, after.version)
moved = " ".join(part.value for part in Component if part in difference.bump_class)
print("5  diff      ", f"{before.version} -> {after.version}", "moved", moved or "nothing")
print("6  render    ", "human · json · sarif, from the one RunReport above")
print()
print("node bodies run:", travel_booking.TRIPPED)
```

<!-- gebra:output id=the-pipeline-in-one-run -->
```text
1  extract    9 nodes, 0 warnings
2  identity   sha256:b310b9dc037b819503de71ac0d29d10ce0902c2901fd13a7cb8a0d5b30766335
3  verify     pass (exit 0) 0 fatal
4  snapshot   1.0.0.0 -> 1.0.0.1
5  diff       1.0.0.0 -> 1.0.0.1 moved E
6  render     human · json · sarif, from the one RunReport above

node bodies run: []
```

The last line is the point of the whole design, printed rather than asserted: the sample
agent's node bodies each record into a module-level ledger before raising if they are ever
called, and after a full extract–verify–snapshot–diff pass that ledger is empty.

## What imports the substrate, and what does not

`langgraph` and `langchain-core` are needed to *read* an agent, and nothing else in this
system needs them. That is enforced by the package layout rather than by convention: of the
sixteen public packages, exactly two pull the execution substrate into their import closure.

| Import closure | Packages |
|---|---|
| Pulls `langgraph` / `langchain-core` | `gebra.extraction`, `gebra.snapshot` |
| Does not | `gebra`, `gebra.ir`, `gebra.verify`, `gebra.annotations`, `gebra.store`, `gebra.versioning`, `gebra.diff`, `gebra.lineage`, `gebra.audit`, `gebra.report`, `gebra.display`, `gebra.testing`, `gebra.pytest_plugin`, `gebra.cli` |

Two consequences a reader can act on. A bare `import gebra` does not import the substrate:
the ten top-level names are resolved lazily on first attribute access (PEP 562), so
annotating a node function with `@gebra.contract` costs nothing at import time and does not
drag the extractor in behind it. And a process that only reads serialized IR — a CI job that
verifies a checked-in `agent.ir.yaml`, a tool that diffs two stored versions — imports none
of the substrate on that route. It is still *installed*: `langgraph` and `langchain-core`
are required dependencies of the distribution, because reading a live agent is what the
package is for. What the layout buys is that a verify-only or diff-only path does not load
them, and cannot be broken by them.

`gebra.snapshot` is on the substrate side because it is the wiring from a live workflow to a
stored snapshot: it extracts, so it imports the extractor. The store, version, diff, lineage
and audit engines under it do not.

The table is measured, not asserted: `tests/docs/test_architecture_overview.py` imports each
package in a fresh interpreter and reads the resulting `sys.modules`, in both directions — a
package that started importing the substrate fails, and so does one this page lists as
importing it that no longer does.

## What is frozen, and what changing one costs

Five surfaces are under a freeze record. The record fixes the names, signatures and field
sets; the page that lists them is the [API reference](api.md).

| Surface | Names | Freeze record | Changing its shape requires |
|---|---|---|---|
| `gebra.ir` | 68 | `docs/governance/IR-MODELS-FREEZE.md` (card IR-06) | A decision record **and** an `ir_version` bump — additive-optional is a minor, anything that moves existing bytes is a major. A ruled change that moves no conforming document's bytes can carve itself out; the node-id uniqueness constraint did. |
| `gebra.verify` | 162 | `docs/governance/VALIDATOR-API-FREEZE.md` (card VAL-12) | An R-05-routed decision: proposal, vault sign-off, then the re-vendored commit. |
| `gebra` | 10 | `docs/governance/EXTRACTOR-API-FREEZE.md` §1.1 (card EX-15) | A decision record before anything new is emitted; refactors that move no name are unaffected. |
| `gebra.extraction` | 72 | `docs/governance/EXTRACTOR-API-FREEZE.md` §1.2 (card EX-15) | The same, plus an `ir_version` bump for anything that lands a new ledger slot. |
| `gebra.annotations` | 55 | `docs/governance/EXTRACTOR-API-FREEZE.md` §1.3 (card EX-15) | The same. |

What a freeze does *not* do is stop ordinary work. An internal refactor that moves no name,
alias, requiredness, discriminator or digest byte needs no record and no bump — the freeze is
about the surface a caller codes against, not about the code behind it.

The IR-models freeze and the validator-result freeze are jointly the trigger the project
calls **F3**, and the reason the document format and the result envelope can both be depended
on. What that buys, stated exactly: a `graph_version` computed from an **IR document** today
is the string a later release computes from that same document, because a change to the
canonicalization rules is digest-breaking and forces an `ir_version` bump, and `ir_version`
sits inside the hashed payload where it firewalls false equality across format versions. It
is not a promise about a *workflow*: what an agent extracts to can move when the extractor
or the substrate changes what it reads, which is what the drift suite and the compatibility
matrix are for. The digest is a function of the document.

## The never-invokes boundary

gebra calls no node function, no router, no tool and no model, and opens no connection of its
own. Extraction is introspection: it reads the tables a builder has already filled in, the
attributes a compiled graph exposes, and — for a contract nothing declares — the *source* of
a node body rather than its behaviour.

There are three places where code that is not gebra's runs, each stated where it happens. The
CLI's `--call` flag calls the attribute you named, once, with no arguments, because a factory
function has to be called to produce the object to read; it is opt-in and documented in the
[CLI reference](cli.md#naming-the-subject). Importing a module runs that module's top-level
code, which is true of any tool that resolves an import reference. And reading a node's or
router's type hints evaluates its annotation *expressions* when they are strings or forward
references — the read the introspection specification licenses by name, resolved against
module namespaces and degraded to an unknown hint when it fails. None of the three is a node
being invoked, and `tests/never_invokes_audit.md` states the licensed reads and the boundary
of the provenance gate in full.

Inside this repository the boundary is a tested invariant, not a policy: every node body and
router in the sample workflows records into a module-level ledger before raising, the
documentation examples run in an interpreter where node invocation, graph compilation, DNS
resolution and socket creation all raise, and the extraction suite carries tripwires on every
path. What that buys a reader is narrow and worth stating plainly: gebra reports what a
definition *declares*, and a declaration can be wrong. Nothing here is a claim about what
your agent does at run time.

## Appendix — the 1.x design-tracked backlog

Every row below is a shape the extractor already reads, classifies or declines today, but for
which ir 1.0/1.1 carries no ledger slot. The table is the one card EX-15 recorded in
`docs/governance/EXTRACTOR-API-FREEZE.md` §2, reproduced here so that integrators can see
which shapes ir 1.0/1.1 has no slot for without reading the build's own records.

Read the Status column literally. **Every row needs a future decision record**, and none of
them is scheduled, planned or promised — a row here is a gap that has been named and anchored
to the specification section that names it, which is the opposite of a roadmap entry. None
may be emitted, coerced into an existing slot, or inferred from a heuristic before its
decision record lands; the extractor's present posture — decline, or provenance-only — is the
conforming one until then.

| # | Item | What it would carry | Spec anchor | Status |
|---|---|---|---|---|
| 1 | `projection` | Declared parent↔child state projection for a subgraph (P-10) | INTROSPECTION-SPEC §7.3 item 2; IR-SPEC §8 "Named deferred 1.x candidates: P-10 / P-11 slots" | Deferred to 1.x by walkthrough #1 (DEC-09, 2026-07-18) — **needs future DEC** |
| 2 | Subgraph child-topology expansion | Child nodes, child edges, and the child's own `entry`/`finish`/Σ for a discovered subgraph (ir 1.0/1.1 carries the parent node only) | INTROSPECTION-SPEC §4.1 (Subgraph discovery); DEC-19 (2026-08-03) | Named "the first 1.x feature"; its own design register (boundary-edge encoding, child `entry`/`finish`/Σ carriage, per-level sentinel ban, `ir_version` bump, H3 activation, P-10 consumption) is ratified as **not to be improvised in 1.0** — **needs future DEC** |
| 3 | `join_key` | Declared branch join keys for a merge node (P-11) | INTROSPECTION-SPEC §7.3 item 2; IR-SPEC §8 | Deferred to 1.x by walkthrough #1 (DEC-09, 2026-07-18) — **needs future DEC** |
| 4 | `codomain` | A router codomain declared independently of `path_map` (P-05(i) coverage) | INTROSPECTION-SPEC §7.3 item 5; §6 codomain-capture rule (DEC-29, 2026-08-10) | Disposition awaits walkthrough #2 (not ratified by walkthrough #1); today the hint lands in provenance only, warning-free — **needs future DEC** |
| 5 | `kind: join` | The all-of barrier semantics of `waiting_edges` (currently flattened to one `normal` edge per source, with a `barrier-flattened` warning) | INTROSPECTION-SPEC §7.3 item 3 | Candidate name recorded; flattening is the accepted 1.0 posture — **needs future DEC** |
| 6 | Managed-value marker slot | A `RemainingSteps`-style managed-value declaration (currently P-02 corroborating provenance only, never a core-IR field) | INTROSPECTION-SPEC §3 (`.channels` row); §7.3 item 4 | No candidate slot name yet — **needs future DEC** |
| 7 | Checkpointer *type* | Which checkpointer class/backend is configured (ir 1.0/1.1 carries only `runtime.checkpointer.present: bool`) | IR-SPEC §3.7 evolution note | "If ever wanted, lands as an additive-optional 1.x extension — never a change to `present`" — **needs future DEC** |
| 8 | Tool projection for `BaseTool`-object bindings | A bound `BaseTool` object's own surface (name/description/schema), so an edit to it moves `config_digest` the way a JSON-schema-dict tool already does | INTROSPECTION-SPEC §7.4 (c)/(d) | Recorded by EX-16 (PD-043 D4): a `BaseTool` object digests by class identity under rule 12 today; widening it is a §7.4 (b)-shaped closed-vocabulary extension — **needs future DEC** |
| 9 | Non-mirrored `StateNodeSpec` builder fields | `metadata`, `cache_policy`, `defer`, `timeout`, the error-handler pair (`is_error_handler`/`error_handler_node`) | INTROSPECTION-SPEC §3 (node-spec table row: "Read but not mirrored in ir 1.0") | Recorded by EX-05 (PD-023 D6, verbatim): dropped, not read at all — **needs future DEC** |
| 10 | Non-mirrored compiled-level provenance facts | `node_error_handler_map`; the folded-`set_node_defaults` resolution (which node declared it) | INTROSPECTION-SPEC §4.1 ("still land in provenance only — no ir 1.0 slot; candidate 1.x extensions") | Recorded by EX-05 (PD-023 D6, verbatim): carried in `CompiledSurfaces.error_handlers` / `CompiledSurfaces.folded_defaults` provenance today, not the core IR — **needs future DEC** |
| 11 | PD-028 D1 fact-pin correction | The ratified correction PD-028's consequences route to this backlog | PD-028 consequences | *(row added at the 2026-08-13 post-landing review — routed here by its PD but missing from the table as landed)* — **needs future DEC** |
| 12 | `_ChatModelBinding` exact-type posture at 1.x | Whether the stock-binding admission stays exact-type or admits subclasses | PD-028 D5 | *(added 2026-08-13, same review)* — **needs future DEC** |
| 13 | Builder-level bound-tool digest coverage | PD-028 D10's coverage gap | PD-028 D10 | *(added 2026-08-13)* — **needs future DEC** |
| 14 | Recognized-template / configurable-fields / `lc_secrets` extension points | PD-014's named extension points | PD-014 via PD-028 | *(added 2026-08-13)* — **needs future DEC** |
| 15 | `RunnableRetry` → `retry_policy` carrier | LCEL retry wrapper mapped to the declared retry slot | PD-025 | *(added 2026-08-13)* — **needs future DEC** |
| 16 | Synthetic composition kinds beyond §5.2 | New segment-kind tokens for compositions 1.0 refuses | PD-025 | *(added 2026-08-13)* — **needs future DEC** |
| 17 | Router-contract surface | `@gebra.contract` on a router is silently inert in 1.0/1.1 (PD-044 D13) | PD-044 D13 | *(added 2026-08-13)* — **needs future DEC** |
| 18 | Send-classified codomain recording | `_record_codomain` is conditional-branch-only in 1.0/1.1 (PD-044 D14) | PD-044 D14 | *(added 2026-08-13)* — **needs future DEC** |
| 19 | Non-string `path_map` label projection | Declined in 1.0/1.1 — DEC-32 rules refusal; a closed projection table (exact-type `bool` first: `"true"`/`"false"`, matching §7.4(d) Coercion K's JCS rendering) is the candidate. Design constraints from the 2026-08-20 probes bind any future table: explicit dispatch order (enum-int hybrids match two rows); no instance dunder reads (`int.__str__` resolves through `object.__str__` to a subclass `__repr__`; the safe spellings are `int.__repr__(x)` and the enum machinery's own `name` getter); composite `Flag` `.name` is `None` on py3.10 vs `"A\|B"` on 3.13 (interpreter-varying — cannot enter hash scope); source-dict equal-hash merges (`{True: 'a', 1: 'b'}`) happen before extraction can see them, so collision-is-error is enforceable only post-projection; str-subclass labels never reach the table (verbatim-value, DEC-32). Trigger: a genuine production refusal report. | DEC-32 | *(added 2026-08-22)* — **needs future DEC** |

Rows 9 and 10 are the disposition of the fields the extractor reads but ir 1.0 does not
mirror. One further item from that ruling — the subgraph boundary-wiring encoding — is not a
separate row: it was ruled in 2026-08-03 (ir 1.0 carries the parent node only) and is
folded into row 2.

The freeze record also states what it does *not* claim, and the same disclaimer travels with
the table: these are the deferred items the specifications and the extractor cards name
today, not a complete account of everything a future ir 1.x might need. A later review may
add a row the same way row 8 was added.

## What this page does not say

It does not describe how to use any of these packages — the [tutorials](../tutorials/extract-your-first-ir.md)
and [guides](../guides/pytest-plugin-and-ci-gating.md) do, and the
[API reference](api.md) is the per-symbol surface. It does not describe the eight
non-wedge properties beyond the registry contract that answers for them: they are not
implemented, and nothing here should be read as a plan to implement them. And it makes no
claim about how any workflow behaves when it runs. gebra reads definitions; LangGraph runs
them.

## Where this page is checked

`tests/docs/test_architecture_overview.py` holds every count and table on this page to the
code it describes: the sixteen packages and their export counts against the live `__all__`
lists in both directions — and against every module under `src/gebra/` that declares one, so
a package added to the distribution and not to this page fails here; the import-closure table
against a fresh interpreter per package, again both ways; the thirteen / five / eight
property counts against the registry's own slug tables; the five frozen surfaces against
their freeze records; and the backlog table line for line against
`docs/governance/EXTRACTOR-API-FREEZE.md` §2, so a row added to the record and not to this
page fails as loudly as a row invented here. The prose between the tables is reviewed, not
machine-checked, and the two examples run in CI through the DOC-01 harness.
