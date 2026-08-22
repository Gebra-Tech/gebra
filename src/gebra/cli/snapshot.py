"""The ``gebra snapshot`` verb — CLI-SPEC §4.2, behind the parser.

The verb is the §4.2 sequence exactly. **Usage validation first** (§3.4, §5.3): everything
independently wrong with the invocation, reported together, with no store touched — and,
per §2.2's per-verb mode rule, a V.S.F.E-label target refused here as usage rather than
resolved, because a stored version is already a snapshot and this verb takes none. **Then
one resolution** (§2): an IR document or an import reference, made exactly once — the
eligibility run and the write share it, so a module is imported once, a ``--call``
attribute is called at most once per invocation, and the digest the store records is the
digest the gate saw. **Then the eligibility run**: :func:`gebra.verify.verify` over the
resolved IR. A run that reached no verdict records nothing and is exit ``2``. **Then the
engine**: :func:`gebra.snapshot.record` (or :func:`~gebra.snapshot.record_document`, for
the document mode), which applies §0.2's recording rule — this verb hands the report over
and renders the answer; it re-derives nothing and has no bypass flag.

**Exit codes are §3.2's ``snapshot`` row.** ``0`` — the store call completed, a snapshot
recorded or nothing moved; ``1`` — only the §0.2 refusal, a reached verdict whose FATAL
findings forbid recording, rendered so the refusal is legible; ``2`` — resolution failed,
the eligibility run reached no verdict, or the store refused the write.

**Never-invokes** (§0.5, WA-07): this verb is one of the three that can reach a live
object, and its tripwire lands with this card (CLI-05) in ``tests/cli/``. The engine it
wraps imports the extractor by SD-03's design ("wired to extract" — its package docstring
prices this in), so :mod:`gebra.snapshot` is imported lazily here, keeping
``import gebra.cli`` substrate-free; on the document path the substrate is *imported* and
nothing more, and on the import path the resolution boundary is §2.4's, unchanged.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.text import Text

from gebra.cli.common import (
    UsageFailure,
    split_arguments,
    strict_refusal_problems,
    unknown_flag_problems,
    write_extraction_warnings,
)
from gebra.cli.render import elide_digest, heading, kv, write_lines
from gebra.cli.resolve import (
    Refusal,
    ResolvedSubject,
    detect_mode,
    resolve_import_reference,
    resolve_ir_document,
    store_for,
)
from gebra.ir import DynamicEdgeUnsupportedError
from gebra.report import TerminalOptions, write
from gebra.verify import STRICT_OFF, RunPolicy, RunReport, verify
from gebra.versioning import Component

if TYPE_CHECKING:
    from gebra.cli.invocation import StrictReading
    from gebra.cli.resolve import Mode
    from gebra.snapshot import SnapshotOutcome

__all__ = ["SnapshotRequest", "run_snapshot"]


@dataclass(frozen=True)
class SnapshotRequest:
    """One parsed ``gebra snapshot`` invocation.

    Attributes:
        arguments: Every positional token the parser collected, unknown flags included
            (the verb ignores unknown options so §5.3 can report every problem at once).
        literal_targets: The tokens after ``--`` — targets whatever they look like (§1.2).
        ir_path, import_ref: The §2.3 selectors this verb takes. ``--snapshot`` is not one
            of them: a stored version is already a snapshot (§4.2).
        store_dir: ``--store``, or ``None`` for ``./.gebra`` (§2.5).
        sidecar: ``--sidecar`` — ``extracted`` mode only (§2.4).
        call: ``--call`` — ``extracted`` mode only, the CLI's one user-code call (§2.4).
        quiet: ``--quiet`` — only the recorded label on stdout, or nothing when nothing
            was recorded (§4.2).
        strict: The pre-parse §3.3 reading. This verb takes no strict flag, so a non-empty
            reading is refused as usage (§3.3: promotion is a gate policy and this verb has
            no gate).
        color: ``--color``/``--no-color``, or ``None`` for auto-detection (§5.1).
        flag_vocabulary: The verb's declared flag spellings, for §5.4 suggestions.
    """

    arguments: tuple[str, ...]
    literal_targets: tuple[str, ...]
    ir_path: str | None
    import_ref: str | None
    store_dir: str | None
    sidecar: str | None
    call: bool
    quiet: bool
    strict: StrictReading
    color: bool | None
    flag_vocabulary: tuple[str, ...]


def run_snapshot(request: SnapshotRequest) -> int:
    """Execute the verb over ``request`` and return the §3.2 exit code.

    Raises:
        UsageFailure: every §3.4 problem with the invocation, together (§5.3).
    """
    positional, unknown_flags = _split_arguments(request)
    problems = _usage_problems(request, positional, unknown_flags)
    if problems:
        raise UsageFailure("snapshot", problems)

    try:
        subject = _resolve(request, positional)
    except Refusal as refusal:
        _write_diagnostic(
            f"nothing was recorded — no verdict was reached (stage: {refusal.stage}): "
            f"{refusal.detail}"
        )
        return 2

    write_extraction_warnings(subject)
    report = verify(subject.ir, RunPolicy(strict=STRICT_OFF, subject=subject.reference))
    if report.error is not None:
        # The eligibility run reached no verdict (§3.2: exit 2, the store untouched); §5.5's
        # anatomy on stderr, and no artifact anywhere — there is no label to report.
        _write_diagnostic(
            f"nothing was recorded — the eligibility run reached no verdict "
            f"(stage: {report.error.stage}): {report.error.detail}"
        )
        return 2

    return _record(request, subject, report)


# ── Usage validation (§3.4, §5.3) ────────────────────────────────────────────────────────


def _split_arguments(request: SnapshotRequest) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Targets and unknown flags, by :func:`gebra.cli.common.split_arguments`'s one reading."""
    return split_arguments(request.arguments, request.literal_targets)


def _usage_problems(
    request: SnapshotRequest, positional: tuple[str, ...], unknown_flags: tuple[str, ...]
) -> tuple[str, ...]:
    """Every §3.4 problem this invocation has, in one pass (§5.3).

    The dependent-problem discipline is ``verify``'s: with an unknown flag in the
    invocation the positional picture is unreliable (the token after a mistyped flag was
    probably its value), so subject-arity and target-mode problems are reported only on an
    invocation whose flags all parsed.
    """
    problems: list[str] = strict_refusal_problems("snapshot", request.strict)
    problems.extend(unknown_flag_problems(unknown_flags, request.flag_vocabulary))

    selectors = [
        (flag, value)
        for flag, value in (("--ir", request.ir_path), ("--import", request.import_ref))
        if value is not None
    ]
    if len(selectors) > 1:
        problems.append(
            "--ir and --import are mutually exclusive mode selectors; give one (CLI-SPEC §2.3)"
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
            problems.append(f"snapshot takes one TARGET; this invocation gives {listed}")
        if not positional and not selectors:
            problems.append(
                "no subject: give a TARGET, or one of --ir/--import — no verb guesses a "
                "default subject (CLI-SPEC §2.3)"
            )
    mode = _requested_mode(request, positional, unknown_flags, bool(selectors))
    if mode == "snapshot":
        problems.append(
            "a stored version is already a snapshot, so snapshot does not take one as its "
            "subject (CLI-SPEC §4.2); name the working definition — an IR document or an "
            "import reference"
        )
    elif mode is not None and mode != "extracted":
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
    return tuple(problems)


def _requested_mode(
    request: SnapshotRequest,
    positional: tuple[str, ...],
    unknown_flags: tuple[str, ...],
    any_selector: bool,
) -> Mode | None:
    """The mode this invocation names, or ``None`` where that is not (yet) determinable."""
    if request.ir_path is not None and request.import_ref is not None:
        return None
    if request.ir_path is not None:
        return "ir-document"
    if request.import_ref is not None:
        return "extracted"
    if not unknown_flags and not any_selector and len(positional) == 1:
        try:
            return detect_mode(positional[0])
        except Refusal:
            return None  # the resolution phase owns that diagnostic
    return None


# ── Resolution and the engine call (§2, §4.2) ────────────────────────────────────────────


def _resolve(request: SnapshotRequest, positional: tuple[str, ...]) -> ResolvedSubject:
    """One subject, resolved once — §4.2's shared resolution for the gate and the write."""
    if request.ir_path is not None:
        return resolve_ir_document(request.ir_path)
    if request.import_ref is not None:
        return resolve_import_reference(
            request.import_ref, call=request.call, sidecar=request.sidecar
        )
    target = positional[0]
    mode = detect_mode(target)
    if mode == "ir-document":
        return resolve_ir_document(target)
    if mode == "snapshot":  # pragma: no cover - refused as usage before resolution
        raise AssertionError("a snapshot-mode target must be refused by usage validation")
    return resolve_import_reference(target, call=request.call, sidecar=request.sidecar)


def _record(request: SnapshotRequest, subject: ResolvedSubject, report: RunReport) -> int:
    """Hand the engine the resolution and the report, and render the §3.2 answer.

    The engine — and with it the extractor and the substrate (SD-03's package prices this
    in) — is imported here, not at module top, so ``import gebra.cli`` stays
    substrate-free.
    """
    from gebra.snapshot import SnapshotError, SnapshotErrorReason, record, record_document

    store = store_for(request.store_dir)
    try:
        if subject.envelope is not None:
            outcome = record(
                subject.envelope,
                store=store,
                source=subject.reference.source,
                eligibility=report,
            )
        else:
            outcome = record_document(
                subject.ir,
                store=store,
                source=subject.reference.source,
                eligibility=report,
            )
    except SnapshotError as error:
        if error.reason is SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE:
            # §3.2's exit 1: the §0.2 refusal, from a run that reached a verdict (the
            # no-verdict case returned 2 above). Rendered so the refusal is legible (§4.2):
            # the report with its FATAL findings on stdout — suppressed by --quiet, whose
            # contract is "nothing when nothing was recorded" — and the refusal on stderr.
            if not request.quiet:
                write(report, sys.stdout, "human", terminal=TerminalOptions(color=request.color))
            _write_diagnostic(
                f"not recorded: the eligibility run counted "
                f"{report.gate.counts.fatal} FATAL finding(s), and a FATAL means no "
                f"snapshot is recorded (PROPERTY-CATALOG-SPEC §0.2). There is no flag to "
                f"bypass this."
            )
            return 1
        _write_diagnostic(f"nothing was recorded: {error}")
        return 2
    except (ValueError, DynamicEdgeUnsupportedError) as error:
        # The engine's whole refusal channel: StoreError, VersionFormatError and the
        # duplicate-node-id refusal are ValueErrors; the DEC-28 decline is a
        # NotImplementedError. A §3.2 exit 2 either way — the store refused the write —
        # and anything outside these two families is a crash §3.4 owns, not a refusal.
        _write_diagnostic(f"nothing was recorded: {error}")
        return 2

    if request.quiet:
        if outcome.recorded:
            sys.stdout.write(f"{outcome.version}\n")
        return 0
    write_lines(_outcome_lines(outcome), sys.stdout, TerminalOptions(color=request.color))
    return 0


# ── What it writes (§4.2, §5.2) ──────────────────────────────────────────────────────────


def _outcome_lines(outcome: SnapshotOutcome) -> list[Text]:
    """§4.2's success sentence as lines: the label, the file, which of S/F/E moved.

    Every fact is the engine's own — the label, the path, the bump class read off the diff
    the label was derived from — and an unchanged call is "a statement that nothing moved,
    never a fabricated new label".
    """
    lines: list[Text] = []
    if not outcome.recorded:
        lines.append(
            heading(f"nothing moved — the store already holds this content as {outcome.version}")
        )
        lines.append(kv("file", str(outcome.path)))
        lines.append(kv("graph_version", elide_digest(outcome.graph_version)))
        return lines
    lines.append(heading(f"recorded {outcome.version}"))
    lines.append(kv("file", str(outcome.path)))
    lines.append(kv("graph_version", elide_digest(outcome.graph_version)))
    if outcome.first:
        lines.append(kv("previous", "none — the store's first snapshot"))
        return lines
    assert outcome.previous is not None and outcome.diff is not None  # SnapshotOutcome invariant
    lines.append(kv("previous", outcome.previous))
    lines.append(kv("moved", _bump_phrase(outcome.bump_class)))
    marker = outcome.diff.evolution_safety
    # The §4.2 marker fact set: property id + slug, the not-checked wording, the status.
    lines.append(kv(f"{marker.property_id} {marker.property}", f"not checked [{marker.status}]"))
    lines.append(kv("", "no safe/breaking classification exists in Phase 0"))
    return lines


def _bump_phrase(bump_class: frozenset[Component]) -> str:
    """The moved components, spelled in label order — S before F before E, as V.S.F.E writes
    them."""
    moved = [component.value for component in Component if component in bump_class]
    return " ".join(moved)


def _write_diagnostic(message: str) -> None:
    """A §5.2 stderr diagnostic, prefixed with the verb that is speaking."""
    sys.stderr.write(f"gebra snapshot: {message}\n")
