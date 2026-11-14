"""Extraction notes on the report surfaces — the label and the text every surface shares.

A run that extracted carries what extraction said as ``RunReport.extraction_notes``
(REPORT-FORMAT-SPEC §1.2; PROPERTY-CATALOG-SPEC §0.6 item 8): the extraction warnings of
INTROSPECTION-SPEC §8 and ANNOTATION-API-SPEC §4, then the disclosures an R-06 record admits as
notes (INTROSPECTION-SPEC §8).
INTROSPECTION-SPEC §8 has a disclosure "rendered wherever warnings are rendered **under its own
label, never a warning's prefix**", so the label is decided once, here, and the human surface,
the SARIF projection and the CLI's stderr lines all take it from this module rather than
spelling it three times.

A note is **never a finding** (§4.6 rule 10): nothing here grades, counts or gates one.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): the input is a
validated note and the output is text. A validated note holds exact built-in values only —
the model converts every string, slot and ``detail`` value on the way in, through unbound
accessors — so formatting one here runs no code a workflow's names or values could carry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from gebra.verify.run import ExtractionNote

__all__ = [
    "DISCLOSURE_LABEL",
    "WARNING_LABEL",
    "detail_text",
    "note_heading",
    "note_label",
]

#: The label an extraction warning is rendered under — the CLI's stderr prefix since CLI-04.
WARNING_LABEL: Final = "extraction warning"

#: The label an extraction disclosure is rendered under: its own, never the warning's
#: (INTROSPECTION-SPEC §8; DEC-36 §4).
DISCLOSURE_LABEL: Final = "extraction disclosure"


def note_label(note: ExtractionNote) -> str:
    """The label ``note`` is rendered under — a disclosure's own, or the warning label."""
    return DISCLOSURE_LABEL if note.is_disclosure else WARNING_LABEL


def note_heading(note: ExtractionNote) -> str:
    """``<label> [<code>]`` — how every surface introduces a note, code verbatim."""
    return f"{note_label(note)} [{note.code}]"


def detail_text(detail: Mapping[str, Any]) -> str:
    """A note's ``detail`` on one line: ``key=value`` pairs in the record's own order.

    A string value is shown as itself; any other value as compact JSON, which is the form the
    native report carries it in — so a reader sees ``applied={"effect": ["write"]}``, never a
    Python ``repr``.
    """
    return " | ".join(
        f"{key}={value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}"
        for key, value in detail.items()
    )
