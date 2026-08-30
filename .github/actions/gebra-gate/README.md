# gebra verification gate — the reusable CI-gate action

A composite action wrapping the gebra pytest plugin as a CI gate: one pytest run,
the `report-only` → `gate` → `strict` rollout ladder as a one-word `mode` switch, the
run's closing `gebra` report appended to the step summary, and two step outputs
(`exit-code`, `outcome`). The plugin extracts and verifies workflow definitions and
never executes them.

The interface contract, the exit-code translation, the recommended rollout, and the
executed in-repo example — this repository's own DoD scenario job issues its pytest
invocation through this action on every push — are documented in
[docs/ci/github-action.md](../../../docs/ci/github-action.md). The driver is
[`gate.py`](gate.py); `tests/action/` holds the action to its documented shape.
