# CLI-SPEC — the `gebra` command-line interface

> **What this document is.** A repo-authored **contract specification**, produced by card
> CLI-02. It fixes the surface brief D-12's artifact table calls "five subcommands: flags, exit
> codes, diagnostics style" — the verb set, how an invocation names what it operates on, the
> exit codes it returns, and the conventions its diagnostics follow — so that the rendering
> engine (CLI-03), the four verb cards (CLI-04…CLI-06) and the integration suite (CLI-07) build
> against one surface instead of five.
>
> **It is not user documentation, and nothing here describes a shipped capability.** There is
> no `gebra` command: the package declares no console script, ships no CLI module, and imports
> `typer` nowhere. The CLI reference a user will read is DOC-15's, written after the verbs
> merge (WA-12 — docs tell no futures). The frozen, vendored specs (PROPERTY-CATALOG-SPEC,
> IR-SPEC, INTROSPECTION-SPEC, ANNOTATION-API-SPEC, …) live in the delivery repository and are
> read-only; this file restates them where it must and redefines nothing.
>
> **Status:** ratified as CLI-02's artifact. Stamped final at the D-12 promotion (CLI-08).

---

## Table of contents

- [0. Scope, authority, status](#0-scope-authority-status)
- [1. The command surface](#1-the-command-surface)
- [2. Subject resolution](#2-subject-resolution)
- [3. Exit codes](#3-exit-codes)
- [4. The verbs](#4-the-verbs)
- [5. Diagnostics conventions](#5-diagnostics-conventions)
- [6. Configuration](#6-configuration)
- [7. Conformance obligations](#7-conformance-obligations)
- [Appendix A — the consolidated flag table](#appendix-a--the-consolidated-flag-table)
- [Appendix B — open items](#appendix-b--open-items)

---

## 0. Scope, authority, status

### 0.1 The presentation-only boundary

**The CLI adds no verification semantics of its own.** This is brief D-12's own framing of its
mandate — "D-12 owns **presentation only**: it wraps logic delivered by other teams and adds no
verification semantics of its own" — and it is the constraint every other section of this
document is written under. Concretely:

1. **No verdict is reached here.** Whether a property passes, which condition ID a finding
   carries, what a witness contains and what claim class it holds are the property catalog's
   (PROPERTY-CATALOG-SPEC §0.1–§0.4) and the validators' (VAL track). The CLI calls them and
   shows what they returned.
2. **No exit code is invented here.** §3 restates PROPERTY-CATALOG-SPEC §0.2's three codes and
   points at REPORT-FORMAT-SPEC §2 for the derivation over a whole run. Where this document
   assigns a code to a non-`verify` verb, it assigns one of those three to an outcome that verb
   already has; it defines no fourth **verdict-bearing** code and no fourth meaning. (The one
   code outside the ladder is `130` for an interrupt, §3.4 — the statement that the run was
   killed, which is not an answer about a workflow at all.)
3. **No structural fact is computed here.** Topology, Σ, node contracts, digests and V.S.F.E
   labels come from the IR and the SD engines. A diff's bump class is
   `WorkflowDiff.bump_class`; a history row's step is `LineageStep`; a report's severity counts
   are `gate.counts`. The CLI recomputes none of them, and a renderer that recomputed one would
   be a second place for the derivation to drift.
4. **No copy overstates what was checked.** Every rendered finding carries its claim class,
   witness-presence wording is the only wording P-02 gets, and a not-implemented marker is
   never shown as a pass (REPORT-FORMAT-SPEC §4.6, WA-06, lint-enforced by TE-15).
5. **Nothing is executed.** §0.5.

A change that would give a verb a verdict of its own — a severity the catalog does not define,
a safe/breaking classification for a diff, a pass/fail for `display` — is out of scope for this
document and for every card that cites it. The route for one is a spec change in the track that
owns the semantics, never a flag added here.

### 0.2 What this document fixes

1. The verb set and the invocation shape (§1), per the CLI-D4 ruling (PD-033).
2. Subject resolution: the three input modes, the target grammar, and what resolving a live
   target is and is not allowed to do (§2) — the card's `input-mode design` decision.
3. The exit codes of every verb, as a complete table (§3), passing through
   PROPERTY-CATALOG-SPEC §0.2 and REPORT-FORMAT-SPEC §2.
4. Each verb's arguments, flags, output surface and failure modes (§4) — the card's
   `flag surface details` decision, consolidated in Appendix A.
5. The diagnostics conventions (§5), per the CLI-D3 ruling (PD-031): framework, degradation,
   streams, multi-error reporting, did-you-mean suggestions, and the copy rules.
6. Configuration: what is *not* configurable in Phase-0 and why (§6) — the card's
   `config-file support` decision.

### 0.3 Authority chain

| Question | Authority |
|---|---|
| Severity ladder, the three exit codes, strict-mode semantics | PROPERTY-CATALOG-SPEC §0.2 — **frozen**; this document restates, never redefines |
| Claim classes, condition IDs, witness/failure/location shapes | PROPERTY-CATALOG-SPEC §0.1, §0.3, §0.4 — **frozen** |
| The run report, exit-code derivation over a run, rendering catalog, SARIF projection | REPORT-FORMAT-SPEC (card CLI-01) |
| Which machine formats ship, and under which flag | PD-015 (CLI-D1 ruling, ratified 2026-07-31) |
| Terminal diagnostics framework and its degradation | PD-031 (CLI-D3 ruling, ratified 2026-08-04) |
| The fifth verb's name and its output shape | PD-033 (CLI-D4 ruling, ratified 2026-08-04) |
| Diagram strategy and overlay encoding | PD-034 (CLI-D2 ruling, ratified 2026-08-04); DIAGRAM-STYLE-GUIDE (CLI-06) |
| What extraction may do to a live object | INTROSPECTION-SPEC §1–§2 — **frozen**; in code, `gebra.extraction.extract` |
| Sidecar discovery and annotation precedence | ANNOTATION-API-SPEC §2, §5 — **frozen** |
| Store layout, paths, file naming | PD-012 (SD-D2 ruling); in code, `gebra.store.SnapshotStore` |
| Snapshot writing, re-snapshot and version-assignment policy | SD track (SD-01, SD-02, SD-03) |
| Structural diff content and its S/F/E bump class | SD track (SD-04, SD-05); in code, `gebra.diff` |
| Version history content and its JSON projection | SD track (SD-06); in code, `gebra.lineage` |
| The pytest plugin's own flag surface | brief D-10; card TE-07 |

Where this document and a frozen spec appear to disagree, the frozen spec wins and the
disagreement is a defect to file (WA-03), never a local reinterpretation. Where it and
REPORT-FORMAT-SPEC appear to disagree about a report, REPORT-FORMAT-SPEC wins and the fix is an
edit to one of the two.

### 0.4 What this document does not own

- **Verification semantics** — §0.1.
- **The run report's shape, its serialization and its SARIF projection** — REPORT-FORMAT-SPEC.
  This document says which surface a flag selects, never what the surface contains.
- **Renderer architecture, palette, column widths, exact layout and wording** — CLI-03's
  latitude (its card and PD-031), within REPORT-FORMAT-SPEC §4/§5's fact sets and copy rules.
- **Diagram style, overlay encoding, large-graph handling** — CLI-06 and DIAGRAM-STYLE-GUIDE,
  within PD-034's sketch.
- **Snapshot policy** — whether an unchanged workflow is re-snapshot, and what label a new
  snapshot gets, are SD-03's; `gebra snapshot` passes the question to the engine and reports
  the answer.
- **The pytest plugin's flags** — TE-07's. The two surfaces must tell the same story in the
  same vocabulary (D-12's shared-formatting requirement); they are not required to spell their
  flags identically, and §3.3 fixes the one spelling they do share.

### 0.5 Never-invokes

WA-07 and INTROSPECTION-SPEC §1 bind every path this document describes: **no verb executes a
workflow node, a router, a tool or a model, and none opens a network connection.** Two
consequences are worth stating explicitly, because the CLI is the one place a user hands gebra a
*live* object rather than a file:

1. **Importing is not invoking, and it is the user's own act.** Resolving an import target
   (§2.4) imports the named module, which runs that module's top-level code — the same thing
   `import travel_booking` does in a REPL. Beyond that import, **the CLI calls nothing on its
   own initiative**: it reads the attribute, and it hands what it found to `extract()`. The one
   case where the CLI calls a user object at all is the explicit `--call` opt-in of §2.4, which
   exists precisely so that executing user code is something a user asked for by name.
2. **What happens after that is `extract()`'s, and this document does not restate it.**
   INTROSPECTION-SPEC §1 is the never-invokes authority for extraction, including the one
   substrate call its §4.2/§4.3 cross-check licenses — `get_graph()`, which the shipped
   extractor makes behind the hazard gate `gebra.extraction.compiled` documents, on stock
   substrate objects only. The CLI adds no call of its own to that surface and relaxes no gate;
   claiming here that extraction makes *no* substrate call would misstate the frozen rules it
   defers to.
3. **The tripwire lands with the path, per card.** WA-07 requires never-invokes coverage in the
   same change as each new extraction path, and three verbs can reach one:

   | Path | Card that must land its tripwire |
   |---|---|
   | `gebra verify` over a live target | CLI-04 |
   | `gebra snapshot` over a live target | CLI-05 |
   | `gebra diff` with one or both sides a live target | CLI-05 |

   Each lands a sentinel target module exercised **through the CLI's own entry point**, not
   through `extract()` alone, arming at least: node callables in the returned graph; an
   attribute that is a zero-argument callable but not a graph factory (pinning §2.4's refusal
   to call without `--call`); an attribute whose callable needs arguments (pinning the exit-2
   refusal); and an import-time marker, so the "top-level code runs" concession above is
   observed rather than assumed. The sentinel derives from `BaseException` and **records the
   call before raising**, and the assertion is on that record — never on the exit code, which
   §3.4 makes uninformative by mapping an escaping exception to a specified exit `2`. This is
   the pattern `tests/sample_workflows/sentinel_resolution.py` already uses, and the reason it
   uses it.

`gebra display` and `gebra history` reach no live object at all: `history` reads a store, and
`display` accepts no import reference (§4.4) — an import-shaped target given to it is a usage
error, not a resolution.

### 0.6 Code anchors

The package symbols this document names. They exist today; the CLI that will call them does
not. `tests/docs/test_cli_spec.py` imports every row, so a rename in the package fails a test
here rather than rotting quietly in prose.

| Symbol | What the CLI uses it for |
|---|---|
| `gebra.__version__` | `tool.version` in a run report; `gebra --version` |
| `gebra.extraction.extract` | the one extraction entry point, for a live target (§2.4) |
| `gebra.extraction.ExtractionError` | a refused object — exit 2, `stage: "extraction"` |
| `gebra.ir.read_ir` | loading an IR document, YAML or JSON by suffix (§2.2) |
| `gebra.ir.YAML_SUFFIXES` | the `.yaml`/`.yml` half of the suffix rule |
| `gebra.ir.JSON_SUFFIXES` | the `.json` half of the suffix rule |
| `gebra.ir.IR_VERSION` | `subject.ir_version` |
| `gebra.ir.graph_version` | `subject.graph_version` for a subject that carries no digest yet |
| `gebra.store.SnapshotStore` | every store read and write (§2.5) |
| `gebra.store.STORE_DIRNAME` | the default store directory name (`.gebra`) |
| `gebra.store.SNAPSHOTS_DIRNAME` | where snapshots live under it |
| `gebra.store.REPORTS_DIRNAME` | where SD-07's audit exports live under it |
| `gebra.store.META_FILENAME` | the store index `history` and `current` are read from |
| `gebra.store.StoreError` | a store refusal — exit 2 |
| `gebra.versioning.Version` | parsing and comparing a V.S.F.E label |
| `gebra.versioning.VersionFormatError` | a malformed label — exit 2 |
| `gebra.diff.workflow_diff` | `gebra diff`'s engine call |
| `gebra.diff.WorkflowDiff` | what it renders, including `bump_class` |
| `gebra.diff.EVOLUTION_SAFETY_DEFERRED` | the deferred-P-12 marker every diff carries (§4.3) |
| `gebra.lineage.lineage` | `gebra history`'s engine call |
| `gebra.lineage.compare` | the two-version diff over a store (§4.3) |
| `gebra.lineage.dump_lineage` | `gebra history --format json` |
| `gebra.lineage.LINEAGE_DOCUMENT_VERSION` | the version line that projection carries |
| `gebra.lineage.LineageError` | an unknown or empty window — exit 2 |
| `gebra.verify.PROPERTY_SLUGS` | the thirteen catalog slugs `--strict=<slug>` ranges over |
| `gebra.verify.WEDGE_SLUGS` | the five whose absence is a dispatch error (§3.1) |
| `gebra.verify.NotImplementedMarker` | the outcome shown as *not checked*, never as a pass |
| `gebra.verify.to_json` | the serialization profile a machine report is written under |

---

## 1. The command surface

### 1.1 The five verbs

```
gebra verify | snapshot | diff | display | history
```

| Verb | One line | Wraps | Card |
|---|---|---|---|
| `verify` | Run the registered validators over a workflow definition and report the result. | `verify()` aggregation (VAL-11) over `gebra.extraction` / `gebra.ir` | CLI-04 |
| `snapshot` | Record a V.S.F.E-versioned snapshot of a workflow definition. | `gebra.store` + SD-03's engine | CLI-05 |
| `diff` | Show what moved between two workflow definitions, and which counters it bumps. | `gebra.diff.workflow_diff` | CLI-05 |
| `display` | Render a workflow definition as Mermaid, optionally overlaid with a run report. | CLI-06's emitter over `gebra.ir` | CLI-06 |
| `history` | List the versions a store holds, oldest first, with per-step summaries. | `gebra.lineage` | CLI-05 |

**The fifth verb is `history`, not `trace`.** PD-033 (CLI-D4, ratified 2026-08-04) renamed it
before it shipped: `trace` means runtime traces bound to a graph in a future hosted
surface, so the name collided at three separate layers, and nothing in the package spells a
verb `trace`. `gebra trace` is not an alias, not a deprecation shim and not a hidden command —
it does not exist, and a user who types it gets the unknown-verb diagnostic of §5.4.

### 1.2 Invocation shape

```
gebra [--version] [--help]
gebra <verb> [ARGUMENTS] [OPTIONS]
```

- One verb per invocation. There are no verb aliases and no abbreviation matching: `gebra ver`
  is an unknown verb, not `verify` (an abbreviation that resolves today can resolve elsewhere
  when a later verb is added, and a CI line that changes meaning on upgrade is worse than one
  that fails).
- Options may follow their arguments or precede them; `--` ends option parsing, so a target
  whose name begins with `-` stays addressable.
- Long options only, with two exceptions: `-o` for `--output` and `-h` for `--help`. A one-verb,
  CI-facing tool gains little from short flags and loses the readability of a CI line that
  states what it does.

### 1.3 Options every verb accepts

| Option | Meaning |
|---|---|
| `--help`, `-h` | Print the verb's usage and exit `0`. |
| `--color` / `--no-color` | Force styled or plain output, overriding auto-detection (§5.1). |

`--version` is an application-level option only (`gebra --version`): it prints
`gebra <gebra.__version__>` on stdout and exits `0`. It is not a per-verb flag, because a run
report already carries `tool.version` and a second place to read it invites the two to drift.

### 1.4 What is not a verb

- **No `gebra run`, and no execution flag anywhere.** gebra never executes a workflow (D-018,
  amended by D-023: execution belongs to the substrate). This is not a gap to be closed later
  in this repository.
- **No `gebra init`, `test` or `push`.** Those were D-04's Rust/clap CLI for the bespoke DSL
  pipeline, which brief D-12 supersedes.
- **No `gebra export`.** MCP/OpenAPI export of verified IR is brief D-13, post-MVP.
- **No extension commands.** The VS Code lens (decision D-028) is P2 and outline-level only
  (CLI-08); nothing in Phase-0's CLI serves it.
- **No property-selection flags** (`--select`, `--skip` or equivalents) on `gebra verify`. The
  exit codes of §3 are defined over a run of all thirteen properties, and REPORT-FORMAT-SPEC
  §1.4 rule 2 makes a run missing a wedge validator a tool error rather than a thin gate wearing
  a pass. Selection stays with the pytest plugin (TE-07), where the scope of a test run is the
  user's own choice, expressed per test rather than per gate.

---

## 2. Subject resolution

A verb operates on a **subject**: one workflow definition, obtained one of three ways. The
three ways are exactly REPORT-FORMAT-SPEC's `Subject.input_mode` values, and resolution is what
fills that model.

### 2.1 The three input modes

| `input_mode` | The subject is | Obtained by | `subject.source` |
|---|---|---|---|
| `extracted` | a live object in an importable module | `gebra.extraction.extract` (§2.4) | the target reference the invocation named, verbatim (e.g. `travel_booking:build_graph`) |
| `ir-document` | a serialized IR file | `gebra.ir.read_ir` | the path exactly as the invocation gave it |
| `snapshot` | one stored version in a `.gebra/` store | `gebra.store.SnapshotStore.read` | the stored snapshot's `extracted_from.source` |

`subject.version` (the V.S.F.E label) is present exactly in `snapshot` mode, and
`subject.extractor_version` exactly in `extracted` mode — both are REPORT-FORMAT-SPEC §1.2's
model invariants, not this document's rules.

### 2.2 The target grammar and the detection rule

Every verb that takes a subject takes it as a positional `TARGET`. The mode is read off the
target's own grammar, in this order, and the three grammars are disjoint:

1. **V.S.F.E label** — four dot-separated ASCII decimal components, matching
   `^\d+\.\d+\.\d+\.\d+$` (`gebra.versioning.Version`). → `snapshot` mode, resolved against the
   store of §2.5. Example: `1.4.2.0`.
2. **IR document** — a target whose suffix is one of `gebra.ir.YAML_SUFFIXES` or
   `gebra.ir.JSON_SUFFIXES` (`.yaml`, `.yml`, `.json`). → `ir-document` mode. Example:
   `build/travel-booking.ir.yaml`. The suffix decides, and nothing sniffs content — the same
   rule `read_ir` already applies.
3. **Import reference** — `module[.submodule…]:attribute`, matching
   `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$`. →
   `extracted` mode. Example: `travel_booking:build_graph`.
4. **Anything else** is a resolution failure: exit `2`, `stage: "input"`, with the diagnostic
   of §5.4 naming which of the three shapes the target came closest to.

Rule 1 precedes rule 2 because a label has no suffix, and rule 2 precedes rule 3 because a
Windows path can carry a colon while no import reference carries a recognized IR suffix. A
target that would match two rules is a bug in this table, not a coin flip in an implementation:
the ordering is normative and CLI-04 tests it directly.

**Not every verb accepts every mode.** The rules above say which mode a target *names*; which
modes a verb *takes* is that verb's own table (§4), consolidated in Appendix A. A target whose
grammar names a mode its verb does not accept is a usage error (exit `2`, §3.4) saying so — it
is never resolved through a mode the verb does not have. This is what closes `gebra display`:
rule 3 is not available there, so `gebra display travel_booking:build_graph` is refused before
any import happens, and `display` reaches no live object on any path (§0.5, §4.4).

### 2.3 Explicit mode selectors

Detection is a convenience, never the only way in. Each mode has an explicit selector that
skips detection entirely:

| Selector | Mode | Notes |
|---|---|---|
| `--ir PATH` | `ir-document` | Removes the detection ambiguity for a path §2.2 would read as something else (a file literally named `1.4.2.0`, say). It does not widen the loader: `read_ir` still chooses YAML or JSON by suffix, and still refuses a suffix it does not recognize. |
| `--import REF` | `extracted` | `REF` must match rule 3's grammar. |
| `--snapshot VERSION` | `snapshot` | `VERSION` must be a V.S.F.E label held by the store. |

The selectors are mutually exclusive with each other and with a positional `TARGET`. Giving two
is a usage error (exit `2`, §3.4) naming both, never a silent precedence. Giving none, on a verb
that requires a subject, is a usage error too — no verb guesses a default subject from the
working directory.

### 2.4 Import-path resolution, and its never-invokes boundary

Resolving `module:attribute` is exactly three steps, and the boundary between them and anything
else is load-bearing (§0.5, WA-07):

1. **Import the module** with `importlib.import_module`. The module's top-level code runs — the
   user asked for this module by naming it, and a definition that only exists after its module
   executes cannot be reached any other way. `sys.path` is the interpreter's own (the working
   directory and `PYTHONPATH` behave as they do for any Python program); the CLI inserts no
   path of its own, so an invocation that works in a shell works the same way under CI.
2. **Read the attribute** with `getattr`. Nothing is called.
3. **Refuse anything that is not already a workflow object** — unless the invocation carried
   `--call`:
   - the attribute **is** a workflow object (a `StateGraph`, a compiled graph, or another
     `Runnable`) → it is the subject, and nothing was called;
   - the attribute is anything else → refused: exit `2`, `stage: "input"`, naming what it found
     and telling the user either to name a module-level graph object (`graph = build_graph()`
     in their own module — the construction then happens at import, which is step 1's already-
     licensed act) or to pass `--call` if they want gebra to call this attribute.

**`--call` is the one place the CLI executes user code on purpose, and it is opt-in.** With it,
step 3 calls the named attribute **once, with no arguments**, and takes the return value as the
subject. Three rules bound it:

- **No arity introspection.** The CLI does not probe the callable's signature to decide whether
  calling it is safe: a signature probe is itself user-influenced (`__signature__`,
  `__wrapped__`), and "takes no arguments" does not distinguish a graph factory from an
  application entry point. It calls with no arguments; a callable that needed some raises, and
  that is exit `2`, `stage: "input"`, with the exception reported.
- **gebra makes no claim about what the call does.** A factory that reaches the network or
  warms a model client is doing so because the user named it and passed `--call` — the same
  category as the module-level code step 1 runs. What this document fixes is what *gebra*
  does: one call, no arguments, nothing else, and then `extract()`'s frozen read-only
  introspection over whatever came back (§0.5 item 2).
- **The refusal is the default.** Without `--call`, no attribute is ever called, so
  `gebra verify travel_booking:main` cannot start an application by accident. The refusal
  message is a usage aid, not a fallback that quietly does it anyway.

`extract()` then produces the IR and its envelope. `--sidecar PATH` overrides
ANNOTATION-API-SPEC §2's discovery for this extraction (it is `extract()`'s own `sidecar`
argument, passed through); it is accepted only in `extracted` mode, since the other two modes
extract nothing, and giving it elsewhere is a usage error rather than a silently ignored flag.
On `gebra diff`, where each side resolves independently, `--sidecar` is accepted only when
exactly one side is an import reference; with two, discovery applies to both and the flag is a
usage error rather than a path silently used twice.

Extraction warnings are rendered, never dropped (§5.2). An `ExtractionError` is exit `2` with
`stage: "extraction"`.

### 2.5 Store resolution

`--store DIR` names the store directory itself — the directory that contains
`gebra.store.SNAPSHOTS_DIRNAME` and `gebra.store.META_FILENAME`. Its default is `./.gebra` —
the `gebra.store.STORE_DIRNAME` directory in the working directory, which is what
`SnapshotStore.for_project(Path.cwd())` computes.

There is **no upward search** for a store. Sidecar discovery walks upward because
ANNOTATION-API-SPEC §2 says it does; a store does not, because an invocation that silently
found a parent project's store would write a snapshot into a history the user was not looking
at. A store that does not exist reads as an empty one (that is `SnapshotStore`'s own rule), so
`gebra history` in a project with no store lists an empty history and exits `0`; `gebra
snapshot` creates the store on first write.

### 2.6 Resolution failures

Every failure below is exit `2` — no verdict was reached — and carries the
REPORT-FORMAT-SPEC §2.4 stage it maps to:

| Failure | `stage` |
|---|---|
| Target matches none of the three grammars | `input` |
| IR document missing, unreadable, or of an unrecognized suffix | `input` |
| Module not importable, attribute missing, attribute not a workflow object with no `--call` given, or a `--call` attribute that raised | `input` |
| Version label malformed, or not held by the store | `input` |
| Store index unreadable, snapshot file missing or failing its digest check | `input` |
| Importing the module raised | `input` |
| A `--report` overlay file is unreadable, is not a valid run report, or carries a `report_format` MAJOR this build does not know (§4.4) | `input` |
| `extract()` raised `ExtractionError` | `extraction` |
| An IR document did not validate against `ir_version` 1.0 | `ir-validation` |
| A wedge validator is not registered, or a validator answered for another property | `dispatch` |

Reach: `ir-validation` applies to every verb that loads an IR document; `dispatch` is reached
only by a run that dispatches validators — `gebra verify`, and the eligibility run inside
`gebra snapshot` (§4.2). Everything else applies to every verb that resolves a subject. For
verbs that emit no run report (§4.3–§4.5), the stage is still the vocabulary the diagnostic
uses, so one taxonomy covers the whole CLI.

---

## 3. Exit codes

### 3.1 The three codes

PROPERTY-CATALOG-SPEC §0.2 fixes three, and those three are the only codes that say anything
about a workflow. Restated here, not redefined:

| Exit code | Condition (§0.2) |
|---|---|
| `0` | Verify pass: zero FATAL/ERROR findings. WARNING findings may be present; they are rendered as notes and do not affect the code. |
| `1` | Verify fail: at least one FATAL or ERROR finding — or a WARNING promoted under strict mode. FATAL additionally suppresses snapshot recording. |
| `2` | Tool error: extraction or IR validation failed before any property ran. No verdict was reached; exit 2 is never a verification result. |

The derivation over a whole run — which records count as findings, how strict mode reaches
them, and why a missing wedge validator is a tool error — is REPORT-FORMAT-SPEC §2, and
`gebra verify` returns `gate.exit_code` from the run report it rendered. It computes nothing
alongside it.

### 3.2 The complete per-verb table

Every verb, every code it can return, and the condition. A cell reading *never* is a statement,
not an omission: that verb cannot return that code.

| Verb | `0` | `1` | `2` |
|---|---|---|---|
| `verify` | `gate.outcome` is `pass` or `pass-with-notes` — no FATAL/ERROR finding, and no strict promotion | `gate.outcome` is `fail` — at least one FATAL or ERROR finding, or at least one WARNING-grade record promoted by the strict policy (§3.3) | `gate.outcome` is `tool-error` — any row of §2.6; the run report carries `error.stage` and no outcomes |
| `snapshot` | the store call completed: a snapshot was recorded, or SD-03's policy recorded nothing because nothing moved | recording was refused because the run was not snapshot-eligible — `gate.snapshot_eligible` is `false` which, for a run that reached a verdict, is `counts.fatal > 0` (§0.2: a FATAL means no snapshot is recorded; the field's full derivation is REPORT-FORMAT-SPEC §2.5's) | subject resolution failed (§2.6), the run that decides eligibility reached no verdict (any tool-error stage, §2.6), or the store refused the write (`StoreError`) |
| `diff` | the comparison completed — by default whether or not anything moved | **only with `--exit-code`**: the comparison completed and the two sides differ (`WorkflowDiff.has_changes`). A difference signal, never a verdict — §4.3 | either side failed to resolve (§2.6), or a stored snapshot failed its digest check |
| `display` | the diagram was emitted | *never* — `display` reaches no verdict and reports no difference | the subject failed to resolve (§2.6), or an overlay report was refused (§4.4) |
| `history` | the history was listed, including an empty history from a store that does not exist | *never* — a listing is not a verdict | the store index was unreadable, or a window argument named a version the history does not hold |

Two rules bind the whole table:

- **Exit `2` never carries a verdict.** Whatever partial work happened, an exit-2 invocation
  says only that no answer was reached — REPORT-FORMAT-SPEC §2.4 keeps `properties` empty for
  exactly this reason.
- **Exit `1` is only ever "the gate says no".** For `verify` it is a failing gate; for
  `snapshot` it is §0.2's own refusal to record; for `diff --exit-code` it is a requested
  difference signal. No verb returns `1` for a condition it merely found interesting.

### 3.3 Strict mode

```
--strict                      promote every WARNING in the run
--strict=<slug>[,<slug>…]     promote only the named properties' WARNINGs
```

`--gebra-strict` is accepted as an **exact alias** of `--strict`, in both forms. It is the
spelling PROPERTY-CATALOG-SPEC §0.2 writes, and the one TE-07's pytest plugin is to carry, so
an invocation copied from the frozen spec — or from a CI file that also runs the plugin — works
unchanged; `--strict` is the canonical spelling for a dedicated binary, matching the unprefixed
`--format` §0.5 writes. The two spellings are one flag: same semantics, same recording, and
giving both is a usage error rather than a double promotion. **`gebra verify --help` shows both
spellings**, so a reader who arrived from the frozen spec finds the one they typed.

- `<slug>` values are the thirteen catalog slugs of `gebra.verify.PROPERTY_SLUGS`. An
  unrecognized slug is a usage error (exit `2`) with the did-you-mean of §5.4 — never a silently
  ignored name, which would leave a CI gate quietly weaker than its author believed.
- The policy in force is recorded verbatim in `gate.strict` (`mode: off | all | per-property`,
  with `properties` for the third), so a reader of the report knows which gate produced the
  code.
- **Promotion moves the gate, never the record.** A promoted finding keeps `severity: warning`
  and its claim class; the only trace is `gate.exit_code`, `gate.outcome` and
  `gate.promotions`. Rendering a promoted HEURISTIC advisory with the weight of a DEFENSIBLE
  finding is the overstatement WA-06 exists to prevent (REPORT-FORMAT-SPEC §4.6 rule 6).
- **Reach** is REPORT-FORMAT-SPEC §2.3's, unchanged: WARNING failures, co-failures, advisories
  (matched on the record's own owning property, not its host report) and WARNING-grade witness
  notes.
- `--strict` is accepted by `gebra verify` only. It is a gate policy, and the other four verbs
  have no gate; in particular `gebra snapshot` does not take it, because snapshot eligibility
  turns on `counts.fatal` alone and promotion never moves the ladder (REPORT-FORMAT-SPEC §2.5).

### 3.4 Usage errors, interrupts and unhandled exceptions

- **A usage error is exit `2`**: an unknown verb, an unknown flag, a missing required argument,
  two mutually exclusive selectors, a flag on a verb that does not accept it, a target naming a
  mode the verb does not accept (§2.2), or a flag value outside its closed set. A usage error is
  **not** a tool error in the run report's sense: the invocation never became a run, so it has
  no `ToolError.stage`, and **no run report is emitted on any format** — including
  `--format json`, where the alternative would be a report describing something that never ran.
  It is a stderr diagnostic and an exit code, and nothing else (§5.5).
- **An interrupt (SIGINT) is exit `130`** — the shell convention for "terminated by SIGINT",
  and deliberately outside §0.2's three codes, which describe answers. A CI system reading
  `130` learns the run was killed, not that a workflow failed.
- **An unhandled exception is exit `2`**, reported as a tool error with the traceback on
  stderr and an invitation to file it. A crash is not a finding (REPORT-FORMAT-SPEC §2.4) and
  must never be reported as a clean run.

### 3.5 What never moves an exit code

- **Extraction warnings.** They are rendered (§5.2), and they are not findings: the severity
  ladder is the catalog's, and INTROSPECTION-SPEC §8's warning taxonomy is a different
  vocabulary. A warning-free extraction is a strict-mode bar for the *extractor*'s conformance
  suite (EX-14), not a CLI gate.
- **Not-implemented markers.** The eight non-wedge properties are outside Phase-0 scope; a run
  is neither stronger nor weaker for saying so (REPORT-FORMAT-SPEC §2.2).
- **Did-you-mean suggestions, progress output and styling.** Display only.
- **`--no-color`, `--format`, `-o`.** Choosing a surface never changes the answer written on
  it. CLI-07 tests this directly: the same subject under all three `verify` formats returns one
  exit code.

---

## 4. The verbs

Each subsection fixes the verb's synopsis, its arguments and flags, what it writes, and its
exit codes. Layout, column widths, ordering within a block and phrasing are CLI-03's, CLI-05's
and CLI-06's latitude within REPORT-FORMAT-SPEC §4/§5 and DIAGRAM-STYLE-GUIDE.

### 4.1 `gebra verify`

```
gebra verify [TARGET] [--ir PATH | --import REF | --snapshot VERSION] [--store DIR]
             [--sidecar PATH] [--call] [--strict[=SLUG,…]] [--format {human,json,sarif}]
             [--output PATH] [--color | --no-color]
```

Resolves a subject (§2), obtains its IR, runs the registered validators through the `verify()`
aggregation (VAL-11), and writes the resulting run report on the selected surface. It reaches
no verdict of its own and returns `gate.exit_code`.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--ir` / `--import` / `--snapshot` | see §2.3 | — | explicit mode selectors, mutually exclusive with `TARGET` |
| `--store` | directory | `./.gebra` | the store `--snapshot` resolves against (§2.5) |
| `--sidecar` | path | ANNOTATION-API-SPEC §2 discovery | the `gebra.toml` extraction uses; `extracted` mode only (§2.4) |
| `--call` | — | off | call the named attribute once, with no arguments, to obtain the workflow object; `extracted` mode only, and the only path on which the CLI executes user code (§2.4) |
| `--strict` | absent, bare, or `=<slug>[,<slug>…]` | absent | strict promotion (§3.3); alias `--gebra-strict` |
| `--format` | `human`, `json`, `sarif` | `human` | which of REPORT-FORMAT-SPEC §0.1's three surfaces to write |
| `--output`, `-o` | path | stdout | write the artifact to a file instead of stdout (§5.2) |
| `--color` / `--no-color` | — | auto-detected | force styled or plain output (§5.1) |

**Formats.** `human` is the default terminal rendering (REPORT-FORMAT-SPEC §5, PD-031's
framework). `json` is the run report itself, serialized under §1.5's profile — lossless, and
what the pytest plugin and any non-GitHub CI consume. `sarif` is the lossy, findings-only SARIF
2.1.0 projection of REPORT-FORMAT-SPEC's Appendix A — a clean run still emits a log with
`results: []`, so a
consumer closes fixed alerts. This answers REPORT-FORMAT-SPEC's open item OI-6: **`json` must
be spelled explicitly**; the no-flag default is the human surface, and `--format human` is a
legal way to say so in a script that wants to be explicit.

**Snapshot subjects.** `--snapshot 1.4.2.0` verifies a stored version rather than the working
definition: `subject.input_mode` is `snapshot`, `subject.version` carries the label, and
`subject.graph_version` is the stored digest. This is the same document SD-07's audit export
writes (REPORT-FORMAT-SPEC §6); the CLI does not write that file (Appendix B, OI-4).

**Exit codes.** §3.2's `verify` row.

### 4.2 `gebra snapshot`

```
gebra snapshot [TARGET] [--ir PATH | --import REF] [--store DIR] [--sidecar PATH]
               [--call] [--quiet] [--color | --no-color]
```

Records a V.S.F.E-versioned snapshot of the resolved subject in the store. `--snapshot` is not
a selector here: a stored version is already a snapshot.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--ir` / `--import` | see §2.3 | — | explicit mode selectors |
| `--store` | directory | `./.gebra` | the store written to; created on first write (§2.5) |
| `--sidecar` | path | discovery | as `verify` (§2.4) |
| `--call` | — | off | as `verify` (§2.4) |
| `--quiet` | — | off | write only the recorded version label to stdout, or nothing when nothing was recorded |
| `--color` / `--no-color` | — | auto-detected | as `verify` |

**The §0.2 recording rule binds this verb.** A FATAL finding means no snapshot is recorded, so
`gebra snapshot` reads `gate.snapshot_eligible` from a verify run over the same subject and
refuses to write when it is `false` (exit `1`, with the FATAL findings rendered so the refusal
is legible). It applies that field; it does not re-derive the rule, and there is no flag to
bypass it — a flag that recorded a snapshot §0.2 says must not be recorded would be the CLI
adding semantics of its own (§0.1).

**The subject is resolved once.** The eligibility run and the write share one resolution and one
IR: a module is imported once, a `--call` attribute is called at most once per invocation, and
the digest the store records is the digest the gate saw. Resolving twice would double any
side effect the user's own module has and could, in principle, record a snapshot of something
the gate never examined.

**What it writes.** On success: the version label recorded, the file it was written to, and
which of S/F/E moved relative to the previous current version. When SD-03's policy records
nothing (an unchanged workflow, per its own re-snapshot rule), that is exit `0` and a statement
that nothing moved — never a fabricated new label. Label assignment and re-snapshot policy are
SD-03's; this verb reports the engine's answer.

**Exit codes.** §3.2's `snapshot` row.

### 4.3 `gebra diff`

```
gebra diff BEFORE AFTER [--store DIR] [--sidecar PATH] [--call] [--exit-code]
           [--output PATH] [--color | --no-color]
```

Renders the structural delta from `BEFORE` to `AFTER`. Both sides are positional and both are
required: there is no implied "latest versus working" default, because a default that changed
with the store's contents would make a CI line mean different things on different days. Each
side resolves independently by §2.2's rules, so a version label, an IR document and an import
reference may be mixed freely — `gebra diff 1.4.2.0 travel_booking:build_graph` compares a
stored version against the working definition.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--store` | directory | `./.gebra` | the store a version-label side resolves against |
| `--sidecar` | path | discovery | applies to an import-reference side; a usage error when the sides that are import references number anything other than one (§2.4) |
| `--call` | — | off | applies to every import-reference side of this invocation (§2.4) |
| `--exit-code` | — | off | return `1` when the two sides differ (§3.2) |
| `--output`, `-o` | path | stdout | write the rendering to a file |
| `--color` / `--no-color` | — | auto-detected | as `verify` |

**What it renders.** `WorkflowDiff` as the engine returns it: both anchors (each side's
`graph_version`, plus its V.S.F.E label when the side came from a snapshot), the topology,
contract and state deltas, the `regrouped` flag, and the **S/F/E bump class**. When both sides
are stored versions the engine call is `gebra.lineage.compare`, which reads both snapshots with
the store's digest check on.

**The deferred-P-12 marker is rendered honestly.** Every `WorkflowDiff` carries
`EVOLUTION_SAFETY_DEFERRED` — the property registry's `not_implemented("evolution-safety")`
marker. It renders as *not checked*, with its status, exactly as a marker renders in a run
report (REPORT-FORMAT-SPEC §4.2): **no diff is labelled safe or breaking**, in any format, at
any severity. P-12 `evolution-safety` is outside the Phase-0 wedge (SOW §8), the bump class is
a statement about which counters moved and not about risk, and copy that turned one into the
other would be precisely the overclaim WA-06 forbids. A diff has no surrounding pass/fail
context to read the marker against, so one more rule holds here that §4.2 there states for a
run: the marker is **never** rendered as a pass, as "no issues found", or as a clean bill —
a diff that changed nothing says the counters did not move, which is a different sentence.

**Exit codes.** §3.2's `diff` row. `--exit-code` is opt-in for a reason: without it, a CI step
that diffs for information never fails on having found information, and with it the `1` means
"these differ", carrying no claim about whether the difference is safe.

### 4.4 `gebra display`

```
gebra display [TARGET] [--ir PATH | --snapshot VERSION] [--store DIR]
              [--report PATH] [--format mermaid] [--output PATH] [--color | --no-color]
```

Emits the subject's topology as Mermaid text, directly from the IR (PD-034: no dependency on
`draw_mermaid()` or `get_graph()` anywhere in this path), optionally overlaid with a run
report's findings per DIAGRAM-STYLE-GUIDE.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--ir` / `--snapshot` | see §2.3 | — | explicit mode selectors |
| `--store` | directory | `./.gebra` | the store `--snapshot` resolves against |
| `--report` | path | — | a native-JSON run report (`--format json` output) whose findings are painted onto the diagram |
| `--format` | `mermaid` | `mermaid` | the only diagram format in Phase-0; PlantUML is demoted out of the phase (PD-034) |
| `--output`, `-o` | path | stdout | write the diagram to a file |
| `--color` / `--no-color` | — | auto-detected | governs the **diagnostics** on stderr only; the diagram itself is plain Mermaid text on every setting |

**No live-target mode in Phase-0.** `display`'s input is a loaded `WorkflowIR` — an IR document
or a stored snapshot. That is PD-034's finding 2 and CLI-06's own prereq set (the IR loaders,
no extraction card); adding an import-reference mode would add extraction scope no card owns
(Appendix B, OI-5). An import-shaped target is therefore a usage error here, not a resolution
(§2.2), which is what makes `display`'s never-invokes claim total (§0.5). A user who wants a
diagram of a live definition writes the IR out first.

**Overlays name their own graph.** `--report` reads a run report the way REPORT-FORMAT-SPEC
§1.6 requires of any consumer — `report_format` first, refusing a MAJOR this build does not
know — and is refused (exit `2`, `stage: "input"`) when the file is unreadable, is not a valid
run report, or carries a `subject.graph_version` differing from the displayed IR's digest:
painting one workflow's findings onto another's topology would be a false statement about both,
and comparing two recorded digests is a provenance check, not a verdict. Every painted finding
carries its claim class, exactly as the terminal renderer does (PD-034, WA-06).

**Exit codes.** §3.2's `display` row.

### 4.5 `gebra history`

```
gebra history [--store DIR] [--since VERSION] [--until VERSION] [--limit N]
              [--reverse] [--format {human,json}] [--output PATH]
              [--color | --no-color]
```

Lists what the store holds. Takes no subject: the store *is* the subject.

| Flag | Value | Default | Meaning |
|---|---|---|---|
| `--store` | directory | `./.gebra` | the store listed (§2.5) |
| `--since` | version label | oldest | inclusive oldest row to show; must be a version the history holds |
| `--until` | version label | newest | inclusive newest row to show; must be a version the history holds |
| `--limit` | non-negative integer | all | at most this many rows, dropping the oldest first — so `--limit 10` is the ten most recent of the selected range; `0` is a legal empty window |
| `--reverse` | — | off | display newest first — a presentation-layer reversal of an unchanged engine order |
| `--format` | `human`, `json` | `human` | see below |
| `--output`, `-o` | path | stdout | write the listing to a file |
| `--color` / `--no-color` | — | auto-detected | as `verify` |

`--since`, `--until` and `--limit` are `gebra.lineage.lineage`'s own window arguments, passed
through unchanged; their refusals (an unknown label, a window whose ends are inverted, a
negative limit) are `LineageError` and exit `2`.

**The output shape is PD-033's ruling**: a table, **oldest first** — the order `Lineage` itself
fixes — with one row per `LineageEntry` and columns for the index, the version label, the
`graph_version` (short form is fine; a digest prefix must read as a prefix), the created-at
timestamp, a current-pointer marker, and a step summary. The step summary is sourced only from
that row's `LineageStep`: which components bumped, in V.S.F.E order, whether content changed,
and a distinct marker for a component that *decreased*. A row whose step is absent or
non-comparable (the oldest row, or a label outside the V.S.F.E grammar) renders an explicit
`n/a`, never a blank cell that could be read as "no change".

**A window states that it is one.** `Lineage` carries `total`, `omitted_before` and
`omitted_after` for the whole history however small the window is, and a paged listing shows
them, so a `--limit 5` view is never mistaken for the entire history.

**`gebra history` never renders a full structural diff inline** (PD-033). The step summary says
which counters moved; a user who wants the content answer for a step runs `gebra diff` between
the two labels. `--format json` is `gebra.lineage.dump_lineage`'s existing byte-stable
projection, stamped with `LINEAGE_DOCUMENT_VERSION` — no second schema is introduced here.
There is no `sarif` value: SARIF is a findings format and a history has no findings.

**Exit codes.** §3.2's `history` row.

---

## 5. Diagnostics conventions

The section brief D-12's OQ-12-03 asks for ("**Output:** diagnostics section of
`CLI-SPEC.md`"), settled by the CLI-D3 ruling.

### 5.1 Framework and degradation

**`rich` is the rendering library** (PD-031), added to the package's core dependencies rather
than an extra, because the default no-flag path is the human surface and cannot be
conditionally absent. gebra builds its own thin renderer on top of it (CLI-03): `rich` supplies
tables, panels, styled text and terminal-capability detection; it supplies no diagnostics
engine, and the mapping from a `PropertyReport` to renderables is gebra's own, taken off the
structured envelope rather than re-derived from prose.

| Situation | Behavior |
|---|---|
| Interactive terminal, full capability | Full styling: severity-colored labels, tables/panels, structured anchors |
| `NO_COLOR` set, `TERM=dumb`, or `--no-color` | Plain text: identical structure and content, severity words spelled out, no color codes emitted |
| Non-tty (piped, redirected, captured by a CI runner) | Auto-detected: plain by default with no flag, `$COLUMNS` or 80 columns wide. Raw ANSI escapes are never written into a log file by default |
| `--color` | Styling forced on regardless of detection |

**Degradation changes styling only** (PD-031, REPORT-FORMAT-SPEC §5.1 rule 7). No finding is
dropped, reordered, truncated or reworded going from styled to plain: the two outputs carry the
same facts, and CLI-07 goldens both.

### 5.2 Streams, and what goes where

- **stdout carries the artifact**: the run report (human, JSON or SARIF), the Mermaid text, the
  history table, the diff rendering, the recorded version label. Nothing else. So
  `gebra verify --format json > report.json` writes exactly the report bytes, and
  `gebra display --ir ir.yaml | mmdc -i -` is a valid pipeline.
- **stderr carries diagnostics about the run**: extraction warnings, tool-error messages, usage
  errors, did-you-mean suggestions, progress. A machine-format consumer parsing stdout never
  has to strip them.
- `--output`/`-o` writes the artifact to a file instead of stdout. A report written to a file
  ends with a single trailing newline; one written to a stream does not add one
  (REPORT-FORMAT-SPEC §1.5).
- **Extraction warnings are rendered on every surface**, always to stderr, in emission order,
  as the structured records they are (INTROSPECTION-SPEC §8's closed taxonomy). They are never
  silently dropped, and they never move an exit code (§3.5). The run report carries no warning
  field, so they have no machine-format home in Phase-0 — stated as open item OI-2 rather than
  patched over by smuggling them into a report the format does not define.

### 5.3 Multi-error reporting in one run

OQ-12-03's first requirement. A run reports **everything it found, in one pass**:

- every finding of every property that produced one — the primary `Failure`, every `CoFailure`,
  every `Advisory` — never a first-error-and-stop, and never a summary that drops records
  (REPORT-FORMAT-SPEC §4.4);
- pass reports and not-implemented markers alongside the failures, so a reader sees what was
  checked and what was not (§5.1 rules 4–5 there);
- independent invocation errors together where they are independent: two mutually exclusive
  selectors and an unknown flag are one diagnostic listing both, not two runs of the tool.

Dependent errors are not invented: once subject resolution fails, no properties ran, so the
output is the tool error and nothing else (§2.6, REPORT-FORMAT-SPEC §2.4).

### 5.4 Did-you-mean suggestions

OQ-12-03's third requirement, and the one PD-031 explicitly left to this section. Suggestions
are computed with the standard library's `difflib` — no dependency — over **closed vocabularies
only**, where a nearest match is a fact rather than a guess:

| Mistyped | Suggested from |
|---|---|
| a verb | the five verbs of §1.1 |
| a `--strict=` slug | `gebra.verify.PROPERTY_SLUGS` |
| a `--format` value | that verb's own value set (§4) |
| a flag name | that verb's flags |
| a `--since`/`--until`/`--snapshot` label | the labels the store's history holds |
| a sidecar or annotation key naming no node | the IR's node ids, when an extraction warning already reports the mismatch |

Rules: at most three candidates; only candidates above a similarity threshold (the exact
threshold is CLI-03's latitude); the suggestion is **display-only** — it never changes an exit
code, never selects a candidate on the user's behalf, and never appears in a machine format.
The last row is the "misspelled node names and state keys" case OQ-12-03 names; the *finding*
there is the extractor's warning, and the suggestion is only a legibility aid attached to it.

### 5.5 Tool-error anatomy

A tool error is an invocation that became a run and then reached no verdict — every row of
§2.6. It reports, in every case: the **stage** it stopped at (§2.6's vocabulary, which is
REPORT-FORMAT-SPEC §2.4's), what was being resolved, the underlying detail as display-only
prose, and — explicitly — **that no verdict was reached**. A *usage* error is the other exit-2
case and has none of this: no stage, no run report, a stderr diagnostic only (§3.4). An exit-2
run is never
presented as a clean run, on any surface: in `--format json` it is the tool-error `RunReport`
with `properties: []`; in `--format sarif` it is either no log at all or a log carrying
`run.properties["gebra/exitCode"]: 2` (REPORT-FORMAT-SPEC Appendix A.7).

### 5.6 Copy rules

REPORT-FORMAT-SPEC §4.6 binds every string the CLI emits, including strings a renderer
assembles at run time and strings in stderr diagnostics. In one line each: the claim class is
always displayed with a finding or verdict; P-02 wording is witness-presence only; the subject
is the workflow **definition**, never the running agent; a not-implemented marker is never
rendered as a pass or counted in a "checks passed" tally; a HEURISTIC advisory never carries the
weight of a DEFENSIBLE finding, promoted or not; prose fields (`remediation`, `CoFailure.note`,
marker and tool-error details) are shown to people and parsed by nothing.

These are lint-enforced, not merely asserted: `tools/honest_claims_lint.py` (TE-15) scans
`src/**/*.py` and `docs/**/*.md`, so renderer templates are in scope, and CLI-07's acceptance
includes "no banned phrases in any captured output".

### 5.7 Source anchors: an honest absence

D-12's diagnostics ambition includes "source anchors pointing at the builder call site where
extraction captured it". **IR 1.0 carries no source spans** — no file, no line, no column, in
IR-SPEC, INTROSPECTION-SPEC or ANNOTATION-API-SPEC — and the extraction envelope records
provenance without a call site (REPORT-FORMAT-SPEC A.5). Phase-0's CLI therefore anchors every
diagnostic **structurally**, on the location the envelope carries (node, edge, cycle, SCC,
state key, path, rendered per REPORT-FORMAT-SPEC §4.5), and **fabricates no file/line anchor**
for any surface, including SARIF, where a wrong anchor would move a baseline matcher's
fingerprints in ways it would read as real churn. Closing the gap needs an extraction-side
capability; it is open item OI-1 here and in REPORT-FORMAT-SPEC, not a defect in either.

---

## 6. Configuration

### 6.1 No configuration file in Phase-0

**The CLI reads no configuration file.** Every option is a flag, and the command line is the
whole policy surface. Three reasons, in the order they bind:

1. **`gebra.toml` is already taken, and by something else.** It is ANNOTATION-API-SPEC §2's
   annotation sidecar: its contents are *inputs to the IR*, they ride inside the `graph_version`
   hash scope, and its discovery walks upward from the working directory. CLI options are
   neither inputs to the IR nor part of any digest. Putting run policy in the same file would
   put two precedence systems with different scopes in one place, and make "the digest moved"
   and "the gate moved" answerable only by reading which table an edit landed in.
2. **A config file adds a precedence ladder the report would have to record.** `gate.strict`
   records "the policy in force" so a reader knows which gate produced a code. With defaults,
   a file, environment variables and flags, honest recording means recording *where* the policy
   came from too — a schema change to a ratified format, for options that are three characters
   apart from being explicit on the command line.
3. **The options that would live in a file are CI-policy options that CI already expresses
   verbatim.** `--strict`, `--format` and `--store` sit in a workflow file, a Makefile or a
   `tox` line as readable text that reviewers see in a diff. PROPERTY-CATALOG-SPEC §0.2 spells
   strict mode as a flag; a CI line that says what it enforces is a feature.

Reopening this is an amendment to this document plus a card — never a file quietly read by an
implementation.

### 6.2 Environment

The CLI honors exactly the terminal conventions `rich` already implements, and defines no
variable of its own:

| Variable | Effect |
|---|---|
| `NO_COLOR` | plain output, as if `--no-color` (§5.1) |
| `TERM=dumb` | plain output |
| `COLUMNS` | output width; 80 columns when absent off a tty |

**There are no `GEBRA_*` environment variables in Phase-0** — same argument as §6.1 item 2: an
invisible input to a gate is an input a reviewer cannot see. `PYTHONPATH` and the working
directory matter for import targets and for sidecar discovery, but they are the interpreter's
and the annotation spec's, not options this CLI defines (§2.4).

### 6.3 Reproducing an invocation

Because the flags are the whole surface, an invocation reproduces by copying the command line —
and a run report carries what it needs to be re-read later: `tool.version` (which build),
`subject.*` (what was verified, and how it was obtained), `gate.strict` (which policy). With
`tool.version` fixed and the same IR, the run report is byte-identical across runs, processes
and platforms (REPORT-FORMAT-SPEC §1.4 rule 5), which is what makes CLI-07's goldens possible
at all.

---

## 7. Conformance obligations

**CLI-03 (rendering engine)** — the human surface for `verify` per REPORT-FORMAT-SPEC §4/§5 and
§5.1 here; degradation per §5.1; `--format json`/`sarif` per REPORT-FORMAT-SPEC §1.5 and
Appendix A; the stream discipline of §5.2; the did-you-mean machinery of §5.4. Add `rich` to
the package's core dependencies (PD-031). **Landed 2026-08-08** as `gebra.report`:
`render(report, format)` and `write(report, stream, format)` for the three surfaces,
`TerminalOptions` carrying §1.3's `--color`/`--no-color` pair, and
`gebra.report.suggestions.did_you_mean` for §5.4 over a caller-supplied closed vocabulary.
`rich>=13.8` is a declared core dependency. The verbs that will call all of this are CLI-04's
and CLI-05's; nothing here parses a flag or resolves a subject.

**CLI-04 (`gebra verify`)** — §2's resolution including the detection-rule ordering and the
per-verb mode restriction, §3.2's `verify` row including tool-error stages, §3.3's strict flag
and its alias (both spellings tested, both shown in `--help`), §4.1's flag table. Land the
never-invokes tripwire for `verify`'s live-target resolution in the same change, in the shape
§0.5 item 3 fixes — sentinel armed at four points, `BaseException`-derived, asserted on the
recorded call list rather than on the exit code.

**CLI-05 (`snapshot`, `diff`, `history`)** — §4.2, §4.3 and §4.5, including the §0.2 recording
refusal, single subject resolution per invocation, the S/F/E bump class in diff output, the
deferred-P-12 marker rendered as *not checked*, and PD-033's oldest-first table with per-row
step summaries and explicit `n/a`. **Two of the three live-target paths are this card's**
(`snapshot`, and `diff` on either or both sides), so it lands their tripwires too, in the same
shape (§0.5 item 3) — including the mixed case where one side is a stored label and the other
an import reference.

**CLI-06 (`display` + DIAGRAM-STYLE-GUIDE)** — §4.4, including the IR-only input surface, the
overlay's `report_format` and digest checks, and claim classes on painted findings. `display`
reaches no live object by construction (an import-shaped target is a usage error, §2.2); a
change that ever gave it one makes it a live-target path and pulls §0.5 item 3's obligation
with it.

**CLI-07 (integration suite)** — the exit codes of §3.2 on constructed cases for all five
verbs (including at least one `2` per stage the verb can reach), the format flags of §4, the
`--strict` forms of §3.3, and both styled and plain renderings of one subject (§5.1). Goldens
normalize `tool.version` and nothing else.

**TE-07 (pytest plugin)** — keeps its own `--gebra-` prefixed flags; §3.3's alias exists so the
strict spelling is shared. Plugin and CLI output must tell the same story in the same
vocabulary (brief D-12), which means the same claim classes, the same severity words and the
same witness-presence wording — not the same layout.

**DOC-15 (CLI reference)** — documents the verbs that have merged, and only those, with
examples executed in CI (WA-12). This document is a contract for implementers; it is not that
reference and must not be published as one.

**CLI-08 (D-12 promotion)** — stamps this document final alongside REPORT-FORMAT-SPEC, and
closes or re-routes every open item below.

---

## Appendix A — the consolidated flag table

Every flag, every verb. `•` = accepted; blank = not accepted (giving it is a usage error, exit
`2`, §3.4).

| Flag | `verify` | `snapshot` | `diff` | `display` | `history` |
|---|---|---|---|---|---|
| `TARGET` (positional) | • | • | two, required | • | |
| `--ir PATH` | • | • | | • | |
| `--import REF` | • | • | | | |
| `--snapshot VERSION` | • | | | • | |
| `--store DIR` | • | • | • | • | • |
| `--sidecar PATH` | • | • | • | | |
| `--call` | • | • | • | | |
| `--strict[=SLUG,…]` (alias `--gebra-strict`) | • | | | | |
| `--format` | `human`, `json`, `sarif` | | | `mermaid` | `human`, `json` |
| `--report PATH` | | | | • | |
| `--exit-code` | | | • | | |
| `--quiet` | | • | | | |
| `--since` / `--until` / `--limit` | | | | | • |
| `--reverse` | | | | | • |
| `--output`, `-o` | • | | • | • | • |
| `--color` / `--no-color` | • | • | • | • | • |
| `--help`, `-h` | • | • | • | • | • |

Application-level: `gebra --version`, `gebra --help`.

Two absences are deliberate and stated so an implementer does not read them as oversights:
`snapshot` and `diff` have no `--format` (Appendix B, OI-3), and no verb has `--select`,
`--skip` or a config-file flag (§1.4, §6.1).

---

## Appendix B — open items

| Id | Item | Owner / route |
|---|---|---|
| OI-1 | No source anchors exist in IR 1.0, so diagnostics anchor structurally and SARIF results carry no `physicalLocation` (§5.7). Pairs with REPORT-FORMAT-SPEC OI-1. | Extraction-side capability (EX track), or a D-12 promotion decision (CLI-08). Not a Phase-0 blocker. |
| OI-2 | Extraction warnings have no machine-format home: they render to stderr, and the run report defines no warning field (§5.2). | An amendment to REPORT-FORMAT-SPEC (a new optional member, MINOR per its §1.6) on evidence of a consumer that needs them structured. |
| OI-3 | `snapshot` and `diff` have no `--format json`: neither engine ships a stable JSON projection, and inventing one here would be a new schema no card owns. `--quiet` covers the scripting case for `snapshot`. | A future card owning the projection, plus an amendment here. |
| OI-4 | SD-07's audit export (`.gebra/reports/<version>.report.json`, REPORT-FORMAT-SPEC §6) is exposed by no verb: no Phase-0 card wires it to the CLI. | SD-07 and CLI-08. |
| OI-5 | `display` has no live-target (import-reference) input mode (§4.4), per PD-034 finding 2 and CLI-06's prereq set. | CLI-08, or a Phase-1 card that owns the added extraction scope. |
| OI-6 | No configuration file and no `GEBRA_*` environment variables (§6). | An amendment here plus a card, on evidence of a need the command line cannot meet. |
| OI-7 | `typer` ships `--install-completion`/`--show-completion` by default. Shell completion is not part of this contract; CLI-04 either disables the pair or documents it as outside the specified surface. | CLI-04, then CLI-08. |
| OI-8 | This document is ratified as CLI-02's artifact and stamped final at the D-12 promotion. | CLI-08. |
| OI-9 | ~~PROPERTY-CATALOG-SPEC §0.3 defines P-02/P-04/P-06 results **only over P-01-clean topology** ("best-effort diagnostics, not contract-bearing verdicts" otherwise), but no rendering obligation says so.~~ **Closed at CLI-03, 2026-08-08.** The amendment this item asked for landed at VAL-11 as `report_format` `1.1`: `RunReport.best_effort` carries the qualification into the artifact (REPORT-FORMAT-SPEC §1.3), §4.2 gives it two rendering rows, §4.6 rule 9 forbids showing a best-effort report as a plain verdict, and §5.1 rule 7 requires the human surface to state it *where those reports are*, not only in the summary. | Closed. CLI-03's `gebra.report.human` implements §5.1 rule 7 and `tests/report/test_human.py::test_best_effort_is_stated_where_its_reports_are` holds it there; a SARIF log carries no such qualification by design (§4.2: "SARIF has no place to qualify a result's weight"). |
| OI-10 | `--call` (§2.4) is the CLI's only path that executes user code, and it is opt-in. Whether the common `build_graph()` layout deserves a smoother route than "write `graph = build_graph()` in your module, or pass `--call`" is a UX question Phase-0 answers conservatively. | CLI-04's implementation experience, then CLI-08. |
