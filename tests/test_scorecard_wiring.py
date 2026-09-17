"""The OpenSSF Scorecard workflow (REL-04) — read-only YAML pins.

``.github/workflows/scorecard.yml`` runs Scorecard over the public repository and uploads the
findings to code scanning. Two things about it are decisions rather than defaults, and both
are held here. It runs with an identity token in reach, so the step that uses it is pinned
to a commit the way ``release.yml`` pins the publish action (GOV-14). And whether its
result is published is the owner's word on the card: the ``publish_results`` flag and the
README's Scorecard badge answer that one question together — a badge with nothing published
behind it has no score to show, and a published score with no badge is a choice the card did
not offer — so they are asserted as one fact.

A publishing run also refuses a workflow shaped outside a short list of rules (no
workflow-level ``env``, ``defaults`` or write permission; only the identity-token job may
mint one; that job carries no ``env``, ``defaults``, container or service, runs on a hosted
Ubuntu runner, and uses nothing but a handful of named actions). The file keeps to them under
either ruling, so turning publication on later is a one-line change and a badge.

Read-only: YAML parsing and text reads of three files in the tree. Nothing here installs,
runs Scorecard, uploads, executes a workflow node or opens a connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCORECARD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "scorecard.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
README = REPO_ROOT / "README.md"

# Keyed on `ci.yml`, not on the file under test: what the skip separates is a source tree from
# a copy of `tests/` without one (an unpacked sdist carries no `.github/`). Keyed on
# `scorecard.yml` itself, deleting or renaming the workflow would skip every pin below and
# leave the suite green; keyed here, it fails them.
pytestmark = pytest.mark.skipif(
    not CI_WORKFLOW.is_file(),
    reason="wiring tests describe the source tree; no workflow beside tests/",
)

#: The repository that is scored. The development repository carries the same file (PD-050).
MIRROR = "Gebra-Tech/gebra"

#: The one job. Named here so a renamed job fails loudly rather than skipping every test.
JOB = "analysis"

#: The Scorecard action, pinned to the commit its `v2.4.4` release tag names (resolved
#: 2026-09-16 through the tag object; the manifest at that commit runs the `v2.4.4` image).
#: The comment beside the SHA names the release, so a reviewer can check the pair without
#: resolving the ref — the form `tests/test_release_wiring.py` holds the publish action to.
SCORECARD_ACTION = "ossf/scorecard-action"
SCORECARD_ACTION_SHA = "2d1146689b8cda280b9bc96326124645441f03bc"
SCORECARD_ACTION_RELEASE = "v2.4.4"

#: The actions a publishing run admits in the job that runs Scorecard, as the action's own
#: documentation lists them.
PUBLISHABLE_ACTIONS = frozenset(
    {
        "actions/checkout",
        "actions/upload-artifact",
        "github/codeql-action/upload-sarif",
        "ossf/scorecard-action",
        "step-security/harden-runner",
    }
)

#: The badge, exactly as the card rules it: the score image, linked to the public viewer.
SCORECARD_BADGE = (
    "[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Gebra-Tech/gebra/badge)]"
    "(https://scorecard.dev/viewer/?uri=github.com/Gebra-Tech/gebra)"
)

_MAJOR_TAG = re.compile(r"^[\w.-]+(/[\w.-]+)+@v\d+$")


@pytest.fixture(scope="module")
def scorecard() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(SCORECARD_WORKFLOW.read_text(encoding="utf-8"))
    return data


def _triggers(workflow: dict[Any, Any]) -> dict[Any, Any]:
    # YAML 1.1 reads the bare key `on` as boolean True.
    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def _job(scorecard: dict[Any, Any]) -> dict[Any, Any]:
    job: dict[Any, Any] = scorecard["jobs"][JOB]
    return job


def _steps(scorecard: dict[Any, Any]) -> list[dict[Any, Any]]:
    steps: list[dict[Any, Any]] = _job(scorecard)["steps"]
    return steps


def _action(ref: str) -> str:
    return ref.split("@", 1)[0]


def _run_step(scorecard: dict[Any, Any]) -> dict[Any, Any]:
    [step] = [
        step for step in _steps(scorecard) if _action(str(step.get("uses"))) == SCORECARD_ACTION
    ]
    return step


# ── When and where it runs ───────────────────────────────────────────────────────────────


def test_the_workflow_runs_weekly_and_on_pushes_to_main(scorecard: dict[Any, Any]) -> None:
    """The two triggers a published result is accepted from, and nothing else.

    A pull-request trigger would score a proposal; the weekly run keeps the checks that read
    time — the repository's age and activity, the advisory database — current in a week with
    no push.
    """
    triggers = _triggers(scorecard)

    assert set(triggers) == {"push", "schedule"}
    assert triggers["push"] == {"branches": ["main"]}
    [entry] = triggers["schedule"]
    minute, hour, day_of_month, month, day_of_week = str(entry["cron"]).split()
    assert minute.isdigit() and hour.isdigit()
    assert (day_of_month, month) == ("*", "*")
    assert day_of_week.isdigit() and 0 <= int(day_of_week) <= 6


def test_the_job_runs_only_on_the_public_repository(scorecard: dict[Any, Any]) -> None:
    """PD-050: the trees are byte-identical, so the condition is what keeps the development
    repository from running Scorecard over itself."""
    assert list(scorecard["jobs"]) == [JOB]
    assert _job(scorecard).get("if") == f"github.repository == '{MIRROR}'"
    assert _job(scorecard).get("runs-on") == "ubuntu-latest"


# ── Permissions: read-only above, the two writes the job needs, and nothing else ─────────


def test_the_workflow_level_grants_no_write_permission(scorecard: dict[Any, Any]) -> None:
    assert scorecard.get("permissions") == {"contents": "read"}


def test_the_job_holds_exactly_the_two_permissions_it_needs(scorecard: dict[Any, Any]) -> None:
    """`security-events: write` uploads the findings; `id-token: write` signs a published
    result. Declared on the job, so they replace the workflow-level grant for it."""
    assert _job(scorecard).get("permissions") == {
        "security-events": "write",
        "id-token": "write",
    }


def test_no_step_reads_a_secret() -> None:
    """The action's token defaults to the run's own; there is no stored credential here.

    Textual, like `release.yml`'s twin: an expression can hide in any field.
    """
    assert "secrets." not in SCORECARD_WORKFLOW.read_text(encoding="utf-8")


# ── The shape a publishing run accepts, kept under either ruling ─────────────────────────


def test_the_file_keeps_to_what_a_publishing_run_accepts(scorecard: dict[Any, Any]) -> None:
    """No workflow-level or job-level `env` or `defaults`, no container, no service, and only
    the named actions — so the owner's word can turn publication on without a reshape."""
    job = _job(scorecard)

    assert "env" not in scorecard and "defaults" not in scorecard
    for key in ("env", "defaults", "container", "services"):
        assert key not in job, key
    assert all("uses" in step and "run" not in step for step in _steps(scorecard))
    assert {_action(str(step["uses"])) for step in _steps(scorecard)} <= PUBLISHABLE_ACTIONS


def test_the_steps_check_out_then_score_then_upload(scorecard: dict[Any, Any]) -> None:
    """Checkout with no credential left behind, Scorecard writing SARIF, and the upload
    reading the file Scorecard wrote."""
    checkout, run, upload = _steps(scorecard)

    assert _action(str(checkout["uses"])) == "actions/checkout"
    assert checkout["with"] == {"persist-credentials": False}
    assert _action(str(run["uses"])) == SCORECARD_ACTION
    assert run["with"]["results_format"] == "sarif"
    assert _action(str(upload["uses"])) == "github/codeql-action/upload-sarif"
    assert upload["with"] == {"sarif_file": run["with"]["results_file"]}


# ── The pin ──────────────────────────────────────────────────────────────────────────────


def test_the_scorecard_action_is_pinned_to_a_commit_with_its_release_named() -> None:
    """Held textually, because YAML drops the comment that names the release.

    A full 40-hex commit SHA — a tag is mutable and an abbreviated SHA is ambiguous — followed
    on the same line by the release it resolves to, and no tag-pinned reference to the action
    left anywhere in the file to fall back to.
    """
    text = SCORECARD_WORKFLOW.read_text(encoding="utf-8")
    [line] = [line.strip() for line in text.splitlines() if f"{SCORECARD_ACTION}@" in line]

    assert line == f"uses: {SCORECARD_ACTION}@{SCORECARD_ACTION_SHA} # {SCORECARD_ACTION_RELEASE}"
    assert len(SCORECARD_ACTION_SHA) == 40
    assert set(SCORECARD_ACTION_SHA) <= set("0123456789abcdef")


def test_the_other_actions_are_pinned_to_major_tags(scorecard: dict[Any, Any]) -> None:
    """The repository's rule: a commit pin for the step that uses an identity token, major tags
    for the rest, the way `ci.yml` pins them."""
    others = [
        str(step["uses"])
        for step in _steps(scorecard)
        if _action(str(step["uses"])) != SCORECARD_ACTION
    ]

    assert others and all(_MAJOR_TAG.match(ref) for ref in others), others


# ── Publication and the badge: one ruling, two places ────────────────────────────────────


def test_the_badge_is_shown_exactly_when_the_result_is_published(
    scorecard: dict[Any, Any],
) -> None:
    """The owner's word on the card sets both, and they cannot disagree.

    `go` publishes and shows the badge; `no-go` does neither. A badge over an unpublished
    project has no score to show, in the row a reader looks at first, and the card offers no
    published score without its badge. Nothing else on the page names the Scorecard service.
    """
    published = _run_step(scorecard)["with"].get("publish_results")
    readme = README.read_text(encoding="utf-8")

    assert isinstance(published, bool)
    assert (SCORECARD_BADGE in readme) is published
    assert readme.count("scorecard.dev") == (2 if published else 0)


def test_scorecard_is_a_workflow_of_its_own_and_not_a_ci_job() -> None:
    """The contributor guide counts `ci.yml`'s jobs; a scoring job folded in there would move
    the count and carry `security-events: write` through every pull-request run."""
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8")

    assert SCORECARD_ACTION not in ci_text
    assert "security-events" not in ci_text
