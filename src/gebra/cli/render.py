"""Line rendering for the store-facing verbs — CLI-05's shared presentation primitives.

``gebra snapshot``, ``gebra diff`` and ``gebra history`` write artifacts no run report
carries — an outcome, a structural delta, a listing — so their lines are built here rather
than in :mod:`gebra.report`, whose surfaces are REPORT-FORMAT-SPEC's three and stay scoped
to the run report. The conventions are CLI-03's, held on purpose so the five verbs read as
one tool (PD-031; REPORT-FORMAT-SPEC §5.1):

* every line is a :class:`rich.text.Text` whose characters are decided before any style is
  attached, so **degradation changes styling only** — strip the escapes from the styled
  rendering and it *is* the plain one;
* ASCII-only chrome, so a non-UTF-8 stream cannot break a render;
* a dim label column at the same width the run-report surface uses;
* a ``graph_version`` elided to a recognizable prefix that reads as a prefix.

The console configuration mirrors ``gebra.report.human``'s for the same reasons stated
there: automatic highlighting, markup and emoji are off, because content must never choose
its own styling (§5.1 rule 8, in the other direction).

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): the inputs
are engine values and the output is text.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any, Final, TextIO

from rich.console import Console
from rich.text import Text

from gebra.report import TerminalOptions

__all__ = [
    "LABEL_STYLE",
    "blank",
    "elide_digest",
    "heading",
    "kv",
    "render_lines",
    "write_lines",
]

#: The dim label style and column width of the run-report surface, matched here.
LABEL_STYLE: Final = "dim"
HEADING_STYLE: Final = "bold"
_LABEL_WIDTH: Final = 24
_INDENT: Final = 2

#: How many hex characters of a ``graph_version`` these surfaces show — the same prefix
#: length the run-report surface uses (§5.1 rule 1 licenses the elision).
_DIGEST_PREFIX: Final = 16


def _console(file: TextIO, options: TerminalOptions) -> Console:
    """A console configured exactly as the run-report surface configures its own."""
    kwargs: dict[str, Any] = {
        "file": file,
        "highlight": False,
        "markup": False,
        "emoji": False,
    }
    if options.width is not None:
        kwargs["width"] = options.width
    if options.color is True:
        kwargs["force_terminal"] = True
        kwargs["no_color"] = False
    elif options.color is False:
        kwargs["force_terminal"] = False
        kwargs["no_color"] = True
    return Console(**kwargs)


def write_lines(lines: Iterable[Text], stream: TextIO, options: TerminalOptions | None) -> None:
    """Write ``lines`` to ``stream`` under the §5.1 degradation rules."""
    console = _console(stream, options or TerminalOptions())
    for line in lines:
        console.print(line)


def render_lines(lines: Iterable[Text], options: TerminalOptions | None) -> str:
    """The lines as text — what ``--output`` writes.

    With ``options.color`` left at ``None`` the buffer is not a terminal, so the text is
    plain — the same auto-detection a redirected stream gets (§5.1).
    """
    buffer = io.StringIO()
    write_lines(lines, buffer, options)
    return buffer.getvalue()


def kv(label: str, value: str, *, indent: int = _INDENT) -> Text:
    """One fact line: a dim label column, then the value.

    A label longer than the column keeps its single separating space rather than running
    into the value — the column is a layout convenience, and no fact is squeezed out of it.
    """
    line = Text(" " * indent)
    line.append(f"{label.ljust(_LABEL_WIDTH - 1)} ", style=LABEL_STYLE)
    line.append(value)
    return line


def heading(text: str) -> Text:
    """A bold section heading."""
    return Text(text, style=HEADING_STYLE)


def blank() -> Text:
    """An empty line."""
    return Text()


def elide_digest(digest: str, *, hex_chars: int = _DIGEST_PREFIX) -> str:
    """``digest`` elided to a prefix that reads as one — never presented as the whole.

    ``sha256:5db68464aabbccdd...`` keeps the algorithm and enough hex to recognize; the
    trailing dots are the statement that characters follow, spelled in ASCII exactly as the
    run-report surface spells them. ``hex_chars`` defaults to that surface's prefix length;
    the history table passes a shorter one so a row holds its columns.
    """
    algorithm, _, hex_part = digest.partition(":")
    if len(hex_part) <= hex_chars:
        return digest
    return f"{algorithm}:{hex_part[:hex_chars]}..."
