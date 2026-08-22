# Contributing to gebra

## Contributor License Agreement (CLA)

All contributions require a signed Contributor License Agreement with
**Gebra Tech, Inc.** before they can be merged. The agreement is [CLA.md](CLA.md);
its "How to sign" section is the procedure.

For now the process is **manual**: email
gebra.dev@gmail.com (or [@hesam-shams](https://github.com/hesam-shams) on
GitHub) with the signing statement before opening your first pull request, and
the maintainer records you in
[docs/governance/cla-signatures.md](docs/governance/cla-signatures.md). That
record is what reviewers check — no row, no merge. A CLA bot that checks pull
requests automatically is deferred to the 1.0 launch; when it lands it reads the
same record.

The pull-request template carries the reminder as its first checklist item.

## Development setup

`gebra` builds with [hatchling](https://hatch.pypa.io/latest/) (PEP 517/PEP 621)
and is managed with [uv](https://docs.astral.sh/uv/). `uv.lock` is committed and
pins the default development environment; use it.

```bash
git clone https://github.com/Gebra-Tech/gebra.git
cd gebra
uv sync --extra dev     # creates .venv exactly as the lockfile pins it
uv run pytest
uv run ruff check .
```

`uv sync --frozen` (what CI runs) refuses to update the lockfile, so a stale
lock fails the job instead of silently re-resolving. `uv lock --check` reports
whether the lock is still consistent with `pyproject.toml`.

**Changing dependencies.** Edit the `[project]` tables in `pyproject.toml`, run
`uv lock`, and commit the refreshed `uv.lock` in the same commit as the
declaration change — a lockfile refresh is an ordinary reviewed change, not a
side effect. The lockfile covers the *default* development environment only:
per-cell compatibility-matrix pins belong to the `compat-test` / `compat-cell-N`
extras (see [Compatibility matrix](#compatibility-matrix)) and never enter the
lock.

**Without uv.** The pip path stays supported and is checked in CI:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

**Building distributions.** `uv build` produces the wheel and sdist through
hatchling into `dist/`. There is no `setup.py`, `setup.cfg`, or `MANIFEST.in`,
and no `*.egg-info` directory should ever appear in the tree — if one does, an
old setuptools-based build ran; delete it.

## Commit messages

This repository uses [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:` — with an
optional scope, e.g. `feat(ir): add SendEdge model`.

## Fixture corpus and other vendored files

`tests/fixtures/properties/` is the acceptance fixture corpus — a byte-copy
snapshot of the specification vault, and a shared contract surface treated as
read-only. Fixture additions or revisions route through the maintainer's review
process (a validator/fixture mismatch is a logged decision, never a quiet edit).
Development-process documentation for regular contributors is maintained
separately; contact the maintainer.

A CI job enforces this rather than leaving it to review. Run it yourself:

```bash
python tools/provenance_guard.py     # no dependencies, no install needed
```

It hashes every vendored file and compares it with
`tools/provenance-manifest.json`, failing on an edited file, a deleted one, or a
file added to the corpus by hand. There is no bypass flag: a sanctioned
re-vendor updates the bytes *and* regenerates the manifest in one commit. The
procedure — and what to do when the guard fails on your branch — is
[docs/governance/re-vendoring.md](docs/governance/re-vendoring.md).

## Code style and quality gates

Four gates run in CI on every push and pull request. Run them locally before
pushing — each reads its configuration from `pyproject.toml`, so a local run and
the CI job check the same thing:

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (drop --check to apply)
uv run mypy                    # strict type check over src/ and tests/
uv run pytest                  # test suite
```

- [ruff](https://docs.astral.sh/ruff/) is the linter and formatter (line length
  100, target Python 3.10). The vendored fixture corpus is excluded from both.
- [mypy](https://mypy.readthedocs.io/) runs in `strict` mode over `src/`,
  `tests/` **and** `tools/`, targeting the declared Python floor (3.10). Type annotations
  everywhere; the package ships a `py.typed` marker. A per-module relaxation in
  `[[tool.mypy.overrides]]` needs a comment saying why it is a fact about the
  environment rather than an exemption.
- Coverage is measured with [coverage.py](https://coverage.readthedocs.io/) via
  `pytest-cov`; settings live in `[tool.coverage.*]`. Run it with
  `uv run pytest --cov`. No minimum is enforced yet — the coverage threshold
  lands with the harness work.
- `.editorconfig` carries the whitespace conventions (UTF-8, LF, final newline,
  4-space Python at 100 columns) and deliberately leaves the vendored fixture
  corpus untouched.
- Tests accompany every change; nothing in the test suite may execute a
  workflow, call an LLM, or open a network connection.

## Compatibility matrix

The four gates above run in the default (locked) environment *and* on a
compatibility matrix of **13 cells**: Python 3.10, 3.11, 3.12 and 3.13 across
three pinned langgraph/langchain-core pairings — twelve blocking cells — plus one
non-blocking `--pre` early-warning cell on 3.13.

The pairings are the compatibility *promise*; the version ranges in
`[project.dependencies]` are only the installability envelope. Each pairing's
exact pins — including transitively resolved ones such as pydantic — live in an
extra, so a CI cell and a local reproduction install the same substrate:

```bash
pip install -e ".[dev,compat-cell-1]"   # langgraph 1.0.x line
pip install -e ".[dev,compat-cell-2]"   # langgraph 1.1.x line
pip install -e ".[dev,compat-cell-3]"   # langgraph 1.2.x line
pip install -e ".[dev,compat-test]"     # the same pins as compat-cell-3
```

Then run the four gates as usual. The CI job takes the cell *number* and nothing
else, so `pyproject.toml` is the only place a cell's substrate is written down.

A few things about these pins are deliberate and easy to undo by accident:

- **They are exact, and they include transitives.** Cell 1 pins
  `langgraph-checkpoint==4.0.3` because a floated 4.1.x calls a langchain-core
  API that cell 1's core does not have, and `import langgraph.graph` then fails
  outright. No resolver prevents this: the declared metadata of every package
  involved is satisfied by the broken combination.
- **The `--pre` cell is unpinned and uncached on purpose.** It installs
  `--pre langgraph langchain-core` fresh on every run, which is the point: it
  reports what tomorrow's substrate would do. It never blocks a run — a failure
  is annotated and summarized instead, and opens a supported-range review.
- **The pins are candidate values, not frozen ones.** They re-resolve when the
  tested matrix is frozen and at each ceiling extension; `pyproject.toml` says so
  at the extras themselves.

`tests/test_compat_matrix.py` holds the workflow and the extras to each other —
the cell count, the pin values, and which gates each cell runs.

### Drift suite

`tests/version_drift/` is the substrate drift-detection suite — the full twelve-test
VERSION-COMPAT §3 inventory: each test builds a minimal live workflow, drives it
through `gebra.extract()`, and holds the core IR byte-identical (and its
`graph_version` string-equal) to a committed golden under
`tests/version_drift/golden/`, beside direct shape assertions on the substrate
surfaces extraction reads (three tests carry a second, document-shaped golden:
the xray drawing, the jsonschema getters' named keys, the drawn LCEL topology).
It runs wherever `pytest` runs, so every matrix cell above exercises it against
its own pinned substrate. A *hard* mismatch fails the cell; a *soft* divergence —
a substrate surface gaining or losing a member (or a rendered schema document
moving) against the recorded per-line inventory in
`tests/version_drift/inventory.py` — keeps the cell green and is emitted as a
warning annotation at the end of the run. Three rows carry special semantics:
the DeltaChannel beta variant is `xfail(strict=False)` everywhere (beta never
blocks a cell), and the drawable-fidelity and `config_schema` tests **block and
route** — their designated failure branches record a templated review proposal
(`tests/version_drift/review.py`: a terminal-summary section, a stable
`DRIFT-REVIEW-PROPOSAL` line, a CI annotation, plus a file drop when
`GEBRA_DRIFT_REVIEW_DIR` is set) before the cell goes red, naming the
VERSION-COMPAT §5 R-06 governance route the follow-up takes. Goldens and
recorded inventories change only with a stated justification (see
`tests/version_drift/golden/README.md`); regenerate goldens with
`python tools/drift_goldens.py --write`.

The failure handling is wired end to end in CI (VERSION-COMPAT §3). Every
matrix cell writes a machine-readable drift report at the end of its pytest
run (the conftest, when `GEBRA_DRIFT_REPORT_FILE` is set; the cell identity
rides in `GEBRA_DRIFT_CELL`) and uploads it; after the matrix, the
`drift-issues` job feeds every report to `tools/drift_issues.py`, which opens
or updates at most one *version-gap* issue per frozen substrate cell — a hard
failure blocks its cell and lands in the issue, a soft-only divergence keeps
its cell green and still lands in the issue — and routes the `--pre` cell's
signals, or a red `--pre` pytest gate, to a *supported-range-review* issue
instead. Dedup rides a fingerprint marker in the issue body: unchanged signals
add nothing on later runs, changed signals land as comments, and an automation
failure turns the `drift-issues` job red rather than passing silently. The
whole chain reproduces locally without touching GitHub: run the suite with the
variables set, then `python tools/drift_issues.py --reports <dir>` — a dry run
prints every payload it would send (`--apply` is CI's). The owner-triggered
`drift-issue-drill` workflow demonstrates the live path on demand: it flips
one golden byte in the runner's checkout, watches the suite go red, and opens
real `[drill]`-labeled issues that are safe to close. The `--pre` cell's
non-pytest gates (resolve/ruff/mypy) stay annotation-and-summary only, as the
matrix wired them.
