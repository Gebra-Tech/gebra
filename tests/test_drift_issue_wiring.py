"""The CI wiring of the version-gap machinery (GOV-07) — read-only YAML pins.

VERSION-COMPAT §3's issue clauses hold only if three files stay in lockstep: the drift
suite's emitters (``tests/version_drift/conftest.py`` and friends), the workflow that
carries each cell's report to the aggregation job (``.github/workflows/ci.yml``), and
the tool that opens the issues (``tools/drift_issues.py``). These tests hold the wiring
together the way ``test_compat_matrix.py`` holds the matrix together: every cell writes
and uploads its report, the ``--pre`` cell's pytest outcome rides in its artifact, the
``drift-issues`` job runs on red and green runs alike under exactly the ``issues: write``
permission it needs, and the drill workflow — the owner-triggered live demonstration —
can only ever be dispatched by hand and only ever opens ``--drill``-scoped issues.

Read-only: YAML parsing plus imports of the seam modules for their constants. Nothing
here installs, executes a workflow, opens a socket, or invokes anything (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.version_drift import conftest as drift_conftest
from tests.version_drift import review
from tools import drift_issues

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DRILL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "drift-issue-drill.yml"

pytestmark = pytest.mark.skipif(
    not CI_WORKFLOW.is_file(),
    reason="wiring tests describe the source tree; no workflow beside tests/",
)


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def drill() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(DRILL_WORKFLOW.read_text(encoding="utf-8"))
    return data


def _uploads(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


# ── Every cell writes and uploads its report ─────────────────────────────────────────────


@pytest.mark.parametrize("job_name", ["test-matrix", "test-matrix-pre"])
def test_every_cell_announces_the_report_through_the_seam_variables(
    workflow: dict[str, Any], job_name: str
) -> None:
    """The env-var *names* come from the conftest/review modules and the *values* must
    match what the upload step and the tool expect — three files, one contract."""
    env = workflow["jobs"][job_name]["env"]

    assert env[drift_conftest.REPORT_FILE_VARIABLE] == drift_issues.REPORT_FILE_NAME
    assert env[review.REVIEW_DIR_VARIABLE] == drift_issues.REVIEW_DIR_NAME
    expected_cell = "${{ matrix.cell }}" if job_name == "test-matrix" else drift_issues.PRE_CELL
    assert env[drift_conftest.CELL_VARIABLE] == expected_cell


@pytest.mark.parametrize("job_name", ["test-matrix", "test-matrix-pre"])
def test_every_cell_uploads_its_report_even_when_red(
    workflow: dict[str, Any], job_name: str
) -> None:
    """A report from a red cell is the whole point; a green cell's context-only report
    is what lets the aggregation tell "clean" from "missing"."""
    [upload] = _uploads(workflow["jobs"][job_name])

    assert upload.get("if") == "always()"
    assert str(upload["with"]["name"]).startswith("drift-report-")
    paths = str(upload["with"]["path"]).split()
    assert drift_issues.REPORT_FILE_NAME in paths
    assert f"{drift_issues.REVIEW_DIR_NAME}/" in paths
    assert upload["with"]["if-no-files-found"] == "error", (
        "a cell whose pytest produced no report must fail its upload loudly — "
        "'report missing' is never a warning nobody reads"
    )


def test_the_frozen_cell_list_is_lockstep_with_the_matrix(workflow: dict[str, Any]) -> None:
    """A cell added to (or renamed in) the matrix must surface here at test time, not
    as a runtime DriftIssueError on the next CI run."""
    matrix = workflow["jobs"]["test-matrix"]["strategy"]["matrix"]

    assert tuple(matrix["cell"]) == drift_issues.FROZEN_CELLS


def test_the_twelve_cell_artifacts_cannot_collide(workflow: dict[str, Any]) -> None:
    """The artifact name carries both matrix axes — twelve cells, twelve artifacts."""
    [upload] = _uploads(workflow["jobs"]["test-matrix"])
    name = str(upload["with"]["name"])

    assert "${{ matrix.python-version }}" in name
    assert "${{ matrix.cell }}" in name


def test_the_report_upload_does_not_soften_a_blocking_cell(workflow: dict[str, Any]) -> None:
    """`if: always()` is not `continue-on-error`: the twelve cells stay blocking."""
    [upload] = _uploads(workflow["jobs"]["test-matrix"])

    assert "continue-on-error" not in upload


def test_the_pre_cell_records_its_pytest_outcome_in_the_artifact(
    workflow: dict[str, Any],
) -> None:
    """Job outputs from a failed job are not gambled on: the outcome rides in the
    artifact file the tool reads (`pre-outcome.txt`)."""
    job = workflow["jobs"]["test-matrix-pre"]
    recorders = [
        step for step in job["steps"] if drift_issues.PRE_OUTCOME_FILE_NAME in step.get("run", "")
    ]

    [recorder] = recorders
    assert recorder.get("if") == "always()"
    assert "steps.test.outcome" in "\n".join(str(value) for value in recorder["env"].values())
    [upload] = _uploads(job)
    assert drift_issues.PRE_OUTCOME_FILE_NAME in str(upload["with"]["path"]).split()


# ── The aggregation job: one consumer, correctly gated ───────────────────────────────────


def test_the_drift_issues_job_runs_after_the_whole_matrix_green_or_red(
    workflow: dict[str, Any],
) -> None:
    """Soft divergences leave cells green by design, so the job cannot be gated on
    failure; hard failures leave them red, so it cannot be gated on success. It skips
    only cancelled runs."""
    job = workflow["jobs"]["drift-issues"]

    assert set(job["needs"]) == {"test-matrix", "test-matrix-pre"}
    assert job["if"] == "${{ !cancelled() }}"


def test_the_drift_issues_job_holds_exactly_the_permission_it_needs(
    workflow: dict[str, Any],
) -> None:
    assert workflow["jobs"]["drift-issues"]["permissions"] == {
        "contents": "read",
        "issues": "write",
    }


def test_the_drift_issues_job_downloads_every_report_and_applies(
    workflow: dict[str, Any],
) -> None:
    job = workflow["jobs"]["drift-issues"]
    downloads = [
        step
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/download-artifact")
    ]

    [download] = downloads
    assert download["with"]["pattern"] == "drift-report-*"
    reports_dir = download["with"]["path"]
    runs = _runs(job)
    assert f"tools/drift_issues.py --reports {reports_dir} --apply" in runs
    apply_step = next(step for step in job["steps"] if "drift_issues.py" in step.get("run", ""))
    assert "GITHUB_TOKEN" in apply_step.get("env", {})


def test_the_ci_workflow_has_exactly_one_apply_site(workflow: dict[str, Any]) -> None:
    """`--apply` talks to the API; the only job doing so is the one holding the
    `issues: write` permission."""
    apply_jobs = [name for name, job in workflow["jobs"].items() if "drift_issues.py" in _runs(job)]

    assert apply_jobs == ["drift-issues"]


def test_the_drift_issues_job_needs_no_environment_sync(workflow: dict[str, Any]) -> None:
    """The tool is stdlib-only; the job proves it by installing nothing."""
    runs = _runs(workflow["jobs"]["drift-issues"])

    assert "uv sync" not in runs
    assert "pip install" not in runs


# ── The drill: owner-triggered, drill-scoped, honest about what it proves ────────────────


def test_the_drill_can_only_be_dispatched_by_hand(drill: dict[str, Any]) -> None:
    """A workflow that opens real issues never rides push, pull_request or a schedule.
    (PyYAML reads the bare `on:` key as boolean True.)"""
    keys: dict[Any, Any] = drill
    triggers = keys.get("on", keys.get(True))

    assert triggers == {"workflow_dispatch": None}


def test_the_drill_holds_exactly_the_permission_it_needs(drill: dict[str, Any]) -> None:
    [job] = drill["jobs"].values()

    assert job["permissions"] == {"contents": "read", "issues": "write"}


def test_the_drill_tampers_a_real_committed_golden(drill: dict[str, Any]) -> None:
    """The version-gap half is the real chain: the flipped byte belongs to a golden
    that actually exists, so the suite genuinely goes red."""
    [job] = drill["jobs"].values()
    runs = _runs(job)
    goldens = re.findall(r"tests/version_drift/golden/\S+\.json", runs)

    assert goldens, "the drill tampers no golden"
    for golden in goldens:
        assert (REPO_ROOT / golden).is_file(), f"{golden} is not a committed golden"


def test_the_drill_requires_the_tampered_run_to_go_red(drill: dict[str, Any]) -> None:
    """A drill whose tampered suite passed demonstrated nothing and must say so."""
    [job] = drill["jobs"].values()
    tampered_runs = [step for step in job["steps"] if step.get("continue-on-error") is True]

    [tampered] = tampered_runs
    assert "pytest" in tampered["run"]
    void_checks = [
        step
        for step in job["steps"]
        if f"steps.{tampered['id']}.outcome != 'failure'" in str(step.get("if", ""))
    ]
    assert void_checks and "exit 1" in void_checks[0]["run"]


def test_the_drill_report_env_matches_the_seam(drill: dict[str, Any]) -> None:
    [job] = drill["jobs"].values()
    tampered = next(step for step in job["steps"] if step.get("continue-on-error") is True)
    env = tampered["env"]

    assert env[drift_conftest.CELL_VARIABLE] == "3"
    assert str(env[drift_conftest.REPORT_FILE_VARIABLE]).endswith(drift_issues.REPORT_FILE_NAME)


def test_the_drill_synthetic_pre_lines_parse_with_the_real_tool(
    drill: dict[str, Any],
) -> None:
    """The heredoc'd --pre report is held to the parser, so it cannot rot apart."""
    [job] = drill["jobs"].values()
    runs = _runs(job)
    drift_lines = [line.strip() for line in runs.splitlines() if line.strip().startswith("DRIFT-")]

    assert drift_lines, "the drill stages no synthetic --pre report"
    report = drift_issues.parse_report("\n".join(drift_lines) + "\n", Path("drill"))
    assert report.context.cell == drift_issues.PRE_CELL
    assert report.hard
    assert "pytest=failure" in runs
    assert f"drift-report-pre/{drift_issues.PRE_OUTCOME_FILE_NAME}" in runs


def test_the_drill_applies_with_the_drill_flag(drill: dict[str, Any]) -> None:
    [job] = drill["jobs"].values()
    runs = _runs(job)

    assert "tools/drift_issues.py --reports drift-reports --apply --drill" in runs
