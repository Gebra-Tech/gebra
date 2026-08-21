"""The ``gebra verify`` verb — CLI-SPEC §4.1, behind the parser.

The verb is four steps, in an order the spec fixes. **Usage validation first** (§3.4, §5.3):
every problem with the invocation itself — unknown flags, conflicting subjects, a strict
token that names no property — is collected and reported in **one** diagnostic, and a usage
error emits no run report on any format, because the invocation never became a run. **Then
resolution** (§2): a failure there is a run that reached no verdict, reported as a
tool-error run report on the selected surface with the §2.6 stage named. **Then the run**:
:func:`gebra.verify.verify` over the resolved IR, with the strict policy and the subject
reference recorded verbatim. **Then the artifact**: the run report written on the selected
surface — stdout, or ``--output`` — with extraction warnings on stderr, in emission order,
never dropped and never moving the exit code (§3.5, §5.2).

The verb reaches no verdict of its own and returns ``gate.exit_code`` from the report it
rendered (§3.1); the one exit outside the report is the §3.4 usage error's ``2``, raised
here as :class:`UsageFailure` and rendered by the application shell.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TextIO

import gebra
from gebra.cli.invocation import StrictReading
from gebra.cli.resolve import (
    Refusal,
    ResolvedSubject,
    detect_mode,
    resolve_import_reference,
    resolve_ir_document,
    resolve_snapshot,
)
from gebra.report import (
    REPORT_FORMATS,
    TerminalOptions,
    did_you_mean,
    render,
    suggestion_sentence,
    write,
    write_human,
)
from gebra.verify import (
    REPORT_FORMAT,
    STRICT_OFF,
    GateOutcome,
    RunPolicy,
    RunReport,
    SeverityCounts,
    StrictPolicy,
    Tool,
    ToolError,
    verify,
)

if TYPE_CHECKING:
    from gebra.cli.resolve import Mode
    from gebra.extraction.warnings import ExtractionWarning

__all__ = ["OutputError", "UsageFailure", "VerifyRequest", "run_verify"]


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


@dataclass(frozen=True)
class VerifyRequest:
    """One parsed ``gebra verify`` invocation, as the parser and the pre-parse reading left it.

    Attributes:
        arguments: Every positional token the parser collected — targets, and (because the
            verb ignores unknown options rather than stopping at the first, §5.3) any
            unknown flag tokens, in order.
        literal_targets: The tokens after ``--``, which are targets whatever they look
            like (§1.2); the unknown-flag scan must not read them as options.
        ir_path, import_ref, snapshot_version: The §2.3 explicit mode selectors.
        store_dir: ``--store``, or ``None`` for the ``./.gebra`` default (§2.5).
        sidecar: ``--sidecar`` — ``extracted`` mode only (§2.4).
        call: ``--call`` — ``extracted`` mode only, the CLI's one user-code call (§2.4).
        strict: The §3.3 reading taken off the raw tokens before parsing.
        report_format: The ``--format`` value, unvalidated (validation is a usage problem
            with §5.4's suggestion, not a parser refusal).
        output: ``--output``/``-o``, or ``None`` for stdout.
        color: ``--color``/``--no-color``, or ``None`` for auto-detection (§5.1).
        flag_vocabulary: The verb's declared flag spellings — §5.4's closed vocabulary for
            unknown-flag suggestions.
    """

    arguments: tuple[str, ...]
    literal_targets: tuple[str, ...]
    ir_path: str | None
    import_ref: str | None
    snapshot_version: str | None
    store_dir: str | None
    sidecar: str | None
    call: bool
    strict: StrictReading
    report_format: str
    output: str | None
    color: bool | None
    flag_vocabulary: tuple[str, ...]


def run_verify(request: VerifyRequest) -> int:
    """Execute the verb over ``request`` and return the §3.2 exit code.

    Raises:
        UsageFailure: every §3.4 problem with the invocation, together (§5.3).
        OutputError: the run completed and ``--output`` could not be written.
    """
    positional, unknown_flags = _split_arguments(request)
    problems = _usage_problems(request, positional, unknown_flags)
    if problems:
        raise UsageFailure("verify", problems)

    strict_policy = request.strict.policy if request.strict.policy is not None else STRICT_OFF
    try:
        subject = _resolve(request, positional)
    except Refusal as refusal:
        report = _tool_error_report(refusal, strict_policy)
        _write_stage_diagnostic(refusal.stage, refusal.detail)
        _write_artifact(report, request)
        return report.gate.exit_code

    _write_extraction_warnings(subject)
    report = verify(subject.ir, RunPolicy(strict=strict_policy, subject=subject.reference))
    if report.error is not None:
        # verify()'s own refusals (an ir 1.1 document, a dispatch failure) reach stderr in
        # the same §5.5 anatomy as a resolution refusal, whatever surface stdout carries.
        _write_stage_diagnostic(report.error.stage, report.error.detail)
    _write_artifact(report, request)
    return report.gate.exit_code


# ── Usage validation (§3.4, §5.3) ────────────────────────────────────────────────────────


def _split_arguments(request: VerifyRequest) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate the collected argument tokens into targets and unknown flags.

    A ``-``-leading token is an unknown flag **unless** it stood after ``--``, where §1.2
    makes it a target; the multiset accounting keeps a spelling that appears on both sides
    of ``--`` honest.
    """
    literal = Counter(request.literal_targets)
    positional: list[str] = []
    unknown: list[str] = []
    for token in request.arguments:
        if token.startswith("-") and token != "-" and not literal[token]:
            unknown.append(token)
            continue
        if literal[token]:
            literal[token] -= 1
        positional.append(token)
    return tuple(positional), tuple(unknown)


def _usage_problems(
    request: VerifyRequest, positional: tuple[str, ...], unknown_flags: tuple[str, ...]
) -> tuple[str, ...]:
    """Every §3.4 problem this invocation has, in one pass (§5.3).

    Dependent problems are not invented: with an unknown flag in the invocation, the
    positional picture is unreliable (the token after ``--frmat`` was probably its value),
    so subject-arity problems are reported only on an invocation whose flags all parsed.
    """
    problems: list[str] = list(request.strict.problems)
    for token in unknown_flags:
        name = token.split("=", 1)[0]
        hint = suggestion_sentence(did_you_mean(name, request.flag_vocabulary))
        problems.append(f"unknown option {name!r}" + (f". {hint}" if hint else ""))
    if request.report_format not in REPORT_FORMATS:
        hint = suggestion_sentence(did_you_mean(request.report_format, REPORT_FORMATS))
        problems.append(
            f"--format {request.report_format!r} is not one of "
            + ", ".join(REPORT_FORMATS)
            + (f". {hint}" if hint else "")
        )

    selectors = [
        (flag, value)
        for flag, value in (
            ("--ir", request.ir_path),
            ("--import", request.import_ref),
            ("--snapshot", request.snapshot_version),
        )
        if value is not None
    ]
    if len(selectors) > 1:
        # Independent of any unknown flag — §5.3's own example pairs exactly these two —
        # because a selector carries its value with it and the argument stream cannot
        # change what was given.
        listed = " and ".join(flag for flag, _ in selectors)
        problems.append(f"{listed} are mutually exclusive mode selectors; give one (CLI-SPEC §2.3)")
    if not unknown_flags:
        if positional and selectors:
            listed = ", ".join(repr(token) for token in positional)
            flags = " and ".join(flag for flag, _ in selectors)
            problems.append(
                f"TARGET ({listed}) and {flags} both name a subject; give one (CLI-SPEC §2.3)"
            )
        if len(positional) > 1:
            listed = ", ".join(repr(token) for token in positional)
            problems.append(f"verify takes one TARGET; this invocation gives {listed}")
        if not positional and not selectors:
            problems.append(
                "no subject: give a TARGET, or one of --ir/--import/--snapshot — no verb "
                "guesses a default subject (CLI-SPEC §2.3)"
            )
    problems.extend(_mode_problems(request, positional, unknown_flags, selectors))
    return tuple(problems)


def _mode_problems(
    request: VerifyRequest,
    positional: tuple[str, ...],
    unknown_flags: tuple[str, ...],
    selectors: list[tuple[str, str]],
) -> list[str]:
    """The per-mode flag restrictions: ``--sidecar`` and ``--call`` are ``extracted``-only.

    Asked only when the invocation determines exactly one subject whose mode the grammar
    can name (§2.2 is pure grammar, so nothing is read or imported here); an invocation
    whose subject is already in question gets those problems instead, not a pile of
    dependent ones.
    """
    if request.sidecar is None and not request.call:
        return []
    mode = _requested_mode(request, positional, unknown_flags, selectors)
    if mode is None or mode == "extracted":
        return []
    problems: list[str] = []
    if request.sidecar is not None:
        problems.append(
            f"--sidecar applies to an import-reference subject only (CLI-SPEC §2.4); "
            f"this subject is {mode}"
        )
    if request.call:
        problems.append(
            f"--call applies to an import-reference subject only (CLI-SPEC §2.4); "
            f"this subject is {mode}"
        )
    return problems


def _requested_mode(
    request: VerifyRequest,
    positional: tuple[str, ...],
    unknown_flags: tuple[str, ...],
    selectors: list[tuple[str, str]],
) -> Mode | None:
    """The mode this invocation names, or ``None`` where that is not (yet) determinable.

    A selector names its mode outright, so an unknown flag elsewhere in the invocation does
    not blur it (§5.3: independent problems report together). The *positional* picture is
    different on both counts: an unknown flag's would-be value lands in it, so with one in
    the invocation the positionals neither name a mode nor count as a competing subject.
    """
    if len(selectors) > 1:
        return None
    if not unknown_flags and positional and selectors:
        return None
    if request.ir_path is not None:
        return "ir-document"
    if request.import_ref is not None:
        return "extracted"
    if request.snapshot_version is not None:
        return "snapshot"
    if not unknown_flags and len(positional) == 1:
        try:
            return detect_mode(positional[0])
        except Refusal:
            return None  # the resolution phase owns that diagnostic
    return None


# ── Resolution and the run (§2, §3.1) ────────────────────────────────────────────────────


def _resolve(request: VerifyRequest, positional: tuple[str, ...]) -> ResolvedSubject:
    """One subject, by explicit selector or by §2.2 detection over the one TARGET."""
    if request.ir_path is not None:
        return resolve_ir_document(request.ir_path)
    if request.import_ref is not None:
        return resolve_import_reference(
            request.import_ref, call=request.call, sidecar=request.sidecar
        )
    if request.snapshot_version is not None:
        return resolve_snapshot(request.snapshot_version, request.store_dir)
    target = positional[0]
    mode = detect_mode(target)
    if mode == "ir-document":
        return resolve_ir_document(target)
    if mode == "snapshot":
        return resolve_snapshot(target, request.store_dir)
    return resolve_import_reference(target, call=request.call, sidecar=request.sidecar)


def _tool_error_report(refusal: Refusal, strict: StrictPolicy) -> RunReport:
    """The §2.4 tool-error run report for a resolution refusal.

    Assembled from the run-level models exactly as ``verify()`` assembles its own: no
    subject (resolution is what failed to produce one), no outcomes, zero counts because
    nothing was counted, and the strict policy recorded as requested so a reader knows
    which gate *would* have judged the run.
    """
    return RunReport(
        report_format=REPORT_FORMAT,
        tool=Tool(name="gebra", version=gebra.__version__),
        subject=None,
        properties=(),
        gate=GateOutcome(
            exit_code=2,
            outcome="tool-error",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=strict,
            promotions=(),
            snapshot_eligible=False,
        ),
        error=ToolError(stage=refusal.stage, detail=refusal.detail),
    )


# ── What goes where (§5.2) ───────────────────────────────────────────────────────────────


def _write_stage_diagnostic(stage: str, detail: str) -> None:
    """The §5.5 stderr diagnostic for a run that reached no verdict.

    Stated on stderr whatever surface stdout carries, so a pipeline that captured the
    artifact still shows *why* in its log — and stated in §5.5's anatomy: the stage, the
    detail, and that no verdict was reached.
    """
    _stderr().write(f"gebra verify: no verdict was reached (stage: {stage}): {detail}\n")


def _write_extraction_warnings(subject: ResolvedSubject) -> None:
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


def _write_artifact(report: RunReport, request: VerifyRequest) -> None:
    """The artifact, on stdout or at ``--output`` (§5.2), on the selected surface.

    A machine report written to a file ends with a single trailing newline; one written to
    a stream does not add one (REPORT-FORMAT-SPEC §1.5) — the split between
    :func:`gebra.report.write` and ``render(..., for_file=True)`` below is that rule.
    """
    terminal = TerminalOptions(color=request.color)
    report_format = request.report_format
    if report_format not in REPORT_FORMATS:  # pragma: no cover - usage validation precedes
        raise AssertionError(f"unvalidated format {report_format!r} reached emission")
    if request.output is None:
        write(report, sys.stdout, report_format, terminal=terminal)
        return
    try:
        with open(request.output, "w", encoding="utf-8", newline="") as handle:
            if report_format == "human":
                write_human(report, handle, terminal)
            else:
                handle.write(render(report, report_format, for_file=True))
    except OSError as error:
        raise OutputError(f"cannot write --output {request.output!r}: {error}") from error


def _stderr() -> TextIO:
    """``sys.stderr`` at call time, so captured streams in tests see the writes."""
    return sys.stderr
