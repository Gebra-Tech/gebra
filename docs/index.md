# gebra

gebra reads a LangGraph workflow **definition** and answers questions about it before
anything runs. It imports and inspects a `StateGraph` builder, a compiled graph or an LCEL
`Runnable` — it never invokes one: no node function, router, tool or model is called, and
no connection is opened — then emits a hermetic intermediate representation (the Gebra IR),
runs property validators over that IR, and records content-addressed snapshots so that a
definition's evolution can be diffed. gebra verifies definitions; LangGraph runs them.

## The boundary this documentation keeps

Every validator answers about the document it was given. A passing result carries a
**witness** — structured evidence, never prose — and a failing result carries a structured
failure with the location it was found at; a pass may also carry notes or a caveat that
qualify it. Neither is a statement about what the workflow does at run time, and no page
here will phrase one as if it were. Where a page describes a frozen specification rather
than merged behaviour, it says so on the page.

The same rule applies to code. An example on this site is marked as executable, and CI then
runs exactly those bytes and holds the printed output to what the page shows —
[Executable examples](contributing/executable-examples.md) explains how. A page cannot show a
transcript its own code did not produce.

## What is on this site

Every page the navigation lists is written: the skeleton reserved one page per planned topic and
the last reservation has now been replaced. That order was deliberate — the skeleton and the
example harness landed first, so that a page's examples were executed and checked from the day it
appeared rather than from the day someone got round to it.

The site itself is built by CI on every push (`mkdocs build --strict`, where a warning is a
failure) and is not deployed anywhere yet, so these pages are read in the repository.

The pages, in the order they were written:

- this page;
- [What gebra checks](concepts/what-gebra-checks.md) — claim classes, the severity ladder,
  exit codes and strict mode, and what a finding does and does not claim;
- [The IR, node identity and graph_version](concepts/ir-and-graph-version.md) — what the
  extracted document holds and why it is hermetic, how nodes are named, and what a
  `graph_version` is derived from, worked through the pinned golden vector;
- [Extract your first IR](tutorials/extract-your-first-ir.md) — a `StateGraph` through
  `gebra.extract()` to IR YAML, how to read the extraction warnings, and what extraction can
  and cannot know about a definition;
- [Contracts and annotations](tutorials/contracts-and-annotations.md) — declaring what a node
  reads, writes and does, in code or in a `gebra.toml` sidecar; which surface wins when two
  disagree, and the line inference will not cross;
- [Verify and interpret](tutorials/verify-and-interpret.md) — running the five validators over a
  real agent and reading what comes back: witnesses, failure records, claim classes, strict mode,
  and what a finding does not claim;
- [Travel booking, end to end](tutorials/travel-booking-end-to-end.md) — the flagship tutorial:
  the whole pipeline over one agent, from a clean extraction through five seeded defects each
  caught by its named property, eight recorded versions, the four evolution steps a reviewer
  would stop on each with its diff classification, and the audit trail the store ends up
  holding — over the same assets and in the same sequence as the repository's acceptance
  scenario;
- [P-01 graph-well-formed](validators/p01-graph-well-formed.md) — the first per-validator page:
  the four conditions, the five keys of the pass witness, what a failure record names, and where
  the claim stops;
- [P-02 termination-witness](validators/p02-termination-witness.md) — the three ways to declare
  a loop bound, what the pass witness and the two failure records hold, which guard strings the
  recognizer accepts, and what witness presence does and does not claim;
- [P-04 dataflow-completeness](validators/p04-dataflow-completeness.md) — the every-path
  write-before-read rule, how to read a coverage map and an offending path, what the two failure
  diagnostics tell you to change, and where P-01 owns the finding instead;
- [P-06 effect-safety](validators/p06-effect-safety.md) — which effect tags raise an obligation,
  the retry-region and plain-cycle distinction, the protection ledger a pass returns, why a
  declared key or hook has to bind, and what a pass does not claim;
- [P-08 determinism-replay](validators/p08-determinism-replay.md) — what makes a determinism claim
  coherent, the ledger of claims a pass returns, why every finding is a WARNING and strict mode is
  the only gate, and what a pinned seed is and is not evidence of;
- [The pytest plugin and CI gating](guides/pytest-plugin-and-ci-gating.md) — the first guide: the
  marker, the `gebra_graph` and `gebra_verification` fixtures, which findings fail which item, what
  `--gebra-strict` moves and what it leaves alone, and the report-only → gate → strict rollout with
  the workflow that runs it;
- [Snapshot, diff and evolution](guides/snapshot-diff-and-evolution.md) — the `.gebra/` store, what
  the four V.S.F.E counters count, reading a diff report line by line over eight versions of one
  agent, and why the bump class routes a review rather than grading it;
- [CLI reference](reference/cli.md) — the five verbs and every flag they take, how an invocation
  names its subject, what each exit code means for each verb, and the surfaces `verify`,
  `display` and `history` write;
- [API reference](reference/api.md) — the public Python surface: every name the five frozen
  packages export, its signature or fields, and what its own docstring says it is, generated
  from those docstrings and checked against them in CI;
- [Architecture overview](reference/architecture.md) — how the pieces fit: the sixteen public
  packages, the six stages from a live agent to a diff report, which two packages import the
  execution substrate and which fourteen do not, what each freeze record costs to change, and
  the 1.x backlog appendix;
- [Install and compatibility](guides/install-and-compatibility.md) — how to install gebra from
  a checkout, the tested Python and substrate pairs and what falls outside them, what
  `GebraVersionWarning` and the out-of-range envelope warning each mean, and what a version
  change moves — the substrate's, gebra's own, and your workflow's V.S.F.E label;
- [Executable examples](contributing/executable-examples.md) — how examples on this site are
  marked, run and checked;
- [Contributor guide](contributing/index.md) — the last of them: clone to first merged change —
  the CLA, how work is chosen and what makes a task claimable, the vendored files that may not be
  edited and the guard that enforces it, what a spec defect is and what to do about one, how a
  fixture changes, commit conventions, and what the CI jobs refuse.

## How the site is arranged

| Section | What it is for |
|---|---|
| **Concepts** | What gebra checks, and what the IR and a `graph_version` are. |
| **Tutorials** | Worked, start-to-finish walkthroughs over a real agent. |
| **Validators** | One page for each of the five properties this release implements: what it reads and what its findings mean. |
| **Guides** | Adoption tasks — CI gating, snapshotting and evolution, install and compatibility. |
| **Reference** | The CLI surface, the public Python API, and an architecture overview. |
| **Contributing** | Working on gebra itself. |

Repository-internal contract documents — the CLI and report-format specifications, the
governance records and the CI notes — live beside the code under `docs/` but are **not part
of this site**. They are written for the build, not for users, and the site build excludes
them by name so the two never mix.
