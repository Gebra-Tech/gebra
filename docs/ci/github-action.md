# Verification as a CI gate — the gebra GitHub Action

This repository ships a reusable GitHub Action, `.github/actions/gebra-gate`, that
wraps the pytest plugin as a CI gate: one pytest run with the plugin active, a
one-word rollout switch, the run's closing `gebra` report appended to the step
summary, and the exit code translated into the step's verdict. The action runs in this
repository's own CI on every push — the DoD scenario job issues its pytest invocation
through it — so the in-repo example below is executed, not aspirational.

This page is the action's own reference. The adopter-facing walkthrough — the plugin
surfaces the gate is built on, which findings fail which test item, and a complete example
workflow that runs all three rungs on every push — is the published guide
[The pytest plugin and CI gating](../guides/pytest-plugin-and-ci-gating.md).

What the gate checks is the workflow **definition**: the plugin extracts the Gebra IR
from the graph a `@pytest.mark.gebra`-marked test returns and verifies it. gebra runs
nothing on that path — it calls the function you marked, the way pytest calls any
test, and inspects what it returns; no workflow node, model call, or network
connection is part of the verification.

## What the action assumes

- The job has already set up Python and installed your test environment with `gebra`
  in it. The action installs nothing — your environment, your package manager, your
  pins. (This repository's own consumer job installs frozen substrate pins first for
  exactly that reason.)
- Installing gebra registers the plugin through pytest's `pytest11` entry point —
  there is nothing to configure in `conftest.py`.
- The collected tests include at least one gebra-marked target. A run that collects
  nothing fails the gate rather than passing it (see the verdict table).

## The interface

Inputs:

| input | default | meaning |
|---|---|---|
| `tests` | `""` | pytest targets for the gated run (paths or node ids, shell-style tokens). Empty means pytest's own collection from the working directory. |
| `mode` | `gate` | The rollout rung: `report-only`, `gate`, or `strict` — see the ladder below. |
| `strict-properties` | `""` | Comma-separated property slugs to promote under `strict` (e.g. `determinism-replay`); empty promotes every WARNING in the run. Refused outside `strict`. |
| `select` | `""` | Comma-separated property slugs, passed as `--gebra-select`. |
| `skip` | `""` | Comma-separated property slugs, passed as `--gebra-skip`. |
| `pytest-args` | `""` | Extra pytest arguments (e.g. `-q`). `--gebra-*` flags are refused here — gate policy is declared once, through the inputs above. |
| `python` | `python` | The interpreter that drives the gate; the gated run is that interpreter's own `-m pytest`, so this one value picks the environment being gated. |
| `working-directory` | `.` | Where the gated run happens. |

Outputs:

| output | meaning |
|---|---|
| `exit-code` | The gated pytest run's raw exit code; empty when the request was refused before pytest ran. |
| `outcome` | One of `pass`, `failures`, `empty`, `error`, `refused`. |

The step verdict, by mode and pytest exit:

| pytest exit | meaning | `report-only` | `gate` / `strict` |
|---|---|---|---|
| 0 | every collected test passed | green | green |
| 1 | tests failed | **green**, with a warning annotation | red |
| 5 | no tests were collected | red | red |
| 2 / 3 / 4 / other | interrupted / internal error / usage error | red | red |

A gate that checked nothing never passes: an empty collection and every
non-completion exit are red under every mode — `report-only` forgives test failures
and nothing else. The unit being gated is the pytest run you point the action at, so
an ordinary (non-gebra) test failing in the same run gates the same way; the
recommended shape below keeps verification in its own job so a red gate means a
finding.

Property-slug vocabulary is the plugin's own: an unknown slug in
`strict-properties`, `select` or `skip` is refused by the plugin itself before
anything runs (a pytest usage error — `outcome: error`), so the action and the plugin
can never disagree about which properties exist. The action refuses, before running
anything, the requests that cannot be meant: a mode outside the ladder,
`strict-properties` outside `strict` mode, and gebra flags smuggled into `tests` or
`pytest-args` (`outcome: refused`).

## The recommended rollout

Adopt the gate in three rungs, each a one-word `mode` change. The point of the ladder
is that findings become visible before they become blocking, so the gate never
arrives as a surprise red.

### 1. `report-only` — see the findings, block nothing

Run the gate with `mode: report-only`. Failing items leave the step green; the run
gets a warning annotation and the full `gebra` report lands in the step summary. Use
this rung to inventory where your workflow definitions stand before anything can
block a merge. Note what report-only does **not** forgive: an interrupted, erroring,
or empty run is still red, because a reporting rung that hides a broken run would
report nothing at all.

### 2. `gate` — FATAL- and ERROR-grade findings block

The default mode. An item fails when a FATAL- or ERROR-grade finding owned by that
property lands; WARNING-grade records are reported as advisory notes and do not gate.
This is the plugin's default severity contract — the same one `gebra verify` exits
on.

### 3. `strict` — promote warnings, per property first

`mode: strict` adds `--gebra-strict` to the run: WARNING-grade records become
failures — including the WARNING-graded structured witness notes a passing report can
carry (a note with no severity grade is never promoted). Promotion
changes the gate, never the record: a promoted finding still reads
`severity: warning` and its own claim class in the report. Start per-property —
`strict-properties: determinism-replay` is the canonical first promotion (P-08's
determinism heuristics, WARNING-grade by the frozen catalog) — and move to bare
strict (promote everything) once the noise floor of your runs is known.

A note on what strictness is about: a P-02 `termination-witness` result concerns
witness presence — never a statement that a run halts — and strict mode does not
change that; it changes only which records fail the step.

## The executed example — this repository's own DoD job

The `dod` job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs
the Phase-0 DoD scenario suites through the action on every push. This step is the
job's, verbatim (held equal to the workflow by
`tests/action/test_rollout_doc.py`):

```yaml
- name: Run the DoD scenario through the repository's own CI-gate action
  uses: ./.github/actions/gebra-gate
  with:
    tests: tests/dod tests/evolution
    pytest-args: "-q"
```

The job installs its pinned environment first (`pip install -e
".[dev,compat-cell-3]"`) — the action deliberately owns no installation — and stays
on the default `gate` mode: the scenario's own strict leg (the seeded defect promoted
under `--gebra-strict=determinism-replay`) runs as an inner pytest session inside the
suite, which is where a policy experiment belongs.

## Using it from another repository

The action lives in this repository, so a workflow elsewhere references it by path
and ref, in a job that sets up its own environment first:

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

Pin a commit SHA rather than `@main` when you need reproducibility. The two step
outputs are addressable the usual way (`steps.<id>.outputs.exit-code`,
`steps.<id>.outputs.outcome`) for follow-on steps that notify or label.

## What a green gate means

A green gebra item means the workflow definition satisfied the checked properties —
never more than that. The eight properties outside the Phase-0 wedge get no pytest
item; they are visible as structured not-implemented markers in the
`gebra_verification` fixture and in the closing report, never as green items. The
step summary's `gebra` section carries the per-property claim classes so a reader
sees not just what passed but what kind of claim each pass is.
