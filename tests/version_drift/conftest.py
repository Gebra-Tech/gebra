"""Version-drift suite wiring: the armed-fixture ledger and the end-of-run emissions.

Four responsibilities, all package-scoped:

* **WA-07 ledger.** The autouse fixture asserts, after every test in this package, that no
  armed fixture body was reached — extraction, drawing, schema rendering, and every surface
  read must leave :data:`tests.version_drift.workflows.TRIPPED` empty.

* **Soft-divergence emission.** VERSION-COMPAT §3: a soft-only divergence "keeps the cell
  green, emits a CI annotation ... Warnings never live only in logs." The tests collect
  divergences through :func:`tests.version_drift.inventory.soft_exact_set`; this hook
  emits them once, at terminal-summary time — under GitHub Actions as ``::warning``
  workflow commands, which the runner lifts into the run's annotations pane (visible
  without opening the log), and everywhere as a titled terminal section. The
  ``DRIFT-SOFT-DIVERGENCE`` line is the stable machine-readable seam the version-gap
  issue automation (``tools/drift_issues.py``, GOV-07) consumes.

* **Review-proposal emission.** The §3 row-4/row-8 failure branches record templated
  governance proposals through :func:`tests.version_drift.review.propose` (which also drops
  the immediate file artifacts) *before* their blocking assertion fails; this hook emits
  each proposal's full body, its stable ``DRIFT-REVIEW-PROPOSAL`` line — the same seam
  contract — and a ``::warning`` workflow command under Actions. The blocking itself
  is the red cell; the annotation is how the proposal reaches the run UI beside it.

* **The drift report file (GOV-07).** When :data:`REPORT_FILE_VARIABLE` is set, the same
  hook writes every signal this run produced to that file as the stable machine-readable
  lines: one ``DRIFT-REPORT-CONTEXT`` line naming the cell (:data:`CELL_VARIABLE`, set by
  the CI matrix), the running Python and the installed substrate pair, then one
  ``DRIFT-HARD-FAILURE`` line per failed or errored test in this package, then the
  soft-divergence and review-proposal lines verbatim. A clean run writes the context line
  alone — "this cell ran and observed nothing" is itself a recorded fact. CI uploads the
  file per cell and the ``drift-issues`` job feeds every cell's report to
  ``tools/drift_issues.py``, which opens the §3 version-gap / supported-range-review
  issues. Hard failures additionally get a terminal section and, under Actions, an
  ``::error`` workflow command each — the failure already blocks the cell through the
  pytest exit code; the annotation is how it reaches the run UI beside the annotation the
  soft channel already had.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from tests import substrate
from tests.version_drift import inventory, review, workflows

#: The environment variable naming the report file this package's terminal-summary hook
#: writes; unset (the default everywhere but CI and drills) writes nothing.
REPORT_FILE_VARIABLE: Final = "GEBRA_DRIFT_REPORT_FILE"

#: The environment variable naming the matrix cell (``1``/``2``/``3``/``pre``) for the
#: report's context line; a run without it records ``cell=unset``.
CELL_VARIABLE: Final = "GEBRA_DRIFT_CELL"

#: The stable machine-readable prefix of a hard drift failure —
#: ``DRIFT-HARD-FAILURE phase=<setup|call|teardown|collect> test=<nodeid to EOL>``.
#: The third seam line beside ``DRIFT-SOFT-DIVERGENCE`` and ``DRIFT-REVIEW-PROPOSAL``;
#: ``phase`` precedes ``test`` because a nodeid may contain spaces.
HARD_MARKER: Final = "DRIFT-HARD-FAILURE"

#: The stable machine-readable prefix of the report's one context line —
#: ``DRIFT-REPORT-CONTEXT cell=<cell> python=<x.y.z> langgraph=<x.y.z>
#: langchain-core=<x.y.z>``.
CONTEXT_MARKER: Final = "DRIFT-REPORT-CONTEXT"


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """Every test in this package asserts the armed fixtures were read, never run."""
    del workflows.TRIPPED[:]
    yield
    assert workflows.TRIPPED == []


def _is_drift_nodeid(nodeid: str) -> bool:
    """Whether a pytest nodeid belongs to this package, wherever pytest was invoked."""
    path = nodeid.split("::", 1)[0].replace("\\", "/")
    return "version_drift" in path.split("/")


def _hard_failure_lines(stats: object) -> list[str]:
    """One stable ``DRIFT-HARD-FAILURE`` line per failed/errored test in this package.

    Read from the terminal reporter's stats: ``failed`` holds call-phase failures,
    ``error`` holds setup/teardown errors (the WA-07 ledger assert lands there) and
    collection errors. ``xfailed``/``xpassed`` never appear — the row-9 beta case and the
    ``--pre`` cell's non-blocking semantics stay exactly what §3 rules them to be.
    """
    lines: list[str] = []
    getter = getattr(stats, "get", None)
    if not callable(getter):
        return lines
    for key in ("failed", "error"):
        for report in getter(key, []) or []:
            nodeid = str(getattr(report, "nodeid", ""))
            if not _is_drift_nodeid(nodeid):
                continue
            phase = getattr(report, "when", None) or "collect"
            lines.append(f"{HARD_MARKER} phase={phase} test={nodeid}")
    return lines


def _context_line() -> str:
    """The report's self-description: cell, Python, and the installed substrate pair."""
    cell = os.environ.get(CELL_VARIABLE, "unset")
    langgraph = ".".join(map(str, substrate.LANGGRAPH_VERSION))
    core = ".".join(map(str, substrate.LANGCHAIN_CORE_VERSION))
    return (
        f"{CONTEXT_MARKER} cell={cell} python={platform.python_version()} "
        f"langgraph={langgraph} langchain-core={core}"
    )


def _write_report_file(hard_failures: list[str]) -> None:
    """Write the machine-readable drift report when the environment asks for one."""
    target = os.environ.get(REPORT_FILE_VARIABLE)
    if not target:
        return
    lines = [_context_line()]
    lines.extend(hard_failures)
    lines.extend(divergence.message() for divergence in inventory.DIVERGENCES)
    lines.extend(proposal.message() for proposal in review.PROPOSALS)
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pytest_terminal_summary(terminalreporter: object) -> None:
    """Emit collected drift signals — annotation-grade — and the report file."""
    writer = terminalreporter
    section = getattr(writer, "section", None)
    write_line = getattr(writer, "write_line", print)
    under_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    hard_failures = _hard_failure_lines(getattr(writer, "stats", {}))
    if hard_failures:
        if callable(section):
            section("version-drift hard failures (cells blocked; VERSION-COMPAT §3)")
        for line in hard_failures:
            write_line(line)
            if under_actions:
                write_line(f"::error title=version-drift hard failure::{line}")
    if inventory.DIVERGENCES:
        if callable(section):
            section("version-drift soft divergences (cells stay green; VERSION-COMPAT §3)")
        for divergence in inventory.DIVERGENCES:
            write_line(divergence.sentence())
            write_line(divergence.message())
            if under_actions:
                write_line(f"::warning title=version-drift soft divergence::{divergence.message()}")
    if review.PROPOSALS:
        if callable(section):
            section("version-drift review proposals (cells blocked; VERSION-COMPAT §3/§5)")
        for proposal in review.PROPOSALS:
            for line in proposal.body.splitlines():
                write_line(line)
            write_line(proposal.message())
            if under_actions:
                write_line(f"::warning title=version-drift review proposal::{proposal.message()}")
    _write_report_file(hard_failures)
