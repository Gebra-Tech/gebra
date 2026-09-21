"""Every workflow's token grant, against a declared table (REL-10).

Five per-workflow wiring modules already hold the files they are named for, and between
them they left a gap: nothing knew how many workflows the tree has, so a sixth file could
arrive — or an existing one could lose its ``permissions:`` block — with every test still
green. That is how three workflows came to run every job on the repository's default token
grant, which OpenSSF Scorecard's Token-Permissions check reads as the weakest shape a
workflow can have.

This module is about the *set*. ``WORKFLOW_PERMISSIONS`` below names every workflow in the
tree with the grant it may declare at the file level and a one-line reason, and a new
workflow fails here until it is registered. Three rules follow from the table:

* every workflow declares a top-level ``permissions`` mapping equal to its entry;
* no entry grants a ``write`` — the file level is read-only everywhere, so a job that
  needs more has to say so on itself; and
* every job-level ``write`` in the tree is named in the table with the job that holds it,
  because a job-level block replaces the file-level one rather than adding to it.

Read-only: YAML parsing of the files under ``.github/workflows/``. Nothing here installs,
executes a workflow node, or opens a connection (WA-07).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
WORKFLOW_DIR: Final = REPO_ROOT / ".github" / "workflows"

# What the skip separates is a source tree from a copy of `tests/` without one: an unpacked
# sdist carries no `.github/`. Keyed on the directory rather than on one workflow inside it,
# so a deleted or renamed workflow fails the registration test below instead of skipping it.
pytestmark = pytest.mark.skipif(
    not WORKFLOW_DIR.is_dir(),
    reason="wiring tests describe the source tree; no workflows beside tests/",
)


@dataclass(frozen=True)
class Grant:
    """One workflow's registered token grant.

    ``top_level`` is the mapping the file must declare above its jobs; ``jobs`` names each
    job that declares a block of its own, with the whole mapping it declares — a job-level
    block replaces the file-level one, so a job that needs a write still has to restate the
    reads it uses.
    """

    reason: str
    top_level: Mapping[str, str]
    jobs: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


#: Every workflow in the tree, with the grant it declares and why it needs it. A workflow
#: that is not listed here fails `test_the_table_names_every_workflow_in_the_tree`.
WORKFLOW_PERMISSIONS: Final[dict[str, Grant]] = {
    "ci.yml": Grant(
        reason="Quality gates read a checkout; `drift-issues` opens the version-gap records.",
        top_level={"contents": "read"},
        jobs={"drift-issues": {"contents": "read", "issues": "write"}},
    ),
    "docs-pages.yml": Grant(
        reason="Builds the documentation site and deploys it to GitHub Pages (PD-051 ruling 6).",
        top_level={"contents": "read"},
        jobs={"deploy": {"contents": "read", "pages": "write", "id-token": "write"}},
    ),
    "drift-issue-drill.yml": Grant(
        reason="The owner-triggered drill opens the drill-scoped issues it exists to demonstrate.",
        top_level={"contents": "read"},
        jobs={"drill": {"contents": "read", "issues": "write"}},
    ),
    "gebra-gate-example.yml": Grant(
        reason="Runs the documented gate over the example suite and writes nothing back.",
        top_level={"contents": "read"},
    ),
    "release.yml": Grant(
        reason="Builds the distributions; the publish job mints the PyPI trusted-publishing token.",
        top_level={"contents": "read"},
        jobs={"publish-pypi": {"id-token": "write"}},
    ),
    "scorecard.yml": Grant(
        reason="Scores the public repository and uploads the findings to the code-scanning page.",
        top_level={"contents": "read"},
        jobs={"analysis": {"security-events": "write", "id-token": "write"}},
    ),
}


@pytest.fixture(scope="module")
def workflows() -> dict[str, dict[Any, Any]]:
    """Every workflow file in the tree, parsed, keyed by file name."""
    parsed: dict[str, dict[Any, Any]] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict), path.name
        parsed[path.name] = document
    return parsed


def _declared_job_permissions(document: dict[Any, Any]) -> dict[str, Mapping[str, str]]:
    """The job-level ``permissions`` blocks of one workflow, keyed by job name."""
    jobs: Mapping[str, Mapping[str, Any]] = document["jobs"]
    return {name: body["permissions"] for name, body in jobs.items() if "permissions" in body}


def _writes(grant: Mapping[str, str]) -> set[str]:
    return {scope for scope, level in grant.items() if level == "write"}


# ── The set of workflows ─────────────────────────────────────────────────────────────────


def test_the_table_names_every_workflow_in_the_tree(workflows: dict[str, dict[Any, Any]]) -> None:
    """A new workflow is registered here before it can be green.

    This is the check the five per-workflow modules cannot make: each of them is named for
    one file and says nothing about a seventh arriving beside it.
    """
    assert set(workflows) == set(WORKFLOW_PERMISSIONS)


def test_every_entry_carries_a_one_line_reason() -> None:
    """The table is read by people too: each row says what the workflow needs its token for."""
    for name, grant in WORKFLOW_PERMISSIONS.items():
        assert grant.reason.strip() == grant.reason and grant.reason, name
        assert "\n" not in grant.reason, name


# ── Rule 1: the file level is declared, and it is what the table says ────────────────────


def test_every_workflow_declares_the_top_level_grant_its_entry_names(
    workflows: dict[str, dict[Any, Any]],
) -> None:
    """A missing block is not a small omission: it hands every job in the file the
    repository's default grant, whatever that is set to on the day the job runs."""
    for name, document in workflows.items():
        declared = document.get("permissions")
        assert isinstance(declared, dict), f"{name} declares no top-level permissions mapping"
        assert declared == dict(WORKFLOW_PERMISSIONS[name].top_level), name


# ── Rule 2: nothing writes from the file level ───────────────────────────────────────────


def test_no_workflow_grants_a_write_at_the_top_level(
    workflows: dict[str, dict[Any, Any]],
) -> None:
    """A write declared above the jobs is a write every job in the file carries, including
    the ones that only read. The jobs that need one declare it on themselves."""
    for name, grant in WORKFLOW_PERMISSIONS.items():
        assert not _writes(grant.top_level), name
    for name, document in workflows.items():
        assert not _writes(document["permissions"]), name


# ── Rule 3: every job-level write is named, with its job ─────────────────────────────────


def test_every_job_level_block_in_the_tree_is_the_one_the_table_names(
    workflows: dict[str, dict[Any, Any]],
) -> None:
    """Named per job, and equal — a job that grew a scope fails here rather than drifting.

    The four blocks: `ci.yml`'s `drift-issues` and the drill's `drill` open version-gap and
    drill issues; `docs-pages.yml`'s `deploy` writes the Pages deployment and mints the token
    that authorizes it; `release.yml`'s `publish-pypi` mints the trusted-publishing token; and
    `scorecard.yml`'s `analysis` uploads its findings to code scanning.
    """
    for name, document in workflows.items():
        declared = _declared_job_permissions(document)
        expected = {job: dict(block) for job, block in WORKFLOW_PERMISSIONS[name].jobs.items()}
        assert {job: dict(block) for job, block in declared.items()} == expected, name


def test_no_write_exists_in_the_tree_that_the_table_does_not_name(
    workflows: dict[str, dict[Any, Any]],
) -> None:
    """The same fact from the other side: collect every write the files grant anywhere, and
    check the table accounts for each one against the job that holds it."""
    found = {
        (name, job, scope)
        for name, document in workflows.items()
        for job, block in _declared_job_permissions(document).items()
        for scope in _writes(block)
    }
    registered = {
        (name, job, scope)
        for name, grant in WORKFLOW_PERMISSIONS.items()
        for job, block in grant.jobs.items()
        for scope in _writes(block)
    }

    assert found == registered
    assert registered == {
        ("ci.yml", "drift-issues", "issues"),
        ("docs-pages.yml", "deploy", "pages"),
        ("docs-pages.yml", "deploy", "id-token"),
        ("drift-issue-drill.yml", "drill", "issues"),
        ("release.yml", "publish-pypi", "id-token"),
        ("scorecard.yml", "analysis", "security-events"),
        ("scorecard.yml", "analysis", "id-token"),
    }


def test_every_registered_job_exists_in_its_workflow(
    workflows: dict[str, dict[Any, Any]],
) -> None:
    """A renamed job fails loudly here instead of quietly leaving the table describing
    nothing — the shape `tests/test_scorecard_wiring.py` takes for its single job."""
    for name, grant in WORKFLOW_PERMISSIONS.items():
        for job in grant.jobs:
            assert job in workflows[name]["jobs"], f"{name}: no job {job!r}"
