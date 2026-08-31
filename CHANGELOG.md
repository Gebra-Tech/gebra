# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The validator explainer "P-01 graph-well-formed"** (card DOC-08; PROPERTY-CATALOG-SPEC §1
  and §0; the DEC-11 and DEC-12 shape pins). `docs/validators/p01-graph-well-formed.md` is the
  first of the five per-validator pages, written for someone holding a report rather than for
  someone learning the tool: what the validator checks, what every field of its witness and its
  failure record means, and where the claim stops.

  Six examples run under the DOC-01 harness, and none of them builds a graph: five read the
  **vendored property-fixture corpus** — a fixture is data, so the page's transcripts are runs
  over the frozen examples the validator is already held to in CI — and the sixth writes a
  one-node IR document by hand. `a-pass-and-its-witness` prints the serialized
  five-key witness (DEC-11's pin) off a corpus positive and re-checks the whole report against the
  fixture's own `expected:` block through §0.3's comparison; `a-failure-and-its-record` does the
  same for the catalog's canonical dangling-`path_map` typo, showing P-01's edge location with
  `source`, `label` and `undefined_target` — and the anchor's `target` deliberately absent, per
  §0.3's dangling-reference rule — beside the unreachable-node cascade riding `co_failures`.

  `four-conditions` runs all seven P-01 fixtures at once, so each condition appears with the
  fixture that pins it and the three distinctions a reader actually needs are read off a
  transcript: unreachable is not orphaned, orphaned is all three at once, and a dead end is about
  outgoing edges rather than about reaching the end of a workflow. `sentinel-wiring` makes DEC-11's
  orphan reading visible on the case that separates it from the rejected one — one node, no edges,
  passing when it is named in `entry`/`finish` and failing as an orphan with two cascades when it
  is not. `topology-only` strips the state schema, every node annotation and the router expression
  out of a passing fixture's document and shows the report is the same value, which is §1.3's
  "not read" list checked rather than believed. `well-formed-is-not-well-behaved` runs P-01 and
  P-02 over an unwitnessed reflection loop, so "well-formedness says nothing about cycles" is a
  transcript rather than a sentence.

  The closing section states the limits with the same discipline: condition (ii) is catalog-literal
  and a trap component is therefore not a P-01 finding (a recorded specification open item, not
  closed quietly here); a mounted subgraph is one opaque node whose interior is P-10's, which this
  release does not implement; and when P-01 fails, P-02, P-04 and P-06 become best-effort
  diagnostics on that run. The site index and the README's documentation list gained the page, and
  `tests/docs/test_docs_site.py`'s `LANDED_PAGES` is what drops it out of the placeholder
  assertions.

- **The tutorial "Verify and interpret"** (card DOC-07; PROPERTY-CATALOG-SPEC §0; SOW §6).
  `docs/tutorials/verify-and-interpret.md` runs the wedge five over the travel-booking agent —
  the same definition the acceptance scenario uses, imported rather than copied — and then reads
  what came back. It is organised around one question: for any line in a verify report, what
  exactly is being claimed, and on what evidence?

  Seven examples run under the DOC-01 harness, in the order a reader meets the material.
  `one-run-report` shows the shape of a run: thirteen outcomes of which five are verdicts and
  eight are structured not-implemented markers, a subject whose label is the caller's while its
  digest is computed, and a gate derived from the outcomes rather than decided per property.
  `five-witnesses` is the half no other page covers — what a **pass** actually contains: P-01's
  two deliberately empty lists (evaluated, not skipped), P-02's inventory entry and re-checkable
  acyclicity certificate, P-04's eighteen `(reader, key)` coverage rows including one satisfied
  at the `START` boundary, P-06's two records showing both protection kinds on one graph, and
  P-08's in-band `claim_class` beside its mandatory provider caveat.

  `reading-a-failure` walks the five seeded-defect variants and reads the failure record field by
  field, with the **locus** as the lesson: defect 1 anchors on an SCC because no single node is
  at fault, defect 4 on a state key with the offending `START`-rooted path, defects 2 and 5 on a
  node — the latter carrying `fanout: send` — and P-04's own `writers_on_other_paths` names the
  node that does write the key, just not on that path. `claim-classes` prints the two frozen
  tables a grade is read off: the property table a pass is displayed under, and the condition
  registry each finding's severity and class come from, with the emittable count computed rather
  than asserted. All three claim classes appear in executed transcripts on the page.

  `strict-mode` runs defect 3 under four policies and makes the record-versus-gate split
  mechanical: the exit code moves twice, and the four runs produce exactly **one** distinct
  `(condition, severity, claim class, warning tally)` tuple between them — printed as a set, so
  the invariance is shown rather than claimed. A per-property flag naming a different property is
  included as the useful negative. `p01-precondition` edits the extracted IR *document* — one
  node dropped from the wired-to-`END` set — to reach a FATAL P-01 finding, and shows
  `best_effort` naming the three topology properties whose passes on that run are diagnostics
  rather than contract-bearing verdicts. `the-rendered-report` prints slices of the real
  `render_human` output, the same rendering `gebra verify` writes, so the page's account of how
  a claim class rides every verdict line is a quotation rather than a description.

  The closing section is the honest boundary, stated as four claims the transcripts above already
  show: witness presence rather than semantic termination, with both P-02 transcripts as the
  evidence; a DEFENSIBLE-A pass as a statement about declarations; vacuous passes distinguished
  by the witness inventory rather than by the verdict word; and a pinned seed as a claim about
  the definition, which is why P-08 is HEURISTIC and carries its caveat.

- **The examples guard pre-imports `gebra.report`** (card DOC-07; WA-07).
  `tools/docs_examples.py` imports the gebra surface an example may use inside its prologue, so
  that a page's own imports reach modules already in `sys.modules` rather than the armed socket
  and the `Runnable` sweep sees every class that will be loaded. `gebra.report` was the first
  module a page imported that the prologue did not name — the verify tutorial's rendered-report
  example reaches it, and with it `rich`, whose import would otherwise have happened after socket
  construction stops being counted and starts raising. Nothing was unarmed by the omission, but
  the list exists so that this need not be checked by hand.

- **The sample-workflow ledger rule is mechanical** (card DOC-07; WA-07).
  A documentation example that builds against `tests/sample_workflows/` inherits that module's
  `TRIPPED` ledger, and whether the leg is live rather than vacuous depends on a control having
  fired one of its bodies inside a real guarded run. Which modules had such a control was a
  hand-maintained table beside a growing set of pages; it is now the source
  `test_every_example_importing_a_sample_workflow_carries_a_fired_ledger_control` reconciles
  against the modules actually imported by the discovered examples — the third rule of this shape,
  after `SELF_DEFINED_MARKERS` and `WRITES_A_MODULE`. It is fail-closed in both directions: an
  import form the parser does not recognise fails rather than reading as importing nothing.

- **The tutorial "Contracts and annotations"** (card DOC-06; ANNOTATION-API-SPEC §1–§6).
  `docs/tutorials/contracts-and-annotations.md` picks up exactly where "Extract your first IR"
  left off — six warnings and one sentence about clearing them — and works that sentence out:
  `@gebra.contract` and the six decorators beside it, the `gebra.toml` sidecar, the per-slot
  precedence chain between them, and the line inference will not cross. The page is
  organised around one question a reader can actually use: for any slot on any node, which
  surface set it, and how would you know.

  Six examples run under the DOC-01 harness, and the progression is deliberate — declare, then
  the rules that refuse a declaration, then a declaration that never arrives, then the second
  surface, then the whole chain in one transcript, then inference's ceiling.
  `declaring-contracts` re-declares the previous tutorial's research assistant and extracts it
  to **zero warnings**, which is the practical payoff stated as a transcript rather than as a
  promise. `decoration-time-rules` fires all four §1 consistency rules plus the
  attachment-impossible refusal, each printed with its stable `reason` code — including the
  duplicate-slot rule firing on two *identical* values, which is stricter than the cross-surface
  rule further down the page and is meant to be.

  `wrapped-declarations` documents a failure mode that is easy to hit and hard to diagnose:
  a decorator of the reader's own that forgets `functools.wraps` breaks the walk
  §6 relies on, so a well-formed declaration is invisible and the node reads as never annotated.
  The transcript makes the cost concrete — the node carrying `effects=["network"]` resolves to
  `pure: true`, the opposite claim, at defaulted grade — and the page states plainly that the
  failure is silent by construction, because nothing distinguishes "declared nothing" from
  "declared something a wrapper hid".

  `precedence` is the centrepiece: one graph with all four tiers live, printing every resolved
  slot with its ANNOTATION §5 grade beside it, then every warning, then two records in full.
  It shows the DEC-07 conflict (decorator kept, sidecar discarded, both values named) beside
  the non-conflict on another slot of the same node where the two surfaces agree; the
  tool-carried tier winning over a sidecar `args_schema`; `pure=False` occupying its slot and
  blocking the tier below, because "set" means not-`None`; the sidecar filling a vendored
  node's contract at declared grade; and a resolved contract no single surface authored —
  decorator `pure` plus sidecar `effects` — repaired by discarding the lower tier with an
  `annotation-invalid` naming both surfaces. `the-sidecar` covers the file itself: the schema
  line, node-id keys and their quoting, the stale-key warning, and why discovery-by-CWD makes
  a `graph_version` depend on where the command ran.

  `never-silent-upgrade` fires the §4 rule at the shape that tests it — a node that is as
  idempotent and as deterministic as code gets, whose extraction declares neither — and prints
  `claims_not_upgraded` from the inference record itself. Its second half is the §5 grade
  lookup made visual: two nodes resolve to the *same* contract, `{'pure': True, 'input':
  ('hits',)}` on both, and only the envelope tells them apart. The page states the corollary
  honestly rather than aspirationally: a declared `pure` may feed the idempotence implication
  and a heuristic one may not, and in this release nothing exercises it, because no implemented
  property validator reads `pure` at all (P-06 delisted it per DEC-13; P-07 is not in the
  wedge). The page is equally careful about what clearing the warnings buys: extraction
  warnings are not findings and never move an exit code, so what declaring changes is the
  *grade* of a value, not the gate — `docs/specs/CLI-SPEC.md` §3.5 is the line it keeps.

  Control coverage lands with the page. `WRITTEN_MODULE_LEDGER_CONTROLS` in
  `tests/docs/test_doc_examples.py` gains an entry for each of the five module-writing
  examples, and now carries the probe state per page rather than sharing one graph's state
  across all of them, so each control calls its node the way that page's workflow would. The
  floor assertion that no example of this shape can land uncontrolled is what makes the
  addition mechanical rather than remembered.

  Two shapes this page introduced needed controls the floor tests cannot find, and both are
  fired rather than argued. A **tool as a node** has an implementation reached by a route that
  is not a node call: the control drives `find_hotels.run(...)`, which is deliberately outside
  the armed invoke family, and the ledger entry it produces is what keeps the page's "read for
  its schema and never invoked" from resting on an empty list nobody could have filled. And an
  example that **decorates callables without building a graph** is matched by neither
  `SELF_DEFINED_MARKERS` nor `WRITES_A_MODULE`, so the decoration-time example arms its own
  targets and a control fires one — a decorator that called what it was handed now fails that
  page instead of printing a clean transcript.

- **The examples guard arms tool invocation by name** (card DOC-06; WA-07).
  `tools/docs_examples.py` now imports `langchain_core.tools` in its guard prologue, beside
  the `language_models` import that is there for the same reason. `BaseTool` overrides
  `invoke`/`ainvoke`, so a class entering the `Runnable` tree *after* the sweep would shadow
  the armed base and silently disarm tool invocation for every documentation example. It was
  in the tree before this change only because `gebra.extraction` imports it to read the
  tool-carried `args_schema` tier — a library import the guard must not depend on, since
  making that import lazy would have broken the leg with no test failing. The raiser controls
  gain a `tool-invoke` case, so the leg is now fired in the same run that claims it.

- **The tutorial "Extract your first IR"** (card DOC-05; INTROSPECTION-SPEC §0–§3, §4.1).
  `docs/tutorials/extract-your-first-ir.md` is the first written page of the Tutorials
  section: a small LangGraph `StateGraph` taken through `gebra.extract()` to IR YAML, read
  field by field, followed by the other half of what extraction hands back — the warnings
  that say how a value got into the document — and then the boundary of what reading a
  definition can know at all.

  Two examples run under the DOC-01 harness, and both **write their agent to a module and
  import it back** rather than defining it inline. That is not decoration: extraction locates
  a node's source the way any Python tool does, so a graph defined in a string-compiled
  `__main__` falls to the conservative defaults on every slot, and a transcript produced that
  way would not be the one a reader saving the same file gets. Writing the file makes the page
  reproducible in the strict sense — the bytes shown are the bytes extracted, and the
  inference the page teaches is the inference a reader sees.

  That shape needed the WA-07 sweep extended, and it is extended here rather than worked
  around on the page. `tools/docs_examples.py`'s trailer swept `__main__` and
  `tests/sample_workflows/` by name; a module an example writes at run time is called neither,
  so its ledger would have failed **open**. The sweep now also reaches any module whose
  `__file__` resolves inside the child's own working directory — the class "a module this
  example wrote", identified by where it is rather than by what the page calls it — and applies
  the unledgered leg to it too, so a written module keeping no ledger fails the example instead
  of reading as clean. No page cooperation is required and no page can evade it by how it
  spells the write. A mutation check confirms the clause is load-bearing: removed, a swallowed
  node call in the tutorial comes back clean.

  `your-first-ir` prints the whole document plus its six warnings and one record in full, so
  that `contract-inferred` is legible as a structured record — which pattern licensed which
  key (`state-access` for a literal read, `return-annotation-keys` for a `TypedDict` return),
  and the `claims_not_upgraded` list naming the slots inference never reaches.
  `knowability-classes` takes the same agent grown a little — a triage router that declares no
  targets, two searches that join, one node carrying a `@gebra.contract` — and demonstrates
  each of the four INTROSPECTION §0 classes from one extraction, with `barrier-flattened` and
  `unsupported-construct` beside them and the consequence a reader needs: a document carrying
  a `dynamic` edge stamps itself `ir_version: 1.1` and reaches **no verdict** from `verify` —
  gate `tool-error`, exit `2`, which is "no verdict", never "the workflow failed".

  The `checkpointer=False` blind spot (INTROSPECTION §4.1) is documented as an admonition
  rather than a footnote, because it is the one limitation on the page that a reader cannot
  detect for themselves: a subgraph compiled that way is invisible to subgraph discovery, so
  the recorded set of subgraph-bearing nodes is a **lower bound** and **no warning is possible
  for what was missed** — extraction cannot warn about what it cannot see, so the paragraph is
  the warning. It is separated from the unrelated scope line beside it: ir 1.0/1.1 carry a
  discovered subgraph as its parent node only, for every subgraph, visible or not.

  Four controls in `tests/docs/test_doc_examples.py` hold the new shape rather than trusting
  it: a fired ledger control per tutorial example (a node body called inside the real run, the
  raise swallowed, the sweep still reporting it); the same call made with an **empty state**,
  which is the accidental-invocation shape that finds a body arming itself too late — every
  body on the page therefore records on its first line, before a missing key can raise from a
  subscript; the fail-closed leg for a written module keeping no ledger; and a floor assertion
  that every example writing a module appears in the fired-control list, so the next page of
  this shape cannot land without one.

- **The concept page "The IR, node identity and graph_version"** (card DOC-03; IR-SPEC,
  DEC-10). `docs/concepts/ir-and-graph-version.md` is the second written page of the Concepts
  section, and the one a reader needs before a snapshot or a diff means anything: what the
  extracted document holds field by field, why `START`/`END` are not rows in `nodes[]` and a
  conditional edge is one edge per label, why the IR is hermetic and what that costs, how a
  node id is built and why a rename is a new identity rather than a moved one, and what a
  `graph_version` is a digest *of*. Labelled **spec-derived** at the top, in the form DOC-02
  established: the field set, the identity grammar, the canonicalization pipeline and the
  hash scope come from the frozen specification, every statement names the section it came
  from, and the page says plainly that those documents are internal contract documents not
  published with this site.

  The canonicalization detail is split by audience rather than averaged: the `graph_version`
  section gives a user the three facts that follow from the hash scope, and a subsection
  marked as contributor depth carries the pipeline a second implementation would have to
  reproduce byte for byte — the two normalizations, the array-sort rules, and why surface
  bytes are never hashed.

  Three examples run under the DOC-01 harness. `golden-vector-001` is the worked example the
  card asks for: **golden vector 001** itself — the specification's own pinned document —
  loaded, canonicalized and digested, printing the 537 canonical bytes, the digest, and the
  recompute-and-compare against the pinned value, with a walkthrough naming which rule
  produced each difference between the authored YAML and those bytes.
  `what-moves-a-graph-version` answers the question from the other side in one transcript:
  the same content authored with different habits and two snapshots taken months apart share
  one digest, while an extra effect tag and a prompt fingerprint each move it.
  `node-identity` shows the grammar working — path ids, `%2F` escaping, a synthetic LCEL
  segment beside the escaped `%25` form of a user who wrote that name literally, and the
  OpenInference attributes of IR-SPEC §5.4.

  Two of the acceptance boxes are held by machine rather than by review, in
  `tests/docs/test_ir_concept_page.py`. The worked example **is** the golden vector: its
  document literal is reconciled byte for byte against the committed
  `vector-001.authored.yaml`, the digest it checks itself against against
  `vector-001.digest`, and the canonical form and byte count in its transcript against
  `vector-001.canonical.json` — all three under `tests/ir/golden/`, so a
  golden-file event that skipped this page fails the build instead of leaving a stale
  transcript in the documentation. And where the specification set is checked out beside this
  repository, the hash-scope table is reconciled against DEC-10 **field for field in both
  directions**, so a field dropped, invented, or moved across the include/exclude line is
  caught; a companion check holds DEC-10 and its normative home in IR-SPEC §6.4 to each other,
  since the page cites both.

- **Brief D-12 is promoted from outline to a full in-repo contract, and its two contract
  specifications are stamped final** (card CLI-08; the F3 trigger is master plan §3's). The
  brief's own status note made promotion conditional on the D-08 IR models and the D-09
  result types freezing; both freezes were recorded on 2026-08-13 (IR-06, VAL-12), so the
  promotion has been eligible since and this change executes it. The record is
  `docs/governance/D-12-PROMOTION.md`, beside the two freeze records it cites.

  **Nothing in `src/` changes.** Promotion is a documentation and governance event: the five
  verbs, the report format, the diagram emitter and the exit codes are exactly what CLI-03…
  CLI-07 merged. What changes is that the documents describing them stop being amendable by
  Phase-0 cards. The record scopes that before claiming it — the vendored brief is not edited
  (WA-03/WA-11) and still reads OUTLINE; what "promoted" means here is the reading the plan
  itself fixed (a promotion record citing F3), and the record says so in as many words.

  **`CLI-SPEC.md`, `REPORT-FORMAT-SPEC.md` and `DIAGRAM-STYLE-GUIDE.md` are now FINAL**, each
  status block carrying the stamp, the date, the card and what final means: no Phase-0 card
  amends the contract further, and a later change needs its own card plus the document's own
  route — §1.6's bump table for the report format, a §7/§9 landing note for the other two.
  Editorial corrections and landing records are explicitly not amendments. **`report_format`
  is `1.1`, final** — the literal every producer and consumer in this repository already reads
  first.

  **Every open item in both Appendix Bs is closed or re-routed**, which is the obligation
  CLI-SPEC §7 wrote for this card, and each disposition lands in the item's own row as well as
  in the record, so the two cannot drift. Four are closed by the promotion (the two "stamped
  final at the promotion" items; CLI-SPEC's audit-export exposure, closed as a decision —
  the export is native JSON at `report_format` `1.1`, so a consumer reads it with no
  gebra-specific tooling and a sixth verb would widen the five-verb surface the brief fixes;
  and the `--call` UX question CLI-04 left for this card to weigh, **weighed and declined**,
  because any route that called a zero-argument attribute *because it looks like a factory*
  would make executing user code implicit — the one thing `--call`'s opt-in exists to
  prevent). `display`'s missing live-target mode is closed as a Phase-0 decision with the
  capability re-routed, on the structural ground that it would pull CLI-SPEC §0.5's tripwire
  obligation with it. The rest are re-routed to Phase-1 with their owners named, and the
  already-closed items are reaffirmed rather than reopened.

  **REPORT-FORMAT-SPEC §1.6 gained the bump rows open item OI-7 commissioned** for this card.
  The unrowed class — a documented member's *value rule* changing while the model is untouched
  — is split by direction: widening, or the same value coming to mean something else, is
  **MINOR** (the model parses either way, so the break is a misreading rather than a parse
  error); narrowing, or merely being made precise, is **none**, with the 2026-08-05
  `subject.source` correction recorded as the worked example. A value-rule change that also
  moves exit-code derivation, the finding set or strict reach stays MAJOR by the row that
  already existed. Adding the rows is not itself a bump: they classify future changes without
  making one.

  **`docs/specs/EXTENSION-SPEC.md` is the brief's last artifact-table row**, at the outline
  depth the brief asks for and no deeper: the rulings that already bind an eventual thin VS
  Code lens (D-028 clause (ii), DEC-26's thin-client-over-CLI wording, read-only, Apache-2.0,
  P2/Phase-1), the five constraints that make it thin, the six CLI surfaces it would wrap —
  all of which exist and are now contract-fixed — and eight questions a Phase-1 contract must
  settle, named and deliberately not answered. **No extension is built, designed or scheduled
  in Phase-0**, and the document opens by saying so; it lives in the repository-internal
  `docs/specs/` tree that `mkdocs.yml` excludes from the user documentation site, so no site
  reader meets a page describing an editor that does not exist (WA-12).

  Both new documents are pinned by tests rather than trusted as prose: `tests/docs/test_d12_promotion.py`
  checks that every repository path the record cites exists, that the two freeze records still
  name this card back, that each document the artifact table calls final actually carries a
  final stamp naming CLI-08, that the `1.1` the record stamps is the `1.1` the spec fixes, and
  that **every** Appendix B item is dispositioned **in both directions** — an item the specs
  carry and the record forgets is a dropped obligation, and one the record invents is a
  disposition of nothing. `tests/docs/test_extension_spec.py` holds the outline to being an
  outline: the opening denial, the P2/Phase-1 status, the absence of any extension source
  tree, the site exclusion (an edit that un-excluded `docs/specs/` turns the outline into a
  published promise and fails here), and that §3 names only verbs CLI-SPEC actually fixes.

- **The README is a working front page: an honest status table, install instructions, and a
  quickstart CI executes against the shipped wheel** (card DOC-04; SOW §1/§5/§6, D-028 via
  `docs/LICENSING.md`). The page now opens with what gebra is and the boundary it keeps,
  then a **status table** whose twelve rows each carry one of four states — `available`,
  `in development`, `out of scope for this phase`, `not in this repository` — and nothing
  claims `available` that this repository cannot answer for: `tests/docs/test_readme.py`
  gives every row a probe (the extractor's object families, the IR digest pipeline over a
  real document, the annotation surface, five implemented validators *and* eight
  not-implemented markers, the `pytest11` entry point beside the CI-gate action, the store
  and diff modules, the five registered CLI verbs) and, where the development-process
  repository is checked out beside this one, reconciles each row against the plan cards
  that produce it **in both directions** — a row may not claim more than the boards have
  delivered, nor stay behind them once they have.

  **Install instructions do not predate the wheel path.** Nothing is published, so the page
  says so and installs from a checkout; a test derives that premise from the declared
  version rather than asserting it, and refuses any index install while the version is a
  pre-release — so the day a final version is declared, the test's premise fails first and
  the install section is what has to be revisited. The **open-core statement** (D-028
  clauses (i), (iii), (v)) is present, and its wording is reconciled against
  `docs/LICENSING.md` where that record is available. Every relative link is checked to
  resolve, and no link may point at a page still carrying the DOC-01 placeholder marker
  (WA-12); the two badges that carry facts — the declared version and the tested Python
  range — are checked against `pyproject.toml`.

  **The quickstart is executed, not illustrated.** `tools/readme_quickstart.py` is a second
  documentation harness, disjoint from DOC-01's: the README marks its steps with
  `<!-- gebra-quickstart:file path=… -->` and `<!-- gebra-quickstart:console id=… exit=N -->`,
  and the harness writes the files, runs each command — split with `shlex`, leading
  `NAME=value` assignments applied, anything a shell would interpret refused rather than
  approximated — and holds its merged terminal output and exit status to the transcript the
  page shows, with a lone `...` line marking omitted output and every shown run required to
  appear contiguously and in order. The new `readme-quickstart` CI job runs it against **a
  fresh virtual environment holding only the wheel `uv build` produced** — no editable
  checkout, no dev extra, no lockfile — so a quickstart that only worked inside the
  repository fails there. Under WA-07 the harness generates a `sitecustomize.py` into that
  environment's `PYTHONPATH`, arming twelve socket entry points — connecting *and* the
  connectionless send/resolve routes a UDP query or a telemetry emitter would take —
  `StateGraph.compile`, and the whole `Runnable` invoke/stream/batch family (`BaseChatModel`
  included, so a stubbed model is unrunnable on its own account), recording each attempt
  before raising. The sweep is fail-closed in both directions: *every* command must leave the
  complete armed manifest behind unless its directive says `python=no`, and a family the
  guard could not arm is reported as a hole rather than passed over. A command may not set
  `PATH` (it would leave the environment under test) and a step may not write
  `sitecustomize.py` (it would take the guard's own slot); the guard directory goes first on
  `PYTHONPATH` so it cannot be shadowed either way.

  **The documentation harness now sweeps an example's own module.** A page may build the
  graph it shows rather than import a sample workflow — the README does, because a README a
  reader cannot reproduce is not one — and extraction unwraps a node to the bare callable, so
  the armed `invoke` family never sees a call on such a body. Pages that define a graph
  therefore arm their own node bodies (record into `TRIPPED`, then raise), and
  `tools/docs_examples.py`'s trailer sweeps `__main__` beside `tests/sample_workflows/` so a
  call a `try` block swallowed is still reported. Two tests hold the rule: one refuses an
  example that registers a node it defined without keeping a ledger, and one fires the
  README example's own body inside a swallowing `try` and requires the sweep to name it.

- **The compatibility posture is finalized — the tested matrix is frozen (F2)** (card
  GOV-08; VERSION-COMPAT §1/§4/§5, gate G7). The `compat-cell-{1,2,3}`/`compat-test`
  extras' substrate pins are frozen citing green drift-suite CI run 33336160085 — the
  CANDIDATE marker they carried since GOV-04 is gone — and the freeze-time pin lock
  closes the fresh-resolution exposure the G6 sign-off recorded: every pip-installing CI
  job (the 12 matrix cells, the DoD job, `pip-editable`, `docs`, and the `--pre` cell's
  dev half) now resolves under the new `tools/matrix-constraints.txt`, generated from
  the committed `uv.lock` by `tools/matrix_constraints.py` (`--check` runs as a test in
  every cell and refuses a lock/constraints skew; `--write` regenerates). The
  constraints are agreement-gated: distributions the cells pin divergently are never
  constrained — the extras remain the substrate's single source of truth — while family
  members every cell pins identically (pydantic, langchain-protocol today) are held to
  exactly that agreed version. The `--pre` cell's substrate resolve still reads the
  day's index (that early warning is the point of the cell, and its red now attributes
  to the substrate rather than to a dev tool — at the recorded cost that a prerelease
  *transitive* under stable named packages, the PD-030 §C4 arrival mode, now reaches
  the cell only via a named-package upgrade), and the build job's clean-venv wheel
  smoke stays a user-shaped fresh install by design.

  **The WA-05 golden-lifecycle guard is CI-enforced**, ending the review-only interim:
  the new `golden-guard` job (`tools/golden_guard.py`, stdlib-only, no bypass flag)
  fails any commit whose diff touches `tests/extraction/golden/`,
  `tests/version_drift/golden/` or `tests/ir/golden/` without a well-formed
  `Golden-Justification:` trailer carrying one of WA-05's two justification kinds
  (`drift-run=<run id>` or `DEC-<n> ir_version=<x.y>`) — judged per commit, with merge
  commits held to their combined diff so a merge resolution cannot smuggle a golden
  change past the constituent commits' trailers.

  **The post-phase watch is wired**: CI now also runs weekly (`schedule`) and on demand
  (`workflow_dispatch`), so the matrix, the `--pre` early-warning cell and the
  drift-issue automation keep observing the index when pushes stop arriving. The
  operating procedures — triage, ceiling extension, cap, the 2.0 watch, pin-lock
  maintenance — are the new `docs/governance/VERSION-COMPAT-RUNBOOK.md`.

- **The tag-triggered release workflow** (card GOV-03; SOW §5, the PD-036/GOV-D4
  destination ruling). Pushing a `v*` tag now produces built and validated distributions
  with no manual assembly: `.github/workflows/release.yml` gates the tag through the new
  `tools/release_gate.py` (stdlib-only, tested), builds wheel + sdist from the tagged
  commit (`uv build`), validates metadata (`twine check --strict`), verifies the artifacts
  are exactly one wheel + one sdist named for exactly the gated version, re-checks
  `py.typed`, installs the wheel into a clean environment against the gated version, and
  uploads the artifacts and extracted release notes to the run (90-day retention).

  The gate is the release policy held mechanically: tags parse inside a three-shape
  grammar — `vX.Y.Z.devN` dev cuts, `vX.Y.ZaN`/`vX.Y.ZbN`/`vX.Y.ZrcN` candidates, bare
  `vX.Y.Z` final — and must equal `v` + `[project].version` byte for byte; a final tag
  additionally requires its dated changelog section, whose body ships as the run's notes
  (dev/rc cuts ship `## [Unreleased]`). The publish leg (`publish-pypi`) targets PyPI via
  trusted publishing — OIDC under the `pypi` deployment environment with `id-token: write`
  and no stored credential of any kind, a fact `tests/test_release_wiring.py` pins along
  with the rest of the wiring — and is triple-gated to the launch: the gate emits
  `publish=true` only for the final form (which no Phase-0 tag carries), the ref must be a
  tag, and the event must be the tag push itself, so during Phase-0 every run stops at
  built-and-validated artifacts (PD-036) and a `workflow_dispatch` rehearsal can never
  publish, whatever ref it is issued on. CI's `build` job now runs the gate in
  dry-run mode plus the same pinned `twine check --strict` on every push, so the tree
  stays release-ready between cuts. Procedure documented in CONTRIBUTING.md ("Releases").

- **The concept page "What gebra checks"** (card DOC-02; PROPERTY-CATALOG-SPEC §0.1/§0.2,
  SOW §6). `docs/concepts/what-gebra-checks.md` is the first written page of the Concepts
  section: what the object under test is, the three claim classes, the severity ladder and
  what each grade does to the gate, the exit codes `0`/`1`/`2`, strict mode in both its bare
  and per-property forms, the five properties this release implements, and — the section the
  page exists for — what a finding does *and does not* claim. It is labelled **spec-derived**
  at the top: the claim-class, severity and exit-code tables are transcribed from the frozen
  specification rather than paraphrased, every statement names the section it came from, and
  the page says plainly that the specification set is an internal contract document that is
  not published with this site, so a reader knows what the section numbers are for.

  Two of its claims are not transcribed but executed. `severity-and-the-gate` verifies the
  five seeded-defect variants of the travel-booking agent and prints, for each, the finding's
  condition ID, severity and claim class beside the gate that follows from it — all three
  severities and all three claim classes in one transcript, with the two FATAL rows leaving
  the run ineligible for a snapshot, the two ERROR rows failing the gate while staying
  eligible for one, and the WARNING row passing with notes at exit `0`.
  `strict-changes-the-gate` runs that WARNING case twice, default and
  `--gebra-strict=determinism-replay`, to show the exit code moving from `0` to `1` while the
  record stays `severity: warning`, `claim_class: heuristic` — promotion changes the gate,
  never the record. Both run under the DOC-01 harness, so the transcripts are what the code
  printed rather than what the prose asserts.

  Two of the tables are held to the specification by machine rather than by review.
  `tests/docs/test_docs_site.py` reconciles the claim-class, severity and exit-code tables
  against the vendored property catalog **cell for cell** where the specification repository
  is checked out beside this one, with the single divergence — a pointer to a vault note no
  reader of this site can follow — declared as a named omission whose text is itself asserted
  against the spec, so a stale exemption cannot quietly license a real drift. A paraphrase
  that softened "Advisory lint; no proof claim." to "Advisory lint." fails the check.

  The page's examples import the seeded-defect module, so `tests/sample_workflows/
  travel_booking_defects.py` now binds `TRIPPED` under its own name — the *same list object*
  its bodies already record into, not a second ledger. Without it the harness's fail-closed
  sweep reads that module as keeping no ledger and refuses the example, which is the correct
  refusal: a sweep cannot tell "records elsewhere" from "records nowhere". A third
  parametrised control fires a defect twin's body inside a real example run and asserts the
  sweep reports it under this module's name, so the new leg is a tripwire that has been
  tripped rather than one that has only been added, and a second test pins the re-export to
  the *identity* of the family ledger — a rebinding rather than an in-place clear would leave
  the sweep reading a list nothing writes to, which is the silent vacuity it exists to
  refuse. `tests/docs/test_docs_site.py` also gained the landed-page bookkeeping the skeleton
  needs as pages get written: a page moves out of the placeholder set in the same change that
  drops its marker, checked in both directions.

- **The documentation site and the executable-examples harness** (card DOC-01; SOW §7,
  WA-07/WA-12). `mkdocs.yml` builds the user documentation from `docs/`, and a new `docs`
  CI job runs `mkdocs build --strict` — nav omissions, links resolving to nothing and
  missing anchors are failures, so the skeleton cannot rot quietly. The site is the six
  sections a reader navigates (Concepts, Tutorials, Validators, Guides, Reference,
  Contributing) with a page reserved for every planned one; all but two are **placeholders**
  that say so, describe no behaviour, and carry a machine-readable marker. The
  repository-internal contract documents that share the `docs/` tree — `docs/specs/`,
  `docs/governance/`, `docs/ci/` — are excluded from the site by name and are neither
  published nor shadowed by it; `tests/docs/test_docs_site.py` holds the exclusion list
  equal to the trees on disk in both directions. The toolchain is one pinned distribution in
  `docs/requirements.txt` rather than a project extra, so it stays out of `uv.lock` and out
  of all thirteen compatibility cells.

  The second half is `tools/docs_examples.py`, through which every later page's examples
  execute: a page marks a fenced block with `<!-- gebra:example id=… -->` (and, optionally,
  `<!-- gebra:output id=… -->`), and the harness runs *those bytes* in a child interpreter
  and holds the printed output to what the page shows. There is no second copy of the code
  to drift from the prose, and no "runs without error" mode — an example declaring no output
  must print nothing, so every example's stdout is pinned. Malformed markup is an error
  rather than a skip, because a typo that silently removed an example from CI would leave
  "examples executed verbatim" enforcing nothing. WA-07 is per example and has no
  per-page opt-out: name resolution and connecting raise from the child's first line,
  `StateGraph.compile` and every `Runnable.invoke`/`stream`/`batch` in the class tree raise
  before the page's code runs (compiling is not the only route to running something), socket
  construction raises once the page's own code begins, and the sample graphs' node bodies
  record the call in their module ledger before raising, so a swallowed sentinel still
  fails. That sweep is fail-closed — a sample workflow keeping no ledger is reported as
  unledgered and fails the example, because "nothing was recorded" must not read the same as
  "nothing ran"; `tests/sample_workflows/sentinel_graph.py` gained the ledger its family had
  been missing, recorded by `SentinelExecutedError` itself so every raise site in it and in
  the five modules reusing that class is covered at once. The child inherits an environment
  allowlist rather than the parent's, so a provider key or a tracing switch never reaches an
  example, and it reports its attempt list, ledger and unledgered set — any of the three
  non-empty fails the example. Every raiser is fired by a control
  probe inside the run that made the claim. Examples run from a temporary working directory,
  so one that writes a `.gebra/` store leaves the tree untouched. Both surfaces are wired:
  each discovered example is its own pytest item (so they run in every cell), and the `docs`
  job runs `python tools/docs_examples.py --report` as the counted report. The demonstration
  is `docs/contributing/executable-examples.md` — extract → verify → snapshot over the
  sentinel graph, executed and output-pinned like any other example.

- **The coverage gate** (card TE-12; briefs D-09 Deliverable 6 / D-10 Deliverable 8,
  SOW §2's supporting acceptance facts). `tools/coverage_gate.py` holds three surfaces
  — `gebra.verify`, `gebra.testing` and the pytest plugin — each **strictly above 80%**,
  aggregated per scope rather than as one project total, so a thin surface can no longer
  hide behind a healthy package average. CI runs it in the `test-locked` job after the
  suite; a scope at or below the floor exits 1 naming the scope and its mandate, and a
  report the gate cannot score honestly (missing, unreadable, measured without branch
  coverage, or matching no file for a scope) exits 2 rather than passing vacuously. There
  is no threshold flag and no bypass. The measurement mode changed with it, and the change
  is load-bearing: the job now measures with `coverage run -m pytest` instead of `pytest
  --cov`, because the plugin is a `pytest11` entry point whose module body runs during
  plugin loading — before pytest-cov starts — which recorded 161 module-level statements
  as never executed and cost the plugin scope 18.9 points of purely artificial miss.
  The gate detects a report measured the old way and refuses it instead of reporting the
  artifact as a regression. Exemptions are now policy rather than convention: structural
  exclusions stay in `[tool.coverage.report] exclude_also`, and a per-line `# pragma: no
  cover` inside a gated scope must carry its reason on the same line or the gate rejects
  it — the discipline the honest-claims lint already applies to its allow-pragma. The
  pragma is recognised by coverage.py's own default pattern rather than by one spelling, so
  every form coverage.py honours (`# pragma:no cover`, `# PRAGMA: NO COVER`) needs a reason
  too, and a machine directive trailing the pragma (`# noqa: …`) does not count as one. The
  policy, the local reproduction recipe and the honest boundary ("a floor under the test
  suite's reach, not a statement about the code's behaviour") are in
  `docs/governance/coverage-gate.md`, with CONTRIBUTING pointing at it. The job's coverage
  artifact is now `coverage-reports` (both `coverage.xml` and the `coverage.json` the gate
  reads); no dependency was added — `coverage` already came with the `dev` extra.

- **The CI-gate GitHub Action** (card TE-13; brief D-10 In-Scope 6/W12). A reusable
  composite action, `.github/actions/gebra-gate`, wraps the pytest plugin as a CI
  gate: one pytest invocation built from typed inputs (`tests`, `select`, `skip`,
  `pytest-args`), the `report-only` → `gate` → `strict` rollout ladder as a one-word
  `mode` switch (strict in both its bare and per-property forms via
  `strict-properties`), the run's closing `gebra` section appended to the step
  summary, one workflow annotation per run, and two step outputs (`exit-code`,
  `outcome`). The exit translation is deliberately asymmetric: `report-only` forgives
  test failures and nothing else — an interrupted, erroring, or empty run is red under
  every mode, so a gate that checked nothing can never pass. The composite is fully
  local (no `uses:` steps; a stdlib-only typed driver, `gate.py`, receives inputs as
  environment variables, so no input value is ever spliced into shell text — both
  posture points test-pinned), and the plugin stays the single authority over
  property-slug vocabulary: an unknown slug is the plugin's own configure-time
  refusal, surfaced as `outcome: error`. The repository's own DoD scenario job now
  issues its one pytest invocation through the action in default `gate` mode — the
  executed reference consumer, with the effective command unchanged. Rollout guidance
  for adopters is `docs/ci/github-action.md`, pinned to the action's manifest and to
  the workflow's own step by `tests/action/`.

- **The DEC-16 gap-fixture extension: the vendored corpus grows 60 → 71** (card TE-14;
  DEC-16/PD-013 authorization; vault `Gebra-Tech/initial-documents@e6ea366`, re-vendored
  with the provenance manifest and PROVENANCE rows in the same landing). Eleven
  R-05-authorized fixtures close the wedge-five coverage gaps the frozen catalog names in
  its own words, each matching its registered validator by §0.3 model equality on arrival:
  the P-08 top-up to the ≥3 pass + ≥3 fail house minimum (the §8.7 vacuous pass with empty
  `claims` and no caveat; the tutorial-§7 `{seed}`-object-with-`temperature`-absent shape),
  the P-01 condition-(iii) orphan negative under DEC-11's Reading A (primary plus its two
  intrinsic same-property cascades), the P-04 cycle-entry pair pinning the A8 T3
  SCC-collapse boundary (entry-at-writer passes, entry-at-reader fails with both
  DEC-11-kept diagnostics naming the in-cycle writer), the P-02 quartet (the unwitnessed
  self-loop exercising the surviving-self-loop SCC branch; the (b)-only pass whose
  WARNING-grade `scc-covered-only-by-recursion-limit` note, `blanket_only: true` location
  and blanket-path certificate the fidelity matrix had recorded as predictions — now the
  strict witness-note promotion's first corpus subject; the 20-cycle census-cap overflow
  carrying the corpus's first `variant` declaration and the bare `cycle-census-capped`
  note; the acyclic empty-inventory vacuous pass), and the two P-06 negatives DEC-13 left
  open (the corpus's first `retry_policy` declaration — a retry region with no cycle and
  no anchor — and the dangling compensation hook recorded through the
  `dangling_compensation_hook` evidence field, registry unchanged). Corpus counts, floors
  (`CORPUS_FLOOR` 71, per-directory `DIRECTORY_MINIMUMS`, `MIN_FIXTURES`), the fidelity
  matrix §5 cells and prose, the DEC-17 audit's V-10/V-13 verifications, the §3
  guard-recognizer tables (55 corpus guards, 12 recognized, the first R1-rejected
  ternaries) and every corpus-count pin across the suite move with it. Two catalog-named
  cases remain the recorded DEC-16 deferrals, not silently omitted: P-02's
  `recursion-limit-without-justification` note-only case and P-08's `deterministic: false`
  explicit disclaimer.

- **The CLI integration suite, and the render sign-off it records** (card CLI-07;
  CLI-SPEC §7; brief D-12's "subprocess tests against the fixture corpus" row). The five
  verbs are now exercised at the process boundary: `tests/cli/test_integration_flow.py`
  drives the SD-08 travel-booking evolution through real child processes of the shipped
  entry points — `verify` over the live definition and a stored version, the six clean
  stages recording under SD-08's own labels, the witness-removal stage's §0.2 FATAL
  refusal, stored-span and stored-versus-live diffs with their S/F/E classes, `history`
  over the live store with `--format json` byte-equal to the engine's `dump_lineage`, and
  `display` plain and overlaid with a report the flow's own `verify --output` wrote — with
  nine byte-compared goldens (`tool.version` normalized and nothing else);
  `tests/cli/test_integration_matrix.py` re-observes the §3.2 exit-code table per verb
  (at least one exit-2 per reachable §2.6 stage, the registry-dependent `dispatch` row in
  process by stated decision), the §3.3 strict forms, §3.5 format invariance, Appendix-A
  blank-cell refusals, §5.1 styled/plain equality on a real pipe, and the console script
  answering byte-identically to `python -m gebra.cli`;
  `tests/cli/test_integration_corpus.py` holds CLI-SPEC §0.1's presentation-only boundary
  as an equality over every corpus IR (exit code and JSON artifact equal to the library's
  own run, a SARIF representative per corpus directory schema-validated), and every stream
  the suite captures is swept against the TE-15 banned-phrase list. The "every
  witness/failure variant renders cleanly" sign-off owed to the VAL track is recorded as
  `docs/governance/RENDER-SIGNOFF.md` — the record VALIDATOR-API-FREEZE.md §3 defers to
  CLI-07 by name — pinned to its cited evidence by `tests/docs/test_render_signoff.py`.
- **The Phase-0 DoD scenario — five seeded defects, the end-to-end harness, and its
  dedicated CI job** (card SD-09; SOW §2 criterion 1; PD-006 R1/R2/R5; PD-047 mitigation).
  Five builder-level seeded-defect variants of the travel-booking agent
  (`tests/sample_workflows/travel_booking_defects.py`) with their expectations recorded
  beside them: a witness-stripped booking cycle (P-02 FATAL
  `cycle-without-termination-witness` on the five-node SCC), an unprotected
  irreversible/billable `book_flight` inside the structural retry region (P-06 ERROR
  `unprotected-effect-in-retry-region`), a seed-only determinism claim on the LLM-backed
  classifier (P-08 WARNING `deterministic-llm-temperature-unpinned`, gated exit 1 under the
  `determinism-replay` per-property promotion while the record stays warning/heuristic), an
  `express` label that skips both bookings (P-04 FATAL `read-key-never-written-on-path` at
  `(notify_traveler, itinerary)`), and a live `Send` fan-out whose billable worker is
  unprotected in the send-extended retry region (P-06 ERROR with `fanout: send` evidence —
  the mixed/09 reference pattern as a live graph, RATIFIED conditions only). `tests/dod/`
  runs the whole PD-006 R5 scenario — extract → verify → snapshot → evolve → diff → report
  — over one store: the healthy agent clean through the pytest plugin, every catch asserted
  by property + condition ID + locus + gate and negative-tested (the checker refuses a
  report the defect is absent from, and defects 2/5 are held to distinct loci), the
  evolution sequence recorded through the measured eligibility boundary, per-version audit
  exports conforming to the §6 snapshot profile, and — the PD-047 mitigation, documented in
  `docs/governance/DOD-SCENARIO.md` — a `reports/lineage.json` lineage document written
  beside the per-version reports, so the store's audit files answer "what changed" without
  a `gebra` installation. The dedicated `dod` CI job runs `pytest tests/dod
  tests/evolution` on the designated blocking cell (py3.13 / cell 3) with
  `timeout-minutes: 5` — the R5 budget made enforcing — and the suite reports the
  non-gating "gebra-work seconds" sub-metric per leg in the job's step summary.
- **`gebra display` — the fifth CLI verb, with its style contract** (card CLI-06;
  CLI-SPEC §4.4; PD-034). `gebra display <ir.yaml | V.S.F.E label>` renders a workflow
  definition as Mermaid text, emitted **directly from the IR** by the new `gebra.display`
  package (PD-034's ratified strategy: no `get_graph()`/`draw_mermaid()` dependency
  anywhere on the path) — the sentinel-augmented, label-expanded multigraph the validators
  anchor findings to, with unresolved references drawn as dashed phantom vertices rather
  than silently dropped. `--report run.json` (a `gebra verify --format json` artifact)
  paints the report's findings onto the drawing: severity-colored node fills and edge
  strokes, `[Fn]` markers, and a rendered legend carrying each finding's severity, claim
  class, condition ID and REPORT-FORMAT-SPEC §4.5 anchor phrase — accepted only after the
  §1.6 `report_format`-first read and the §4.4 provenance check (the report's recorded
  `subject.graph_version` must equal the displayed IR's own digest). The rules the diagram
  follows are `docs/specs/DIAGRAM-STYLE-GUIDE.md`, a new repo-authored contract artifact
  (the brief D-12 deliverable resolving OQ-12-02's overlay design), machine-pinned to the
  emitter by `tests/docs/test_diagram_style_guide.py`; emissions are parse-checked against
  the guide's licensed Mermaid subset by the new `tools/mermaid_check.py` across the whole
  corpus (60 fixtures, 67 IRs, plain and overlaid). `display` has no live-target mode: an
  import-shaped target is a usage error refused before any import happens (CLI-SPEC §4.4,
  OI-5), held in the never-invokes suite on `sys.modules` itself and in the
  substrate-blocked guarded child. An `ir_version` 1.1 `dynamic`-bearing document is
  declined exactly as `verify()` declines it — the diagram representation of a headless
  router edge lands with the kind's consumer-side semantics, not by improvisation.
- **The travel-booking evolution scenario — brief D-11's W9 sequence as a regression suite**
  (card SD-08; PD-006 R4 / PHASE-0-DOD-CHECKLIST §S2; SOW §2 criterion 1 context). Eight
  builder-level versions of the TE-05 travel-booking agent
  (`tests/sample_workflows/travel_booking_evolution.py`) covering D-11's three
  safe-extension shapes — a new optional Σ key, a new wired contracted node, a new guarded
  edge — and the three canonical breaking cases, with the read-key case in both spellings:
  removal *and* retype, termination-witness removal (the form-(c) `variant` carrier), and
  effect-class escalation into the P-06 trigger set. The expected V.S.F.E label and bump
  class per stage are recorded beside the builders (`EVOLUTION`), and `tests/evolution/`
  holds the engines to that record: recording the sequence assigns exactly the expected
  labels with byte-identical stores across independent runs; every one of the twenty-eight
  version pairs derives exactly the expected S/F/E classes in both directions, the
  deferred-P-12 marker on every diff and each step's delta content pinned by name (which
  key, which node, which slot); every snapshot reloads to the IR it was made from; and the
  eligibility boundary SD-09's DoD pipeline inherits is measured rather than assumed —
  v1–v6 verify clean and snapshot-eligible (P-04 skips a read of a key outside Σ, whose
  membership is the non-wedge P-03's finding, so the read-key pairs are graded only by
  the deferred P-12's structural classes), while v7–v8 carry the catalog's FATAL
  `cycle-without-termination-witness`, so the sequence stores all eight only through the
  recorder's documented handed-none-records posture. Classification is structural
  S/F/E only throughout; no output makes a safe/breaking claim (SOW §8; PD-006 R4).
- **Version-gap issue automation — the drift suite's failure handling wired end to end**
  (card GOV-07; VERSION-COMPAT §3–§4; SOW §2 criterion 4). Every matrix cell now writes
  a machine-readable drift report at the end of its pytest run
  (`tests/version_drift/conftest.py`, when CI sets `GEBRA_DRIFT_REPORT_FILE`): one
  context line naming the cell, Python and substrate pair, one stable
  `DRIFT-HARD-FAILURE` line per failed or errored drift test — now also emitted as a
  terminal section and, under Actions, an `::error` annotation each — plus the existing
  soft-divergence and review-proposal lines verbatim. Each cell uploads its report, and
  the new `drift-issues` CI job aggregates all thirteen once the matrix finishes,
  driving `tools/drift_issues.py` (new; stdlib-only): at most one open *version-gap*
  issue per frozen substrate cell — a hard failure blocks its cell AND lands in the
  issue, a soft-only divergence keeps its cell green and still lands in the issue — and
  the `--pre` cell's signals (or its red pytest gate, recorded in the artifact) open a
  *supported-range-review* issue instead, carrying the §5 R-06 routing. Issues dedup by
  a fingerprint marker: unchanged signals add nothing on later runs, changed signals
  land as comments, and an automation failure turns the job red rather than passing
  silently. A dry run (`--reports` without `--apply`) prints every payload offline; the
  tests drive the API flows through fake transports only (WA-07). The owner-triggered
  `drift-issue-drill` workflow demonstrates the live chain on demand — one golden byte
  flipped in the runner's checkout, the suite goes red, and real `[drill]`-labeled
  issues open from the real report (safe to close after inspection).
- **The three store-facing CLI verbs: `gebra snapshot`, `gebra diff`, `gebra history`**
  (card CLI-05; CLI-SPEC §4.2, §4.3, §4.5; PD-033). Four of the five verbs now exist —
  `display` remains CLI-06's. `gebra snapshot` records a V.S.F.E-versioned snapshot of an
  IR document or an import reference: one resolution serves both the eligibility
  `verify()` run and the write, PROPERTY-CATALOG-SPEC §0.2's recording rule is applied by
  the SD-03 engine off `gate.snapshot_eligible` (exit `1` with the FATAL findings rendered
  when it refuses; no bypass flag exists), an unchanged definition is a stated no-op at
  the label the store already holds, and `--quiet` writes the recorded label or nothing.
  `gebra diff BEFORE AFTER` renders the structural delta exactly as the engine returns
  it — both anchors (a stored side keeps its V.S.F.E label), the topology/contract/state
  deltas with contract values in canonical JSON, the `regrouped` flag, and the S/F/E bump
  class — with the deferred-P-12 marker rendered as *not checked* on every outcome: no
  diff is labelled safe or breaking, and `--exit-code` is an opt-in difference signal
  carrying no such claim. `gebra history` lists a store as PD-033's oldest-first table
  (index, version, digest prefix, created-at, a current-pointer marker, and a per-row
  step summary with an explicit `n/a` and a distinct marker for a counter that
  decreased); `--since`/`--until`/`--limit` pass through to `gebra.lineage.lineage`
  unchanged, `--reverse` is display-only, and `--format json` writes `dump_lineage`'s
  byte-stable projection verbatim. Never-invokes tripwires for the two new live-target
  paths (snapshot; diff with an import-reference side, the mixed case included) land in
  the same change, and every subcommand is golden-tested against a prepared store.
- **`gebra.snapshot.record_document`** (same card): the recording policy over a
  serialized IR document — the `gebra snapshot --ir` path, which has no extraction
  envelope to hand `record()`. Same label policy, same §0.2 eligibility application, same
  ir 1.1 decline; the provenance states what a document recording honestly knows (the
  caller's reference, the recording build's version, no sidecar).

- **The version-drift suite completed: tests 7–12** (card GOV-06; VERSION-COMPAT §3).
  `tests/version_drift/` now carries the full twelve-test §3 inventory. The six new tests
  cover the jsonschema getters (named-key document golden beside the core-IR golden; the
  full rendered dict is the row's designated *soft* half, recorded per release line), the
  `context_schema`/`config_schema` constructor surface (the legacy spelling must still
  deprecation-warn and auto-route — both spellings are held to one golden), the per-key
  channel objects behind Σ (`BinaryOperatorAggregate`/`LastValue` classes,
  `ValueType`/`UpdateType`, the recorded member sets), the 1.2-era additive `add_node`
  kwargs (`timeout=`/`error_handler=` round-trip into the node spec and
  `node_error_handler_map` on the line that has them, with the pre-1.2 fields held
  undisturbed against a cross-cell plain-twin golden; the 1.0/1.1 builders *swallow* both
  kwargs, so presence-gating — never try/except — decides which arm runs), LCEL fragment
  identity (drawn names + topology as a document golden, raw uuid-per-call ids asserted
  disjoint across draws and absent from the extracted ledger-§5 synthetic ids, double
  extraction byte-identical), and the compiled P-13 carriers (`runtime.interrupts` /
  `runtime.checkpointer` against a golden — the one registry fixture handed to
  `extract()` compiled). Special §3 semantics land with them: the row-9 DeltaChannel
  variant is `xfail(strict=False)` on every cell (beta never blocks; the marker itself is
  integrity-tested), and the row-4/row-8 failure branches now **block and route**: a
  drawable-only divergence records a templated `get-graph-demotion` review proposal, an
  observed `config_schema` removal records the 2.0-ceiling `major-version-review`
  proposal — recorded (with its optional `GEBRA_DRIFT_REVIEW_DIR` file drop and
  run-summary append) *before* the blocking assertion fires, then emitted at end of run as
  a terminal-summary section, a stable `DRIFT-REVIEW-PROPOSAL` line (the version-gap
  automation seam) and a CI annotation; both branches are dry-run-proven by driving the
  real tests to failure in
  `tests/version_drift/test_review.py`. `tools/drift_goldens.py` gains the two new
  document goldens; `tests/substrate.py` gains the `HAS_NODE_TIMEOUT` and
  `HAS_DELTA_CHANNEL` predicates. Verified locally on all three substrate cells across
  four CPython versions (seven combinations), goldens byte-identical on every run.

- **The version-drift suite, tests 1–6** (card GOV-05; VERSION-COMPAT §3). A new
  `tests/version_drift/` package runs the first six drift-detection conformance tests on
  every compatibility-matrix cell (it rides `pytest`, so all 13 cells exercise it against
  their own pinned substrates). Each test carries the §3 row's three parts: hard
  surface-shape preconditions asserted directly on the substrate (`StateNodeSpec` field
  floor, `BranchSpec` path/ends shape, `edges`/`waiting_edges` join classification, the
  `get_graph(xray=True)` drawing, `Send.node`/`.arg`, the six `RetryPolicy` fields), a hard
  golden compare of the extracted core IR (canonical bytes byte-identical + `graph_version`
  string-equal against `tests/version_drift/golden/`, taken at the locked substrate and
  required to hold byte-identically on every frozen cell — verified locally on all three
  substrate cells across four CPython versions), and a paired soft exact-set assertion
  against per-release-line surface inventories (`tests/version_drift/inventory.py`) — a
  soft-only divergence keeps the cell green and is emitted as a CI `::warning` annotation
  plus a stable machine-readable `DRIFT-SOFT-DIVERGENCE` line at the end of the run, never
  only a log entry. Test 4 additionally pins the drawable graph (node/edge counts +
  per-edge conditional flags, ledger-§5 path-id keyed) and holds it equal to the
  builder-derived IR modulo the per-level `__start__`/`__end__` pseudo-nodes and the xray
  subgraph expansion. Goldens follow the WA-05 lifecycle (`golden/README.md`); regenerate
  with the new `tools/drift_goldens.py --check|--write`, which double-takes every case and
  refuses to pin an unstable extraction. No drift fixture carries a chat model, a `bind()`
  wrapper, or a langgraph-1.2-only builder API — the composition rule that lets one byte
  golden hold across the whole matrix.

- **The `gebra` command line, with its first verb: `gebra verify`** (card CLI-04; CLI-SPEC
  §4.1). The package now declares one console script — `gebra = "gebra.cli:main"`, on `typer`
  per brief D-12, with `python -m gebra.cli` naming the same function — carrying the
  application level (`--version`, `--help`, exit-code discipline: usage errors `2`, SIGINT
  `130`, a crash `2` with the traceback and an invitation to file it, never a clean run) and
  the `verify` verb over all three CLI-SPEC §2 input modes: a serialized IR document, a stored
  snapshot version, and a live import target.
  - **Subject resolution is §2.2's grammar in its normative order** (V.S.F.E label → IR
    suffix → import reference), with the explicit `--ir`/`--import`/`--snapshot` selectors,
    `--store` for the snapshot store (default `./.gebra`, no upward search), and every
    resolution failure reported as the §2.6 tool error it is — exit `2`, the stage named
    (`input`/`extraction`/`ir-validation`), a stderr diagnostic stating that no verdict was
    reached, and the tool-error run report as the stdout artifact on whichever `--format` was
    selected. An ir 1.1 document is `verify()`'s own DEC-28 refusal, carried through unchanged.
  - **The never-invokes boundary of §2.4, exactly**: resolving `module:attribute` imports the
    module (the user's own act), reads the attribute, and refuses anything that is not already
    a workflow object — nothing is called, no signature is probed, and
    `gebra verify pkg:main` cannot start an application by accident. `--call` is the one
    opt-in that executes user code: one call, no arguments. The extractor (and with it
    langgraph) is imported only on this path — verifying an IR document or a snapshot reaches
    no substrate import at all, held by a guarded interpreter in
    `tests/cli/test_never_invokes.py` alongside the CLI-SPEC §0.5 item 3 sentinel tripwires
    (`tests/sample_workflows/sentinel_cli.py`) and a strong-form socket/compile child.
  - **Exit codes are the report's own** (§3.1/§3.2): the verb returns `gate.exit_code`
    unchanged — `0` pass (WARNING-grade notes included), `1` fail or strict promotion, `2`
    tool error — and `--format`/`--output`/`--color` never move it (§3.5).
  - **Strict mode in both spellings** (§3.3): bare `--strict` promotes every WARNING,
    `--strict=<slug>[,…]` the named properties'; `--gebra-strict` is an exact alias and both
    spellings show in `--help`. The flag is read off the raw argument list before parsing, so
    a bare `--strict` never swallows the target; giving the flag twice, an empty value, or an
    unrecognized slug is a usage error with a did-you-mean over the thirteen catalog slugs.
  - **Reports on the three §4.1 surfaces** through the CLI-03 rendering engine: `human` (the
    no-flag default), `json` (the lossless run report), `sarif` (the findings-only
    projection). `--output`/`-o` writes the artifact to a file (machine formats gain the §1.5
    trailing newline); stdout carries the artifact and nothing else, stderr the diagnostics —
    extraction warnings render there in emission order, never dropped, with §5.4's
    did-you-mean attached to an `annotation-unknown-node` record.
  - **Usage errors report everything at once** (§5.3): unknown flags (with suggestions from
    the verb's own flag set), selector conflicts, mode-restricted flags (`--sidecar`/`--call`
    outside an import subject), and strict-grammar problems arrive as one diagnostic; a usage
    error emits no run report on any format. Typer's shell-completion options are disabled
    (CLI-SPEC Appendix B OI-7, resolved).
  - Golden-tested end to end: one passing and one failing corpus fixture on all three
    surfaces (`tests/cli/goldens/`, `tool.version` normalized and nothing else), within a
    117-test suite across the shell, the strict reading, resolution, the verb, and the WA-07
    tripwires.
  - The declared `typer` floor rises `>=0.12` → `>=0.27`: `gebra.cli` imports the parser
    exceptions from `typer._click`, the click fork typer now vendors instead of depending on
    `click`, and an older typer has no such module — the floor states what the code needs.

- **The round-trip drift suite — designated corpus fixtures against live extractor output**
  (card TE-11; brief D-10 In-Scope 5 / Deliverable 6, and the risk row it answers: *hand-written
  fixtures drift from what `gebra.extract()` actually emits — golden tests pass against an IR no
  one produces*). `tests/drift/` pairs **sixteen vendored fixtures with sixteen mini LangGraph
  builder scripts** (seventeen pairs — one evolution fixture carries two IR blocks, so its one
  script has two factories), builds each graph live under the pinned substrate, extracts it, and
  compares the result against the fixture's own `ir:` block. No user-facing API changed; this is
  test infrastructure, and it runs inside the existing `test-locked` job and every version-matrix
  cell because `testpaths = ["tests"]` already covers it.
  - **The comparison is IR-SPEC §1.2's extractor-conformance operation with a fixture in the
    golden's place**: canonical bytes byte-identical **and** `graph_version` string-equal.
    Model equality would have failed every pair on declaration order alone — a builder yields
    its nodes and edges in §6 canonical order and a fixture is authored in reading order — and
    would have said nothing about content. A structural diff over the two canonical JSON
    documents is computed only to *render* a failure; the verdict is the bytes, and the suite
    substitutes one byte at every position of a green pair's canonical form to hold itself to
    that.
  - **The set is drawn from the fixtures whose every edge is `normal` or `send`, and the reason
    is recorded rather than glossed.** Extraction fills a *conditional* edge's `condition` slot
    with the declared branch name, and INTROSPECTION-SPEC §3's own row anticipates the
    divergence ("authored IRs may carry richer declared expressions in the same slot"), which is
    what every conditional fixture in the corpus does. `send` edges are **not** excluded: §6's
    `StateNodeSpec.ends` surface — `destinations=` on a `Send`-hinted node — has no `BranchSpec`
    behind it and so emits no `condition`, which is the shape the corpus's send fixtures
    declare, and one of them is designated. The cost is stated: `termination-witness` and
    `retry-coherence` have **no pair**, because every fixture in both is conditional. A real gap
    in this suite, on the card, not hidden by a different denominator.
  - **One corpus↔extractor divergence was found, and it is logged rather than edited away.**
    The corpus writes `reducer: operator.add`; extraction writes `_operator.add`, because
    `operator.add.__module__` *is* `_operator` and PD-021 D3 spells a reducer as Python carries
    it. Both sides are settled elsewhere — the extractor spelling is pinned in three EX-14
    conformance goldens under the WA-05 lifecycle at a signed gate, and the corpus is
    R-05-owned and vendored read-only under WA-04 — so the three affected pairs stay in the
    registry carrying the exact difference, and the suite fails if it widens *or* if it
    quietly goes away; the question is **deferred, not declined**, routed to TE-14 as the next
    card that opens the vault-first fixture flow. What it costs today: no validator reads a
    reducer's name (P-09 reads presence and absence), so no verdict moves — what differs is
    `graph_version`, and `gebra.diff`, whose `StateFacet.reducer_changed` compares the strings.
  - **Fourteen pairs round-trip byte-identically**, and they also agree at *model* level up to
    one named residue: a fixture node carrying neither `effect` nor `pure` leaves the slot
    open, which is what ANNOTATION-API-SPEC §4 inference fills, so the script closes it with
    `@gebra.contract(effects=[])` — canonically identical (§6.3 omit-normalizes an empty
    `effect`), `None` vs `()` in the models. Asserted, not tolerated. The three divergent pairs
    are held to the bytes and to their record only, not at model level.
  - **Ten seeded builder-script divergences are caught**, one per way a builder can move an IR
    field — `entry`, `finish`, `state` (membership and optionality), `nodes` (identity and
    three annotation slots), `edges` (presence and target). The same module's *unseeded*
    baseline is asserted byte-identical first, so each failure is attributable to its own edit.
  - **WA-07**: every node body in every script records itself and raises a `BaseException`
    subclass; the ledger is read on entry to and exit from every test, every body is fired to
    prove the arming is live, and every pair is extracted with `StateGraph.compile` armed to
    refuse — the subject is the builder level throughout (PD-023 D4). The suite adds no
    extraction path, so no new tripwire is owed; `tests/never_invokes_audit.md` §4 gains its
    paragraph.

- **The extractor + annotation API freeze and 1.x backlog (card EX-15; brief D-08 week-12
  milestone, G5 exit card)**. `docs/governance/EXTRACTOR-API-FREEZE.md` freezes the
  `gebra.extract()` entry point, the `gebra.extraction` package (72 exports), and the
  `@gebra.contract`/`gebra.toml`/inference annotation surface `gebra.annotations` (55
  exports), then records the design-tracked 1.x backlog: ten deferred slots — `projection`
  (P-10), subgraph child-topology expansion, `join_key` (P-11), `codomain` (P-05), `kind:
  join` (waiting-edge flattening), a managed-value marker slot, checkpointer *type*, tool
  projection for `BaseTool`-object bindings (EX-16/PD-043 D4), and the two non-mirrored
  `StateNodeSpec`/compiled-provenance field groups (EX-05/PD-023 D6, taken verbatim) —
  each cited to its INTROSPECTION-SPEC/IR-SPEC anchor and marked "needs future DEC". Any
  change emitting one of the ten rows requires a vault decision record plus an
  `ir_version` bump before it lands (WA-03/WA-04); an ordinary refactor that moves none of
  the frozen surface is unaffected.

- **The IR-models API freeze (card IR-06; freeze event F3, jointly with VAL-12)**.
  `docs/governance/IR-MODELS-FREEZE.md` freezes the `gebra.ir` model/node-identity/
  canonical-serialization surface — the ir 1.1 surface as amended by DEC-28 (the
  `dynamic` edge kind, the widened `ir_version` literal, the §8 minimal-stamping
  policy) — records the validator-consumer sign-off ("the IR gives validators what
  they need", read off VAL-11/TE-04's exercise) and the snapshot-consumer sign-off
  ("serialization is stable enough to snapshot and diff", read off SD-01…SD-04's
  exercise), and states the DEC-09 post-freeze policy: any further change requires a
  vault decision record plus an `ir_version` bump. With VAL-12 and CLI-02 already
  `done`, this record arms all three of CLI-08's prerequisites. `PD-048` (delivery-plan
  repo) files, as a WA-03 spec-defect record, the `retry_policy`/`variant`/
  `compensation` requiredness divergence between the IR-SPEC §2.5 model stubs and the
  vendored `schema.yaml` v2.2 that IR-01/IR-03/IR-05 each flagged as unfiled.

- **`gebra.audit` — the per-version audit export and the snapshot-freshness check** (card
  SD-07; brief D-11 In-Scope 6–7, W8). `export_store(store)` writes one JSON property report
  per stored version to `.gebra/reports/<version>.report.json`, and
  `freshness(ir, store=store)` answers whether the store's current snapshot is still the
  definition in front of you.
  - **The export has no schema of its own.** It is the `RunReport` of
    `docs/specs/REPORT-FORMAT-SPEC.md` §1 in the snapshot profile of its §6 — ratified at
    CLI-01, which states it in terms: "SD-07 defines no export schema of its own and carries
    no second version line". `subject.input_mode` is `snapshot`, `subject.version` is the
    label the file is named for, `subject.graph_version` is the stored snapshot's, and
    `check_profile` is those obligations as a function, run before every write so a document
    that does not conform never lands on disk. `read_export` parses a file back through the
    same model the verify path emits, which is what makes reading one a check rather than a
    JSON load.
  - **A run that reached no verdict is never written as an audit record.** §6.2's obligations
    are all about identity, and a `dispatch`-stage tool error carries a full subject — so it
    satisfies every one of them while carrying no outcomes at all. An export refuses it, with
    the reason carried into the message: a file at the audit path is read as *the* record of a
    stored version, and one that answered nothing would be indistinguishable from one that did.
  - **An export is byte-reproducible**, because the run report carries no wall-clock field
    (§1.3) — the dating rides the snapshot's own `extracted_from.extracted_at`. So
    re-exporting after a validator lands rewrites identical bytes for everything that did not
    change, and is a safe act rather than a change in the audit trail.
  - **Three things brief D-11 In-Scope 6 lists that the ratified profile does not carry**,
    stated rather than discovered: the *timestamp* (§1.3 refuses it — the dating rides the
    snapshot's `extracted_from.extracted_at`), a *claim class on a passing property* (§4.2: "a
    pass carries no per-record grade" — it is read from the property catalog), and the
    *classified diff against the previous version* (§0.4 and §7 note 5: a structural diff is
    not a run report). None of the three is lost: the first two are one join away and the diff
    is `gebra.lineage`'s, whose listing carries every version's digest and per-pair bump class
    and whose `compare()` returns the diff for any pair. Folding any of them in would be the
    second schema for one document that the ratification exists to prevent. The diff clause has
    a tension behind it — PD-006 R4's rationale asks for it while PD-006's own frozen checklist
    block, which is what G7 acceptance is verified against, does not — recorded as PD-047.
  - **Freshness answers in three states**, not two: `fresh`, `stale`, and a store that holds
    nothing at all, which is not the same event and does not want the same words. The
    comparison is against the store's **current** snapshot — the same one
    `gebra.snapshot.snapshot` makes before deciding whether to record — so the check and the
    recorder cannot disagree about whether anything moved. A stale outcome carries the whole
    `WorkflowDiff`, so it can say which of S/F/E moved without reading the store twice.
  - **It never writes and it grades nothing.** A freshness check that recorded the snapshot it
    was missing would be a gate that always passes. And P-12 `evolution-safety` is out of
    Phase-0 scope (SOW §8), so a stale outcome reports that the content moved and which
    counters moved with it, and stops.
  - **`gebra.audit` imports no substrate.** It takes a `WorkflowIR`, not a live workflow, so
    unlike `gebra.snapshot` the never-invokes claim holds for its import closure too — the
    extraction leg is the pytest plugin's, which already has it.
- **`@pytest.mark.gebra_freshness` — the snapshot-freshness gate in CI** (card SD-07; brief
  D-11 In-Scope 7 and deliverable 6). Mark a function that returns your workflow and its one
  item fails when what it returns is not the snapshot the store currently holds; the message
  names the store, both digests, which of S/F/E moved, and the call that records it. `store=`
  names the `.gebra/` directory, relative to pytest's rootdir and defaulting to `.gebra`;
  `name=` and `sidecar=` are the `gebra` marker's. It is a check on the store rather than a
  fourteenth property, which is why it is its own marker rather than an extra item on the
  `gebra` marker's per-property parametrization. `gebra.pytest_plugin.check_freshness` is the
  same question programmatically.
- **`gebra.snapshot` — the snapshot engine, wired to `extract()`** (card SD-03; brief D-11 W4
  and In-Scope 3). `snapshot(workflow, store=store)` runs the whole path a stored version
  needs: `gebra.extract()` produces the IR, the IR-SPEC §4.1 envelope wraps it with its
  provenance, the V.S.F.E label is derived, and `gebra.store` writes it.
  `record(envelope, store=store)` is the same call for a caller that already holds an
  extraction — which is what lets a verify run and the write share one resolution and one IR.
  Both answer with a `SnapshotOutcome`: what was done, under which label, to which file, and
  which of S/F/E moved relative to the previous version.
  - **The re-snapshot policy** (the card's decision). A call compares the working IR's
    `graph_version` against the store's **current** snapshot. Equal: nothing is written, no
    clock is read, and the call reports the label the store already holds — never a
    fabricated new one. Different: the label is `workflow_diff(current, working).bump(current
    label)`, so the counters that move are the ones the diff engine derived. Empty store:
    `1.0.0.0`, chosen rather than derived, because there is no earlier IR to compare against.
    The comparison is against `current` rather than the whole history, so reverting a
    workflow records a *new* version carrying the older digest: the history is a log of what
    happened, and two versions holding one digest is a shape the store and `gebra.lineage`
    both already model.
  - **The provenance bridge.** Extraction's `extracted_from` and the store's are different
    models with different jobs; this engine is where they meet. `source`, `extractor_version`
    and the sidecar path (including its absence — ANNOTATION-API-SPEC §2) cross over
    unchanged, and `extracted_at` is added here, because `gebra.store` reads no clock at all.
    That clock is injectable: pass `extracted_at` and the whole path from an envelope to the
    bytes on disk is a function of its arguments — two stores that never saw each other then
    hold identical bytes. `source` defaults to what extraction knows (the object's type
    identity) and can be given the reference the caller actually named, which is what a
    report over a stored version quotes back.
  - **The §0.2 recording rule is applied, never re-derived.** Hand the engine the `RunReport`
    of a verify run over the same IR and it refuses to record when `gate.snapshot_eligible`
    is false (PROPERTY-CATALOG-SPEC §0.2: a FATAL means no snapshot is recorded). It runs no
    validators and decides nothing about what a FATAL is; handed no report, it records, which
    is stated rather than defaulted around. It also checks that the report is *about* this IR,
    by comparing the digest the report's subject carries — one `verify()` computes rather than
    accepts — with the digest being stored, which makes CLI-SPEC §4.2's "the digest the store
    records is the digest the gate saw" true by construction rather than by caller discipline.
  - **A document repeating a node id is refused rather than stored**, on every path including
    the first snapshot of an empty store. Node ids MUST be unique within a document (IR-SPEC
    §2.1, ratified DEC-22); until IR-07 puts that on the model, the shipped floor is the diff
    engine's resolver, and this engine routes every IR through it before looking at the store.
    Storing such a document would put a label on content whose canonical form is
    authored-order-dependent, and would leave a store that reads fine and can never be added
    to, since every later call would be refused when it tried to diff against it.
  - **Refusals are coded** (`SnapshotError` with a reason): a current label outside the
    V.S.F.E grammar, which has no counter to bump; content that moved while the diff selected
    no component, which would put two contents under one label; and a run report about some
    other IR. Store faults propagate as the store's own `StoreError` — one fault, one
    vocabulary.
  - **Never-invokes (WA-07).** This is the first module outside `gebra/extraction/` that
    hands a live object to the extractor, so it carries the strong form of the guard:
    `tests/snapshot/test_travel_booking.py` snapshots the sentinel-guarded travel-booking
    agent twice in a fresh interpreter where name resolution, connection opening, socket
    construction and `StateGraph.compile` all raise, pins the stored document to that agent's
    node set and to a fresh extraction's digest, and arms every raiser the claim rests on.
    Importing `gebra.snapshot` imports the substrate; `gebra.store`, `gebra.versioning`,
    `gebra.diff` and `gebra.lineage` stay free of it and are tripwired for it.
  - **No safe/breaking claim is made anywhere.** P-12 `evolution-safety` is out of Phase-0
    scope (SOW §8), and the diff an outcome carries holds the structured marker that says so.

- **The plugin's gate flags — `--gebra-strict`, `--gebra-select`, `--gebra-skip`** (card
  TE-07; brief D-10 In-Scope 2 and W9; PROPERTY-CATALOG-SPEC §0.2). The severity contract the
  plugin already enforced now has its CI policy layer, and a run no longer ends without saying
  what it checked.
  - **`--gebra-strict`, in both of §0.2's forms.** Bare promotes every WARNING-grade record in
    the run; `--gebra-strict=<slug>[,<slug>…]` promotes only the named properties'. A promoted
    record fails its property's item — and is **unchanged** in the report: it keeps
    `severity: warning` and its claim class, because "promotion changes the gate, never the
    record". Nothing about the ladder moves with it: `gate.counts` is untouched, and a run
    whose only failure is a promotion is still snapshot-eligible. The flag reaches the
    `gebra_verification` fixture too, so a suite asserting on `report.gate.exit_code` sees the
    gate CI ran.
  - **Witness-note reach.** §0.2's promotion reach is about severity, so it includes
    WARNING-grade structured *witness notes* — records no finding walk can see. The item now
    carries them (`ItemOutcome.witness_notes`), notes them by default, and fails on one that a
    strict policy promoted. The live case is P-02's `scc-covered-only-by-recursion-limit`. Its
    promoted item is reported under `cycle-without-termination-witness`, an id the §0.4
    registry grades FATAL while the record is a WARNING-grade note — so the rendering joins
    back to the record for the grade and shows the id as an identity, which is
    REPORT-FORMAT-SPEC §4.6 rule 8 in terms.
  - **`--gebra-select` / `--gebra-skip`** subset which properties get an item —
    `enabled ∩ select \ skip`, repeatable and comma-separated, in catalog order however typed.
    Neither reaches `verify()`: the run still answers the whole catalog, so a skipped property
    is un-*itemized*, never unchecked, and `gebra_verification.report` still carries all
    thirteen outcomes. A slug outside the closed thirteen-slug vocabulary ends the session
    rather than being ignored, and so does a subset that would leave nothing to check.
  - **A closing `gebra` report**, printed with no flag, carrying REPORT-FORMAT-SPEC §5.1's
    obligations onto a pytest run. One block per verified target: the subject; every property
    by id and slug, with either a §4.3 witness summary and its catalog claim class or every
    failure-side record rendered per §4.4 and anchored per §4.5; the eight Phase-0 defers shown
    as *not checked*; the notes; the best-effort qualifier beside the reports it qualifies; and
    a summary with the counts, the exit code, the strict policy in force and each record it
    promoted. Two bounds rather than one blanket claim: it is **not** `gebra verify`'s human
    profile (that surface is CLI-03's), and the witness rows are summaries — the whole witness
    is on `gebra_verification.report`. It is a rendering, not a machine format: PD-015 (the
    CLI-D1 ruling) puts the native JSON envelope and its SARIF projection on
    `gebra verify --format`.
    One bound, stated rather than left to be found: the blocks are assembled in the process
    that ran the items, so under a plugin that distributes them to workers (`pytest-xdist`) the
    section is not expected on the controller. That combination is untested in this
    environment; the per-item report section travels with the report regardless.
  - The plugin implements no promotion of its own: it hands the policy to
    `gebra.verify.verify()` and reads `gate.promotions`, so §2.3's reach — the advisory row
    included — stays implemented once.

- **The pytest plugin — `pytest` as the front door to gebra verification** (card TE-06; brief
  D-10 In-Scope 2 and deliverable 2). `gebra.pytest_plugin` is registered as a `pytest11`
  entry point, so installing the package is the whole of switching it on — no `-p gebra`, no
  `conftest.py` wiring. Two surfaces:
  - **`@pytest.mark.gebra` — one test item per target × enabled property.** The marked
    function *is* the graph producer: whatever it returns (a `StateGraph`, a compiled graph,
    an LCEL `Runnable`, or a `WorkflowIR` you already hold) is extracted and handed to
    `gebra.verify.verify()`, and pytest collects one item per property, named the way D-10
    spells it — `test_gebra[travel_agent-termination-witness]`. The target's label comes from
    `@pytest.mark.gebra(name=...)` or from the function name without its `test_` prefix,
    because the id has to be known at collection time. Marked functions take fixtures like
    any other test, and compose with `@pytest.mark.parametrize`; the gebra component lands
    last in the id.
  - **`gebra_graph` — the extracted IR, for plain assertions.** Override `gebra_workflow` in
    your `conftest.py` (D-10's "conftest.py factory") and `gebra_graph` is that workflow's
    `WorkflowIR`, and `gebra_verification` the whole verification over it — a
    `TargetVerification` whose `.report` is the `RunReport` and whose `.extraction_notes` are
    the warnings extraction raised. The shipped `gebra_workflow` has no default and says so
    with the override to write, rather than failing as a missing fixture.
  - **Which properties get an item, and what fails one.** Every property this build
    registered a validator for, read off the registry rather than listed — the wedge five
    today. The eight SOW §8 defers get **no item**: not generating one is not a pass claim,
    and their structured not-implemented markers stay visible through `gebra_verification`.
    An item fails on the D-10 default severity mapping — a FATAL or ERROR **finding** *owned
    by that property* (REPORT-FORMAT-SPEC §2.3's owner attribution, so a co-failure riding
    another property's report fails the right item) — while a WARNING-grade finding is
    attached to the item as a note. A `WitnessNote` is not a finding and the item carries
    none: notes are "never gate-bearing" (PROPERTY-CATALOG-SPEC §P-02.3), they are reachable
    through `gebra_verification.report`, and they land on the item with TE-07 below. A P-08
    fixture whose report is `result: "fail"` at WARNING grade therefore
    passes its item, which is the distinction the mapping exists to make. A tool error (exit
    2, "no verdict was reached") fails every item of that target, and §0.3's best-effort
    qualifier rides the items that inherit it — including the passing ones, since a qualified
    pass is still qualified.
  - **Importing the plugin costs a session that does not use it nothing.** A `pytest11` entry
    point is imported at the start of *every* pytest session in an environment that has gebra
    installed, so the module's import closure is `pytest` plus the standard library: `gebra.ir`
    (~90 ms) and `gebra.verify` (~190 ms) resolve inside the functions that need them, and the
    extractor only on the branch handed a live workflow. Measured in a child process that
    imports nothing else.
  - **Never-invokes (WA-07).** gebra runs nothing on this path. It calls the function you
    marked — your code, called the way pytest calls any test — and hands what that returns to
    `gebra.extract()`, which imports and inspects. It reads no attribute off the target to
    classify it (one `isinstance`, then the extractor), because a `property` on a user object
    would be user code running inside a verification path; and it takes the fixture names
    pytest already resolved rather than asking `inspect.signature` for them, because from
    Python 3.14 that call evaluates the function's annotations. Two tripwires:
    `tests/plugin/test_plugin.py` reads the travel-booking agent's sentinel ledger after each
    in-process inner session, and `tests/plugin/test_hermeticity.py` runs a whole inner pytest
    session — the marker surface and the fixture surface, over that agent's already-extracted
    IR — in an interpreter where every substrate import, socket construction and name
    resolution raises after recording the attempt, which is the card's "importable without
    langgraph in fixture-only mode" as a test rather than a claim. Its armed control is the
    plugin's other resolution branch: the same guarded child handed a target that is not a
    `WorkflowIR` must reach the extractor, trips the blocker, and fails all five items.
  - **Extraction warnings are surfaced, not dropped** (INTROSPECTION-SPEC §8: "never silently
    droppable"). Each one rides its item and the run's closing `gebra notes` section, under its
    §8 taxonomy code — `contract-defaulted`, not the Python enum's name — so a default `pytest`
    run shows them without a flag. An explicit `gebra.toml` is declarable on both surfaces
    (`@pytest.mark.gebra(sidecar=...)`, or a `gebra_sidecar` fixture), which is
    ANNOTATION-API-SPEC §2's "reproducible/CI extraction SHOULD pass `sidecar=` explicitly";
    without one, discovery walks up from the pytest process's working directory, and
    sidecar-filled annotations move P-04 and P-06 verdicts as well as the digest.

- **The travel-booking agent fixture — the shared end-to-end substrate** (card TE-05; SOW §2
  criterion 1; briefs D-10 W4 and D-11 W4). `tests/sample_workflows/travel_booking.py` is a
  live LangGraph `StateGraph` re-expressing the `07-AI-Agent-Orchestration` tutorial agent the
  Phase-0 Definition of Done is written about: nine nodes, two routed re-entry decisions, one
  non-trivial SCC holding two simple cycles, a narrowed `input_schema=`, and the full decorator
  contract surface (`contract`, `deterministic`, `variant`, `idempotent`, `compensation`).
  It extracts to `ir_version` 1.0 with **no error and no warning**, and at v1 the wedge five
  all pass — exit code 0, snapshot-eligible, and nothing promoted under `--gebra-strict`.
  - **Clean by construction, not by omission.** The four frozen passages that quote this agent
    quote it broken — PROPERTY-CATALOG-SPEC §2.2 (unwitnessed booking cycle), §6.2
    (unprotected `irreversible`+`billable` `book_flight`), §4.2 (an express path that skips the
    booking nodes), §8.2 (an unpinned determinism claim on an LLM node). Seeding those is
    SD-09's card; v1 carries the same graph in each passage's *fixed* state, so a defect
    variant is one annotation edit away. The cycle carries P-02 witness form (c) — a `variant`
    on `replan`, which both simple cycles pass through — because form (a) is a guard grammar
    over `edges[].condition`, a slot IR-SPEC §2.4 fills from declared annotations/config and
    INTROSPECTION §3 fills, on the extraction path, with the declared branch *name*; and form
    (b) is `runtime.recursion_limit`, which no extraction path supplies at either level.
    `book_flight` and `book_hotel` carry one each of P-06's two admitted remedies, both bound
    to the IR they name. The narrowed `input_schema=` is PD-021 D1's author-side recovery, and
    without it P-04 would pass vacuously — so the builder takes a `narrow_input_schema` flag
    whose only job is to build that counterfactual, and the suite runs P-04 over both: under
    the counterfactual every obligation is discharged at START, under v1 every internal-key
    obligation names a writing node. Both pass; the difference is whether the verdict could
    have been anything else. P-02's certificate is likewise re-checked against a residual
    graph rebuilt from the IR, rather than taken on the validator's word.
  - **Never-invokes (WA-07).** Every node function and router records itself in a `TRIPPED`
    ledger and then raises a `BaseException` subclass, so no `except Exception` guard can
    swallow one. `tests/testing/test_travel_booking.py` asserts the ledger is empty on entry to
    *and* exit from every test (entry too, because the module-scoped extraction runs before the
    first test's own setup), *fires* all eleven bodies to prove the ledger is live, and runs the
    whole extract → verify path — at both the builder and the compiled level, with the document
    pinned to this agent's node set — in a fresh interpreter where name resolution, connection
    opening, socket construction and `StateGraph.compile` all raise. Every raiser the claim
    rests on is armed by a control matched on its full message, and two of those controls
    swallow the exception, so the record-before-raise design is exercised rather than described.
    Importing the module builds no graph and compiles nothing, proven the same way.
  - **The subject is the builder** (the explicit choice PD-023 asks TE-05 and SD-08 to make):
    `runtime.checkpointer` is read only off a compiled object, so the compiled document of this
    agent carries a `runtime` block and a different `graph_version` — pinned as a test, with
    `compile_travel_booking_agent()` exposed for the cards that want the §4 surface. No library
    code changed.

- **The never-invokes tripwire audit and the consolidated adversarial suite** (card EX-13;
  INTROSPECTION-SPEC §1 and DEC-19;
  SOW §2 criterion 5). `tests/never_invokes_audit.md` is the path-to-tripwire audit table:
  every extraction path in `src/gebra/extraction/` mapped to its tripwire test and armed
  control, the six DEC-19 `get_graph()` drawing routes and the §1 rule 4 hazards mapped to
  their armed fixtures, and a stated boundary for the provenance gate (WA-06). The table is
  machine-checked — `tests/test_never_invokes.py::test_the_audit_table_lists_every_extraction_path`
  reconciles it against the package on every run, so a path that lands without a tripwire row
  fails the suite. `tests/extraction/test_never_invokes_adversarial.py` extracts one workflow
  packing all four §1 rule 4 hazards (pydantic validator execution, `__init_subclass__`,
  decorator side effects, string/forward-ref annotation evaluation) through the public
  `gebra.extract()` and asserts none fired, with a seeded-execution test proving the invariant
  is not vacuous. Route 5 (a `__root__` channel's `ValueType()`, called as a constructor) gains
  a genuinely-armed fixture; the compiled guarded child now arms `Runnable.invoke` with a
  counted `ChannelWrite` allow-list and asserts `langgraph.pregel.remote` never enters
  `sys.modules`. No library code changed — the extractor was already never-invokes-conformant,
  and this card commits the audited evidence surface that says so.

- **The extractor-conformance suite and its committed goldens** (card EX-14;
  IR-SPEC §1.2–§1.3 layer 2 and §6; SOW §2
  criterion 3). Eight live conformance workflows —
  `tests/sample_workflows/conformance.py`, spanning the three object families (builder,
  compiled, LCEL) plus annotation resolution, the four edge kinds (`normal`, `conditional`,
  `send`, `dynamic`), both `ir_version` values, the §3.6 digest slots, the §3.7 runtime
  block, and all three §6.3 state-value forms — are each paired with a committed canonical
  serialization and `graph_version` under `tests/extraction/golden/conformance/`.
  `tests/extraction/test_conformance.py` re-extracts every workflow and requires the bytes
  **byte-identical** and the digest **string-equal**; it also runs the comparison against
  every single-byte substitution of every golden (and a JSON-equal but byte-different
  variant), so "a single differing byte is non-conformance" is executed, not quoted. The
  goldens follow the WA-05 lifecycle (see the README beside them);
  `tools/conformance_goldens.py --check|--write` is the sanctioned regeneration path, with
  an in-process determinism guard. One comparison is substrate-gated by exact pin: the
  tool-bound chain's `config_digest` embeds `metadata.lc_versions` — the installed
  langchain-core's own version string — so its golden holds only at the release it was
  taken at (langchain-core 1.5.2, the locked development pin) and skips with that stated
  reason anywhere else; every other golden holds byte-identically on every cell of the
  frozen version matrix (verified per cell). No library code changed: the extractor was
  already conformant, and this card commits the evidence surface that says so.

- **`ir_version` 1.1 and the `dynamic` edge kind; router edges are classified `send` vs
  `conditional` from declared return-type hints** (card EX-03;
  INTROSPECTION-SPEC §6, IR-SPEC
  §2.4/§2.5/§8, both as amended by the ratified DEC-28; PD-041).
  - **Classification.** `gebra.extract()` now reads a routing declaration's **declared
    return-type hint** — never its body — and emits `kind: send` when the hint names `Send`
    (bare `Send`, `list[Send]`/`Sequence[Send]`, or a `Union`/`Command` form admitting one).
    Everything else stays `kind: conditional`: a `Literal[…]` label hint, a plain `str`, a
    `Command[Literal[…]]` (which names no `Send`), an unreadable hint, or no hint at all. Both
    surfaces §6 covers are classified — `add_conditional_edges` routers and a node's
    `destinations=`/`Command[Literal[…]]` declaration — so the mainstream `Command`-routing
    idiom and a `Send` fan-out no longer extract to the same kind.
  - **A router that declares no targets is now extractable.** It emits
    `{from, kind: dynamic, condition}` — the fourth edge kind, ratified at DEC-28 — plus the
    `unsupported-construct` warning scoped to dynamic dispatch, replacing the boundary refusal
    the previous release raised for the canonical bare-`Send` map-reduce. The kind carries no
    `to` and no `path_map`, so the ambiguous "declared and empty" target set DEC-18 ruled out is
    not constructible on it.
  - **`ir_version` is stamped from content, not from the writing build.** Emitters write the
    lowest minor sufficient for the document: `"1.1"` iff a `dynamic` edge is present, `"1.0"`
    otherwise (`gebra.ir.lowest_ir_version`). **No existing document's canonical bytes move** —
    golden vector 001 still reproduces its 537 bytes and its digest, and a test appends a
    `dynamic` edge to every vendored corpus document and every golden, then removes it again, and
    requires the original bytes back exactly.
  - **A router codomain that ir 1.0 cannot carry is recorded beside the IR.** A `Literal[…]`
    return hint declaring targets *distinct* from the declared `path_map` lands in
    `extracted_from.router_codomains` and is never merged into `path_map` (§6's codomain-capture
    rule), so it cannot reach `graph_version`.
  - **The annotation-evaluation hazard is disclosed, not implied.** §6's read is
    `typing.get_type_hints()`, which §1 rule 3 permits with its own caveat: it evaluates string
    and forward-reference annotations, so an annotation *expression* runs. Evaluation is
    therefore scoped — a callable with no return annotation is never handed to it, an
    already-resolved annotation is read as it is, and only routing declarations are asked — every
    failure degrades to "no hint" (the conservative kind) with the reason reported, and the
    residue that remains has its own fixture and its own test rather than a footnote. A router
    **body** is never reached, which the tripwire suite holds to account with sentinels that
    record before they raise.
  - **The one thing to know if you consume a 1.1 document today:** `gebra verify` **refuses** it
    — exit `2`, `error.stage: "ir-validation"`, no verdict — and the structural diff and the
    shared validator graph model raise a `NotImplementedError` subclass naming the card that
    lands the semantics. That is deliberate rather than incomplete: a `dynamic` edge contributes
    no member to the graph the topology properties are computed over, so reading such a document
    under 1.0 rules would report nodes as unreachable that the router can reach at runtime. A
    wrong verdict is worse than an absent one.

- **`gebra.report` — the shared rendering layer: one run report, three surfaces** (card CLI-03;
  [REPORT-FORMAT-SPEC](docs/specs/REPORT-FORMAT-SPEC.md) §4/§5 and Appendix A;
  [CLI-SPEC](docs/specs/CLI-SPEC.md) §5; the CLI-D3 ruling PD-031). `render(report, "human" |
  "json" | "sarif")` turns the `RunReport` that `gebra.verify.verify()` returns into the surface
  a caller asked for. It reaches no verdict of its own: the severity tally it prints is
  `gate.counts`, the code is `gate.exit_code`, the promotions are `gate.promotions`, and every
  finding's severity and claim class are the record's own.
  - **Human terminal output** (`gebra.report.human`, the no-flag default) on `rich`, which
    PD-031 ruled and which this change promotes from a transitive dependency of `typer` to a
    declared core one (`rich>=13.8`) — the default surface cannot be conditionally absent.
    Every line is a `rich.text.Text` whose characters are decided before any style is attached,
    so PD-031's "degradation changes styling only" is an equality the suite asserts rather than
    an intention: strip the escapes from the styled rendering and it *is* the plain one. The
    block per property carries §4.2–§4.5's fact sets — the claim class with every verdict, a
    marker as *not checked* and never as a pass, `best_effort` stated beside the reports it
    qualifies rather than only in the summary, and a promotion shown as what a strict policy
    selected with the record's own WARNING grade intact.
  - **Native JSON** (`gebra.report.native`) — the run report itself under §1.5, lossless, with
    the one file-level rule §1.5 states (a file ends with a single trailing newline; a stream
    is not given one).
  - **SARIF 2.1.0** (`gebra.report.sarif`) — the lossy, findings-only projection of Appendix A:
    the `rules[]` catalog of all thirteen emittable §0.4 conditions in registry order whether or
    not they fired, one `result` per finding with the record's own grade in
    `properties["gebra/severity"]`, `logicalLocations` on every result, and A.6's fingerprints.
    The three declared losses stay losses: pass witnesses and not-implemented markers do not
    project at all, and FATAL collapses to `level: "error"` with the distinction surviving only
    in the property bag. No `physicalLocation` is fabricated (A.5: IR 1.0 carries no source
    spans, and a wrong anchor is worse than an absent one). A clean run emits `results: []`; an exit-2 run carries
    `run.properties["gebra/exitCode"]: 2`, so it can never read as a clean one.
  - **The rule copy** (`gebra.report.rules`) is the prose Appendix A.3 hands to this card:
    every `shortDescription` is A.3's own table cell, held equal to the spec by a test that
    parses it back out, and `fullDescription`/`help` state each condition and its remediation
    within §4.6's copy rules and Appendix C's ≤1024-character budget.
  - **Did-you-mean suggestions** (`gebra.report.suggestions`), which CLI-SPEC §7 puts on this
    card: `difflib` over a **closed** vocabulary — the five verbs, `PROPERTY_SLUGS`, a verb's
    own `--format` values — at most three candidates above a similarity floor, phrased as a
    question because §5.4 makes a suggestion a legibility aid and never a selection.
  - **Evidence.** `tests/report/` renders every §4 variant on all three surfaces against
    committed goldens; the variant catalog is proven complete against the *live* models — every
    concrete envelope class and every closed vocabulary member — rather than against a sample.
    Every emitted SARIF log validates against the vendored OASIS SARIF 2.1.0 schema document
    (`tests/schemas/sarif-2.1.0.json`) with `tools/json_schema.py`, a dependency-free draft-07
    subset validator that **refuses** any keyword it does not implement, so a construct it
    cannot check fails the run instead of passing unchecked. And the TE-15 banned-phrase matcher
    runs over the *rendered* text of every variant, not only over the templates — §4.6 rule 4
    makes a phrase composed from parts at run time a violation, which a file scan cannot see.


- **Structural mutation operators and metaproperty suite I — P-01 and P-02 under mutation**
  (card TE-09). `gebra.testing.mutations` gains seventeen operators that break the *topology*
  rather than a contract, and `tests/testing/test_metaproperties_structural.py` gains
  seventeen metaproperties that quantify what the two structural validators answer over them,
  each at a thousand examples. Eleven operators target P-01 `graph-well-formed` — a node
  nothing wires to, a leaf whose one inbound edge is then deleted, a sink left out of
  `finish`, a node wired to nothing at all, an emptied `entry`, and one per DEC-12 reference
  site (a bad `entry` id, a bad `finish` id, an unresolved edge `from`, an unresolved edge
  `to`, a dangling `path_map` label), plus the coherent repair. Six target P-02
  `termination-witness` — a cycle whose form-(c) `variant` is taken away, one whose form-(b)
  `recursion_limit` blanket is, one whose `variant` names a key outside Σ, a cycle running
  through two nodes rather than one, and the D4 pair whose members differ in a single
  `path_map` value. Nine of the eleven P-01 operators inject exactly one finding; the two
  that cascade do so in a shape the suite asserts in full, which is what makes the
  `(iii) → (i) → (ii)` suffix of §1.4 Step 5's root-cause order an executable claim rather
  than a review note. (The leading `F_iv` block is *not* covered here — no operator emits a
  condition-(iv) finding alongside another block — and stays pinned by the corpus's
  `mixed/04`.)
- **The WA-07 tripwire gains an eighth leg** (card TE-09). `tests/testing/test_hermeticity.py`'s
  guarded child now runs P-01 and P-02 over both halves of fifty structural mutations, in the
  interpreter where a substrate import, a socket and a name resolution each raise. What it adds
  over the contract leg is the two validators that read the *graph*, on the input where a
  validator would be tempted to resolve something: P-01 spells an unresolved reference back into
  a report rather than looking it up, and P-02 hands every router's declared `condition` to the
  TERMINATION-WITNESS-SPEC §3 recognizer, which is a regular expression over declared text and
  must stay one. New asserted keys `structural` / `structural_targets` /
  `structural_as_predicted`. The closure floor also moved **18 → 30**: it had been rising by one
  per card rather than being derived, and the real closure is 33 — so it had come to tolerate
  45% of the closure vanishing from the report, which is exactly what would make the two static
  scans that iterate that list silently vacuous.
- **`Mutation` carries the whole anchor of the finding it predicts**, in one location-valued
  slot (`Mutation.location`), because §1.3 anchors a P-01 reference finding at an *edge* and
  §2.3 anchors a P-02 finding at an SCC or a cycle — neither of which the record's `node` and
  `key` scalars can express. It also carries `Mutation.well_formed`, false exactly for a
  breaking P-01 mutation: PROPERTY-CATALOG-SPEC §0.3 defines the other four properties'
  results only over P-01-clean topology and says in terms that "cross-validator agreement on
  ill-formed input is NOT promised", so a cross-cutting metaproperty scopes on that flag
  rather than asserting agreement the frozen text declines to promise.
- **`gebra.testing.mutations.acyclic_envelope`** — the size-envelope narrowing that makes a
  draw carry no cycle, now public because every operator that *adds* one needs it, as does a
  suite that builds both polarities of a loop edit from a single draw.

- **`docs/governance/VALIDATOR-API-FREEZE.md` — the validator-result API freeze record**
  (card VAL-12, freeze event F3's VAL half, jointly with IR-06). Records the harness-consumer
  sign-off brief D-09's DoD names ("callable, structured, assertable"), evidenced from card
  TE-04's corpus-green run rather than asserted; states that any post-freeze change to the
  frozen surface — the `gebra.verify` result envelope, condition-ID/property registry, wedge
  validator entry points and the `RunReport`/`verify()` run-level models — now requires an
  R-05-routed decision, the same discipline WA-03/WA-04 already apply to the frozen specs this
  surface implements; and records D-12 promotion eligibility (CLI-08) as **VAL-12's half
  only** — IR-06 is `todo` as of this record, so CLI-08 is not yet READY, exactly as its own
  `prereqs` (`IR-06, VAL-12, CLI-02`) already say. The CLI render sign-off ("every witness/
  failure variant renders cleanly") is deliberately **not** captured here; it is CLI-07's.
  `tests/docs/test_validator_api_freeze.py` (9 tests) cross-checks every symbol the note names
  against the live `gebra.verify` exports in both directions, so the record cannot silently
  drift from the surface it freezes.

- **`python tools/corpus_green.py` — SOW §2 criterion 2 as one run** (card TE-04). The
  corpus-green definition PD-006 R3 fixes is four clauses, and until now each was checked by
  a different tool or by nothing: the load layer (all sixty fixtures load, lint against
  schema v2.2, their IR payloads validate, and their `expected:` blocks compose — this last
  one asserted in the form the next entry describes, never as an unqualified sixty), the wedge
  assertion layer (every obligation the ruling enumerates green by structural model
  equality — never string equality), the skip layer (every non-wedge component a structured
  skip naming its property and citing SOW §8, counted, never rendered as a pass) and the run
  layer (a `verify()` report listing all thirteen properties with the eight non-wedge
  markers). This command evaluates all four together and prints the result clause by clause.
  It distinguishes two kinds of shortfall and never conflates them: a **violation** is a
  shortfall nothing accounts for and fails the gate in every mode, while **residue** is one
  that carries a named cause or a routed decision-log row — reported, counted, and never
  rendered as a pass. The verdict line says which; it does not claim criterion 2 is met
  while anything is outstanding. `--strict` is the literal reading of the ruling and fails on
  residue too.
- **The composition ledger is now checked rather than described** (card TE-04). Twenty-seven
  of the sixty `expected:` blocks do not compose into a PROPERTY-CATALOG-SPEC §0.3 report,
  because the shapes they carry are ones the frozen specs deliberately do not model.
  `corpus_green.py` derives a named cause for each — a non-wedge owning property, a
  non-wedge record riding a wedge property's block, a condition ID §0.4 holds back, or
  `mixed/10`'s run-level wrapper — and *verifies* it rather than labelling it: the
  non-wedge-record case is only claimed where restricting those records out is what makes
  the wedge share compose. A block that stops composing with no such cause is a violation, so
  a fixture cannot quietly join the twenty-seven. **Those four causes are a closed set**, and
  closed by ruling rather than by convention: a fifth is a decision the acceptance criterion's
  owner takes, never an edit to this tool, which is what keeps "accounted for" from drifting
  into "whatever the gate currently tolerates".
- **`gebra.verify.verify(ir, policy=None)` — the run-level report and its gate** (card
  VAL-11). One call runs the registered validators over one IR and returns the `RunReport`
  of `docs/specs/REPORT-FORMAT-SPEC.md` §1: all thirteen catalog properties in catalog
  order, with a structured not-implemented marker wherever no validator is registered and
  never a silent pass; the IR's own identity (`ir_version` and the IR-SPEC §6
  `graph_version` digest, computed here rather than accepted); and the gate — the exit code,
  the outcome word, the severity counts, the strict policy in force with what it promoted,
  and snapshot eligibility. The exit codes are PROPERTY-CATALOG-SPEC §0.2's, derived over a
  whole run by §2.2: `0` for a pass (or `pass-with-notes` where a WARNING-grade record or
  note is present), `1` for a FATAL or ERROR finding — or for a WARNING promoted under
  strict mode — and `2` for a run that reached no verdict at all. Exit `2` is never a
  verification result: an unregistered member of the wedge five is a tool error rather than
  a thinner gate, and an exception escaping a validator is a tool error rather than a
  failing property. **Strict mode** ships in both of §0.2's forms — bare
  (`StrictPolicy(mode="all")`, every WARNING in the run) and per-property
  (`mode="per-property"` with the catalog slugs) — and it reaches WARNING failures,
  co-failures, advisories and WARNING-grade witness notes, matching on the **record's own**
  property, so a policy naming P-08 promotes a P-08 advisory riding another property's
  report. Promotion moves the gate and nothing else: the whole `properties` block is
  byte-identical with a strict flag on and off, and a promoted P-02 note leaves its report a
  pass with its witness intact. Only a FATAL suppresses snapshot recording; a promoted
  WARNING does not. Nothing on this path imports langgraph, executes a workflow node, calls
  a model or opens a network connection.
- **`RunReport.best_effort` — the P-01-clean precondition, reported** (card VAL-11).
  PROPERTY-CATALOG-SPEC §0.3 defines P-02, P-04 and P-06 results only over P-01-clean
  topology and calls their reports on a P-01 failure "best-effort diagnostics, not
  contract-bearing verdicts". P-01 runs first, its FATAL findings alone fix the run's gate
  (exit `1`, no snapshot, whatever the other four found), and `best_effort` names the three
  properties whose outcomes a consumer must read as diagnostics — a qualification, not a
  suppression: every report is still carried in full.

- **P-02's strict-mode surface, and the census cap tested at its boundary** (card VAL-08).
  `--gebra-strict` is a **gate** policy, so P-02's report is the same report under every
  policy — PROPERTY-CATALOG-SPEC §0.2 promotes a WARNING-grade record "with the report,
  witness, and note records unchanged", and DEC-11 item 6 ratified it in those words. What
  strict mode produces instead is a selection, and `gebra.verify.strict_promotions(report)`
  is it: given a P-02 report it returns one `StrictPromotion` per residual SCC that only a
  justified `recursion_limit` covers, each carrying the note's own kind, the residual-SCC
  location with `blanket_only: true`, and the condition ID TERMINATION-WITNESS-SPEC §6.1's
  strict row reports it under — `cycle-without-termination-witness`, the same RATIFIED ID a
  cycle with no witness at all fails under, since "no new condition ID is introduced". It
  returns promotions rather than a second report on purpose: a second report for one
  property and one IR would be the record changing, whatever produced it. A promotion
  carries no severity — the promoted record is the note and keeps its own `warning` grade —
  so nothing on this path can reach a run's FATAL count, which is the rule that keeps
  snapshot recording unaffected by a strict flag (`REPORT-FORMAT-SPEC` §2.5: "promotion
  moves the gate, not the ladder"). The lookup needs no re-analysis
  because a blanket never participates in residual construction, so the SCCs the strict row
  reports are exactly the ones the record already lists. Relatedly, the blanket note's
  location now carries `blanket_only: true`, which §6.1 fills from "justified
  `recursion_limit` present?" for the passing row as much as for the strict one; `false` is
  still never emitted. The **abort-capped cycle census** shipped at VAL-07 is unchanged and
  now tested where it matters: at B = 16 the list is complete, at B + 1 it is omitted
  entirely (never truncated) and replaced by the `cycle-census-capped` note, self-loops and
  parallel label-edges count against the cap on the spec's own rule rather than by vertex
  circuit, and the abort is taken *during* enumeration — on a complete twelve-node digraph
  with 119,481,284 simple cycles the search hands back exactly B + 1 circuits and stops.
  The run-report spec's §2.1 was corrected in the same change: it defined a note as one
  "riding a passing report's witness", which the promotable fail-path notes DEC-23 put on
  `Failure.notes`/`CoFailure.notes` contradict — §2.3's reach table was already right, so
  the definition now matches it. Prose only; no model changed and `report_format` stays
  `1.0`.
- **The P-02 `termination-witness` validator** (card VAL-07):
  `gebra.verify.check_termination_witness(ir)` — the last of the wedge five, so every
  Phase-0 validator now answers with a report rather than a not-implemented marker. P-02
  asks one question of the label-expanded graph: does **every simple cycle** carry a
  declared termination witness? Three forms answer it (TERMINATION-WITNESS-SPEC §2): a
  bounded counter in the state schema behind a recognized conditional exit (form (a),
  through the §3 guard grammar that shipped at VAL-06), a justified graph-level
  `recursion_limit` (form (b), a blanket), and an annotated loop `variant` (form (c),
  attested). Discharge follows the DEC-23 rulings exactly: only the gated then-label edge
  of a qualifying guard enters the witness set (Q1), and the D4 exit test is evaluated
  against the guard's dominator-derived natural loop with the SCC test as its fail-closed
  fallback (Q4) — which is what lets a nested inner loop's counter discharge while its
  escape stays inside the enclosing SCC. Coverage is decided by Lemma 1 — one residual
  acyclicity check, linear in the graph, never a cycle enumeration — and a failing SCC
  reports **one** representative witness-free cycle (`exhaustive: false`), extracted as the
  first back edge of a deterministic DFS. A counter guard none of whose labels leaves its
  loop fails under the distinct `counter-guard-without-exit-edge` condition (DEC-05 D4),
  which subsumes the base condition for its own SCC. On a pass the witness carries the
  S-element inventory, a re-checkable acyclicity certificate, and — per PD-011,
  unconditionally — the B-capped cycle census (B = 16; self-loops and parallel label-edges
  counted per T-W-SPEC §6.3), with the structured `cycle-census-capped` note when the cap
  aborts it. A justified `recursion_limit` covering cycles no element witness reaches is a
  **pass with a WARNING-grade note** (`scc-covered-only-by-recursion-limit`), one note per
  residual SCC with its representative cycle. Every claim states witness **presence** only:
  what a run does at runtime is never claimed, and the attested components are recorded and
  trusted, never checked.
- **The DEC-23 (PD-037 Q2) envelope extensions** that ride with it: `WitnessNoteKind`
  gains the fifth member `counter-key-not-qualified` — a recognized guard whose counter is
  absent from the state schema or not integer-compatible now surfaces the near-miss with
  the guard edge, the unmatched identifier and (for the wrong-type case) the declared
  type, so a misspelled counter never silently shrinks coverage — and `Failure`/`CoFailure`
  gain the structured same-property `notes` channel, carried unconditionally whenever the
  P-02 result is fail. `WitnessNote` carries the per-kind evidence fields
  (`guard_edge`/`identifier`/`declared_type`; `node`/`key`), and the report-format spec's
  rendering catalog names the new kind.

- **The 13-cell compatibility matrix, and the `compat-test` / `compat-cell-N` extras that pin
  it** (card GOV-04). CI stops testing four hand-written corner cells and starts exercising the
  compatibility surface the package actually promises: Python 3.10, 3.11, 3.12 and 3.13 across
  three pinned langgraph/langchain-core pairings — **twelve blocking cells** — plus one
  non-blocking `--pre` early-warning cell on 3.13. Every cell runs all four gates (`ruff check`,
  `ruff format --check`, `mypy`, `pytest`), not just the test suite: the substrate a cell pins
  changes what mypy resolves, so a cell that ran only `pytest` would leave the type surface
  unchecked on eleven cells of twelve.

  **The pins live in `pyproject.toml`, and they include transitives.** A matrix cell in the
  workflow carries a cell *number* and nothing else — `pip install -e ".[dev,compat-cell-1]"` —
  so there is exactly one place a cell's substrate is written down, and reproducing a CI cell
  locally is that same command. One extra per cell, because one extra cannot hold three: the
  cells pin the same distributions to different versions, so a single requirement set carrying
  all three is unsatisfiable by construction. `compat-test` is the newest frozen pair (the same
  pins as `compat-cell-3`), so `pip install "gebra[compat-test]"` installs a real cell rather
  than warning that the extra does not exist.

  Cell 1 pins `langgraph-checkpoint==4.0.3` — a bound, not a resolved value. Checkpoint 4.1.0
  changed a module-level `Reviver()` to `Reviver(allowed_objects="core")`, and that parameter
  first exists in the langchain-core 1.2 line, so an unbounded cell 1 floats to 4.1.1 and dies
  at `import langgraph.graph`. No resolver prevents it: checkpoint declares only
  `langchain-core>=0.2.38` and langgraph 1.0.10 declares `langgraph-checkpoint<5.0.0`, and the
  broken combination satisfies both. pydantic is pinned per cell (2.13.4 in all three today)
  rather than once for the matrix, because that agreement is a property of today's resolution
  and not a durable one. The values are **candidate pins**, marked as such at the extras
  themselves; they re-resolve when the tested matrix is frozen.

  **The `--pre` cell is unpinned, uncached and non-blocking, all three deliberately.** It
  installs `--pre langgraph langchain-core` fresh on every run — pinning or caching it would
  delete the early warning it exists to give — and a failure never blocks the run. It is also
  never silent: each gate reports its own outcome, and a red gate writes the resolved substrate
  and every outcome to the job summary and raises a warning annotation naming the
  supported-range review it routes to.

  `tests/test_compat_matrix.py` holds the workflow and the extras to each other — the cell
  count, the four gates per cell, the pin values, the transitive bounds, that no cell pins a
  yanked release, that no blocking cell is allowed to fail, and that each cell's pair is a
  *tested* pairing by `gebra.extraction.compat`'s own classification (the runtime check and the
  CI pins are separately derived from the same ranges, and must agree). It reads TOML and YAML
  and nothing else — no install, no build, no execution (WA-07).

  **What the new cells report today, stated rather than implied.** Every cell was run locally,
  step for step, before this landed. All 13 pass `ruff check` and `ruff format --check`, and
  cell 3 (langgraph 1.2.10 + langchain-core 1.5.3) passes the test suite on 3.10, 3.12 and 3.13,
  as does the `--pre` cell. Three things are red, none of them a packaging or substrate defect:

  - Cells 1 and 2 fail 36 extraction tests on every Python, from two causes rather than one.
    Fifteen are `tests/sample_workflows/sentinel_compiled.py` building its fixtures with
    langgraph 1.2-era builder APIs (`set_node_defaults`, `add_node(..., error_handler=...)`)
    that the 1.0.x and 1.1.x builders do not have. The other twenty-one, in
    `tests/extraction/test_digests.py`, have **no identified cause yet** — that module does not
    touch the compiled sentinel, so it is a separate investigation, not a cascade. Either way
    those pairings are inside the declared compatibility promise and had never actually been
    exercised.
  - All three 3.11 cells fail one further test that passes on 3.10, 3.12 and 3.13 with the same
    substrates — a CPython parse-depth difference, reproducible with the standard library
    alone, on the interpreter axis the old two-Python corner matrix could not see.
  - `mypy` is red on all 13 cells, and in the pre-existing `typecheck` job, for a reason that
    predates this card entirely: from a *cold* cache it reports two `--strict` errors whose
    message text carries a lone surrogate, and then crashes writing that text into its own
    cache — on a strict-UTF-8 pipe, which is what CI log capture is, it crashes while printing
    them, so the job shows an opaque internal error rather than the two lines behind it. A warm
    cache reports success, which is why it had gone unnoticed; a CI runner is always cold.
    Reproduce with `mypy --no-incremental`.

  All of it is left **blocking** rather than downgraded, which is what the version-compatibility
  policy requires. Closing each gap is separate, tracked work.

- **`docs/specs/CLI-SPEC.md` — the `gebra` command-line interface** (card CLI-02). The second
  of D-12's two contract artifacts: the verb set, how an invocation names what it operates on,
  the exit codes it returns, and the conventions its diagnostics follow. Like its sibling it is
  a specification, not an implementation — there is no `gebra` command, the package declares no
  console script, and the document says so.

  **Five verbs, and the fifth is `history`.** `verify | snapshot | diff | display | history`,
  per the CLI-D4 ruling (PD-033) that retired `trace` before it shipped — not as an alias or a
  deprecation shim, but as a name that does not exist. Each verb gets its arguments, its flags,
  what it writes and where, and its failure modes; Appendix A consolidates every flag against
  every verb, including the two absences (`snapshot`/`diff` have no `--format`; no verb has
  property selection or a config file) that are decisions rather than oversights.

  **A complete exit-code table.** PROPERTY-CATALOG-SPEC §0.2's three codes, restated and then
  assigned per verb with the condition in every cell — including the cells that read *never*,
  because `display` and `history` reach no gate. `verify` returns `gate.exit_code` from the run
  report and derives nothing beside it; `snapshot` applies §0.2's own recording refusal by
  reading `gate.snapshot_eligible`, with no flag to bypass it; `diff --exit-code` is an opt-in
  difference signal that carries no safe/breaking claim, since P-12 stays deferred and the
  marker renders as *not checked*. Usage errors are exit `2`, an interrupt is `130`, and a
  crash is a tool error rather than a finding.

  **Subject resolution, decided.** Three input modes matching the run report's own
  `Subject.input_mode` — a live import target, an IR document, a stored version — reached by one
  positional target whose grammar decides the mode (V.S.F.E label, then IR suffix, then import
  reference; the ordering is normative and the regexes are executed by a test), with explicit
  `--ir`/`--import`/`--snapshot` selectors that skip detection. Resolving an import target
  imports the module and reads the attribute — and then **refuses anything that is not already
  a workflow object** unless the invocation passed `--call`, which is the one path on which the
  CLI executes user code, calls once with no arguments, and probes no signature (a signature
  probe runs user code too, and "takes no arguments" does not tell a graph factory apart from
  an application entry point). The three verbs that can reach a live object each carry a
  never-invokes tripwire obligation in the spec, in the `BaseException`-sentinel,
  record-before-raise shape, asserted on the recorded call list rather than on an exit code.

  **Diagnostics per PD-031**, with `rich`, a degradation matrix covering `NO_COLOR`,
  `TERM=dumb`, non-tty capture and the explicit overrides, a stream split that keeps
  `--format json` output parseable, multi-error reporting in one pass, and did-you-mean
  suggestions scoped to closed vocabularies and to display only. The source anchors D-12 wanted
  are declared absent rather than faked: IR 1.0 carries no spans.

  **No configuration file, and no `GEBRA_*` environment variables** — the command line is the
  whole policy surface, `gebra.toml` stays the annotation sidecar it already is, and an
  invisible input to a CI gate is one a reviewer cannot see. `tests/docs/test_cli_spec.py`
  holds the document to the package: the verb set, the exit-code table's completeness, the
  input modes and tool-error stages read out of REPORT-FORMAT-SPEC's own model stubs, the
  disjointness of the two target grammars, and every package symbol the spec names.

- **`docs/specs/REPORT-FORMAT-SPEC.md` — the run-level report format** (card CLI-01). The
  contract PROPERTY-CATALOG-SPEC §0.3 hands out at its scope boundary: the wrapper around all
  thirteen `PropertyReport`s, plus IR identity, exit-code derivation and the serialization
  profile. It is a specification, not an implementation — no `gebra` command exists yet, and
  the document says so.

  **One document, three surfaces** (per PD-015, the CLI-D1 ruling): the native JSON of
  `--format json` is the run report itself, lossless; the default terminal output is a
  rendering of it; `--format sarif` is a lossy, findings-only projection. The wrapper is
  fixed as normative model stubs — `RunReport{report_format, tool, subject, properties, gate,
  error?}`, whose thirteen `properties` entries are the `NotImplementedMarker | PropertyReport`
  union `run_property()` already returns — with a `report_format` versioning policy and a
  serialization profile that carries no wall-clock field, so a report over one unchanged
  workflow is byte-reproducible.

  **Exit codes, derived once.** §0.2's ladder over a whole run: which records count as
  findings, how strict mode reaches WARNING failures, co-failures, advisories *and*
  warning-grade witness notes (matching on the record's owning property, not its host
  report), why promotion never rewrites the record, and why a missing wedge validator is a
  tool error rather than a thin gate. Snapshot eligibility is carried as a field so the CLI
  and the snapshot engines read one rule.

  **A rendering for every §0.3 variant.** Each of the 36 envelope models — five witnesses and
  their substructures, the failure records, the six anchors and six concrete locations, the
  not-implemented marker — has a row stating what the native JSON, the human surface and the
  SARIF projection do with it, including where SARIF drops it and why. Layout stays the
  renderer's; the fact set and the honest-claims copy rules do not.
  `tests/docs/test_report_format_spec.py` holds the document to the live models: a variant with
  no row, or a SARIF rule table that disagrees with the §0.4 registry about a severity or a
  claim class, fails a test.

  **Appendix A restates the SARIF mapping as an exporter contract**, with the `rules[]` catalog
  derived from the §0.4 registry's thirteen *emittable* condition IDs (held names never get a
  rule), fingerprint construction, and one honest gap: IR 1.0 carries no source spans, so
  results carry logical locations only and a Phase-0 SARIF log may not surface as GitHub
  code-scanning annotations. Fabricating an anchor to satisfy the ingestion path is refused.
  The optional `sarif-full` profile stays deferred.

  **§6 ratifies SD-07's audit-export schema**: the per-version export at
  `.gebra/reports/<version>.report.json` is the same `RunReport` in a snapshot profile, so
  there is no second schema and no second version line to keep in step.

- **Mutation operators and the contract/advisory metaproperty suite — `gebra.testing.mutations`**
  — the adversarial half of the hypothesis work: an operator takes a well-formed draw, breaks
  exactly one property at exactly one point, and hands back the verdict the validator that owns
  it must reach:

  ```python
  from hypothesis import given

  from gebra.testing.mutations import Mutation, dataflow_mutations
  from gebra.verify.properties.dataflow_completeness import check_dataflow_completeness


  @given(mutation=dataflow_mutations())
  def test_p04_says_what_the_operator_injected(mutation: Mutation) -> None:
      assert check_dataflow_completeness(mutation.origin).result == "pass"

      report = check_dataflow_completeness(mutation.ir)

      assert (report.result == "fail") == mutation.breaking
      if mutation.breaking:
          assert report.failure.property_condition == mutation.condition
          assert report.failure.location.node == mutation.node
  ```

  **Seventeen operators over the three contract and advisory validators.** P-04
  `dataflow-completeness`: a read no path writes, a node that writes only what it reads
  (first-arrival semantics), the `optional: true` boundary flip, a universally-written key, and
  a read of a key outside Σ. P-06 `effect-safety`: an unprotected trigger tag in a retry region
  and on a fresh cycle, the FATAL `irreversible` + keyless combination, an idempotency key that
  does not bind, a compensation hook that resolves to nothing — plus the two protections that
  discharge the obligation. P-08 `determinism-replay`: a bare claim on a node whose effects
  evidence a remote provider call, an unpinned or nonzero temperature, the two coherent claims,
  and the explicit `deterministic: false` disclaimer.

  **"Breaks exactly one property", made checkable.** A `Mutation` carries the *normalized*
  origin as well as the mutant, so the claim is about the pair: between them the only verdict
  that moves is the operator's target, and it moves exactly when the operator is a breaking one.
  That is asserted at scale over every operator, P-01 included — so a contract or advisory
  mutation never quietly damages the topology the other verdicts are defined over.

  **Thirty metaproperties, each at 1000 examples with no health check suppressed**
  (`tests/testing/test_metaproperties_contract.py`), against a target of twenty. They cover the
  must-write analysis and the validity of the path it attributes a violation to; the protection
  lattice and the reality of every cycle P-06 names; PROPERTY-CATALOG-SPEC §8.7's "must not
  couple to topology", mechanized by rewiring the graph under the advisory and comparing the
  report; and, over every operator at once, validator determinism, §0.4 condition-ID closure
  with the registry's own severity and claim-class grading, §0.3 envelope round-tripping and
  packaging, and the shared-graph-model seam. The count is machine-checked against the module,
  as is the example count, so a deleted metaproperty or a quietly reduced budget fails a test
  rather than weakening a claim that keeps its name.

  **`hypothesis` stays a development dependency**, on the same terms as the strategy library:
  `gebra.testing` does not import this module, and importing `gebra.testing.mutations` without
  hypothesis raises an `ImportError` naming this module and the extra.
  **Nothing here executes a workflow node, a model call or document content** (WA-07): the
  operators rewrite frozen pydantic values into new frozen pydantic values through the
  constructors, and everything run is in-repo and hermetic — the wedge validators and the shared
  graph pre-analysis, over serialized IR. The tripwire's guarded child now runs
  P-04, P-06 and P-08 over deliberately broken IR — a dangling compensation hook, an unwritten
  read, a determinism claim on a remote-provider node — in an interpreter where a substrate
  import, a socket and a name resolution each raise.

- **Hypothesis strategies for well-formed IR — `gebra.testing.strategies`** — generation for
  the properties a fixture corpus cannot cover, because the interesting shape space is larger
  than any hand-written set of files:

  ```python
  from hypothesis import given

  from gebra.ir import WorkflowIR
  from gebra.ir.canonical import graph_version
  from gebra.testing.strategies import WIDE_ENVELOPE, workflow_irs


  @given(ir=workflow_irs())
  def test_every_well_formed_workflow_has_a_digest(ir: WorkflowIR) -> None:
      assert graph_version(ir).startswith("sha256:")


  @given(ir=workflow_irs(envelope=WIDE_ENVELOPE))  # denser graphs, deeper ids
  def test_the_same_over_bigger_shapes(ir: WorkflowIR) -> None:
      assert graph_version(ir).startswith("sha256:")
  ```

  **What every draw satisfies**, tested rather than asserted in prose: it validates at
  `ir_version` 1.0 and reloads identically through `dump_json`/`load_json`; every
  `nodes[].id` is grammatical under IR-SPEC §5 and the ids are distinct; every reference
  resolves — `entry`, `finish`, an edge's `from`, a `normal`/`send` edge's `to`, every
  `path_map` value, `runtime.interrupts`, `annotations.compensation.hook`; the graph is
  **P-01 clean**, checked by running `graph-well-formed` itself over each draw rather than by
  re-deriving its conditions; the IR-SPEC §2.3 cross-field obligations hold
  (`input`/`output` ⊆ `keys(state)`, `idempotent.key` ∈ `input`); and every scalar is inside
  the §6.3 exact ranges, so `graph_version` never refuses a draw. The conjunction runs at
  1000 examples on each of the three size envelopes with no health check suppressed.
  **Verdicts other than P-01's are deliberately free.** A draw may or may not have a
  termination witness, complete dataflow, safe effects or pinned determinism — that variation
  is what the mutation suites will range over, and PROPERTY-CATALOG-SPEC §0.3 defines those
  validators over P-01-clean topology, which is what the strategies supply.
  **Sizes are envelopes, not knobs scattered through the code.** `SizeEnvelope` is a frozen
  record of maxima with three presets (`MINIMAL_ENVELOPE`, `DEFAULT_ENVELOPE`,
  `WIDE_ENVELOPE`); the minima are structural, which is what makes every counterexample shrink
  to the same floor — one node, `entry == finish ==` that node, and nothing else. Composition
  seams are explicit: `topologies()` yields the graph before any content is attached, and
  `workflow_irs()` takes a topology or a state schema to build around.
  **`hypothesis` stays a development dependency.** `gebra.testing` does not import this module,
  so `import gebra.testing` needs no hypothesis (test-proven in an interpreter where importing
  it raises); importing `gebra.testing.strategies` without it raises an `ImportError` that says
  which package and which extra.
  **Nothing here executes anything** (WA-07): the strategies build frozen pydantic values out
  of generated primitives, and the WA-07 tripwire's guarded child now generates from them and
  runs P-01 over each draw in an interpreter where a substrate import, a socket and a name
  resolution each raise.

- **`gebra.extract()` checks the installed substrate against the tested version matrix** —
  once per process, on the first call, per VERSION-COMPAT.md §4:

  ```python
  import gebra

  gebra.extract(builder)  # langgraph 1.0.5 + langchain-core 1.3.0: both in range, untested
  # UserWarning (gebra.extraction.GebraVersionWarning): gebra has not been tested against
  # this exact substrate pairing — …

  gebra.extract(builder)  # same process, second call: silent — the warning is warn-once
  ```

  **Three outcomes, never a fourth.** A pairing inside one of VERSION-COMPAT §1's three
  frozen cells, on a tested Python (3.10-3.13), is silent. An install where every package is
  individually within its declared `>=1.0,<2.0` range (Python has no declared ceiling) but
  the *pairing* is untested — or Python is above 3.13 — warns `GebraVersionWarning` once per
  process, never more. An install outside the declared range (`langgraph`/`langchain-core`
  `<1.0` or `>=2.0`, or Python `<3.10`) proceeds best-effort: no Python warning, but every
  envelope produced while the install stays out of range carries an `unsupported-construct`
  extraction warning naming the installed versions — an envelope is a record of one
  extraction, so the fact rides every one of them, not just the first.
  **`import gebra` never runs this check and never fails on version grounds.** The warning
  and the envelope fact are wired into `extract()` alone; a bare `import gebra` never
  reaches either, checked with warnings promoted to errors (`python -W error -c "import
  gebra"`) and by asserting a bare import never calls the version reader at all.
  **Nothing here imports langgraph or langchain-core.** Only their installed-distribution
  *metadata* (`importlib.metadata.version`) and `sys.version_info` are read.

- **A store's version history is queryable — `gebra.lineage.lineage`** — every version a
  `.gebra/` store holds, in the store's own order, with its digest, when it landed, and the
  V.S.F.E step from the version before it:

  ```python
  from gebra.lineage import dump_lineage, lineage

  history = lineage(store)

  history.versions  # ('1.0.0.0', '1.1.1.0', '1.1.2.0', '1.1.2.1')
  history.newest.graph_version  # 'sha256:296bc4bf…'
  history.newest.step.bump_class  # (Component.E,)
  history.newest.step.content_changed  # True

  lineage(store, limit=2).versions  # the two most recent
  lineage(store, since="1.1.1.0", until="1.1.2.0").versions
  dump_lineage(history)  # canonical JSON, byte-stable
  ```

  **A listing reads one file.** It opens `meta.yaml` and never a snapshot, so listing a
  hundred versions is one read — and what it reports is what the *index* records. Whether
  each snapshot file still hashes to the digest beside it is a different question with its
  own answer, `SnapshotStore.check()`.
  **Two different questions about a pair, and both are available.** `step.bump_class` is what
  the two *labels* record — which of V, S, F and E counts higher than on the row before.
  `gebra.lineage.compare(store, before, after)` is what the *content* says: both snapshots
  read and run through `workflow_diff`. Nothing in the store makes a label describe what
  changed, so the two can disagree over S, F and E, and neither is quietly preferred. They are
  comparable over those three and nowhere else: a diff never reports V, since the frozen
  scheme defines S, F and E and says nothing about what V counts — so a `1.x → 2.x` step is
  not a disagreement, it is outside the domain a diff speaks about. A step also reports which
  counters went *down*, because a history is not required to be label-monotonic, and reports
  nothing at all for a label outside the V.S.F.E grammar — the store's floor on a label is
  path-safety, not that grammar, so a listing stays total over what the store accepts.
  **One order, and a window that never lies about the whole.** Oldest first, the store's own
  append order; `since`/`until` are inclusive anchors and `limit` keeps the most recent rows.
  Whatever the window, `total`, `omitted_before`, `omitted_after` and each row's absolute
  `index` ride along, and a page's first row still reports its true predecessor in the store.
  **The output is a stable document.** `dump_lineage` emits canonical JSON through the same
  RFC 8785 emitter the content digest goes through, with one trailing newline, so a history
  can be held in a golden file; `lineage_document` is the same shape as a mapping. Members
  that do not apply are absent rather than null — no step on the oldest version, no bump
  class between labels that are not both V.S.F.E — so the mapping and its text describe one
  shape exactly.
  **Nothing here grades a change.** A step names which counters moved; a comparison returns a
  diff carrying the deferred-P-12 marker where a safe/breaking classification would sit.
  This is the engine, not a command: which verb exposes it, and what that verb's output looks
  like, is the CLI track's open question.

- **A diff says which V.S.F.E counters a change bumps — `gebra.diff.workflow_diff`** — the
  topology diff below, plus the contract and state-schema deltas, plus the bump class
  derived from them:

  ```python
  from gebra.diff import workflow_diff
  from gebra.versioning import Version

  diff = workflow_diff(store.read("1.4.2.0"), working_ir)

  diff.contracts.changed
  # (NodeContractChanged(node="book_flight", present_before=True, present_after=True,
  #                      slots=(SlotChange(slot="effect", before='["network"]',
  #                                        after='["billable","irreversible"]'),)),)
  diff.state.added
  # (StateKeyRef(key="hotel", declaration=KeyDeclaration(type="str", optional=True)),)
  diff.bump_class
  # frozenset({Component.F, Component.E})
  str(diff.bump(Version.parse("1.4.2.0")))
  # '1.4.3.1'
  ```

  **The class is read off the deltas, and it agrees with the version engine.** S when the
  topology moved, F when a node contract or the graph-level `runtime` block did, E when the
  state schema did. That is checked against `gebra.versioning`'s own `changed_components`
  on every constructed pair and over generated ones, in both directions — a component the
  diff failed to report would put a second workflow content under a label that already
  names one, and a label is a snapshot's file name.
  **Contract changes are reported slot by slot, valued in the canonical JSON the digest
  sees.** `effect`, `deterministic`, `variant`, `retry_policy`, `prompt_digest` and the rest
  each report their two sides; a node that gained or lost its `annotations` object entirely
  reports that too, since an empty contract and no contract are different content. State
  keys report per key, split into `type`, `reducer` and `optional`, so a key kept and
  re-declared reads as a retype rather than as a removal and an addition.
  **One flag exists for a change no routing graph can show.** Conditional edges are
  label-expanded before any graph algorithm runs, so merging two routers into one — or
  splitting one into two — leaves every route identical while the authored `edges` array,
  and with it the content digest, moves. `diff.regrouped` says so, which is what keeps the
  derived S bump honest.
  **A workflow that declares one node id twice is refused, not diffed.** Node ids must be
  unique within a document; every delta here is anchored on node identity, and such a document
  has none to anchor on — so it raises, naming the rule, rather than report a collapsed
  answer. Nothing extraction produces can hit this: substrate node names are dictionary keys,
  and it is reachable only by hand-building an IR.
  **No part of the output grades the change.** Every diff carries the property registry's
  own structured marker for P-12 `evolution-safety` — `status="deferred-to-phase-1"` — in
  the slot where a classification would sit. Phase 0 ships no safe/breaking classifier, and
  a test sweeps every string a diff renders to keep it that way.

- **Two workflow versions can be structurally diffed — `gebra.diff.topology_diff`** — a
  topology diff over networkx between two snapshots or IRs, reporting nodes and edges added,
  removed and rewired:

  ```python
  from gebra.diff import topology_diff

  diff = topology_diff(store.read("1.0.0.0"), store.read("1.1.0.0"))

  diff.nodes.added
  # ("audit",)
  diff.nodes.rewired
  # ("report",) — kept its identity, its connections moved
  diff.edges.changed
  # (EdgeChanged(kind="conditional", source="plan", label="done",
  #              target_before="work", target_after="audit", ...),)
  ```

  **The diff is anchored on node identity and on `graph_version`.** A node is its id and
  nothing else, so a renamed node is a new node — one removal plus one addition, never a
  fuzzy match. Both sides are named by their recomputed content digest: equal digests
  short-circuit to the empty diff, and each side taken from a snapshot carries its V.S.F.E
  label on the anchor. A snapshot whose stored digest disagrees with its own IR is refused
  rather than diffed under a wrong anchor.
  **"Changed" needs a persisting authored identity.** A router label whose target or guard
  moved, or the one remaining out-edge of a node whose target or guard moved, reports as a
  change with both sides shown; everything else — an edge re-kinded, a label renamed — is
  a removal plus an addition, because nothing authored ties the two sides together.
  **What the diff sees is the expanded routing graph, compared the way the digest compares
  content.** Reordered nodes or edges and a duplicated `entry` member are not changes here,
  exactly as they are not `graph_version` changes. And whenever the diff reports anything,
  the version engine's S counter moves for the same pair.
  **An empty topology diff does not mean nothing changed** — it means the expanded topology
  graph did not. Contract and state-schema changes are outside *this* function's scope, and
  so is re-grouping inside the `edges` field itself: two routers merged into one with every
  labeled route preserved keep the same graph, while the digest — and the S counter, which
  counts the authored field — still move. `workflow_diff` above covers all three.
  **No part of the diff calls a change safe.** It reports structure — what was added,
  removed, rewired — and nothing about what the change means.

- **Version numbers can be read, compared and derived — `gebra.versioning`** — the V.S.F.E
  scheme (S for topology, F for node contracts, E for the state schema) as a small engine
  that takes two IRs and a label and answers what the next label is:

  ```python
  from gebra.versioning import Version, changed_components, next_version

  changed_components(stored_ir, working_ir)
  # frozenset({Component.S, Component.E})   — the topology and the state schema moved
  str(next_version(Version.parse("1.4.2.0"), stored_ir, working_ir))
  # '1.5.2.1'
  ```

  **A label says which part of the workflow moved.** S counts topology changes — nodes,
  edges, START/END wiring; F counts contract changes — a node's `@gebra.effect`,
  `@gebra.deterministic`, `@gebra.variant` and the rest, plus the graph-level `runtime`
  block; E counts state-schema changes. Reading `1.4.2.0 → 1.5.2.1` tells you the topology
  and the schema moved and the contracts did not, before you open a diff. A prompt-body edit
  moves F: `prompt_digest` is part of a node's contract, so an edited prompt is a changed
  contract, not an invisible one.
  **The counters are independent — a bump resets nothing.** One change can move more than
  one of them, and the F counter still reads how many contract changes this workflow has
  seen since it was first snapshotted. Any change moves the version strictly forward, so
  sorting versions and sorting by when they were taken give the same order.
  **The comparison is by content, not by how the file was written.** Nodes listed in
  another order, an `entry` written as a one-element list, a state value written in its
  object form instead of as a bare type name — none of these is a new version, because none
  of them changes `graph_version`. The engine compares the same canonical form the digest is
  taken over, so the two do not disagree about whether a workflow changed.
  **Adding or removing a node moves S and F together**: the topology gained a vertex and the
  contract set gained a member (an empty one, if the node carries no contract). A rename is
  the same case — node identity is structural, so a renamed node is a new node.
  **`V` is yours.** Nothing in a workflow bumps the leading component; the engine carries it
  through untouched, for whatever generation you want to mark by hand.
  **What a version does not tell you** is *what* changed — for topology that is
  `gebra.diff`'s structural diff; contract and state-schema deltas have no diff engine yet
  — or whether a change is safe or breaking. No part of this classifies a change as safe.

- **A workflow's IR can be written to a `.gebra/` snapshot store and read back** —
  `gebra.store` persists an IR under the snapshot envelope (`version`, `extracted_from`,
  `graph_version`) and reads it back equal to what was written:

  ```python
  from gebra.store import ExtractedFrom, Snapshot, SnapshotStore

  snapshot = Snapshot.of(
      ir,
      version="1.0.0.0",
      extracted_from=ExtractedFrom(
          source="travel_booking:build_graph",
          extractor_version="0.0.1.dev0",
          extracted_at="2026-08-04T09:00:00Z",
      ),
  )
  store = SnapshotStore.for_project(project_root)
  store.write(snapshot)  # .gebra/snapshots/1.0.0.0.yaml + .gebra/meta.yaml
  store.read("1.0.0.0") == snapshot
  # True
  ```

  **The files are meant to be committed.** One snapshot per version, YAML in your models'
  own field order, block style, non-ASCII left as itself, LF endings, one trailing newline —
  so `git diff` on `.gebra/` shows what changed in the workflow rather than what the emitter
  felt like doing that morning. The same snapshot written twice produces byte-identical
  files, in the same process or in two runs under different `PYTHONHASHSEED`s: nothing in
  the store reads a clock, iterates a `set`, or otherwise varies per run. A write is a
  function of its arguments.
  **Every write is atomic** — the text goes to a temp file in the target's own directory, is
  flushed and `fsync`ed, and is then swapped in with `os.replace`. A reader never sees half
  a document. Across the two files a write touches, the snapshot lands before the index, so
  an interruption between them leaves a snapshot file the index does not mention — which
  every reader ignores, and which re-running the write completes. `SnapshotStore.check()`
  reports the whole store's state in one call, separating actual problems from that kind of
  harmless leftover.
  **A snapshot's `graph_version` is checked against its own IR** on every write and every
  read — recompute and string-compare, IR-SPEC §6.1 step 9. Editing the IR inside a stored
  file without touching its digest is caught rather than believed. Nothing is repaired
  behind your back: a damaged file is reported with a code you can branch on, and
  `read(version, verify=False)` is there for when you need to look at what is wrong.
  **A prompt edit is a new snapshot, not a silent overwrite.** Because `prompt_digest` and
  `config_digest` are inside the hash scope, two versions of a workflow that differ only in
  prompt text carry different `graph_version`s and land as two distinct files. With those
  slots empty they would be the same document — node bodies are opaque to the IR — which is
  exactly the gap those digests close. The prompt text itself is not in the file; only the
  fingerprint is.
  **The version label is a string this layer stores and never parses.** Parsing, comparing
  and bumping it is `gebra.versioning`'s job (below); deciding which version a newly
  extracted workflow gets, structural diff between two snapshots, the audit export under
  `.gebra/reports/`, and the `gebra snapshot` command are all still to come. What the label
  is checked for here is that it can safely be a file name.

- **A prompt edit changes `graph_version`** — nodes bound to a prompt template or to a chat
  model now carry `prompt_digest` / `config_digest`, so editing prompt text or a generation
  parameter moves the workflow's version exactly as editing an edge does:

  ```python
  chain = ChatPromptTemplate.from_messages([("system", "Be terse.")]) | model
  envelope = gebra.extract(chain)

  envelope.ir.nodes[0].annotations.prompt_digest
  # 'sha256:9c4f…'
  envelope.ir.nodes[1].annotations.config_digest
  # 'sha256:c7dd…'
  ```

  **The prompt itself never enters the IR** — only the fingerprint. Nothing gebra writes down
  contains your prompt text, your system message, or a value from your model config; a
  workflow's extracted document stays safe to commit, diff and publish. That is also why the
  digests exist: without them two workflows differing only in prompt text extract to identical
  documents with identical versions.
  **The digest is over a fixed projection, not over whatever a library happens to serialize.**
  A string template digests the exact UTF-8 bytes of its template — no trimming, no
  normalization. A chat template digests a canonical form over its messages in the order you
  wrote them, covering role-tagged message templates, `MessagesPlaceholder`, and static
  `SystemMessage`/`HumanMessage`/`AIMessage`/`ChatMessage`/`ToolMessage`. A model digests its
  class identity, its declared fields, and the kwargs of any `.bind()`-style wrapper around it
  (outermost wins), with secret-typed fields left out and `with_config` metadata excluded.
  **Two runs on two machines give the same digest.** Nothing time-, address- or
  environment-dependent reaches the bytes: a value gebra cannot represent in JSON is recorded
  by its *class name* rather than by `repr()` (which would embed a memory address), a
  `set`-valued parameter is ordered by content rather than by Python's per-process hash order,
  and the digest projection itself calls no property, method or `repr` on your model or your
  prompt — it reads declared pydantic fields and template attributes only. (One honest edge:
  Python lets a class override attribute access itself — a base-class `@property` shadowing a
  declared field, or a custom `__getattr__` — and such code runs on *any* attribute read;
  gebra reads the declared fields as pydantic defines them and does not scan for overrides.)
  **Two things it deliberately does not notice**, so they are worth stating: `template_format`
  and `input_variables`/`partial_variables` are not digested (two templates with identical text
  share a digest), and neither is anything passed through `with_config`.
  **One thing it does notice that may surprise you**: LangChain stamps its own version into a
  chat model's `metadata` field when you construct it, and that field is part of the config
  gebra digests — so upgrading `langchain-core` changes `config_digest`, and with it
  `graph_version`, for every model-bearing workflow.
  **Where a digest cannot be computed, it is absent and said so**: a prompt-template class
  outside the recognised set (a few-shot template, an image content part) leaves the slot empty
  and reports `unsupported-construct` naming the class — never a partial digest over the part
  gebra understood. A model reached only through a wrapper class gebra will not read gets no
  digest, and the existing `lcel-composition-not-stock` warning is what names it. (When this
  entry first landed that included `model.bind(...)`, whose LangChain-internal subclass was kept
  opaque; the EX-16 entry under *Changed* below admits the enumerated stock subclasses and closes
  that case, so a tool-bound model does carry a `config_digest`. Nothing has released between the
  two entries — this one is left as written with the correction beside it rather than rewritten,
  since it is the record of what that change shipped.)
  Digests are never rolled up onto a parent: the node whose own bound object is the template or
  the model is the one that carries the slot.

- **`gebra.extract()` takes an LCEL chain** — the third and last object family is wired in, so
  a bare `Runnable` extracts instead of being refused:

  ```python
  chain = RunnableLambda(plan) | RunnableParallel(docs=fetch, meta=describe)
  envelope = gebra.extract(chain)

  [node.id for node in envelope.ir.nodes]
  # ['%seq[0]', '%seq[1]', '%seq[1]/%map[docs]', '%seq[1]/%map[meta]']
  ```

  **The ids are structural, not names.** A chain's steps have no user-given names, so each one
  is keyed by where it sits: `%kind[selector]`, where `kind` is what holds it (`seq`, `map`,
  `branch`, `lambda`, `retry`, `fallback`, `bind`) and `selector` is its source key when it has
  one (a `RunnableParallel` dict key) and its position when it does not. A nested chain hangs
  off its parent's id with `/`, so containment is readable straight off an id. LangChain's own
  drawing ids are fresh UUIDs on every call and are never used — gebra reads the composition
  from the objects themselves and never draws at all.
  **Re-extracting an unchanged chain gives byte-identical ids and the same `graph_version`**,
  including across separate processes. That is worth stating because it is not free: LangChain
  reports a lambda's captured runnables in an order that can differ between runs, so gebra
  derives that order from the function's own compiled form instead of taking it as given.
  **Steps you have not annotated take the conservative default.** A stitched lambda body is
  opaque, so it gets `effect: ["write"]` — never `pure`, never `idempotent` — and says so with
  an `opaque-lambda` warning naming the node id you can attach a contract to, either with
  `@gebra.contract` on the function or with a `gebra.toml` entry keyed by that id.
  **Composition gebra will not read, it reports rather than guesses**: a subclass of one of the
  seven composition types (it could answer with code of its own, which gebra never runs), a
  lambda whose captured runnables sit behind an attribute of one of your own objects, a
  composition that contains itself, and one nested deeper than 32 levels. Each is one
  `unsupported-construct` warning naming what was not read.
  **Two limits worth knowing.** A `Runnable` that is none of the seven types and composes
  nothing — a bare `RunnablePassthrough`, a chat model on its own — has no id under this
  version's vocabulary and is refused rather than given an invented one; the same object is
  extracted normally *inside* a chain, where its position names it. And a chain bound as a
  node of a `StateGraph` is still extracted as that one node: expanding it in place is not part
  of this release.

- **`gebra.extract()` takes a compiled graph** — the second of the three object families is
  wired in, so a `CompiledStateGraph` (or any other Pregel object) extracts instead of being
  refused:

  ```python
  compiled = builder.compile(interrupt_before=["book"], checkpointer=saver)
  envelope = gebra.extract(compiled)

  envelope.ir.runtime.interrupts.before  # ('book',)
  envelope.ir.runtime.checkpointer  # Checkpointer(present=True)
  ```

  **The builder is what defines the graph.** Everything about topology, state and per-node
  declarations comes from the `.builder` backreference, exactly as if you had passed the
  uncompiled builder — extracting before and after `.compile()` gives you the same nodes, the
  same edges, the same state block and the same contracts. What compiling adds is the
  `runtime` block: which nodes are interrupt-gated (a `"*"` gate is expanded to the full node
  list) and whether a checkpointer is attached. Checkpointer presence is recorded either way,
  `true` or `false`, because at the compiled level it is a known fact; at the builder level the
  slot stays absent rather than being guessed. That means a compiled workflow and the same
  workflow before compiling have **different `graph_version` digests** — snapshot one level and
  stay on it. One further difference is LangGraph's rather than gebra's, and worth knowing if
  you use `set_node_defaults`: `compile()` writes those defaults into the builder's own node
  specs, so a `retry_policy` you never declared per node appears in the IR from the moment you
  compile, whichever level you then extract. The envelope records which nodes got theirs that
  way.
  **When the two levels disagree, the builder wins and the disagreement is reported.** gebra
  cross-checks the builder's topology against the compiled graph's own drawing; if they differ,
  the IR keeps the builder's reading unchanged and a `builder-compiled-divergence` warning
  carries both readings.
  **That drawing is the one thing gebra calls, and it is gated.** Producing it walks the
  compiled graph symbolically, and on langgraph 1.2.10 that walk reaches your code in five
  places — a custom channel's `get()`, a custom checkpointer's `get_next_version()`, a node's
  cache key function, a `ChannelWrite` mapper, and a `__root__` channel's value type, which it
  *constructs*. So gebra takes the drawing only from a real LangGraph `Pregel` whose channels,
  checkpointer, cache key functions and write mappers all come from LangGraph itself, at the
  graph and at every subgraph. Otherwise the cross-check is skipped, with the reason recorded in
  the envelope's provenance — so a run with no divergence warning is never ambiguous about
  whether the comparison happened.
  **Facts the IR has no field for are recorded beside it**, not dropped: which nodes carry a
  discovered subgraph, which node-spec members were filled in by `set_node_defaults` rather than
  declared, and the error-handler map.
  **A subgraph comes across as the node that holds it.** IR 1.0 carries a discovered subgraph as
  its parent node — the child's own nodes, edges and state are not expanded — and the envelope's
  provenance names which nodes those are. That is the complete form for this version, not a
  partial one: a workflow with subgraphs is warning-free like any other and can pass a
  warning-free check. Expanding children is the next version's first feature. One limit worth
  knowing: a subgraph compiled with `checkpointer=False` is invisible to LangGraph's own
  discovery, so the recorded list is a lower bound — nothing can report what it cannot see.
  **A Pregel object with no builder extracts from the compiled level alone**, with a single
  `compiled-only-extraction` warning saying so: the topology comes from the graph's own drawing,
  the state block is absent rather than guessed, and node contracts fall to the conservative
  defaults — a `gebra.toml` entry still applies. Here the drawing is the only surface there is,
  so an object that fails the gate above is refused with a typed error instead. That includes
  `RemoteGraph`, whose `get_graph()` is an HTTP call: `gebra.extract()` never opens a network
  connection, so it declines rather than fetching.
- **Node contracts now reach the IR** — the three declaration surfaces gebra already had are
  resolved against each other, per slot, and the result lands on the node. The order is fixed:
  a `@gebra.contract` decorator wins, then a LangChain tool's own `args_schema`, then a
  `gebra.toml` entry, then shallow inference fills whatever is left:

  ```python
  @gebra.contract(reads=["query"], writes=["plan"], effects=["network"])
  def plan_step(state: State) -> State: ...


  gebra.extract(builder).ir.nodes[0].annotations
  # Annotations(input=("query",), output=("plan",), effect=("network",))
  ```

  **A lower source fills gaps; it never overrides.** A `gebra.toml` entry that sets a slot the
  decorator already set to a *different* value is kept out, and the disagreement is reported as
  an `annotation-conflict` warning naming the node, the slot, both values and both sources.
  Two sources that say the same thing are not a disagreement, and "the same thing" is decided
  on the IR's own canonical bytes — so `reads=["b", "a"]` and `reads = ["a", "b"]` are one
  declaration, and a decorator's `temperature=0.0` and a TOML `temperature = 0` are one value.
  **A contract nobody wrote as a whole is checked as a whole.** Gap-filling can assemble a
  node that is `pure` in one source and effectful in another, or whose idempotency key names a
  state key its declared reads do not include. Every node's *resolved* contract is validated
  against the same rules the decorator enforces at import time; a violation drops the
  lower-precedence half and reports an `annotation-invalid` warning naming the rule, the slots,
  the sources and the values. It is never an error — a stale sidecar degrades visibly rather
  than bricking extraction. When a heuristic input set is what a declared key was checked
  against, the report says so and nothing is dropped.
  **Contracts survive `.compile()`.** Extraction follows `functools.wraps` chains and the
  substrate's own wrappers to find the callable you decorated, so extracting a workflow before
  and after compiling it yields identical contracts (there is a committed golden for it). If
  two callables in one chain carry different contracts, the outermost wins whole and both are
  named in a warning. A user decorator that does *not* apply `functools.wraps` hides the
  declaration — indistinguishable from never having written one, which is why `functools.wraps`
  is the thing to remember.
  **Every heuristic slot says it is one.** A slot filled by inference or by the conservative
  default carries a `contract-inferred` or `contract-defaulted` warning naming the node and the
  slot, which is how a later check can tell what you declared from what gebra guessed.
  A node with no declaration anywhere therefore gets the conservative default and a warning
  saying so — `effect: ["write"]` where the node writes state, `pure: true` where nothing in
  the body says it does. That is a no-evidence-found result, not a finding about the node.
  Nothing about any of this runs your code: the wrapper chain is attribute reads, a tool's
  `args_schema` is read by pydantic introspection, and node bodies are parsed, never called.
- **The state schema in the IR** — `gebra.extract()` now fills the `state` block, so an
  extracted workflow carries what its keys are as well as how its nodes are wired.
  `TypedDict`, pydantic and dataclass state schemas are all read, and each key comes across
  with its declared type, the `Annotated[T, reducer]` merge function where it has one, and an
  `optional` flag for the keys that arrive from outside:

  ```python
  class State(TypedDict):
      task: str
      notes: Annotated[list[str], operator.add]
      draft: str


  class Input(TypedDict):
      task: str


  gebra.extract(StateGraph(State, input_schema=Input)).ir.state
  # {"task":  StateField(type="str", optional=True),
  #  "notes": StateField(type="list[str]", reducer="_operator.add"),
  #  "draft": "str"}
  ```

  **`optional` follows what your graph declares, and it is worth declaring.** It means "this
  key is there before any node runs", which is what lets dataflow analysis tell a key someone
  forgot to write from one the caller supplies. With a plain `StateGraph(State)` the input
  schema *is* the state schema — a caller may pass any key — so every key is flagged and a
  read-before-write can never be reported. Naming a narrower `input_schema=` is what makes
  that distinction, and it is the difference between an analysis that can find a missing
  writer and one that cannot. A pydantic or dataclass field with a default is flagged too,
  for the same reason: it is there before any node runs.
  A value that carries neither a reducer nor a flag is written as the bare type name
  (`"str"`), which is the IR's canonical form for it — so an extracted schema and a
  hand-written one that spelled it the long way are the same document and the same
  `graph_version`.
  Where a declared type or reducer has no spelling gebra is willing to invent — a type
  variable, an enum-valued `Literal`, a channel class of your own — **the key keeps its place
  in the schema** and carries a marker plus a warning saying what could not be read. Dropping
  it would read downstream as "no such key", which is a different and wrong thing to say
  about a key your schema declares. Managed values (`RemainingSteps` and its kind) are the
  one exception: ir 1.0 has no slot for what they mean, so they are recorded on the envelope's
  provenance rather than described wrongly in the schema — without a warning, because
  declaring one is not a defect.
  Nothing about this runs your code. The type hints are already resolved on the builder by
  the time `extract()` sees it, so no annotation is evaluated, no validator fires, no channel
  property of yours is read, and no reducer is called — only named.
- **Shallow contract inference** — the third and last source a node contract can come from,
  and the only one you write nothing for: what your node's own source already makes obvious.
  `gebra.annotations.inference` reads a node function's AST and fills at most two slots,
  `input` and `output`, from a **closed** list of five patterns — a `TypedDict`/pydantic
  *projection* annotation on the state parameter; a literal `state["k"]` or `state.k` read in
  the body; a literal dict returned; a `TypedDict` return annotation; a literal
  `Command(update={...})`. That list is the whole of it, down to the asymmetry: a pydantic
  model is read as a projection on the state parameter and not on the return, because that is
  how the spec's table is written and output keys are a claim about what you *write*. A dict
  built by a helper, a computed key, `dict(**kwargs)`, a read inside a nested function — all
  deliberately out, because the point of stopping here is that every inferred key can be
  pointed at a line in your own node, and a contract nobody declared should never be more
  confident than that.
  Two of the exclusions are worth knowing about because they look like omissions and are not.
  `def node(state: State) -> State` — the ordinary LangGraph shape — infers **nothing** from
  its annotations: naming the whole state schema says which type flows through, not which
  keys this node cares about. And with several `return`s, either every one of them is a
  literal gebra can read or the write set is abandoned wholesale; half a write set reads as a
  complete one, and that is worse than none.
  What is left over gets the conservative floor rather than a guess: a node with visible
  writes resolves to `effect: ["write"]`, and one with no write evidence at all to
  `pure: true` — which is a "nothing found", not a proof, since a write inside a helper is
  exactly what shallow analysis cannot see. "Visible" means any of the patterns above
  matching, including a return annotation that names what the node writes even when the
  bodies' returns were too dynamic to read. A node whose body could not be read at all — a
  callable object, a `functools.partial`, something compiled from a string — takes the
  `effect: ["write"]` floor, never `pure`.
  **Inference never upgrades a contract.** It cannot produce `idempotent`, `deterministic`,
  `variant`, `compensation` or `args_schema`, in any shape, ever: those unlock retry,
  memoisation, termination-witness and compensation reasoning, and they stay something you
  opt into by declaring them. And everything inference *does* fill arrives with a structured
  warning attached — `contract-inferred` with the licensing pattern for each key, or
  `contract-defaulted` with the default applied and why no pattern matched — so a validator
  can always tell an author's declaration from a guess, and so can you.
  Nothing is evaluated on the way: no annotation is resolved (a string annotation, which is
  what `from __future__ import annotations` leaves behind, is simply not read rather than
  `eval`-ed back), no import is followed, and the only file opened is the one that defines
  the node.
  As with the decorators and the sidecar, none of this reaches the IR yet: the rules that
  resolve decorator against sidecar against inference are the next piece, so today inference
  is a function you can call on a node and every node still comes back with no resolved
  contract.
- **The `gebra.toml` sidecar** — you can now declare a node's contract in a file instead of
  on the function, which is the only option when the function is not yours to decorate: a
  third-party tool, a vendored callable, a bound method of a frozen class. The vocabulary is
  the same nine slots the decorators take, spelled the same way:

  ```toml
  schema = "gebra-sidecar-v1"

  [nodes.book_flight]
  reads   = ["itinerary", "budget"]
  writes  = ["booking_ref"]
  effects = ["network", "billable", "irreversible"]
  idempotent = { key = "booking_ref" }

  [nodes."research/tools/web_search"]   # nested nodes are quoted: "/" is not a bare key
  effects = ["network"]
  ```

  Which file governs is decided once per `extract()` call and never by merging: an explicit
  `gebra.extract(workflow, sidecar="…/gebra.toml")` wins outright, and otherwise the nearest
  `gebra.toml` walking up from the current directory to your repository root — the first one
  found, and only that one. A sidecar sitting above your checkout never reaches inside it.
  The table key is the node id exactly as the IR spells it, byte for byte, case-sensitively.
  For an ordinary node that is just its name. For a nested one it is the `/`-joined path, and
  a literal `/` or `%` *inside* a name arrives already escaped (`summarize%2Fmerge`) — quote
  the key, never escape it twice. A key that matches no node in the graph gets you an
  `annotation-unknown-node` warning rather than silence, because renaming a node gives it a
  new identity and a stale key is precisely the config drift a sidecar is prone to.
  **Nothing in a sidecar can break an extraction.** A file is config, so every way it can be
  wrong is a warning: a missing file, a syntax error, a `schema` that is not
  `"gebra-sidecar-v1"` (the file is skipped entirely and named), a key that is not one of the
  nine slots, an effect tag outside `{network, write, external, irreversible, billable}` (the
  tag is dropped, the rest of the entry stands), `pure = true` next to a non-empty `effects`
  (both go — the file gives no basis to prefer one), a `deterministic` table without its
  `seed`, or a value of the wrong shape. In every case the slot is left *unset* rather than
  filled with a guess, so the lower-precedence sources can still fill it, and the warning
  says which rule was violated. Note the one thing this means: an explicit `sidecar=` path
  that does not exist warns and proceeds without it — it does not fall back to the search,
  because silently using a *different* file than the one you named is the failure worth
  preventing.
  The absolute path of the file that was used is recorded on the envelope
  (`extracted_from.sidecar`), or its absence is. Sidecar-declared contracts affect
  `graph_version`, and where the file was found depends on where you ran from — so if two
  runs disagree, this field is what tells you why. For reproducible and CI runs, pass
  `sidecar=` explicitly and assert on that field.
  As with the decorators, nothing reads these declarations into the IR yet: the rules that
  resolve decorator against sidecar against inference are the next piece, so today a sidecar
  is found, parsed, validated and recorded, and every node still comes back with no resolved
  contract.
- **Contract decorators** — you can now declare what a node does, next to the node:
  `@gebra.contract(reads=[...], writes=[...], effects=[...], pure=..., idempotent=...,
  deterministic=..., args_schema=...)`, plus the shorthands `@gebra.pure`,
  `@gebra.effect("network", "billable")`, `@gebra.idempotent` / `@gebra.idempotent(key=...)`,
  `@gebra.deterministic` / `@gebra.deterministic(seed=42, temperature=0.0)`,
  `@gebra.variant(key=..., measure=...)` and `@gebra.compensation(hook=...)`. They stack
  freely.
  A decorator attaches its declaration under one attribute (`__gebra_contract__`) and hands
  you back **the same function** — it never wraps it, never reorders anything, and never
  calls it. That is what lets a contract survive `.compile()`: LangGraph re-wraps your
  function, not a wrapper gebra slipped underneath it. It is also why decorating costs
  nothing at runtime, and why `import gebra` plus a decorator pulls in neither LangGraph nor
  the extractor.
  If a stack contradicts itself you find out when you import the module, not when you run
  `gebra verify`. Setting the same slot twice is an error even if both values agree — inside
  one author's stack there is no config drift to excuse, so a duplicate is confusion worth
  catching. `pure=True` alongside a non-empty `effects` is an error. An effect tag outside
  `{network, write, external, irreversible, billable}` is an error. And the object form of
  `deterministic` needs its `seed`: `@gebra.deterministic(temperature=0.0)` on its own
  declares nothing you could replay.
  What you *cannot* declare is as fixed as what you can. Nine slots are annotatable and the
  set is closed; reaching for anything else — `retry_policy`, `prompt_digest`,
  `config_digest`, interrupt gates, checkpointing — tells you where that value actually comes
  from, because it is extracted or computed rather than declared. Two checks are deliberately
  *not* made here: whether an idempotency key is one of the node's inputs, and whether
  `irreversible` sits alongside `idempotent=True`. Both need the fully resolved contract,
  which does not exist until extraction reads the sidecar and inference too, so both are
  warnings there rather than import errors here.
  Nothing reads these declarations yet: `gebra.extract()` still returns nodes with no
  contract. The sidecar, inference and the precedence rules that combine the three are the
  next pieces.
- **Builder extraction** — `gebra.extract(builder)` now returns a real IR for an uncompiled
  `StateGraph`. This is the first of the three object families to get its rules, and it is
  the one that matters most, because the builder is the record of what you actually wrote:
  it is read *before* `compile()` folds defaults and turns your declarations into channels,
  and `compile()` is never called on it — the graph you hand in is the graph that is read.
  What comes back is the topology you declared. Every node you added becomes a node in the
  IR, with its name escaped only where it has to be (a literal `/` or `%` in a node name is
  percent-encoded, so that a node id can always be split on `/` without knowing anything
  about it). Every plain edge becomes an edge. Every `add_conditional_edges` router becomes
  one conditional edge carrying the branch's declared name and its `path_map` — the router's
  *body* is never read and never stored, because a guard in gebra is a reference to a
  decision, not a copy of it. `add_edge(START, x)` and `set_conditional_entry_point` both
  feed `entry`; `add_edge(x, END)` feeds `finish`.
  Two things it deliberately does not do. It reads no annotations — decorators, `gebra.toml`
  and inference are all still ahead — so every node comes back with no contract rather than
  with a guessed one, and passing `sidecar=` has no effect yet. And it does not decide
  whether a router is a `Send` fan-out, which is read from declared return-type hints and is
  its own piece of work; until then a fan-out router extracts as a conditional edge over the
  same declared targets, which claims strictly less than a `send` edge would.
  Where the builder declares something the IR has no shape for, you get told. A
  `waiting_edges` join flattens to plain edges with a `barrier-flattened` warning, because
  the IR cannot say "wait for all of these" and pretending otherwise would quietly change
  what a later check means. An entry router with no `path_map` extracts to an empty `entry`
  with a warning naming the branch, because which node runs first is genuinely a runtime
  decision. A `retry_policy` whose triggers are a callable rather than declared exception
  types extracts with an empty `retry_on` *and* a warning saying the trigger set is opaque —
  read them together, because the empty list means "not knowable", not "never retries". A
  list of retry policies projects the first and says how many were dropped.
  And where it cannot produce an honest IR at all it refuses, with a `reason` code, rather
  than handing back something that looks complete: a router that declares no targets, a node
  declared with `destinations=`, or a node whose name is the empty string.
- `entry` and `finish` accept the **empty list**, and it means something specific: no entry
  or finish wiring is statically knowable. This matters for a shape that is entirely
  ordinary — a workflow that reaches its end through a router (`{"done": END}`) rather than
  through an `add_edge(x, END)` has no finish *node* to name, and it now extracts cleanly
  and without a warning, because nothing about it is undeclared. A workflow that is
  genuinely unwired extracts to the same empty form *with* a warning. Both were previously
  unrepresentable. The empty string is not a second way to spell this and is rejected.
- The extraction entry point — `gebra.extract(workflow)`, plus `gebra.extraction` for the
  types around it. This is the front door of the library, and what landed is the door
  rather than the rooms behind it: `extract()` recognises which of the three object
  families it was handed — a LangGraph `StateGraph` builder, a compiled graph (or any
  other Pregel-protocol object), an LCEL `Runnable` — and refuses anything else with a
  typed `ExtractionError` naming the type it got. It classifies by `isinstance` and two
  attribute reads, so nothing you hand it is invoked, and a builder handed in is never
  compiled: those are checked by sentinel fixtures whose every node, router and LCEL step
  raises if it is ever called.
  A compiled graph is read through its `.builder` backreference, because the builder is
  what records what you wrote; one with no reachable builder takes the compiled-only path
  instead, which says so rather than pretending to know as much.
  Refusal has four causes, each with a stable `reason` code you can branch on rather than
  a message you would have to match: the object is not one of the three families, a
  Pregel-protocol object has no usable surface at all, a builder has no nodes to extract,
  or this build carries no extraction path for that family yet. That last one is the
  common case today — the per-family paths are separate work — and it is a refusal on
  purpose: half an IR that looks whole is worse than an error.
  `extract()` returns an `ExtractionEnvelope`: the IR, where it came from, and the
  warnings. The warnings are the one closed taxonomy the specs define, spelled exactly as
  ratified (`contract-inferred`, `contract-defaulted`, `opaque-lambda`,
  `builder-compiled-divergence`, `compiled-only-extraction`, `barrier-flattened`,
  `unsupported-construct`, `annotation-conflict`, `annotation-unknown-node`,
  `annotation-invalid`), and each one is a record, never a sentence: a code, the node it
  concerns, the contract slots it names, and structured detail. That shape is what makes
  them answerable — `envelope.slot_grade(node, slot)` tells you whether a contract slot
  was declared by you or produced by inference, which is the distinction a validator has
  to know before it reasons from a value, and the one the IR itself deliberately does not
  carry. Warnings are returned rather than raised through Python's `warnings` module, so
  no filter anywhere can drop one.
  The envelope sits *around* the IR, never inside it, and that is load-bearing: the
  content hash is computed from the IR alone, so a warning, a sidecar path, or an
  extractor version can never move a `graph_version`. Checked against the frozen golden
  vector rather than against itself — an envelope carrying three warnings digests to the
  same string as the bare IR.
- The effect-safety check — `from gebra.verify import check_effect_safety`. P-06
  `effect-safety` is the fourth of the five validators to land, and it answers one question
  about a workflow: is there a node you have tagged as spending money or doing something
  permanent, sitting somewhere the graph can re-enter it, with nothing declared to make that
  safe? The
  canonical case is the booking retry: `book_flight` charges a card and files a reservation, a
  check node routes back to it on failure, and nothing says what happens on the second lap. Two
  laps, two charges. This finds it in the definition instead of in the bill.
  Only two effect tags create the obligation — `irreversible` and `billable`. A node tagged
  `network`, `external`, `audit`, or with a tag of your own is not flagged for looping; those
  tags still ride along in the report as context, because when you read a finding you want the
  node's declaration as you wrote it, not a filtered version of it.
  Two declarations discharge it, and both are checked for whether they actually bind.
  `@gebra.idempotent(key="flight_id")` counts when `flight_id` is among the node's declared
  reads — a key the node generates itself is minted fresh on every attempt and stabilises
  nothing, so that reports as unprotected. A compensation hook counts when it names a node that
  exists; a hook naming nothing is a typo, not a safety net, and the bad name rides the finding
  as evidence.
  Where the node sits changes which finding you get, not whether you get one. A node the graph
  re-enters directly on a routing decision — or that a `Send` fan-out re-dispatches, or that
  declares its own retry policy — is in a *retry region*; a node reached only after intermediate
  work on the way round is in a plain *cycle*. Both are errors, with distinct condition IDs, so
  a report tells you which shape you are looking at. A node that no loop and no declared retry
  policy can re-enter needs nothing declared, and gets no finding: this does not flag every
  irreversible effect, which is exactly the thing that would make it useless.
  One combination is rejected on its own, loop or no loop: `irreversible` together with a bare
  keyless `@gebra.idempotent`. That is a claim about a provider deduplicating, tied to no input
  Gebra can see, and it is a fatal finding on an entirely straight-line graph.
  What a pass records is the declaration, and only the declaration. Gebra reads that you
  declared a key or a hook; it does not check that your provider deduplicates, or that the hook
  undoes anything, and it never runs the node to find out. The witness lists each cycle the
  graph contains, one representative loop apiece, and one record per effect-carrying node saying
  where it sits and what protects it there.
  All six of the property's fixtures reproduce their expected report as model equality, along
  with all four mixed fixtures that exercise it — including the one where the effect finding
  rides another property's report. The cycle analysis never enumerates loops: it asks which
  region each node belongs to and picks one representative cycle per finding, so a graph with
  2^60 distinct loops through a node still returns an answer — where enumerating them would not
  return at all.
- The dataflow check — `from gebra.verify import check_dataflow_completeness`. P-04
  `dataflow-completeness` is the third of the five validators to land, and it answers one
  question about a workflow: could any routing of this definition reach a node whose declared
  read has never been supplied? The canonical case is a branch that skips a writer — a new
  "express" label routes an availability check straight to the confirmation step, which reads a
  `booking_id` only the booking node writes. The express path never writes it, and the first
  pre-held booking crashes in production. This fails it at design time instead, and names the
  path it fails on.
  **Every** path, not some path. A read is covered only when every route from the graph's entry
  to the reading node passes through a writer of that key first — so two alternative branches
  that both write it are fine, and two branches where only one writes it are not. Which branch
  a router picks at runtime is not something this decides, and it never assumes the lucky one.
  A key declared `optional` in the state schema counts as supplied at the start, which is what
  makes it a graph input.
  Order matters as much as presence. A writer wired *after* its reader supplies nothing, so the
  common ordering slip — publish the itinerary after notifying the traveller about its URL — is
  a finding, not a pass. Inside a loop the same rule applies at the first arrival: a node's own
  write never satisfies its own read, because the first iteration runs before it. That last
  point is where a shortcut would be tempting and wrong: a loop is not summarised by the set of
  keys its members eventually write. Whether a loop entered at its reader is broken and the same
  loop entered at its writer is fine are two different answers, and this gives two different
  answers.
  What a failure carries is a person's next move: the state key, the reading node, and the
  shortest actual path from the start on which nothing wrote it. Where it helps, two further
  hints ride along — the writers that *do* cover the other paths, and any writer that exists but
  sits downstream of the reader. Neither changes the verdict; both shorten the search. A clean
  graph returns the coverage list instead: one entry per reachable read, naming what covers it.
  A node no route can reach is not this check's business at all — it produces no dataflow
  finding, because the topology gate already reports the node itself and one root cause deserves
  one report.
  All six of the property's fixtures reproduce their expected report as model equality, along
  with the dataflow half of the mixed loop fixture. The every-path question is answerable at
  all because the analysis never walks the routes: it solves for what must have been written
  by the time each node runs, so a graph with 2^60 distinct paths through it still returns an
  answer — where enumerating those paths would not return at all.
- The termination-witness guard recognizer — `from gebra.verify import classify_guard`. P-02's
  first half: given the declared condition string of a router edge, it decides whether that
  string is a *counter guard* — the `'retry' if … and retry_count < 3 else 'done'` shape — and,
  when it is, says which state key is the counter, which way the bound runs, what the bound is,
  and which of the two labels the comparison gates. `qualify_counter_guard` adds the second
  question a counter guard has to answer: is that key actually in the state schema, declared as
  an integer? Only `int` counts, in either of the two spellings the schema admits; anything else
  — `float`, `number`, a sized integer, an `Optional` wrapper — is not a counter, and the guard
  contributes nothing.
  What it reads is *syntax*, and that boundary is the point. A recognized guard means the
  definition names a bound. It does not mean the bound is ever reached, that the counter is
  advanced, or that the loop stops — those are questions about a running program, and the
  condition string is opaque Python that Gebra never executes.
  Everything outside the grammar is opaque, and opaque means **nothing at all** is taken from
  the string — not the part that looked fine. A condition carrying `or`, a negation, a nested
  ternary, a call like `len(...)`, a bracket, or a quoted string literal in the middle is
  rejected whole, even when a perfectly good `retry_count < 3` is sitting inside it. That is
  deliberate: a disjunct lets the loop continue no matter what the counter says, so half-reading
  one would claim a bound that is not there. The same fail-closed rule covers `==`, negative
  bounds, unquoted labels, non-ASCII identifiers and worklist-emptiness guards — each an
  excluded shape rather than a guessed one. The else-branch of a recognized guard is never
  treated as bounded either: it is selected exactly when the test is false, which for a
  conjunction says nothing about the counter. One length limit applies for a practical reason
  rather than a grammatical one: a bound of more than 640 digits is not recognized, because
  Python cannot print an integer that long without being reconfigured, and a bound that cannot
  be printed cannot appear in a report. Every real counter bound is a handful of digits.
  All eleven guard strings the termination-witness fixtures carry classify exactly as the
  frozen spec's own validation table says they should — the six recognized ones down to the
  counter key, the bound and the gated label, cross-checked against three fixtures' recorded
  expectations, and the five deliberately-opaque ones rejected at the lexical gate. Across the
  whole 60-fixture corpus, exactly eight of the forty-eight declared router conditions are
  recognized.
- The topology gate — `from gebra.verify import check_graph_well_formed`. P-01
  `graph-well-formed` is the second of the five validators to land, and the first that reads a
  graph: over the sentinel-augmented, label-expanded model it checks that every node is
  reachable from START, that every node with no outgoing edge is wired to END, that no node
  participates in nothing at all, and that every reference — each `entry` and `finish` id, each
  edge's `from` and `to`, and every `path_map` value — names a node that exists. A clean graph
  returns a structured witness listing what was checked (the reachable set, the nodes wired to
  END, and the two conditions evidenced as empty); a broken one returns the finding a person
  should fix first, with every other finding carried alongside it rather than dropped.
  Which finding comes first is the part worth knowing. The four conditions cascade — one typo
  in a router's target strands the node behind it, which strands its reader — so the report is
  ordered by root cause, and a reference that names nothing sorts behind one anchored at a node
  you can actually open. All six of the property's fixtures reproduce their expected report as
  model equality, and so does the topology half of the all-properties-pass fixture.
  Two boundaries it holds deliberately. It **never enumerates cycles**, and it never needs to:
  one graph build, one breadth-first pass and two degree scans, so the work it does grows with
  the size of the graph and not with how many cycles are in it — a graph carrying more simple
  cycles than there are grains of sand costs the same as a straight line of the same size. And it reads
  **only** topology — no state schema, no annotations, no router condition strings — so nothing
  about a node's contract can move its verdict.
- The shared graph pre-analysis the topology-facing validators read their graph from —
  `from gebra.verify import build_graph_model`. One module builds the graph P-01
  `graph-well-formed`, P-02 `termination-witness`, P-04 `dataflow-completeness` and P-06
  `effect-safety` all open with, so they agree on it by construction rather than by four
  parallel readings of the same passages: every `path_map` label expanded into its own
  directed edge before any algorithm runs, `START`/`END` materialized as real vertices and
  wired from `entry`/`finish` and from the blessed `"END"` label literal, parallel edges and
  self-loops kept distinct (merging them would let one discharged label-edge discharge its
  sibling), and iterative Tarjan components with the condensation utilities on top —
  reachability, a topological worklist order, induced subgraphs, and one deterministic
  shortest anchor cycle per request.
  Two things it deliberately does not do. By default it **resolves nothing into existence**:
  a reference naming no node contributes no vertex and no edge, and is recorded instead —
  with the role that failed, its anchor and its label — so the validator that owns the
  finding reads it off a record rather than re-deriving it, and a cascade is reported at each
  site rather than collapsed. (What to do with such a reference is the one thing the
  properties genuinely disagree about, and the property catalog says so: two of them drop it
  and two carry it as a phantom vertex, and cross-property agreement on ill-formed input is
  explicitly not promised. So it is a parameter, not a default chosen on four validators'
  behalf.) And it **enumerates no cycles**: the mandatory path is one component pass, since a
  graph's simple-cycle count can grow faster than exponentially in its size.
  It carries no property semantics — no condition ID, no severity, no witness — and it uses
  no graph library: every traversal is iterative and stdlib-only, so deep graphs cannot
  exhaust the interpreter's recursion limit and nothing new enters `import gebra.verify`'s
  import closure.
- The golden harness — `from gebra.testing import run_corpus`, and the
  `python tools/golden_harness.py` gate that runs it in CI. Every vendored fixture becomes
  one **obligation** per property it exercises, and each obligation is compared against the
  validator that owns it as PROPERTY-CATALOG-SPEC §0.3 model equality — set-comparison on
  the fields the specs mark order-free, never string or raw-dict equality. Which fields
  those are is read off the envelope models, where each mark carries its citation, so the
  harness decides nothing about ordering itself: a permuted P-04 `coverage` matches (§4.3
  says its order is not normative) and a permuted P-02 `certificate` does not (a permutation
  of a topological order certifies nothing).
  Sixty fixtures state seventy-eight obligations. **Five of P-08's six are asserted and
  green** — its four `determinism-replay` fixtures and `mixed/10`'s determinism witness
  entry, all model equality against `check_determinism_replay`; the sixth, `mixed/03`'s two
  advisory records, is an open fidelity-matrix entry. The rest are named, counted, structured
  absences rather than passes: a property outside the Phase-0 wedge is `deferred-to-phase-1`
  citing SOW §8, and a wedge property whose validator has not been wired yet is
  `pending-validator` — the same two statuses `gebra.verify.not_implemented` reports at the
  API level, so the harness and the registry say the same thing about the same absence.
  Neither is ever rendered as a pass.
  A cross-property `mixed/` fixture's `expected:` block is a run-level composition that no
  single validator produces whole — `mixed/04`'s carries a `dataflow-completeness`
  co-failure on a `graph-well-formed` primary, which the emission constructors' ownership
  check forbids a P-01 validator from emitting — so four **projection rules** say how one
  property's share is read out of it. Each rule is data carrying its citation, and each is
  logged in the fidelity matrix.
- `docs/governance/FIDELITY-MATRIX.md` — the decision log for every place a validator and a
  fixture disagree, with its route: fix the validator, or request a fixture revision through
  R-05 sign-off recorded vault-first. The corpus is a read-only vendored contract surface,
  so a mismatch is never resolved by editing a fixture here.
  It is machine-checked rather than maintained by hand: `tools/golden_harness.py`
  cross-checks the file against a live run in both directions, so a deviation with no open
  entry fails the gate and an open entry that no longer reproduces fails it too. The four
  open entries are exactly the three R-05 calls the corpus-reconciliation ruling left open,
  rediscovered from the corpus rather than transcribed — `mixed/10`'s pre-contract P-04
  witness sub-block, `mixed/03`'s two P-08 advisories carrying a bare node location, and
  `mixed/05`'s two pair-scoped `snapshot: ir_after` records. Two closed entries record the
  loop's first completed circuit: the P-08 negatives, whose deviation the reconciliation
  pass resolved.
- The fixture corpus is reconciled to the property catalog's per-property I/O contracts —
  the single shape-reconciliation pass the catalog mandates, ruled as DEC-17 and re-vendored
  from the specification vault. Twelve fixtures carried `expected:` blocks that predated the
  contracts they are written against: P-04 and P-06 failure records without their `location`
  discriminator or their `severity`/`claim_class`, three cycle lists in traversal order
  rather than least-id-first canonical rotation, one region named `cycle` where the region
  rule says `retry`, and the two P-08 `remediation` strings that were condensed action
  clauses rather than the warning grammar's closing paragraph. All twenty-two are now the
  shapes the catalog pins.
  What this buys a consumer: **every fixture in all five wedge directories now loads into a
  `PropertyReport`** — thirty of them, eight more than before, taking the whole corpus from
  25 of 60 to 33 — so a validator can be asserted against its fixtures as model equality
  rather than through a per-fixture normalization ledger. The four `determinism-replay`
  fixtures are the proof: they are model-equal to what `check_determinism_replay` produces,
  raw, and the deviation ledger that validator shipped with is gone.
- Corpus reconciliation tooling — `python tools/corpus_reconcile.py`, which holds that pass
  as data: each edit a *(before, after)* pair of the literal `expected:` block with the
  frozen passage that fixes its target shape, so the record of what changed and why is
  executable rather than prose. `--audit` prints it per item with citations; `--check` is
  the regression gate that exits 1 if any ruled revision were reverted.
  It never writes inside `tests/fixtures/properties/`, before or after a ruling — a corpus
  revision routes proposal → sign-off recorded vault-first → re-vendor commit citing the new
  vault hash, so what the tool produces is a *candidate* corpus elsewhere, and pointing
  `--emit` at the vendored tree is refused rather than confirmed. Because it reads whatever
  corpus it is given, the test suite reconstructs the pre-ruling bytes and requires the tool
  to reproduce the vendored ones from them, file for file: what was merged is checked against
  what was ruled, not asserted to match it.
- The hermetic fixture loader — `from gebra.testing import load_corpus, load_fixture`. A
  vendored property fixture is a *(Gebra IR, expected verdict, witness/failure)* triple, and
  this is the path from the file on disk to the two model surfaces it is a triple over:
  `yaml.safe_load` (in a private `SafeLoader` subclass, so a tag another library registers on
  the shared one cannot change what a fixture means) into `ir_version` 1.0 `WorkflowIR` for
  the IR blocks, and PROPERTY-CATALOG-SPEC §0.3's
  `PropertyReport.model_validate({"property": fixture["property"], **fixture["expected"]})`
  for the `expected:` block — the same class a validator's own output validates into, which
  is the whole of convention PC-6. All 60 vendored fixtures load, with every one of their 67
  IR blocks a 1.0 model. A cross-property `mixed/` fixture's owning property is not readable
  off the document, so it is derived from the primary finding's condition ID through the §0.4
  registry.
  Nothing is coerced on the way in: the four things PyYAML's safe constructor set admits and
  JSON does not — a non-string mapping key, a timestamp or binary scalar, `.nan`/`.inf`, a
  recursive anchor — are refused by name with a stable `FixtureErrorReason`, because a fixture
  that quietly changed meaning between the file and the model is the one failure a golden
  corpus cannot tolerate. `source_snippet` is carried as an inert string and is never
  compiled, imported or executed.
- Corpus lint — `python tools/corpus_lint.py`, running as its own CI job. It is the
  repository's corpus lint: schema v2.2 conformance, exactly one IR shape per
  fixture (with the `ir_before`/`ir_after` pair form tied to evolution-safety in both
  directions), the corpus README's per-directory positive/negative minimums, serial-number
  collisions, and witness/failure presence — 32 rules in a closed vocabulary, each seeded and
  proven to fire in a temporary copy of the corpus, never the corpus itself.
  The envelope rules are *read off the vendored `schema.yaml` at run time* rather than
  restated, so a re-vendored schema retunes the gate instead of silently outrunning it; the IR
  blocks are delegated to `WorkflowIR`, which `tools/schema_lockstep.py` already holds in
  lockstep with the same file's `gebra-ir` `$defs`. Whether each `expected:` block composes
  into a §0.3 report is reported per fixture and never gated — 33 of 60 do (all thirty
  wedge-directory fixtures, plus `mixed/02`, `/04` and `/08`), and the 27 that do not are
  shapes the frozen specs themselves carry as pending, under three headings the report names
  rather than blurring: the non-wedge witness/location shapes `schema.yaml` marks provisional,
  P-03's three condition IDs that §0.4 holds back, and `mixed/10`'s run-level wrapper, which
  §0.3's scope boundary assigns to REPORT-FORMAT-SPEC. A fourth heading — the *wedge* negatives
  whose `location` block predated its §P-nn.3 subtype — is gone with the corpus reconciliation
  below. Reconciling the rest routes through R-05 vault sign-off (WA-04), never a local edit.
  Nothing on the load path imports langgraph or langchain, opens a socket, or executes
  anything. The whole path — loader, corpus, lint — runs in an interpreter where a substrate
  import, a socket and a name resolution each raise, following the tripwire pattern ratified
  for the envelope: every trip is recorded before it raises, so a swallowed `ImportError`
  still fails the run; and each half has a negative control that deliberately trips it, so a
  tripwire that stopped working cannot hide behind a green suite (WA-07).
- P-08 `determinism-replay`, the first of the five validators —
  `from gebra.verify import check_determinism_replay`. It reads two annotation slots
  (`deterministic`, `effect`) over `nodes[]` and nothing else: no `edges[]`, no `state`, no
  `runtime`, and no graph machinery, as PROPERTY-CATALOG-SPEC §8.7 states in the negative.
  A declared `@gebra.deterministic` claim on a node whose effects evidence a remote LLM call
  (`external`/`network`, the D-011 proxy) must pin both halves of the D-013 contract: a bare
  boolean is `deterministic-llm-seed-unpinned`, and an object form whose `temperature` is
  absent or nonzero is `deterministic-llm-temperature-unpinned`. Everything else — a claim on
  pure local computation, an explicit `deterministic: false` disclaimer, a node with no claim
  at all — is coherent and recorded as such.
  Every finding is WARNING severity from a HEURISTIC property, always, both read off the §0.4
  registry rather than restated: P-08 checks the *coherence* of a determinism claim, never the
  behavior of a provider, and a pass witness carrying an LLM-backed claim carries the mandatory
  `provider-seed-reproducibility-not-guaranteed` caveat with it. Multiple findings pack the
  §0.3 way — canonical node order fixes the primary, the rest ride as same-property
  `co_failures` — and `remediation` renders from the Appendix B §B.3 warning grammar, which is
  display-only prose beside a fully structured verdict.
  All four vendored `determinism-replay` fixtures are reproduced as **model equality** against
  their own raw `expected:` blocks, as is `mixed/10`'s P-08 witness — no field is normalized on
  either side, and no deviation ledger stands between them, because the two fields §8 carried
  as pending were reconciled in the corpus pass below. Registration is what dispatch runs on:
  `run_property("determinism-replay", ir)` now returns a report, and the other four wedge
  slugs still answer with their structured not-implemented marker.
- Condition-ID and property registries — `from gebra.verify import emit_failure, run_property`:
  the two tables every report is dispatched and emitted through. `gebra.verify.conditions`
  carries the PROPERTY-CATALOG-SPEC §0.4 registry as its 21 frozen entries — 11 RATIFIED
  wedge strings, 8 RESERVED non-wedge names, 2 PROPOSED — each with the property that holds
  it, the severity and claim class §0.4 pins for it, its in-corpus precedent, and the dated
  decision record that ratified it. `gebra.verify.registry` carries the thirteen catalog
  slugs with their claim classes, severities and derivation references, and restates no
  condition ID: it reads them off §0.4, so the two tables cannot disagree.
  A validator cannot emit a condition ID the catalog does not know. Registration is closed
  at the type level — `ConditionId` is now a `Literal` over the registry's members, so an
  unregistered string is refused wherever a `Failure`, `CoFailure` or `Advisory` is built or
  loaded — and emittability is checked at `emit_failure()` / `emit_co_failure()` /
  `emit_advisory()`, which are the sole emission surface and read severity, claim class and
  the owning property off §0.4 rather than taking them from the caller. The two guards are
  separate on purpose: a name may be *registered but not emittable*, and a report is allowed
  to record one even though a validator may not produce it — the corpus does exactly that
  with the P-07/P-09/P-12 RESERVED names. Emittability turns on a dated record, never on the
  tier: `orphan-node` and `edge-target-undefined` were filed in the same PROPOSED table on the
  same day and are both emittable now — the first because DEC-11 ratified it by name, the
  second since DEC-12 did the same — while the eight RESERVED names, which have no such
  record, stay recordable but not emittable.
  Dispatch is registry-driven and never silently passes. `run_property(slug, ir)` returns a
  `PropertyReport` when a validator is registered and a structured `NotImplementedMarker`
  otherwise — `deferred-to-phase-1` for the eight properties outside the Phase-0 wedge,
  `not-yet-implemented` for a wedge property not yet wired in. The marker is deliberately
  not a `PropertyReport` (the §0.3 envelope knows only `pass` and `fail`), so it cannot be
  read as a verdict, and registering a validator for one of the eight is refused.
  One §0.3 packaging rule is enforced at the same surface: `emit_failure()` refuses an
  `advisories` entry from the emitting property itself, because advisories carry
  cross-property WARNING-class side findings and a same-property finding rides `co_failures`.
- Result-envelope models — `from gebra.verify import PropertyReport, validate_report`: the
  normative PROPERTY-CATALOG-SPEC §0.3 envelope every property report is written in, with
  the shapes ratified at review walkthrough #2 (DEC-11). `PropertyReport` carries a
  witness *xor* a failure and enforces it; `Failure`/`CoFailure`/`Advisory` carry the
  packaging rule (further same-property findings ride `co_failures`, cross-property
  WARNING-class side findings ride `advisories`, and every record carries its own severity
  and claim class); `Location` is the six-anchor discriminated union, joined by the wedge's
  concrete subtypes; `Witness` is the five-member union — `WellFormednessWitness` (the
  5-key form), `TerminationWitness` (inventory, acyclicity certificate, structured notes,
  the optional capped cycle census), `DataflowWitness`, `EffectSafetyWitness`,
  `DeterminismWitness` (the provider caveat is required exactly when a claim is LLM-backed).
  One set of models with two duties (A6 PC-6): the same classes validate a fixture's
  `expected:` block and a validator's output, so comparison is model equality rather than
  raw-dict or string equality. All 30 single-property corpus fixtures in the five wedge
  directories — both polarities, every wedge family — plus three cross-property `mixed/`
  blocks validate and round-trip through the envelope as they stand, and reports built from
  the constructors are asserted *equal* to the ones loaded from those fixtures; the
  remaining blocks are the non-wedge shapes the specs still mark provisional, and no model
  was relaxed to accommodate them.
  Report node ids reuse the frozen IR-SPEC §5 grammar byte-for-byte, which is also what
  keeps the reserved `__start__`/`__end__` spellings out of a serialized report: the
  report-side spelling is the display sentinel `START`/`END`, and `to_display()` is the
  projection. `to_data()`/`to_json()` are the canonical serialization profile (definition
  order, unset optionals omitted), and `models_equivalent()` compares two envelope values
  the way §0.3 defines comparison — model equality, with multiset comparison on the three
  fields the catalog says are order-independent. The condition-ID vocabulary these models
  carry is closed to the §0.4 registry by the entry above.
- YAML/JSON loaders and dumpers — `from gebra.ir import load_yaml, load_json, dump_yaml,
  dump_json, read_ir, write_ir`: the *surface* form of an IR document, for every
  `ir_version` 1.0 model rather than only `WorkflowIR`. A model reloads equal to itself
  through either format — model equality, not text equality — which is what SOW §2
  criterion 6 asks for; five committed round-trip goldens under
  `tests/ir/golden/roundtrip/`, all 67 vendored corpus IR payloads, a per-model table and
  eight round-trip properties carry that claim. `read_ir()`/`write_ir()` do the same for a
  file, choosing the format by suffix (`.yaml`/`.yml`/`.json`).
  YAML is loaded through the IR-SPEC §2.5 note 4 ingestion path — `yaml.safe_load`, a JSON
  re-encoding, then `model_validate_json` — so both entry points share one strict
  JSON-mode validation and a sequence lands in the tuple-typed members. The re-encoding
  refuses rather than coerces what JSON cannot carry: a non-string mapping key, `.inf` /
  `.nan` (or JSON's non-standard `Infinity`/`NaN` literals, which both Python's parser and
  pydantic's accept), a YAML timestamp, a recursive anchor each raise
  `IRSerializationError` (a `ValueError` with a stable `reason` code and the path of the
  offending value). So does a document past the size or depth ceilings — a YAML alias is
  one shared object when parsed and a full copy once re-encoded, so a few hundred bytes of
  nested aliases would otherwise expand without bound. YAML is parsed through this
  package's own subclass of PyYAML's safe loader, so a tag another library registers on the
  shared `SafeLoader` cannot change what a gebra document means.
  These are surface bytes and are never hashed: the dump keeps the representations
  canonicalization collapses (`entry` as authored, an empty `interrupts.before`, an
  explicit `kind`), so whether two documents are the same workflow stays a question for
  `graph_version()` and never for these bytes. Dump styling is fixed by the goldens: block YAML and two-space JSON, members
  in declaration order, non-ASCII written as itself, one trailing newline.
- Canonical serialization + `graph_version` — `from gebra.ir import canonical_bytes,
  graph_version, verify_graph_version`: the IR-SPEC §6 pipeline (DEC-10) over a validated
  `WorkflowIR`. `canonical_bytes()` produces the RFC 8785 (JCS) canonical form after
  hash-scope projection, omit-/representation-normalization and the Gebra array sorts
  (`nodes[]` by id as UTF-16 code units, `edges[]` bytewise by their own canonical bytes,
  set-valued arrays sorted, `args_schema` array order preserved); `graph_version()` renders
  its SHA-256 as `"sha256:<hex>"`; `verify_graph_version()` recomputes and string-compares.
  Scalar constraints are enforced before any bytes exist, per the ratified wide-integer
  ruling (PD-004): an integer outside ±(2⁵³−1) — in a model field or inside `args_schema` —
  is a `CanonicalizationError` (a `ValueError` carrying a stable `reason` code and the
  offending path), never a stringified value; NaN/Infinity are refused; identifier-role
  strings must be NFC. The JCS emitter (UTF-16 member sorting, ECMAScript number
  formatting) is implemented in-house and pinned by RFC-8785-derived unit and property
  tests. Golden vector 001 (IR-SPEC §6.5) is committed under `tests/ir/golden/` — authored
  YAML, the 537 canonical bytes, and the digest — and the test suite reproduces it
  byte-exactly, re-canonicalizes the canonical form to itself, and runs
  recompute-and-compare across all 67 vendored corpus IR payloads.
- IR 1.0 models — `from gebra.ir import WorkflowIR`: the normative IR-SPEC §2.5 interface as
  pydantic-v2 models. `WorkflowIR` carries the seven top-level fields (`ir_version`, `entry`,
  `finish`, `state`, `nodes`, `edges`, `runtime`), `Node`/`Annotations` carry the node
  contract — the eight retained slots plus the nine new-in-1.0 slots ratified in PD-003
  Appendix A (`args_schema`, `retry_policy`, `variant`, `compensation`, `prompt_digest`,
  `config_digest` on annotations; `recursion_limit`, `interrupts`, `checkpointer` on
  `runtime`) — and `Edge` is a union discriminated on `kind` over `NormalEdge`,
  `ConditionalEdge` and `SendEdge`. An edge object with no `kind` loads as kind `normal`,
  and the `from` member keeps that name on the wire — the Python attribute is `from_`, so
  output serialized with `by_alias=True` carries `from`. Every model sits on
  one frozen, `extra="forbid"`, strict base (`IRModel`) that also refuses the
  validation-skipping `model_construct()`.
- Node-identity utilities — `from gebra.ir import node_id_from_names, parse_node_id, …`: the
  IR-SPEC §5 node-id grammar as functions, so that code needing a node id — extraction,
  canonicalization — has one implementation to call rather than a grammar to re-derive.
  `escape_segment()` NFC-normalizes a source name and percent-escapes
  it (`/` → `%2F`, `%` → `%25`); `unescape_segment()` is its strict inverse;
  `node_id_from_names()` and `join_node_id()` build a `/`-joined path, one segment per nesting
  level; `synthetic_segment()` mints the LCEL tokens (`%seq[0]`, `%map[docs]`) over the closed
  seven-kind vocabulary 1.0 fixes; `parse_node_id()`/`split_node_id()` read an id back, and
  `openinference_attributes()` derives the three `graph.node.*` telemetry fields. The reserved
  segments `__start__` and `__end__` are refused at every nesting level, by every builder and
  every parser. A refusal raises `NodeIdError` — a `ValueError` carrying a `reason` code, the
  offending segment, and its nesting level.
- `nodes[].id` is now checked against that grammar when a `WorkflowIR` loads, which is where
  IR-SPEC §2.3 puts the requirement. The check is a plain Python validator, so
  `model_json_schema()` is unchanged.
- What these models decide is otherwise document *shape* — field names, aliases,
  requiredness, types, and edge discrimination. Canonical serialization and the
  `graph_version` hash are their own piece (above), the loaders another; the spec's
  cross-field obligations (an `idempotent` key appearing in `input`, `input`/`output` naming
  declared state keys) are reported by the property validators, so a document that violates
  one still loads. The grammar likewise binds the definition site only: the id-shaped
  strings that *refer* to a node — `entry`, `finish`, `from`, `to`, `path_map` values,
  `runtime.interrupts`, `compensation.hook` — are left to the stage that resolves them.
- Schema-lockstep CI check (IR-05, IR-SPEC §2.5 note 5): `tools/schema_lockstep.py` asserts
  `WorkflowIR.model_json_schema()` stays consistent with the vendored `schema.yaml`'s
  `gebra-ir` `$defs`, wired into CI as its own `schema-lockstep` job. The comparison is a
  field-name vocabulary diff over 14 conceptual locations (the workflow root, each
  annotation/runtime sub-object, and the edge kinds unioned), not full JSON-Schema
  equivalence or requiredness — the two schemas differ in shape by design (a discriminated
  union vs. a flat conditionally-required object), and two requiredness divergences are
  already ruled rather than accidental (`RecursionLimit.justification`;
  `retry_policy`/`variant`/`compensation`'s sub-fields), so a vocabulary-only comparison
  reports neither as drift while still catching an added, removed, or renamed field. The
  vendored schema is only ever read, never edited (WA-04/WA-11).
- Repository scaffold: src-layout `gebra` package with `py.typed`, subpackage
  stubs (`gebra.ir`, `gebra.verify`, `gebra.testing`), never-invokes tripwire
  test scaffold, the 60-fixture acceptance corpus and its parse gate, CI
  baseline (lint + 4-cell test matrix), Apache-2.0 licensing set (LICENSE,
  NOTICE, CONTRIBUTING with CLA).
- Toolchain quality gates: CI now runs `ruff check`, `ruff format --check`,
  `mypy --strict` and `pytest` on every push and pull request. The mypy
  configuration (`[tool.mypy]`, strict over `src/` and `tests/`, targeting the
  declared Python 3.10 floor) makes bare `mypy` the gate, so a local run and the
  CI job check the same thing.
- `.editorconfig` carrying the repository whitespace conventions (UTF-8, LF,
  final newline, 4-space Python at 100 columns, matching ruff), with the
  vendored fixture corpus explicitly opted out so no editor reformats it.
- Coverage tooling: `coverage.py` via `pytest-cov`, configured in
  `[tool.coverage.*]` (branch coverage over the `gebra` package) and measured by
  the locked CI test job, which uploads `coverage.xml`. No minimum is enforced
  yet.
- Development dependencies added for the new gates: `mypy`, `types-PyYAML`,
  `pytest-cov`.
- Contribution governance: `CLA.md` (the Individual Contributor License
  Agreement and how to sign it, manually during the private phase — a CLA bot is
  deferred to public launch), the signature record at
  `docs/governance/cla-signatures.md`, and a pull-request template that makes
  the CLA its first checklist item alongside commit format, the provenance
  guard, golden-file justification and the quality gates.
- Honest-claims lint (WA-06, TE-15): `tools/honest_claims_lint.py` scans `src/`, `docs/`,
  `README.md` and `CHANGELOG.md` for the banned overclaiming phrases listed in
  `tools/honest-claims-phrases.txt` (case-insensitive substring match), exempting the
  vendored fixture corpus (`tests/fixtures/properties/`) by path. A line that genuinely
  needs to quote banned wording (e.g. explaining the ban itself) can carry a justified
  `honest-claims: allow: <reason>` pragma on that line or the line directly above/below; an
  unjustified pragma is itself flagged, not a silent bypass. Wired into CI as its own
  dependency-free `honest-claims` job, alongside `provenance`. There is no bypass flag.
  `tools/honest-claims-phrases.txt` is committed as an owner-reviewed, owner-sanctioned
  artifact (a mechanical banned-phrase gate can never pass a file whose every line *is* the
  banned phrase, the same bootstrap tripwire GOV-09's provenance guard hit); a new test
  (`test_the_phrase_list_matches_the_companion_skills_copy`, skipped unless the
  development-process repository is checked out beside this one) asserts it stays
  phrase-for-phrase identical to the interactive `honest-claims` skill's own list, so the
  two cannot silently drift apart.
- Provenance guard: `tools/provenance_guard.py` and
  `tools/provenance-manifest.json` record the SHA-256 of every vendored file in
  this repository (the 63-file acceptance fixture corpus) and a new
  dependency-free CI job fails the build on an edited, deleted, or hand-added
  file. The manifest is derived from the vendored documentation package's
  provenance record; the sanctioned re-vendor path — vault first, then bytes,
  provenance rows and a regenerated manifest in one commit — is documented in
  `docs/governance/re-vendoring.md`. There is no bypass flag.

### Changed

- **A tool-bound chat model now carries a `config_digest`, and its tool set is part of
  `graph_version`** (card EX-16; INTROSPECTION-SPEC §7.4 (a) as amended by **DEC-21**, whose
  enumeration is the A1-D21 addendum; supersedes the PD-028 D5 recorded limit). `.bind()` on a
  chat model has returned a `RunnableBinding` **subclass** since langchain-core 1.4.0, and the
  composition gate matches by exact type — so until now `prompt | model.bind(tools=…)` was
  declined at that gate: the model got no node of its own and no digest, and only an
  `lcel-composition-not-stock` warning said so. The gate now admits an **enumerated** set of
  stock langchain-core binding subclasses (`gebra.extraction.stock`; `_ChatModelBinding` at the
  pinned substrate), so the model is discovered under the wrapper, carries its `config_digest`,
  and the bound tools ride the digest's `"bound"` overlay. Editing a tool's name, description or
  parameter schema — or adding one — now moves `graph_version`, exactly as editing prompt text
  does.
  - **This moves `graph_version` for existing tool-bound workflows**, because the node set gains
    the model's node. That is the ruled outcome rather than a side effect: DEC-21 closes the gap
    deliberately before the first release. It also closes a matrix inconsistency EX-17 recorded —
    below langchain-core 1.4.0 `bind()` returns the stock class, which was already admitted, so
    the same authored workflow used to extract to *different node sets* on different cells of the
    tested matrix. Both ends now agree.
  - **Every other `RunnableBinding` subclass stays declined**, with the same warning as before
    (DEC-20 stockness discipline): a subclass can answer `bound` or `kwargs` with code of its
    own, and extraction runs no such code. The admitted classes are checked — against the
    *installed* substrate, not against the source they were read in — to override neither member,
    and the enumeration itself is re-derived from the substrate by a drift test, so a
    langchain-core release that adds a stock binding subclass fails the suite instead of being
    silently admitted or silently missed.
  - **One limit worth knowing before relying on the slot.** Tools reach the digest through the
    ratified coercion K: the mainstream shape — the JSON-schema dicts a provider's `bind_tools`
    converts to — is digested member by member, but a tool passed as a `BaseTool` *object* is not
    JSON data and is recorded by its class identity, so swapping one `StructuredTool` for another
    does not move the digest. Tested in both directions and recorded as a 1.x item rather than
    improvised around.

- **P-04's emitted `location.path` no longer names phantom vertices** (DEC-26, the §0.3
  phantom-leak rule — closing the fork fidelity-matrix entry FM-008 had recorded, the same
  leak class DEC-12 closed for P-01's `terminal_nodes`). On P-01-dirty topology the
  degradation convention still carries the phantom internally and the verdict, condition,
  key and node anchor are exactly as before; only the reported path is cleansed
  (`mixed/04`'s emitted path drops `legal_hold_review`, pinned in both directions). The
  FM-008 row itself stays open as ruled recorded residue — this closes its fork, not its
  observation. Also under DEC-25 (PD-040): REPORT-FORMAT-SPEC OI-8 closes — Appendix C's
  state-key FQN is amended to `state:<key>`, which is what the shipped exporter already
  emits; and the `orphan-node` registry note reroutes its condition-(iii) fixture pointer
  to DEC-16 gap-fixture work (DEC-26 marker lift).

- **`mixed/08` corpus revision (DEC-24, WA-04 route) — the last fidelity-matrix deviation
  with a corpus route is closed, and the corpus-green gate now runs `--strict`.** The
  fixture's P-04 failure record gains the one optional diagnostic the shipped validator
  emits and four sibling fixtures already encoded emit-iff-non-empty for
  (`writers_on_other_paths: [compliance_gate]` — §4.4 Step 4 + DEC-11 decision 3); the
  revised block was verified equal to the validator's live output before filing. With it,
  every R3.2-scoped wedge obligation matches (41/41), FM-009 moves to the matrix's closed
  section, the R3.1 compose attribution is reclassified accounted-not-residue per the
  ratified PD-039 Q1 reading (the four causes are a closed set), and the `corpus-green` CI
  job takes `--strict` — SOW §2 criterion 2 in its literal form. A vault clarifying
  addendum to DEC-12 rides the same vault commit, fixing that its byte-identity sentence
  speaks about `mixed/04`'s merged fixture list, never P-01's own `co_failures` ordering.

- **`REPORT-FORMAT-SPEC` §4.5 records three FQN readings, and Appendix B gains OI-8** (card
  CLI-03; editorial, so `report_format` stays `1.1` per §1.6's last row). The edge FQN's
  `#<kind>` segment reports what the anchor carries (`conditional` when a label is present,
  `normal` otherwise), because an `EdgeLocation` carries no ledger edge kind; a cycle, SCC or
  path FQN is spaceless, because an FQN is an identifier and the spaced walk is the human
  surface's. And the state-key FQN is `state:<key>`: PROPERTY-CATALOG-SPEC Appendix C spells `state:<SchemaName>.<key>`, but
  IR 1.0's Σ is a nameless mapping and the §0.3 envelope carries no schema identity, so no
  producer can fill `<SchemaName>` — and supplying one from outside the report would make A.6's
  fingerprint depend on the caller. Appendix C is frozen and wins where the two differ, so the
  divergence is recorded as **OI-8** and filed as an issue-ready WA-03 spec-defect note
  (PD-040 in the delivery repository) rather than reinterpreted locally. Filed now rather than
  at the D-12 promotion because the FQN feeds `gebraConditionHash/v1`: nothing has shipped, so
  settling the spelling early costs nothing and settling it late moves fingerprints.
- **`REPORT-FORMAT-SPEC` A.4 records one refusal** (card CLI-03): a finding whose condition ID
  is registered but not emittable has no rule in the A.3 catalog, and A.4's "never dropped" is
  the rule a silent skip would break — so the exporter raises. `verify()` cannot produce such a
  report; only a document loaded from another build can carry one.
- **`CLI-SPEC` Appendix B OI-9 is closed** (card CLI-03). The rendering obligation it asked for
  landed at VAL-11 as `report_format` `1.1`'s `best_effort` field plus REPORT-FORMAT-SPEC §4.2,
  §4.6 rule 9 and §5.1 rule 7; CLI-03's human surface implements it and a test holds it there.


- **The P-06 `unprotected-cycle` operator now declares a termination-witness blanket on both
  halves** (card TE-09, applying TE-10's own hand-off note). The self-loop it adds is an
  unwitnessed simple cycle, so once P-02 was registered the same edit moved two verdicts and
  "breaks exactly one property" stopped being true of it. A justified
  `runtime.recursion_limit` (TERMINATION-WITNESS-SPEC §2.2; IR-SPEC §3.5) discharges every
  cycle at once without touching an edge kind, and no wedge validator but P-02 reads
  `runtime` at all, so P-06's `region == "cycle"` prediction is untouched. Making the loop
  `conditional` with a counter guard would have been the obvious repair and is the wrong one:
  a conditional intra-component edge puts the node in a structural retry region under
  PROPERTY-CATALOG-SPEC §6.4 Phase 3 (DEC-13), destroying the prediction the operator exists
  for.
- **Two golden-harness projection rules now apply the run-level rules
  `docs/specs/REPORT-FORMAT-SPEC.md` states, and two decision-log rows closed with them**
  (card TE-04). `PR-3` — a wedge property's findings riding another property's report as
  advisories — reduces **both** sides' locations to their §0.3 anchor before comparing, which
  is §3.2 rule 3 (a projected finding keeps its anchor and drops the concrete subtype's
  evidence) applied through `gebra.verify.anchor_location`. It was previously comparing the
  fixture's already-projected form against the property's own un-projected record, so the two
  sides could never agree on shape however right they were on substance. `PR-1` — one
  property's share of a mixed fixture's block — compares the restricted co-failures of a
  **merged** source list as a multiset, on §3.3's rule that above one property "order carries
  no meaning" and records are identified by `(property, property_condition, location)` rather
  than by position; everything else in the projected report stays exactly compared. Neither
  is a relaxation of the comparison: `Failure.co_failures` is not marked `SetCompared` (that
  would assert what PROPERTY-CATALOG-SPEC §1.4 Step 5 denies), no validator changed, and no
  vendored fixture was touched. P-01 still emits §1.4's order and P-08 still anchors on
  §8.3's subtype, both still pinned in their own suites.
- **`report_format` `1.1`** (card VAL-11, `docs/specs/REPORT-FORMAT-SPEC.md` §1.6, MINOR).
  Two members join shapes that did not carry them at `1.0`. `Promotion.property_condition`
  is now carried on a `witness-note` promotion where the owning property's spec fixes an
  identity for the promoted kind: P-02's `scc-covered-only-by-recursion-limit` promotes
  under `cycle-without-termination-witness` with `blanket_only: true` on its location, which
  is TERMINATION-WITNESS-SPEC §6.1's third profile row — "the strict promotion reuses the
  same condition ID … no new condition ID is introduced". `gate.promotions` is the only
  artifact a promotion appears in (a note does not project to SARIF), so at `1.0` that
  frozen rule had nowhere to land; this is the gap VAL-08 handed forward, closed. The
  identity names the promoted **item** and is never a grade — the record keeps its own
  WARNING severity, the id never enters `gate.counts`, and §4.6 gains the copy rule that
  says so. `RunReport.best_effort` is the second member. Two invariants `1.0` stated only in
  prose became model validators in the same change: §2.2's "the two never disagree" between
  `outcome` and `exit_code`, and `Promotion`'s own present-iff rules. No `1.0` document was
  ever produced — no `RunReport` existed in code until this card — so the bump is a
  bookkeeping event rather than a compatibility one.
- **`gebra.verify.strict_promotions()` now refuses a WARNING-grade note that carries no
  location** (card VAL-11, found at its pre-review), instead of answering with an empty
  selection. TERMINATION-WITNESS-SPEC §6.1 reports a promoted item on its residual SCC, so a
  note naming none has nothing to be promoted on — and a silently dropped promotion is a gate
  a strict run was owed. It joins the two refusals that were already there (an unknown
  WARNING-grade note kind, and a note anchored off an SCC) on the same rule. No shipped
  behaviour changes: every note P-02 emits carries its SCC. `verify()` turns all three into a
  `stage: "dispatch"` tool error rather than an exception, so a refusal cannot make one IR
  answer normally without a strict flag and raise with one.

- **`docs/specs/REPORT-FORMAT-SPEC.md` §1.3 — `subject.source` for an extracted subject** is
  the target reference the invocation resolved, not the extraction envelope's
  `extracted_from.source` (found while CLI-02 designed input modes). That envelope field is the
  extracted object's *type* identity, so it is the same string for every extracted run, which
  would have collapsed the SARIF `automationDetails.id` onto one value for every workflow in a
  repository — the opposite of what Appendix A.7 derives it for. No model changed, so
  `report_format` stays `1.0` (§1.6).
- **`mixed/10` corpus revision (DEC-23, WA-04 route) — the all-properties-pass fixture now
  passes for reasons the shipped validators can derive.** Three parts, one vault commit:
  its router guard is reworded to the corpus's prose-conjunct style
  (`'retry' if publish failed and attempts < 3 else 'done'`), so the declared P-02 bound is
  inside the TERMINATION-WITNESS-SPEC §3 grammar instead of hidden behind a quoted
  comparison; `price_data`/`news_data` are declared `optional: true` — running the shipped
  P-04 validator surfaced that the parallel fan-in reads otherwise fail under §4's
  every-path quantification, which the fixture's `unmodelled` P-04 sub-block had kept
  invisible; and that sub-block's pre-contract aggregate is replaced by the §4.3
  `DataflowWitness` the validator actually derives (closing fidelity-matrix entry FM-003 —
  the harness now asserts it as a matched obligation). The guard-recognizer census tests
  and the fidelity matrix moved in lockstep: nine of the corpus's forty-eight guards are
  now recognized, and fourteen routers (not fifteen) still declare a bound the grammar
  cannot reach — none of them claiming a P-02 witness; that residual idiom is registered
  as a candidate Phase-1 grammar widening, not a Phase-0 change.
- **Two numbers the decorators now refuse, because the IR could never carry them.** A
  non-finite `temperature` (`@gebra.deterministic(seed=1, temperature=float("nan"))`) and an
  integer outside the exact range JSON round-trips, ±(2⁵³−1), in either `deterministic.seed`
  or anywhere inside `args_schema`. Both were previously accepted at the decorator and then
  rejected by the canonical form, so the failure arrived as a `CanonicalizationError` the
  first time anything asked for a `graph_version` — with nothing pointing back at the
  decorator that introduced the value. You now find out where you wrote it. On the sidecar
  these are warnings and the slot is dropped, like every other sidecar validation failure.
  (TOML integers are 64-bit, so a large `seed` in a sidecar is an easy thing to write.)
- **Runtime dependency added on Python 3.10 only: `tomli`.** The `gebra.toml` sidecar is
  TOML, and the parser for it (`tomllib`) is in the standard library from 3.11 on. `tomli`
  is that same parser under its pre-stdlib name, so on 3.11+ nothing is installed and
  nothing changes. It was already a development dependency for the packaging tests; it is
  now a runtime one, conditional on `python_version < "3.11"`.
- The IR's `entry`/`finish` list form no longer requires at least one member, and the
  scalar form now requires a non-empty string. Both follow the ratified ruling DEC-18, which
  amended the specification and the vendored fixture schema together: the empty list became
  the way to say "no statically known sentinel wiring", so an empty *string* had to stop
  being a second way to say the same thing. Nothing that was valid before is invalid now
  except `entry: ""`/`finish: ""`, which no workflow could have meant; no existing document
  changes shape, and no `graph_version` moves — the frozen golden vector digests to the same
  string it always has. `ir_version` stays `1.0`.
- `ExtractionError` gained two `reason` codes for refusals the builder path can hit:
  `construct-not-carried` (the object is fine, this build has no shape for something it
  declares) and `unrepresentable-node-id` (a node name that is not a node id under any
  grammar — today, the empty string, which LangGraph itself accepts). Existing codes are
  unchanged.
- `edge-target-undefined` (P-01) is now **ratified and emittable**: its §0.4 decision
  record DEC-12 landed in the specification vault (commit `9093972`), so the condition-ID
  registry flips `ratified_by`/`precedent` accordingly and the vendored `mixed/04` fixture
  gains the ratified ID's first in-corpus precedent (one appended co-failure; primary and
  existing co-failures byte-identical). Re-vendored per the sanctioned procedure in
  `docs/governance/re-vendoring.md`.
- Build backend migrated from setuptools to **hatchling** (`hatchling>=1.27`),
  the backend ruled for this repository. The `[tool.setuptools.*]` tables are
  replaced by `[tool.hatch.build.targets.*]`; the wheel still ships `gebra/`
  from the src layout with its `py.typed` marker, and the project metadata
  (including the PEP 639 `license` expression) is unchanged. The setuptools-era
  `src/gebra.egg-info/` build artifact is removed.
- The repository is now **uv-managed**: `uv.lock` is committed and pins the
  default development environment. `uv sync --extra dev` is the documented
  setup path and CI syncs `--frozen`; `pip install -e ".[dev]"` remains
  supported and is exercised by its own CI job. Per-cell compatibility-matrix
  pins stay out of the lock.
- Development dependency added: `tomli` on Python 3.10 (stdlib `tomllib`
  covers 3.11+), used by the packaging tests to read `pyproject.toml`/`uv.lock`.
  (Since promoted to a runtime dependency by the sidecar loader — see the entry
  at the top of this section.)
- `mypy --strict` now also covers `tools/`, the development tooling CI executes;
  it stays out of the wheel; the sdist carries it so the shipped tests stay
  runnable.
- `ruff format`/`ruff check` scope now excludes the vendored fixture corpus
  (`tests/fixtures/properties/`) so the formatter never proposes edits to a
  frozen, byte-copy vendored surface (WA-04/WA-11).
### Fixed

- **The snapshot store no longer accepts a workflow it can never diff — the ir 1.1 decline is
  now made at the mouth, on every surface, and documented** (card SD-12, a regression card
  against SD-03/SD-07; the posture is PD-044 D11's — consumers with no 1.1 semantics decline,
  they do not default — over the edge kind DEC-28 ratified). A `dynamic`
  edge is what `gebra.extract()` emits for a router whose target set is not statically known —
  a bare-`Send` map-reduce, or a hintless router — and the validator graph model and the
  topology diff have declined such a document from the start. Three surfaces built on top of
  the diff had not, and the seam showed on all four of the ways it could:
  - **`gebra.snapshot.snapshot()` / `record()` stored one into an *empty* store.** The label a
    snapshot gets is derived by diffing it against the store's current one, so the first
    snapshot — the only one with nothing to diff against — was the one place the decline was
    never reached. Every later *changed* re-snapshot of that store then failed, in words about
    a topology graph the caller never asked for, leaving a store nothing could move forward.
    Both entry points now raise `DynamicEdgeUnsupportedError` **before anything is written**,
    and say so in their `Raises`.
  - **`gebra.audit.freshness()` did the same on a stale pair**, and now declines in all three
    of its states rather than only where a diff happens to run — reporting `unsnapshotted` for
    such a document would have sent a reader to a `snapshot()` call that refuses it.
  - **The `@pytest.mark.gebra_freshness` gate printed a raw traceback**, because the hook
    caught `GebraTargetError` and `ValueError` and the decline is a `NotImplementedError`
    subclass. The item now fails with the designed `pytrace=False` message — "the freshness
    check could not be made" — beside the damaged-store and unextractable-target refusals it
    belongs with, and it is reported as neither fresh nor stale, because no comparison was made.
  - **A store that already holds a 1.1 snapshot errors with guidance; nothing is migrated.** The
    refusal closes the route the snapshot engine owns; a store can still be in that state from a
    pre-fix build, a hand-written file, or a direct `SnapshotStore.write`, which has no edge-kind
    opinion of its own. Its bytes are left exactly as they are and stay readable through
    `SnapshotStore.read`: rewriting the document without its `dynamic` edge would delete a
    declared router from `graph_version` hash scope — the silent drop DEC-28's amendments forbid
    — and move a digest under a V.S.F.E label that already names other content.
  - **No ir 1.0 behaviour changed**; the guard tests the edge kind and nothing else. When the
    1.1 validator semantics land, these refusals are re-visited in the same card that lifts the
    validator gate.

- **Version-portable test suite: cells 1 and 2 of the tested matrix are green on all four
  Pythons** (card EX-17; PD-038 Findings 2–3). The GOV-04 13-cell matrix reported 36 red
  extraction tests on the two frozen
  VERSION-COMPAT §3 cells below langgraph 1.2, plus one
  CPython-3.11-only failure. None of them was a defect in `gebra`: the extraction code reads
  whatever surface the installed substrate has, and it was the *suite* that assumed one cell's.
  Three causes, each fixed where it was:
  - **15 failures in `tests/extraction/test_compiled.py`** — `tests/sample_workflows/sentinel_compiled.py`
    built two fixtures with `StateGraph.set_node_defaults(...)` and
    `StateGraph.add_node(..., error_handler=...)`, both introduced in **langgraph 1.2.0**, so
    fixture construction died on cells 1–2 and took the WA-07 tripwires down with it. The two
    fixtures now join the table only where their API exists; the tests that read them skip with
    a reason naming the API and the minor, and the names stay in every parametrization so the
    cases read as named skips rather than vanishing. New `tests/substrate.py` holds every such
    predicate in one table (read from `importlib.metadata`, never by importing the substrate),
    and `tests/test_substrate.py` re-derives each one from the installed packages so a
    mis-stated boundary fails a test instead of silently mis-gating a fixture.
  - **21 failures in `tests/extraction/test_digests.py`** — cause identified (PD-038 left it
    open): **langchain-core**, not langgraph, and not the digest rules. From core **1.4.7**
    `BaseChatModel` fills its `metadata` field with `{"lc_versions": …}`; below it the default
    is `None`, which INTROSPECTION-SPEC §7.4 (c) omits — so the config form legitimately has no
    `metadata` member on cells 1–2, and the fixture had the 1.5-era form hard-coded. From core
    **1.4.0** `bind()` answers with the `_ChatModelBinding` subclass; below it the stock
    `RunnableBinding` comes back and §5 stitching descends into it, so the model *is* discovered
    and no `lcel-composition-not-stock` record is due. Both are ruled behaviour, not spec
    defects — §7.4 (e) names a substrate release moving `config_digest` as exactly what the
    VERSION-COMPAT drift probes exist to detect — so the expectations now state what each
    substrate does, in both directions, and a new positive control pins the stock-binding
    reading on every cell.
  - **1 failure in `tests/annotations/test_inference.py`** — a 6000-term expression fails
    `ast.parse` on CPython 3.11 and parses on 3.10/3.12/3.13 (stdlib-only; no `gebra` and no
    substrate involved). The property being pinned — a body too deep for the machinery degrades
    to the D-011 floor, never an exception out of `infer()` — is unchanged and now asserted
    unconditionally, with the *route* to that floor pinned against what each interpreter's own
    `ast.parse` actually does. A second test at a depth every tested interpreter parses keeps
    the `body-too-deep` walk route covered everywhere.
  - Also fixed: the hash-seed determinism child in `tests/extraction/test_lcel.py` replaced the
    parent's `PYTHONPATH` instead of prepending to it, which dropped the substrate for anyone
    reproducing a matrix cell through a private prefix. Its assertions are unchanged.
- **Cold-cache `mypy --strict` failure on `main`, and a regression guard for the class**
  (card GOV-11; PD-038 Finding 1). From a cold cache — what every CI runner always is —
  `mypy` reported two genuine `--strict` errors at
  `tests/sample_workflows/sentinel_resolution.py:290-291` (a `typeddict-item` on the
  fixture's lone-surrogate state key and a `redundant-expr` on the always-truthy fixed
  2-tuple that guarded it), and mypy 2.3.0 then crashed serializing the surrogate-bearing
  error text into its own cache — on a strict-UTF-8 pipe (CI log capture) the crash happens
  before the two errors even print, so the `typecheck` job showed only an opaque internal
  error. Invisible under a warm developer `.mypy_cache`, which never re-runs a stale SCC and
  reports `Success`; the GOV-04 13-cell matrix multiplied the crash across all 13 cells.
  Both errors are now cleared without weakening the fixture: the surrogate-key read stays a
  literal `state["\ud800"]` subscript in source (the annotation-inference AST walk reads it
  as text, never at runtime — the node is armed and always raises first), carrying a
  targeted, justified `# type: ignore[typeddict-item]`; the redundant-expr is gone because
  the branch now tests `all(seen)` — a real runtime question — instead of a fixed 2-tuple's
  statically-known truthiness. `tests/test_mypy_cold_cache.py` is a new regression guard
  that shells `mypy` against a fresh `--cache-dir` (never against the repo's own
  `.mypy_cache`) so this class cannot hide behind a warm cache again; it runs in the default
  `pytest -q` lane (`test-locked` in CI), not only inside the 13-cell compat matrix.
  `tests/extraction/test_contracts.py::test_an_inferred_slot_the_ir_cannot_carry_is_dropped_and_unnamed`
  — the test that actually exercises the surrogate path through extraction — stays green and
  unchanged.

