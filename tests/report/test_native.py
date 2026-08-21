"""The native JSON surface against REPORT-FORMAT-SPEC §1.5 (card CLI-03).

`--format json` is the run report itself, so the property worth testing is that it is
*lossless*: what comes back out of the text is the same model that went in, compared as §0.3
defines comparison. The rest is the §1.5 profile — member order, omitted optionals, indentation
and the trailing-newline rule that separates a file from a stream.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gebra.report import native_data, render_native
from gebra.verify.base import models_equivalent
from gebra.verify.run import RunReport
from tests.report.goldens import compare_golden
from tests.report.variants import CASES


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_native_surface_round_trips_losslessly(case: Any) -> None:
    """§0.1 row 2: "The run report **itself**, serialized. Lossless.\""""
    restored = RunReport.model_validate_json(render_native(case.report))
    assert models_equivalent(restored, case.report)
    assert restored == case.report


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_absent_optionals_are_omitted_not_null(case: Any) -> None:
    """PC-4: omission round-trips, so a producer that never set a key and a consumer that
    drops one read back the same."""
    assert "null" not in render_native(case.report)


def test_member_order_is_definition_order() -> None:
    """§1.5: "never alphabetical, never sorted at write time"."""
    data = native_data(CASES[0].report)
    assert list(data) == [name for name in RunReport.model_fields if name in data]


def test_the_indentation_is_two_spaces() -> None:
    text = render_native(CASES[0].report)
    assert '\n  "tool": {' in text


def test_a_file_ends_with_one_newline_and_a_stream_does_not() -> None:
    """§1.5's one file-level rule."""
    text = render_native(CASES[0].report)
    assert not text.endswith("\n")
    assert render_native(CASES[0].report, for_file=True) == f"{text}\n"


def test_the_compact_form_carries_identical_content() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    compact = render_native(report, compact=True)
    assert "\n" not in compact
    assert json.loads(compact) == json.loads(render_native(report))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_serialization_is_deterministic(case: Any) -> None:
    """§1.4 rule 5, on the surface goldens are taken from."""
    assert render_native(case.report) == render_native(case.report)


def test_a_tool_error_serializes_as_a_tool_error() -> None:
    """§2.4: exit 2 is never a clean run, on any surface."""
    report = next(case.report for case in CASES if case.name == "tool-error")
    data = native_data(report)
    assert data["properties"] == []
    assert data["error"]["stage"] == "dispatch"  # type: ignore[index]
    assert data["gate"]["exit_code"] == 2  # type: ignore[index]


def test_the_report_format_is_the_first_member_a_consumer_reads() -> None:
    """§1.6: "read ``report_format`` first" — so it is the first key of the document."""
    assert next(iter(native_data(CASES[0].report))) == "report_format"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_native_golden(case: Any) -> None:
    compare_golden(f"json/{case.name}.json", render_native(case.report, for_file=True))
