# D-12 promotion record — outline brief to full in-repo contract (card CLI-08)

> **What this is.** The record that brief D-12 ("CLI and Reporting") has been promoted from
> outline status to a full contract, and the statement of what that promotion consists of in
> this repository. The brief's own status note fixes the trigger:
>
> *"This is an outline brief. It stays outline until the D-08 IR models and the D-09
> `validate(ir)` result types freeze; it is then promoted to a full team contract."*
>
> Both freezes are recorded (§1). Like [RENDER-SIGNOFF.md](RENDER-SIGNOFF.md), this is
> evidence read against a wording, not an unevidenced declaration: §2 says what promotion is
> taken to mean *before* §3–§5 claim it, and §7 says what it does not claim. The owner's merge
> of the CLI-08 change is the recording act (WA-08 — the human owner is always the merger).

**Status: PROMOTED**, 2026-08-31, card CLI-08.

## 1. The trigger: F3, both halves recorded

Master plan §3 names the event: *"F3 — IR-models + validator-result API freezes (IR-06,
VAL-12, at G5) — jointly the D-12 promotion trigger (CLI-08)."* Both halves have landed and
both records live beside this one:

| Half | Brief | Record | Card | Recorded |
|---|---|---|---|---|
| IR models (`gebra.ir`) | D-08 | [IR-MODELS-FREEZE.md](IR-MODELS-FREEZE.md) | IR-06 | 2026-08-13 |
| Validator-result API (`gebra.verify`) | D-09 | [VALIDATOR-API-FREEZE.md](VALIDATOR-API-FREEZE.md) | VAL-12 | 2026-08-08 |

The two dates are each record's own **Status: FROZEN** line, and they differ: the validator
half landed first, so **F3 was complete on 2026-08-13**, the later of the two. Master plan
§4's G5 cell lists both under the G5 recording date, which is the gate's date rather than
each freeze's — a record whose whole method is evidence read against a wording should not
inherit that rounding.

Each of those records anticipated this one: both name CLI-08 and both state that stamping
`report_format` final is *this* card's event and not theirs (VALIDATOR-API-FREEZE.md §1,
IR-MODELS-FREEZE.md's closing section). The third named prereq, **CLI-02** (CLI-SPEC.md,
2026-08-05), was already `done`, so the promotion has been eligible since 2026-08-13 and this
record is its execution, not its authorization.

**Final does not mean frozen forever, and the stamp deliberately does not close the growth
channels the frozen catalog requires.** PROPERTY-CATALOG-SPEC §0.3 makes witness membership
per-property, and §0.4 grows the condition registry by addendum; REPORT-FORMAT-SPEC OI-5
re-routes exactly that growth to Phase-1 as a MINOR bump plus a §4 row (§5), and §1.6's
post-final route keeps it open. What the stamp fixes is Phase-0 (§6).

The extractor-API freeze ([EXTRACTOR-API-FREEZE.md](EXTRACTOR-API-FREEZE.md), EX-12) is not
part of F3 and is named here only so a reader who finds three freeze records knows which two
the trigger counts.

## 2. What promotion is taken to mean here

Stated before it is claimed, because "promoted to a full team contract" could be read as an
act on the brief itself, and that reading is not available:

1. **The brief is not edited, and this record does not edit it.** `docs/briefs/D-12-CLI-and-Reporting.md`
   in the development-process repository is a vendored byte-copy of the vault original
   (WA-11); editing it is prohibited (WA-03), and its `> [!note] Status: OUTLINE` block
   therefore still reads OUTLINE and will keep reading OUTLINE. Promotion is recorded *about*
   the brief, in the repository the brief commissioned.
2. **The plan already fixed what the promotion's evidence is.** PHASE-0-DOD-CHECKLIST's G7-4
   row names it: *"D-12 promoted | CLI-08 promotion record citing the F3 freeze (IR-06 +
   VAL-12)"*, and master plan §4's G7 evidence checklist carries the same phrase. That is
   the reading this record executes; nothing here invents a promotion procedure.
3. **"Full contract" means the artifacts, not a second brief.** Where the brief's outline-level
   Definition of Done says *"the full brief drafted (roster, week-level milestones,
   in/out-of-scope)"*, this build has those three things elsewhere and does not duplicate them:
   the roster is the master plan's §2 role model, the week-level milestones are
   `docs/plan/advisory-sequencing.md` (advisory, never gating, per master plan §4), and the
   in/out-of-scope line is SOW §1/§8 as narrowed by master plan §1. What promotion adds is
   what only this track can add: the artifact set of the brief's own table, complete, with its
   four open questions ruled and its two contract specifications stamped final (§3–§6).
4. **Promotion changes no behavior.** Not one line of `src/` changes on this card. The verbs,
   the report format, the diagram emitter and the exit codes are exactly what CLI-03…CLI-07
   merged; what changes is that the documents describing them stop being amendable by Phase-0
   cards (§6).

## 3. The artifact table, row by row

Brief D-12's "Concrete output artifacts" table, with the state of each row at promotion.
Every path below is in this repository.

| Artifact (brief D-12) | State at promotion | Where | Card |
|---|---|---|---|
| `CLI-SPEC.md` — five subcommands: flags, exit codes, diagnostics style | **final** (stamped by this record) | `docs/specs/CLI-SPEC.md` | CLI-02 |
| `REPORT-FORMAT-SPEC.md` — human + CI report schema (OQ-12-01) | **final** (stamped by this record); `report_format` fixed at `1.1` | `docs/specs/REPORT-FORMAT-SPEC.md` | CLI-01 |
| `DIAGRAM-STYLE-GUIDE.md` — Mermaid rendering of the IR; overlay design (OQ-12-02) | **final** (stamped by this record; its own status line named this card) | `docs/specs/DIAGRAM-STYLE-GUIDE.md` | CLI-06 |
| `EXTENSION-SPEC.md` (outline-level) — thin VS Code extension wrapping the CLI | **outline, Phase-1** — written by this card; no extension is built, designed or scheduled in Phase-0 | `docs/specs/EXTENSION-SPEC.md` | CLI-08 |
| `gebra` typer CLI module in the `gebra` package | **shipped**: all five verbs (`verify`, `snapshot`, `diff`, `display`, `history`) | `src/gebra/cli/`, `src/gebra/display/`, `src/gebra/report/` | CLI-03…CLI-06 |
| CLI integration test suite | **shipped**: flow, process-level matrix, corpus sweep | `tests/cli/` | CLI-07 |

The three stamped documents are **repo-authored** contract specifications, not vendored specs:
they are this track's own output, and stamping them final is a decision this track is
competent to take. Nothing in the vendored, frozen spec package
(PROPERTY-CATALOG-SPEC, IR-SPEC, INTROSPECTION-SPEC, TERMINATION-WITNESS-SPEC, …) is touched,
re-read or re-interpreted by this promotion.

`EXTENSION-SPEC.md` is the one row that is deliberately *not* full-contract depth. The brief
calls for it "at outline level", SOW §1 prices the extension **P2 — follows the CLI**, and
master plan §1 puts it out of Phase-0 scope in as many words: *"The VS Code extension is P2 —
outline spec only (CLI-08)."* Its own §0 says the same thing in the first paragraph a reader
meets.

## 4. The four open questions, all ruled

Brief D-12 opens with four questions and names the artifact each must produce. All four are
ruled, each by a ratified decision record, each landed in the artifact the brief named:

| Question | Ruling | Recorded in | Landed in |
|---|---|---|---|
| **OQ-12-01** — CI report format: JSON, SARIF, or both behind `--format` | **Both**, behind one `--format`; native JSON is the source of truth and every other machine format derives from it; human terminal stays the no-flag default | PD-015 (CLI-D1, ratified 2026-07-31) | REPORT-FORMAT-SPEC §0.1, Appendix A; CLI-SPEC §4.1 |
| **OQ-12-02** — Mermaid: post-process `draw_mermaid()` or emit from the IR | **Emit from the IR.** A gebra-owned emitter over `WorkflowIR`; no dependency on `get_graph()` or `draw_mermaid()` on the `display` path; PlantUML demoted out of Phase-0 | PD-034 (CLI-D2, ratified 2026-08-04) | DIAGRAM-STYLE-GUIDE (all sections); `src/gebra/display/` |
| **OQ-12-03** — diagnostics framework for Python | **`rich`**, with plain-text degradation that changes styling only, multi-error reporting in one run, labelled levels and did-you-mean suggestions; source anchors are structural because IR 1.0 carries no spans (CLI-SPEC §5.7) | PD-031 (CLI-D3, ratified 2026-08-04) | CLI-SPEC §5; REPORT-FORMAT-SPEC §5 |
| **OQ-12-04** — `gebra trace` output shape, and the `trace` naming collision | **The verb is `history`, not `trace`**, renamed before it shipped; output is a table with per-step summaries and window statements, no inline diffs | PD-033 (CLI-D4, ratified 2026-08-04) | CLI-SPEC §1.1, §4.5; `src/gebra/cli/history.py` |

The brief's own words on OQ-12-04 were *"the decision lands in `CLI-SPEC.md` at promotion,
before the collision can ship"*. It landed earlier than that and the collision never shipped:
nothing in the package spells a verb `trace`, and `gebra trace` gets the unknown-verb
diagnostic of CLI-SPEC §5.4.

## 5. Open-item dispositions

CLI-SPEC §7's own sentence for this card is *"stamps this document final alongside
REPORT-FORMAT-SPEC, and closes or re-routes every open item below."* Every item in both
Appendix Bs is dispositioned here, and each disposition is written into the item's own row in
the same change, so the specs and this record cannot drift apart.

**Re-routed** means the item is real, is not Phase-0's, and now names where it goes.
**Closed** means it needs nothing further: either the question was answered, or the answer is
"deliberately not done", stated with its reason.

### CLI-SPEC Appendix B

| Item | Disposition |
|---|---|
| OI-1 — no source anchors, so no SARIF `physicalLocation` | **Re-routed to Phase-1 (IR/EX tracks).** Not closable here: IR 1.0 carries no source spans, IR-SPEC is frozen, and adding them is an `ir_version` question, not a presentation decision. §5.7 already declares the absence rather than faking an anchor. Pairs with REPORT-FORMAT-SPEC OI-1, which is the same gap seen from the projection side. |
| OI-2 — extraction warnings have no machine-format home | **Re-routed unchanged**, now under the post-final route of §6: a `report_format` MINOR amendment (REPORT-FORMAT-SPEC §1.6, new-optional-member row) owned by a Phase-1 card, on evidence of a consumer that needs them structured. No such consumer has appeared. |
| OI-3 — `snapshot` and `diff` have no `--format json` | **Re-routed to Phase-1.** Unchanged in substance: neither engine ships a stable JSON projection, and inventing one at the presentation layer would be a new schema no card owns (CLI-SPEC §0.1 rule 3). A Phase-1 card owning the projection carries the amendment with it. |
| OI-4 — SD-07's audit export is exposed by no verb | **Closed as a decision.** SD-07 landed (`gebra.audit`, 2026-08-12) and writes `.gebra/reports/<version>.report.json` through the store; **no verb produces, discovers or is wired to it**, and none is added. Stated precisely, because "no verb touches it" would be false and the true version is the stronger one: the file is native JSON at `report_format` `1.1` — the same document `gebra verify --format json` emits — so `gebra display --snapshot <V> --report .gebra/reports/<V>.report.json` reads it today like any other run report, digest check and all. That *is* the disposition's point: the export needs no gebra-specific tooling and no verb of its own, while a sixth verb would widen the five-verb surface brief D-12 fixes. Exposing it later is a Phase-1 card plus an amendment here, not a default drifting in. |
| OI-5 — `display` has no live-target input mode | **Closed as a decision for Phase-0; the capability is re-routed to Phase-1.** Not added, and the reason is structural rather than budgetary: giving `display` an import reference makes it a live-target path and pulls CLI-SPEC §0.5 item 3's tripwire obligation with it (§7 says exactly this). A Phase-1 card that wants it owns the added extraction scope *and* the tripwire. The refusal is specified, tested and stable in the meantime. |
| OI-6 — no configuration file, no `GEBRA_*` variables | **Re-routed unchanged.** §6.1 argues the Phase-0 answer (a config file that could set `gate.strict` moves a gate outcome out of the invocation and into a file a reviewer may not read); reopening it is an amendment here plus a card, on evidence of a need the command line cannot meet. |
| OI-7 — shell completion | **Closed at CLI-04** (2026-08-21, disabled). Reaffirmed, not reopened: `add_completion=False`, held by `tests/cli/test_app.py`. |
| OI-8 — this document is stamped final at the D-12 promotion | **Closed by this record.** |
| OI-9 — best-effort rendering obligation | **Closed at CLI-03** (2026-08-08, via `report_format` `1.1`'s `best_effort`). Reaffirmed. |
| OI-10 — whether `--call` deserves a smoother route for the `build_graph()` layout | **Closed: weighed at promotion and declined.** The evidence CLI-04 left for this card to weigh is now three cards deep — the refusal names the found type and both remedies in one sentence, the tripwire suites pin that no probe softens it, and the integration matrix exercises it at the process boundary — and no smoother route survives the boundary that matters: any route that calls a zero-argument attribute *because it looks like a factory* makes executing user code implicit, which is the one thing `--call`'s opt-in exists to prevent (CLI-SPEC §0.5). Phase-0 answers conservatively and Phase-1 inherits the same argument, not an open question. |

### REPORT-FORMAT-SPEC Appendix B

| Item | Disposition |
|---|---|
| OI-1 — no source anchors, so SARIF results carry no `physicalLocation` | **Re-routed to Phase-1 (IR/EX tracks)**, on the same ground as CLI-SPEC OI-1: it needs an extraction-side capability behind an `ir_version` change, which no presentation decision can supply. A.5 declares the gap; the log stays spec-valid without it. |
| OI-2 — the `sarif-full` profile is deferred | **Re-routed unchanged.** A.8's argument stands (no consumer has asked; a second profile doubles the exporter's surface), and reopening it is a MINOR amendment under §1.6 owned by a Phase-1 card. |
| OI-3 — fidelity-matrix entries FM-004/FM-007 | **Closed at TE-04** (2026-08-06). Reaffirmed. |
| OI-4 — `report_format` `1.1` is stamped final at the D-12 promotion | **Closed by this record.** `report_format` is **`1.1`**, final; §6 states what may still change it and by what route. |
| OI-5 — the witness and location unions grow as property sections merge | **Re-routed to Phase-1**, unchanged: each new member is a MINOR bump and a new §4 row, carried by whichever card merges the section. Phase-0 merges no further sections, so nothing is owed here now. |
| OI-6 — the `--format` default | **Closed by CLI-SPEC §4.1** (CLI-02, 2026-08-05). Reaffirmed. |
| OI-7 — §1.6's bump table has no row for a value-rule change that leaves the model alone | **Closed by this record: the row is added**, in this same change, exactly as the item routes it ("an added §1.6 row at CLI-08"). The rule the row states is in §1.6 and summarized in §6 below. |
| OI-8 — `StateKeyLocation`'s FQN spelling | **Closed at CLI-03/DEC-25** (PD-040 Option A ratified 2026-08-09). Reaffirmed on the ruling, which is what this item asked CLI-08 to do; the vault decision is the authority and this record adds nothing to it. |

DIAGRAM-STYLE-GUIDE carries no open-item appendix — its deferrals (PlantUML §8, large-graph
folding §6) are stated as Phase-1 possibilities inside the sections that raise them, and this
promotion moves neither.

## 6. What "final" means, and what it does not

A stamp that meant "this can never change" would be false, and a stamp that meant nothing
would not be worth making. What it means, precisely:

1. **No Phase-0 card amends these three documents' contracts any further.** Before the stamp,
   an amendment was an ordinary edit by whichever card found the need — that is how
   `report_format` reached `1.1` (VAL-11) and how CLI-SPEC's `subject.source` note was
   corrected (CLI-02). After it, a contract change needs its own card and its own record.
2. **`report_format` is `1.1` and stays `1.1` for Phase-0.** Every producer and consumer in
   this repository is built against that literal; the audit export, the `--format json`
   surface and the plugin all read it first (§1.6's own rule).
3. **The route for a later change is the documents' own, not a quieter one.** For
   REPORT-FORMAT-SPEC that is §1.6's bump table — MAJOR, MINOR or none, decided by the table
   and recorded in the amendment log. For CLI-SPEC and DIAGRAM-STYLE-GUIDE, which carry no
   version line, it is a card plus a landing note in §7 (respectively §9) recording what moved
   and why.
4. **Records are not amendments.** Adding a landing note, closing an open item on a ruling
   already made, or fixing a typo changes no contract and needs no bump — the specs' own
   "editorial change, clarified prose" row. This record's own edits to all three documents are
   of exactly that kind, plus the §1.6 row OI-7 commissioned, which classifies future changes
   without making one. **Tracking a re-vendored upstream authority is on the same side of the
   line**, and it is worth saying so before someone has to decide it under pressure: where one
   of these documents *restates* a frozen spec — CLI-SPEC §0.5 restating INTROSPECTION-SPEC §1
   is the case to think about — the restatement never carried the authority. CLI-SPEC §0.3
   already says the frozen spec wins and the disagreement is a defect to file (WA-03), so
   correcting a stale restatement is bringing prose into line with something that had already
   won, not moving a contract. What *is* an amendment, and needs its own card, is a change that
   makes one of these documents promise something different from what the upstream says —
   including anything that would weaken a never-invokes rule, which the stamp now makes exactly
   as hard as strengthening one.
5. **The `1.6` row added here** (the OI-7 row) splits the unrowed class by direction: a value
   rule that *narrows or is clarified*, admitting nothing a consumer had not already been told
   to expect, is **none**; a value rule that *widens or changes what the same value means* is
   **MINOR** on the same ground as the present-iff row — the documents are a superset and a
   strict consumer built against the narrower rule may refuse one, or worse, read it. A
   value-rule change that also moves exit-code derivation, the finding set or strict reach is
   **MAJOR** by the row that already exists. The 2026-08-05 `subject.source` amendment is the
   worked example: it was a narrowing correction (the field always held the invocation's own
   reference; the pointer beside the example was wrong), so it was, and remains, **none**.

## 7. What this record does not claim

- **No verification claim of any kind.** Promotion is a documentation and governance event.
  It says nothing about what a validator decides, what a witness means, or what a passing run
  establishes; the honest-claims boundary (WA-06) is untouched and P-02 language remains
  witness-presence wording only.
- **It does not sign a gate.** G7 is open and this record is one of its evidence items, not
  its sign-off. PHASE-0-DOD-CHECKLIST's Protocol paragraph assigns evidence slots to the
  traceability role; G7-4's slot names this file, and filling it stays that role's act
  (WA-09 — gates pass by evidence and sign-off, never by a card declaring them passed).
  The same holds for the two countersigned dry-run records, whose open deviations DV-1-2 and
  DV-2-2 triage to "task: CLI-08": this card's completion is what those deviations were
  waiting on, and recording that in the records is the traceability role's act, not this
  file's.
- **It does not promote the brief's post-freeze scope.** Brief D-12 describes growth under the
  control-plane arc — trace overlays on the versioned graph (gated on brief D-14) and
  ESTIMATED-class stochastic overlays (gated on brief R-08). Both stay gated on their own
  briefs, out of scope for Phase-0 (SOW §8), and neither is armed by this promotion.
- **It does not ship, schedule or design a VS Code extension.** §3's EXTENSION-SPEC row is an
  outline for Phase-1. No extension code exists in this repository, none is planned in
  Phase-0, and the outline itself builds nothing.
- **It does not re-open, or stand in for, the brief's other Definition-of-Done lines.** Only
  the first of that DoD's five is this card's ("promotion criteria met"). The rest were
  discharged, or are owned, elsewhere, and this record neither repeats nor re-certifies them:
  "all five subcommands run end-to-end against the travel-booking workflow" is CLI-07's
  integration flow; "output distinguishes the claim classes and severities … no banned claim
  phrasing anywhere" is CLI-03's rendering catalog with CLI-07's render sign-off
  ([RENDER-SIGNOFF.md](RENDER-SIGNOFF.md)) and the TE-15 lint; "`gebra display` output renders
  correctly in external Mermaid viewers" is the **DOC track's**, still open, and
  DIAGRAM-STYLE-GUIDE §9 is careful that its own parse-check is not that observation; "CI
  format consumed successfully by the D-10 pytest plugin and a sample GitHub Actions gate" is
  TE-07's plugin plus the CI-gate note in `docs/ci/`. A reader auditing the brief against this
  repository should walk those to their own cards, not to this file.

## 8. Who consumes this

- **G7-4** (PHASE-0-DOD-CHECKLIST; master plan §4) — "D-12 promoted". This is the record its
  evidence column names.
- **CLI-SPEC §7 and REPORT-FORMAT-SPEC §7** — both name CLI-08 as the card that stamps them;
  both now carry the landing note pointing back here.
- **DOC-15** (CLI reference) and the rest of the DOC track — they document the shipped verbs
  against a contract that no longer moves under them.
- **A Phase-1 reader** — §5's re-routed items are the honest backlog this track hands forward,
  and §6 is the route each of them travels.
