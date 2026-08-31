"""The release workflow's wiring (GOV-03) — read-only YAML pins.

PD-036 holds only if the workflow stays shaped the way the ruling reads: tag-triggered,
gated through ``tools/release_gate.py``, publish leg reachable only for a final tag under
the ``pypi`` environment with OIDC and **no stored credential of any kind**, and CI's
``build`` job running the same gate + metadata validation on every push so the tree stays
release-ready between cuts. These tests hold ``.github/workflows/release.yml``,
``.github/workflows/ci.yml`` and the gate tool in lockstep the way
``test_drift_issue_wiring.py`` holds the drift machinery together.

Read-only: YAML parsing plus an import of the gate module for its constants. Nothing here
installs, executes a workflow, builds, publishes, or opens a socket (WA-07).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import release_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(
    not RELEASE_WORKFLOW.is_file(),
    reason="wiring tests describe the source tree; no workflow beside tests/",
)

#: One spelling of the metadata validation, shared verbatim by both workflows: the pinned
#: twine resolved by uvx, strict so a warning is a failure.
TWINE_COMMAND = "uvx twine@6.1.0 check --strict dist/*"


@pytest.fixture(scope="module")
def release() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def ci() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


def _triggers(workflow: dict[Any, Any]) -> dict[Any, Any]:
    # YAML 1.1 reads the bare key `on` as boolean True.
    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def _steps(workflow: dict[Any, Any], job: str) -> list[dict[Any, Any]]:
    steps: list[dict[Any, Any]] = workflow["jobs"][job]["steps"]
    return steps


def _step_index(steps: list[dict[Any, Any]], fragment: str) -> int:
    for index, step in enumerate(steps):
        if fragment in str(step.get("run", "")) or fragment in str(step.get("uses", "")):
            return index
    raise AssertionError(f"no step matches {fragment!r}")


# ── Triggers: tags in the gate's own grammar prefix, plus the one-click dry run ──────────


def test_the_workflow_triggers_on_v_tags_and_manual_dispatch(release: dict[Any, Any]) -> None:
    triggers = _triggers(release)
    assert triggers["push"] == {"tags": [release_gate.TAG_PREFIX + "*"]}
    assert "workflow_dispatch" in triggers


def test_the_workflow_reads_contents_only_at_the_top_level(release: dict[Any, Any]) -> None:
    assert release["permissions"] == {"contents": "read"}


def test_the_uv_version_stays_in_lockstep_with_ci(
    release: dict[Any, Any], ci: dict[Any, Any]
) -> None:
    assert release["env"]["UV_VERSION"] == ci["env"]["UV_VERSION"]


# ── The build job: gate → build → validate → verify → smoke, outputs wired ───────────────


def test_the_build_job_exposes_the_gate_outputs(release: dict[Any, Any]) -> None:
    outputs = release["jobs"]["build"]["outputs"]
    assert outputs["version"] == "${{ steps.gate.outputs.version }}"
    assert outputs["kind"] == "${{ steps.gate.outputs.kind }}"
    assert outputs["publish"] == "${{ steps.gate.outputs.publish }}"


def test_the_gate_step_runs_both_modes_through_the_gate_tool(release: dict[Any, Any]) -> None:
    steps = _steps(release, "build")
    gate = steps[_step_index(steps, "tools/release_gate.py --ref")]
    assert gate["id"] == "gate"
    run = gate["run"]
    assert 'python tools/release_gate.py --ref "$GITHUB_REF"' in run
    assert "python tools/release_gate.py --dry-run" in run
    assert "--notes-out release-notes.md" in run
    assert '--github-output "$GITHUB_OUTPUT"' in run


def test_the_build_step_is_the_same_command_ci_runs(
    release: dict[Any, Any], ci: dict[Any, Any]
) -> None:
    release_steps = _steps(release, "build")
    ci_steps = _steps(ci, "build")
    build = release_steps[_step_index(release_steps, "uv build")]["run"]
    assert build == ci_steps[_step_index(ci_steps, "uv build")]["run"]


def test_the_twine_validation_is_pinned_and_identical_in_both_workflows(
    release: dict[Any, Any], ci: dict[Any, Any]
) -> None:
    release_steps = _steps(release, "build")
    ci_steps = _steps(ci, "build")
    assert release_steps[_step_index(release_steps, "twine")]["run"] == TWINE_COMMAND
    assert ci_steps[_step_index(ci_steps, "twine")]["run"] == TWINE_COMMAND


def test_the_dist_verification_runs_after_the_build(release: dict[Any, Any]) -> None:
    steps = _steps(release, "build")
    build = _step_index(steps, "uv build")
    verify = _step_index(steps, "--verify-dist dist")
    twine = _step_index(steps, "twine")
    smoke = _step_index(steps, "wheelcheck")
    assert build < twine
    assert build < verify
    assert build < smoke


def test_the_wheel_smoke_test_asserts_the_gated_version(release: dict[Any, Any]) -> None:
    steps = _steps(release, "build")
    smoke = steps[_step_index(steps, "wheelcheck")]
    assert smoke["env"]["GATE_VERSION"] == "${{ steps.gate.outputs.version }}"
    assert 'test "$installed" = "$GATE_VERSION"' in smoke["run"]


def test_the_uploads_carry_retention_and_fail_on_missing_files(
    release: dict[Any, Any],
) -> None:
    uploads = [
        step
        for step in _steps(release, "build")
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert len(uploads) == 2
    names = {upload["with"]["name"] for upload in uploads}
    assert names == {
        "gebra-dist-${{ steps.gate.outputs.version }}",
        "release-notes-${{ steps.gate.outputs.version }}",
    }
    for upload in uploads:
        assert upload["with"]["retention-days"] == 90
        assert upload["with"]["if-no-files-found"] == "error"


# ── The publish leg: reachable only for a final tag, OIDC only, no secret anywhere ───────


def test_the_publish_job_is_gated_on_the_gate_output_and_a_real_tag_push(
    release: dict[Any, Any],
) -> None:
    """All three gates: the gate's verdict, a tag ref, AND the push event itself — a
    `workflow_dispatch` issued on a tag ref must stay a build-and-validate run."""
    publish = release["jobs"]["publish-pypi"]
    assert publish["needs"] == "build"
    condition = publish["if"]
    assert "needs.build.outputs.publish == 'true'" in condition
    assert "github.ref_type == 'tag'" in condition
    assert "github.event_name == 'push'" in condition


def test_the_publish_job_uses_the_pypi_environment_and_id_token_only(
    release: dict[Any, Any],
) -> None:
    publish = release["jobs"]["publish-pypi"]
    assert publish["environment"]["name"] == "pypi"
    assert str(publish["environment"]["url"]).startswith("https://pypi.org/project/gebra/")
    assert publish["permissions"] == {"id-token": "write"}


def test_the_publish_job_downloads_the_dist_artifact_and_publishes_via_the_pypa_action(
    release: dict[Any, Any],
) -> None:
    steps = _steps(release, "publish-pypi")
    download = steps[_step_index(steps, "actions/download-artifact")]
    assert download["uses"] == "actions/download-artifact@v4"
    assert download["with"]["name"] == "gebra-dist-${{ needs.build.outputs.version }}"
    publish = steps[_step_index(steps, "pypa/gh-action-pypi-publish")]
    assert publish["uses"] == "pypa/gh-action-pypi-publish@release/v1"
    assert publish["with"] == {"packages-dir": "dist"}


def test_no_step_in_the_release_workflow_reads_a_secret(release: dict[Any, Any]) -> None:
    """PD-036: no long-lived credential exists; the OIDC exchange is the whole auth."""
    assert "secrets." not in RELEASE_WORKFLOW.read_text(encoding="utf-8")
    del release  # the pin is textual on purpose: expressions hide in any field


def test_only_the_publish_job_carries_an_environment_or_extra_permissions(
    release: dict[Any, Any],
) -> None:
    for name, job in release["jobs"].items():
        if name == "publish-pypi":
            continue
        assert "environment" not in job
        assert "permissions" not in job


# ── CI stays release-ready: the same gate + validation on every push ─────────────────────


def test_ci_build_runs_the_dry_run_gate_with_dist_verification(ci: dict[Any, Any]) -> None:
    steps = _steps(ci, "build")
    gate = steps[_step_index(steps, "tools/release_gate.py --dry-run")]
    assert gate["run"] == "python tools/release_gate.py --dry-run --verify-dist dist"
    assert _step_index(steps, "uv build") < _step_index(steps, "tools/release_gate.py --dry-run")
