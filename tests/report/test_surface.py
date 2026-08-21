"""The package's own entry points — ``render`` and ``write`` (card CLI-03).

The three surfaces have their own modules and their own tests; this one covers the dispatch a
caller with a ``--format`` flag actually uses, including the stream discipline CLI-SPEC §5.2
fixes (stdout carries the artifact, and nothing else).

Nothing here executes a workflow node, calls a model or opens a socket (WA-07).
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from gebra.report import (
    REPORT_FORMATS,
    ReportFormat,
    TerminalOptions,
    render,
    render_human,
    render_native,
    render_sarif,
    write,
)
from tests.report.variants import CASES

REPORT = CASES[0].report


def test_the_format_vocabulary_is_the_cli_spec_flag_values() -> None:
    """CLI-SPEC §4.1: ``--format {human,json,sarif}``, with ``human`` the no-flag default."""
    assert REPORT_FORMATS == ("human", "json", "sarif")


def test_the_default_surface_is_the_human_one() -> None:
    assert render(REPORT) == render(REPORT, "human")


@pytest.mark.parametrize(
    ("report_format", "expected"),
    [
        ("json", render_native),
        ("sarif", render_sarif),
    ],
)
def test_render_dispatches_to_the_named_surface(report_format: ReportFormat, expected: Any) -> None:
    assert render(REPORT, report_format) == expected(REPORT)


def test_render_passes_terminal_options_through() -> None:
    options = TerminalOptions(color=False, width=60)
    assert render(REPORT, "human", terminal=options) == render_human(REPORT, options)


@pytest.mark.parametrize("report_format", ["json", "sarif"])
def test_for_file_reaches_only_the_machine_surfaces(report_format: ReportFormat) -> None:
    """§1.5's trailing-newline rule is a file rule; the human surface is a stream rendering."""
    assert render(REPORT, report_format, for_file=True).endswith("\n")
    assert not render(REPORT, report_format).endswith("\n")
    assert render(REPORT, "human", for_file=True) == render(REPORT, "human")


@pytest.mark.parametrize("report_format", REPORT_FORMATS)
def test_write_puts_the_artifact_on_the_stream(report_format: ReportFormat) -> None:
    """CLI-SPEC §5.2: stdout carries the artifact and nothing else."""
    stream = io.StringIO()
    write(REPORT, stream, report_format)
    assert stream.getvalue() == render(REPORT, report_format, terminal=TerminalOptions(color=None))


def test_write_lets_rich_see_the_real_stream() -> None:
    """A buffer is not a terminal, so the human surface written to one is plain (§5.1)."""
    stream = io.StringIO()
    write(REPORT, stream)
    assert "\x1b" not in stream.getvalue()
