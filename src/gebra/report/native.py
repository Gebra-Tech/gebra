"""The native JSON surface — REPORT-FORMAT-SPEC §0.1 row 2 and §1.5.

`--format json` is not a rendering: it is "the run report **itself**, serialized (§1.5).
Lossless." So this module adds no shape of its own. It applies the §1.5 profile, which in
code "is exactly ``gebra.verify.to_data`` / ``gebra.verify.to_json``" — definition order,
``exclude_none=True``, two-space indentation, ``ensure_ascii=False``, no JCS — and owns the
one thing §1.5 states about the *file* rather than the document: a report written to a file
ends with a single trailing newline, and one written to a stream does not add one.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

from gebra.verify.base import to_data, to_json
from gebra.verify.run import RunReport

__all__ = ["native_data", "render_native"]


def native_data(report: RunReport) -> dict[str, object]:
    """The run report as JSON data, in the §1.5 (PC-4) profile."""
    return to_data(report)


def render_native(report: RunReport, *, compact: bool = False, for_file: bool = False) -> str:
    """The run report serialized under §1.5.

    Args:
        report: The run report to serialize. It is emitted as it stands — a tool-error run
            serializes with ``properties: []`` and its ``error``, because §2.4 keeps exit 2
            from ever reading as a clean run.
        compact: The single-line form §1.5 offers stream consumers. Identical content.
        for_file: Whether the text is destined for a file, which §1.5 ends with a single
            trailing newline; a stream gets none.
    """
    text = to_json(report, indent=None if compact else 2)
    return f"{text}\n" if for_file else text
