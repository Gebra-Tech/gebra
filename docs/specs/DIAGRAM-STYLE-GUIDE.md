# DIAGRAM-STYLE-GUIDE — Mermaid rendering of the Gebra IR

> **What this document is.** A repo-authored **contract specification**, produced by card
> CLI-06 — the artifact brief D-12's table names for OQ-12-02 ("Mermaid rendering of the IR;
> overlay design"). It fixes how `gebra display` draws a workflow definition as Mermaid text
> and how a run report's findings are painted onto that drawing, so that the emitter, its
> tests (CLI-07), and any later lens over the same diagram (the P2 VS Code extension,
> CLI-08's EXTENSION-SPEC outline) draw one picture instead of several.
>
> **Authority.** The emit-vs-overlay question is settled by PD-034 (CLI-D2, ratified
> 2026-08-04): the diagram is emitted **directly from the `WorkflowIR`** by a gebra-owned
> emitter — no dependency on LangGraph's `get_graph()` or `draw_mermaid()` anywhere in the
> `display` path — and PlantUML is demoted out of Phase-0 (§8). This guide resolves the
> latitude PD-034 reserves to CLI-06 (id mapping, style choices, overlay encoding,
> large-graph handling) and changes nothing PD-034 fixed. The verb's flags, modes and exit
> codes are CLI-SPEC §4.4's; the envelope shapes painted here are PROPERTY-CATALOG-SPEC
> §0.3's (frozen); the report wrapper is REPORT-FORMAT-SPEC's.
>
> **The presentation-only boundary binds the diagram** (CLI-SPEC §0.1). A diagram states
> what the IR declares and what a run report recorded — it reaches no verdict, computes no
> structural fact of its own beyond the spec-fixed §2.4 label expansion it shares with every
> graph-algorithm consumer, and never labels a workflow safe, correct, or verified. Every
> painted finding carries its claim class (WA-06; PD-034).
>
> **Status: FINAL.** Ratified as CLI-06's artifact, and **stamped final at the D-12 promotion
> on 2026-08-31** (card CLI-08; the record is
> [docs/governance/D-12-PROMOTION.md](../governance/D-12-PROMOTION.md)). Final means no
> Phase-0 card amends this contract further; a later change needs its own card and a landing
> note in §9. The guide's two deferrals move with it and are not reopened by the promotion:
> PlantUML stays out of Phase-0 (§8) and large-graph folding stays a Phase-1 possibility (§6).

---

## Table of contents

- [1. The artifact](#1-the-artifact)
- [2. Identity: Mermaid ids and labels](#2-identity-mermaid-ids-and-labels)
- [3. Topology](#3-topology)
- [4. The verification overlay](#4-the-verification-overlay)
- [5. Palette](#5-palette)
- [6. Large graphs](#6-large-graphs)
- [7. Copy rules](#7-copy-rules)
- [8. PlantUML](#8-plantuml)
- [9. Conformance](#9-conformance)

---

## 1. The artifact

1. **One Mermaid flowchart per invocation**, UTF-8 text, beginning (after the `%%` header
   comments of rule 5) with exactly `flowchart TD`. Top-down is the reading direction of
   the reports rendered beside it (START first, END last); no other direction is emitted in
   Phase-0.
2. **The diagram is the stdout artifact and nothing else rides it** (CLI-SPEC §5.2):
   `gebra display --ir workflow.ir.yaml | mmdc -i -` is a valid pipeline. Diagnostics go to
   stderr. `--color`/`--no-color` govern the stderr diagnostics only — the diagram itself
   is plain Mermaid text on every setting (CLI-SPEC §4.4); its colors are Mermaid
   directives (§5), not terminal escapes.
3. **Byte-reproducible.** Equal inputs (IR, and report when one is given) produce identical
   bytes across runs, processes and platforms. The diagram embeds **no tool version** and no
   timestamp; provenance is the subject line in the header and, on the overlay path, the
   report's own recorded identity (§4.1). This is what makes the CLI-07 goldens
   byte-comparable with nothing normalized.
4. **Line discipline.** Every line, including the last, ends with `\n`; the same bytes are
   written to a stream and to `--output`. Indentation inside the flowchart body is two
   spaces; blank lines separate the header, the node definitions, the edges, the legend
   (when present), and the style directives, in that order.
5. **Header comments.** The artifact opens with `%%` comment lines (invisible in a rendered
   diagram; part of the text artifact) stating, in order:
   - `%% gebra display: workflow definition as Mermaid (DIAGRAM-STYLE-GUIDE)`
   - `%% subject: <source> (<input_mode>)` — the CLI-SPEC §2.1 subject label, when the
     caller supplied one (the verb always does; the library function admits `None`);
   - `%% ir_version: <ir.ir_version>`;
   - on the overlay path, the `%% overlay:` lines of §4.1.

## 2. Identity: Mermaid ids and labels

The IR node-id grammar (IR-SPEC §5) and Mermaid's identifier rules are different languages,
so the emitter assigns every drawn element a Mermaid-legal id **deterministically derived
from the model vertex it draws** (PD-034's required property). The mapping deliberately does
not borrow LangGraph's `:`-nesting convention (PD-034 finding 6).

1. **Vertex ids.** The sentinel vertices `__start__`/`__end__` map to the fixed ids
   `START` and `END`. Every other vertex (a declared node id, or a carried unresolved
   reference, §3.2) maps to `n_` + the escape of the vertex string: each character in
   `[A-Za-z0-9]` is kept; every other character is replaced by `_` + two lowercase hex
   digits per UTF-8 byte (`_` itself becomes `_5f`). The escape is injective, so two
   distinct vertices can never collide on a Mermaid id.
2. **Overlay ids.** Legend nodes are `f_1`, `f_2`, … in finding order, and `f_0` for the
   §4.3 statement entry when there is no finding to number; the legend subgraph id is
   `gebra_findings`. The three id families (`START`/`END`, `n_…`, `f_…` +
   `gebra_findings`) are prefix-disjoint by construction.
3. **No emitted id is a Mermaid keyword.** The reserved words (`end`, `subgraph`,
   `flowchart`, `graph`, `classDef`, `class`, `linkStyle`, `style`, `click`, `direction`,
   `default`) cannot arise from the mapping above (`END` is upper-case; every other id
   carries its prefix); the conformance checker refuses them anyway (§9).
4. **Labels.** Every node and edge label is a double-quoted Mermaid string of the display
   text with exactly five escape rules, each to a Mermaid decimal entity: `#` → `#35;`,
   `"` → `#34;`, `<` → `#60;`, `>` → `#62;`, and every control character (below U+0020,
   and U+007F) → `#<decimal>;`. The angle brackets are escaped because Mermaid's default
   label mode reads HTML-shaped text as markup, and a node id such as an LCEL
   `%map[<lambda>]` segment must render as its own characters, not vanish into a tag. All
   other characters, including non-ASCII, are kept verbatim. Display text for a vertex is its report-side spelling:
   `__start__`/`__end__` render as `START`/`END` (PROPERTY-CATALOG-SPEC §0.3's display
   sentinels — the same spelling a report shown beside the diagram uses); every other
   vertex renders its id byte-for-byte, never unescaped and never re-derived.

## 3. Topology

### 3.1 The drawn graph

The drawing is the **sentinel-augmented, label-expanded multigraph** of IR-SPEC §4.2
(m1)–(m5) — in code, `gebra.verify.graph.build_graph_model(ir,
carry_unresolved_references=True)`. This is the one shared implementation of the §2.4
label-expansion rule "every graph-algorithm consumer already applies" (PD-034), so the
topology the diagram draws is expressed in exactly the vocabulary the validators anchor
findings to; the emitter runs **none** of the analyses that model offers (no reachability,
no components) — verification content enters only through a run report (§4).

Concretely:

- **(m1)/(m2)** each `entry` member draws as an edge `START → e`, each `finish` member as
  `f → END`, both in the normal-edge style — the sentinel wiring the IR declares;
- **(m3)** each `path_map` label draws as one labeled arrow `from → path_map[label]`, the
  label being the map key; a label valued `"END"` targets the END vertex;
- **(m4)** `to: "END"` on a `normal`/`send` edge is **not** a sentinel reference (the
  literal is blessed for `path_map` values only — IR-SPEC §4.2 (m4) as corrected at
  DEC-27): it resolves like any other target, to a declared node of that id if one exists,
  else as an unresolved reference (§3.2);
- **(m5)** START has no incoming and END no outgoing edge; a declared reference spelling a
  reserved segment (`__start__`/`__end__`) is never materialized, so an edge wired to one
  is not drawn (its finding, if a report carries one, is legend-only — §4.5).

### 3.2 Vertices

| Vertex | Shape | Class (§5) | Label |
|---|---|---|---|
| START / END | stadium — `START(["START"])` | `gebra_sentinel` | the display sentinel |
| declared node (`ir.nodes[]`) | rectangle — `n_x["…"]` | none (renderer default) | the node id, byte-for-byte |
| carried unresolved reference | rectangle | `gebra_unresolved` (dashed) | the reference string, byte-for-byte |

A **carried unresolved reference** is a declared reference (an `entry`/`finish` member, an
edge endpoint, a `path_map` value) naming no node in the document. It is drawn — dashed,
in the muted §5 style — because the declaration is IR content and a diagram that silently
dropped it would hide exactly the defect P-01 reports there; the dashed style states "the
definition names this; no node of this id exists", nothing more. Node **annotations**
(contracts, effects, digests) and the state schema Σ are not drawn in Phase-0: a run
report's findings carry the annotation facts that matter onto the diagram (§4), and a
per-node contract dump is a Phase-1+ possibility, not a present capability.

**Definition order** is fixed: START; the declared nodes in `ir.nodes[]` order; the carried
references in first-recorded model order; END.

### 3.3 Edges

| Edge | Arrow | Label |
|---|---|---|
| `normal` (including m1/m2 sentinel wirings) | solid `-->` | none |
| `conditional`, per expanded label | solid `-->\|"label"\|` | the `path_map` key |
| `send` | dashed `-.->` | none |

The dashed `send` arrow denotes the **dynamic fan-out template**: the IR is deliberately
silent on the runtime fan-out count, and the diagram draws one arrow — never N — so it
cannot imply one (PD-034). A `conditional` edge's `condition` string (the declared router
expression) is **not** drawn: the per-label arrows carry the router's structure, and the
expression is declared IR content a reader finds in the document itself — elided here as a
legibility choice, stated so it is not read as absence. Edges are emitted in the model's
emission order (entry wirings, finish wirings, then `ir.edges` in authored order with each
router's labels in authored order) — the order that makes Mermaid's link indices, and with
them §4.4's `linkStyle` paints, deterministic.

### 3.4 Documents this guide declines

A document carrying a `dynamic` edge (`ir_version` 1.1 — DEC-28) is **declined**, exactly
as `verify()`, the structural diff and the snapshot engines decline it: a `dynamic` edge
contributes no member to the graph the §0.3 vocabulary is defined over, and its
consumer-side representation is assigned to the kind's paired follow-up cards, not
improvised here. `gebra display` reports the decline as a CLI-SPEC §2.6 tool error
(`ir-validation` stage, exit 2); the diagram representation of a headless router edge lands
with those semantics, in a later card, not in this guide.

## 4. The verification overlay

### 4.1 Pairing: overlays name their own graph

The overlay input is a native-JSON run report (`gebra verify --format json` output). Before
anything is painted (CLI-SPEC §4.4; REPORT-FORMAT-SPEC §1.6):

1. `report_format` is read first, off the parsed JSON; a MAJOR this build does not know is
   refused, and so is a MINOR this build does not read (§1.6 grants a strict consumer that
   refusal; the diagnostic names the format this build reads).
2. The document must validate as a `RunReport`.
3. The report must **name its own graph**: a report with no `subject` (a tool error that
   preceded IR identity) is refused — it carries no `graph_version` for the provenance
   check, and no findings to paint.
4. `subject.graph_version` must equal the displayed IR's own IR-SPEC §6 digest, computed by
   the same `gebra.ir.graph_version` pipeline everything else uses. A mismatch is refused:
   painting one workflow's findings onto another's topology would be a false statement
   about both. The comparison is a string-compare of two digests — a provenance check,
   never a verdict.

An accepted overlay adds `%% overlay:` header lines stating the report's own facts,
verbatim from the report: the (elided) `graph_version`, `gate.outcome` with
`gate.exit_code`, the `gate.counts` triple, `gate.strict` when its mode is not `off`, the
`gate.promotions` count when it is non-empty (with §0.2's own sentence — promotion moves
the gate, never the record), and — when `best_effort` is non-empty — the §1.3 statement
that those properties' outcomes are best-effort diagnostics, not contract-bearing
verdicts.

### 4.2 What is painted

The overlay paints **findings** — REPORT-FORMAT-SPEC §2.1's definition: a failing report's
primary `Failure`, every `CoFailure`, every `Advisory`, each with its own severity, claim
class, condition ID and location. In code the walk is
`gebra.report.findings.findings_of`, the same §2.1 traversal the terminal renderer uses.
Nothing else is painted: pass witnesses, witness notes and not-implemented markers are
report content, not diagram paint (the run report beside the diagram carries them), and a
strict-mode promotion moves the gate, never the record — a promoted finding is painted at
its own recorded severity like any other (§0.2).

### 4.3 Finding indices and the legend

Findings are numbered `F1, F2, …` in report order (properties in catalog order, records in
their §1.4 rule-3 order). **Every finding appears exactly once in the legend**, whatever
its anchor: the legend is a `subgraph gebra_findings["gebra findings overlay"]` block of
one node per finding, styled by the finding's severity class, labeled on one line:

```
F<i> <severity> [<claim-class>] <condition-id> - <location phrase>
```

- the severity word and claim class are the record's own, in their serialized spellings —
  the claim class is **always** displayed with the painted finding (WA-06; PD-034), and the
  legend is a rendered element, visible in the diagram, not a comment;
- the location phrase is REPORT-FORMAT-SPEC §4.5's one-line anchor phrase
  (`gebra.report.anchors.location_phrase`), so the diagram and the terminal report name an
  anchor identically;
- a finding whose owner is in `report.best_effort` carries the suffix ` (best-effort)`;
- a finding with no drawable anchor (§4.5) carries the suffix
  ` - not drawn in this diagram`.

Legend nodes are wired to nothing: the legend is chrome, visually a box of labeled entries,
and never adds an edge to the workflow picture. With an accepted overlay and **zero**
findings, the legend still renders, with one neutral entry stating the report's own gate
outcome and pointing at the run report — e.g. for a pass:
`no findings to paint - gate: pass (exit 0); per-property claim classes are in the run
report` — never a bare pass badge, never "no issues" (the wording rules of §7 bind it).
For a tool-error report that carries a subject, the entry states that no verdict was
reached and names the stage.

### 4.4 Paint by location kind

Dispatch is on the anchor's frozen `kind` discriminator (PROPERTY-CATALOG-SPEC §0.3);
concrete subtypes paint as their anchor kind. Two paint channels keep distinct meanings:
**node fill** (severity classDef) marks a finding anchored *at* a vertex; **linkStyle**
(severity stroke) marks a finding anchored *along* edges.

| kind | Anchor resolution | Paint |
|---|---|---|
| `node` | the named vertex | severity class on the vertex + ` [Fn]` appended to its label |
| `edge` | expanded edges with the anchor's source and target; the anchor's `label` when present narrows to that label-expansion; a dangling anchor (`target` omitted) matches the carried-reference edge for its `undefined_target` (and `label`, when present) | severity `linkStyle` on each matched edge + `[Fn]` on its label |
| `cycle` | the member edge set: for each consecutive pair of the recorded rotation, closing wrap included, every expanded edge between that pair | severity `linkStyle` over the set + `[Fn]` on each member edge's label |
| `scc` | every expanded edge with both endpoints in the member set | as `cycle` |
| `path` | for each consecutive pair of the recorded node sequence, every expanded edge between that pair, in path order | as `cycle` |
| `state-key` | the location's `node` when present (Σ has no vertex; the attributed reader/writer is the nearest relevant node — PD-034's anchor latitude, resolved here; P-04's `DataflowLocation` always names one) | severity class on that vertex + ` [Fn]` on its label; legend-only when the location names no node |

Resolution details, fixed so two implementations cannot diverge:

- A report-side node reference resolves to the declared node of that exact id when one
  exists, else `START`/`END` resolve to the sentinels, else to a carried reference vertex
  of that string, else the finding is **not drawn** (§4.5). Preferring the declared node
  makes a user node genuinely named `START` win over the sentinel reading, which is the
  only deterministic choice available to a reader of the serialized form (the projection is
  stated forward-only — `gebra.verify.base.from_display`'s own caveat).
- A pair with **parallel edges** paints all of them: the record names vertices, not which
  parallel edge, and painting a subset would be a derivation the record does not license.
- Multiple findings on one element: the element takes the **highest** severity's style
  (fatal > error > warning) and accumulates every marker — `[F1 F3]`.
- Cycle and SCC paints are linkStyle runs, never `subgraph` boxes: a vertex can sit in two
  findings' member sets, and Mermaid puts a node in at most one subgraph — a grouping box
  would collide exactly where overlays overlap. (PD-034 offers either encoding; this guide
  fixes the linkStyle run.) The condition ID labeling PD-034 requires rides the `[Fn]`
  markers, which resolve in the rendered legend to the condition ID on the same line.

### 4.5 Nothing is dropped

A finding whose anchor has no on-picture element — a reserved-segment reference that (m5)
keeps out of the drawing, a report-side name resolving to no vertex — is still numbered,
still in the legend, suffixed ` - not drawn in this diagram`. The legend is the complete
finding list; the picture is the subset with drawable anchors. (For a report that passed
§4.1's digest check, anchors resolve in practice; the rule exists so the corner cases
degrade to honesty rather than silence.)

## 5. Palette

One visual vocabulary with the terminal renderer (PD-031: fatal/error in the red family,
warning in amber). Class and stroke values are fixed here so every emission styles alike:

```
classDef gebra_fatal fill:#dc2626,stroke:#7f1d1d,color:#ffffff
classDef gebra_error fill:#fecaca,stroke:#dc2626,color:#7f1d1d
classDef gebra_warning fill:#fef3c7,stroke:#d97706,color:#78350f
classDef gebra_sentinel fill:#f3f4f6,stroke:#374151,color:#111827
classDef gebra_unresolved fill:#f9fafb,stroke:#6b7280,stroke-dasharray: 4 3,color:#374151
classDef gebra_info fill:#f3f4f6,stroke:#6b7280,color:#111827
```

Link paints: fatal `stroke:#7f1d1d,stroke-width:3px`; error
`stroke:#dc2626,stroke-width:2px`; warning `stroke:#d97706,stroke-width:2px`.

`gebra_info` styles the zero-findings legend entry (§4.3). Only the classes an emission
uses are declared in it. Severity is **never** carried by color alone: the severity word is
in the legend line and the `[Fn]` marker is on the painted element, so a monochrome
rendering of the diagram loses styling, not facts — the same degradation rule the terminal
surface holds (REPORT-FORMAT-SPEC §5.1 rule 7, carried to this artifact).

Emission order of the style block: `classDef` lines (fixed order: fatal, error, warning,
sentinel, unresolved, info — those used), then `class` assignment lines grouped per class
in definition order, then `linkStyle` lines in ascending link index.

## 6. Large graphs

**Phase-0 draws everything.** No automatic collapsing, sampling, or elision: every declared
node, every carried reference, and every expanded edge is in the picture, because a diagram
that silently dropped elements would misstate the definition it claims to draw — the same
rule the report surfaces hold (REPORT-FORMAT-SPEC §4.4 "never a summary that drops
records"). The honest costs are stated instead: a wide `path_map` draws one arrow per
label (that is the router's actual structure), and layout of a large drawing is the
renderer's job, not this artifact's. Interactive folding, subgraph collapsing and
level-of-detail are Phase-1+ possibilities for the extension lens (D-028), named here only
as possibilities.

## 7. Copy rules

REPORT-FORMAT-SPEC §4.6 binds every string this artifact emits — labels, legend lines,
header comments — and the TE-15 lint scans the emitter's templates like any other source.
In particular: the claim class is always displayed with a painted finding (§4.3); a
diagram never states or implies a verdict of its own — the gate line in the overlay header
is the report's own recorded outcome, quoted; witness-presence wording is the only wording
P-02 content gets; a zero-findings overlay names the gate outcome and points at the run
report, never "no issues found"; and the subject is the workflow **definition** — nothing
here describes runtime behavior.

## 8. PlantUML

There is **no PlantUML emitter in Phase-0** (PD-034: demoted out of the phase). PlantUML
output is a possibility a later phase may take up under its own card; it is named here so
its absence reads as decided, and nothing in this repository emits or tests it (WA-12: this
sentence describes a decision, not a capability).

## 9. Conformance

- **The emitter** is `gebra.display` (`render_mermaid(ir, report=None, source=None)`), and
  `gebra display` (CLI-SPEC §4.4) is its one CLI caller. Every rule above is testable and
  tested: ids and escapes (§2), the drawn multigraph and its ordering (§3), the pairing
  refusals (§4.1), per-kind paint and the legend (§4.3–§4.5), the palette block (§5).
- **The licensed Mermaid subset** is exactly what this guide names: `%%` comments,
  `flowchart TD`, rectangle and stadium node definitions with double-quoted labels, solid
  and dotted arrows with optional quoted labels, one non-nested `subgraph … end`,
  `classDef`/`class`/`linkStyle` with the §5 declarations. `tools/mermaid_check.py` is the
  conformance checker: a dependency-free validator of that subset which **refuses any
  construct outside it** — an undefined node reference (Mermaid itself would silently
  auto-vivify a vertex for a typo'd id), a keyword id, a malformed label entity, a
  `linkStyle` index no emitted link has, a nested subgraph — so an emission it cannot check
  fails the suite instead of passing unchecked (the `tools/json_schema.py` discipline).
  CLI-07's corpus-level suite runs every emission through it.
- **What "parse-checked" claims.** The checker parses the emitted text against the licensed
  subset of Mermaid's documented flowchart grammar; it is not the Mermaid renderer, and
  rendering in external viewers is exercised where D-12's Definition of Done places it
  (the executed-examples harness and the flagship tutorial, DOC track).
- **CLI-08 (D-12 promotion), landed 2026-08-31.** This guide is stamped final with CLI-SPEC and
  REPORT-FORMAT-SPEC; the record is
  [docs/governance/D-12-PROMOTION.md](../governance/D-12-PROMOTION.md), which carries the
  artifact table the stamp completes. Nothing above changed: no rule, no palette value, no
  escape, no emitter behavior. The one forward reference this guide already made — that a later
  lens over the same diagram should draw one picture rather than several — now has its
  addressee in [EXTENSION-SPEC.md](EXTENSION-SPEC.md) §4.2, which binds a Phase-1 extension to
  §4's encoding rather than letting it invent one.
