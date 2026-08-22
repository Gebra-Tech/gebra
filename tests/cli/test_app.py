"""The application shell — CLI-SPEC §1's surface and §3.4's exit-code discipline (CLI-04).

Everything here runs through :func:`gebra.cli.main`, the function the console script and
``python -m gebra.cli`` both name; one subprocess test proves that module-runner spelling
against a real interpreter, and one static test pins the ``[project.scripts]`` row so the
installed command is the same function.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import gebra
from gebra.cli.app import _command
from tests.cli.conftest import RunCli

REPO_ROOT = Path(__file__).parent.parent.parent

# ── §1.2/§1.3: the application level ─────────────────────────────────────────────────────


def test_version_prints_the_installed_version_on_stdout_and_exits_zero(run_cli: RunCli) -> None:
    result = run_cli("--version")
    assert result.exit_code == 0
    assert result.stdout == f"gebra {gebra.__version__}\n"
    assert result.stderr == ""


def test_application_help_exits_zero_and_lists_only_landed_verbs(run_cli: RunCli) -> None:
    """WA-12: the help surface names the verbs this build registers, not the roadmap.

    As of CLI-05 that is four of PD-033's five — ``verify``, ``snapshot``, ``diff`` and
    ``history``; ``display`` stays unadvertised until CLI-06 lands it.
    """
    result = run_cli("--help")
    assert result.exit_code == 0
    for landed in ("verify", "snapshot", "diff", "history"):
        assert f"\n  {landed}" in result.stdout, f"help does not list landed {landed!r}"
    assert "\n  display" not in result.stdout, "help advertises unlanded 'display'"


def test_h_is_the_short_help_spelling(run_cli: RunCli) -> None:
    assert run_cli("-h").exit_code == 0


def test_a_bare_invocation_is_a_usage_error_not_a_help_page(run_cli: RunCli) -> None:
    """§3.4: a missing required argument — the verb — is exit 2 with a stderr diagnostic."""
    result = run_cli()
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "usage error" in result.stderr


def test_an_unknown_verb_is_refused_with_a_suggestion(run_cli: RunCli) -> None:
    """§5.4: the vocabulary is the registered verbs; the sentence is a question."""
    result = run_cli("verfy", "x.yaml")
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "No such command 'verfy'." in result.stderr
    assert "Did you mean verify?" in result.stderr


def test_an_abbreviation_is_an_unknown_verb_not_a_match(run_cli: RunCli) -> None:
    """§1.2: no abbreviation matching — ``gebra ver`` is not ``verify``."""
    result = run_cli("ver", "x.yaml")
    assert result.exit_code == 2
    assert "No such command 'ver'." in result.stderr


def test_an_unknown_application_option_is_a_usage_error(run_cli: RunCli) -> None:
    result = run_cli("--versoin")
    assert result.exit_code == 2
    assert "--versoin" in result.stderr
    assert "Did you mean --version?" in result.stderr


def test_the_completion_pair_is_not_part_of_the_surface(run_cli: RunCli) -> None:
    """Appendix B OI-7, resolved as: the typer completion options do not exist here."""
    result = run_cli("--help")
    assert "--install-completion" not in result.stdout
    assert "--show-completion" not in result.stdout
    assert run_cli("--install-completion").exit_code == 2


def test_application_options_are_value_less() -> None:
    """The pre-parse reading takes the first ``-``-free token as the verb; that is sound
    only while no application-level option consumes a following value. Pinned here."""
    root = _command()
    for parameter in root.params:
        assert getattr(parameter, "is_flag", False) or parameter.name == "help", (
            f"application option {parameter.name!r} takes a value; the verb detection in "
            "gebra.cli.invocation must learn to skip it before this can land"
        )


# ── §3.4: interrupts and crashes ─────────────────────────────────────────────────────────


def _app_module() -> object:
    """The ``gebra.cli.app`` **module** — by ``sys.modules``, because the package re-exports
    a Typer instance under the same name and attribute access finds that instead."""
    return sys.modules["gebra.cli.app"]


def test_sigint_is_exit_130(run_cli: RunCli, monkeypatch: pytest.MonkeyPatch) -> None:
    """§3.4: an interrupt is the shell convention, outside §0.2's three codes."""

    def interrupt(request: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(_app_module(), "run_verify", interrupt)
    result = run_cli("verify", "x.yaml")
    assert result.exit_code == 130


def test_a_crash_is_exit_2_with_the_traceback_and_an_invitation(
    run_cli: RunCli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3.4: an unhandled exception is a tool error with the traceback — never a clean run."""

    def crash(request: object) -> int:
        raise RuntimeError("wired to crash by the test")

    monkeypatch.setattr(_app_module(), "run_verify", crash)
    result = run_cli("verify", "x.yaml")
    assert result.exit_code == 2
    assert "Traceback" in result.stderr
    assert "wired to crash by the test" in result.stderr
    assert "crash, not a verification result" in result.stderr
    assert "https://github.com/Gebra-Tech/gebra/issues" in result.stderr


# ── The entry points are one function ────────────────────────────────────────────────────


def test_the_console_script_names_main() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.scripts]" in pyproject
    assert 'gebra = "gebra.cli:main"' in pyproject


def test_python_dash_m_runs_the_same_entry_point() -> None:
    """``python -m gebra.cli --version`` in a real interpreter, exit code included."""
    finished = subprocess.run(
        [sys.executable, "-m", "gebra.cli", "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == f"gebra {gebra.__version__}\n"
