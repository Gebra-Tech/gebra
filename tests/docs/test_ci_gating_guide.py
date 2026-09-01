"""``docs/guides/pytest-plugin-and-ci-gating.md`` pinned to the shapes it documents (DOC-13).

The guide takes a team from one dependency to a merge gate, so every copyable thing on it is
something this repository actually runs, and every claim about what each rung blocks is a
statement about code. Prose cannot hold itself to any of that, so this module does:

* the two example files it reproduces are ``examples/ci_gate/`` verbatim, byte for byte;
* the workflow it prints is ``.github/workflows/gebra-gate-example.yml`` minus that file's
  final self-check step, structurally — and each rung's quoted step is that workflow's own
  step with the same ``id``;
* the interface table names every input the action declares, with the manifest's own default,
  and the mode-by-exit table is the driver's own translation rather than a transcription;
* the item ids the page shows are the ids pytest collects from that suite, and the failing
  item's message is the message the plugin renders;
* the severity mapping, the rollout order and the record-versus-gate boundary are read off the
  plugin rather than trusted (WA-06).

The module parses YAML and Markdown and runs pytest in a child process over the example
suite. It executes no workflow node: the agent those examples mark is the shared
sentinel-guarded travel-booking fixture, whose bodies record and raise if anything calls them,
so a child in which one ran could not report the verdicts asserted below (WA-07).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest
import yaml

from gebra.pytest_plugin import (
    BLOCKING_SEVERITIES,
    CHECK_PARAM,
    FRESHNESS_MARKER,
    MARKER,
    SELECT_OPTION,
    SKIP_OPTION,
    STRICT_OPTION,
    WORKFLOW_FIXTURE,
    enabled_properties,
)
from tools.honest_claims_lint import load_phrases, scan, scan_files

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "guides" / "pytest-plugin-and-ci-gating.md"
WORKFLOW: Final = REPO_ROOT / ".github" / "workflows" / "gebra-gate-example.yml"
ACTION_DIR: Final = REPO_ROOT / ".github" / "actions" / "gebra-gate"
SUITE: Final = REPO_ROOT / "examples" / "ci_gate"

#: The job the example workflow declares, and the local reference each rung step uses.
JOB: Final = "gebra-gate-example"
GATE_USES: Final = "./.github/actions/gebra-gate"

#: The example files the page reproduces verbatim, in the order it shows them.
REPRODUCED_FILES: Final[tuple[str, ...]] = ("conftest.py", "test_agent.py")


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(page_text: str) -> str:
    """The page with every run of whitespace collapsed, for sentence-level assertions.

    A sentence this module pins may be re-wrapped by an editor without changing a word, and a
    check that broke on a line break would be a check on the paragraph shape rather than on
    the claim. Table and fence assertions read ``page_text`` instead, where layout is content.
    """
    return re.sub(r"\s+", " ", page_text)


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _triggers(document: dict[Any, Any]) -> Any:
    """A workflow's ``on:`` block.

    Asked for under both spellings because PyYAML resolves a bare ``on`` key to the boolean
    ``True`` (YAML 1.1's implicit typing), which GitHub Actions files hit every time.
    """
    return document["on"] if "on" in document else document[True]


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    parsed = yaml.safe_load((ACTION_DIR / "action.yml").read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    """The action's driver, imported from its file — ``.github/`` is no package.

    The same recipe ``tests/action/conftest.py`` uses, restated here rather than imported
    across test packages: that fixture is package-scoped to ``tests/action``.
    """
    spec = importlib.util.spec_from_file_location("gebra_gate_driver_docs", ACTION_DIR / "gate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fences(text: str, language: str) -> list[str]:
    """Every fenced block of one language on the page, in document order."""
    return re.findall(rf"```{language}\n(.*?)```", text, flags=re.DOTALL)


def _table_rows(text: str, header: str) -> list[list[str]]:
    """The body cells of the pipe table whose header line is ``header``, row by row."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        rows = []
        for candidate in lines[index + 2 :]:  # +2 skips the alignment row
            if not candidate.startswith("|"):
                break
            rows.append([cell.strip() for cell in candidate.strip("|").split("|")])
        return rows
    raise AssertionError(f"no table with header {header!r}")


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = workflow["jobs"][JOB]["steps"]
    return steps


def _run_pytest(*arguments: str) -> subprocess.CompletedProcess[str]:
    """pytest over the example suite, in a child process, from the repository root."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# ── The example suite the page reproduces ────────────────────────────────────────────────


def test_the_page_reproduces_the_example_files_verbatim(page_text: str) -> None:
    """A snippet a reader copies is the file CI runs, not a retelling of it."""
    fences = _fences(page_text, "python")
    for name in REPRODUCED_FILES:
        source = (SUITE / name).read_text(encoding="utf-8")
        assert source in fences, f"examples/ci_gate/{name} is not reproduced verbatim"


def test_the_deliberately_failing_module_is_outside_testpaths() -> None:
    """A module that fails its gate on purpose must never be collected by a bare ``pytest``."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'testpaths = ["tests"]' in pyproject
    assert (SUITE / "test_unprotected_retry.py").is_file()
    assert SUITE.relative_to(REPO_ROOT).parts[0] == "examples"


def test_the_item_ids_the_page_shows_are_the_ids_pytest_collects(page_text: str) -> None:
    """The parametrization spelling, taken from a real collection rather than described."""
    collected = _run_pytest("--collect-only", "-q", str(SUITE / "test_agent.py"))
    assert collected.returncode == 0, collected.stdout + collected.stderr

    ids = [
        line.split("::", 1)[1]
        for line in collected.stdout.splitlines()
        if line.startswith("examples/ci_gate/test_agent.py::test_gebra[")
    ]
    assert ids == [f"test_gebra[travel_agent-{slug}]" for slug in enabled_properties()]
    for item in ids:
        assert item in page_text, item


def test_the_failing_items_message_is_the_message_the_plugin_renders(page_text: str) -> None:
    """The excerpt of a red build is quoted from one, not written for the page."""
    finished = _run_pytest("-q", str(SUITE / "test_unprotected_retry.py"))
    assert finished.returncode == 1, finished.stdout + finished.stderr

    quoted = [
        "gebra · unprotected_retry · effect-safety",
        "ERROR unprotected-effect-in-retry-region [defensible-a]",
    ]
    for line in quoted:
        assert line in page_text, line
        assert line in finished.stdout, line
    assert "at node 'book_flight'" in finished.stdout


# ── The workflow, and the three rungs quoted from it ─────────────────────────────────────


def test_every_yaml_fence_parses(page_text: str) -> None:
    """Parsed, never executed — a fence that stopped being YAML fails the page."""
    fences = _fences(page_text, "yaml")
    assert len(fences) >= 5, "the page lost its workflow examples"
    for fence in fences:
        yaml.safe_load(fence)


def test_the_documented_workflow_is_the_real_one_without_its_self_check(
    page_text: str, workflow: dict[str, Any]
) -> None:
    """The page's complete workflow equals the file, minus that file's last step.

    The omitted step is the one that compares each rung's outcome against this page; it is
    machinery for keeping the page honest rather than something an adopter copies, and the
    page says so. Everything above it is equal, structurally — comments and formatting are
    the page's own, the steps are not.
    """
    documented = [
        yaml.safe_load(fence)
        for fence in _fences(page_text, "yaml")
        if isinstance(yaml.safe_load(fence), dict) and "jobs" in yaml.safe_load(fence)
    ]
    assert len(documented) == 1, "the page must print exactly one complete workflow"
    shown = documented[0]

    assert shown["name"] == workflow["name"]
    assert _triggers(shown) == _triggers(workflow) == {"push": None, "pull_request": None}
    assert shown["jobs"][JOB]["name"] == workflow["jobs"][JOB]["name"]
    assert shown["jobs"][JOB]["runs-on"] == workflow["jobs"][JOB]["runs-on"]
    assert shown["jobs"][JOB]["steps"] == _steps(workflow)[:-1]


def test_each_rung_quotes_its_own_step_of_that_workflow(
    page_text: str, workflow: dict[str, Any]
) -> None:
    """One rung section, one real step — matched by the step id the page shows."""
    by_id = {step["id"]: step for step in _steps(workflow) if "id" in step}
    assert set(by_id) == {"report_only", "gate", "strict"}

    quoted = [
        parsed[0]
        for fence in _fences(page_text, "yaml")
        if isinstance(parsed := yaml.safe_load(fence), list) and len(parsed) == 1
    ]
    shown = {step["id"]: step for step in quoted if isinstance(step, dict) and "id" in step}

    assert shown == by_id


def test_every_rung_step_runs_the_local_action(workflow: dict[str, Any]) -> None:
    """The workflow gates through the shipped action rather than calling pytest itself."""
    gate_steps = [step for step in _steps(workflow) if step.get("uses") == GATE_USES]

    assert len(gate_steps) == 3
    assert [step["with"].get("mode", "gate") for step in gate_steps] == [
        "report-only",
        "gate",
        "strict",
    ]
    invocation = re.compile(r"(?m)^\s*(?:[\w./-]*python[\w.]*\s+-m\s+)?pytest\b")
    assert not [step for step in _steps(workflow) if invocation.search(str(step.get("run", "")))]


def test_the_workflow_checks_each_rung_against_what_the_page_documents(
    page_text: str, prose: str, workflow: dict[str, Any]
) -> None:
    """The last step is the page's warranty: the documented outcomes, asserted in CI.

    Read out of the step's own body, so a rung whose expected outcome was quietly relaxed
    there — or whose documented word moved here — fails rather than drifts.
    """
    check = _steps(workflow)[-1]
    expected = dict(re.findall(r'check "([^"]+)" "\$[A-Z_]+" "([^"]+)"', check["run"]))

    assert expected == {
        "report-only pytest exit": "1",
        "report-only outcome": "failures",
        "gate outcome": "pass",
        "strict outcome": "pass",
    }
    assert "`failures`" in page_text
    assert "A gate that checked nothing never passes" in prose


# ── The action's interface, and the ladder's translation table ───────────────────────────


def test_the_input_table_is_the_manifest(page_text: str, manifest: dict[str, Any]) -> None:
    """Every input, with the manifest's own default — a renamed input fails the build."""
    rows = _table_rows(page_text, "| input | default | meaning |")
    documented = {row[0]: row[1] for row in rows}

    assert set(documented) == {f"`{name}`" for name in manifest["inputs"]}
    for name, spec in manifest["inputs"].items():
        default = str(spec["default"])
        assert documented[f"`{name}`"] == (f"`{default}`" if default else '`""`'), name


def test_the_whole_output_and_mode_vocabulary_is_named(
    page_text: str, manifest: dict[str, Any], gate: ModuleType
) -> None:
    for name in manifest["outputs"]:
        assert f"`{name}`" in page_text, name
    for mode in gate.MODES:
        assert f"`{mode}`" in page_text, mode
    for outcome in gate.OUTCOMES:
        assert f"`{outcome}`" in page_text, outcome
    # The one number the page quotes about the step summary, read off the driver.
    assert f"{gate.SECTION_LINE_CAP}-line cap" in page_text


def test_the_exit_table_is_the_drivers_own_translation(page_text: str, gate: ModuleType) -> None:
    """Each row's meaning and both verdicts are computed, never transcribed."""
    rows = _table_rows(page_text, "| pytest exit | meaning | `report-only` | `gate` / `strict` |")
    documented = {int(row[0]): row for row in rows}

    assert set(documented) == set(gate.EXIT_MEANINGS)
    for exit_code, row in documented.items():
        assert row[1] == gate.EXIT_MEANINGS[exit_code], exit_code
        for column, mode in ((2, "report-only"), (3, "gate")):
            _outcome, step_exit = gate.outcome_for(mode, exit_code)
            verdict = "green" if step_exit == 0 else "red"
            assert verdict in row[column], (exit_code, mode)
            assert ("red" if verdict == "green" else "green") not in row[column]


def test_the_rollout_ladder_is_in_rollout_order(page_text: str) -> None:
    rungs = ("### 1. `report-only`", "### 2. `gate`", "### 3. `strict`")
    positions = [page_text.find(rung) for rung in rungs]

    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions)


# ── What the page says the plugin does, read off the plugin ──────────────────────────────


def test_the_severity_mapping_is_the_plugins_own(page_text: str, prose: str) -> None:
    """FATAL/ERROR block and WARNING does not — stated on the page, decided in the plugin."""
    assert BLOCKING_SEVERITIES == frozenset({"fatal", "error"})
    for severity in BLOCKING_SEVERITIES:
        assert f"**{severity.upper()}**" in page_text, severity
    assert "a **WARNING** finding is reported and gates nothing" in prose


def test_every_plugin_name_the_page_uses_is_the_shipped_spelling(page_text: str) -> None:
    """A renamed marker, fixture or flag fails here rather than misleading a reader."""
    for name in (
        f"@pytest.mark.{MARKER}",
        f"@pytest.mark.{FRESHNESS_MARKER}",
        WORKFLOW_FIXTURE,
        "gebra_graph",
        "gebra_verification",
        STRICT_OPTION,
        SELECT_OPTION,
        SKIP_OPTION,
    ):
        assert name in page_text, name
    # The parametrization argname is the plugin's; the page shows it only inside item ids.
    assert CHECK_PARAM == "gebra_check"


def test_the_record_boundary_and_the_witness_wording_hold(page_text: str, prose: str) -> None:
    """WA-06 on this page's own copy: promotion is a gate policy, never a re-grading."""
    assert "changes the gate, never the record" in prose
    assert "`severity: warning`" in page_text
    assert "**witness presence**" in prose
    assert "never a statement that a run halts" in prose


def test_the_example_suite_stays_inside_the_honest_claims_vocabulary() -> None:
    """WA-06 over the tree the default lint scope leaves out, held here permanently.

    ``tools/honest_claims_lint.py``'s DEFAULT_INCLUDE covers ``src/**``, ``docs/**`` and the
    top-level prose, not ``examples/**`` — whose docstrings are repo-authored prose a reader
    copies. The same posture ``tests/action/test_action_interface.py`` takes for ``.github/**``:
    the same scan, the same phrase list, on every run instead of a sweep by hand.
    """
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    include = ("examples/**/*.py", "examples/**/*.md")
    covered = set(scan_files(REPO_ROOT, include, ()))

    assert {f"examples/ci_gate/{name}" for name in (*REPRODUCED_FILES, "__init__.py")} <= covered
    report = scan(REPO_ROOT, phrases, include=include, exclude=())
    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]


def test_the_page_never_calls_a_deferred_property_checked(prose: str) -> None:
    """The eight properties outside this release are named as unchecked, never as passing."""
    assert "no item generated" in prose
    assert "never as a green check" in prose
    assert "A green run is green on five." in prose
