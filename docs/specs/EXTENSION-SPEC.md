# EXTENSION-SPEC — the thin VS Code lens over the `gebra` CLI (outline)

> **Nothing in this document is built, and nothing in it is scheduled for Phase-0.** There is
> no VS Code extension in this repository, no extension source tree, no packaging target and
> no Phase-0 card that produces one. Every capability described below is **Phase-1**, and every
> sentence about the extension is written in the future or the conditional for that reason
> (WA-12 — docs tell no futures). What *does* exist today is the CLI this outline is a lens
> over: `gebra verify | snapshot | diff | display | history` (CLI-SPEC), its report format
> (REPORT-FORMAT-SPEC) and its Mermaid emitter (DIAGRAM-STYLE-GUIDE).
>
> **What this document is.** The outline-level artifact brief D-12's table names — *"`EXTENSION-SPEC.md`
> (outline-level): thin VS Code extension wrapping the CLI: webview/Custom-Editor lens for
> graph, verification overlays, diffs — read-only canvas synced to code (decision D-028;
> Workflow-Visualization-Design)"* — written at the D-12 promotion (card CLI-08) because the
> promotion is when the brief's artifact set has to be complete, not because an extension is
> imminent.
>
> **It is not user documentation, and it is not published.** It sits in the repository-internal
> `docs/specs/` tree, which `mkdocs.yml` excludes by name from the user documentation site,
> alongside CLI-SPEC and REPORT-FORMAT-SPEC. A user who reads the site will not find a page
> describing an editor extension, because there is none to describe.
>
> **Status:** **OUTLINE — Phase-1.** Priority **P2**, trailing the CLI (SOW §1's component
> table: *"Thin VS Code extension (read-only lens over the CLI) … P2 — follows the CLI"*;
> master plan §1: *"The VS Code extension is P2 — outline spec only (CLI-08)"*). This document
> is deliberately not a full contract: see §5 for what a Phase-1 build must settle first, and
> §6 for the standard this outline holds itself to.

---

## Table of contents

- [0. Status and scope](#0-status-and-scope)
- [1. Authority](#1-authority)
- [2. The boundary: what the extension may and may not be](#2-the-boundary-what-the-extension-may-and-may-not-be)
- [3. The CLI surface a lens would wrap](#3-the-cli-surface-a-lens-would-wrap)
- [4. The three views, at outline depth](#4-the-three-views-at-outline-depth)
- [5. Open questions a Phase-1 contract must settle](#5-open-questions-a-phase-1-contract-must-settle)
- [6. What this outline does not do](#6-what-this-outline-does-not-do)

---

## 0. Status and scope

**In scope for this document:** recording the rulings that already bind an eventual extension
(§1, §2), naming the CLI surfaces it would read (§3), sketching the three views decision D-028
names (§4), and enumerating what a Phase-1 contract must decide before anyone writes code (§5).

**Out of scope for this document:** the extension's architecture, its UI, its packaging and
publishing, its language-server or protocol design, its test strategy, its version support
matrix, and its schedule. Those are the Phase-1 contract's, and inventing them here would be
designing a product nobody has committed to building — the opposite of what "outline level"
asks for.

**Out of scope for Phase-0 entirely:** the extension itself. SOW §1 prices it P2 behind the
CLI; master plan §1 lists it under out-of-scope as "outline spec only (CLI-08)". No Phase-0
acceptance criterion (SOW §2) mentions it, and none should.

## 1. Authority

Nothing in this outline is a new decision. Every constraint below is inherited:

| Question | Authority |
|---|---|
| That there is an extension at all, and that it is thin | Decision **D-028 clause (ii)** (vault; via SOW §1 and brief D-12's "Extension deliverable" section) |
| Thin-client-over-CLI architecture — "the editor extension is a shell; every capability lives in the CLI it wraps" | **DEC-26** reword, 2026-08-09 (quoted in brief D-12) |
| Read-only lens, no authoring canvas, no IDE fork | Decision **D-028**; brief D-12's "What this brief is *not*" |
| Licence | **Apache-2.0**, like everything else in this SOW (D-028 clause (i); SOW §5) |
| Priority and phase | **P2, Phase-1** (SOW §1 component table; master plan §1) |
| The presentation-only rule, extended to the extension | Brief D-12: *"The extension adds no verification semantics of its own (the presentation-only rule above extends to it)"*; CLI-SPEC §0.1 |
| Honest-claims copy discipline | **WA-06**; PROPERTY-CATALOG-SPEC §0.1's claim classes; the banned-phrase list at `tools/honest-claims-phrases.txt` |
| Never-invokes | **WA-07**; INTROSPECTION-SPEC §1 — reached only through the CLI, which owns the one opt-in (`--call`, CLI-SPEC §2.4) |
| The command surface it wraps | **CLI-SPEC** (final at the D-12 promotion) |
| The artifact it renders verdicts from | **REPORT-FORMAT-SPEC** (final; `report_format` `1.2`) |
| How a graph is drawn | **DIAGRAM-STYLE-GUIDE** (final) |

Where this outline and any of those disagree, they win and the disagreement is a defect to
file (WA-03) — this document redefines nothing.

## 2. The boundary: what the extension may and may not be

The five rules that make it *thin*, stated as constraints a Phase-1 design must satisfy rather
than as features:

1. **Every capability lives in the CLI.** DEC-26's own words. A behavior the extension can do
   that `gebra` cannot is a capability in the wrong place: the fix is a CLI card, after which
   the extension calls it. This is what keeps a terminal user, a CI job and an editor user
   looking at the same answers.
2. **It reaches gebra only through the CLI's public surface.** The extension is a consumer of
   the documented verbs, their exit codes and their machine formats — not of `gebra`'s Python
   internals. A lens that imported `gebra.verify` would fork the contract and would silently
   couple an editor release to a library version.
3. **It adds no verification semantics.** No verdict, no severity, no claim class, no exit code
   and no structural fact originates in the extension; each is read off a run report or a diff.
   CLI-SPEC §0.1's four numbered rules apply verbatim, including the fourth: every displayed
   finding carries its claim class, P-02 language is witness-presence wording only, and a
   not-implemented marker is never displayed as a pass.
4. **The canvas is read-only.** D-028 is explicit — no freehand editing, no authoring, no
   graph-to-code generation. The graph is a *view of code the user wrote*; edits happen in the
   editor, and the view follows them.
5. **It executes no workflow.** Never-invokes (WA-07) binds it exactly as it binds everything
   else. The extension runs `gebra`; `gebra` extracts without invoking; `--call` remains the
   user's own explicit opt-in and the extension may not make it implicit — the same argument
   that closed CLI-SPEC's OI-10 at the promotion. Read "extracts without invoking" in
   CLI-SPEC §0.5's own terms rather than as a stronger claim: importing the user's module is
   the user's own act and runs its top-level code (item 1), and extraction makes the one
   substrate call INTROSPECTION-SPEC §4.2/§4.3 licenses (item 2). A Phase-1 contract author
   reading only this page should take item 2's warning with it — claiming that extraction
   makes *no* substrate call would misstate the frozen rules both documents defer to.

## 3. The CLI surface a lens would wrap

These exist today and are contract-fixed, which is what makes a thin client possible at all.
An extension would read them and nothing else:

| Need | CLI surface | Contract |
|---|---|---|
| Draw the graph | `gebra display --format mermaid` | DIAGRAM-STYLE-GUIDE; CLI-SPEC §4.4 |
| Overlay verification results on the graph | `gebra display --report <run-report.json>` | DIAGRAM-STYLE-GUIDE §4; CLI-SPEC §4.4 |
| List findings (severity, claim class, condition ID, location) and pass witnesses | `gebra verify --format json` | REPORT-FORMAT-SPEC §1 (`report_format` `1.2`) |
| Gate a workspace the way CI would | the exit codes `0` / `1` / `2` | PROPERTY-CATALOG-SPEC §0.2 via CLI-SPEC §3 |
| Show what moved between two versions | `gebra diff` | CLI-SPEC §4.3; `gebra.diff.WorkflowDiff` |
| Show the version history of a store | `gebra history --format json` | CLI-SPEC §4.5; `gebra.lineage.dump_lineage` |

Two consequences worth stating, because they are what "thin" buys:

- **`report_format` is the integration contract**, not a private protocol. An extension reads
  `report_format` first (REPORT-FORMAT-SPEC §1.6's rule for every consumer), refuses a MAJOR it
  does not know, and is otherwise insulated from how the library changed underneath.
- **Two of the six rows are `--format json`**, and `snapshot` and `diff` currently have no JSON
  projection (CLI-SPEC Appendix B, OI-3, re-routed to Phase-1 at the promotion). A diff view
  that wants structured input is therefore *gated on that item*, not on this outline — and that
  is precisely the kind of dependency an outline exists to surface early.

## 4. The three views, at outline depth

Decision D-028 and brief D-12 name three things the lens renders. Each is sketched to the depth
that constrains a Phase-1 design and no further:

**4.1 The graph view.** A webview or Custom Editor showing the workflow's topology as drawn by
DIAGRAM-STYLE-GUIDE — the same picture `gebra display` writes to a terminal, so an editor user
and a terminal user are never looking at two different graphs. "Synced to the code" means the
view re-renders when the file the graph was extracted from changes; it does not mean the view
can change that file (§2 rule 4).

**4.2 The verification overlay.** The findings of a run report painted onto the graph view, with
the guide's §4 encoding: severity by node fill and link stroke, an F-indexed legend carrying
every finding once with its claim class, condition ID and anchor phrase, and unresolved anchors
stated as not drawn rather than dropped. The guide already fixes all of this because it was
written so that *"any later lens over the same diagram (the P2 VS Code extension, CLI-08's
EXTENSION-SPEC outline) draw[s] one picture instead of several"* — an extension that invented
its own overlay encoding would be the failure that sentence anticipates.

**4.3 The diff view.** Two versions of a workflow shown side by side with what moved and the
S/F/E bump class, from `gebra diff`. Two constraints it inherits: the deferred-P-12 marker is
rendered honestly — P-12 `evolution-safety` is Phase-1 scope, so no view may label a change safe
or breaking (CLI-SPEC §4.3; SOW §8) — and the structured input it wants is OI-3's, per §3.

## 5. Open questions a Phase-1 contract must settle

Named, not answered. Answering them here would be designing the extension.

| Id | Question |
|---|---|
| EX-OQ-1 | **Invocation model.** Does the extension shell out to a `gebra` on the user's PATH, to one in the workspace's virtual environment, or to a bundled interpreter? Each answer has a different failure mode when the two disagree about a version, and the answer decides what "thin" costs a user at install time. |
| EX-OQ-2 | **Sync trigger.** What re-runs extraction — a save, a debounce, an explicit command, a file watcher? Extraction imports the user's module (CLI-SPEC §0.5 item 1), so an aggressive trigger runs top-level code more often than a user expects. |
| EX-OQ-3 | **Where a run report comes from.** Does the extension run `gebra verify` itself, read an artifact CI produced, or read the store's audit export (`.gebra/reports/<version>.report.json`)? The third is free of any run at all, and REPORT-FORMAT-SPEC §6 is already its contract. |
| EX-OQ-4 | **Rendering the Mermaid.** A bundled Mermaid renderer in the webview, or VS Code's own Markdown preview pipeline? DIAGRAM-STYLE-GUIDE §9 is careful that "parse-checked" is not "renders in someone else's viewer"; whichever is chosen is the first consumer that actually renders. |
| EX-OQ-5 | **Diff input.** Whether the diff view waits for the JSON projection of OI-3 or parses the human rendering. Only the first is a contract; the second would couple an editor to terminal layout. |
| EX-OQ-6 | **Error surface.** How exit `2` (a tool error, with its `error.stage`) is shown, distinctly from exit `1` (a gate failure with findings). Collapsing them would show a broken invocation as a failing workflow. |
| EX-OQ-7 | **Packaging, publishing and the marketplace listing**, including how the listing's copy is held to WA-06 — a marketplace description is repo-authored prose that no lint in this repository currently scans. |
| EX-OQ-8 | **Substrate and editor version support**, and how it relates to VERSION-COMPAT's matrix — the extension adds a second dimension (VS Code versions) the drift suite knows nothing about. |

## 6. What this outline does not do

- **It does not build, design or schedule an extension.** No architecture is chosen, no API is
  fixed, no milestone is implied. A Phase-1 team is free to answer §5 any way it likes, subject
  only to §1's inherited authorities and §2's boundary.
- **It does not commit the project to shipping one.** D-028 clause (ii) says an extension is the
  intended second face; nothing here converts that into a delivery promise, and P2 means exactly
  what SOW §1 says it means — it follows the CLI.
- **It does not describe any capability as available.** Cross-check for the reader who arrived
  here from a search: there is no `gebra` extension to install, and the only shipped user
  surfaces are the CLI, the Python API and the pytest plugin.
- **It makes no verification claim.** Every rule in §2 is a presentation constraint. What a
  finding means, and what a passing run establishes, remain the property catalog's — an
  extension displays claim classes, it does not strengthen them.
