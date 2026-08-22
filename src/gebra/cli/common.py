"""What every verb's behavior module shares — the §3.4/§5.3 plumbing, stated once.

CLI-04 built this machinery inside the ``verify`` verb; CLI-05's three verbs need the same
pieces, so they live here and ``verify`` keeps its behavior by importing them. Three kinds
of thing:

* the two exceptions the application shell turns into exit ``2`` —
  :class:`UsageFailure` (a §3.4 usage error, everything wrong reported together per §5.3)
  and :class:`OutputError` (the run completed and ``--output`` could not be written, §3.4);
* the argument-stream reading every verb repeats: separating collected tokens into targets
  and unknown flags (the verbs parse with ``ignore_unknown_options`` so §5.3 can report
  every problem in one pass), and the unknown-flag problems with §5.4's did-you-mean;
* the strict-flag refusal for the four verbs that do not take it. §3.3 scopes ``--strict``
  to ``gebra verify`` alone, and the pre-parse reading (:mod:`gebra.cli.invocation`)
  removes strict tokens before the parser sees them — so a verb without the flag must
  refuse a non-empty reading itself, exactly as that module's docstring instructs.

Nothing here resolves a subject, reaches a verdict, or renders anything (CLI-SPEC §0.1).
"""

from __future__ import annotations

import sys
from collections import Counter
from typing import TYPE_CHECKING, Final, TextIO

from gebra.report import did_you_mean, suggestion_sentence

if TYPE_CHECKING:
    from gebra.cli.invocation import StrictReading
    from gebra.cli.resolve import ResolvedSubject
    from gebra.extraction.warnings import ExtractionWarning

__all__ = [
    "OutputError",
    "UsageFailure",
    "split_arguments",
    "strict_refusal_problems",
    "unknown_flag_problems",
    "write_extraction_warnings",
]


class UsageFailure(Exception):
    """A §3.4 usage error: the invocation never became a run.

    Everything independently wrong is carried together (§5.3) — the shell renders the
    problems as one diagnostic on stderr and exits ``2``, and no run report is emitted on
    any format.
    """

    def __init__(self, verb: str, problems: tuple[str, ...]) -> None:
        super().__init__("; ".join(problems))
        self.verb: Final = verb
        self.problems: Final = problems


class OutputError(Exception):
    """``--output`` could not be written after the run completed.

    Deliberately not a run-report tool error — the run reached its answer; what failed is
    delivering it where the invocation asked. The shell reports it on stderr and exits
    ``2``, which keeps the §0.2 reading intact: no answer was delivered, and a partial or
    missing artifact is never presented as one.
    """


def split_arguments(
    arguments: tuple[str, ...], literal_targets: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate the collected argument tokens into targets and unknown flags.

    A ``-``-leading token is an unknown flag **unless** it stood after ``--``, where §1.2
    makes it a target; the multiset accounting keeps a spelling that appears on both sides
    of ``--`` honest.
    """
    literal = Counter(literal_targets)
    positional: list[str] = []
    unknown: list[str] = []
    for token in arguments:
        if token.startswith("-") and token != "-" and not literal[token]:
            unknown.append(token)
            continue
        if literal[token]:
            literal[token] -= 1
        positional.append(token)
    return tuple(positional), tuple(unknown)


def unknown_flag_problems(
    unknown_flags: tuple[str, ...], flag_vocabulary: tuple[str, ...]
) -> list[str]:
    """One §3.4 problem per unknown flag, with §5.4's suggestion over the verb's own flags."""
    problems: list[str] = []
    for token in unknown_flags:
        name = token.split("=", 1)[0]
        hint = suggestion_sentence(did_you_mean(name, flag_vocabulary))
        problems.append(f"unknown option {name!r}" + (f". {hint}" if hint else ""))
    return problems


def write_extraction_warnings(subject: ResolvedSubject) -> None:
    """Extraction warnings, on stderr, in emission order (§5.2) — never dropped.

    They are not findings and never move the exit code (§3.5). An
    ``annotation-unknown-node`` record carries the name that missed, and the IR beside it
    holds the closed vocabulary the name missed *from*, so that one row gets §5.4's
    did-you-mean attached — a legibility aid on the extractor's finding, never a selection.
    """
    if not subject.warnings:
        return
    stream = _stderr()
    node_ids = tuple(node.id for node in subject.ir.nodes)
    for warning in subject.warnings:
        stream.write(_warning_line(warning, node_ids))


def _warning_line(warning: ExtractionWarning, node_ids: tuple[str, ...]) -> str:
    line = f"extraction warning [{warning.code.value}]: {warning.message}"
    if warning.code.value == "annotation-unknown-node" and warning.node is not None:
        hint = suggestion_sentence(did_you_mean(warning.node, node_ids))
        if hint:
            line += f" {hint}"
    return line + "\n"


def _stderr() -> TextIO:
    """``sys.stderr`` at call time, so captured streams in tests see the writes."""
    return sys.stderr


def strict_refusal_problems(verb: str, strict: StrictReading) -> list[str]:
    """The §3.3 refusal for a verb that has no gate: ``--strict`` is ``gebra verify``'s.

    The pre-parse reading removed the tokens, so the parser cannot refuse them; the verb
    does, quoting the spelling that was typed. §3.3's own reason is stated because it is
    the verb-specific fact a user needs: the other verbs have no gate for a promotion to
    move.
    """
    if not strict.tokens:
        return []
    listed = ", ".join(strict.tokens)
    return [
        (
            f"{listed}: --strict is accepted by gebra verify only (CLI-SPEC §3.3) — "
            f"{verb} has no gate for a promotion to move"
        )
    ]
