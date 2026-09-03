# gebra

**Design-time verification and versioning for LangGraph agent workflows.**

[![CI](https://github.com/Gebra-Tech/gebra/actions/workflows/ci.yml/badge.svg)](https://github.com/Gebra-Tech/gebra/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%E2%80%93%203.13-blue.svg)](#install)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/release-0.0.1-blue.svg)](#status)

`gebra` reads a LangGraph workflow **definition** and answers questions about it before
anything runs. It imports and inspects a `StateGraph` builder, a compiled graph or an LCEL
`Runnable` — it never invokes one: no node function, router, tool or model is called, and no
connection is opened — then emits a hermetic intermediate representation (the Gebra IR), runs
property validators over that IR, and records content-addressed snapshots so a definition's
evolution can be diffed. gebra verifies definitions; LangGraph runs them.

```text
extract  →  verify  →  snapshot  →  diff  →  report
```

**The boundary this project keeps.** Every validator answers about the document it was given.
A passing result carries a **witness** — structured evidence, never prose — plus any
structured notes that qualify it, and a failing one carries a structured failure with the
location it was found at. Neither is a statement about what the workflow does at run time:
witness *presence* is what a P-02 result reports, and semantic termination is never claimed.
Every finding carries its claim class — DEFENSIBLE, DEFENSIBLE-A or HEURISTIC — so a reader
can tell what was decided over the document alone from what rests on a trusted declaration,
and both from an advisory lint. Three of the five properties read the topology and are defined
only over a graph P-01 has already passed; where P-01 fails, their reports are best-effort
diagnostics rather than verdicts.
[What gebra checks](docs/concepts/what-gebra-checks.md) is the long form.

## Status

`0.0.1` is the released version — the first one — and `pip install gebra` installs it. This
checkout declares `0.0.2.dev0`: development re-opened on the next patch after that release, so
installing from the tree gives you that instead, and the badge above stays on the number the
index serves. The table is what is merged in this repository, and nothing else; a row is
`available` only where the capability is in the package and covered by its tests.

| Capability | Status | Notes |
|---|---|---|
| `gebra.extract()` over a `StateGraph`, a compiled graph or an LCEL `Runnable` | available | `ir_version` 1.0; a router whose targets are decided at run time makes the document 1.1, which this build extracts but does not yet verify, snapshot or diff — exit `2`, no verdict |
| The IR models, canonical serialization and the `graph_version` digest | available | surface frozen — [IR-MODELS-FREEZE.md](docs/governance/IR-MODELS-FREEZE.md) |
| Node contracts: `@gebra.contract`, the `gebra.toml` sidecar, inference and their precedence | available | every inferred or defaulted slot carries a warning saying so |
| The five property validators — P-01, P-02, P-04, P-06, P-08 — and `verify()` | available | surface frozen — [VALIDATOR-API-FREEZE.md](docs/governance/VALIDATOR-API-FREEZE.md) |
| The other eight catalog properties (P-03, P-05, P-07, P-09…P-13) | out of scope for this phase | answered in every run by a structured not-implemented marker, never a silent pass |
| pytest plugin and the reusable CI-gate GitHub Action | available | auto-loaded through the `pytest11` entry point — see [the pytest plugin and CI gating](docs/guides/pytest-plugin-and-ci-gating.md) |
| Snapshot store, V.S.F.E versioning, structural diff, lineage and audit export | available | a diff reports what moved; classifying a change as safe or breaking is P-12, out of scope here — see [snapshot, diff and evolution](docs/guides/snapshot-diff-and-evolution.md) |
| The CLI — `verify`, `snapshot`, `diff`, `display`, `history` | available | exit codes `0` pass, `1` fail, `2` no verdict reached — see [the CLI reference](docs/reference/cli.md) |
| Published documentation site | in development | all twenty pages are written — no placeholder is left — and CI builds the site with `mkdocs build --strict` on every push; nothing deploys it, so it is read here in the repository |
| Installation from a package index | available | `pip install gebra` — the [`gebra` project on PyPI](https://pypi.org/project/gebra/); see [Install](#install) |
| VS Code extension | out of scope for this phase | specified at outline level only; no implementation is in this repository |
| Hosted control plane — registry, telemetry binding, governance | not in this repository | a separate, closed product — see [Open core](#open-core) |

## Install

From the package index:

```bash
pip install gebra
```

The published package is [`gebra` on PyPI](https://pypi.org/project/gebra/). From a checkout —
the route every contributor runs, and the one that builds the package from the tree you have:

```bash
git clone https://github.com/Gebra-Tech/gebra.git
cd gebra
pip install .
```

Python 3.10–3.13, against `langgraph` 1.x and `langchain-core` 1.x. Those ranges are the
installability envelope; the compatibility *promise* is the tested pair matrix inside them,
pinned by the `compat-cell-1|2|3` extras in [pyproject.toml](pyproject.toml) and run as twelve
CI cells. Importing gebra never fails on version grounds, and never checks either — the first
`gebra.extract()` call is what compares what you have against that matrix. A pairing inside the
declared ranges but outside a tested cell (including a Python newer than 3.13) runs, and warns
once with a `GebraVersionWarning`: "extraction unverified against this pair". A substrate
outside the ranges runs best-effort and carries the version fact as an `unsupported-construct`
warning in the extraction envelope, which the report renders.

For a development environment, the repository is managed with [uv](https://docs.astral.sh/uv/)
and `uv.lock` pins it:

```bash
uv sync --extra dev     # creates .venv from the committed lockfile
uv run pytest
```

[CONTRIBUTING.md](CONTRIBUTING.md) has the rest — the CLA, commit conventions and the review
path.

## Quickstart

Ten minutes, from an installed package to a verification report. Every command below is run
verbatim by CI against the built wheel, in a fresh environment holding only the package and
what it depends on, and the transcript is that run's own output — trimmed where a `...` line
appears, exact everywhere it does not. That wheel is built from this tree, so the version line
below reads the declared `0.0.2.dev0` rather than the `0.0.1` the index serves.

### 1. A workflow to check

Two nodes and a retry loop. Save it as `booking.py`:

<!-- gebra-quickstart:file path=booking.py -->
```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import gebra


class BookingState(TypedDict):
    query: str
    options: list[str]
    confirmation: str


@gebra.contract(reads=["query"], writes=["options"], pure=True)
def search_flights(state: BookingState) -> dict:
    return {"options": ["AA100", "BA200"]}


@gebra.contract(reads=["options"], writes=["confirmation"], effects=["billable", "irreversible"])
def book_flight(state: BookingState) -> dict:
    return {"confirmation": "PNR-1"}


def book_again(state: BookingState) -> str:
    return "done" if state["confirmation"] else "retry"


workflow = StateGraph(BookingState)
workflow.add_node("search_flights", search_flights)
workflow.add_node("book_flight", book_flight)
workflow.add_edge(START, "search_flights")
workflow.add_edge("search_flights", "book_flight")
workflow.add_conditional_edges("book_flight", book_again, {"retry": "book_flight", "done": END})
```

The two `@gebra.contract` decorators declare what each node reads, writes and does. They
attach a declaration and return the function unchanged — no wrapper, nothing called. Without
them gebra still works: it infers what it can from the node's own signature and body — never
from what a helper the node calls does — and falls back to conservative defaults, and every
slot it had to guess arrives with a warning naming the node and the slot.

### 2. Verify it

<!-- gebra-quickstart:console id=verify exit=1 -->
```console
$ PYTHONPATH=. gebra verify booking:workflow
gebra 0.0.2.dev0 — booking:workflow (extracted)
...
P-01 graph-well-formed — pass  [DEFENSIBLE]
  witness                 2 nodes reachable from START | 1 terminal node | no
orphan nodes | no unresolved targets
...
P-02 termination-witness — fail  (1 finding: 1 fatal)
  fatal: cycle-without-termination-witness  [P-02 termination-witness |
DEFENSIBLE]
    component               book_flight
    representative          book_flight -> book_flight
    cycle list              not exhaustive — a re-run after a fix may surface
another
    finding                 Simple cycle carries no declared termination witness
...
P-06 effect-safety — fail  (1 finding: 1 error)
  error: unprotected-effect-in-retry-region  [P-06 effect-safety | DEFENSIBLE-A]
    node                    book_flight
    declared effects        billable, irreversible
    anchor cycle            book_flight -> book_flight
    finding                 Effect-carrying node in a retry region without
binding protection
...
summary
  findings                1 fatal | 1 error | 0 warning
  notes                   0 carried (0 warning-grade)
  properties              5 reported | 8 produced no verdict
  strict                  off
  exit                    1 — a FATAL or ERROR finding is present, or a strict
policy promoted a warning
  snapshot                not recorded for this run: a FATAL finding is present
(PROPERTY-CATALOG-SPEC §0.2)
```

`PYTHONPATH=.` is Python's, not gebra's: the CLI imports the module you name the way any
Python program would and inserts no import path of its own. The `workflow` it reads is the
uncompiled builder; handing it `.compile()`'s result works too, and is a different document
with its own `graph_version` — a compiled graph also records compile-time facts, checkpointer
presence and interrupt gates among them, which a builder cannot know.

### 3. What the report says

Two findings — the same two conditions this repository's own acceptance scenario seeds into a
travel-booking agent as its first two defects ([`tests/dod/`](tests/dod)):

- **P-02 `termination-witness`, FATAL, DEFENSIBLE.** `book_flight` can route back to itself,
  and nothing in the definition declares a bound on that loop — no loop-variant annotation, no
  justified recursion limit, no counter guard on the router's declared condition. The finding
  says a cycle carries no declared termination witness. It does not say the workflow fails to
  terminate; that is not a question reading the definition can answer.
- **P-06 `effect-safety`, ERROR, DEFENSIBLE-A.** The same node declares `billable` and
  `irreversible` effects and sits inside that retry region with no binding protection — the
  shape that risks charging a card twice on a retry. DEFENSIBLE-A because it rests on the
  effect tags the decorator declared: gebra checks that the declaration is unprotected, never
  that the node really does what it says.

The exit code is `1`, so a CI gate fails on it. `0` means pass, `1` means a FATAL or ERROR
finding was present (or strict mode promoted a warning), and `2` means no verdict was reached
— a broken input, never a verification failure. A run carrying a FATAL finding is also
ineligible to be snapshotted, which is why the summary says the snapshot was not recorded.

Each finding has its own fix, and the gate clears only once both are addressed — and each has
to be declared where gebra reads it. **P-02** takes a loop-variant annotation on the looping
node, `@gebra.variant(key=…, measure=…)`: `key` names a state key (it must be one
`BookingState` declares) and `measure` describes the well-founded measure you are attesting
decreases on every execution of that node — an attestation gebra records and trusts, never
checks. Its other witness form, a bounded counter, is read off a router's *declared*
condition, and extraction fills that slot with the branch name rather than the router's body,
so a counter written inside `book_again` is not visible here. **P-06** takes a keyed
idempotency declaration whose key is among the node's declared reads, a compensation hook
naming an existing node, or moving the booking call out of the retry region — but never a bare
`idempotent=True` on an `irreversible` node, which is a forbidden combination and turns the
ERROR into a FATAL of its own.

`gebra verify --format json` writes the same run report as the lossless JSON record, and
`--format sarif` as the findings-only projection a code-scanning UI reads.

## From Python

The CLI is a face on a library. This example is executed in CI too, and prints what it shows.
Its one node body raises if anything calls it — which is how the run proves that extracting
and verifying the graph did not: the example is checked for that as well as for its output.

<!-- gebra:example id=readme-library -->
```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from gebra.verify import verify


class State(TypedDict):
    query: str
    answer: str


TRIPPED: list[str] = []


def plan(state: State) -> dict:
    # This body is never called. It says so out loud, so that CI can hold the claim:
    # anything that ran it would land in TRIPPED, and the example would fail.
    TRIPPED.append("plan")
    raise AssertionError("gebra does not run nodes")


workflow = StateGraph(State)
workflow.add_node("plan", plan)
workflow.add_edge(START, "plan")
workflow.add_edge("plan", END)

extracted = gebra.extract(workflow)
report = verify(extracted.ir)

print("ir", extracted.ir.ir_version, "|", len(extracted.ir.nodes), "node(s)")
print("gate", report.gate.outcome, "| exit", report.gate.exit_code)
```

<!-- gebra:output id=readme-library -->
```text
ir 1.0 | 1 node(s)
gate pass | exit 0
```

`gebra.extract()` returns an extraction envelope: the IR plus the provenance and the warnings
that explain how it was read. `verify()` runs the registered validators over that IR and
returns one run report — the same record the CLI renders.

In a test suite, the pytest plugin does this for you. Install the package and pytest loads it
through its own entry point; mark a function that returns your graph with
`@pytest.mark.gebra` and you get one test item per checked property.

## Documentation

All twenty pages of the documentation site are written; nothing publishes them yet, so they are
read here in the repository. Those, and the repository documents worth reading beside them:

- [What gebra checks](docs/concepts/what-gebra-checks.md) — claim classes, the severity ladder,
  exit codes, strict mode, and what a finding does and does not claim.
- [The IR, node identity and graph_version](docs/concepts/ir-and-graph-version.md) — what the
  extracted document holds and why it is hermetic, how nodes are named, and what a
  `graph_version` is a digest of, worked through the specification's pinned golden vector.
- [Extract your first IR](docs/tutorials/extract-your-first-ir.md) — a worked tutorial from a
  `StateGraph` to IR YAML: reading the document, reading the extraction warnings, and the four
  knowability classes that say what extraction can and cannot know.
- [Contracts and annotations](docs/tutorials/contracts-and-annotations.md) — a worked tutorial
  through the `@gebra.contract` decorators and the `gebra.toml` sidecar: the precedence chain
  that decides which declaration wins, and what inference will never fill in for you.
- [Verify and interpret](docs/tutorials/verify-and-interpret.md) — a worked tutorial through a
  verify report: what a pass witness contains, what a failure record names, where a claim class
  comes from, what strict mode moves, and what a finding does not claim.
- [Travel booking, end to end](docs/tutorials/travel-booking-end-to-end.md) — the flagship
  tutorial: the whole pipeline over one agent, from a clean extraction through five seeded
  defects each caught by its named property, eight recorded versions, the four evolution steps
  a reviewer would stop on each with its diff classification, and the audit trail the store
  ends up holding — over the same assets and in the same sequence as the repository's
  acceptance scenario.
- [P-01 graph-well-formed](docs/validators/p01-graph-well-formed.md) — the first per-validator
  explainer: the four conditions, the five keys of the pass witness, the fields of a failure
  record, and what a P-01 pass does not claim.
- [P-02 termination-witness](docs/validators/p02-termination-witness.md) — the three ways to
  declare a loop bound, the inventory-and-certificate witness, the two findings and their
  anchors, which guard strings the recognizer accepts, and the boundary of the claim.
- [P-04 dataflow-completeness](docs/validators/p04-dataflow-completeness.md) — the every-path
  write-before-read rule, the coverage-map witness, the offending path and the two optional
  diagnostics, and what a declared write is and is not evidence of.
- [P-06 effect-safety](docs/validators/p06-effect-safety.md) — the two trigger tags, the
  retry-region and plain-cycle split, the protection ledger a pass returns, why an idempotency key
  or a compensation hook has to bind, and what a declared protection is and is not evidence of.
- [P-08 determinism-replay](docs/validators/p08-determinism-replay.md) — the three coherence
  questions, the claim ledger and its mandatory caveat, the two findings and their evidence, why
  every finding is a WARNING that only strict mode gates, and what a pinned seed is not evidence of.
- [The pytest plugin and CI gating](docs/guides/pytest-plugin-and-ci-gating.md) — a guide from
  one dependency to a merge gate: the marker and the two fixtures, which findings fail which test
  item, what `--gebra-strict` moves and what it leaves untouched, and the report-only → gate →
  strict rollout, with the workflow this repository runs on every push.
- [Snapshot, diff and evolution](docs/guides/snapshot-diff-and-evolution.md) — a guide to keeping
  and reading the record of how an agent changes: the `.gebra/` store, what each of the four
  V.S.F.E counters counts, the anatomy of a diff report over eight versions of one agent, the
  per-version audit export and the freshness check, and why a bump class tells a reviewer where to
  look rather than what to conclude.
- [Install and compatibility](docs/guides/install-and-compatibility.md) — a guide to running
  gebra somewhere: the install routes and the CI job behind each, the twelve tested Python and
  substrate pairs against the wider ranges that merely install, what `GebraVersionWarning` and
  the out-of-range envelope warning each report, and what a version change moves — the
  substrate's, gebra's own, and your workflow's V.S.F.E label.
- [CLI reference](docs/reference/cli.md) — the five verbs, every flag each one takes, how an
  invocation names the definition it operates on, what `0`, `1` and `2` mean for each verb, and
  the report surfaces `verify`, `display` and `history` write.
- [API reference](docs/reference/api.md) — the public Python surface: every name the five
  frozen packages export, with its signature or its fields and what its own docstring says it
  is, generated from those docstrings and held to them in CI.
- [Architecture overview](docs/reference/architecture.md) — the as-built map: the sixteen
  public packages, the six stages from a live agent to a diff report, which two packages
  import the execution substrate and which fourteen do not, what changing each frozen surface
  costs, and the 1.x design-tracked backlog appendix.
- [Contributor guide](docs/contributing/index.md) — clone to first merged change: the CLA, how
  work is chosen and what makes a task claimable, the vendored files you may not edit and the
  guard that enforces it, what to do when a frozen document cannot be implemented as written,
  how a fixture changes, commit conventions, and what the eighteen CI jobs refuse.
- [Executable examples](docs/contributing/executable-examples.md) — how the examples on the
  site are marked, run and checked in CI.
- [The CI-gate GitHub Action](docs/ci/github-action.md) — the action's own interface reference:
  inputs, outputs and the refusal vocabulary. (A repository document, not a site page.)
- [CONTRIBUTING.md](CONTRIBUTING.md) · [CHANGELOG.md](CHANGELOG.md)

That is the site's whole navigation: no reserved placeholder is left in it.

## Open core

**This repository is the open core, and stays that way.** Everything in it — the CLI, the
extractor, the IR models, the validators, the pytest plugin, the snapshot and diff engine, and
the VS Code extension when it is built — is licensed **Apache-2.0, forever**. Nothing here is
ever re-licensed. The repository carries that license from its first commit; making it public
at launch changes nothing about it.

**The commercial product is a separate, closed repository.** The paid surface is the hosted
control plane — the workflow registry, trace-to-version telemetry binding, governance and
RBAC, and the stochastic and optimization tiers. It lives elsewhere under a proprietary
license and consumes this package as a dependency. None of it is in this repository, and none
of this repository is in it.

**Contributions require a signed Contributor License Agreement** with Gebra Tech, Inc. — see
[CLA.md](CLA.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Contact & questions

Open a [GitHub issue](https://github.com/Gebra-Tech/gebra/issues) or email
gebra.dev@gmail.com.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
