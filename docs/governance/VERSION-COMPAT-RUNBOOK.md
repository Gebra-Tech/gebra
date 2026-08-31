# VERSION-COMPAT runbook — ceiling extensions, caps, and the 2.0 watch

Post-phase operations for the frozen tested matrix (freeze event F2, card GOV-08,
2026-08-31). This is a procedure document for whoever maintains the compatibility
surface; the *policy* lives in the living document `VERSION-COMPAT.md` (§4 pinning &
release policy, §5 update discipline — kept in the supplementary repo beside the plan),
and where the two ever disagree, the living document wins and this file gets fixed.

## The frozen posture — where every pin lives

The tested matrix is Python 3.10–3.13 × three langgraph/langchain-core pair cells
(12 blocking CI cells) plus one non-blocking `--pre` early-warning cell. Frozen at F2
citing green drift-suite CI run 33336160085 (2026-08-30). Four files carry it:

| File | What it pins |
|---|---|
| `pyproject.toml` — `compat-cell-{1,2,3}` / `compat-test` extras | The substrate family per cell, exact, transitives included (the FROZEN marker cites the freeze run) |
| `tools/matrix-constraints.txt` | The dev toolchain and other lock-resolved dependencies, for every pip-installing CI job — generated from `uv.lock` by `tools/matrix_constraints.py`, agreement-gated (divergently pinned family members are never constrained) |
| `uv.lock` | The locked default environment the constraints derive from |
| `.github/workflows/ci.yml` | The 13 cells, the gates each runs, the drift-report seam, the `drift-issues` automation, the `golden-guard` job, and the watch triggers |

Between substrate changes, nothing in a cell's resolution follows the day's index — the
two G6-window drift events (a hypothesis profile change, typer 0.27.2) came through
fresh floors, and the constraints file is the closure. Two deliberate exceptions stay
fresh: the `--pre` cell's substrate resolve step (it exists to see today's index) and
the build job's clean-venv wheel smoke (a user-shaped install is its point). One
freeze-shape fact worth knowing at triage: the constraints carry the lock's versions,
which can sit slightly behind what the cited run's fresh resolution produced on its day
(langsmith, for example) — the weekly watch run re-proves the constrained environment,
so any such gap surfaces there rather than at a release.

## The watch — how runs keep happening after the phase

CI runs on every push and pull request, **and**:

- **weekly, on a schedule** (`cron: "23 6 * * 1"`, Mondays 06:23 UTC) — the full run:
  the 12 frozen cells re-prove themselves, the `--pre` cell resolves that day's newest
  (pre)release substrate, every cell writes its drift report, and the `drift-issues`
  job opens or updates version-gap / range-review issues from them;
- **on demand** (`workflow_dispatch`) — Actions → CI → *Run workflow*. This is the
  "immediate `--pre` run" VERSION-COMPAT §4 names for the day a 2.0 alpha appears.

Two operational caveats, both GitHub-side:

- GitHub disables scheduled workflows in a repository after ~60 days without repository
  activity, with a warning email first. If the watch email arrives (or the weekly runs
  stop appearing), re-enable the workflow from the Actions tab — the runbook cadence
  depends on it.
- Issue automation writes with the run's own `GITHUB_TOKEN` (`issues: write` on the
  `drift-issues` job only). On a fork pull request that token is read-only; the job
  goes red rather than opening the issue — loud, never silent (recorded at GOV-07).

One watch-scope trade, taken at GOV-08 so a red `--pre` cell attributes to the
substrate: with the cell's dev half installed under the constraints, a prerelease
*transitive* arriving under stable named packages (the PD-030 §C4 mode — pydantic
2.14.0a1, 2026-08-04) reaches the cell only when a named-package upgrade pulls it.

## Triage — reading a watch run

Open the run summary. Each cell's section lists its resolved substrate; the `--pre`
cell's section additionally reports every gate outcome.

- **All green, `--pre` resolved pair == cell 3's pair:** nothing to do.
- **All green, `--pre` resolved a newer stable pair:** the tested ceiling is behind the
  index — a ceiling-extension candidate. Follow the green path below at your cadence
  (upstream ships weekly–biweekly; batching a few patches into one extension is fine).
- **A `version-gap/cell-N` issue opened or updated:** a frozen cell drifted. Hard
  failure = the cell is red and release-blocking; soft-only divergence = the cell is
  green with an annotation. Either way the issue body quotes the stable `DRIFT-*` lines
  and carries the §3/§4 routing checklist — work it, never close it silently.
- **A `range-review/pre` issue:** the `--pre` cell hit drift signals or a red pytest
  gate. That is the early warning doing its job; route per the 2.0-watch section below
  if the cause is a 2.0 prerelease, otherwise treat as advance notice for the next
  stable pair.

## Ceiling extension — the green path (VERSION-COMPAT §4)

When upstream ships a new substrate release you want inside the tested matrix:

1. **Resolve the candidate pins by the §3 rule:** the latest non-yanked patch of the
   cell's named langgraph line, plus the latest non-yanked langchain-core patch
   satisfying both that langgraph's own core pin and the cell's named core band —
   transitives included (pydantic among them). Family transitives follow PD-030 item 5:
   the latest non-yanked version that both resolves against the cell's named pair *and*
   passes the import + §2-surface probe — which may be a Gebra-chosen bound rather than
   the resolver's float (cell 1's `langgraph-checkpoint==4.0.3`, PD-030 Q1, exists
   because the float dies at import). Yanked releases never enter the matrix.
2. **Run the drift suite against the candidate before changing anything.** Locally:

   ```bash
   python -m venv /tmp/candidate
   /tmp/candidate/bin/pip install -e ".[dev]" -c tools/matrix-constraints.txt \
       "langgraph==<X>" "langchain-core==<Y>"   # + the family pins the resolver names
   /tmp/candidate/bin/python -m pytest tests/version_drift/ -q   # then the full gates
   ```

   Or push a branch that bumps the candidate cell's extra — the pull request runs the
   full 13-cell matrix on it, which is the justifying run you will cite.
3. **Green → one extension change, containing all of:**
   - the bumped `compat-cell-N` (and `compat-test`, if cell 3 moved) pins in
     `pyproject.toml`;
   - if cell 3 or any locked dependency moved: `uv lock` refresh **and**
     `python tools/matrix_constraints.py --write` in the same commit (the staleness
     test is red otherwise);
   - a CHANGELOG entry citing the drift-suite run ID + substrate pair;
   - the living-document edit (supplementary repo): the §1/§4 ceiling line moves, in
     exactly one commit citing the same run ID + pair, with
     `python3 tools/provenance_guard.py --provenance-doc docs/PROVENANCE.md --regenerate`
     run in that commit (PD-035 mechanics).
4. **Goldens stay byte-identical.** The drift goldens hold on every cell by
   construction (the suite's composition rule); a new cell that moves a golden is not
   an extension — it is drift, and it routes down the red path instead. Never edit a
   golden to make an extension green.

## Cap — the red path (VERSION-COMPAT §4)

When the drift suite is red against a new substrate release (or a frozen cell starts
failing after an upstream yank/republish):

1. The version-gap issue is already open (the automation opened it from the reports);
   if the red came from a local candidate run, open it by running
   `python tools/drift_issues.py --reports <dir>` against the run's reports.
2. **Cap the tested ceiling at the last green pair** — the extras simply do not move;
   record the cap + the issue link in the CHANGELOG, and land the cap as a living-doc
   commit citing the red run (§5 discipline, same regenerate mechanics as above).
3. No assertion is downgraded on either path. An assertion downgrade (for example
   demoting the drawable cross-check) routes through §5 R-06 governance — never a
   repo-only edit.

## The 2.0 watch (VERSION-COMPAT §4)

`<2.0.0` is the vendor's only structural guarantee for the surfaces extraction reads;
majors ship "6–12 months" apart. When a 2.0 alpha appears on PyPI:

1. **Dispatch an immediate run** (Actions → CI → *Run workflow*). The `--pre` cell
   resolves the alpha (`--pre` is a global resolver flag — prerelease transitives ride
   in too) and runs the full gate set non-blocking.
2. The resulting signals — including drift test 8's `config_schema`-removal branch,
   which is the designed 2.0-ceiling tripwire — route to a `range-review/pre` issue
   automatically.
3. **A supported-range review is R-06 vault governance, not a repo edit** (§5): the
   ceiling question (stay `<2.0.0`, cap harder, or begin a 2.0 line) is ruled
   vault-first; the living document records the ruling afterwards, citing it. The same
   applies to any floor move.

## Golden lifecycle at any of the above (WA-05)

A golden under `tests/extraction/golden/`, `tests/version_drift/golden/` or
`tests/ir/golden/` changes only in a commit whose message carries a well-formed
`Golden-Justification:` trailer — `drift-run=<run id> …` (matrix extension) or
`DEC-<n> ir_version=<x.y> …` (ratified IR change). The `golden-guard` CI job enforces
presence and form per commit; regenerate drift goldens only via
`python tools/drift_goldens.py --write`, and check a pending change locally with
`python tools/golden_guard.py --files <paths> --message "<message>"`. Forms and details:
CONTRIBUTING.md, "Golden files and their justification".

## Pin-lock maintenance

Dev-toolchain upgrades are deliberate events, not ambient drift: refresh `uv.lock`
(`uv lock` / `uv lock --upgrade-package <name>`), run
`python tools/matrix_constraints.py --write`, and land both in one commit — the
`--check` test in every cell refuses a skew. The substrate family never moves this way;
it moves only through the extension/cap paths above, extras-first.
