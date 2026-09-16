"""The documentation site's deployment (REL-03) — read-only YAML pins.

``.github/workflows/docs-pages.yml`` is what turned PD-051 ruling 6 from a recorded
destination into a served site. The ruling is only kept if the workflow stays shaped the way
it reads: the site that is *published* has to be the site the ``docs`` job *gated*, the
deployment has to be confined to the public mirror, and it has to stay credential-free the
way ``release.yml``'s publish leg is (PD-036).

So rather than restate the build in a second place, these tests hold the deployment to the
files that already own each fact — the build command and the toolchain install are read out
of ``ci.yml``'s ``docs`` job, the uploaded directory is read out of ``mkdocs.yml``'s
``site_dir`` — and a change to either one that forgets this workflow fails here.

Read-only: YAML parsing of three files in the tree. Nothing here installs, builds,
deploys, executes a workflow node or opens a connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docs-pages.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MKDOCS = REPO_ROOT / "mkdocs.yml"

pytestmark = pytest.mark.skipif(
    not PAGES_WORKFLOW.is_file(),
    reason="wiring tests describe the source tree; no workflow beside tests/",
)

#: The repository that serves the site. The development repository is a byte-identical
#: private tree (PD-050), so the condition — not the absence of the file — is what keeps it
#: from deploying.
MIRROR = "Gebra-Tech/gebra"

#: The one job. Named here so a renamed job fails loudly rather than skipping every test.
DEPLOY_JOB = "deploy"

#: `owner/repo@vN` — a major tag, the way `ci.yml` pins every action it uses. The publish
#: action in `release.yml` is the repository's one SHA pin (GOV-14 `DV-A-9`): it mints a
#: credential against a package the world installs, where the token exchanged here acts on
#: this repository's own Pages site.
_MAJOR_TAG = re.compile(r"^[\w.-]+/[\w.-]+@v\d+$")


@pytest.fixture(scope="module")
def pages() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(PAGES_WORKFLOW.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def ci() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def mkdocs_config() -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(MKDOCS.read_text(encoding="utf-8"))
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


def _uses(steps: list[dict[Any, Any]]) -> list[str]:
    return [str(step["uses"]) for step in steps if "uses" in step]


# ── Where it runs: one branch, one repository, on demand ─────────────────────────────────


def test_the_deployment_triggers_on_main_and_on_demand(pages: dict[Any, Any]) -> None:
    """A push to `main` publishes; `workflow_dispatch` re-publishes without an empty commit.

    Nothing else triggers it. A pull-request trigger would deploy a proposal over the
    served site, and the scheduled runs `ci.yml` carries exist to re-resolve an index the
    site build does not read.
    """
    triggers = _triggers(pages)

    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"branches": ["main"]}


def test_the_deployment_runs_only_on_the_public_mirror(pages: dict[Any, Any]) -> None:
    """PD-050: the two trees are byte-identical, so the condition is what separates them.

    The development repository has to carry this file — a path that differed between the
    repositories is exactly what the mirror sync refuses — and it must not deploy from it.
    """
    assert pages["jobs"][DEPLOY_JOB]["if"] == f"github.repository == '{MIRROR}'"
    assert list(pages["jobs"]) == [DEPLOY_JOB]


def test_the_workflow_asks_for_exactly_what_a_pages_deployment_needs(
    pages: dict[Any, Any],
) -> None:
    """Read the tree, write the deployment, mint the token that authorizes it — and no more."""
    assert pages["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert "permissions" not in pages["jobs"][DEPLOY_JOB]


def test_one_deployment_runs_at_a_time(pages: dict[Any, Any]) -> None:
    """Serialized, and the run in flight finishes.

    `concurrency: pages` is the group with `cancel-in-progress` left at its default, which
    is not to cancel: a Pages deployment interrupted mid-upload can leave the site on a
    partial artifact, and the cost of waiting is that the next push waits.
    """
    assert pages["concurrency"] == "pages"


def test_the_deployment_runs_in_the_github_pages_environment(pages: dict[Any, Any]) -> None:
    """The environment is where the OIDC token comes from, and where the URL is reported."""
    job = pages["jobs"][DEPLOY_JOB]

    assert job["environment"]["name"] == "github-pages"
    assert job["environment"]["url"] == "${{ steps.deployment.outputs.page_url }}"

    deploy = _steps(pages, DEPLOY_JOB)[-1]
    assert deploy["id"] == "deployment", "the environment URL reads this step's output"


def test_no_step_in_the_deployment_reads_a_secret() -> None:
    """The whole authorization is the OIDC exchange — there is no stored credential.

    Textual on purpose, like `release.yml`'s twin: a `secrets.` expression can hide in any
    field of any step, including ones a parsed step dictionary would not be asked about.
    """
    assert "secrets." not in PAGES_WORKFLOW.read_text(encoding="utf-8")


# ── What it publishes: the site the `docs` job gated, and nothing rebuilt ─────────────────


def _docs_job_step(ci: dict[Any, Any], fragment: str) -> dict[Any, Any]:
    steps = _steps(ci, "docs")
    return steps[_step_index(steps, fragment)]


def test_the_build_command_is_the_docs_jobs_own(pages: dict[Any, Any], ci: dict[Any, Any]) -> None:
    """One build command, read out of `ci.yml` rather than restated here.

    The gate and the deployment have to run the same thing or "the site CI builds" and
    "the site a reader is served" are two claims. Raising `--strict`, or moving the build
    behind a script, fails here until this workflow is moved with it.
    """
    gate = _docs_job_step(ci, "mkdocs build")
    build = _steps(pages, DEPLOY_JOB)[_step_index(_steps(pages, DEPLOY_JOB), "mkdocs build")]

    assert gate["run"] == "mkdocs build --strict"
    assert build["run"] == gate["run"]
    assert build["name"] == gate["name"]


def test_the_toolchain_install_is_the_docs_jobs_own(
    pages: dict[Any, Any], ci: dict[Any, Any]
) -> None:
    """The generator is the pinned one the gate resolved (PD-051 ruling 4).

    `ci.yml` installs the package as well, because the pages' examples import it; this job
    renders Markdown and does not, so it takes that job's second line only — and the line
    itself, constraints file included, is read from there rather than written twice.
    """
    gate_lines = [
        line.strip()
        for line in str(_docs_job_step(ci, "docs/requirements.txt")["run"]).splitlines()
        if line.strip()
    ]
    install = _steps(pages, DEPLOY_JOB)[
        _step_index(_steps(pages, DEPLOY_JOB), "docs/requirements.txt")
    ]

    assert "pip install -r docs/requirements.txt -c tools/matrix-constraints.txt" in gate_lines
    assert str(install["run"]).strip() in gate_lines


def test_the_interpreter_is_the_docs_jobs_own(pages: dict[Any, Any], ci: dict[Any, Any]) -> None:
    gate = _docs_job_step(ci, "actions/setup-python")
    setup = _steps(pages, DEPLOY_JOB)[
        _step_index(_steps(pages, DEPLOY_JOB), "actions/setup-python")
    ]

    assert setup["with"]["python-version"] == gate["with"]["python-version"] == "3.13"


def test_the_uploaded_directory_is_the_one_mkdocs_writes(
    pages: dict[Any, Any], mkdocs_config: dict[Any, Any]
) -> None:
    """The artifact is `site_dir`, read from `mkdocs.yml`.

    The action's own default is `_site/`, so this is not a line that can be dropped: with
    no `path` the upload would look somewhere the build never wrote, and a renamed
    `site_dir` would quietly publish nothing. Compared as directories rather than as
    spellings, so a trailing slash on either side is not a failure.
    """
    upload = _steps(pages, DEPLOY_JOB)[
        _step_index(_steps(pages, DEPLOY_JOB), "actions/upload-pages-artifact")
    ]

    assert str(upload["with"]["path"]).rstrip("/") == str(mkdocs_config["site_dir"]).rstrip("/")


def test_the_site_build_imports_nothing_from_this_repository(
    mkdocs_config: dict[Any, Any],
) -> None:
    """Why this job can omit the package the `docs` job installs.

    `ci.yml` installs `gebra` before it builds, because the pages' examples import it; this
    job does not, and `mkdocs build --strict` succeeds without it — but only while the
    configuration stays a Markdown renderer. A `plugins:` or `hooks:` entry (mkdocstrings,
    macros, gen-files, a hook module) would put repository code inside the build, which is
    both an install this job would then need and a WA-07 surface a deployment should not be
    where it is first discovered. Adding one is allowed; doing it without reading this is not.
    """
    assert "plugins" not in mkdocs_config
    assert "hooks" not in mkdocs_config


def test_the_steps_build_before_they_publish(pages: dict[Any, Any]) -> None:
    """Checkout, interpreter, toolchain, build, then the three Pages actions in order."""
    steps = _steps(pages, DEPLOY_JOB)
    order = [
        "actions/checkout",
        "actions/setup-python",
        "docs/requirements.txt",
        "mkdocs build",
        "actions/configure-pages",
        "actions/upload-pages-artifact",
        "actions/deploy-pages",
    ]

    assert [_step_index(steps, fragment) for fragment in order] == list(range(len(order)))
    assert len(steps) == len(order)


def test_a_run_can_neither_enable_pages_nor_choose_how_the_site_is_built(
    pages: dict[Any, Any],
) -> None:
    """The source switch stays in the repository's settings, where a person makes it.

    `actions/configure-pages` will enable Pages itself when asked (`enablement: true`),
    which would make a workflow file the thing that decides a repository serves a website.
    Left at its default it reads the configuration and reports the base URL; the
    Settings -> Pages -> Source switch remains the owner's, made once.
    """
    configure = _steps(pages, DEPLOY_JOB)[
        _step_index(_steps(pages, DEPLOY_JOB), "actions/configure-pages")
    ]

    assert "with" not in configure


# ── How it is pinned, and where it is not ────────────────────────────────────────────────


def test_every_action_is_pinned_to_a_major_tag(pages: dict[Any, Any]) -> None:
    unpinned = [ref for ref in _uses(_steps(pages, DEPLOY_JOB)) if not _MAJOR_TAG.match(ref)]

    assert unpinned == []


def test_the_deployment_is_a_workflow_of_its_own_and_not_a_ci_job(ci: dict[Any, Any]) -> None:
    """The separation the contributor guide's job count depends on.

    `ci.yml` stays eighteen jobs of quality gates that need `contents: read` and nothing
    else (`tests/docs/test_contributor_guide.py` holds that number against the page). A
    deployment folded in there would have moved the count and carried `pages: write`
    through every pull-request run.
    """
    assert "pages" not in str(ci.get("permissions", ""))
    assert "deploy-pages" not in CI_WORKFLOW.read_text(encoding="utf-8")
    assert "docs" in ci["jobs"] and "deploy" not in ci["jobs"]
