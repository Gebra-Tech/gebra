"""Configuration tests for the toolchain quality gates (GOV-02).

SOW §4 states that every CI cell runs ``ruff check`` + ``ruff format --check``,
``mypy --strict`` and ``pytest``; SOW §5 requires the tool configuration to live in
``pyproject.toml`` alongside an ``.editorconfig``. These tests pin that
configuration so a gate cannot be dropped — from the CI workflow or from the tool
config — without a test turning red.

They read and parse files only: no build, no install, no import of a workflow, no
node execution, no LLM call, no socket (WA-07).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from coverage import Coverage

from tools import coverage_gate

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
EDITORCONFIG = REPO_ROOT / ".editorconfig"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(
    not PYPROJECT.is_file(),
    reason="toolchain-config tests describe the source tree; no pyproject.toml beside tests/",
)

VENDORED_FIXTURE_GLOB = "tests/fixtures/properties/**"


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


def _editorconfig_sections() -> dict[str, dict[str, str]]:
    """Parse ``.editorconfig`` into ``{glob: {key: value}}`` (preamble under ``""``)."""
    sections: dict[str, dict[str, str]] = {"": {}}
    current = ""
    for raw in EDITORCONFIG.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        key, _, value = line.partition("=")
        sections[current][key.strip().lower()] = value.strip()
    return sections


# ── The tool configuration (SOW §5: config in pyproject.toml + .editorconfig) ──


def test_mypy_runs_strict_over_source_and_tests(pyproject: dict[str, Any]) -> None:
    """``mypy`` with no arguments is the gate, so the config carries every knob."""
    mypy = pyproject["tool"]["mypy"]
    assert mypy["strict"] is True
    # `tools` joined the scope with the provenance guard (GOV-09), and `.github` with the
    # CI-gate action's driver (TE-13): CI-executed tooling is checked as strictly as the
    # package.
    assert set(mypy["files"]) == {"src", "tests", "tools", ".github"}


def test_mypy_targets_the_declared_python_floor(pyproject: dict[str, Any]) -> None:
    """Type checking runs against the floor, not the interpreter that happens to run it."""
    floor = pyproject["project"]["requires-python"].lstrip(">=")
    assert pyproject["tool"]["mypy"]["python_version"] == floor


def test_dev_extra_carries_every_gate_tool(pyproject: dict[str, Any]) -> None:
    """Each gate is installable from the declared dev extra — CI installs nothing extra."""
    dev = pyproject["project"]["optional-dependencies"]["dev"]
    names = {re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0].lower() for requirement in dev}
    assert {"ruff", "mypy", "pytest", "pytest-cov", "types-pyyaml"} <= names


def test_coverage_configuration_is_loadable(pyproject: dict[str, Any]) -> None:
    """coverage.py reads its settings from pyproject.toml (branch coverage on ``gebra``).

    Constructing ``Coverage`` parses the configuration; it starts no measurement and
    runs no code.
    """
    assert "coverage" in pyproject["tool"]
    config = Coverage(config_file=str(PYPROJECT)).config
    assert config.branch is True
    assert config.source_pkgs == ["gebra"]


def test_the_coverage_threshold_lives_in_the_gate_not_in_fail_under(
    pyproject: dict[str, Any],
) -> None:
    """GOV-02 configured the coverage tooling; TE-12 armed the >80% gate — elsewhere.

    This replaces the earlier "threshold is not armed here" pin, and asserts the same
    absence for the opposite reason. ``fail_under`` is one number over everything measured,
    compared with ``>=``; the briefs ask for three named surfaces each strictly above 80%
    (D-09 Deliverable 6, D-10 Deliverable 8, SOW §2). A project total can sit well above the
    floor while one of those surfaces rots underneath it, so the threshold lives in
    ``tools/coverage_gate.py`` — which is where a reader must find one number, not two.
    """
    assert "fail_under" not in pyproject["tool"]["coverage"].get("report", {})
    assert coverage_gate.THRESHOLD == 80.0


# ── .editorconfig (SOW §5 repo conventions) ──


def test_editorconfig_is_present_and_rooted() -> None:
    assert EDITORCONFIG.is_file()
    assert _editorconfig_sections()[""]["root"] == "true"


def test_editorconfig_python_width_matches_ruff(pyproject: dict[str, Any]) -> None:
    """An editor and ``ruff format`` must not disagree about the line width."""
    python_section = _editorconfig_sections()["*.py"]
    assert int(python_section["max_line_length"]) == pyproject["tool"]["ruff"]["line-length"]


def test_editorconfig_leaves_the_vendored_corpus_alone() -> None:
    """Whitespace normalization of a byte-copy vendored fixture is an edit (WA-04/WA-11)."""
    section = _editorconfig_sections()[VENDORED_FIXTURE_GLOB]
    assert section["trim_trailing_whitespace"] == "unset"
    assert section["insert_final_newline"] == "unset"


def test_ruff_does_not_format_the_vendored_corpus(pyproject: dict[str, Any]) -> None:
    """The same exclusion holds for the formatter now that ``--check`` gates CI."""
    assert "tests/fixtures/properties" in pyproject["tool"]["ruff"]["extend-exclude"]


# ── The CI workflow actually runs the gates ──


def _workflow_run_steps() -> list[str]:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step.get("run"), str)
    ]


@pytest.mark.parametrize(
    "gate",
    [
        r"ruff check",
        r"ruff format --check",
        r"\bmypy\b",
        r"\bpytest\b",
    ],
)
def test_ci_workflow_runs_the_gate(gate: str) -> None:
    """SOW §4: the four gates run in CI. Dropping one from ci.yml fails here."""
    pattern = re.compile(gate)
    assert any(pattern.search(step) for step in _workflow_run_steps()), (
        f"no CI step runs {gate!r} — SOW §4 requires it on every cell"
    )


def test_ci_workflow_measures_coverage() -> None:
    """The coverage configuration is exercised by a CI job, not merely present."""
    assert any("coverage run -m pytest" in step for step in _workflow_run_steps())


def test_ci_measures_coverage_before_pytest_starts() -> None:
    """The measurement mode is load-bearing for the plugin scope, so it is pinned (TE-12).

    ``gebra.pytest_plugin`` is a ``pytest11`` entry point: pytest imports it while loading
    plugins, before ``pytest-cov`` would start measuring. Under ``pytest --cov`` its
    module-level statements are recorded as never executed and the scope reads 18.9 points
    low. Switching the job back to ``--cov`` fails here — and would anyway be refused by the
    gate itself, which detects the mis-measurement rather than scoring it.
    """
    measuring = [step for step in _workflow_run_steps() if "coverage run" in step]
    assert measuring, "no CI step measures coverage with `coverage run`"
    assert not any("--cov" in step for step in _workflow_run_steps())


def test_ci_runs_the_coverage_gate() -> None:
    """SOW §2's supporting fact is enforced by a step, not by looking at the report."""
    assert any("tools/coverage_gate.py" in step for step in _workflow_run_steps())
