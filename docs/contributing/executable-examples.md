# Executable examples

An example marked as executable is executed in CI, exactly as it appears on the page. The
page is the source: the harness reads the fenced block out of the Markdown, runs those bytes
in a fresh interpreter, and compares what they printed against the output block the page
shows. There is no second copy of the code to fall out of step with the prose, so an example
that stopped working stops the build instead of misleading a reader.

This page is both the description of that mechanism and a demonstration of it — the example
below is discovered, run and checked by the same harness as every other.

## Marking an example

Two HTML comments, which every Markdown renderer hides:

````markdown
<!-- gebra:example id=first-look -->
```python
print("hello")
```

<!-- gebra:output id=first-look -->
```text
hello
```
````

The `id` is unique within the page and joins the two blocks. The output block is optional,
and leaving it out is not a gap: an example that declares no output must print nothing, so
every example's standard output is pinned either way. A directive in the `gebra:` namespace
that the harness does not recognise is an error rather than a silently skipped example.

## What the harness does with it

`tools/docs_examples.py` scans the site's Markdown — reading text, importing nothing — and
runs each example in a child interpreter under a guard, from a temporary working directory
so that an example writing a `.gebra/` store leaves the repository untouched.

The guard is the point. Documentation examples read workflow definitions; they never run
them:

- name resolution and *connecting* raise from the child's first line, and constructing a
  socket raises from the moment the example's own code begins;
- `StateGraph.compile` raises from before `gebra` is imported, and so does every
  `Runnable.invoke` / `stream` / `batch` in the class tree — compiling is not the only route
  to running something. Compiled graphs and chat models are both in that tree, so a model
  call trips on its own account rather than only because it would have needed the network;
- the sample graphs the examples are written against arm the rest: every node body and
  router in `tests/sample_workflows/` raises if it is called, and records the call in the
  module's ledger *before* raising, so a sentinel that a `try` block swallowed still fails
  the run;
- that sweep is fail-closed. A sample workflow keeping no ledger is reported as unledgered
  and fails the example, rather than being read as clean — "nothing was recorded" must not
  give the same answer as "nothing ran";
- and it reaches a third kind of module: one the example **wrote into its working directory
  and imported**, found by its `__file__` rather than by its name. That shape exists because
  what the extractor can read off a node body depends on the body being in a file, so a page
  whose subject is inference has to put its graph in one;
- the child reports its attempt list, the ledger and the unledgered set when it finishes,
  and any of the three coming back non-empty fails the example.

Three boundaries follow, and they are worth knowing before writing a page.

Arming `StateGraph.compile` excludes the compiled path and only that one — extracting an
LCEL `Runnable` compiles nothing — so the harness admits builder-path, LCEL and
document-path examples. Extending it to a compiled graph is a change to the harness, with
its own controls, and never something an individual page opts out of.

The armed surface is `tests/sample_workflows/` **and any module the example itself defines or
writes**. A body a page defines is its author's code, and the armed `invoke` family does not
reach it — extraction unwraps a node to the bare callable, so a call on that reference goes
past every raiser above. **A page that defines the graph it shows therefore arms its own node
bodies: record into a module-level `TRIPPED` list on the body's first line, then raise.** The
first line matters. A body that reads its state before arming itself can be entered with a
state that lacks the key, and then the read raises, the ledger is never written, and a caller
that swallowed the exception leaves nothing behind — which is exactly the accidental shape the
ledger is for. A page that needs a ready-made graph builds against the sample workflows instead
and inherits their ledger.

The guard lives inside one interpreter. A subprocess an example spawns inherits none of it,
and the underscore-prefixed interpreter internals behind the guarded modules are not patched.
**Examples do not spawn processes and do not reach past the public modules** — the guard is
built to catch a page that innocently reaches out, not one written to get around it.

`tests/docs/test_doc_examples.py` turns every discovered example into its own test, so the
suite runs them in each CI cell, and fires a control probe at each raiser in the guard: a
tripwire nobody trips reports nothing.

## The demonstration

Extraction, verification and a snapshot over the sentinel graph — a workflow whose every
node raises if it is called:

<!-- gebra:example id=extract-verify-snapshot -->
```python
from pathlib import Path

import gebra
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from gebra.verify import PropertyReport, verify
from tests.sample_workflows.sentinel_graph import build_sentinel_graph

envelope = gebra.extract(build_sentinel_graph())
print("nodes:", [node.id for node in envelope.ir.nodes])
print("warnings:", sorted({warning.code.value for warning in envelope.warnings}))

report = verify(envelope.ir)
print("gate:", report.gate.outcome, "exit", report.gate.exit_code)
for outcome in report.properties:
    if isinstance(outcome, PropertyReport):
        print(f"  {outcome.property}: {outcome.result}")

store = SnapshotStore.for_project(Path.cwd())
recorded = snapshot(build_sentinel_graph(), store=store, source="docs/example")
print("snapshot:", recorded.action.value, "as", recorded.version)
print("store:", sorted(path.name for path in store.path.iterdir()))
```

<!-- gebra:output id=extract-verify-snapshot -->
```text
nodes: ['act_step', 'plan_step', 'summarize_step']
warnings: ['contract-defaulted']
gate: pass exit 0
  graph-well-formed: pass
  termination-witness: pass
  dataflow-completeness: pass
  effect-safety: pass
  determinism-replay: pass
snapshot: recorded as 1.0.0.0
store: ['meta.yaml', 'reports', 'snapshots']
```

Four things in that transcript are worth naming, because they are what the run establishes
rather than what the prose asserts.

- The extraction reports a `contract-defaulted` warning: these nodes carry no annotated
  contract, so the conservative default was applied and written into the IR. The warning is
  what keeps that value heuristic-grade instead of letting it read as declared.
- Five properties are printed because five are implemented in this release. The catalog holds
  thirteen, and the other eight come back as structured not-implemented markers that take no
  part in the exit code — a property nobody has written never reports a silent pass.
- Each of the five reports `pass`. That is a statement about the definition *as written* —
  its structure and its declared contracts — and about nothing else; and since the contracts
  here were defaulted rather than declared, part of it is a statement about a default.
- Some of those passes are vacuous, which is worth reading rather than glossing over. The
  sentinel graph is acyclic, so `termination-witness` passes because there is no simple cycle
  for a bound to be declared on — not because a bound was found.

The snapshot is then recorded under `1.0.0.0` because the store was empty.

## Running it yourself

```console
$ python tools/docs_examples.py --list      # what is marked, and where
$ python tools/docs_examples.py --report    # run them all; exit 1 on any failure
```

The `docs` CI job runs the second form, and the test suite runs each example as its own
test item.
