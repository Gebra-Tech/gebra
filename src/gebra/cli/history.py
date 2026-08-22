"""The ``gebra history`` verb — CLI-SPEC §4.5, behind the parser.

Lists what the store holds. Takes no subject — the store *is* the subject — and wraps
:func:`gebra.lineage.lineage` as thinly as a verb can: ``--since``/``--until``/``--limit``
are the engine's own window arguments passed through unchanged, their refusals are the
engine's :class:`~gebra.lineage.LineageError` reported as exit ``2``, and the one shaping
this verb does — ``--reverse`` — is the presentation-layer reversal D-11 In-Scope 3 and
PD-033 both put here, over an unchanged engine order.

**The output shape is PD-033's ruling**: a table, oldest first, one row per
``LineageEntry``, with columns for the index, the version label, the ``graph_version``
(a short prefix that reads as a prefix), the created-at timestamp, a current-pointer
marker, and a step summary sourced only from that row's ``LineageStep`` — which components
bumped in V.S.F.E order, a distinct ``-`` marker for a component that *decreased*, whether
the content changed, and an explicit ``n/a`` for a row whose step is absent or
non-comparable, never a blank cell that could be read as "no change". A window states that
it is one: ``total``, ``omitted_before`` and ``omitted_after`` are shown however small the
window. **No full structural diff renders inline** (PD-033): the step summary says which
counters moved, and the content answer for a step is ``gebra diff`` between the two
labels.

``--format json`` is :func:`gebra.lineage.dump_lineage`'s existing byte-stable projection,
stamped with ``LINEAGE_DOCUMENT_VERSION``, written verbatim — no second schema, and no
``sarif``: SARIF is a findings format and a history has no findings.

**Exit codes are §3.2's ``history`` row**: ``0`` — the history was listed, an empty
history from a store that does not exist included; ``1`` — never, a listing is not a
verdict; ``2`` — the store index was unreadable, or a window argument named a version the
history does not hold.

**Never-invokes** (§0.5): this verb reaches no live object on any path — it reads a store
index and nothing else.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.text import Text

from gebra.cli.common import (
    OutputError,
    UsageFailure,
    split_arguments,
    strict_refusal_problems,
    unknown_flag_problems,
)
from gebra.cli.render import LABEL_STYLE, blank, elide_digest, render_lines, write_lines
from gebra.cli.resolve import store_for
from gebra.lineage import (
    Lineage,
    LineageEntry,
    LineageError,
    LineageErrorReason,
    dump_lineage,
    lineage,
)
from gebra.report import TerminalOptions, did_you_mean, suggestion_sentence
from gebra.store import StoreError
from gebra.versioning import Component

if TYPE_CHECKING:
    from gebra.cli.invocation import StrictReading
    from gebra.lineage import LineageStep

__all__ = ["HISTORY_FORMATS", "HistoryRequest", "run_history"]

#: §4.5's ``--format`` value set. There is no ``sarif``: a history has no findings.
HISTORY_FORMATS: tuple[str, ...] = ("human", "json")

#: How many hex characters of a digest a table row shows. Shorter than the fact-line
#: surfaces' prefix so a common row holds its columns at 80 columns; still a prefix that
#: reads as one (§4.5 licenses the short form).
_ROW_DIGEST_HEX = 6


@dataclass(frozen=True)
class HistoryRequest:
    """One parsed ``gebra history`` invocation.

    Attributes:
        arguments: Every positional token the parser collected, unknown flags included.
            The verb takes no TARGET, so any real positional is a usage error.
        literal_targets: The tokens after ``--`` (§1.2).
        store_dir: ``--store``, the store listed (§2.5).
        since, until: The inclusive window anchors, passed to the engine unchanged.
        limit: ``--limit`` as given. Its *shape* (an integer) is usage; its *semantics*
            (non-negativity, the window it selects) are the engine's own refusals (§4.5).
        reverse: ``--reverse`` — display newest first; the engine order is unchanged.
        history_format: ``--format``, unvalidated (validation is a usage problem with
            §5.4's suggestion).
        output: ``--output``/``-o``, or ``None`` for stdout.
        strict: The pre-parse §3.3 reading, refused here — a listing has no gate.
        color: ``--color``/``--no-color``, or ``None`` for auto-detection (§5.1).
        flag_vocabulary: The verb's declared flag spellings, for §5.4 suggestions.
    """

    arguments: tuple[str, ...]
    literal_targets: tuple[str, ...]
    store_dir: str | None
    since: str | None
    until: str | None
    limit: str | None
    reverse: bool
    history_format: str
    output: str | None
    strict: StrictReading
    color: bool | None
    flag_vocabulary: tuple[str, ...]


def run_history(request: HistoryRequest) -> int:
    """Execute the verb over ``request`` and return the §3.2 exit code.

    Raises:
        UsageFailure: every §3.4 problem with the invocation, together (§5.3).
        OutputError: the listing completed and ``--output`` could not be written.
    """
    positional, unknown_flags = _split_arguments(request)
    problems = _usage_problems(request, positional, unknown_flags)
    if problems:
        raise UsageFailure("history", problems)

    store = store_for(request.store_dir)
    limit = None if request.limit is None else int(request.limit)
    try:
        listing = lineage(store, since=request.since, until=request.until, limit=limit)
    except LineageError as error:
        hint = ""
        if error.reason is LineageErrorReason.UNKNOWN_VERSION:
            # §5.4's closed vocabulary for a --since/--until label: what the store holds.
            hint_sentence = suggestion_sentence(did_you_mean(error.value, store.versions()))
            hint = f" {hint_sentence}" if hint_sentence else ""
        _write_diagnostic(f"the history was not listed: {error}{hint}")
        return 2
    except StoreError as error:
        _write_diagnostic(f"the history was not listed: {error}")
        return 2

    if request.history_format == "json":
        _write_artifact_text(dump_lineage(listing), request)
        return 0
    text_lines = _history_lines(listing, store_label=str(store.path), reverse=request.reverse)
    _write_artifact_lines(text_lines, request)
    return 0


# ── Usage validation (§3.4, §5.3) ────────────────────────────────────────────────────────


def _split_arguments(request: HistoryRequest) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Targets and unknown flags, by :func:`gebra.cli.common.split_arguments`'s one reading."""
    return split_arguments(request.arguments, request.literal_targets)


def _usage_problems(
    request: HistoryRequest, positional: tuple[str, ...], unknown_flags: tuple[str, ...]
) -> tuple[str, ...]:
    """Every §3.4 problem this invocation has, in one pass (§5.3)."""
    problems: list[str] = strict_refusal_problems("history", request.strict)
    problems.extend(unknown_flag_problems(unknown_flags, request.flag_vocabulary))
    if positional and not unknown_flags:
        listed = ", ".join(repr(token) for token in positional)
        problems.append(
            f"history takes no TARGET — the store is the subject (CLI-SPEC §4.5); this "
            f"invocation gives {listed}"
        )
    if request.history_format not in HISTORY_FORMATS:
        hint = suggestion_sentence(did_you_mean(request.history_format, HISTORY_FORMATS))
        problems.append(
            f"--format {request.history_format!r} is not one of "
            + ", ".join(HISTORY_FORMATS)
            + " — there is no sarif here: SARIF is a findings format and a history has no "
            "findings (CLI-SPEC §4.5)" + (f". {hint}" if hint else "")
        )
    if request.limit is not None and not _is_integer(request.limit):
        problems.append(
            f"--limit {request.limit!r} is not an integer; it counts rows (CLI-SPEC §4.5)"
        )
    return tuple(problems)


def _is_integer(text: str) -> bool:
    """Whether ``text`` spells an integer — sign included, so ``-1`` reaches the engine's
    own negative-limit refusal rather than a shape error here."""
    try:
        int(text)
    except ValueError:
        return False
    return True


# ── What it renders (§4.5, PD-033) ───────────────────────────────────────────────────────


def _history_lines(listing: Lineage, *, store_label: str, reverse: bool) -> list[Text]:
    """PD-033's table: the window statement, a header row, one row per entry."""
    lines: list[Text] = [_window_line(listing, store_label, reverse=reverse)]
    if listing.truncated:
        # §4.5: a window states that it is one — its own line, under the statement, so a
        # long history's numbers never crowd the header line off its width.
        lines.append(
            Text(
                f"showing {len(listing.entries)} of {listing.total} "
                f"({listing.omitted_before} omitted before, {listing.omitted_after} after)",
                style=LABEL_STYLE,
            )
        )
    if not listing.entries:
        return lines
    lines.append(blank())
    widths = _column_widths(listing)
    lines.append(_header_row(widths))
    entries = reversed(listing.entries) if reverse else iter(listing.entries)
    lines.extend(_entry_row(entry, widths) for entry in entries)
    return lines


def _window_line(listing: Lineage, store_label: str, *, reverse: bool) -> Text:
    """The listing's first line: whose history, how big, where the pointer stands."""
    line = Text()
    line.append(f"history of {store_label}", style="bold")
    if listing.total == 0:
        line.append(" — the store holds no versions")
        return line
    plural = "" if listing.total == 1 else "s"
    line.append(f" — {listing.total} version{plural}")
    if listing.current is not None:
        line.append(f"; current {listing.current}")
    if reverse:
        line.append("; newest first", style=LABEL_STYLE)
    return line


@dataclass(frozen=True)
class _Widths:
    """The computed column widths of one rendered table."""

    index: int
    version: int
    digest: int
    created: int


def _column_widths(listing: Lineage) -> _Widths:
    """Fixed column widths for this window, computed so every cell fits its column."""
    return _Widths(
        index=max(1, *(len(str(entry.index)) for entry in listing.entries)),
        version=max(len("version"), *(len(entry.version) for entry in listing.entries)),
        digest=max(
            len("graph_version"),
            *(len(_row_digest(entry.graph_version)) for entry in listing.entries),
        ),
        created=max(len("created"), *(len(entry.created_at) for entry in listing.entries)),
    )


def _row_digest(graph_version: str) -> str:
    """The digest column's short prefix."""
    return elide_digest(graph_version, hex_chars=_ROW_DIGEST_HEX)


def _header_row(widths: _Widths) -> Text:
    """The dim column-label row. ``#`` is the index; the current-pointer column is
    unlabeled, one character wide, and rendered as ``*`` on the row the pointer names."""
    return Text(
        "  "
        + "#".rjust(widths.index)
        + "  "
        + "version".ljust(widths.version)
        + "  "
        + "graph_version".ljust(widths.digest)
        + "  "
        + "created".ljust(widths.created)
        + "  step",
        style=LABEL_STYLE,
    )


def _entry_row(entry: LineageEntry, widths: _Widths) -> Text:
    """One ``LineageEntry`` as one table row."""
    line = Text()
    line.append("* " if entry.is_current else "  ", style="bold")
    line.append(str(entry.index).rjust(widths.index))
    line.append("  ")
    line.append(entry.version.ljust(widths.version))
    line.append("  ")
    line.append(_row_digest(entry.graph_version).ljust(widths.digest), style=LABEL_STYLE)
    line.append("  ")
    line.append(entry.created_at.ljust(widths.created))
    line.append("  ")
    line.append(_step_phrase(entry.step))
    return line


def _step_phrase(step: LineageStep | None) -> str:
    """PD-033's step-summary cell, sourced only from the row's ``LineageStep``.

    An absent step is the store's oldest version; a non-comparable one has a label outside
    the V.S.F.E grammar on one side. Both render an explicit ``n/a`` naming which (PD-033's
    comparable-vs-not distinction) — never a blank cell. A comparable step spells rises as
    ``+X`` and falls as ``-X`` in label order (the distinct decreased marker), and beside
    them whether the content moved — two different facts the index states independently.
    """
    if step is None:
        return "n/a (oldest version)"
    if step.bump_class is None or step.decreased is None:
        return "n/a (label not V.S.F.E)"
    movements = [f"+{component.value}" for component in Component if component in step.bump_class]
    movements += [f"-{component.value}" for component in Component if component in step.decreased]
    moved = " ".join(movements) if movements else "no label movement"
    # "content changed" is what differing index digests license (canonicalization is
    # deterministic, so different digests are different canonical bytes); the converse is a
    # collision-resistance assumption the model deliberately does not make, so equal digests
    # are stated as exactly that.
    content = "content changed" if step.content_changed else "same digest"
    return f"{moved}, {content}"


# ── Streams (§5.2) ───────────────────────────────────────────────────────────────────────


def _write_artifact_lines(lines: list[Text], request: HistoryRequest) -> None:
    """The human table, on stdout or at ``--output`` (§5.2)."""
    terminal = TerminalOptions(color=request.color)
    if request.output is None:
        write_lines(lines, sys.stdout, terminal)
        return
    _write_file(render_lines(lines, terminal), request.output)


def _write_artifact_text(text: str, request: HistoryRequest) -> None:
    """The machine projection, verbatim — ``dump_lineage`` owns its bytes, trailing
    newline included, and this verb changes none of them (§4.5, PD-033)."""
    if request.output is None:
        sys.stdout.write(text)
        return
    _write_file(text, request.output)


def _write_file(text: str, output: str) -> None:
    try:
        with open(output, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as error:
        raise OutputError(f"cannot write --output {output!r}: {error}") from error


def _write_diagnostic(message: str) -> None:
    """A §5.2 stderr diagnostic, prefixed with the verb that is speaking."""
    sys.stderr.write(f"gebra history: {message}\n")
