"""The dedicated DoD CI job, held to PD-006 R5's shape — the house guardrail pattern.

R5 states the job verifiably: one dedicated CI job on a standard GitHub-hosted
``ubuntu-latest`` runner, on one designated blocking matrix cell (recorded by SD-09 in
PHASE-0-DOD-CHECKLIST §S1 as **py3.13 / cell 3** — the newest frozen pair, the substrate
line ``uv.lock`` tracks), whose total wall-clock is under 5:00. This module pins the
workflow to that ruling the way every other gate's guardrail test pins its job: the job
exists, it runs on the designated cell's pins, its timeout *is* the budget (a job that
cannot finish green over 5:00 makes "green" and "under budget" one observation), and its
one pytest invocation runs the scenario suite plus the R4 evolution sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

#: The designated blocking cell, exactly as PHASE-0-DOD-CHECKLIST §S1 records it.
DESIGNATED_CELL = "py3.13 / cell 3"


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


def test_the_dod_job_runs_the_scenario_and_the_evolution_sequence() -> None:
    """One pytest invocation carrying both halves R5 names for the job."""
    job = _dod_job()
    pytest_steps = [step for step in _run_steps(job) if step.startswith("pytest")]
    assert len(pytest_steps) == 1
    assert "tests/dod" in pytest_steps[0] and "tests/evolution" in pytest_steps[0]
