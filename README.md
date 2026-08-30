# gebra — verify and version LangGraph agent workflows

## What it is

`gebra.extract()` introspects an existing LangGraph `StateGraph`,
`CompiledStateGraph`, or LCEL `Runnable` — without ever invoking user code —
and emits the frozen Gebra IR (`ir_version` 1.0, or 1.1 for a workflow whose
router targets are decided at runtime). Five property validators
(P-01 `graph-well-formed`, P-02 `termination-witness`, P-04
`dataflow-completeness`, P-06 `effect-safety`, P-08 `determinism-replay`)
verify that IR and return structured witnesses or failures, and a pytest
plugin makes verification run on every commit. A snapshot store and structural
diff (V.S.F.E versioning plus the `graph_version` content hash) record and
classify how workflow definitions evolve, behind a
`gebra verify | snapshot | diff | display | history` CLI. Gebra verifies
definitions; LangGraph runs them — nothing in this repository executes a
workflow.

## Status

Early development (`0.0.1.dev0`). The package skeleton, CI baseline, the
acceptance fixture corpus (`tests/fixtures/properties/`, 71 fixtures), the
IR 1.0 models with their node-identity utilities, the canonical serialization +
`graph_version` digest pipeline, and the YAML/JSON loaders (`gebra.ir`), and the
result-envelope models the validators report in together with the frozen
condition-ID and property registries that drive dispatch and emission
(`gebra.verify`), the shared graph pre-analysis the topology-facing validators
build on, the P-02 counter-guard recognizer that reads declared router
conditions for a bounded loop counter, and all five wedge
validators — P-08 `determinism-replay`, P-01 `graph-well-formed`, P-04
`dataflow-completeness`, P-06 `effect-safety` and P-02 `termination-witness`,
each checked against its corpus
fixtures — are in place, together with the run-level aggregation
`gebra.verify.verify(ir)` that runs them as one gate: all thirteen catalog
properties in catalog order (the eight outside the Phase-0 wedge answer with
structured not-implemented markers, never silent passes), the exit codes 0/1/2
of the severity ladder, strict mode in both its bare and per-property forms —
which changes the gate and never a record — and the FATAL-suppresses-the-snapshot
signal. The `gebra` command now carries its first verb: `gebra verify` runs that
same gate from the shell — over a serialized IR document, a stored snapshot
version, or an import path like `gebra verify travel_booking:graph`, where
`--call` is the one explicit way to have the CLI call a zero-argument factory you
name — and returns the report's own exit code, rendered as terminal output, JSON,
or SARIF (`--format`). The other four verbs are still under development. The
extraction entry point `gebra.extract()` is in as a library call too
(`gebra.extraction`) — object-family dispatch, the typed `ExtractionError`, and the
provenance envelope with its structured warning taxonomy, all of it behind a
tripwire that fails if anything handed to it is invoked or compiled.
All three per-family paths are in place. An uncompiled `StateGraph` extracts to
IR — nodes, edges, routers with their declared `path_map`, entry/finish wiring,
the per-node retry policy the builder declares, the state schema, and the
resolved node contracts — read from the builder alone, with `compile()` never
called.
Router edges carry a kind, decided by what the router *declares* and never by
what its body does. A routing callable annotated `-> list[Send]` (or `Send`,
`Sequence[Send]`, or a union or `Command` form admitting one) makes its edges
`kind: send` — one per declared target, a fan-out template about which gebra
says nothing at all as to how many instances run. Every other declaration is
`kind: conditional`: a `Literal[...]` hint, a plain `str`, the
`Command[Literal[...]]` idiom, or no annotation. The default direction is the
conservative one, so a hint gebra cannot read leaves the edge conditional
rather than upgrading it, and the reason is on the envelope. And a router that
declares no targets at all — the map-reduce shape where the `Send`s are built
inside the callable — now extracts instead of being refused: it becomes
`kind: dynamic`, an edge that records the router and its guard and claims
nothing about where it goes, with a warning saying the targets are decided at
runtime. That kind is what makes such a document `ir_version` 1.1; a workflow
without one is still stamped 1.0, and no document that already existed changed
a byte. Declaring targets is still worth doing, and this is why: only a
declared target set can be checked. **`gebra verify` does not read a 1.1
document yet** — it stops with "no verdict was reached" rather than reporting
one, because a `dynamic` edge is absent from the graph the topology properties
are computed over, and answering under the 1.0 rules would call nodes
unreachable that the router reaches. The validator semantics are their own card.
A router annotated with a `Literal[...]` codomain *wider* than its declared
`path_map` has that codomain recorded on the envelope rather than merged into
the map, since the IR has no field for it — reading a declared return type is
also the one place extraction evaluates anything, and it does so only for
routing declarations, only where the annotation is a string, and never in a way
that reaches the router's body.
The state schema comes across as the IR's `state` block: one entry per key, with
the declared type, the `Annotated[T, reducer]` merge function where there is one,
and the graph-input/defaulted keys flagged `optional`. `TypedDict`, pydantic and
dataclass schemas are all read, and no type hint is resolved on the way — the
annotations are already on the builder by the time `extract()` sees it. Which
keys are flagged `optional` follows what the graph declares: with no
`input_schema=` every key is a graph input, so every key is flagged; declaring
`StateGraph(State, input_schema=Input)` is what tells gebra which keys arrive
from outside, and dataflow analysis is only as sharp as that declaration.
A key whose type or reducer has no spelling gebra will invent keeps its place in
the schema and carries a warning saying so, rather than disappearing from it.
All three of the annotation surface's contract sources are in place. The
`@gebra.contract` decorator family (`gebra.annotations`) attaches a declared node
contract and returns the decorated function unchanged — no wrapper, no
invocation — over a closed set of nine slots, with the contradictions a single
decorator stack can contain raised as `GebraContractError` when the module is
imported. The `gebra.toml` sidecar carries the same nine slots for nodes whose
source cannot be decorated: an explicit `gebra.extract(workflow, sidecar=...)`
wins, otherwise the nearest `gebra.toml` from the current directory up to the
repository root, exactly one file and never merged; entries are keyed by node id
in its escaped form; and everything a sidecar can get wrong degrades to a
warning, so a malformed file never breaks an extraction. The absolute path of
the file used is recorded on the envelope. And where nothing was declared at
all, shallow inference reads a node's own source — a closed list of five
patterns over `input` and `output` only, never evaluating an annotation and
never following an import — falling back to the conservative `effect: ["write"]`
/ `pure` defaults, with every inferred or defaulted slot carrying a structured
warning that says which pattern licensed it or why none did. Inference never
yields `idempotent`, `deterministic`, `variant` or `compensation`.
The precedence chain that resolves the sources against each other is in place, so
a node's contract now reaches the IR. Resolution is per slot and strict —
decorator, then a LangChain tool's own `args_schema`, then the sidecar, then
inference — and a lower source fills gaps rather than overriding: a differing
value is kept out and reported as an `annotation-conflict`, while two sources
that canonicalize to the same bytes are not a disagreement at all. Every node's
*resolved* contract is then checked against the same rules a single decorator
stack is held to, warning-grade, dropping the lower-precedence half rather than
failing the extraction. Contracts are located through `functools.wraps` chains
and the substrate's own wrappers, so extracting a workflow before and after
`.compile()` yields identical contracts.
The compiled path is in place, so a `CompiledStateGraph` — or any other Pregel
object — extracts as well. The builder backreference defines the graph, so
topology, state and contracts are exactly what the uncompiled builder gives; what
compiling adds is the `runtime` block, with the interrupt gates each side of a
node (a `"*"` gate expanded to the full node list) and whether a checkpointer is
attached, recorded either way because at that level it is a known fact. At builder
level the slot stays absent rather than guessed, so a compiled workflow and the
same workflow before compiling carry different `graph_version` digests. One other
difference is LangGraph's own: `compile()` writes `set_node_defaults` into the
builder's node specs, so a graph-level `retry_policy` reaches the IR from the moment
you compile, at either level — the envelope records which nodes inherited it. gebra also
cross-checks the builder's topology against the compiled graph's own drawing and,
where they differ, keeps the builder's reading and reports a
`builder-compiled-divergence` warning carrying both. Producing that drawing is the
one call gebra makes into the substrate, and it is gated: the walk reaches custom
channels, checkpointers, cache key functions and write mappers, so gebra takes a
drawing only from a real LangGraph `Pregel` whose surfaces all come from LangGraph
itself, and otherwise skips the cross-check with the reason recorded on the
envelope. Facts the IR has no field for ride in provenance instead of being dropped:
which nodes carry a discovered subgraph, which node-spec members `set_node_defaults`
filled in, and the error-handler map. A discovered subgraph comes across as the node
that holds it — children are not expanded, and that is IR 1.0's complete form rather
than a partial one, so a workflow with subgraphs stays warning-free; expanding them
is the next version's first feature, and a subgraph compiled with
`checkpointer=False` is invisible to LangGraph's own discovery, so the recorded list
is a lower bound. A Pregel object with no builder extracts from the compiled
level alone with one `compiled-only-extraction` warning, its state block absent
rather than guessed — and where the drawing is the only surface and the gate refuses
it, so does extraction, `RemoteGraph`'s HTTP-backed getter included.
The LCEL path completes the three object families: a bare `Runnable` extracts as a
fragment, keyed by structural position rather than by name — `%seq[0]`,
`%map[docs]`, `%lambda[1]`, over the seven composition kinds IR 1.0 fixes — with a
nested chain hanging off its parent's id. LangChain's own drawing ids are fresh
UUIDs per call and are never used: gebra reads the composition off the objects and
never draws. Re-extracting an unchanged chain gives byte-identical ids and the same
`graph_version`, across processes as well as within one, which needs gebra to derive
a lambda's captured-runnable order from the function's compiled form rather than
take LangChain's, whose order can differ between runs. A stitched lambda body is opaque,
so an unannotated one takes the conservative `effect: ["write"]` default and reports
it with an `opaque-lambda` warning naming the id you can attach a contract to.
Where gebra will not read a composition it reports that rather than guessing — a
subclass of a composition type, a lambda whose captured runnables sit behind one of your own
objects' attributes, a self-referential composition, one nested past 32 levels.
A `Runnable` that is none of the seven kinds and composes nothing has no id under
this version's vocabulary and is refused rather than given an invented one; inside a
chain the same object extracts normally, since its position names it. A chain bound
as a `StateGraph` node is still extracted as that one node.
A node bound to a prompt template or to a chat model also carries a `prompt_digest`
or a `config_digest`, so **editing prompt text moves `graph_version` the way editing
an edge does** — while the prompt itself never enters the IR, which is the point:
what is recorded is a fingerprint, so an extracted document stays safe to commit and
publish. The fingerprint is over a projection gebra fixes, not over whatever a
library happens to serialize: a string template's exact UTF-8 bytes, untrimmed and
unnormalized; a chat template's messages in the order you wrote them; a model's class
identity, declared fields and `.bind()` kwargs, with secret-typed fields left out.
Nothing time-, address- or environment-dependent reaches those bytes, so two runs on
two machines agree — a value gebra cannot represent in JSON is recorded by its class
name rather than by `repr()`, and a `set`-valued parameter is ordered by content
rather than by Python's per-process hash order. Two insensitivities are deliberate
and worth knowing: `template_format` and `input_variables` are not digested, and
neither is anything passed through `with_config`. One sensitivity is worth knowing
too: LangChain stamps its own version into a chat model's metadata at construction,
and that is part of what gets digested, so upgrading `langchain-core` moves
`config_digest`. A model behind `.bind(...)` is read through the wrapper — including
the wrapper `model.bind(tools=[...])` returns — so a tool-bound model carries a
`config_digest` and editing the tool schemas you bound moves `graph_version`; a tool
passed as a `BaseTool` object rather than as a schema dict is recorded by its class
name, so swapping one such tool for another does not move it. Where a digest cannot
be computed — a prompt-template class outside the recognised set, or a model behind a
wrapper class gebra does not recognise and so keeps opaque — the slot is absent and a
warning names what it was.
The `.gebra/` snapshot store now writes and reads: `gebra.store` persists an IR
under the `version` / `extracted_from` / `graph_version` envelope, one committable
YAML file per version plus an append-only index, with atomic writes and byte-stable
output. Version assignment and the structural diff are in as libraries too:
`gebra.versioning` parses, compares and bumps V.S.F.E labels, and `gebra.diff`
reports what moved between two snapshots or IRs — topology over networkx, node
contracts, the state schema — and derives the bump class from those deltas. Nothing
in the diff classifies a change as safe or breaking: P-12 `evolution-safety` is out
of Phase-0 scope, and every diff carries the structured marker that says so.
`gebra.lineage` lists a store's version history — every version, its digest, when it
landed, and which V.S.F.E counters moved between each neighbouring pair — reading the
index and no snapshot file, and projects it to byte-stable JSON. Those pieces are now
joined up: `gebra.snapshot.snapshot(workflow, store=store)` extracts a live workflow,
wraps the IR in the envelope, assigns the V.S.F.E label the diff engine's bump class
lands on, and writes it — and re-snapshotting a definition that has not changed writes
nothing and reports the version the store already holds. `gebra.audit` closes the loop:
`export_store(store)` writes one JSON property report per stored version to
`.gebra/reports/<version>.report.json` — the same run report a verification produces, in
its snapshot profile, with no second schema and no timestamp, so re-exporting an unchanged
version rewrites identical bytes — and `freshness(ir, store=store)` answers whether the
store's current snapshot is still the definition in front of you. Of the five CLI
verbs, `verify` exists today; `gebra snapshot`, `diff`, `display` and `history` are
still under active development, and the library calls above are their surface until then.
The **pytest plugin** is in, and pytest loads it itself: installing the package registers a
`pytest11` entry point, so nothing needs adding to a `conftest.py` to switch it on. Put
`@pytest.mark.gebra` on a function that returns your `StateGraph` — or your compiled graph,
your LCEL runnable, or an IR you already have — and pytest collects one item per checked
property, named for the target and the property
(`test_gebra[travel_agent-termination-witness]`), each one extracting the graph and running
`verify()` over it. If you would rather write your own assertions, define a `gebra_workflow`
fixture in your `conftest.py` and take `gebra_graph` (the extracted IR) or `gebra_verification`
(the whole run) as a fixture instead. Items are generated for the properties this build can
answer — the wedge five; the eight Phase-0 defers get no item rather than a green one, and
`gebra_verification` is where their not-implemented markers are visible. What fails an item is
severity, not verdict: a FATAL or ERROR finding *owned by that property* fails its item and
a WARNING-grade one is reported on it as advisory — so a P-08 finding, which is WARNING-grade,
is shown and does not turn CI red — unless you ask for it. `--gebra-strict` promotes
WARNING-grade records to gate failures, either bare (everything in the run) or
`--gebra-strict=determinism-replay` for one property at a time; it also reaches the structured
witness notes a passing report can carry, which is what turns P-02's justified-recursion-limit
note into a red item. A promoted record is unchanged in the report — still `severity: warning`,
still its own claim class — because strictness is a CI policy and not a re-grading.
`--gebra-select` and `--gebra-skip` choose which properties get an item; neither narrows the
run, so a skipped property is un-itemized and still carried in `gebra_verification`. The run
closes with a `gebra` section: one block per target, every property with its claim class and
either a witness summary or its findings, the eight Phase-0 defers shown as not checked, the
extraction warnings under their own taxonomy codes, and the exit code with the policy that
produced it. That section is assembled in the process that ran the items, so a plugin that
distributes them to workers — `pytest-xdist` — is not expected to show it on the controller;
that combination is untested here, and the per-item detail travels with the report either way.
gebra runs nothing on that path: it calls the function you marked — your code,
called the way pytest calls any test — and hands what it returns to `gebra.extract()`, which
imports and inspects only. An explicit `gebra.toml` is declarable, with
`@pytest.mark.gebra(sidecar=...)` or a `gebra_sidecar` fixture; without one, discovery walks
up from wherever pytest was started, and sidecar annotations change verdicts as well as the
digest. Which level you hand it is your declaration too: a builder and the same graph compiled
are different documents with different `graph_version`s.
A second marker, `@pytest.mark.gebra_freshness`, is the snapshot-freshness gate: mark a
function that returns your workflow and the item fails when what it returns is not the
snapshot your `.gebra/` store currently holds — the message names the store, both digests,
which of S/F/E moved, and the call that records it. It is a check on the store rather than a
fourteenth property: it runs no validator, it writes nothing, and it says the content moved,
never whether the change is safe.
The plugin is also packaged as a reusable GitHub Action, `.github/actions/gebra-gate`,
that runs it as a CI gate: one pytest run built from typed inputs, a
`report-only` → `gate` → `strict` rollout switch, the closing `gebra` report appended
to the step summary, and the exit code translated into the step verdict — with the
asymmetry that matters for a gate: report-only forgives test failures and nothing
else, so an interrupted, erroring, or empty run is red under every mode. This
repository's own DoD scenario job issues its pytest invocation through the action on
every push; the interface and the recommended rollout are documented in
[docs/ci/github-action.md](docs/ci/github-action.md).
The `verify()` aggregation over the five validators is in place, and with it
strict mode, which is a gate policy: `gebra.verify.verify(ir, policy)` records what a
strict run promoted and leaves every report exactly as its validator wrote it. The
`gebra.verify` result-envelope and registry surface is now frozen
([docs/governance/VALIDATOR-API-FREEZE.md](docs/governance/VALIDATOR-API-FREEZE.md)),
and so is the `gebra.ir` model/serialization surface, covering the ir 1.1 `dynamic`
edge kind
([docs/governance/IR-MODELS-FREEZE.md](docs/governance/IR-MODELS-FREEZE.md)) — further
shape changes to either route through a vault decision record plus an `ir_version`/API
bump rather than a local edit.
The hand-written fixture corpus is now held against the extractor and not only against the
validators. Sixteen of the seventy-one fixtures have a matching mini LangGraph builder script in this
repository, and the suite builds each one live, extracts it, and requires the canonical bytes
and the `graph_version` to match that fixture's own `ir:` block — except for three pairs held
instead to a recorded difference, below — so a fixture and the extractor cannot drift apart
without a test going red. The designated set is the fixtures whose IR extraction can actually
emit: a conditional edge's `condition` carries the *declared branch name*, and the corpus writes
guard expressions and English sentences there, so no conditional fixture has a pair —
`termination-witness` and `retry-coherence` are not covered. The one difference the set found is
recorded rather than smoothed over: the corpus spells a state reducer `operator.add` and
extraction spells it `_operator.add`, which is the module Python itself reports for that
function. No verdict in the corpus turns on it — no validator reads a reducer's name — but the
two digests differ, and so does a `gebra.diff` across the two spellings.
User documentation and tutorials will land in `docs/` as
the corresponding features ship.

## Quickstart

The project is built with [hatchling](https://hatch.pypa.io/latest/) and managed
with [uv](https://docs.astral.sh/uv/); `uv.lock` pins the development
environment.

```bash
git clone https://github.com/Gebra-Tech/gebra.git
cd gebra
uv sync --extra dev     # creates .venv from the committed lockfile
uv run pytest
```

Without uv, the standard pip path works too:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Contact & questions

Open a [GitHub issue](https://github.com/Gebra-Tech/gebra/issues) or email
gebra.dev@gmail.com.

## License

Apache-2.0 (see [LICENSE](LICENSE) and [NOTICE](NOTICE)). The `gebra` package
is open core: this library is and stays Apache-2.0; any hosted commercial
products are separate and out of this repository's scope. All contributions
require a signed CLA with Gebra Tech, Inc. — see
[CONTRIBUTING.md](CONTRIBUTING.md).
