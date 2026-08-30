"""Behaviour tests for the coverage gate (TE-12; briefs D-09/D-10, SOW §2).

The gate enforces one mandate — ``gebra.verify``, ``gebra.testing`` and the pytest plugin each
stay **strictly above 80%** — and these tests pin what that means where it matters: a scope
one point under the floor turns CI red and says which scope and why; a scope sitting at
exactly 80.00% is *not* above 80% and fails too; and none of the ways a coverage run can go
wrong (missing report, no branch data, a scope that matched nothing, a report measured after
pytest imported the plugin) is ever reported as a pass.

The reports here are synthetic by design. A test that had to run the real suite to observe
a red gate could only ever observe today's number; assembling coverage.py's own report shape
lets each clause of the mandate be exercised exactly, in milliseconds, including the ones the
repository is nowhere near. The counterpart — that the *real* numbers clear the floor — is
the card's second acceptance box and is observed by running the gate on a real measurement,
which is also what CI's ``test-locked`` job does on every push.

Everything here reads and writes text files and runs the gate script. No workflow node is
executed, no LLM is called, no socket is opened (WA-07).
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from coverage.config import DEFAULT_EXCLUDE
from coverage.results import Numbers

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

from tools.coverage_gate import (
    GATED_SCOPES,
    PLUGIN_SCOPE,
    PRAGMA_PATTERN,
    THRESHOLD,
    CoverageDataError,
    PragmaViolation,
    Scope,
    gate,
    load_report,
    main,
    measure,
    scan_pragmas,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "tools" / "coverage_gate.py"
DOC = REPO_ROOT / "docs" / "governance" / "coverage-gate.md"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

VERIFY_FILE = "src/gebra/verify/run.py"
TESTING_FILE = "src/gebra/testing/harness.py"
PLUGIN_FILE = "src/gebra/pytest_plugin.py"


# ── Building coverage.py's report shape ──────────────────────────────────────────────────


def _entry(
    statements: int,
    covered: int,
    branches: int = 0,
    covered_branches: int = 0,
    *,
    measured_late: bool = False,
) -> dict[str, Any]:
    """One ``files[...]`` entry, shaped like ``coverage json`` writes it.

    ``measured_late`` reproduces the ``pytest --cov`` signature for the plugin module: the
    module body ran during plugin loading, before measurement started, so the file's first
    statement is recorded as missing rather than executed.
    """
    missing = statements - covered
    if measured_late:
        missing_lines = list(range(1, missing + 1))
        executed_lines = list(range(missing + 1, missing + covered + 1))
    else:
        executed_lines = list(range(1, covered + 1))
        missing_lines = list(range(covered + 1, covered + missing + 1))
    measured = statements + branches
    percent = 100.0 * (covered + covered_branches) / measured if measured else 0.0
    return {
        "executed_lines": executed_lines,
        "missing_lines": missing_lines,
        "excluded_lines": [],
        "summary": {
            "covered_lines": covered,
            "num_statements": statements,
            "percent_covered": percent,
            "percent_covered_display": f"{percent:.0f}",
            "missing_lines": missing,
            "excluded_lines": 0,
            "num_branches": branches,
            "num_partial_branches": 0,
            "covered_branches": covered_branches,
            "missing_branches": branches - covered_branches,
        },
    }


def _report(files: dict[str, dict[str, Any]], *, branch_coverage: bool = True) -> dict[str, Any]:
    return {
        "meta": {"format": 3, "version": "7.15.2", "branch_coverage": branch_coverage},
        "files": files,
        "totals": {"covered_lines": 0, "num_statements": 0, "percent_covered": 0.0},
    }


def _healthy_files(**overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every gated scope comfortably above the floor, plus one file outside every scope."""
    files = {
        VERIFY_FILE: _entry(100, 95),
        TESTING_FILE: _entry(100, 94),
        PLUGIN_FILE: _entry(100, 92),
        "src/gebra/ir/models.py": _entry(100, 10),
    }
    files.update(overrides)
    return files


def _write(tmp_path: Path, report: dict[str, Any], name: str = "coverage.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A minimal tree carrying the gated scopes, so the exemption scan has sources to read."""
    for scope in GATED_SCOPES:
        directory = tmp_path / scope.source_dir
        directory.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/gebra/verify/run.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src/gebra/testing/harness.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / PLUGIN_FILE).write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


def _run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the gate exactly as CI runs it — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_gate_on(checkout: Path, report_path: Path) -> subprocess.CompletedProcess[str]:
    """The same, pointed at a scratch checkout so the real tree's state cannot change a verdict."""
    return _run_gate("--report", str(report_path), "--root", str(checkout))


# ── The mandate: strictly above 80%, per scope ───────────────────────────────────────────


def test_the_threshold_is_the_briefs_floor() -> None:
    """D-09 Deliverable 6, D-10 Deliverable 8 and SOW §2 all say 80%; nothing else may."""
    assert THRESHOLD == 80.0


def test_the_gated_scopes_are_the_three_the_card_names() -> None:
    assert [scope.name for scope in GATED_SCOPES] == [
        "gebra.verify",
        "gebra.testing",
        "gebra.pytest_plugin",
    ]


@pytest.mark.parametrize(
    ("scope_name", "path"),
    [
        ("gebra.verify", VERIFY_FILE),
        ("gebra.testing", TESTING_FILE),
        ("gebra.pytest_plugin", PLUGIN_FILE),
    ],
)
def test_a_scope_below_the_floor_fails_and_is_named(
    checkout: Path, scope_name: str, path: str
) -> None:
    """Acceptance box 1, per scope: one thin surface is enough to fail the gate."""
    report_path = _write(checkout, _report(_healthy_files(**{path: _entry(100, 79)})))

    result = gate(load_report(report_path), checkout, report_path)

    assert not result.ok
    assert [failed.scope.name for failed in result.failing] == [scope_name]


def test_exactly_at_the_floor_is_not_above_it(checkout: Path) -> None:
    """The briefs wrote ``> 80%``. 80.00% is the boundary case, and it fails."""
    report_path = _write(checkout, _report(_healthy_files(**{VERIFY_FILE: _entry(100, 80)})))

    result = gate(load_report(report_path), checkout, report_path)

    assert not result.ok
    assert result.failing[0].totals.percent == pytest.approx(80.0)


def test_a_hair_above_the_floor_passes(checkout: Path) -> None:
    report_path = _write(checkout, _report(_healthy_files(**{VERIFY_FILE: _entry(1000, 801)})))

    result = gate(load_report(report_path), checkout, report_path)

    assert result.ok
    assert result.scopes[0].totals.percent == pytest.approx(80.1)


def test_a_healthy_report_passes_and_carries_the_context_total(checkout: Path) -> None:
    report_path = _write(checkout, _report(_healthy_files()))

    result = gate(load_report(report_path), checkout, report_path)

    assert result.ok
    assert result.project_files == 4
    # The ungated `ir/models.py` at 10% drags the project number down without failing the
    # gate: the project total is context, and the three named scopes are the verdict.
    assert result.project.percent == pytest.approx(72.75)


# ── The exit status CI reads ─────────────────────────────────────────────────────────────


def test_the_script_exits_1_below_the_floor(checkout: Path) -> None:
    """The proof CI is entitled to: the command in ci.yml, run, exiting non-zero."""
    report_path = _write(checkout, _report(_healthy_files(**{TESTING_FILE: _entry(100, 55)})))

    completed = _run_gate_on(checkout, report_path)

    assert completed.returncode == 1
    assert "coverage gate: FAILED" in completed.stderr
    assert "gebra.testing is at 55.00%" in completed.stderr
    assert completed.stdout == ""


def test_the_script_exits_0_above_the_floor(checkout: Path) -> None:
    report_path = _write(checkout, _report(_healthy_files()))

    completed = _run_gate_on(checkout, report_path)

    assert completed.returncode == 0, completed.stderr
    assert "coverage gate: OK" in completed.stdout


def test_the_script_reports_every_failing_scope_not_just_the_first(checkout: Path) -> None:
    report_path = _write(
        checkout,
        _report(_healthy_files(**{VERIFY_FILE: _entry(100, 20), TESTING_FILE: _entry(100, 30)})),
    )

    completed = _run_gate_on(checkout, report_path)

    assert completed.returncode == 1
    assert "gebra.verify is at" in completed.stderr
    assert "gebra.testing is at" in completed.stderr


# ── No verdict is never a pass (exit 2) ──────────────────────────────────────────────────


def test_a_missing_report_is_no_verdict(tmp_path: Path) -> None:
    completed = _run_gate("--report", str(tmp_path / "absent.json"))

    assert completed.returncode == 2
    assert "no verdict" in completed.stderr


def test_an_unparsable_report_is_no_verdict(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text("{not json", encoding="utf-8")

    completed = _run_gate("--report", str(path))

    assert completed.returncode == 2
    assert "unreadable coverage report" in completed.stderr


def test_a_report_without_branch_coverage_is_no_verdict(checkout: Path) -> None:
    """``branch = true`` is what the gated percentage means; a flat report is a different number."""
    report_path = _write(checkout, _report(_healthy_files(), branch_coverage=False))

    with pytest.raises(CoverageDataError, match="without branch coverage"):
        load_report(report_path)


def test_a_scope_that_matched_no_file_is_no_verdict(checkout: Path) -> None:
    """A renamed tree must go red, never vacuously green on an empty scope."""
    files = _healthy_files()
    del files[TESTING_FILE]
    report_path = _write(checkout, _report(files))

    with pytest.raises(CoverageDataError, match="gebra.testing matched no measured file"):
        gate(load_report(report_path), checkout, report_path)


def test_a_root_without_the_gated_sources_is_no_verdict(tmp_path: Path) -> None:
    """Pointed at the wrong checkout, the exemption scan would read nothing and say OK."""
    report_path = _write(tmp_path, _report(_healthy_files()))

    with pytest.raises(CoverageDataError, match="no gated source found"):
        gate(load_report(report_path), tmp_path, report_path)


def test_an_empty_files_map_is_no_verdict(checkout: Path) -> None:
    report_path = _write(checkout, _report({}))

    with pytest.raises(CoverageDataError, match="matched no measured file"):
        gate(load_report(report_path), checkout, report_path)


def test_a_malformed_file_entry_is_no_verdict(checkout: Path) -> None:
    files = _healthy_files()
    files[VERIFY_FILE] = {"summary": {"covered_lines": 1}}
    report_path = _write(checkout, _report(files))

    with pytest.raises(CoverageDataError, match="num_statements"):
        gate(load_report(report_path), checkout, report_path)


# ── The measurement mode the plugin scope depends on ─────────────────────────────────────


def test_a_report_measured_after_plugin_import_is_refused(checkout: Path) -> None:
    """``pytest --cov`` under-measures a pytest11 plugin; the gate refuses to score it.

    The plugin module is imported while pytest loads plugins — before pytest-cov starts — so
    its module-level statements read as never executed and the scope loses 18.9 points to a
    measurement artifact. Failing on that number would be a red the gate cannot justify, and
    passing on it would be luck, so it is a no-verdict.
    """
    files = _healthy_files(**{PLUGIN_FILE: _entry(100, 92, measured_late=True)})
    report_path = _write(checkout, _report(files))

    with pytest.raises(CoverageDataError, match="only after pytest had imported it"):
        gate(load_report(report_path), checkout, report_path)


def test_the_refusal_names_the_command_that_measures_it_correctly(checkout: Path) -> None:
    files = _healthy_files(**{PLUGIN_FILE: _entry(100, 92, measured_late=True)})
    report_path = _write(checkout, _report(files))

    with pytest.raises(CoverageDataError, match=r"coverage run -m pytest"):
        gate(load_report(report_path), checkout, report_path)


def test_a_plugin_with_nothing_executed_is_the_same_refusal(checkout: Path) -> None:
    """The extreme case: a session running pytest has the module imported by definition.

    Zero executed lines is that mis-measurement at its limit, not "a plugin nobody tested",
    so it takes the same no-verdict exit rather than failing as a 0% scope.
    """
    files = _healthy_files(**{PLUGIN_FILE: _entry(100, 0)})
    report_path = _write(checkout, _report(files))

    with pytest.raises(CoverageDataError, match="only after pytest had imported it"):
        gate(load_report(report_path), checkout, report_path)


def test_a_correctly_measured_plugin_is_scored_normally(checkout: Path) -> None:
    report_path = _write(checkout, _report(_healthy_files()))

    result = gate(load_report(report_path), checkout, report_path)

    plugin = next(scope for scope in result.scopes if scope.scope.name == PLUGIN_SCOPE.name)
    assert plugin.ok
    assert plugin.totals.percent == pytest.approx(92.0)


# ── Aggregation: coverage.py's own arithmetic ────────────────────────────────────────────


def test_a_scope_percentage_is_coverage_pys_own_arithmetic(checkout: Path) -> None:
    """For a single-file scope the gate must print what ``coverage report`` prints.

    Checked against coverage.py itself — ``Numbers.pc_covered``, the class that computes the
    ``Cover`` column — rather than against this file's own copy of the formula, which would
    pass just as happily if both were wrong.
    """
    entry = _entry(640, 582, 214, 177)
    report_path = _write(checkout, _report(_healthy_files(**{PLUGIN_FILE: entry})))
    expected = Numbers(
        n_statements=640, n_missing=58, n_branches=214, n_missing_branches=37
    ).pc_covered

    result = measure(load_report(report_path))

    plugin = next(scope for scope in result.scopes if scope.scope.name == PLUGIN_SCOPE.name)
    assert plugin.totals.percent == pytest.approx(expected)


def test_branch_arcs_count_toward_the_gated_percentage(checkout: Path) -> None:
    """Statements alone would read 100%; the configured metric counts the untaken arcs."""
    report_path = _write(
        checkout, _report(_healthy_files(**{VERIFY_FILE: _entry(100, 100, 100, 50)}))
    )

    result = gate(load_report(report_path), checkout, report_path)

    verify = result.scopes[0]
    assert verify.totals.statement_percent == pytest.approx(100.0)
    assert verify.totals.percent == pytest.approx(75.0)
    assert not verify.ok


def test_scope_files_aggregate_by_size_not_by_file(checkout: Path) -> None:
    """A tiny 100% module cannot lift a large thin one — the sum is over statements."""
    files = _healthy_files(
        **{VERIFY_FILE: _entry(900, 630), "src/gebra/verify/tiny.py": _entry(4, 4)}
    )
    report_path = _write(checkout, _report(files))

    result = gate(load_report(report_path), checkout, report_path)

    assert result.scopes[0].totals.percent == pytest.approx(100.0 * 634 / 904)
    assert not result.ok


# ── Scope matching is anchored, and layout-independent ───────────────────────────────────


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/gebra/verify/run.py", True),
        ("src/gebra/verify/properties/effect_safety.py", True),
        ("/home/runner/.venv/lib/python3.13/site-packages/gebra/verify/run.py", True),
        ("gebra/verify/run.py", True),
        ("src/gebra/verifying/run.py", False),
        ("src/gebra/testing/harness.py", False),
        ("tests/verify/test_run.py", False),
    ],
)
def test_the_verify_scope_matches_exactly_its_package(path: str, expected: bool) -> None:
    assert GATED_SCOPES[0].matches(path) is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/gebra/pytest_plugin.py", True),
        ("/x/site-packages/gebra/pytest_plugin.py", True),
        ("src/gebra/pytest_plugin_helpers.py", False),
        ("tests/plugin/test_plugin.py", False),
        ("src/other/gebra_pytest_plugin.py", False),
    ],
)
def test_the_plugin_scope_matches_exactly_one_module(path: str, expected: bool) -> None:
    assert PLUGIN_SCOPE.matches(path) is expected


def test_every_gated_scope_exists_in_this_checkout() -> None:
    """If a scope's tree is renamed, this fails here rather than emptying the gate silently."""
    for scope in GATED_SCOPES:
        assert scope.source_files(REPO_ROOT), f"{scope.name} has no sources under {REPO_ROOT}"


# ── The exemption policy ─────────────────────────────────────────────────────────────────


def test_the_pragma_pattern_is_coverage_pys_own() -> None:
    """The policy must police every spelling coverage.py honours, or it is a bypass.

    The gate carries a copy of the pattern to stay dependency-free; this holds the copy
    equal to the installed library's default, so a coverage.py release that broadened the
    spelling turns this red instead of quietly opening a hole.
    """
    assert PRAGMA_PATTERN.pattern in DEFAULT_EXCLUDE


@pytest.mark.parametrize(
    "pragma",
    [
        "# pragma: no cover",
        "# pragma:no cover",
        "# pragma no cover",
        "# pragma:  no cover",
        "#pragma: no cover",
        "# PRAGMA: NO COVER",
    ],
)
def test_every_spelling_coverage_py_excludes_is_policed(checkout: Path, pragma: str) -> None:
    """Each of these excludes the line in coverage.py, so each must need a reason here."""
    line = f"x = 1  {pragma}"
    assert any(re.search(pattern, line) for pattern in DEFAULT_EXCLUDE)
    (checkout / VERIFY_FILE).write_text(line + "\n", encoding="utf-8")

    scan = scan_pragmas(checkout)

    assert scan.pragmas == 1, f"{pragma!r} was not recognised as an exclusion"
    assert len(scan.violations) == 1


def test_a_spelling_coverage_py_ignores_is_not_policed_either(checkout: Path) -> None:
    """Lockstep runs both ways: mixed case excludes nothing, so it hides nothing.

    ``#\\s*(pragma|PRAGMA)...`` admits all-lower and all-upper only. A line coverage.py
    still measures is not an exemption, and reporting it as one would be a false red.
    """
    line = "x = 1  # Pragma: no COVER"
    assert not any(re.search(pattern, line) for pattern in DEFAULT_EXCLUDE)
    (checkout / VERIFY_FILE).write_text(line + "\n", encoding="utf-8")

    assert scan_pragmas(checkout).pragmas == 0


@pytest.mark.parametrize(
    "trailer",
    ["# noqa: E501", "# type: ignore[misc]", "#comment"],
)
def test_a_machine_directive_is_not_a_reason(checkout: Path, trailer: str) -> None:
    """The policy asks for prose. Another comment marker is a tool talking, not a human."""
    (checkout / VERIFY_FILE).write_text(f"x = 1  # pragma: no cover  {trailer}\n", encoding="utf-8")

    scan = scan_pragmas(checkout)

    assert len(scan.violations) == 1


def test_a_reason_followed_by_a_machine_directive_is_still_a_reason(checkout: Path) -> None:
    (checkout / VERIFY_FILE).write_text(
        "x = 1  # pragma: no cover - the substrate never returns here  # noqa: E501\n",
        encoding="utf-8",
    )

    assert scan_pragmas(checkout).violations == ()


def test_an_unreadable_gated_source_is_no_verdict(checkout: Path) -> None:
    """A scan that could not read is not a scan that found nothing."""
    (checkout / VERIFY_FILE).write_bytes(b"x = '\xff\xfe'\n")
    report_path = _write(checkout, _report(_healthy_files()))

    with pytest.raises(CoverageDataError, match="unreadable gated source"):
        gate(load_report(report_path), checkout, report_path)


def test_a_bare_pragma_in_a_gated_scope_is_a_violation(checkout: Path) -> None:
    (checkout / VERIFY_FILE).write_text(
        "def f(x):\n    if x:  # pragma: no cover\n        return 1\n    return 0\n",
        encoding="utf-8",
    )

    scan = scan_pragmas(checkout)

    assert scan.pragmas == 1
    assert scan.violations == (
        PragmaViolation(
            path="src/gebra/verify/run.py",
            line_no=2,
            text="if x:  # pragma: no cover",
        ),
    )


@pytest.mark.parametrize(
    "pragma",
    [
        "# pragma: no cover - the substrate always sets one",
        "# pragma: no cover — unreachable: the component is non-trivial",
        "# pragma: no cover: defensive, see above",
        "# pragma: no cover  exercised on the 3.10 matrix cells",
        "# noqa: BLE001  # pragma: no cover - defensive",
    ],
)
def test_a_pragma_with_a_reason_is_allowed(checkout: Path, pragma: str) -> None:
    """Any separator reads as one; what the policy requires is that a human wrote why."""
    (checkout / VERIFY_FILE).write_text(f"def f():\n    return 1  {pragma}\n", encoding="utf-8")

    scan = scan_pragmas(checkout)

    assert scan.pragmas == 1
    assert scan.violations == ()


def test_a_bare_pragma_fails_the_gate_even_with_every_scope_green(checkout: Path) -> None:
    """Acceptance box 1's other half: an unexplained exemption is a hole in the floor."""
    (checkout / TESTING_FILE).write_text("x = 1  # pragma: no cover\n", encoding="utf-8")
    report_path = _write(checkout, _report(_healthy_files()))

    result = gate(load_report(report_path), checkout, report_path)

    assert not result.failing
    assert not result.ok
    assert len(result.pragmas.violations) == 1


def test_an_ungated_scope_is_not_policed(checkout: Path) -> None:
    """The rule binds the surfaces this gate answers for; it is not a repo-wide edict."""
    outside = checkout / "src/gebra/ir"
    outside.mkdir(parents=True)
    (outside / "models.py").write_text("x = 1  # pragma: no cover\n", encoding="utf-8")

    assert scan_pragmas(checkout).violations == ()


def test_this_repository_states_a_reason_for_every_exemption_today() -> None:
    """The premise of the policy: the gated scopes are already compliant, and stay so."""
    scan = scan_pragmas(REPO_ROOT)

    assert scan.violations == ()
    assert scan.pragmas > 0
    assert scan.files > 0


# ── WA-07: the gate itself reaches nothing ───────────────────────────────────────────────


ALLOWED_GATE_IMPORTS = {
    "__future__",
    "argparse",
    "collections",
    "dataclasses",
    "json",
    "pathlib",
    "re",
    "sys",
    "typing",
}


def test_the_gate_imports_stdlib_only() -> None:
    """The module's WA-07 claim, held by a sweep rather than by its own docstring.

    Same guard as the CI-gate action's driver (TE-13): importing this module must reach no
    gebra code, no substrate and no network client — and it must keep running when the
    environment under measurement is broken, which is exactly when a coverage report is
    worth reading.
    """
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None and node.level == 0
            imported.add(node.module.partition(".")[0])
    assert imported <= ALLOWED_GATE_IMPORTS
    assert "gebra" not in imported and "coverage" not in imported


def test_the_gate_opens_no_file_for_writing() -> None:
    """It reads a report and some sources; a CI gate that rewrote either would be a hazard."""
    source = GATE.read_text(encoding="utf-8")
    assert "write_text" not in source
    assert "open(" not in source
    assert "subprocess" not in source


# ── The command-line surface ─────────────────────────────────────────────────────────────


def test_main_defaults_to_coverage_json_under_the_root(checkout: Path) -> None:
    _write(checkout, _report(_healthy_files()))

    assert main(["--root", str(checkout)]) == 0


def test_main_returns_2_when_the_default_report_is_absent(checkout: Path) -> None:
    assert main(["--root", str(checkout)]) == 2


def test_there_is_no_threshold_flag() -> None:
    """Lowering the floor is a frozen-brief question (WA-03), not a command-line option."""
    completed = _run_gate("--threshold", "50")

    assert completed.returncode == 2
    assert "unrecognized arguments" in completed.stderr


def test_a_scope_needle_is_derived_from_the_dotted_name() -> None:
    assert Scope("gebra.verify", "package", "").needle == "gebra/verify/"
    assert Scope("gebra.pytest_plugin", "module", "").needle == "gebra/pytest_plugin.py"


# ── The documentation says what the gate does ────────────────────────────────────────────


@pytest.fixture(scope="module")
def gate_doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_doc_names_every_gated_scope(gate_doc: str) -> None:
    """A scope added to the gate without a line in the policy page fails here."""
    for scope in GATED_SCOPES:
        assert f"`{scope.name}`" in gate_doc


def test_the_doc_states_the_shipped_threshold(gate_doc: str) -> None:
    assert f"{THRESHOLD:g}%" in gate_doc
    assert "strictly" in gate_doc


def test_the_doc_prints_the_commands_ci_runs(gate_doc: str) -> None:
    """The reproduction recipe is the CI recipe, or the page is telling a nicer story."""
    for command in ("coverage run -m pytest", "coverage json", "python tools/coverage_gate.py"):
        assert command in gate_doc
        assert command in CI_WORKFLOW.read_text(encoding="utf-8")


def test_the_doc_lists_the_structural_exclusions_that_are_configured() -> None:
    """`exclude_also` is half the exemption policy; the page must carry what it says."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        configured = tomllib.load(handle)["tool"]["coverage"]["report"]["exclude_also"]
    # The page quotes the TOML *source*, where a backslash is doubled; compare against the
    # parsed patterns by undoing that one escape.
    documented = DOC.read_text(encoding="utf-8").replace("\\\\", "\\")
    for pattern in configured:
        assert pattern in documented, f"{pattern!r} is excluded in config but not documented"


def test_the_doc_carries_the_exit_status_vocabulary(gate_doc: str) -> None:
    for phrase in ("`0`", "`1`", "`2`", "no verdict"):
        assert phrase in gate_doc


def test_contributing_points_at_the_policy_and_states_the_floor() -> None:
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "docs/governance/coverage-gate.md" in contributing
    assert "80%" in contributing
    # The pre-TE-12 sentence, which was true then and would be a false claim now.
    assert "No minimum is enforced yet" not in contributing
