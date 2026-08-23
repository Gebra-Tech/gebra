"""Shared plumbing for the CLI integration suite (card CLI-07).

The unit suites beside this one drive :func:`gebra.cli.main` in process; the integration
suite's spine runs the CLI as a **real child process** — brief D-12's artifact table names
the suite "subprocess tests against the fixture corpus" — so the claims here are about the
shipped process surface: real ``argv``, real streams, real exit codes, through the same
entry points a user has (``python -m gebra.cli``, and the installed ``gebra`` console
script, which name one function — CLI-SPEC §1.2, ``pyproject.toml``).

Two disciplines live here so every test in the suite inherits them:

* **Hermetic children.** The terminal variables ``rich`` honours are stripped from every
  child's environment (the same set ``tests/cli/conftest.py`` strips for in-process runs),
  so renderings are plain, 80 columns, runner-independent — which is what makes goldens
  byte-stable. The repository root is prepended to ``PYTHONPATH`` so import-reference
  targets (``tests.sample_workflows...``) resolve from any working directory; CLI-SPEC §2.4
  is explicit that ``PYTHONPATH`` behaves for the CLI as it does for any Python program.
* **The WA-06 sweep.** Every stream every child produces is swept against the TE-15
  banned-phrase list before the result is handed to a test — the card's "no banned phrases
  in any captured output" acceptance box held structurally over the whole suite, not spot-
  checked. The list is loaded through the lint's own loader, so the sweep tracks the file
  CI reads (the CLI-03 precedent).

Never-invokes posture (WA-07): nothing here adds an extraction path — every invocation
drives the shipped verbs over the boundaries CLI-04/CLI-05 landed tripwires for. The live
targets the suite names are the sentinel-guarded travel-booking modules, whose every body
records and raises a ``BaseException``; a body running inside a child therefore crashes
that child (CLI-SPEC §3.4), and the exit-code assertions fail loudly rather than pass over
an execution.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tools.honest_claims_lint import load_phrases

__all__ = [
    "PHRASES",
    "REPO_ROOT",
    "ProcessResult",
    "console_script",
    "run_gebra",
    "sweep_for_banned_phrases",
]

REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The TE-15 banned-phrase list, through the lint's own loader (lowercased entries).
PHRASES: Final = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")

#: The terminal conventions ``rich`` honours — stripped from every child (CLI-SPEC §5.1/§6.2).
_TERMINAL_VARIABLES: Final = ("NO_COLOR", "FORCE_COLOR", "TERM", "COLORTERM", "COLUMNS", "LINES")


def sweep_for_banned_phrases(context: str, *streams: str) -> None:
    """Assert no banned phrase appears in any of ``streams`` (WA-06, acceptance box 3)."""
    for text in streams:
        lowered = text.lower()
        for phrase in PHRASES:
            assert phrase not in lowered, f"{context}: captured output carries {phrase!r}"


@dataclass(frozen=True)
class ProcessResult:
    """One child-process CLI run: the §3 exit code and the two §5.2 streams."""

    exit_code: int
    stdout: str
    stderr: str


def run_gebra(
    *argv: str,
    cwd: Path,
    program: tuple[str, ...] | None = None,
    timeout: float = 120.0,
) -> ProcessResult:
    """Run one ``gebra`` invocation as a child process and hand back all three surfaces.

    ``program`` defaults to ``(sys.executable, "-m", "gebra.cli")``; pass the console
    script's own path to exercise the generated wrapper instead. Both streams are swept
    for banned phrases before the result is returned.
    """
    environment = {
        name: value for name, value in os.environ.items() if name not in _TERMINAL_VARIABLES
    }
    # Stripping the inherited terminal variables makes the child hermetic; pinning a wide
    # console makes its LAYOUT deterministic too. Without this the CLI wraps at the rich
    # non-TTY default of 80 columns, and a phrase that sits after a path in the same
    # sentence splits across the wrap on runners whose tmp paths are longer than a
    # workstation's — which is a fact about the machine, not about the output the
    # assertions pin (CLI-09: CLI-07's confirming run red on exactly that).
    environment["COLUMNS"] = "500"
    inherited = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(REPO_ROOT) if not inherited else f"{REPO_ROOT}{os.pathsep}{inherited}"
    )
    completed = subprocess.run(
        [*(program if program is not None else (sys.executable, "-m", "gebra.cli")), *argv],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )
    sweep_for_banned_phrases(f"gebra {' '.join(argv)}".rstrip(), completed.stdout, completed.stderr)
    return ProcessResult(
        exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def console_script() -> tuple[str, ...]:
    """The installed ``gebra`` entry point beside the running interpreter, as a program.

    Every environment CI runs this suite in installs the package (``uv sync`` or
    ``pip install -e``), and both write the ``[project.scripts]`` wrapper next to the
    interpreter — so its absence is an environment defect worth failing on, not skipping
    over.
    """
    directory = Path(sys.executable).parent
    for name in ("gebra", "gebra.exe"):
        candidate = directory / name
        if candidate.is_file():
            return (str(candidate),)
    raise AssertionError(
        f"no `gebra` console script beside {sys.executable} — the package is expected to be "
        "installed (uv sync / pip install -e), which writes the [project.scripts] wrapper"
    )
