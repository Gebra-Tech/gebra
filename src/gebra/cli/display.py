"""The ``gebra display`` verb — CLI-SPEC §4.4, behind the parser.

The verb is three steps. **Usage validation first** (§3.4, §5.3): every problem with the
invocation reported together, and — the rule that closes this verb's never-invokes claim —
an **import-shaped target is a usage error here**, refused before any import could happen:
``display``'s input surface is an IR document or a stored snapshot, and it has no
``extracted`` mode to resolve through (§2.2, §4.4, PD-034 finding 2). **Then resolution**
(§2): the ir-document or snapshot resolver, exactly ``verify``'s rows. **Then the
artifact**: ``gebra.display.render_mermaid`` over the loaded IR, with the ``--report``
overlay loaded the way REPORT-FORMAT-SPEC §1.6 requires of any consumer — ``report_format``
read first off the parsed JSON, an unknown MAJOR refused, and this build's strict models
refusing the rest — then the guide §4.1 pairing checks (subject present; recorded digest
equal to the displayed IR's own). The diagram is plain Mermaid text on stdout on every
setting; ``--color`` governs the stderr diagnostics only (§4.4).

Exit codes are §3.2's ``display`` row: ``0`` the diagram was emitted; ``1`` never —
``display`` reaches no verdict and reports no difference; ``2`` the subject failed to
resolve or the overlay report was refused, plus §3.4's usage-error family raised here as
:class:`UsageFailure`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Final, TextIO

from gebra.cli.common import (
    OutputError,
    UsageFailure,
    split_arguments,
    strict_refusal_problems,
    unknown_flag_problems,
)
from gebra.cli.invocation import StrictReading
from gebra.cli.resolve import (
    Refusal,
    ResolvedSubject,
    detect_mode,
    resolve_ir_document,
    resolve_snapshot,
)
from gebra.display import OverlayPairingError, render_mermaid
from gebra.ir import CanonicalizationError, DynamicEdgeUnsupportedError
from gebra.report import did_you_mean, suggestion_sentence
from gebra.verify import REPORT_FORMAT, RunReport

__all__ = ["DISPLAY_FORMATS", "DisplayRequest", "run_display"]

#: §4.4's one diagram format in Phase-0; PlantUML is demoted out of the phase (PD-034).
DISPLAY_FORMATS: Final[tuple[str, ...]] = ("mermaid",)


@dataclass(frozen=True)
class DisplayRequest:
    """One parsed ``gebra display`` invocation.

    Attributes:
        arguments: Every positional token the parser collected, unknown flags included
            (the verb ignores unknown options so §5.3 can report every problem at once).
        literal_targets: The tokens after ``--`` — targets whatever they look like (§1.2).
        ir_path, snapshot_version: The §2.3 explicit mode selectors this verb has (§4.4 —
            there is no ``--import`` here).
        store_dir: ``--store``, or ``None`` for the ``./.gebra`` default (§2.5).
        report_path: ``--report`` — the native-JSON run report painted onto the diagram.
        display_format: The ``--format`` value, unvalidated (validation is a §5.3 usage
            problem with §5.4's suggestion).
        output: ``--output``/``-o``, or ``None`` for stdout.
        color: ``--color``/``--no-color`` — the stderr diagnostics only (§4.4).
        strict: The §3.3 reading, refused here: ``display`` has no gate.
        flag_vocabulary: The verb's declared flags, for §5.4 suggestions.
    """

    arguments: tuple[str, ...]
    literal_targets: tuple[str, ...]
    ir_path: str | None
    snapshot_version: str | None
    store_dir: str | None
    report_path: str | None
    display_format: str
    output: str | None
    color: bool | None
    strict: StrictReading
    flag_vocabulary: tuple[str, ...]


def run_display(request: DisplayRequest) -> int:
    """Execute the verb over ``request`` and return the §3.2 exit code.

    Raises:
        UsageFailure: every §3.4 problem with the invocation, together (§5.3).
        OutputError: the diagram was rendered and ``--output`` could not be written.
    """
    positional, unknown_flags = split_arguments(request.arguments, request.literal_targets)
    problems = _usage_problems(request, positional, unknown_flags)
    if problems:
        raise UsageFailure("display", problems)

    try:
        subject = _resolve(request, positional)
        report = _load_report(request.report_path)
        text = render_mermaid(
            subject.ir,
            report=report,
            source=f"{subject.reference.source} ({subject.reference.input_mode})",
        )
    except Refusal as refusal:
        _write_diagnostic(f"no diagram was emitted (stage: {refusal.stage}): {refusal.detail}")
        return 2
    except DynamicEdgeUnsupportedError as error:
        _write_diagnostic(f"no diagram was emitted (stage: ir-validation): {error}")
        return 2
    except CanonicalizationError as error:
        _write_diagnostic(
            "no diagram was emitted (stage: ir-validation): the IR has no canonical "
            f"form, so it has no digest for the --report provenance check: {error}"
        )
        return 2
    except OverlayPairingError as error:
        _write_diagnostic(f"no diagram was emitted (stage: input): --report was refused: {error}")
        return 2

    _write_artifact(text, request)
    return 0


# ── Usage validation (§3.4, §5.3) ────────────────────────────────────────────────────────


def _usage_problems(
    request: DisplayRequest, positional: tuple[str, ...], unknown_flags: tuple[str, ...]
) -> tuple[str, ...]:
    """Every §3.4 problem this invocation has, in one pass (§5.3).

    As on the other verbs, subject-arity problems are reported only when every flag
    parsed — an unknown flag's would-be value pollutes the positional picture — while
    selector conflicts and format-value problems are independent and always reported.
    """
    problems: list[str] = list(request.strict.problems)
    problems.extend(strict_refusal_problems("display", request.strict))
    problems.extend(unknown_flag_problems(unknown_flags, request.flag_vocabulary))
    if request.display_format not in DISPLAY_FORMATS:
        hint = suggestion_sentence(did_you_mean(request.display_format, DISPLAY_FORMATS))
        problems.append(
            f"--format {request.display_format!r} is not one of "
            + ", ".join(DISPLAY_FORMATS)
            + " — the only diagram format in Phase-0 (CLI-SPEC §4.4)"
            + (f". {hint}" if hint else "")
        )

    selectors = [
        (flag, value)
        for flag, value in (("--ir", request.ir_path), ("--snapshot", request.snapshot_version))
        if value is not None
    ]
    if len(selectors) > 1:
        problems.append(
            "--ir and --snapshot are mutually exclusive mode selectors; give one (CLI-SPEC §2.3)"
        )
    if not unknown_flags:
        if positional and selectors:
            listed = ", ".join(repr(token) for token in positional)
            flags = " and ".join(flag for flag, _ in selectors)
            problems.append(
                f"TARGET ({listed}) and {flags} both name a subject; give one (CLI-SPEC §2.3)"
            )
        if len(positional) > 1:
            listed = ", ".join(repr(token) for token in positional)
            problems.append(f"display takes one TARGET; this invocation gives {listed}")
        if not positional and not selectors:
            problems.append(
                "no subject: give a TARGET, or one of --ir/--snapshot — no verb guesses "
                "a default subject (CLI-SPEC §2.3)"
            )
        if len(positional) == 1 and not selectors and _names_import_reference(positional[0]):
            problems.append(
                f"{positional[0]!r} is an import reference, and display has no live-target "
                "mode (CLI-SPEC §4.4): it draws an IR document or a stored snapshot, and "
                "an import-shaped target is refused before any import happens. Record a "
                "snapshot (gebra snapshot) and display the stored version, or write the "
                "IR to a file (gebra.ir.write_ir) and display that"
            )
    return tuple(problems)


def _names_import_reference(target: str) -> bool:
    """Whether §2.2's grammar reads ``target`` as an import reference — pure grammar.

    A target matching none of the three grammars is not a usage error: resolution owns
    that diagnostic (§2.6), exactly as on the other verbs.
    """
    try:
        return detect_mode(target) == "extracted"
    except Refusal:
        return False


# ── Resolution and the artifact (§2, §4.4) ───────────────────────────────────────────────


def _resolve(request: DisplayRequest, positional: tuple[str, ...]) -> ResolvedSubject:
    """One subject, by explicit selector or §2.2 detection — the two modes this verb has."""
    if request.ir_path is not None:
        return resolve_ir_document(request.ir_path)
    if request.snapshot_version is not None:
        return resolve_snapshot(request.snapshot_version, request.store_dir)
    target = positional[0]
    mode = detect_mode(target)
    if mode == "ir-document":
        return resolve_ir_document(target)
    if mode == "snapshot":
        return resolve_snapshot(target, request.store_dir)
    raise AssertionError(  # pragma: no cover - usage validation refused it (§4.4)
        "an import-shaped target reached resolution on display"
    )


def _load_report(path: str | None) -> RunReport | None:
    """The ``--report`` overlay input, read as REPORT-FORMAT-SPEC §1.6 requires (§4.4).

    ``report_format`` is read first, off the parsed JSON: an unknown MAJOR is refused by
    that fact alone, and a MINOR this build does not read is refused naming the one it
    does (§1.6 grants a strict consumer that refusal). Only then does the strict model
    validate the whole document.

    Raises:
        Refusal: ``input`` — the file is unreadable, is not a run report, or carries a
            ``report_format`` this build does not read (§2.6).
    """
    if path is None:
        return None
    try:
        text = _read_text(path)
    except UnicodeDecodeError as error:
        raise Refusal(
            "input", f"--report {path!r} is not UTF-8 text, so it is no run report: {error}"
        ) from error
    except OSError as error:
        raise Refusal("input", f"cannot read --report {path!r}: {error}") from error
    try:
        document = json.loads(text)
    except ValueError as error:
        raise Refusal(
            "input", f"--report {path!r} is not a readable run report: {error}"
        ) from error
    if not isinstance(document, dict) or not isinstance(document.get("report_format"), str):
        raise Refusal(
            "input",
            f"--report {path!r} is not a run report: it carries no report_format member "
            "(REPORT-FORMAT-SPEC §1.6: read report_format first)",
        )
    declared: str = document["report_format"]
    known_major, _, _ = REPORT_FORMAT.partition(".")
    major, _, _ = declared.partition(".")
    if major != known_major:
        raise Refusal(
            "input",
            f"--report {path!r} carries report_format {declared!r}, a MAJOR this build "
            f"does not know; it reads {REPORT_FORMAT!r} (REPORT-FORMAT-SPEC §1.6)",
        )
    if declared != REPORT_FORMAT:
        raise Refusal(
            "input",
            f"--report {path!r} carries report_format {declared!r}, which this build does "
            f"not read: its strict models read {REPORT_FORMAT!r} exactly "
            "(REPORT-FORMAT-SPEC §1.6 — a consumer MUST refuse a MAJOR it does not know "
            "and MAY refuse a higher MINOR; this build refuses every report_format its "
            "models were not built against)",
        )
    try:
        return RunReport.model_validate_json(text)
    except ValueError as error:
        raise Refusal("input", f"--report {path!r} is not a valid run report: {error}") from error


def _read_text(path: str) -> str:
    """The file's text, UTF-8."""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _write_artifact(text: str, request: DisplayRequest) -> None:
    """The diagram, on stdout or at ``--output`` (§5.2) — the same bytes either way (§1.4).

    Raises:
        OutputError: ``--output`` could not be written (§3.4's exit-2 case, rendered by
            the shell).
    """
    if request.output is None:
        sys.stdout.write(text)
        return
    try:
        with open(request.output, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as error:
        raise OutputError(f"cannot write --output {request.output!r}: {error}") from error


def _write_diagnostic(message: str) -> None:
    """A §5.2 stderr diagnostic, prefixed with the verb that is speaking."""
    _stderr().write(f"gebra display: {message}\n")


def _stderr() -> TextIO:
    """``sys.stderr`` at call time, so captured streams in tests see the writes."""
    return sys.stderr
