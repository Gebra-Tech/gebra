# The IR, node identity and graph_version

!!! note "Spec-derived page"

    The vocabulary on this page — the field set, the node-identity grammar, the
    canonicalization pipeline and the hash scope — is transcribed from **IR-SPEC** (frozen
    2026-07-18) and the ruling that fixed the digest, **DEC-10**, and every statement names
    the section it came from. Those documents are internal contract documents and are not
    published with this site; the section numbers are here so that a claim can be *checked*
    against them rather than taken on trust.

    The three examples are not spec-derived. They are executed in CI and print what this
    release actually does — see [Executable examples](../contributing/executable-examples.md).

## What the IR is

The Gebra IR is a **document**. `gebra.extract()` imports and inspects a `StateGraph`
builder, a compiled graph or an LCEL `Runnable` — it never invokes one: no node function,
router, tool or model is called, and no connection is opened — and writes out a value with
these fields (§2.1):

| Field | Required | What it holds |
|---|---|---|
| `ir_version` | yes | The format version — `"1.0"`, or `"1.1"` for a document that needs the 1.1 edge kind. |
| `entry` | yes | The node or nodes wired from the implicit `START` sentinel. |
| `finish` | yes | The node or nodes wired to the implicit `END` sentinel. |
| `state` | no | The state schema: each key's declared type, its reducer if it has one, and whether it is optional. |
| `nodes` | yes | Each node's id, and the contract its `annotations` declare — reads, writes, effects, idempotence, determinism. |
| `edges` | yes | The edges, each carrying its kind: `normal`, `conditional`, `send`, and `dynamic` at 1.1. |
| `runtime` | no | Graph-level configuration: `recursion_limit`, `interrupts`, `checkpointer`. |

Two shapes surprise people, so they are worth naming before anything else.

`START` and `END` are **not rows in `nodes[]`**. They are real vertices of the graph the
validators analyse, but the document encodes their incidences positionally: an id in `entry`
means an edge from `START`, an id in `finish` means an edge to `END`, and a `path_map` label
whose value is the literal `"END"` is a labelled edge to `END` (§4.2). A `to: "END"` on a
`normal` or `send` edge is *not* one of those forms — it is looked up like any other target:
it names a node called `END` if you declared one, and is an unresolved reference if you did
not (§4.2, as corrected by DEC-27).

And a `conditional` edge is **one edge per label**. Before any graph algorithm runs — cycle
detection, reachability, dataflow — each `path_map` entry is expanded into its own directed
edge carrying that label (§2.4). The document stores the branch; the analysis sees the
branches.

Everything above is the **core IR**. When `gebra snapshot` records a document it wraps it in
an **envelope** — a V.S.F.E `version` label, provenance in `extracted_from`, and the
`graph_version` digest — which is metadata *about* the document and no part of it (§4.1).
That split is what the rest of this page turns on.

## Why it is hermetic

The IR is deliberately smaller than the program it came from. Three things it does not carry
(§7):

- **Guard bodies.** A router's `condition` is a *declared string*, recognised by shape where
  the termination grammar recognises it and never evaluated by gebra (§2.4). From an
  extraction it is the declared branch name; an authored IR may carry a richer declared
  expression in the same slot.
- **Fan-out counts.** A `send` edge is a branch *template*. The number of branches a run
  actually dispatches is a run-time quantity, and the IR is silent on it rather than guessing
  (§2.4).
- **Node function bodies.** A node reduces to its contract plus, where the extractor can
  compute them, the `prompt_digest` and `config_digest` fingerprints of its prompt template
  and model configuration. Bodies never enter the IR; only fingerprints do — the layered
  hashing pattern (§3.6; DEC-10).

What that buys is the whole point of the format. The document is self-contained: plain YAML
or JSON, no live object references, no imports to resolve. It can be committed beside the
code, handed to a build machine, diffed against last month's copy, and read again years from
now. Verifying one needs neither the source program nor a runtime — importing gebra's
validator lane pulls in no LangGraph or LangChain package at all, which a test in a fresh
interpreter asserts (`tests/verify/test_base.py`).

What it costs is worth saying just as plainly. A contract in `annotations` is **declared**,
and gebra checks that a declaration is coherent with the graph rather than true of the
function body — the trust model behind the DEFENSIBLE-A claim class
([What gebra checks](what-gebra-checks.md)). Where a node declared nothing, extraction
applies the conservative default and records a `contract-defaulted` warning, so a defaulted
contract never reads as a declared one.

## Node identity

Every node has an id, and the id is a **path from the graph root** — one segment per nesting
level, `/` between them (§5.1). The root graph contributes no segment; a top-level node's id
is just its name.

One scoping note before the grammar, because the grammar is wider than what this release
emits: `ir_version` 1.0 and 1.1 carry a discovered subgraph as its **parent node only** — no
child nodes and no child edges — so the multi-segment ids extraction produces today come from
LCEL fragment nesting rather than from nested `StateGraph`s. Child-topology expansion is a
recorded limitation of this build, not something being described ahead of time; it is listed
as such in `docs/governance/EXTRACTOR-API-FREEZE.md`.

Two rules make an id safe to split and safe to compare. A source name containing the delimiter
is percent-escaped — `/` becomes `%2F` and `%` becomes `%25`, and nothing else is escaped —
so `node_id.split("/")` is always right with no context to consult. And an unnamed LCEL
fragment, which has no source name to use, gets a **synthetic segment** instead:
`%seq[0]`, `%map[docs]`, `%branch[…]` and four more kinds, a closed vocabulary in 1.0 (§5.2).
Because a literal `%` in a source name always escapes to `%25`, the two namespaces are
disjoint by construction (§5.1) — that is the
`summarize/%map[docs] -> summarize/%25map[docs]` line in the transcript below.

Two segments are reserved and never emitted: `__start__` and `__end__`, mirroring LangGraph's
own sentinels, so the per-level pseudo-nodes an analysis needs can never collide with a name
you chose (§5.1). And ids never contain uuids: drawing ids, task ids and checkpoint
namespaces are construction- or run-dependent, and the grammar exists precisely to refuse
inheriting them (§5.2).

**One id names at most one node.** A document declaring the same `id` twice in `nodes[]` is
refused when it loads, with an error naming the repeated id and both of its positions — §2.1
makes uniqueness a MUST and words it at the loader. Extraction cannot produce such a document
(a LangGraph node name is a dict key), so this is a rule about hand-written IR. It matters
because everything downstream keys on the id: `graph_version` orders `nodes[]` by it and
`gebra diff` anchors every change on it, so two nodes under one id would mean one workflow
with two digests and a diff that reports less than moved.

<!-- gebra:example id=node-identity -->
```python
from gebra.ir import (
    escape_segment,
    join_node_id,
    node_id_from_names,
    openinference_attributes,
    parse_node_id,
    split_node_id,
    synthetic_segment,
)

# One segment per nesting level, from the graph root down; the root contributes none.
print(node_id_from_names(["research", "tools", "web_search"]))

# A source name containing the delimiter is escaped, so splitting never needs context.
escaped = node_id_from_names(["research", "web/search"])
print(escaped, "->", split_node_id(escaped))

# An unnamed LCEL fragment gets a synthetic segment instead of a name. A literal "%" in a
# source name escapes to "%25", so the two namespaces cannot collide.
fragment = join_node_id([escape_segment("summarize"), synthetic_segment("map", "docs")])
print(fragment, "->", node_id_from_names(["summarize", "%map[docs]"]))
for segment in parse_node_id(fragment).segments:
    print(f"  {segment.text:12} {segment.kind.value:10} selector={segment.selector!r}")

# Renaming a node produces a new identity, never a moved one.
print(node_id_from_names(["research", "tools", "search_web"]))

# The IR-SPEC §5.4 OpenInference attributes derived from that node id.
for key, value in openinference_attributes("research/tools/web_search").items():
    print(f"  {key} = {value!r}")
```

<!-- gebra:output id=node-identity -->
```text
research/tools/web_search
research/web%2Fsearch -> ('research', 'web%2Fsearch')
summarize/%map[docs] -> summarize/%25map[docs]
  summarize    user       selector=None
  %map[docs]   synthetic  selector='docs'
research/tools/search_web
  graph.node.id = 'research/tools/web_search'
  graph.node.parent_id = 'research/tools'
  graph.node.name = 'web_search'
```

The line printing `research/tools/search_web` is the rule people most often want softened,
and it is the one that holds hardest: **a rename is a new identity.** So is re-keying a
parallel branch, moving a node across a subgraph boundary, or shifting a sibling's index. An
id is a deterministic function of structure and names — re-extract unchanged source and you
get byte-identical ids (§5.3) — which is exactly why it cannot also track a node *through* a
rename. Following one node across two versions of a workflow is the diff layer's job, never
the id's.

The last three lines are the §5.4 OpenInference mapping — the three attributes a node id
derives, **per definition and not per invocation**, so every execution of that node in a
trace shares them. gebra derives the mapping; emitting spans is not part of this release.

## What a `graph_version` is

A `graph_version` is the **SHA-256 digest of the canonical serialization of the core IR**,
rendered as `"sha256:"` followed by 64 lowercase hex characters — the OCI digest grammar, so
that moving to another hash function later would not break the format (§6.1 steps 6–8).

For most readers three consequences are the whole story:

- the same definition always produces the same digest, on any machine and in any
  implementation that follows §6;
- any change to content the digest covers changes the canonical bytes, and with them the
  version — including a prompt edit, which moves it exactly as a topology edit does (§6.6);
- how the document was *written* — key order, indentation, quoting, the order of things that
  are sets — never moves it, and neither does anything the envelope records about when and
  where it was extracted.

Those three follow from one table. This is the hash scope, ruled by DEC-10 and normative at
§6.4:

| In the digest? | What it covers |
|---|---|
| **INCLUDE** | The entire core IR: `ir_version`; `entry`/`finish`; `state` (keys, types, reducers, optional flags); `runtime` and every sub-slot (`recursion_limit`, `interrupts`, `checkpointer`); every `nodes[]` id and **all** of its annotations, the newer slots included, and `prompt_digest`/`config_digest` — digests, not bodies, which is what layered hashing means here; every `edges[]` entry's `from`/`to`/`kind`/`condition`/`path_map`. |
| **EXCLUDE** | The envelope: the V.S.F.E `version` label (it is *derived from* diffs of the digested content, so including it would be circular), `extracted_from` (provenance — how and when the document was made), and the `graph_version` digest itself, which cannot contain itself. Also `source_snippet` and any `notes`/`description` field: these are not IR fields at all, and a core-IR document carrying one is refused before it can be hashed. Authored array order and absent, null or defaulted optionals are outside it too — those are normalized away before serialization rather than filtered out (§6.2, §6.3). |

One principle runs through both rows: **semantic content in; provenance, presentation and
derived labels out.** And one thing a digest is not: a verdict. It says *which* definition you
are looking at, never whether that definition is any good — that is what
[verification](what-gebra-checks.md) answers, and a report carries the digest of the document
it was computed over.

### The pipeline, step by step

This subsection is contributor depth. If you only need to reason about digests, the table
above is enough; this is what a second implementation would have to reproduce byte for byte
(§6.1):

1. **Parse** the document into the data model. Surface bytes are never hashed — YAML has no
   canonical byte form, so it is an authoring format and nothing more.
2. **Project to the hash scope** — drop every *field* in the EXCLUDE row.
3. **Omit- and representation-normalize** (§6.3). Remove every optional member that is `null`,
   equal to its schema default, or an empty optional array — *absent, null and default are one
   thing*. Then collapse the surface's equivalent spellings: `entry`/`finish` become a scalar
   exactly when the wired set is a singleton, and a `state` value becomes a bare type name
   exactly when it carries no reducer and no optional flag.
4. **Sort the arrays** (§6.2), which JCS itself does not do: `nodes[]` by its escaped id in
   UTF-16 code-unit order, `edges[]` bytewise by each edge object's own canonical
   serialization, and the set-valued string arrays — `effect`, `input`, `output`, `retry_on`,
   the `interrupts` lists, the list forms of `entry`/`finish` — in UTF-16 code-unit order,
   because they are sets and their authored order means nothing. An array *not* on that list
   keeps the order it was authored in; the arrays inside
   an `args_schema` are the case that matters, since order can be semantic in JSON Schema.
5. **Check the scalars**: identifier-role strings in NFC, no NaN or infinity, and every
   integer inside the exact-integer range JSON can carry.
6. **Serialize** with RFC 8785 JCS to UTF-8 — member names sorted as UTF-16 code units, no
   whitespace at all.
7. **Digest** those bytes with SHA-256.
8. **Render** the result as `"sha256:" + lowercase hex`, matching `sha256:[a-f0-9]{64}`.

Verification is step 9 and it is the same pipeline: recompute the digest and string-compare
(§6.1). That single operation is what conformance means for both a document and an extractor
(§1.2) — there is no partial conformance in either, because one differing byte in the
canonical form is a different digest.

## The worked example: golden vector 001

The specification pins one document as **golden vector 001**: an input, its canonical bytes,
and its digest, shipped so that any implementation can be checked against it rather than
against a description of what it should do (§1.3, §6.5). It lives in this repository at
`tests/ir/golden/vector-001.*`, and the example below is that vector — the same document, run
through this release:

<!-- gebra:example id=golden-vector-001 -->
```python
from gebra.ir import WorkflowIR, canonical_bytes, graph_version, load_yaml, verify_graph_version

AUTHORED = """\
ir_version: "1.0"
entry: plan
finish: report
runtime:
  recursion_limit: {value: 10, justification: "redo loop bounded by review budget"}
state:
  task: str
  result: str
nodes:
  - id: plan
    annotations: {pure: true, output: [task]}
  - id: act
    annotations: {input: [task], output: [result], effect: [network]}
  - id: report
    annotations: {input: [result]}
edges:
  - from: plan
    to: act
  - from: act
    kind: conditional
    condition: "done(result)"
    path_map: {done: report, redo: act}
"""

PINNED = "sha256:5db68464c736069f7213902a1f6cb566c70c623de32a754d42d2d8498e4ba69d"

ir = load_yaml(WorkflowIR, AUTHORED)
canonical = canonical_bytes(ir)

print(canonical.decode())
print()
print("canonical bytes:", len(canonical))
print("nodes, as authored:", [node.id for node in ir.nodes])
print("graph_version:", graph_version(ir))
print("recomputes to golden vector 001:", verify_graph_version(ir, PINNED))
```

<!-- gebra:output id=golden-vector-001 -->
```text
{"edges":[{"condition":"done(result)","from":"act","kind":"conditional","path_map":{"done":"report","redo":"act"}},{"from":"plan","to":"act"}],"entry":"plan","finish":"report","ir_version":"1.0","nodes":[{"annotations":{"effect":["network"],"input":["task"],"output":["result"]},"id":"act"},{"annotations":{"output":["task"],"pure":true},"id":"plan"},{"annotations":{"input":["result"]},"id":"report"}],"runtime":{"recursion_limit":{"justification":"redo loop bounded by review budget","value":10}},"state":{"result":"str","task":"str"}}

canonical bytes: 537
nodes, as authored: ['plan', 'act', 'report']
graph_version: sha256:5db68464c736069f7213902a1f6cb566c70c623de32a754d42d2d8498e4ba69d
recomputes to golden vector 001: True
```

A three-node workflow: `plan` hands a task to `act`, and a router either finishes at `report`
or sends the work back round to `act`. That `redo` loop is a cycle, and the declared
`recursion_limit` is the graph-level bound offered as its termination witness — but reading
the *document* is not what this section is for. Read the 537 bytes instead, because every
difference between them and the YAML above is one rule doing one thing:

- **`nodes[]` is sorted by id**, so the canonical order is `act`, `plan`, `report` while the
  model still holds `plan`, `act`, `report` — the order the file was written in. The line
  printing "as authored" is there to make that visible: canonicalization is a pipeline the
  digest runs, not an edit to your document.
- **`edges[]` is sorted by each edge's own canonical bytes**, which is why the conditional
  edge comes first: its bytes begin `{"condition"`, and `c` sorts before the `f` of
  `{"from"`. No composite sort key to get wrong, and no tie to break.
- **Member names are sorted everywhere**, by JCS: `edges`, `entry`, `finish`, `ir_version`,
  `nodes`, `runtime`, `state` at the top level; `annotations` before `id` in a node;
  `justification` before `value` inside `recursion_limit`.
- **`entry` and `finish` stay scalars**, because each wired set here is a singleton. Written
  as `entry: [plan]` they would collapse to the same scalar, and to the same digest.
- **The `state` values stay bare type names** — `"str"`, not `{"type": "str"}` — because
  neither key declares a reducer or an optional flag.
- **The `plan → act` edge carries no `kind`.** It did not in the YAML either, and it does not
  in the canonical form: `normal` is the one non-null default the 1.0 format has, and
  omit-normalization removes it. The conditional edge keeps its `kind`, because it is not the
  default.
- **There is no whitespace and no line break.** The wrapping in the specification's own copy
  of this example is for display; the bytes are one line, and the byte count is part of what
  is pinned.

Changing any of the three files behind that vector is a golden-file event in this
repository's working agreements — it takes a ratified format change and a decision record,
never a quiet edit — because the vector is what makes a digest this implementation computes
checkable against the specification rather than only against itself.

## What moves a `graph_version`, and what does not

The same question from the other side, on a smaller document so that the whole comparison
fits in one transcript:

<!-- gebra:example id=what-moves-a-graph-version -->
```python
from gebra.ir import WorkflowIR, graph_version, load_yaml
from gebra.store import ExtractedFrom, Snapshot

AUTHORED = """\
ir_version: "1.0"
entry: plan
finish: act
state:
  task: str
  result: str
nodes:
  - id: plan
    annotations: {output: [task]}
  - id: act
    annotations: {input: [task], output: [result], effect: [network]}
edges:
  - from: plan
    to: act
"""

# The same content, authored by someone with different habits: another key order, the
# default edge kind written out, the singleton `entry` as a list, `state` in object form.
SAME_CONTENT = """\
edges:
  - {from: plan, to: act, kind: normal}
nodes:
  - id: act
    annotations:
      effect: [network]
      output: [result]
      input: [task]
  - id: plan
    annotations: {output: [task]}
state:
  result: {type: str}
  task: {type: str}
finish: [act]
entry: [plan]
ir_version: "1.0"
"""

base = load_yaml(WorkflowIR, AUTHORED)
baseline = graph_version(base)


def row(label: str, digest: str) -> None:
    print(f"{label:40}{digest[:23]}…  {'same' if digest == baseline else 'moved'}")


row("the document itself", baseline)
row("the same content, authored differently", graph_version(load_yaml(WorkflowIR, SAME_CONTENT)))

# The envelope: one document recorded twice, months and extractor versions apart. The label
# does not move, because the content did not.
august = Snapshot.of(
    base,
    version="1.0.0.0",
    extracted_from=ExtractedFrom(
        source="app/workflow.py:build",
        extractor_version="0.0.2.dev0",
        extracted_at="2026-08-31T09:00:00Z",
    ),
)
november = Snapshot.of(
    base,
    version="1.0.0.0",
    extracted_from=ExtractedFrom(
        source="app/workflow.py:build",
        extractor_version="0.9.2",
        extracted_at="2026-11-14T17:30:00Z",
    ),
)
row(f"recorded in August as {august.version}", august.graph_version)
row("re-recorded in November, unchanged", november.graph_version)

edited = AUTHORED.replace("effect: [network]", "effect: [network, billable]")
row("one more effect tag on act", graph_version(load_yaml(WorkflowIR, edited)))

prompted = AUTHORED.replace(
    "annotations: {input: [task], output: [result], effect: [network]}",
    "annotations:\n"
    "      input: [task]\n"
    "      output: [result]\n"
    "      effect: [network]\n"
    '      prompt_digest: "sha256:' + "0" * 64 + '"',
)
row("a prompt fingerprint on act", graph_version(load_yaml(WorkflowIR, prompted)))
```

<!-- gebra:output id=what-moves-a-graph-version -->
```text
the document itself                     sha256:f4ee58d9d92403cd…  same
the same content, authored differently  sha256:f4ee58d9d92403cd…  same
recorded in August as 1.0.0.0           sha256:f4ee58d9d92403cd…  same
re-recorded in November, unchanged      sha256:f4ee58d9d92403cd…  same
one more effect tag on act              sha256:5cac4f0802f7bef8…  moved
a prompt fingerprint on act             sha256:4096271a28baf4dc…  moved
```

Four readings, in order:

**Authoring habits are invisible.** The second document reorders every level, writes the
default `kind` out, spells a singleton `entry` as a list and expands both `state` values into
objects — and lands on the same digest, because steps 3 and 4 of the pipeline erase exactly
those differences. Two teams who never agreed on a house YAML style still agree on the
version.

**Provenance is invisible.** The two recordings differ in their timestamp and in the extractor
version that made them, and share one `graph_version`. That is the EXCLUDE row acting — and it
is also what makes "unchanged" decidable. `gebra snapshot` compares the digest, finds that the
store already holds this content, writes nothing and answers with the label the store already
had; a digest that moved when you re-recorded the same definition in November would make that
impossible.

**A contract edit moves it.** One extra effect tag — an `act` that is now marked `billable` —
is a change to what the document says, so it is a change to the version. Contracts are in
scope exactly like topology.

**A prompt edit moves it too.** The prompt text itself never enters the IR; its
`prompt_digest` does, and the digest is in scope. This closes a gap that would otherwise be
wide open: without it, two workflows differing only in the wording of a prompt would extract
to identical documents and carry identical versions (§6.6).

## Versioning the format itself

`ir_version` is the version of the **format**, and it moves under its own rules (§8):

- **Additive-optional changes are minor** — a new optional slot, or a new token in a closed
  vocabulary. Neither moves an existing document's digest, but for two different reasons, and
  §8 is careful to keep them apart. A new optional slot cannot, because absent, null and
  default are one thing after normalization — that is §6.3's corollary. A new vocabulary token
  holds on its own terms instead: no document written before it contains the token, and the
  serialization rules of the tokens that already existed are untouched.
- **Breaking changes are major** — renaming, removing or retyping a field, changing
  requiredness or meaning, and, categorically, **any change to the canonicalization rules that
  would alter the canonical bytes or digest of an existing valid document**. That last rule is
  DEC-10's, and it is what makes a `graph_version` comparable over time: `ir_version` sits
  inside the hashed payload, where it firewalls false equality across format versions.

One minor exists. `ir_version` `"1.1"` adds a fourth edge kind, `dynamic`, for a router whose
target set is not statically knowable (§8; DEC-28); a document is stamped `"1.1"` only if it
actually contains such an edge, and `"1.0"` otherwise. In this release a 1.1 document
**extracts but is not verified, snapshotted or diffed** — the pipeline stops there and
reports a tool error rather than a verdict.

Finally, two version-like things that are never the same thing (§8). `ir_version` is the
format. The V.S.F.E `version` in the envelope is *the workflow's* evolution, derived by
diffing one document against another. A `gebra diff` verdict says nothing about `ir_version`,
and an `ir_version` bump says nothing about your workflow.

## Where this page is checked

All three examples are executed in CI, in a child interpreter where compiling a graph,
invoking a runnable, resolving a hostname or opening a connection all raise. The transcripts
above are what those runs printed —
[Executable examples](../contributing/executable-examples.md) explains the harness.

Two further checks hold the prose to its sources rather than to review. The worked example's
document, the digest it checks itself against, and the canonical form and byte count in its
transcript are all reconciled against the committed golden vector, so a change to that vector
which skipped this page fails the build instead of leaving a stale transcript here. And the
hash-scope table is reconciled against DEC-10 field by field, in both directions — that one
runs where the specification set is checked out beside this repository, which is a working
checkout rather than this repository's own CI.
