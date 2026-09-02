# Contributing to gebra

**New here? Start with the [contributor guide](docs/contributing/index.md)** — clone to first
merged change, in the order you meet each step: the CLA, how work is chosen and what makes a task
claimable, the vendored files you may not edit and the guard that enforces it, what to do when a
frozen document cannot be implemented as written, how a fixture changes, commit conventions, and
what each CI job refuses. This file is the mechanics reference it links into: exact commands,
exact configuration, and the procedures in full.

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

The pull-request template carries the reminder as its first checklist item, and the reviewer's
check against the record is computed rather than eyeballed — see
[The pre-merge checklist](#the-pre-merge-checklist-wa-08).

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
The [contributor guide](docs/contributing/index.md) walks that route — what the
corpus is, why a mismatch is a decision rather than an edit, and the four steps a
revision takes.

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

## Golden files and their justification (WA-05)

Three trees pin extracted IR bytes and digests as goldens: the extractor-conformance
set (`tests/extraction/golden/`), the drift-suite set (`tests/version_drift/golden/`)
and the IR golden vector + round-trip set (`tests/ir/golden/`). A golden there changes
only in a commit that carries its justification, and there are exactly two accepted
kinds (working agreement WA-05): a green-path matrix extension citing its drift-suite
run, or a ratified IR change with the `ir_version` bump and its decision record.

CI enforces this per commit (the `golden-guard` job): a commit whose diff touches one
of those trees must carry a `Golden-Justification:` trailer, in one of the two forms —

```
Golden-Justification: drift-run=<Actions run id> <substrate pair>
Golden-Justification: DEC-<n> ir_version=<x.y> <what changed>
```

A justified commit never covers an unjustified one in the same push, and there is no
bypass flag. The guard checks that the justification is present and well-formed;
whether the citation actually justifies the diff stays with review. Check a pending
change before pushing:

```bash
python tools/golden_guard.py --files <changed paths...> --message "<the commit message>"
```

The CLI, report and lineage goldens (`tests/cli/goldens/`, `tests/report/goldens/`,
`tests/lineage/golden/`) pin rendering rather than extracted IR and change under
ordinary review — no trailer needed. So does documentation *inside* a golden tree (a
`README.md`): the guard classifies only non-Markdown files, because WA-05 enumerates
golden files and no `.md` can become one. One squash-merge note: the squashed commit
message is what the guard judges on the main-branch push — keep the trailer in it.

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
- Coverage is measured with [coverage.py](https://coverage.readthedocs.io/);
  settings live in `[tool.coverage.*]`. CI holds `gebra.verify`, `gebra.testing`
  and the pytest plugin each **strictly above 80%**, and a scope below the floor
  fails the build. Run the gate yourself:

  ```bash
  uv run coverage run -m pytest -q   # not `pytest --cov` — see the doc for why
  uv run coverage json
  python tools/coverage_gate.py
  ```

  What the gate measures, why the measurement mode matters to the plugin scope,
  and the exemption policy for `# pragma: no cover` are in
  [docs/governance/coverage-gate.md](docs/governance/coverage-gate.md).
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
pip install -e ".[dev,compat-cell-1]" -c tools/matrix-constraints.txt   # langgraph 1.0.x line
pip install -e ".[dev,compat-cell-2]" -c tools/matrix-constraints.txt   # langgraph 1.1.x line
pip install -e ".[dev,compat-cell-3]" -c tools/matrix-constraints.txt   # langgraph 1.2.x line
pip install -e ".[dev,compat-test]" -c tools/matrix-constraints.txt     # = compat-cell-3
```

Then run the four gates as usual. The CI job takes the cell *number* and nothing
else, so `pyproject.toml` is the only place a cell's substrate is written down.

A few things about these pins are deliberate and easy to undo by accident:

- **They are exact, and they include transitives.** Cell 1 pins
  `langgraph-checkpoint==4.0.3` because a floated 4.1.x calls a langchain-core
  API that cell 1's core does not have, and `import langgraph.graph` then fails
  outright. No resolver prevents this: the declared metadata of every package
  involved is satisfied by the broken combination.
- **The `--pre` cell's substrate is unpinned and uncached on purpose.** It
  installs `--pre langgraph langchain-core` fresh on every run, which is the
  point: it reports what tomorrow's substrate would do. It never blocks a run — a
  failure is annotated and summarized instead, and opens a supported-range
  review. Its dev toolchain installs under the constraints below, so a red there
  attributes to the substrate.
- **The pins are frozen (F2, GOV-08, 2026-08-31).** The tested matrix froze
  citing green drift-suite run 33336160085; `pyproject.toml` says so at the
  extras themselves. From here the pins change only through a ceiling extension
  or cap — one commit citing its own drift-suite run. The procedure, the red
  path, and the 2.0 watch live in
  [docs/governance/VERSION-COMPAT-RUNBOOK.md](docs/governance/VERSION-COMPAT-RUNBOOK.md).
- **The rest of a cell's resolution comes from the lock.**
  `tools/matrix-constraints.txt` — generated from `uv.lock` by
  `python tools/matrix_constraints.py --write`, verified by `--check` in every
  cell — pins the dev toolchain for every pip-installing CI job, so a cell's
  greenness cannot drift with the day's index between substrate changes. It is
  agreement-gated: distributions the cells pin divergently are never constrained
  (the extras stay the substrate's single source of truth); family members every
  cell pins identically ride along at the agreed version. Refresh it in the same
  commit as any `uv.lock` change.

CI also runs on a weekly schedule and by `workflow_dispatch` (the VERSION-COMPAT
§4 watch): the matrix re-proves itself and the `--pre` cell reads that day's
index with the drift-issue automation live, whether or not anyone pushed.

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

## Specialist pre-review (WA-08)

Three areas of this repository are governed by a frozen document, and a change touching one
gets a **specialist pre-review against that document before the code owner's review** — so
that a factual disagreement with a frozen document reaches the maintainer as a citation
rather than as an opinion. The three are the intermediate representation and extraction
(`ir-contract`), the property catalog and its witnesses (`property-contract`), and the
never-invokes invariant (`never-invokes`).

Which of them a change owes is computed from the change, not remembered:

```bash
python tools/pre_review_routing.py --files $(git diff --name-only main...HEAD) --card EX-06
```

Two triggers, and a change owes any specialist either one names: the **paths** it touches
(globs over repository-relative paths, so `git diff --name-only` output pastes in unchanged)
and the **track** of the card it is written against, which is why an extractor card whose
diff lands entirely in tests still gets the reviews its board is about. One path rule is
computed rather than listed — a documentation page routes to `never-invokes` when it carries
an example CI executes, read off the page by `tools/docs_examples.py` itself. A pull-request
*label* is deliberately not a trigger: a label is set by the author of the change it would
constrain. `--check` turns the report into a hook's gate (exit 1 means a pre-review is owed)
and `--format json` prints the same routing as data.

**The note that comes back has a fixed shape**, and the same tool prints it, already filled
in with what routed the change and what the verdict is measured against:

```bash
python tools/pre_review_routing.py --files <paths...> --card EX-06 --comment ir-contract
```

The verdict comes first, in that specialist's own vocabulary — `APPROVE`,
`APPROVE-WITH-NOTES` (the two contract specialists only; an execution hazard is either absent
or it is the finding) or `BLOCK` — then what was read and what it was read against, then one
line per finding, then one routing line per finding. That last pairing is what keeps an
escalation from evaporating, and it is checked rather than trusted:

```bash
python tools/pre_review_routing.py --check-comment <the note>
```

That exits 1 on a template recorded unfilled, a verdict outside the specialist's vocabulary,
a `BLOCK` naming no finding, or a finding whose routing was never written down. It judges the
note's shape only; whether a finding is right is the reviewer's business and the maintainer's.

**A finding is routed one of two ways, and neither is settling it in the thread.** If it is
about the change, fix it — or, where the frozen document leaves the question open, record the
reading as an implementer's decision naming the passage that leaves it open, then re-run the
pre-review. If it is about the document, the passage cannot be implemented as written and
that is a spec defect: file it, the card goes on hold with the link, and work stops at the
boundary rather than picking a reading. The specialist has no authority to bless a deviation
from a frozen document and an author has none to overrule a citation of one; which of the two
kinds a finding is, when that is itself disputed, is the maintainer's call. A verdict is
advice — the maintainer merges either way, as above.

The [contributor guide](docs/contributing/index.md#the-specialist-pre-review) walks the same
flow with a worked example of both outputs.

## The pre-merge checklist (WA-08)

Three of the obligations a review owes before a merge are settled by a record this repository
already keeps, so the review reads the record rather than recalling the rule. One command reads
all three:

```bash
python tools/pr_checklist.py --author <handle> --base main --head HEAD
```

- **The CLA row** comes from
  [docs/governance/cla-signatures.md](docs/governance/cla-signatures.md). A row covers a
  contribution when its handle is the author's, its `CLA version` is the version `CLA.md`
  currently publishes, and its `Type` covers how the work is owned. A code owner needs no row,
  as the record itself says.
- **The golden-file justification** is `tools/golden_guard.py`'s verdict, taken per commit — the
  same call the `golden-guard` job makes, so this cannot pass a commit that job fails.
- **Release conformance** is `tools/release_gate.py`: with `--tag` it gates the tag before it
  exists, and without one it is the dry run CI's `build` job makes on every push, which is what
  catches an ordinary change that leaves the tree unable to release.

`--base`/`--head` judges each commit separately, as the golden guard does. Where there is no
range to walk, the git-free spelling takes the change pasted in:

```bash
python tools/pr_checklist.py --author <handle> \
    --files $(git diff --name-only main...HEAD) --message "$(git log -1 --format=%B)"
```

Add `--tag v0.0.1.dev1` when the change under review is the release cut itself, `--employer-owned`
when the work is owned by your employer (which is a different row in the record), and
`--format json` for the same report as data, each finding beside its own remediation. Exit 0
passes, 1 is a refusal, 2 means a check reached no verdict at all — which is not a pass, and
there is no bypass flag.

The maintainers' pre-merge review reaches these three verdicts by running this same command, so
neither side is working from its own copy of the rules — as with the honest-claims lint, the
command is the mechanical part of the check rather than the whole of it. A verdict is still about
the commits it was handed, so re-run it over the range under review rather than treating an
earlier local green as carrying forward.

Three things the command deliberately does not decide, and the reviewer still does: whether the
commits are conventional and carry their card ID, whether the board moved with the change, and
whether the prose claims only what the code does. The first two are the boards' own business and
the last is `tools/honest_claims_lint.py` plus the reading no substring search can do.

## Releases

Releases are cut by pushing a tag; the `release` workflow
(`.github/workflows/release.yml`) does everything else. There is no manual
assembly step anywhere: the tag *is* the procedure.

**The tag grammar** — three shapes, and nothing else passes the gate:

| Tag | Meaning | Publish leg |
|---|---|---|
| `vX.Y.Z.devN` | routine dev cut | skipped |
| `vX.Y.ZaN` / `vX.Y.ZbN` / `vX.Y.ZrcN` | pre-release / ship-decision candidate | skipped |
| `vX.Y.Z` | final release (the Phase-0 launch form) | runs — PyPI via trusted publishing |

The tag must equal `v` + `[project].version` from `pyproject.toml`, byte for
byte: the version is bumped by hand in the release commit and
`tools/release_gate.py` refuses a tag naming anything else. There is no
VCS-derived versioning. Because the three shapes are disjoint, a dev or rc wheel
can never be mistaken for a final release by its version string.

**Cutting a dev/rc release:**

1. Land the release commit through the normal review path: bump
   `[project].version` (say `0.0.1.dev1`) and make sure `CHANGELOG.md` carries
   what the cut should ship under `## [Unreleased]`. CI's `build` job runs the
   same gate in dry-run mode (plus `twine check --strict`) on every push, so a
   tree that is not release-ready is red before any tag exists.
2. Tag that commit on the repository the workflows run in
   (`Gebra-Tech/gebra`): `git tag v0.0.1.dev1 && git push origin v0.0.1.dev1`.
3. The `release` workflow gates the tag, builds wheel + sdist from it
   (`uv build`), validates metadata (`twine check --strict`), verifies the
   artifacts are exactly one wheel + one sdist named for exactly the gated
   version, re-checks the `py.typed` marker, installs the wheel into a clean
   environment and compares the installed version against the tag, extracts the
   changelog section as the run's release notes, and uploads everything to the
   run (90-day retention — run artifacts are working copies; the durable release
   surface is PyPI, at launch).
4. The `publish-pypi` job is skipped: the gate emits `publish=true` only for the
   bare `vX.Y.Z` form, which no Phase-0 tag carries.

**The launch release** is the owner's step (MANUAL-STEPS M14 in the delivery
repo): configure the PyPI trusted publisher — repository `Gebra-Tech/gebra`,
workflow `release.yml`, environment `pypi` — then push the final tag. Trusted
publishing is OIDC: the workflow's identity is verified per run, so no API token
or stored secret exists anywhere, and `tests/test_release_wiring.py` holds the
workflow file to that.

**Changelog discipline:** `CHANGELOG.md` is written by hand (Keep a Changelog);
the gate extracts, never generates. A final tag requires its dated
`## [X.Y.Z] - YYYY-MM-DD` section and refuses to release a version the changelog
does not record; dev/rc cuts ship the `## [Unreleased]` section as notes.

**Rehearsal:** the workflow also runs on `workflow_dispatch` as a
build-and-validate rehearsal that can never publish — the publish job requires
the triggering event to be the tag push itself — and the same checks run
locally:

```bash
python tools/release_gate.py --dry-run
uv build --out-dir dist
python tools/release_gate.py --dry-run --verify-dist dist
```
