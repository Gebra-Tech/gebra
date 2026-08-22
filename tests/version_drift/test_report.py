"""The drift report file, proven live — the GOV-07 issue-automation seam is load-bearing.

The version-gap machinery consumes one machine-written file per matrix cell: a context
line, then the stable signal lines (hard failures, soft divergences, review proposals).
A report format nobody has ever watched being produced would leave the issue automation
consuming an assumption, so this module drives the conftest hook directly with staged
stats and ledgers — the same technique ``test_softness.py`` uses — and pins each fact the
consumer (``tools/drift_issues.py``) relies on: the file exists exactly when the
environment asks for one, a clean run still records its context, hard lines name phase
and test and never include anything outside this package (nor any xfail), and the soft
and proposal lines land verbatim. All signals are staged onto patched ledgers — the real
:data:`~tests.version_drift.inventory.DIVERGENCES` / ``review.PROPOSALS`` lists are never
appended to, so no phantom annotation or report reaches the suite's own summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests import substrate
from tests.version_drift import conftest, inventory, review


@dataclass(frozen=True)
class _Report:
    """A test-report stand-in: exactly the two attributes the hook reads."""

    nodeid: str
    when: str | None = "call"


class _Reporter:
    """A terminal-reporter stand-in that keeps every line it is handed."""

    def __init__(self, stats: dict[str, list[_Report]] | None = None) -> None:
        self.stats: dict[str, list[_Report]] = stats or {}
        self.lines: list[str] = []
        self.sections: list[str] = []

    def section(self, title: str) -> None:
        self.sections.append(title)

    def write_line(self, line: str) -> None:
        self.lines.append(line)


@pytest.fixture()
def staged_ledgers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patched divergence/proposal ledgers so staged signals never reach the summary."""
    monkeypatch.setattr(inventory, "DIVERGENCES", [])
    monkeypatch.setattr(review, "PROPOSALS", [])


@pytest.fixture()
def report_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A report target announced through the environment, the way CI announces it."""
    target = tmp_path / "drift-report.txt"
    monkeypatch.setenv(conftest.REPORT_FILE_VARIABLE, str(target))
    monkeypatch.setenv(conftest.CELL_VARIABLE, "3")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return target


def _divergence() -> inventory.SoftDivergence:
    return inventory.SoftDivergence(
        test="test_drift_send_signature",
        surface="send-members",
        owner=inventory.LANGGRAPH,
        installed="9.9.9",
        line=(9, 9),
        recorded=frozenset({"arg", "node"}),
        observed=frozenset({"arg", "node", "brand_new"}),
    )


def _proposal() -> review.ReviewProposal:
    return review.ReviewProposal(
        kind="get-graph-demotion",
        test="test_drift_get_graph_drawable_fidelity",
        detail="staged for the report test",
        body="# staged proposal body",
    )


def test_the_report_carries_context_and_every_signal_kind(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """One file, four line kinds — context first, then hard, soft, proposal verbatim."""
    inventory.DIVERGENCES.append(_divergence())
    review.PROPOSALS.append(_proposal())
    reporter = _Reporter(
        stats={
            "failed": [
                _Report("tests/version_drift/test_version_drift.py::test_drift_send_signature"),
                _Report("tests/extraction/test_builder.py::test_unrelated"),
            ],
            "error": [
                _Report(
                    "tests/version_drift/test_version_drift.py::test_drift_builder_edges_waiting_edges",
                    when="teardown",
                )
            ],
        }
    )

    conftest.pytest_terminal_summary(reporter)

    lines = report_file.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith(conftest.CONTEXT_MARKER + " ")
    assert lines[1:] == [
        (
            f"{conftest.HARD_MARKER} phase=call "
            "test=tests/version_drift/test_version_drift.py::test_drift_send_signature"
        ),
        (
            f"{conftest.HARD_MARKER} phase=teardown "
            "test=tests/version_drift/test_version_drift.py"
            "::test_drift_builder_edges_waiting_edges"
        ),
        _divergence().message(),
        _proposal().message(),
    ]


def test_the_context_line_names_cell_python_and_the_installed_pair(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """The report self-describes: the cell CI set, the Python, the substrate pins."""
    import platform

    conftest.pytest_terminal_summary(_Reporter())

    [context] = report_file.read_text(encoding="utf-8").splitlines()
    langgraph = ".".join(map(str, substrate.LANGGRAPH_VERSION))
    core = ".".join(map(str, substrate.LANGCHAIN_CORE_VERSION))
    assert context == (
        f"{conftest.CONTEXT_MARKER} cell=3 python={platform.python_version()} "
        f"langgraph={langgraph} langchain-core={core}"
    )


def test_a_clean_run_writes_a_context_only_report(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """A green cell still reports — "ran and observed nothing" is a recorded fact."""
    conftest.pytest_terminal_summary(_Reporter())

    content = report_file.read_text(encoding="utf-8")
    assert content.startswith(conftest.CONTEXT_MARKER + " ")
    assert len(content.splitlines()) == 1


def test_no_report_is_written_when_the_variable_is_unset(
    staged_ledgers: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local runs stay file-free: the report exists only where CI asked for it."""
    monkeypatch.delenv(conftest.REPORT_FILE_VARIABLE, raising=False)
    inventory.DIVERGENCES.append(_divergence())

    conftest.pytest_terminal_summary(_Reporter())

    assert list(tmp_path.iterdir()) == []


def test_an_absent_cell_variable_reads_unset(
    staged_ledgers: None,
    report_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No invented cell identity: outside the matrix the report says so."""
    monkeypatch.delenv(conftest.CELL_VARIABLE, raising=False)

    conftest.pytest_terminal_summary(_Reporter())

    [context] = report_file.read_text(encoding="utf-8").splitlines()
    assert " cell=unset " in context


def test_report_parent_directories_are_created(
    staged_ledgers: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A nested report path is not a crash — CI may point into a fresh directory."""
    target = tmp_path / "nested" / "deeper" / "drift-report.txt"
    monkeypatch.setenv(conftest.REPORT_FILE_VARIABLE, str(target))

    conftest.pytest_terminal_summary(_Reporter())

    assert target.is_file()


def test_only_this_packages_failures_become_hard_lines(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """A red unit test elsewhere is not substrate drift and never enters the report."""
    reporter = _Reporter(
        stats={
            "failed": [_Report("tests/extraction/test_digests.py::test_something")],
            "error": [_Report("tests/test_packaging.py::test_other", when="setup")],
        }
    )

    conftest.pytest_terminal_summary(reporter)

    content = report_file.read_text(encoding="utf-8")
    assert conftest.HARD_MARKER not in content


def test_xfail_semantics_never_reach_the_hard_channel(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """The row-9 beta xfail and any xpass live in stats keys the hook never reads."""
    reporter = _Reporter(
        stats={
            "xfailed": [
                _Report(
                    "tests/version_drift/test_version_drift.py"
                    "::test_drift_channel_reducer_repr_delta_beta"
                )
            ],
            "xpassed": [
                _Report(
                    "tests/version_drift/test_version_drift.py"
                    "::test_drift_channel_reducer_repr_delta_beta"
                )
            ],
        }
    )

    conftest.pytest_terminal_summary(reporter)

    content = report_file.read_text(encoding="utf-8")
    assert conftest.HARD_MARKER not in content


def test_a_collection_error_reads_phase_collect(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """A report shape without ``when`` (a collect error) still lands, named honestly."""
    reporter = _Reporter(
        stats={"error": [_Report("tests/version_drift/test_version_drift.py", when=None)]}
    )

    conftest.pytest_terminal_summary(reporter)

    content = report_file.read_text(encoding="utf-8")
    assert f"{conftest.HARD_MARKER} phase=collect test=tests/version_drift/" in content


def test_hard_failures_reach_the_terminal_section_and_the_actions_error_channel(
    staged_ledgers: None,
    report_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under Actions a hard failure is an ``::error`` annotation beside the red cell."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    reporter = _Reporter(
        stats={"failed": [_Report("tests/version_drift/test_version_drift.py::test_x")]}
    )

    conftest.pytest_terminal_summary(reporter)

    assert "version-drift hard failures (cells blocked; VERSION-COMPAT §3)" in reporter.sections
    stable = [line for line in reporter.lines if line.startswith(conftest.HARD_MARKER)]
    assert stable == [
        f"{conftest.HARD_MARKER} phase=call test=tests/version_drift/test_version_drift.py::test_x"
    ]
    commands = [line for line in reporter.lines if line.startswith("::error ")]
    assert commands == [f"::error title=version-drift hard failure::{stable[0]}"]


def test_hard_failures_stay_plain_off_actions(
    staged_ledgers: None,
    report_file: Path,
) -> None:
    """Off Actions the section and the stable line print; no workflow command does."""
    reporter = _Reporter(
        stats={"failed": [_Report("tests/version_drift/test_version_drift.py::test_x")]}
    )

    conftest.pytest_terminal_summary(reporter)

    assert any(line.startswith(conftest.HARD_MARKER) for line in reporter.lines)
    assert not any(line.startswith("::error") for line in reporter.lines)


def test_a_quiet_run_emits_no_hard_section(staged_ledgers: None, report_file: Path) -> None:
    """No failures → no section, no lines — green runs stay quiet on the terminal."""
    reporter = _Reporter()

    conftest.pytest_terminal_summary(reporter)

    assert reporter.sections == []
    assert reporter.lines == []


def test_the_nodeid_predicate_is_position_independent() -> None:
    """The package is recognized by path component, not by invocation directory."""
    assert conftest._is_drift_nodeid("tests/version_drift/test_version_drift.py::test_x")
    assert conftest._is_drift_nodeid("version_drift/test_report.py::test_y")
    assert conftest._is_drift_nodeid(r"tests\version_drift\test_report.py::test_y")
    assert not conftest._is_drift_nodeid("tests/extraction/test_builder.py::test_x")
    assert not conftest._is_drift_nodeid("tests/test_version_drift_lookalike.py::test_x")
