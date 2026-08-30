# The coverage gate

CI holds three surfaces above 80% test coverage, each measured on its own:

| scope | what it is | mandate |
|---|---|---|
| `gebra.verify` | the property validators, the result envelope, the registry | brief D-09, Deliverable 6 and its Definition of Done |
| `gebra.testing` | the fixture loader, the golden harness, strategies, mutations | brief D-10, Deliverable 8 and its Definition of Done |
| `gebra.pytest_plugin` | the pytest plugin — the `pytest11` entry point | brief D-10, Deliverable 8 and its Definition of Done |

SOW §2 carries both briefs' clauses as one supporting acceptance fact: "harness/plugin
test coverage exceeds 80%". The floor is therefore **strictly greater than 80.0%** —
a scope sitting at exactly 80.00% fails.

The gate is `tools/coverage_gate.py`, run by the `test-locked` job in
`.github/workflows/ci.yml` after the suite. It has no bypass flag and no threshold
option: the floor comes from frozen briefs, so lowering it is a specification question,
not a command-line one.

## Running it yourself

```bash
uv run coverage run -m pytest -q     # measure (see "Why not pytest --cov" below)
uv run coverage report               # the human table, per file
uv run coverage xml                  # the artifact CI keeps for external tools
uv run coverage json                 # the report the gate reads
python tools/coverage_gate.py        # the gate — no dependencies beyond the stdlib
```

Those are the five commands the `test-locked` job runs, in that order. `coverage` comes
with the `dev` extra (via `pytest-cov`); the gate itself imports nothing but the standard
library, so it also runs against a report produced elsewhere:

```bash
python tools/coverage_gate.py --report path/to/coverage.json --root path/to/checkout
```

A passing run prints one line per scope, then the project total and the exemption count as
context. This is the real output of the full suite on 2026-08-30:

```
coverage gate: OK — every gated scope above 80%

  ok   gebra.verify          99.72%   statements 1941/1944, branches 560/564, 16 file(s)
  ok   gebra.testing         97.95%   statements 1223/1242, branches 256/268, 5 file(s)
  ok   gebra.pytest_plugin   93.91%   statements 615/640, branches 187/214, 1 file(s)

  context (not gated): whole package  98.01% over 105 file(s); 19 exemption(s) read in 22 gated source file(s)
```

Exit status: `0` when every gated scope is above the floor and every exemption carries
its reason; `1` when one is not — the failing scopes are named with their mandate; `2`
when no verdict was reached at all (report missing, unreadable, measured without branch
coverage, mis-measured, or a scope that matched no measured file). A run the gate cannot
score is never reported as a pass.

## Why three scopes rather than one project total

A single number over the whole package can sit comfortably above the floor while one of
the three named surfaces rots underneath it — which is the regression the gate exists to
block. Each scope is aggregated over its own files and compared on its own; the project
total is printed for context and gates nothing.

That is also why `[tool.coverage.report]` carries no `fail_under`: it is one number over
everything measured, and it compares with `>=` rather than the briefs' `>`.

## What the percentage counts

`[tool.coverage.run] branch = true`, so the gated number is coverage.py's own combined
ratio — executed statements *and* taken branch arcs over the total of both. It is the
number `coverage report` prints in its `Cover` column, so the gate and a local report
agree by construction. The per-scope line breaks the two components out, because *where*
a scope is thin is usually the useful part.

## Why not `pytest --cov`

`gebra.pytest_plugin` is a `pytest11` entry point: pytest imports it while loading
plugins, which happens **before** `pytest-cov` starts measuring. Its module-level
statements — imports, `def` lines, decorators, constants — have therefore already run by
the time measurement begins, and coverage records every one of them as never executed. On
this repository that is exactly 161 statements. Measured both ways over the plugin's own
suite (`tests/plugin`) on 2026-08-30, the scope reads 70.02% under `pytest --cov` and 88.88%
under `coverage run -m pytest`, with identical branch numbers — 161 statements out of 854
measured units, so 18.9 points of measurement artifact rather than untested code. (The
sample output above is higher again, 93.91%: it is the whole suite, which reaches the plugin
through the DoD and CI-gate-action suites as well.)

`coverage run -m pytest` starts measurement before pytest imports anything, so the plugin
module's body is measured like any other. The gate detects the other mode rather than
scoring it: if the plugin's first statement reads as never executed, it exits `2` with the
correct command in the message. Neither a red the gate cannot justify nor a green it got
by luck.

Child pytest sessions that tests spawn as subprocesses are outside the measurement either
way — `coverage run` measures the process it starts. In-process sessions (pytest's
`pytester` fixture, which the plugin's tests use) are measured normally.

## Exemption policy

There are exactly two ways for a line inside a gated scope not to count, and no third.

**Structural exclusions** live in one reviewed place, `[tool.coverage.report]
exclude_also` in `pyproject.toml`:

```toml
exclude_also = [
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@(typing\\.)?overload",
]
```

These are rules about code that cannot run in a test process, not waivers for particular
lines. Adding one is a reviewed change to a file everybody reads.

**Per-line exclusions** — `# pragma: no cover` — are allowed **only with a stated reason
on the same line**:

```python
if step is None:  # pragma: no cover — unreachable: the component is non-trivial
except ImportError:  # pragma: no cover - PyYAML is a declared dev dependency
```

A bare `# pragma: no cover` is a silent hole in the floor, so the gate rejects it and
names the line — the same discipline the honest-claims lint applies to its allow-pragma.
Any of `-`, `–`, `—` or `:` may introduce the reason, or nothing at all; what the policy
requires is that a *human wrote why* the line cannot be exercised. A remainder that just
starts another comment (`# pragma: no cover  # noqa: E501`) is a machine directive, not a
reason, and counts as bare — though a reason followed by one is fine.

The pragma is recognised by coverage.py's own pattern rather than by the one spelling
above, so every form coverage.py honours needs a reason: `# pragma:no cover`,
`# PRAGMA: NO COVER`, `# pragma  no cover`. A test holds the gate's copy of that pattern
equal to the installed coverage.py's default, in both directions — a spelling coverage.py
does *not* exclude (mixed case, e.g. `# Pragma: no COVER`) is not policed here either,
because it is not an exemption.

There is no file-level waiver, no scope-level waiver, no threshold flag, and no
environment variable that turns the gate off.

The reason-required rule is enforced over the gated scopes — the surfaces this gate is
answerable for. The rest of `src/` follows the same convention by hand; extending the rule
to code the gate does not measure would be a policy this card was not asked to set.

## What a green gate means, and what it does not

It means: on the locked development environment, the suite executed more than 80% of the
statements and branch arcs in each of the three scopes, and every excluded line says why
it is excluded.

It does not mean the covered lines are correct, that the uncovered ones are unimportant,
or anything at all about a workflow's runtime behaviour — gebra analyses serialized IR and
executes nothing. Coverage is a floor under the test suite's reach, not a statement about
the code's behaviour.

## Recorded state

Observed on 2026-08-30, on the locked development environment (Python 3.13, the whole
suite — 9042 passed, 35 skipped — under `coverage run -m pytest`): the three scopes stand
at 99.72%, 97.95% and 93.91%, and all nineteen exemptions in them carry a reason. CI
prints the current numbers on every push and keeps the run's `coverage.xml` and
`coverage.json` as the `coverage-reports` artifact.
