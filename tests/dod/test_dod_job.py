"""The dedicated DoD CI job, held to PD-006 R5's shape — the house guardrail pattern.

R5 states the job verifiably: one dedicated CI job on a standard GitHub-hosted
``ubuntu-latest`` runner, on one designated blocking matrix cell (recorded by SD-09 in
PHASE-0-DOD-CHECKLIST §S1 as **py3.13 / cell 3** — the newest frozen pair, the substrate
line ``uv.lock`` tracks), whose total wall-clock is under 5:00. This module pins the
workflow to that ruling the way every other gate's guardrail test pins its job: the job
exists, it runs on the designated cell's pins, its timeout *is* the budget (a job that
cannot finish green over 5:00 makes "green" and "under budget" one observation), and its
one pytest invocation runs the scenario suite plus the R4 evolution sequence.

Since TE-13 that one invocation is issued through the repository's own CI-gate action
(the card's consumer-proof box: the action runs the plugin gate on this repo's own DoD
workflow), so the invocation pin follows the indirection rather than weakening: the job
carries exactly one local `uses:` of the action, zero direct pytest steps beside it,
and the action's inputs spell the same command as before — the driver builds exactly
one pytest invocation from them, held by ``tests/action/test_gate_driver.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

#: The designated blocking cell, exactly as PHASE-0-DOD-CHECKLIST §S1 records it.
DESIGNATED_CELL = "py3.13 / cell 3"

#: The local reference to TE-13's CI-gate action — how the job issues its invocation.
GATE_ACTION = "./.github/actions/gebra-gate"


def _dod_job() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "dod" in workflow["jobs"], "the DoD scenario needs its dedicated CI job"
    job: dict[str, Any] = workflow["jobs"]["dod"]
    return job


def _run_steps(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if isinstance(step.get("run"), str)]


def test_the_dod_job_is_dedicated_and_budgeted() -> None:
    """R5's clock, enforced in the workflow itself: ubuntu-latest, timeout-minutes 5."""
    job = _dod_job()
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 5
    assert job["name"] == f"DoD scenario ({DESIGNATED_CELL})"


def test_the_dod_job_runs_on_the_designated_cell() -> None:
    """The §S1-recorded cell: Python 3.13 with the ``compat-cell-3`` frozen pins."""
    job = _dod_job()
    setups = [
        step["with"]
        for step in job["steps"]
        if isinstance(step.get("uses"), str) and "setup-python" in step["uses"]
    ]
    assert len(setups) == 1 and setups[0]["python-version"] == "3.13"
    assert any(".[dev,compat-cell-3]" in step for step in _run_steps(job))


def test_the_dod_job_runs_the_scenario_through_the_gate_action() -> None:
    """One invocation carrying both halves R5 names — issued by the TE-13 gate action.

    No direct pytest step remains, exactly one gate step exists, and its inputs spell
    the pre-TE-13 command (`tests/dod tests/evolution` under `-q`). The outer run stays
    on the default `gate` severity policy: R2's defect-3 strict leg is an inner pytest
    session inside the suite, never the whole job's gate.
    """
    job = _dod_job()
    assert not [step for step in _run_steps(job) if "pytest" in step]
    gate_steps = [step for step in job["steps"] if step.get("uses") == GATE_ACTION]
    assert len(gate_steps) == 1
    configured = gate_steps[0]["with"]
    assert configured["tests"] == "tests/dod tests/evolution"
    assert configured["pytest-args"] == "-q"
    assert configured.get("mode", "gate") == "gate"
