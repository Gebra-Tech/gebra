"""The coverage upload (REL-04) — read-only YAML pins.

The coverage number already existed: `test-locked` measures the suite with `coverage run -m
pytest`, and `tools/coverage_gate.py` holds three scopes above 80% each (TE-12). It was
visible to nobody outside a run's artifact list. REL-04 sends the same measurement to Codecov
from that job, on the public repository, so the README can show it — and the whole design is
in one sentence of `docs/governance/coverage-gate.md`: the gate is the floor and Codecov is
the display, never the other way round.

So these tests hold the step to that sentence rather than to its current spelling. The upload
comes after the gate and nothing lets a red gate reach it; it sends exactly the report the
measurement wrote; a missing token is a red step; it runs only where the token lives; it is the
one place `ci.yml` reads a stored secret — the discipline `release.yml` and `docs-pages.yml`
keep at zero (`tests/test_release_wiring.py`, `tests/test_docs_pages_wiring.py`); and the
Codecov configuration turns off everything with which Codecov would judge a commit.

Read-only: YAML parsing and text reads of files in the tree. Nothing here installs, measures,
uploads, executes a workflow node or opens a connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CODECOV_CONFIG = REPO_ROOT / ".github" / "codecov.yml"
GATE_DOC = REPO_ROOT / "docs" / "governance" / "coverage-gate.md"

pytestmark = pytest.mark.skipif(
    not CI_WORKFLOW.is_file(),
    reason="wiring tests describe the source tree; no workflow beside tests/",
)

#: The job that measures and gates coverage, and so the only one with a report to send.
JOB = "test-locked"

#: The upload action, at the major tag the card rules — the way `ci.yml` pins its other
#: actions. The trade-off is stated rather than argued away: this is the one step in the file
#: that receives a stored secret, and a tag is mutable, so what runs with the token is whatever
#: the tag names on the day. What the token can do is bounded — it authorizes coverage uploads
#: to this repository's Codecov project, and nothing on GitHub — which is why the repository's
#: commit pins stay with the steps that use an identity token (`release.yml`'s publish action,
#: `scorecard.yml`'s Scorecard action). A commit pin here is a one-line change on the owner's
#: word.
UPLOAD_ACTION = "codecov/codecov-action@v5"

#: The public repository — the one the Codecov token is stored on. The development
#: repository carries a byte-identical `ci.yml` (PD-050) and must skip the step.
MIRROR = "Gebra-Tech/gebra"

#: The stored secret, spelled the one way it may appear.
TOKEN_EXPRESSION = "${{ secrets.CODECOV_TOKEN }}"

#: What `coverage xml` writes with no `[tool.coverage.xml] output` configured.
REPORT = "coverage.xml"

#: The workflow expression functions that would let a step run after a failure.
_STATUS_FUNCTIONS = re.compile(r"\b(always|failure|cancelled|success)\s*\(")


@pytest.fixture(scope="module")
def ci() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


def _steps(ci: dict[Any, Any]) -> list[dict[Any, Any]]:
    steps: list[dict[Any, Any]] = ci["jobs"][JOB]["steps"]
    return steps


def _step_index(steps: list[dict[Any, Any]], fragment: str) -> int:
    matches = [
        index
        for index, step in enumerate(steps)
        if fragment in str(step.get("run", "")) or fragment in str(step.get("uses", ""))
    ]
    assert len(matches) == 1, f"{fragment!r} matches steps {matches}, not exactly one"
    return matches[0]


def _upload(ci: dict[Any, Any]) -> dict[Any, Any]:
    steps = _steps(ci)
    return steps[_step_index(steps, "codecov/codecov-action")]


# ── Where it sits: after the gate, and nothing lets a red gate reach it ──────────────────


def test_the_upload_is_the_codecov_action_at_its_major_tag(ci: dict[Any, Any]) -> None:
    assert _upload(ci)["uses"] == UPLOAD_ACTION


def test_the_upload_comes_directly_after_the_coverage_gate(ci: dict[Any, Any]) -> None:
    """Measure, write the reports, gate — then upload. Directly after, so no step between the
    verdict and the display can change what is sent."""
    steps = _steps(ci)
    measure = _step_index(steps, "coverage run -m pytest")
    write = _step_index(steps, "coverage xml")
    gate = _step_index(steps, "tools/coverage_gate.py")
    upload = _step_index(steps, "codecov/codecov-action")

    assert measure < write < gate < upload
    assert upload == gate + 1


def test_a_red_suite_or_a_red_gate_never_uploads(ci: dict[Any, Any]) -> None:
    """The upload's condition names no status function, so GitHub applies `success()`.

    Every way a red result could still reach the upload is refused here: `always()` or
    `failure()` in the upload's own condition, and `continue-on-error` on the measuring step
    or the gate, which would turn their failure into a success the implicit `success()` then
    believes. (The report-writing step runs `if: always()` on purpose — so a red suite still
    leaves its artifact — and that is safe only because the gate after it does not.)
    """
    steps = _steps(ci)
    upload = _upload(ci)

    assert not _STATUS_FUNCTIONS.search(str(upload.get("if", ""))), upload.get("if")
    assert "continue-on-error" not in upload
    for fragment in ("coverage run -m pytest", "tools/coverage_gate.py"):
        step = steps[_step_index(steps, fragment)]
        assert "continue-on-error" not in step, fragment
        assert not _STATUS_FUNCTIONS.search(str(step.get("if", ""))), fragment
    assert "continue-on-error" not in ci["jobs"][JOB]


def test_the_upload_runs_only_on_the_public_repository(ci: dict[Any, Any]) -> None:
    """The development repository holds no token, so its runs skip the step and stay green."""
    assert _upload(ci).get("if") == f"github.repository == '{MIRROR}'"


# ── What it sends: exactly the report the measurement wrote ──────────────────────────────


def test_the_upload_sends_exactly_the_report_the_measurement_wrote(ci: dict[Any, Any]) -> None:
    """One file, and no search beside it.

    The action's `files` input *adds* to its own search for coverage files — a search that
    would also find `coverage.json` beside the report, and anything shaped like a report
    under `tests/`. `disable_search` is what makes the upload this file and only this file:
    the XML twin of the JSON the gate read, both written by the step before the gate from the
    one measurement. The artifact the job keeps names the same file.
    """
    steps = _steps(ci)
    upload = _upload(ci)

    assert upload["with"].get("files") == REPORT
    assert upload["with"].get("disable_search") is True
    assert "coverage xml" in str(steps[_step_index(steps, "coverage xml")]["run"])
    artifact = steps[_step_index(steps, "actions/upload-artifact")]
    assert REPORT in str(artifact["with"]["path"]).split()


def test_a_missing_or_refused_token_fails_the_step(ci: dict[Any, Any]) -> None:
    """`fail_ci_if_error: true` is the card's ruling: a missing token must be visible.

    With the action's default (`false`) a mirror run without the secret, or with a revoked
    token, would upload nothing and still show green — a badge going stale with no red step
    anywhere to say why.
    """
    upload = _upload(ci)

    assert upload["with"].get("fail_ci_if_error") is True
    assert upload["with"].get("token") == TOKEN_EXPRESSION


def test_the_codecov_upload_is_the_one_step_in_ci_that_reads_a_secret(ci: dict[Any, Any]) -> None:
    """The `release.yml` discipline, with exactly one sanctioned exception.

    Textual first, like its two twins: a `secrets.` expression can hide in any field — a
    job's `env`, a matrix, a step name — that a parsed step dictionary would not be asked
    about. Then structural, so the one occurrence is known to sit in this step and not merely
    to share its spelling. The automatic per-run token is spelled `github.token` in the
    `drift-issues` job for the same reason.
    """
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    reading = [line.strip() for line in text.splitlines() if "secrets." in line]

    assert reading == [f"token: {TOKEN_EXPRESSION}"]
    holders = [
        (name, step.get("name"))
        for name, job in ci["jobs"].items()
        for step in job.get("steps", [])
        if "secrets." in yaml.safe_dump(step)
    ]
    assert holders == [(JOB, _upload(ci)["name"])]


# ── What Codecov is allowed to do with it: display, and nothing else ─────────────────────


@pytest.fixture(scope="module")
def codecov_config() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(CODECOV_CONFIG.read_text(encoding="utf-8"))
    return data


def test_codecov_posts_no_commit_status(codecov_config: dict[Any, Any]) -> None:
    """A `codecov/project` or `codecov/patch` status is a pass/fail verdict on a commit.

    The gate already gave that verdict, per scope, and a second one computed by other
    arithmetic is the other way round. YAML reads Codecov's documented `off` as `False`.
    """
    assert codecov_config["coverage"]["status"] == {"project": False, "patch": False}


def test_codecov_comments_on_nothing_and_annotates_nothing(codecov_config: dict[Any, Any]) -> None:
    assert codecov_config["comment"] is False
    assert codecov_config["github_checks"] == {"annotations": False}


def test_the_gate_page_says_which_is_the_floor_and_which_is_the_display() -> None:
    """The sentence the upload is built to, on the page that owns the gate."""
    page = re.sub(r"\s+", " ", GATE_DOC.read_text(encoding="utf-8"))

    assert "the gate is the floor and Codecov is the display, never the other way round" in page
    assert "`.github/codecov.yml`" in page
