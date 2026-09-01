# Never-invokes tripwire audit (WA-07 · SOW §2 criterion 5 · INTROSPECTION-SPEC §1)

This is the path-to-tripwire audit for the never-invokes invariant: `gebra.extract()` **imports
and inspects — it never invokes** (INTROSPECTION-SPEC §1; decisions D-018/D-023). No extraction
path calls a node function, router, or tool; contacts an LLM; or opens a network connection. The
invariant is a tested one, not a convention (SOW §2 criterion 5).

It is the index a reviewer reads to answer *"does every landed extraction path carry a
tripwire?"*. It is **machine-checked**: `tests/test_never_invokes.py::test_the_audit_table_lists_every_extraction_path`
reconciles this table against `src/gebra/extraction/` on every run, so a new path that lands
without a row here — or a row naming a tripwire file that does not exist — fails the suite.
A path that lands adds its row here in the same commit (WA-02).

The claim each tripwire makes is bounded, never blanket: several paths perform *reads*
INTROSPECTION §1 rule 3 licenses (`typing.get_type_hints()` evaluates annotation expressions,
`get_graph()` runs a bounded symbolic drawing over stock objects). What must never run is a node
or router **body**, a user channel/checkpointer/mapper method, a pydantic validator, or a
`ValueType()` constructor — and that is what each tripwire arms.

## 1. Extraction paths — `src/gebra/extraction/`

Each guarded path arms a fresh interpreter (sockets, name resolution, `StateGraph.compile`, and
more) and extracts every shape under the guard, so the never-invokes claim covers the whole path
rather than the one line a test happened to touch. Each carries an **armed control** — a probe
that proves the tripwire trips when something *does* run, so a tripwire nobody trips proves
nothing.

| Path (module) | INTROSPECTION § | Tripwire test | Armed control |
|---|---|---|---|
| `dispatch.py` — object-family dispatch + boundary errors | §2 | `tests/extraction/test_dispatch.py` | socket/name-resolution/`compile` raisers |
| `builder.py` — `StateGraph` (§3) extraction | §3 | `tests/extraction/test_builder.py` | `compile` replaced by a raiser before first extract |
| `routing.py` — §6 edge classification (reads return hints) | §6 | `tests/extraction/test_routing.py` | router/node bodies record before they raise (`TRIPPED`) |
| `state.py` — Σ (state-schema) projection | §3 | `tests/extraction/test_state.py` | pydantic validators, `__init_subclass__`, `ValueType`, reducers armed |
| `contracts.py` — §3/§6 precedence + §6 wrapper walk | §3/§6 | `tests/extraction/test_contracts.py` | `StateNodeSpec.runnable` wrapper-chain reads armed (`TRIPPED`/`PROBED`) |
| `inference.py` — §4 engine-side warning records | §4 | `tests/extraction/test_contracts.py` (shares) | reaches no substrate of its own; shares the contract path's guard |
| `compiled.py` — `CompiledStateGraph`/`Pregel` (§4) + `get_graph()` gate | §4 | `tests/extraction/test_compiled.py` | six drawing routes armed (table 2); `Runnable.invoke` armed with a counted `ChannelWrite` allow-list |
| `lcel.py` — LCEL fragment (§5) stitching | §5 | `tests/extraction/test_lcel.py` | every `Runnable` execution entry point + `get_graph` + `uuid4` armed |
| `digests.py` — §7.4 prompt/config digests | §7.4 | `tests/extraction/test_digests.py` | `repr`/`__str__`/config-source reads armed (`TRIPPED`) |
| `stock.py` — §7.4(a) stock binding-wrapper enumeration | §7.4(a) | `tests/extraction/test_digests.py` (`NonStockBinding`) | non-stock `kwargs` records and raises; `tests/extraction/test_stock.py` re-derives the enumeration from the installed substrate |
| `compat.py` — first-extract version check (VERSION-COMPAT §4) | §1 | `tests/extraction/test_compat.py` | every network primitive armed; reads `importlib.metadata`, never the packages |

**Data-only modules (read no live workflow object; nothing to invoke).** `base.py` (object-family
enum + `type_identity`), `envelope.py` (envelope models), `errors.py` (`ExtractionError` types),
`warnings.py` (the §8 warning taxonomy), and `sidecar.py` (the loader→extraction seam — it builds
records from a parsed reading; the `gebra.toml` loader itself is `tests/annotations/test_sidecar.py`).
These hold and serialize IR/envelope/warning data; they read no channel, node, router, model, or
drawing, so there is no body for them to run.

## 2. The six `get_graph()` drawing routes (DEC-19 · INTROSPECTION §1 rule 3/4)

DEC-19 (2026-08-03) replaced §1 rule 3's "no user code runs" parenthetical: at langgraph 1.2.x a
`get_graph()` drawing can reach user code by six pinned routes — five that run a user *body*
(routes 1–5) and one that is a network call (route 6). `compiled.py`'s
`_drawing_hazard` is the required provenance-verified gate in front of every drawing call; it
declines the SHOULD-grade cross-check, or refuses at the object boundary where the drawing is the
only surface. Each route has an armed fixture in `tests/sample_workflows/sentinel_compiled.py`,
asserted in `tests/extraction/test_compiled.py`.

| Route | Reaches | Armed fixture |
|---|---|---|
| 1 | a user `BaseChannel` method (earliest `from_checkpoint`) | `ArmedChannel` |
| 2 | a checkpointer's `get_next_version()` | `ArmedSaver` |
| 3 | a node `cache_policy.key_func` | `armed_cache_key` |
| 4 | a `ChannelWrite` entry `mapper` (a literal `Runnable.invoke`) | `armed_mapper` |
| 5 | a `__root__` channel's `ValueType()`, **called as a constructor** | `ArmedRootValueType` |
| 6 | a builderless `PregelProtocol` object's network call (`RemoteGraph`) | `SocketOpeningPregel`; the child also asserts `langgraph.pregel.remote` never enters `sys.modules` |

The gate lets one thing through by design: a drawing of a *stock* `Pregel` runs LangGraph's own
`ChannelWrite.invoke` on LangGraph's own objects — library code, not the workflow. The compiled
guarded child arms `Runnable.invoke`, allow-lists `ChannelWrite`, and **counts** those calls, so
that stated residue is a counted one and every other invoke trips.

## 3. The §1 rule 4 named hazards and the consolidated adversarial suite

INTROSPECTION §1 rule 4 names four hazards beyond node/router bodies. Each is covered in depth by
the path whose reads reach it, and all four together by the consolidated adversarial suite
`tests/extraction/test_never_invokes_adversarial.py`, which extracts one workflow packing all four
through the public `gebra.extract()` and asserts nothing fired.

| Hazard | Deep coverage | Consolidated |
|---|---|---|
| pydantic validator execution | `tests/extraction/test_state.py` (`PydanticState`), route 5 above | adversarial suite |
| `__init_subclass__` hooks | `tests/extraction/test_state.py` | adversarial suite |
| decorator side effects (at import) | `tests/annotations/test_decorators.py`, `tests/extraction/test_contracts.py` | adversarial suite |
| string/forward-ref annotation evaluation | `tests/extraction/test_routing.py`, `tests/extraction/test_state.py` (`from __future__ import annotations`) | adversarial suite |

The **seeded-execution** property SOW §2 criterion 5 asks for — *the suite fails if a sentinel
executes anywhere* — is armed two ways: every guarded child above carries a control that seeds an
execution in a fresh interpreter and asserts a non-zero exit (e.g.
`test_compiled.py::test_each_raiser_is_armed`, `::test_the_invoke_guard_notices_a_non_channelwrite_invoke`),
and the adversarial suite's `test_a_seeded_execution_is_caught_by_the_invariant` seeds one
in-process and shows the record-based invariant is what catches it.

## 4. The annotation surface and the non-extraction WA-07 paths

The annotation surface feeds extraction and carries its own guarded children: `contract.py`
(`tests/annotations/test_decorators.py`), the `gebra.toml` loader `sidecar.py`
(`tests/annotations/test_sidecar.py`), the §4 shallow-inference engine `inference.py`
(`tests/annotations/test_inference.py`), and the precedence chain `resolve.py`
(`tests/annotations/test_resolve.py`). Five landed paths sit **outside** extraction and carry the
weaker form of the guard where no user object is in reach — the `.gebra/` store
(`tests/store/test_store.py`), the V.S.F.E version engine (`tests/versioning/test_classify.py`),
the diff engine (`tests/diff/test_topology.py`, `tests/diff/test_workflow.py`), the
version-history engine (`tests/lineage/test_engine.py`), and the audit-export/freshness engine
(`tests/audit/test_freshness.py`, card SD-07) — each asserting the rest of the invariant
(no langgraph/langchain import, no connection) with an armed negative control. The last of those
is deliberately IR-level: `gebra.audit.freshness` takes a `WorkflowIR` rather than a live
workflow, so the extraction leg belongs to the pytest plugin and the package itself can be held
to the *import* claim as well as the invocation one. Its child exports two whole stores, reads
every export back, and asks all three freshness questions; networkx is on the allowance list and
asserted imported, since a stale outcome carries a `gebra.diff` diff.

One landed path outside `src/gebra/extraction/` carries the **strong** form instead, because it
is the one that hands a live workflow object to the extractor: the snapshot engine
(`src/gebra/snapshot/`, card SD-03), guarded by `tests/snapshot/test_travel_booking.py`. Its
child runs the whole `extract` → store path over the travel-booking agent — twice, so the
re-snapshot no-op is under the guard as well as the first write — in a fresh interpreter where
name resolution and connection opening raise from the first line and `StateGraph.compile`
raises from before gebra is imported at all (this card's subject is the builder, so nothing on
the path ever compiles). Socket **construction** is counted rather than refused while the
substrate imports — the same urllib3 IPv6 capability probe §1's `dispatch.py` row records — and
raises from the moment gebra's own work begins; the count is reported by the child rather than
collected silently, and deliberately not bounded. Every raiser the claim rests on has an armed
control matched on its full message, including the `sys.modules` leg no socket probe could arm
and one control that swallows the exception so the record-before-raise ledger is exercised. The
child pins the stored document to the agent's node set and to a fresh extraction's digest, so a
run that silently stopped reaching the agent fails rather than passes. It adds **no extraction
path** — it calls `gebra.extract()` and nothing else — so §1's machine check owes it nothing.
Two import claims sit beside the run: the child keeps `langgraph.pregel.remote`, the one
substrate module carrying a network client, out of `sys.modules`; and that importing
`gebra.snapshot` **does** pull langgraph — the cost of being wired to the extractor — is
measured in a separate child that imports nothing else, against a control child importing
`gebra.store`, `gebra.diff`, `gebra.versioning` and `gebra.lineage`, which pulls none.

The **audit path** (`src/gebra/audit/`, card SD-07) carries the strong form as well, in
`tests/audit/test_travel_booking.py`, and for a narrower reason than the snapshot engine's: the
engine itself hands nothing to the extractor, but the card's own acceptance is stated over the
live agent, so the whole `extract` → snapshot → export → read-back → freshness path is run in a
fresh interpreter under the same raisers (`StateGraph.compile`, `getaddrinfo`, `gethostbyname`,
`create_connection`, and socket construction once gebra's own work begins), with the same
counted-not-refused import-phase residual and the same `langgraph.pregel.remote` absence check.
The child pins the export to a *fresh* extraction's digest and the stale diff to the added
node's id, so a run that stopped reaching the agent fails rather than passes. **Seven armed
controls stand behind it** — SD-03's parametrized table ported verbatim in scope, one row per
raiser (socket construction, `getaddrinfo`, `gethostbyname`, `create_connection`,
`StateGraph.compile`), each matched on that raiser's **full** message so a control cannot drift
onto a different raiser and still look green, plus the two legs no network probe can arm: a
probe that fires the added node's own sentinel body and swallows the exception, so the
record-before-raise ledger is what fails the child, and a `langgraph.pregel.remote` import. The
per-raiser granularity is the point: `StateGraph.compile` is the whole of the §1 rule 2 evidence
on this path and socket construction the whole of the post-import network claim, so a table at
raiser-*class* granularity would leave both untested. It adds **no extraction path** — it calls
`gebra.extract()` and nothing else — so §1's machine check owes it nothing.

The **evolution sequence** (`tests/sample_workflows/travel_booking_evolution.py`, card SD-08)
extends the travel-booking *fixture family* rather than any engine surface: eight builder-level
versions of the TE-05 agent, whose every body — twelve node bodies and two routers of its own,
since the evolved stages carry schema-neutral twins of v1's functions — records itself in the
**same** `TRIPPED` ledger and raises the same `BaseException`-derived sentinel, so one ledger
covers the family and `tests/evolution/test_travel_booking_evolution.py` asserts it empty on
entry to and exit from every test. The arming test fires every body reachable from **any**
evolved stage's built graph — fourteen callables once deduplicated by function identity, the
twins the later stages supersede (`replan`, `check_booking`) included, since those stay the live
runnables most of the sequence hands to the extractor — so a node added to any stage, or
swapped in mid-sequence, and forgotten is still fired, and the fired label set is pinned to the
module's fourteen. The scenario carries the
**strong** form in the snapshot engine's pattern: a fresh-interpreter child runs the whole
eight-stage `snapshot()` → `extract()` → store sequence under the same raisers (name resolution,
connection opening, socket construction counted through the import phase and refused once
gebra's own work begins, `StateGraph.compile` removed before gebra is imported — every stage's
subject is the builder, so nothing on the path ever compiles), re-asserts each stage's expected
V.S.F.E label and bump class under the guard, pins the final stored document to the evolved node
set and to a fresh extraction's digest, and keeps `langgraph.pregel.remote` out of
`sys.modules`. Five per-raiser armed controls are matched on each raiser's full message, plus
the legs no socket probe can arm: a probe that fires an evolution body in both the raising and
the swallowed form — the record-before-raise ledger is what fails the swallowed one — and a
`langgraph.pregel.remote` import. It adds **no extraction path** — every stage goes through
`gebra.snapshot.snapshot()` and `gebra.extract()` and nothing else — so §1's machine check owes
it nothing.

The **seeded-defect variants** (`tests/sample_workflows/travel_booking_defects.py`, card SD-09)
extend the same fixture family once more: five builder-level variants of the TE-05 agent, one
per SOW §2 criterion-1 defect, each reusing v1's sentinel bodies wherever its story says
"unchanged" and carrying six schema-neutral twins of its own (five node bodies and the
`Send`-hinted `route_legs` router), every one recording itself in the **same** `TRIPPED` ledger
and raising the same `BaseException`-derived sentinel. `tests/dod/conftest.py` asserts the
ledger empty on entry to and exit from every DoD test; the arming test
(`tests/dod/test_dod_guard.py`) fires every body reachable from **any** variant's built graph —
seventeen callables once deduplicated by function identity, the eleven reused v1 bodies
included, so the collected surface is the whole family and a node added to a variant and
forgotten is still fired — and pins the fired label sets to both modules' expected names. The
strong form runs the DoD's whole catch leg in a fresh-interpreter child under the family's
raiser set (name resolution, connection opening, socket construction counted through the import
phase and refused once gebra's own work begins, `StateGraph.compile` removed before gebra is
imported — every variant's subject is the builder, so nothing on the path ever compiles):
healthy v1 verifies clean and **all five defects are caught under the guard** — named property,
condition ID, locus and gate, the defect-3 strict promotion included — so the DoD's acceptance
claim is asserted where nothing could have run. Five per-raiser armed controls are matched on
each raiser's full, DoD-specific message (no control can alias the evolution child's), plus the
legs no socket probe can arm: a defect twin fired in the raising and the swallowed form, and a
`langgraph.pregel.remote` import. It adds **no extraction path** — the only live objects the
harness touches go to `gebra.extract()`; everything after that is IR- and file-level engine
work (`gebra.verify.verify()`, `gebra.snapshot.record()`, `gebra.store.SnapshotStore`,
`gebra.diff.workflow_diff`, `gebra.audit`, `gebra.lineage`), each with its own §4 guard row —
so §1's machine check owes it nothing.

The **CLI's live-target resolution** (`src/gebra/cli/`, card CLI-04) is the seam CLI-SPEC §0.5
item 3 names: `gebra verify <module>:<attribute>` imports a module and hands what it finds to
`gebra.extract()`, and the explicit `--call` opt-in is the one path on which the CLI itself
calls a user attribute (once, no arguments, no signature probe — §2.4). Its tripwire is
`tests/cli/test_never_invokes.py` over `tests/sample_workflows/sentinel_cli.py`, in exactly the
shape the spec fixes: the sentinel derives from `BaseException` and records before raising, the
four armed points are the spec's four (node callables in the resolved graph; a zero-argument
non-factory attribute, pinning the refusal to call without `--call`; an argument-needing
callable under `--call`, pinning the exit-2 refusal; and an import-time marker, so the
"top-level code runs" concession is observed rather than assumed), every run goes through
`gebra.cli.main` — the function the console script names — and the never-invokes assertions
are on the ledgers rather than on the exit code, which §3.4 makes uninformative for that
purpose by mapping an escaping exception to a specified exit `2` (the exit codes the spec
itself fixes, like the exit-2 refusal, are of course pinned as codes). As a live-object hand-off to the extractor it also carries
the **strong** form, in the snapshot engine's pattern: a fresh-interpreter child arms name
resolution, connection opening, socket construction (counted through the import phase, refused
once the CLI's work begins — the same urllib3 capability-probe residual as every other guarded
child) and `StateGraph.compile`, then drives three whole invocations through `main()` (a
module-level graph, a `--call` factory, and the no-`--call` refusal) and asserts the ledgers,
the socket count, and `langgraph.pregel.remote`'s absence from `sys.modules`; five per-raiser
armed controls are matched on each raiser's full message, plus the leg no socket probe can arm
— a probe that fires a node body and swallows the sentinel, failed by the record-before-raise
ledger. A second child holds the boundary in the other direction: with the substrate made
**unimportable** (a `sys.meta_path` blocker), verifying an IR document completes on all three
`--format` surfaces and a stored snapshot version verifies end to end (store write,
digest-checked read, all thirteen properties) — which is `gebra.cli.resolve`'s lazy extractor
import held to its word on both substrate-free modes, and its own armed control imports
langgraph and dies. The CLI adds **no extraction path** — it
calls `classify()` (isinstance-only, INTROSPECTION §1 rule 3's licensed reads) to route §2.4's
refusal, and `gebra.extract()` for everything else — so §1's machine check owes it nothing.

The **store-facing verbs** (card CLI-05) put two more verbs in front of that same seam —
`gebra snapshot` over an import reference, and `gebra diff` with one or both sides one — and
add no resolution of their own: both drive `gebra.cli.resolve`'s §2.4 boundary exactly as
`verify` does, and the snapshot verb then hands the *same* envelope to
`gebra.snapshot.record` (whose own guarded-child evidence is the snapshot-engine paragraph
above; `record_document`, added at CLI-05, takes a file-loaded IR and reaches no live object
at all). Their per-path tripwire (CLI-SPEC §0.5's table rows 2–3) is
`tests/cli/test_never_invokes_store.py`, over the same sentinel module and through `main()`:
the four arms on **each** path (on diff, the refusal and argument-needing arms ride a mixed
invocation and the fresh-module import arm is its own), the mixed stored-label/import diff
the spec names, a two-sided `--call` diff, and two call-count pins only the factory ledger
can state — the snapshot verb's eligibility run and store write share **one** resolution
(one factory call per invocation, never one per phase), and a diff whose first side failed
resolves no further side, so no user code runs for a comparison that can no longer happen.
`gebra history` reaches no live object on any path: it reads `meta.yaml` and nothing else.

The **display verb** (card CLI-06) is the one CLI verb with **no** live-target mode at all:
CLI-SPEC §4.4 gives it the ir-document and snapshot modes only, so an import-shaped target
is a §3.4 *usage* error decided by grammar before resolution — no import, no attribute
read, no refusal-with-remedy that could tempt a later change into resolving it. The
emitter behind it (`gebra.display`, PD-034) is string-building over the IR models plus the
shared `gebra.verify.graph` model; it imports nothing from the substrate, and the
`--report` overlay path reads a JSON file through the run-report models — no network, no
execution, and the digest comparison is a string-compare. The evidence is in
`tests/cli/test_never_invokes.py`: the import-shaped refusal is held on `sys.modules`
itself (the sentinel module is demonstrably absent after the run, so its top-level code
never ran — a stronger fact than an empty ledger), the nonexistent `--import` selector is
held the same way, and the substrate-blocked guarded child runs the whole §4.4 surface —
a plain drawing, an overlaid drawing whose report was produced under the same blocker, and
a stored-snapshot drawing — to completion with `langgraph` unimportable. CLI-SPEC §0.5's
tripwire table therefore has no `display` row to land: the verb adds no extraction path,
and a change that ever gave it one pulls the §0.5 item 3 obligation with it (§7's CLI-06
entry states this in the contract itself).

The **CLI integration suite** (card CLI-07) puts child processes in front of the same seam
and adds **no extraction path and no live-target verb**, so CLI-SPEC §0.5's tripwire table
gains no row here. What its children reach, they reach through the shipped boundary the
rows above already cover: real `python -m gebra.cli` and console-script processes driving
`--import` + `--call` over the sentinel-guarded travel-booking family (one shared `TRIPPED`
ledger, `BaseException` sentinels) and `tests/cli/targets.py`'s body-less refusal targets.
A parent-process ledger cannot speak for a child, so the child legs rest on output/exit
disjointness instead, stated rather than hoped: a tripped body escapes `resolve.py`'s
deliberate `(Exception, SystemExit)`-only catches and maps to §3.4's crash — exit 2 with a
traceback banner — which is disjoint from every asserted live-path exit (0 or 1) and from
the `(stage: …)` refusal diagnostics the suite's exit-2 assertions pin, with byte-strict
goldens over stdout besides; the ledger-asserted guarded-child form for these boundaries
remains `tests/cli/test_never_invokes.py` / `tests/cli/test_never_invokes_store.py`,
untouched. The runner (`tests/cli/integration.py`) prepends the repository root to each
child's `PYTHONPATH` (src layout, so the installed package cannot be shadowed; the only
modules children import are the import-safe fixture modules), passes the environment
through minus the terminal variables, reads the SARIF schema and the banned-phrase list
from disk, and opens no network connection. The in-process legs execute nothing: the
corpus module runs `verify()` over file-loaded fixture IRs, the matrix module's one
registry monkeypatch constructs §2.6's `dispatch` tool error, and the flow module's
fixture use is imports and EVOLUTION-table reads under its own entry-and-exit `TRIPPED`
guard.

The **pytest plugin** (`src/gebra/pytest_plugin.py`, card TE-06) is another seam between a live
workflow object and the extractor — a marked function's return value goes straight to
`gebra.extract()` — and it carries **two** tripwires, because the claim has two halves and one
guard cannot hold both.

The *import* half is `tests/plugin/test_hermeticity.py`. What runs inside it is a whole inner
`pytest` session: the `pytest11` module is imported, a `@pytest.mark.gebra` target that is
already a `WorkflowIR` produces one item per wedge property, and the `gebra_workflow` →
`gebra_graph` → `gebra_verification` fixture surface runs on the same document — all in an
interpreter where every substrate import, socket construction and name resolution raises after
recording the attempt. The document is the travel-booking agent's own IR, extracted in the
parent, so the guard covers the card's acceptance subject rather than a minimal graph; the
substrate is unimportable in that child, so nothing there can build or compile a graph, which is
exactly why the live-object half is somewhere else. **Its armed control is the plugin's own other
branch**: the same child handed a target that is *not* a `WorkflowIR` must reach the extractor,
the blocker fires, the attempt is recorded and all five items fail — which is what makes the
fixture-only claim a fact about the branch taken rather than about the run being uneventful. Four
raisers stand behind it (the substrate-import blocker, socket construction, `getaddrinfo`,
`create_connection`), with five deliberate-trip rows over them and one further test for the
record-before-raise design: a swallowed `ImportError` leaves the child green and the attempt on
the record, and that is what is asserted.

The *live-object* half is `tests/plugin/test_plugin.py`, which drives inner sessions over the
sentinel-guarded agent and reads its `TRIPPED` ledger on entry to and exit from every test.
Bounded rather than blanket: those inner sessions are **in-process**, so the ledger is the same
list object and an escape is visible; the file's two `runpytest_subprocess` legs are a different
process and are covered instead by their own output assertions (and, for the extraction they
perform, by TE-05's guarded child over the same agent).

`tests/audit/test_freshness_gate.py` (card SD-07, the `@pytest.mark.gebra_freshness` marker)
carries the **same** in-process ledger assertion on entry to and exit from every test — and with
its own carve-out, stated rather than assumed. Every target that is a *workflow* is a live
object — the sentinel-guarded agent or its one-node-added variant — so the ledger is doing real
work there rather than standing in for a fixture-only run; no target is a `WorkflowIR` taking
`resolve_ir`'s fixture-only branch. The two exceptions are targets that are not workflows at
all and are there to be refused: `test_a_function_that_returns_nothing_is_a_usage_error_not_a_pass`
returns `None` and `test_a_target_that_cannot_be_extracted_is_reported_as_such` returns
`object()`. Its `runpytest` sessions are all in-process — the file has no `runpytest_subprocess`
leg — so the ledger is the same list object throughout and an escape would be visible. The
marker adds no extraction path: it calls `resolve_ir`, which is the plugin's own existing
branch, and the comparison after it is a digest against a stored digest.

`tests/test_dynamic_document_seam.py` (card SD-12, the ir-1.1 decline across the snapshot,
freshness and `gebra_freshness` surfaces) carries the in-process ledger assertion over
`tests/sample_workflows/sentinel_routing.py`'s `TRIPPED` — the ledger for the guarded builder
whose bare-`Send` router is what makes a document ir 1.1 in the first place — in the
**cleared-on-entry** form `tests/extraction/test_contracts.py` uses, and that is the one form
true of *this* ledger: `sentinel_routing.TRIPPED` is session-global and is deliberately filled by
`tests/extraction/test_routing.py`'s arming test, which fires every one of those callables to
prove the guard is live. Asserting it empty on entry would have been a claim about collection
order rather than about this file (and was: it failed this card's first full-suite run).

What that ledger covers is stated in the fixture rather than assumed, because the two halves
differ here: `route_send_list` records before raising, so an invocation of the *router* — the
declaration this whole card is about — is visible even if an `except Exception` on the extraction
path swallowed it; the two *node* bodies come from `sentinel_graph.raiser`, which raises a
`RuntimeError` subclass **without** recording, so an invocation of those is caught by the
exception propagating rather than by the list. The guarded child that holds that half for this
exact builder is `tests/extraction/test_routing.py`'s fresh-interpreter run over
`ROUTING_BUILDERS` (`dynamic_send_hinted` is a pinned member of that table), and the one that
holds the `snapshot()` → `extract()` → store *path* is `tests/snapshot/test_travel_booking.py`,
above. Exactly one test in the file reaches a live object
(`test_snapshot_declines_a_live_map_reduce_workflow`, which states the decline at the entry point
a user meets it on); every other target is a hand-built `WorkflowIR`, including the one the
generated inner test file returns, which takes `resolve_ir`'s fixture-only branch. Its `pytester`
session is in-process — the file has no `runpytest_subprocess` leg — so the ledger is the same
list object throughout. A guarded subprocess is **not** claimed here and is not owed: the card
adds no extraction path (it calls `gebra.snapshot.snapshot()` and nothing else), and the refusals
it adds reach no live object and trigger no extraction of their own — on the `snapshot()` path
extraction runs *first* and the decline is what stops the document being stored, never what stops
it being read.

`tests/plugin/test_gating.py` (card TE-07, the three gate flags) carries the **same** ledger
assertion on entry to and exit from every test in it, on the same in-process terms — and with
the same carve-out, stated rather than left to be assumed. Two of its targets are
live workflow objects (corrected at the 2026-08-12 post-landing review — a reviewer
fix-ordering artifact had left this paragraph counting one): the test that re-checks TE-05's
"clean under strict" hand-off on the travel-booking agent (in-process, same ledger object,
re-asserted), and `test_an_extraction_warning_survives_a_run_that_reached_no_verdict`, whose
subprocess child constructs and extracts `_build_warning_bearing_agent` — a live
`StateGraph` with sentinel-guarded bodies whose own ledger (`WIDENER_TRIPPED`) the child
asserts empty as its final act. Every other target is a `WorkflowIR` — some literal blocks
written in the file, some loaded from the vendored corpus — which takes `resolve_ir`'s
fixture-only branch and reaches no substrate at all. The second `runpytest_subprocess` leg is a
different process the parent ledger cannot speak for, and needs no cover: that child measures
the plugin's import closure over a test file that is an `import sys` and one assertion, so it
constructs no workflow object of any kind. The card adds no extraction path and no execution
seam: a gate flag decides which items are generated and which gate a run reports, and it
touches nothing on the way to `gebra.extract()`.

The plugin adds **no extraction path** — it calls `gebra.extract()` and nothing else — so §1's
machine check owes it nothing. That a marked function's *body* runs is outside §1's scope: §1
binds `gebra.extract()`, and the body is a pytest test function, called exactly as pytest's own
`pytest_pyfunc_call` would call it. The plugin takes the fixture names from the list pytest
already resolved rather than from `inspect.signature`, which under PEP 649 (3.14) would evaluate
the marked function's annotations inside the verification path.

The **round-trip drift suite** (`tests/drift/`, card TE-11) hands the extractor a live workflow
object per pair per round trip — seventeen designated pairs and eleven seeded variants, each
built fresh on every call — and it carries the ordinary in-process form of the guard rather than
a guarded child. Every node body in every mini builder script (the sixteen designated scripts
plus `tests/drift/seeded.py`) records itself in `tests.drift.sentinels.TRIPPED` and then raises a
`BaseException` subclass, so no `except Exception` on an extraction path can demote one to a
warning; `tests/drift/test_round_trip.py` reads that ledger on entry to **and** exit from every
test in the file, and `test_every_registered_node_body_is_armed` *fires* every one of them, so
the arming is measured rather than described. That test derives its set from
`builder.nodes[…].runnable` on the built graphs rather than from module-level naming — the
pre-review's finding, since a name-convention collection would silently miss a lambda, a
`partial`, a callable instance, or a body whose name happens to start with `build` — and it
requires each body to record **exactly one** label and that label to be its own. Two further
claims sit beside it, both stated as tests rather than as prose:
`test_extraction_never_compiles_a_graph` runs every designated pair *and* every seeded variant
with `StateGraph.compile` monkeypatched to a record-before-raise refuser of the same
`BaseException` grade the node bodies use, because PD-023 D4 makes the compiled document a
different document and a pair that reached `compile()` would be comparing the fixture against the
wrong one; and importing `tests.drift.builders` constructs no graph at all — every module defines
a state schema, decorated functions and a factory, and the factory is called only inside
`tests.drift.roundtrip.round_trip`.

A guarded subprocess is **not** claimed here and is not owed. The suite adds no extraction path —
it calls `gebra.extract()` and nothing else, so §1's machine check owes it nothing — and the
paths it reaches each already carry their own guarded child in §1 above. That reach is measured
rather than argued (`trace.Trace` over the whole set): `dispatch`, `builder`, `state`,
`contracts`, `inference`, `digests`, `warnings`, plus `compat` and `sidecar`, which every call
through the entry point traverses, plus `routing` — reached only by the one send pair, whose
`Send`-hinted node declaration is read through §6's hint machinery. `compiled`, `lcel` and
`stock` are not reached at all: nothing here is compiled, no LCEL fragment is built, and no
drawing is taken. The import-and-network half of the invariant for every one of those paths is
what their own guarded children measure.

The **version-drift suite** (`tests/version_drift/`, cards GOV-05/GOV-06/GOV-07) hands the extractor one
live fixture per VERSION-COMPAT §3 row — builders, one bare LCEL chain, and one **compiled** graph
carrying an `InMemorySaver` and both interrupt gates (row 12: the P-13 carriers exist only at the
compiled level) — and additionally performs the substrate reads the §3 rows themselves name:
`get_graph(xray=True)` on the drawable fixture, `get_graph()` twice on the LCEL chain, the two
jsonschema getters, `compile()` in fixtures and tests, and one deprecated-constructor probe under
a recording warnings filter. It carries the ordinary in-process guard form: every node body,
router, reducer and inline lambda records itself in `tests.version_drift.workflows.TRIPPED` and
raises a `BaseException` subclass; the package `conftest.py` reads that ledger after **every**
test; and `test_the_drift_fixtures_are_armed` fires every body — walking `builder.nodes[…]` and
`.branches`, the LCEL sequence steps and parallel branches, and the two line-gated 1.2 graphs
where the substrate builds them, with the line-gated bodies (one of them `async`, driven to its
immediate raise by a single `send(None)`) additionally fired directly on every cell — so the
arming is measured, not described. The golden tool (`tools/drift_goldens.py`) checks the same
ledger around every take. It adds **no extraction path** — `gebra.extract()` and attribute reads
only, so §1's machine check owes it nothing — and every path it reaches carries its own guarded
child above: the compiled path (§1; its checkpointer drawing route is §2 route 2, armed by
`ArmedSaver`), the LCEL path (§1), and the builder path. The suite-side drawing and rendering
calls are §3-row-named surface reads over fully armed fixtures under the per-test ledger, not new
routes: a substrate release whose drawing or schema rendering started invoking bodies trips the
sentinels and fails the run loudly. GOV-07's report seam adds no execution surface: the package
conftest's terminal-summary hook additionally writes the collected signal lines to a text file
when CI asks (`GEBRA_DRIFT_REPORT_FILE`), and the issue automation (`tools/drift_issues.py`) is
a stdlib CLI that CI runs after the suite — its tests (`tests/test_drift_issues.py`,
`tests/test_drift_issue_wiring.py`) drive every API flow through in-process fake transports and
hold the one real transport to its loud no-token refusal, so nothing in the suite or its tests
opens a network connection.

One **fixture** carries a guarded child of its own, listed here because a reviewer looking for it
would look at this index: the shared travel-booking agent
(`tests/sample_workflows/travel_booking.py`, card TE-05) is guarded by
`tests/testing/test_travel_booking.py`, whose child runs the whole extract → verify path over the
agent at both the builder and the compiled level with name resolution, connection opening, socket
construction and `StateGraph.compile` armed. It adds **no extraction path** — every path it
reaches has its own row in §1 above — so §1's machine check owes it nothing; the arming is a guard
over the substrate six later cards build on, not a replacement for those rows.

The **CI-gate action suite** (`tests/action/`, card TE-13) drives the composite action's driver
(`.github/actions/gebra-gate/gate.py`) — the step that wraps one pytest invocation as a CI gate.
The driver is standard library only, held to that by an AST sweep over its imports
(`test_the_driver_imports_stdlib_only`), so importing it reaches neither gebra nor the substrate,
and its only subprocess is the pytest child it exists to run — the suite's end-to-end tests point
that child at files they wrote themselves in tmp directories. Every child but one collects plain
assert-style files that mark nothing and build nothing. The one child that exercises the plugin
gate proper (`test_the_plugin_gate_runs_through_the_driver_on_the_live_agent`) marks the shared
sentinel-guarded travel-booking agent — the same target the DoD suite marks, with the same arming:
its node bodies record and raise `BaseException`-grade sentinels, so a child in which anything was
invoked exits non-zero and the test goes red; the depth guard over that agent remains
`tests/testing/test_travel_booking.py`'s child, above. The suite adds **no extraction path** — the
one extraction it reaches is the plugin's own `gebra.extract()` call over the armed agent, and
every path that call reaches carries its own guarded child in §1 — so §1's machine check owes it
nothing, and nothing in the driver or its tests opens a network connection.

The **coverage gate** (`tools/coverage_gate.py`, card TE-12) adds no execution surface of its own
— it reads a coverage.py JSON report and the gated `.py` files as text, holds no write-mode file
handle and spawns no process, and is standard library only under the same AST sweep the action's
driver carries (`test_the_gate_imports_stdlib_only`). It is recorded here for a second reason: the
card changed the command **every tripwire in this repository now runs under**, from `pytest -q
--cov …` to `coverage run -m pytest -q` in CI's `test-locked` job. That change is measurement-only
and was checked leg by leg at pre-review: plugin discovery is unchanged (the same `pytest11`
loading, only with the tracer already armed); guarded *child* processes stay unmeasured under both
modes, because neither `pytest-cov` nor `coverage run` sets `COVERAGE_PROCESS_START` and
`[tool.coverage.run]` enables no subprocess patching, so every sentinel-armed child in §§1–4 runs
exactly as before; and the one new inherited variable, `COVERAGE_RUN`, is read nowhere in the
repository. No tripwire, sentinel, or hermeticity child was weakened, skipped, or re-scoped by it.

The **freeze-time pin lock and the golden-lifecycle guard** (`tools/matrix_constraints.py` +
`tools/matrix-constraints.txt`, `tools/golden_guard.py`; card GOV-08) add no execution surface of
their own: the constraints tool reads two TOML files and writes one text file; the golden guard
matches text and — only in its CI range mode — shells `git` plumbing (`rev-list`, `diff-tree`,
`log`). Its test suite replaces that boundary wholesale (a behavioural `FakeGit` that also pins
the load-bearing `diff-tree` flags), and one armed test runs the judgement half with
`subprocess.run` disabled outright, so plain `pytest -q` spawns nothing through either tool.
Neither is an extraction path — nothing under `src/gebra/extraction/` references them, so §1's
machine check owes them no row; they are recorded here for the coverage-gate reason: GOV-08
changed the resolution every matrix cell's interpreter installs (the dev toolchain now resolves
under `pip install -c` at the `uv.lock` versions). That change is environment-pinning only,
checked leg by leg at pre-review: the divergent substrate family is excluded from constraint by
construction and by test, so each cell's sentinel suites see the same substrate bytes as before;
the two constrained family members (pydantic, langchain-protocol) are held to exactly the version
every cell extra already pins; and the `--pre` cell's substrate resolve stays unconstrained. No
tripwire, sentinel, or hermeticity child was weakened, skipped, or re-scoped by it.

The **CI-gating guide's example suite** (`examples/ci_gate/`, its workflow
`.github/workflows/gebra-gate-example.yml`, and `tests/docs/test_ci_gating_guide.py`; card
DOC-13) adds **no extraction path**: the only extraction it reaches is the plugin's own
`gebra.extract()` call, whose every path has a row in §1. What it adds is three more *consumers*
of the plugin gate, and each inherits the arming the target already carries. Both marked modules
return the shared sentinel-guarded travel-booking agent at the **builder** level —
`test_agent.py` the v1 builder, `test_unprotected_retry.py` the SD-09 defect-2 variant, whose
bodies record into the same family ledger (the defects module re-exports that list object rather
than keeping a second one) — and the depth guard over that agent remains
`tests/testing/test_travel_booking.py`'s child. The suite is outside `testpaths`
(`pyproject.toml` names `tests` alone, with no `addopts`) and is reached only by explicit path:
by the workflow's three gate steps, through the TE-13 driver above, and by this module's two
pytest children (`--collect-only`, and one `-q` run whose exit 1 and rendered finding are what
the page quotes).

Where each consumer's arming actually bites is worth stating leg by leg rather than in one
sentence, because the legs are not equally strong. Rungs 2 and 3 assert `outcome: pass`, and
`tests/docs/test_ci_gating_guide.py` pins the *rendered condition id* of the defect module's
finding — a fired sentinel breaks extraction and therefore breaks both. Rung 1 is the weak leg:
its asserted verdict is `exit 1` / `outcome: failures`, which is also what a sentinel-blown
session produces, so that step alone cannot tell the seeded P-06 finding from an invocation.
`examples/conftest.py` closes most of that gap — an autouse fixture asserting
`travel_booking.TRIPPED == []` before and after every example test, the TE-05 idiom, placed one
level above `ci_gate/` because those files are reproduced byte-equal on the published page. It
is placed there rather than left implicit precisely because "nothing was recorded" must not read
the same as "nothing ran"; the residue that remains — a ledger-fixture failure is also `exit 1` —
is recorded here rather than engineered away.

The guide's own eight examples run under the DOC-01 harness guard like every other page's, and
the trailer's ledger sweep covers both fixtures they import by name (`travel_booking`,
`travel_booking_defects`), each with a fired control in `tests/docs/test_doc_examples.py`;
`nothing-was-executed` additionally prints that ledger into a pinned output block, so a fired
body fails the example on stdout as well as on `WA07-LEDGER`. None of the eight registers a node
it defined or writes a module, so neither `SELF_DEFINED_MARKERS` nor `WRITES_A_MODULE` owes
anything. One of them writes a `.gebra/` store — into the child's temporary working directory,
never the repository — through `gebra.snapshot`, which extracts and never runs. This card also
extends `GUARD_PROLOGUE` with `import gebra.pytest_plugin`: the eight examples are the first to
import a public gebra module the prologue did not preload, and preloading it is what keeps a
future module-level substrate import in that module from landing a `Runnable` subclass *after*
the arming sweep. Nothing in the example suite, in either gated run, or in this module opens a
network connection; the workflow's checkout, interpreter setup and install steps are ordinary CI
provisioning, outside that claim exactly as the TE-13 paragraph above scopes its own.

## 5. Boundary of the provenance gate (stated, not overstated — WA-06)

The `get_graph()` gate admits an object as stock-substrate by its `__module__` top-level package
(`compiled.py::_from_substrate`). This is a deliberate, load-bearing boundary, not an oversight:
LangGraph's own write mapper for a `StateGraph`-compiled node is a **closure**
(`CompiledStateGraph.attach_node.<locals>._get_updates`) with no `sys.modules`-resolvable
identity, so a stricter identity check would decline the cross-check on *every* ordinary compiled
graph. The gate therefore trusts `__module__`.

The consequence, stated plainly: an object that **forges** `__module__ = "langgraph…"` on an
otherwise user-authored channel is admitted, and its methods would run in the drawing. This is
outside the never-invokes threat model rather than a hole in it. `gebra.extract()` runs in the
author's own process over the author's own workflow; it is not a sandbox, and there is no
privilege boundary an author crosses by arranging to run their own code during their own
extraction (they could call it directly). The invariant the tripwires hold is the one that
matters in practice: extraction of an **honest** workflow — including one with honestly-custom
channels, checkpointers, or mappers, which are correctly declined by provenance — runs no node,
router, tool, LLM, or network call, and no user callable a drawing would otherwise reach. Any
change to what the gate *verifies* is an extraction-semantics change for its own card and review,
never a quiet edit here.
