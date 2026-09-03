# The pytest plugin and CI gating

This page takes a team from an ordinary Python repository to a merge gate: one dependency, one
marker, and a workflow that turns design-time verification into a check on every pull request.

It is written to answer the question that decides whether such a gate survives its first month —
**what exactly does each stage block, and what does it merely report?** A gate nobody understands
gets disabled the first time it goes red for a reason nobody expected, so every claim below about
what fails and what does not is printed by code CI executes, and the workflow it ends with is a
file this repository runs on every push.

!!! note "Following along"

    The suite this page shows is `examples/ci_gate/` in this repository, and the workflow is
    `.github/workflows/gebra-gate-example.yml`. The suite's two main files are reproduced here
    verbatim, and the workflow all but its last step — each held equal to its file by
    `tests/docs/test_ci_gating_guide.py`, so the page cannot document a workflow CI does not
    run. The agent under test is `tests/sample_workflows/travel_booking.py`, the same
    definition the other pages use; in your repository that import is your own builder and
    nothing else changes.

## The gate reads your workflow; it does not run it

The plugin calls the function you marked — your code, called the way pytest calls any test —
and hands what it returns to `gebra.extract()`, which imports and inspects a `StateGraph`, a
compiled graph or an LCEL `Runnable` without invoking one. From there the validators see only
the extracted document. No node body, router, tool or model is called, and no connection is
opened.

That is checkable rather than promised. The agent below is guarded: every one of its node
bodies records itself and raises if anything calls it. Extract it, verify it, and read the
ledger afterwards.

<!-- gebra:example id=nothing-was-executed -->
```python
from gebra.pytest_plugin import verify_target
from tests.sample_workflows import travel_booking

verification = verify_target(
    travel_booking.build_travel_booking_agent(),
    name="travel_agent",
    source="examples/ci_gate/test_agent.py::test_gebra#travel_agent",
)

print(f"gate             exit {verification.report.gate.exit_code}")
print(f"node bodies run  {travel_booking.TRIPPED}")
```

<!-- gebra:output id=nothing-was-executed -->
```text
gate             exit 0
node bodies run  []
```

`verify_target` is the plugin's own entry point — the function each generated test item calls.
A green gate therefore says something about the definition as written, never about what the
agent does when it runs; [what gebra checks](../concepts/what-gebra-checks.md) is where that
boundary is drawn in full.

## One dependency, one marker

Installing the package registers the plugin through pytest's `pytest11` entry point. There is
nothing to add to `conftest.py` and no `-p` flag to pass: mark a function that *returns* your
graph, and the run reports one test item per checked property.

```python
import pytest

from my_package.agents import build_travel_booking_agent


@pytest.mark.gebra(name="travel_agent")
def test_gebra():
    return build_travel_booking_agent()
```

Run `pytest` and that one function becomes five items — one per property this release can
answer, named so a red build points at the property before anyone opens a log:

<!-- gebra:example id=one-item-per-property -->
```python
from gebra.pytest_plugin import enabled_properties
from gebra.verify import PROPERTY_SLUGS, is_implemented

for slug in enabled_properties():
    print(f"test_gebra[travel_agent-{slug}]")

deferred = [slug for slug in PROPERTY_SLUGS if not is_implemented(slug)]
print()
print(f"items generated     {len(enabled_properties())}")
print(f"catalog properties  {len(PROPERTY_SLUGS)}")
print(f"no item generated   {len(deferred)} deferred: {', '.join(deferred[:3])}, …")
```

<!-- gebra:output id=one-item-per-property -->
```text
test_gebra[travel_agent-graph-well-formed]
test_gebra[travel_agent-termination-witness]
test_gebra[travel_agent-dataflow-completeness]
test_gebra[travel_agent-effect-safety]
test_gebra[travel_agent-determinism-replay]

items generated     5
catalog properties  13
no item generated   8 deferred: signature-soundness, guard-exhaustiveness, retry-coherence, …
```

Three things in that list are worth reading before you point CI at it.

**One item per property, not one per test.** The `name=` keyword labels the target in the item
id; without it the function's name minus its `test_` prefix is used. A red build therefore names
the property that failed, in the item id, before anyone opens a log.

**Eight properties get no item, and that is not a pass.** The catalog holds thirteen properties
and this release implements five. The other eight answer with a structured not-implemented
marker, which is visible in the run report and in the closing `gebra` section — never as a green
check. A property nobody has written never reports a silent success.

**Returning nothing is a usage error.** A marked function that falls off the end has verified
nothing, and a green item there would be the worst possible outcome, so the plugin refuses it.
The same is true of an `async def` target: there is nothing to await, because nothing is run.

## Assert against the extracted graph yourself

The marker is the gate. Beside it, two fixtures let you write ordinary pytest against the same
extraction. Override `gebra_workflow` once, in `conftest.py`, and both follow from it:
`gebra_graph` is the extracted IR, and `gebra_verification` is the whole verification run over
it.

```python
"""Declare which workflow the gebra fixtures are about.

``gebra_workflow`` is the one fixture a suite overrides. Everything else follows from it:
``gebra_graph`` is this workflow's extracted IR, and ``gebra_verification`` is the whole
verification run over that IR. Nothing here runs the workflow — the builder is handed to
gebra, which imports and inspects it.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.sample_workflows.travel_booking import build_travel_booking_agent


@pytest.fixture
def gebra_workflow() -> Any:
    """The workflow under verification — in your repository, your own builder."""
    return build_travel_booking_agent()
```

```python
"""The whole of a first gebra gate: one marked function, plus assertions of your own.

The marked function is the gate — the plugin calls it, extracts what it returns and reports
one test item per checked property. The two tests under it are ordinary pytest, written
against the fixtures the plugin ships.
"""

from __future__ import annotations

from typing import Any

import pytest

from gebra.ir import WorkflowIR
from gebra.pytest_plugin import TargetVerification
from tests.sample_workflows.travel_booking import build_travel_booking_agent


@pytest.mark.gebra(name="travel_agent")
def test_gebra() -> Any:
    """Return the workflow to verify; one item per property is generated from it."""
    return build_travel_booking_agent()


def test_the_compensating_path_is_still_wired(gebra_graph: WorkflowIR) -> None:
    """`gebra_graph` is the extracted IR — assert against it like any other value."""
    assert "release_hotel_hold" in {node.id for node in gebra_graph.nodes}


def test_no_property_reported_a_blocking_finding(gebra_verification: TargetVerification) -> None:
    """`gebra_verification` is the whole run: all thirteen outcomes and the derived gate."""
    gate = gebra_verification.report.gate
    assert (gate.counts.fatal, gate.counts.error) == (0, 0)
```

`gebra_graph` is a plain value — a `WorkflowIR` — so assertions about topology, state schema or
declared contracts are ordinary Python. `gebra_verification` carries the run: all thirteen
outcomes, the derived gate, and the warnings extraction raised on the way.

<!-- gebra:example id=the-two-fixtures -->
```python
from gebra.pytest_plugin import resolve_ir, verify_target
from gebra.verify import PropertyReport
from tests.sample_workflows.travel_booking import build_travel_booking_agent

resolution = resolve_ir(build_travel_booking_agent())
print("gebra_graph")
print(f"  {len(resolution.ir.nodes)} nodes, {len(resolution.ir.edges)} edges")
print(f"  input_mode {resolution.input_mode}, extractor {resolution.extractor_version}")

verification = verify_target(
    build_travel_booking_agent(),
    name="travel_agent",
    source="examples/ci_gate/test_agent.py::test_gebra#travel_agent",
)
report = verification.report
verdicts = [item for item in report.properties if isinstance(item, PropertyReport)]
print("gebra_verification")
print(
    f"  {len(report.properties)} outcomes ({len(verdicts)} verdicts, "
    f"{len(report.properties) - len(verdicts)} not-implemented markers)"
)
print(f"  gate {report.gate.outcome}, exit {report.gate.exit_code}")
print(f"  extraction warnings {len(verification.extraction_notes)}")
```

<!-- gebra:output id=the-two-fixtures -->
```text
gebra_graph
  9 nodes, 7 edges
  input_mode extracted, extractor 0.0.1
gebra_verification
  13 outcomes (5 verdicts, 8 not-implemented markers)
  gate pass, exit 0
  extraction warnings 0
```

Two practical notes about what you hand these surfaces.

**A builder and the same graph compiled are different documents.** `runtime.checkpointer` and
`runtime.interrupts` can be read only off a compiled object, so the compiled extraction carries a
`runtime` block the builder extraction does not — and therefore a different `graph_version`.
Neither is more correct and the plugin chooses neither; a suite that compares an item against a
stored snapshot needs both to be at the same level.

**Which `gebra.toml` was in reach is a fact about the run.** A sidecar can fill every annotation
slot the decorators can — contracts, effect tags, the loop-variant declaration P-02 reads, the
determinism claim P-08 reads — so it sits inside the `graph_version` hash scope and moves
verdicts, not only the digest. Without
an explicit path, discovery walks up from the pytest process's working directory — which is
exactly the thing that differs between a laptop and a runner. On a CI surface, pin it: the marker
takes `sidecar="path/to/gebra.toml"`, and the fixture surface takes the same value by overriding
`gebra_sidecar`. Whichever file was used is recorded on
`gebra_verification.report.subject.sidecar`.

## Severity decides which item fails

The default mapping is one sentence: a **FATAL** or **ERROR** finding owned by a property fails
that property's item; a **WARNING** finding is reported and gates nothing. Here is a variant of
the same agent with one edit — the billable `book_flight` node has lost the `@gebra.idempotent`
declaration that protected it inside the booking retry region.

<!-- gebra:example id=severity-decides-the-item -->
```python
from gebra.pytest_plugin import BLOCKING_SEVERITIES, enabled_properties, item_outcome, verify_target
from tests.sample_workflows.travel_booking_defects import build_defect_2_unprotected_retry

verification = verify_target(
    build_defect_2_unprotected_retry(),
    name="unprotected_retry",
    source="examples/ci_gate/test_unprotected_retry.py::test_gebra#unprotected_retry",
)

print(f"blocking severities: {sorted(BLOCKING_SEVERITIES)}")
for slug in enabled_properties():
    outcome = item_outcome(verification, slug)
    print(f"  {slug:<22} {'FAILED' if outcome.failed else 'passed'}")
    for finding in outcome.findings:
        print(f"      {finding.severity} {finding.property_condition} [{finding.claim_class}]")
print(f"run gate: exit {verification.report.gate.exit_code}")
```

<!-- gebra:output id=severity-decides-the-item -->
```text
blocking severities: ['error', 'fatal']
  graph-well-formed      passed
  termination-witness    passed
  dataflow-completeness  passed
  effect-safety          FAILED
      error unprotected-effect-in-retry-region [defensible-a]
  determinism-replay     passed
run gate: exit 1
```

One item failed and four did not. That is what the per-property itemization buys in a CI log: a
red build points at `effect-safety` and a node, not at "gebra failed". The message the failing
item carries opens like this:

```text
gebra · unprotected_retry · effect-safety
  ERROR unprotected-effect-in-retry-region [defensible-a]
    at node 'book_flight', effect=[…], cycle=[…]
```

The condition id is from a closed registry, the anchor is a structured location, and the
`[defensible-a]` is the finding's **claim class** — how strong a claim this particular record is.
[P-06 effect-safety](../validators/p06-effect-safety.md) is what that finding means and what to
change; [verify and interpret](../tutorials/verify-and-interpret.md#a-failure-names-a-condition-and-a-locus)
is how to read any of them.

Which item a finding fails is decided by the property that **owns** it, not by the report it
arrived on. The envelope licenses one cross-property carrier — an *advisory*, a WARNING-class side
finding riding another property's report — and it still fails its own property's item, never the
host's. (A co-failure is same-property carriage, so its owner and its host are the same property
by construction. And in this release `verify()` assembles no advisories of its own, so the
cross-property case is a rule the itemization already honours rather than something a report you
hold will show you.) The point that survives either way: the item that goes red is the property
the finding belongs to, so the itemization stays a reliable index into what went wrong.

One outcome is not a finding at all. If the run could not be assembled — a target that would not
extract, an IR this build has no semantics for — no verdict was reached, and **every** item of
that target fails carrying that reason rather than one of them reporting a property's opinion.
Exit 2 is never a verification result.

### A WARNING is reported, and by default gates nothing

The complement, on a different edit of the same agent: `classify_request` keeps its determinism
claim but drops the `temperature` pin, which P-08 reports as an incoherent claim at WARNING grade.

<!-- gebra:example id=a-warning-is-a-note -->
```python
from gebra.pytest_plugin import item_outcome, verify_target
from tests.sample_workflows.travel_booking_defects import build_defect_3_false_determinism

verification = verify_target(
    build_defect_3_false_determinism(),
    name="loose_claim",
    source="examples/ci_gate/test_agent.py::test_gebra#loose_claim",
)
outcome = item_outcome(verification, "determinism-replay")

for finding in outcome.findings:
    print(f"finding      {finding.severity} {finding.property_condition} [{finding.claim_class}]")
print(f"blocking     {len(outcome.blocking)}")
print(f"notes        {len(outcome.notes)}")
print(f"item failed  {outcome.failed}")
print(
    f"run gate     exit {verification.report.gate.exit_code} — {verification.report.gate.outcome}"
)
```

<!-- gebra:output id=a-warning-is-a-note -->
```text
finding      warning deterministic-llm-temperature-unpinned [heuristic]
blocking     0
notes        1
item failed  False
run gate     exit 0 — pass-with-notes
```

The finding is present, carried on the item and in the closing report, and the build is green.
`pass-with-notes` is the run's own word for that state. Whether it should stay green is a policy
question, and the next section is the flag that answers it.

## Strict mode moves the gate, never the record

`--gebra-strict` promotes WARNING-grade records to gate failures. It comes in two forms: bare, it
promotes every WARNING in the run; `--gebra-strict=<slug>[,<slug>…]` promotes only the named
properties'. Run the same defective agent under all three policies and watch what moves.

<!-- gebra:example id=the-gate-moves-the-record-does-not -->
```python
from gebra.pytest_plugin import item_outcome, verify_target
from gebra.verify import STRICT_ALL, STRICT_OFF, StrictPolicy
from tests.sample_workflows.travel_booking_defects import build_defect_3_false_determinism

policies = [
    ("no flag", STRICT_OFF),
    (
        "--gebra-strict=determinism-replay",
        StrictPolicy(mode="per-property", properties=("determinism-replay",)),
    ),
    ("--gebra-strict", STRICT_ALL),
]

for label, strict in policies:
    verification = verify_target(
        build_defect_3_false_determinism(),
        name="loose_claim",
        source="examples/ci_gate/test_agent.py::test_gebra#loose_claim",
        strict=strict,
    )
    outcome = item_outcome(verification, "determinism-replay")
    record = outcome.findings[0]
    gate = verification.report.gate
    print(label)
    print(f"    record      {record.severity} {record.property_condition} [{record.claim_class}]")
    print(
        f"    item        {'FAILED' if outcome.failed else 'passed'}"
        f"  ({len(outcome.promotions)} promotion(s))"
    )
    print(f"    run gate    exit {gate.exit_code} — {gate.outcome}")
```

<!-- gebra:output id=the-gate-moves-the-record-does-not -->
```text
no flag
    record      warning deterministic-llm-temperature-unpinned [heuristic]
    item        passed  (0 promotion(s))
    run gate    exit 0 — pass-with-notes
--gebra-strict=determinism-replay
    record      warning deterministic-llm-temperature-unpinned [heuristic]
    item        FAILED  (1 promotion(s))
    run gate    exit 1 — fail
--gebra-strict
    record      warning deterministic-llm-temperature-unpinned [heuristic]
    item        FAILED  (1 promotion(s))
    run gate    exit 1 — fail
```

The record line is byte-identical in all three runs. `severity: warning`, the same condition id,
the same claim class — promotion **changes the gate, never the record**. What failed the item is
the promotion, which the report shows beside the record rather than in place of it, so a promoted
finding never reads as a stronger finding than it is.

Two consequences worth carrying into a rollout decision.

**Per-property first.** Promoting one property is a decision about one kind of finding;
promoting everything is a decision about a noise floor you have not measured yet.
`--gebra-strict=determinism-replay` is the usual first promotion, because every P-08 condition
this release can emit is WARNING-grade by the frozen catalog — so nothing about determinism claims
gates until you say so.

**Strict reaches records no finding list shows.** A property can carry a WARNING-graded structured
*note* — display-adjacent, never gate-bearing on its own — on a passing report's witness and on a
failing one's records alike, and a strict policy promotes those too. A note with no grade is never
promotable. This is why "we have no
WARNING findings" is not the same statement as "bare strict changes nothing for us"; the run
report is where you check, and [strict mode in the verify
tutorial](../tutorials/verify-and-interpret.md#strict-mode-moves-the-gate-never-the-record) walks
the whole shape.

A word on the property whose name invites the misreading: `termination-witness` reports **witness
presence** — whether every simple cycle carries a declared bound in a form the checker recognises
— and never a statement that a run halts. Strict mode changes which records fail a step. It
changes nothing about what any of them claim.

## Subsetting items does not subset the run

`--gebra-select` and `--gebra-skip` narrow which properties get an item. They do not narrow what
is checked: the run always answers the whole catalog, so `gebra_verification` still carries
thirteen outcomes and the run's own exit code is still derived from all of them.

<!-- gebra:example id=subsetting-items -->
```python
from gebra.pytest_plugin import GatePolicy, enabled_properties_for, item_outcome, verify_target
from gebra.verify import STRICT_OFF
from tests.sample_workflows.travel_booking_defects import build_defect_2_unprotected_retry

verification = verify_target(
    build_defect_2_unprotected_retry(),
    name="unprotected_retry",
    source="examples/ci_gate/test_unprotected_retry.py::test_gebra#unprotected_retry",
)
itemized = enabled_properties_for(GatePolicy(strict=STRICT_OFF, skip=("effect-safety",)))

print(f"items with --gebra-skip=effect-safety: {len(itemized)}")
print(f"  {', '.join(itemized)}")
print(f"any item failing: {any(item_outcome(verification, slug).failed for slug in itemized)}")
print(
    f"the run's own gate: exit {verification.report.gate.exit_code}, "
    f"{verification.report.gate.counts.error} error"
)
```

<!-- gebra:output id=subsetting-items -->
```text
items with --gebra-skip=effect-safety: 4
  graph-well-formed, termination-witness, dataflow-completeness, determinism-replay
any item failing: False
the run's own gate: exit 1, 1 error
```

Every pytest item is green and the run found an ERROR. That is the flag doing exactly what was
asked of it, and it is a trap worth knowing about before you put a `--gebra-skip` in `addopts`:
the closing `gebra` section says so out loud, counting the blocking findings and promotions that
fell outside the subset and naming the properties that own them. Skipping is for staging an
adoption, not for silencing a finding — and a slug outside the thirteen-property catalog is
refused at configure time rather than dropped, so a typo cannot quietly widen what gates.

## The rollout: report-only → gate → strict

The action wraps all of this as one CI step, and the ladder is one word in the workflow. The
point of climbing it is that findings become visible before they become blocking, so the gate
never arrives as a surprise red.

### 1. `report-only` — see the findings, block nothing

```yaml
- name: Rung 1 — report-only, over a suite that has a real finding
  id: report_only
  uses: ./.github/actions/gebra-gate
  with:
    tests: examples/ci_gate/test_unprotected_retry.py
    mode: report-only
    pytest-args: "-q"
```

Failing items leave the step **green**; the run gets one warning annotation and its closing
`gebra` report is appended to the job summary — up to a 200-line cap, past which the remainder is
counted in a note rather than dropped in silence, with the whole of it still in the job log. Use
this rung to inventory where your workflow definitions actually stand — typically for as long as
it takes to fix or accept what it finds.

Note what report-only does *not* forgive. An interrupted run, an internal error, a usage error,
and a run that collected **nothing** are all red on this rung, because a reporting stage that hid
a broken run would report nothing at all.

### 2. `gate` — FATAL and ERROR block

```yaml
- name: Rung 2 — gate, the recommended steady state
  id: gate
  uses: ./.github/actions/gebra-gate
  with:
    tests: examples/ci_gate/test_agent.py
    pytest-args: "-q"
```

The default mode, and the steady state the ladder is climbing towards. An item fails when a
FATAL- or ERROR-grade finding owned by that property lands; WARNING-grade records are reported
and do not gate. Those are the same two severities `gebra verify` exits 1 on, so a red build
reproduces from the command line with no second policy to remember.

### 3. `strict` — promote warnings, per property first

```yaml
- name: Rung 3 — strict, promoting every WARNING in the run
  id: strict
  uses: ./.github/actions/gebra-gate
  with:
    tests: examples/ci_gate/test_agent.py
    mode: strict
    pytest-args: "-q"
```

`mode: strict` adds `--gebra-strict` to the run. Add `strict-properties: determinism-replay` to
promote one property instead of all of them; that input is refused outside `strict`, so a policy
that would silently do nothing is a loud misconfiguration instead. As the section above shows,
promotion moves the gate and leaves every record exactly where it stands.

### What each mode does with a pytest exit

| pytest exit | meaning | `report-only` | `gate` / `strict` |
|---|---|---|---|
| 0 | every collected test passed | green | green |
| 1 | tests failed | **green**, with a warning annotation | red |
| 2 | the run was interrupted | red | red |
| 3 | internal pytest error | red | red |
| 4 | pytest usage error | red | red |
| 5 | no tests were collected | red | red |

`report-only` forgives exactly one thing: test failures. **A gate that checked nothing never
passes.** The step also publishes two outputs — `exit-code`, the gated run's raw pytest exit, and
`outcome`, one of `pass`, `failures`, `empty`, `error` or `refused` — so a follow-on step can
notify or label without re-parsing a log. Those five words are the *step's* vocabulary, and they
are not the run's: `gate.outcome` inside a gebra report is `pass`, `pass-with-notes`, `fail` or
`tool-error`, which is why the same run can be an `outcome: pass` step and a `pass-with-notes`
report.

## The action's interface

| input | default | meaning |
|---|---|---|
| `tests` | `""` | pytest targets for the gated run (paths or node ids, shell-style tokens). Empty means pytest's own collection from the working directory. |
| `mode` | `gate` | The rollout rung: `report-only`, `gate` or `strict`. |
| `strict-properties` | `""` | Comma-separated property slugs to promote under `strict`; empty promotes every WARNING in the run. Refused outside `strict`. |
| `select` | `""` | Comma-separated property slugs, passed as `--gebra-select`. |
| `skip` | `""` | Comma-separated property slugs, passed as `--gebra-skip`. |
| `pytest-args` | `""` | Extra pytest arguments (e.g. `-q`). `--gebra-*` flags are refused here — gate policy is declared once, through the inputs above. |
| `python` | `python` | The interpreter that drives the gate; the gated run is that interpreter's own `-m pytest`, so this one value picks the environment being gated. |
| `working-directory` | `.` | Where the gated run happens. |

Two boundaries the action keeps deliberately.

**It installs nothing.** Your environment, your package manager, your pins — the job sets Python
up and installs the test environment before the gate step, exactly as it would for any other
pytest run. An action that installed for you would be a second, invisible resolution of the
dependency you are gating.

**It owns no vocabulary.** An unknown property slug in `strict-properties`, `select` or `skip` is
refused by the plugin itself, before anything runs, and surfaces as `outcome: error`. The action
and the plugin can therefore never disagree about which properties exist.

From another repository, reference it by owner, repository and ref — pin a commit SHA rather than
a branch when you need reproducibility:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.13"
- name: Install your test environment (gebra included)
  run: pip install -e ".[test]" # your project's own equivalent
- name: gebra gate
  uses: Gebra-Tech/gebra/.github/actions/gebra-gate@main
  with:
    tests: tests/agents
    mode: report-only
```

## The whole workflow

Here it is, all but its last step. This repository runs it on every push and every pull request;
the three rung steps above are its steps, quoted from it.

```yaml
name: gebra gate example

on:
  push:
  pull_request:

jobs:
  gebra-gate-example:
    name: "The documented gate, on all three rungs"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      # The action installs nothing; this is the environment being gated.
      - name: Install the package and the test environment being gated
        run: pip install -e ".[dev]" -c tools/matrix-constraints.txt

      - name: Rung 1 — report-only, over a suite that has a real finding
        id: report_only
        uses: ./.github/actions/gebra-gate
        with:
          tests: examples/ci_gate/test_unprotected_retry.py
          mode: report-only
          pytest-args: "-q"

      - name: Rung 2 — gate, the recommended steady state
        id: gate
        uses: ./.github/actions/gebra-gate
        with:
          tests: examples/ci_gate/test_agent.py
          pytest-args: "-q"

      - name: Rung 3 — strict, promoting every WARNING in the run
        id: strict
        uses: ./.github/actions/gebra-gate
        with:
          tests: examples/ci_gate/test_agent.py
          mode: strict
          pytest-args: "-q"
```

Two lines of it are this repository's rather than yours. `-c tools/matrix-constraints.txt` is a
freeze-time pin lock, and the local `./.github/actions/gebra-gate` reference works because the
action lives here; from elsewhere it is the `Gebra-Tech/gebra/...@ref` form above.

The real file carries one further step, which is why this page can make claims about the ladder
at all: it compares each rung's `outcome` output against what this page documents for it — `1` and
`failures` for report-only, `pass` for gate and for strict — and fails the workflow if any of them
has moved. A change that made report-only stop forgiving test failures, or made the seeded
finding stop being found, turns that workflow red rather than quietly dating this page.

In your own repository you would normally run **one** rung, not three: point `tests` at your
verification targets, start on `report-only`, and change the one word when you are ready.

## Has the store kept up? The freshness marker

The plugin ships a second marker for a different question. `@pytest.mark.gebra_freshness` fails
when the workflow a function returns is not the snapshot the `.gebra/` store currently holds —
the CI check for "the definition changed and nobody re-snapshotted it".

```python
@pytest.mark.gebra_freshness(name="travel_agent")
def test_snapshot_is_current():
    return build_travel_booking_agent()
```

`check_freshness` is the same question programmatically:

<!-- gebra:example id=freshness -->
```python
from pathlib import Path

from gebra.pytest_plugin import check_freshness
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows.travel_booking import build_travel_booking_agent
from tests.sample_workflows.travel_booking_defects import build_defect_2_unprotected_retry

store = SnapshotStore.for_project(Path.cwd())
snapshot(build_travel_booking_agent(), store=store, source="examples/ci_gate")

unchanged = check_freshness(build_travel_booking_agent(), store=store.path)
print(f"unchanged  fresh={unchanged.fresh}  state={unchanged.state.value}")

edited = check_freshness(build_defect_2_unprotected_retry(), store=store.path)
print(f"edited     fresh={edited.fresh}  state={edited.state.value}")
```

<!-- gebra:output id=freshness -->
```text
unchanged  fresh=True  state=fresh
edited     fresh=False  state=stale
```

It is a check on the **store**, not a fourteenth property. It runs no validator, and — this is
the part that makes it a gate rather than a formality — it never writes: a check that fixed
itself would be a check that always passes. Recording is `gebra snapshot`'s job. And a stale
result says the content moved and which counters move with it, never whether the change is safe.

Put it on its own function. The two markers ask different questions of the same graph, and the
plugin refuses both on one function rather than letting one of them silently not run.

## What a green gate means

A green gebra item means the workflow **definition** satisfied the checked property, on the
evidence that property reads, and nothing more than that. Four things follow, and they are worth
saying to a team before the badge goes on the README rather than after.

**It is not a statement about behaviour at run time.** Nothing was executed; see the ledger at
the top of this page.

**Some passes are qualified, and the report says which.** A pass is reported with a claim class,
read from the property catalog: a `heuristic` one is advisory lint with no proof claim, and a
`defensible-a` one is decided over the IR plus what the code declared about itself — annotation
truthfulness is trusted there, the way a type annotation is trusted. Where P-01 found the topology
ill-formed, the other topology-consuming properties' results become best-effort diagnostics for
that run rather than contract-bearing verdicts — and each such report says so on its own line.

**Some passes are vacuous, and the witness says so.** `termination-witness` passes on an acyclic
graph because there is no cycle for a bound to be declared on. That is a true and useful answer,
and it is not the same answer as "every loop is bounded".

**Eight properties were never checked.** They are in the report as not-implemented markers, which
take no part in the exit code. A green run is green on five.

The closing `gebra` section prints all of this — the claim class and a witness summary for each
pass, every record of each failure, the not-checked markers, the strict policy in force with
whatever it promoted, and the run's counts and exit code — with no flag, on every run, so a
default `pytest` cannot show five green ticks and stay silent about the rest.

## Where this page is checked

Every Python example above runs in CI through the [executable-examples
harness](../contributing/executable-examples.md), in a child interpreter where opening a
connection, compiling a graph and invoking a runnable all raise, and its printed output is
compared against what this page shows.

The workflow, the three rung steps and the two example files are held equal to
`.github/workflows/gebra-gate-example.yml` and `examples/ci_gate/` by
`tests/docs/test_ci_gating_guide.py`, which also holds the two interface tables to the action's
own manifest and the mode-by-exit table to the driver's own translation — so a renamed input, a
new outcome word or a changed exit rule fails the build instead of dating the page. The item ids
this page shows are the ids pytest actually collects from that suite, checked the same way.

The workflow itself runs on every push and every pull request, and its last step asserts that each
rung reported what this page says it reports.

One file of the example suite is this repository's rather than an adopter's, and it is the reason
the first section can open the way it does: a conftest one level above `examples/ci_gate/` asserts,
before and after every test there, that the guarded agent's node ledger is empty. It is not
reproduced above because nothing in it is something you would copy — it is the tripwire that keeps
"the gate ran and nothing was invoked" a checked statement rather than a sentence.
