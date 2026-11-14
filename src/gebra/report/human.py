"""The human terminal surface — REPORT-FORMAT-SPEC §5, on the CLI-D3 framework (PD-031).

The default, no-flag rendering: every fact §4 requires, laid out for a person. `rich` supplies
the console, the styling and the terminal-capability detection PD-031 adopted it for; the
mapping from a run report to lines is gebra's own, taken off the structured envelope and never
re-derived from prose.

**Degradation changes styling only** (§5.1 rule 8, PD-031). That is an equality here, not an
intention: every line is a :class:`rich.text.Text` whose characters are decided before any
style is attached, so the styled and the plain rendering of one report differ by exactly the
ANSI escapes — no box drawing that has to be down-converted, no table that re-flows, no finding
dropped, reordered or reworded. ``tests/report/test_human.py`` asserts the equality directly.

**What the rendering may not do**, restated from §4.6 because this is the surface a person
reads: the claim class is displayed with every finding and every verdict; a pass report's class
is the property catalog's, since a pass carries no per-record grade; P-02 wording is
witness-presence only; a not-implemented marker is shown as *not checked* and never counted in
a passed tally; a promoted record keeps its own WARNING grade and a promotion is never shown as
a second finding; and the severity tally, the exit code and the promotion list are read off
``gate`` rather than recounted (CLI-SPEC §0.1 rule 3).

**Extraction notes are a block of their own** (§4.2's ``RunReport.extraction_notes`` row, §4.6
rule 10, §5.1 rule 9): right under the subject they qualify, never inside a property's block,
never in a findings list and never in the summary's counts, and a disclosure under its own label
(:mod:`gebra.report.notes`).

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): the input is a
:class:`~gebra.verify.run.RunReport` and the output is text.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final, TextIO

from rich.console import Console
from rich.text import Text

from gebra.report.anchors import location_lines, location_phrase
from gebra.report.evidence import note_lines, witness_lines, witness_summary
from gebra.report.findings import Finding, findings_of, notes_of
from gebra.report.notes import detail_text, note_heading
from gebra.report.rules import RULE_COPY
from gebra.verify.base import ClaimClass, PropertySlug, Severity
from gebra.verify.registry import MARKER_REASONS, NotImplementedMarker, property_entry
from gebra.verify.report import PropertyReport
from gebra.verify.run import GateOutcome, Promotion, RunReport, Subject

__all__ = ["TerminalOptions", "render_human", "write_human"]

#: The severity styles PD-031 sketches (red family for fatal/error, amber for warning). The
#: exact palette is CLI-03's latitude; what is not latitude is that the severity **word** is
#: always spelled out, so a plain rendering loses nothing (§5.1 rule 3).
_SEVERITY_STYLE: Final[dict[str, str]] = {
    "fatal": "bold red",
    "error": "red",
    "warning": "yellow",
    "note": "cyan",
    "pass": "green",
    "not checked": "dim",
}

_LABEL_STYLE: Final = "dim"
_HEADING_STYLE: Final = "bold"

#: The style of an extraction note's label — the witness note's colour, because neither is a
#: severity; the label word, not the colour, is what says which kind of note it is.
_NOTE_STYLE: Final = _SEVERITY_STYLE["note"]

#: Width of the label column in an evidence line. Layout is CLI-03's latitude (§4.1).
_LABEL_WIDTH: Final = 24
_RECORD_INDENT: Final = 2
_EVIDENCE_INDENT: Final = 4

#: How many hex characters of a ``graph_version`` the terminal surface shows (§5.1 rule 1).
_DIGEST_PREFIX: Final = 16


@dataclass(frozen=True)
class TerminalOptions:
    """How the terminal surface is written — the §5.1 degradation table, as parameters.

    Attributes:
        color: ``True`` forces styling on, ``False`` forces it off, ``None`` leaves the
            decision to `rich`'s own detection — a tty check plus the ``NO_COLOR`` and
            ``TERM=dumb`` conventions PD-031 adopted it for. The CLI's ``--color`` /
            ``--no-color`` pair is exactly this field (CLI-SPEC §1.3). ``True`` overrides
            ``NO_COLOR`` — §5.1's "styling forced on regardless of detection" — but not
            ``TERM=dumb``, which says the terminal cannot render color at all rather than
            that the user would rather it did not.
        width: The output width, or ``None`` for `rich`'s own rule (``$COLUMNS``, else 80
            columns off a tty).
    """

    color: bool | None = None
    width: int | None = None


def _console(file: TextIO, options: TerminalOptions) -> Console:
    """A console configured for ``options`` — and for nothing `rich` would add on its own.

    ``highlight``, ``markup`` and ``emoji`` are all off: automatic number/string highlighting
    and markup interpretation would let the *content* of a node id change the styling, which
    is precisely what §5.1 rule 8's "styling only" forbids in the other direction.
    """
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


# ── Line primitives ──────────────────────────────────────────────────────────────────────


def _kv(label: str, value: str, *, indent: int = _EVIDENCE_INDENT) -> Text:
    """One evidence line: a dim label column, then the value.

    A label longer than the column keeps its single separating space rather than running into
    the value — the column is a layout convenience, and no fact is ever squeezed out of it.
    """
    line = Text(" " * indent)
    line.append(f"{label.ljust(_LABEL_WIDTH - 1)} ", style=_LABEL_STYLE)
    line.append(value)
    return line


def _blank() -> Text:
    return Text("")


def _claim(claim_class: ClaimClass) -> str:
    """The display form of a claim class — uppercase, as the SARIF bags spell it too (A.2)."""
    return claim_class.upper()


def _catalog_claim(slug: PropertySlug) -> str:
    """A passing property's claim class, read from the catalog (§4.6 rule 1)."""
    return "/".join(_claim(claim_class) for claim_class in property_entry(slug).claim_classes)


def _severity_breakdown(findings: Iterable[Finding]) -> str:
    tally: dict[Severity, int] = {"fatal": 0, "error": 0, "warning": 0}
    total = 0
    for finding in findings:
        tally[finding.severity] += 1
        total += 1
    parts = ", ".join(f"{count} {severity}" for severity, count in tally.items() if count)
    return f"{total} finding{'' if total == 1 else 's'}" + (f": {parts}" if parts else "")


# ── Report-level blocks ──────────────────────────────────────────────────────────────────


def _subject_lines(report: RunReport) -> list[Text]:
    """§5.1 rule 1: what was verified, and under which build and policy."""
    subject: Subject | None = report.subject
    heading = Text()
    heading.append(f"gebra {report.tool.version}", style=_HEADING_STYLE)
    if subject is None:
        heading.append(" — no subject was resolved")
        return [heading]
    heading.append(f" — {subject.source} ({subject.input_mode})", style=_HEADING_STYLE)
    identity = [
        f"ir_version {subject.ir_version}",
        f"graph_version {_elided_digest(subject.graph_version)}",
    ]
    if subject.version is not None:
        identity.append(f"version {subject.version}")
    if subject.extractor_version is not None:
        identity.append(f"extractor {subject.extractor_version}")
    if subject.sidecar is not None:
        identity.append(f"sidecar {subject.sidecar}")
    identity.append(f"strict {_strict_phrase(report.gate)}")
    return [heading, _kv("identity", " | ".join(identity), indent=_RECORD_INDENT)]


def _elided_digest(graph_version: str) -> str:
    """The digest as a recognizable prefix (§5.1 rule 1 licenses eliding it for length).

    The full string is one ``--format json`` away and rides every SARIF fingerprint; what the
    terminal needs is something a reader can match against another report at a glance, which
    is why the elision keeps the ``sha256:`` scheme and marks the truncation.
    """
    scheme, _, digest = graph_version.partition(":")
    if not digest or len(digest) <= _DIGEST_PREFIX:
        return graph_version
    return f"{scheme}:{digest[:_DIGEST_PREFIX]}..."


def _strict_phrase(gate: GateOutcome) -> str:
    if gate.strict.mode == "per-property":
        return f"per-property ({', '.join(gate.strict.properties)})"
    return gate.strict.mode


def _extraction_note_lines(report: RunReport) -> list[Text]:
    """§4.2's ``RunReport.extraction_notes`` rows — a block of its own, and never a finding.

    One entry per note, in emission order: its label and code, the node and slots it names, its
    message. A warning's ``detail`` follows, because a warning's message is a one-line summary
    of the record (INTROSPECTION-SPEC §8's "what it carries" column is the detail); a
    disclosure's does not, because its message states what INTROSPECTION-SPEC §8 says the record
    carries. Every record is carried whole in the native report. Nothing here is counted, graded
    or gated, and nothing is added to the summary, whose notes are witness notes (§2.1, §4.6
    rule 10).
    """
    if not report.extraction_notes:
        return []
    heading = Text()
    heading.append("extraction notes", style=_HEADING_STYLE)
    heading.append(
        " — what extraction recorded while reading this subject; not findings, and not the "
        "witness notes the summary counts: no exit code, count or strict promotion turns on "
        "them, and the native JSON report carries each record whole"
    )
    lines = [heading]
    for note in report.extraction_notes:
        header = Text(" " * _RECORD_INDENT)
        header.append(note_heading(note), style=_NOTE_STYLE)
        where = []
        if note.node is not None:
            where.append(f"node {note.node}")
        if note.slots:
            where.append(f"slots {', '.join(note.slots)}")
        if where:
            header.append(f"  [{' | '.join(where)}]", style=_LABEL_STYLE)
        lines.append(header)
        lines.append(_kv("message", note.message))
        if not note.is_disclosure and note.detail:
            lines.append(_kv("detail", detail_text(note.detail)))
    return lines


def _finding_lines(finding: Finding) -> list[Text]:
    """§4.4: one record, whole — its own severity word, its own claim class, its anchor."""
    header = Text(" " * _RECORD_INDENT)
    header.append(f"{finding.severity}: ", style=_SEVERITY_STYLE[finding.severity])
    header.append(finding.property_condition)
    attribution = f"{property_entry(finding.owner).property_id} {finding.owner}"
    if finding.origin == "advisory":
        attribution = f"advisory from {attribution}"
    elif finding.origin == "co-failure":
        attribution = f"co-failure, {attribution}"
    header.append(f"  [{attribution} | {_claim(finding.claim_class)}]", style=_LABEL_STYLE)
    lines = [header]
    lines.extend(_kv(label, value) for label, value in location_lines(finding.location))
    copy = RULE_COPY.get(finding.property_condition)
    if copy is not None:
        lines.append(_kv("finding", copy.short_description))
    if finding.subsumed_by is not None:
        lines.append(
            _kv(
                "owned upstream by",
                f"{finding.subsumed_by} — the root cause is reported there, so this is not a "
                "second charge",
            )
        )
    for key, value in finding.evidence.items():
        lines.append(_kv(_evidence_label(key), _evidence_value(key, value)))
    if finding.note is not None:
        lines.append(_kv("note", finding.note))
    for note in finding.notes:
        lines.extend(_kv(label, value) for label, value in note_lines(note))
    if finding.remediation is not None:
        lines.append(_kv("remediation", finding.remediation))
    return lines


#: The P-04 diagnostics §4.4 asks to be shown as what they are. The third (DEC-28 clause 2),
#: the fourth (DEC-33 §3.4) and the fifth (DEC-37 §3.2) carry their own gloss in the value, so
#: a reader does not take any of them for a finding: each names readers whose reads (or, for
#: the fifth, whose reads along a ``send`` edge) were not decided, not a second violation, and
#: says where the answer lives — a dynamic router, a containment root, the payload's contents.
_EVIDENCE_LABELS: Final[dict[str, str]] = {
    "gebra/writersOnOtherPaths": "writers on other paths",
    "gebra/downstreamWriters": "writers wired after the reader",
    "gebra/outsideStaticCoverage": "outside static coverage",
    "gebra/containedReaders": "contained readers",
    "gebra/payloadReaders": "payload readers",
}

_EVIDENCE_GLOSS: Final[dict[str, str]] = {
    "gebra/outsideStaticCoverage": (
        " — top-level readers no declared START-path reaches (reachable only through a dynamic "
        "router); no analysis in this run covers their reads"
    ),
    "gebra/containedReaders": (
        " — contained readers no declared START-path reaches, answered by their containment "
        "root rather than by a dynamic router; no obligation was raised and no analysis in "
        "this run covers their reads"
    ),
    "gebra/payloadReaders": (
        " — reachable readers entered through a send edge: along it their declared reads are "
        "reads of the payload it delivers, which the IR does not carry, so no obligation was "
        "raised for them and none was decided; a reader also entered by an ordinary edge is "
        "decided over that edge"
    ),
}


def _evidence_label(key: str) -> str:
    return _EVIDENCE_LABELS.get(key, key)


def _evidence_value(key: str, value: object) -> str:
    listed = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
    return f"{listed}{_EVIDENCE_GLOSS.get(key, '')}"


def _report_lines(report: PropertyReport, *, best_effort: bool) -> list[Text]:
    """One property's verdict block (§4.2's two ``PropertyReport`` rows)."""
    entry = property_entry(report.property)
    header = Text()
    header.append(f"{entry.property_id} {report.property}", style=_HEADING_STYLE)
    findings = tuple(findings_of(report))
    if report.result == "pass":
        header.append(" — ")
        header.append("pass", style=_SEVERITY_STYLE["pass"])
        header.append(f"  [{_catalog_claim(report.property)}]", style=_LABEL_STYLE)
    else:
        header.append(" — ")
        header.append("fail", style=_SEVERITY_STYLE["error"])
        header.append(f"  ({_severity_breakdown(findings)})", style=_LABEL_STYLE)
    lines = [header]
    if best_effort:
        lines.append(
            _kv(
                "best-effort",
                "P-01 found the topology ill-formed, so this property's contract does not "
                "cover it: read this as a diagnostic, not as a verdict",
                indent=_RECORD_INDENT,
            )
        )
    if report.witness is not None:
        lines.append(_kv("witness", witness_summary(report.witness), indent=_RECORD_INDENT))
        lines.extend(_kv(label, value) for label, value in witness_lines(report.witness))
    for finding in findings:
        lines.extend(_finding_lines(finding))
    return lines


def _marker_lines(marker: NotImplementedMarker) -> list[Text]:
    """§4.2's two ``NotImplementedMarker`` rows — *not checked*, and explicitly not a pass.

    The reason each status states is the registry's, keyed by the status itself
    (:data:`~gebra.verify.registry.MARKER_REASONS` — for ``deferred-to-phase-1`` the
    charter's own words, DEC-42 §3.1), and the detail beneath it carries the registry's copy
    with its "No verdict was reached — this is not a pass." verbatim.
    """
    header = Text()
    header.append(f"{marker.property_id} {marker.property}", style=_HEADING_STYLE)
    header.append(" — ")
    header.append("not checked", style=_SEVERITY_STYLE["not checked"])
    header.append(f"  [{marker.status}]", style=_LABEL_STYLE)
    reason = f"no verdict was reached — this is not a pass: it {MARKER_REASONS[marker.status]}"
    return [header, _kv("status", reason, indent=_RECORD_INDENT), _kv("detail", marker.detail)]


def _tool_error_lines(report: RunReport) -> list[Text]:
    """§4.2's ``ToolError`` row: where it stopped, and that no verdict was reached."""
    error = report.error
    assert error is not None  # the model's own present-iff rule (§1.2)
    header = Text()
    header.append("tool error", style=_SEVERITY_STYLE["fatal"])
    header.append(" — no verdict was reached; this is not a verification result")
    return [
        header,
        _kv("stage", error.stage, indent=_RECORD_INDENT),
        _kv("detail", error.detail, indent=_RECORD_INDENT),
    ]


def _promotion_line(promotion: Promotion) -> str:
    """§4.2's ``Promotion`` row: what a strict policy selected, and under which identity."""
    promoted = promotion.note_kind if promotion.origin == "witness-note" else None
    identity = promoted or promotion.property_condition or "(no identity is fixed for it)"
    where = f" at {location_phrase(promotion.location)}" if promotion.location is not None else ""
    reported_as = (
        f", reported under {promotion.property_condition}"
        if promotion.origin == "witness-note" and promotion.property_condition is not None
        else ""
    )
    return (
        f"{property_entry(promotion.property).property_id} {promotion.property}: "
        f"{identity} ({promotion.origin}){reported_as}{where}"
    )


def _properties_phrase(report: RunReport, reported: int, markers: int) -> str:
    """§5.1 rule 6's "how many properties produced no verdict".

    A tool-error run gets its own sentence rather than the arithmetic: §2.4 keeps ``properties``
    empty there, so "0 produced no verdict" would be read as *none failed to produce one*, which
    inverts what happened.
    """
    if report.error is not None:
        return "none — the run reached no verdict for any property"
    return f"{reported} reported | {markers} produced no verdict"


def _summary_lines(report: RunReport) -> list[Text]:
    """§5.1 rule 6, read off ``gate`` — the counts, the code and its reason, and the policy."""
    gate = report.gate
    counts = gate.counts
    reported = sum(1 for outcome in report.properties if isinstance(outcome, PropertyReport))
    markers = len(report.properties) - reported
    notes = [
        note
        for outcome in report.properties
        if isinstance(outcome, PropertyReport)
        for note in notes_of(outcome)
    ]
    warning_notes = sum(1 for note in notes if note.severity == "warning")

    heading = Text()
    heading.append("summary", style=_HEADING_STYLE)
    lines = [
        heading,
        _kv(
            "findings",
            f"{counts.fatal} fatal | {counts.error} error | {counts.warning} warning",
            indent=_RECORD_INDENT,
        ),
        _kv(
            "notes", f"{len(notes)} carried ({warning_notes} warning-grade)", indent=_RECORD_INDENT
        ),
        _kv("properties", _properties_phrase(report, reported, markers), indent=_RECORD_INDENT),
        _kv("strict", _strict_phrase(gate), indent=_RECORD_INDENT),
    ]
    if gate.promotions:
        lines.append(
            _kv(
                "promotions",
                (
                    f"{len(gate.promotions)} selected — each record is unchanged and keeps "
                    "its own warning grade"
                ),
                indent=_RECORD_INDENT,
            )
        )
        lines.extend(_kv("promoted", _promotion_line(promotion)) for promotion in gate.promotions)
    elif gate.strict.mode != "off":
        lines.append(
            _kv(
                "promotions",
                "none — the policy selected no warning-grade record",
                indent=_RECORD_INDENT,
            )
        )
    if report.best_effort:
        lines.append(
            _kv(
                "best-effort",
                (
                    f"{', '.join(report.best_effort)} — answered on topology P-01 found "
                    "ill-formed, so those reports are diagnostics, not verdicts"
                ),
                indent=_RECORD_INDENT,
            )
        )
    exit_line = Text(" " * _RECORD_INDENT)
    exit_line.append(f"{'exit'.ljust(_LABEL_WIDTH - 1)} ", style=_LABEL_STYLE)
    exit_line.append(
        f"{gate.exit_code}", style=_SEVERITY_STYLE["fatal" if gate.exit_code else "pass"]
    )
    exit_line.append(f" — {_EXIT_REASON[gate.outcome]}")
    lines.append(exit_line)
    if not gate.snapshot_eligible:
        lines.append(_kv("snapshot", _SNAPSHOT_REASON[gate.exit_code == 2], indent=_RECORD_INDENT))
    return lines


#: Why the run took the code it took (§5.1 rule 6), one phrase per §2.2 outcome.
_EXIT_REASON: Final[dict[str, str]] = {
    "pass": "no warning-grade finding or note was carried",
    "pass-with-notes": "warning-grade records were carried, and none was promoted",
    "fail": "a FATAL or ERROR finding is present, or a strict policy promoted a warning",
    "tool-error": "no verdict was reached",
}

_SNAPSHOT_REASON: Final[dict[bool, str]] = {
    False: "not recorded for this run: a FATAL finding is present (PROPERTY-CATALOG-SPEC §0.2)",
    True: "not recorded for this run: no verdict was reached",
}


# ── The surface ──────────────────────────────────────────────────────────────────────────


def _lines(report: RunReport) -> list[Text]:
    """Every line of the human surface, in order.

    The extraction notes come straight after the subject they qualify, on a tool-error run as
    on a verdict run: a run that reached no verdict after an extraction that warned is exactly
    the run whose notes say most about why.
    """
    lines = _subject_lines(report)
    notes = _extraction_note_lines(report)
    if notes:
        lines.append(_blank())
        lines.extend(notes)
    if report.error is not None:
        lines.append(_blank())
        lines.extend(_tool_error_lines(report))
        lines.append(_blank())
        lines.extend(_summary_lines(report))
        return lines
    best_effort = set(report.best_effort)
    for outcome in report.properties:
        lines.append(_blank())
        if isinstance(outcome, PropertyReport):
            lines.extend(_report_lines(outcome, best_effort=outcome.property in best_effort))
        else:
            lines.extend(_marker_lines(outcome))
    lines.append(_blank())
    lines.extend(_summary_lines(report))
    return lines


def write_human(report: RunReport, stream: TextIO, options: TerminalOptions | None = None) -> None:
    """Write the human surface of ``report`` to ``stream`` (§5, PD-031)."""
    console = _console(stream, options or TerminalOptions())
    for line in _lines(report):
        console.print(line)


def render_human(report: RunReport, options: TerminalOptions | None = None) -> str:
    """The human surface of ``report`` as text.

    With ``options.color`` left at ``None`` the buffer is not a terminal, so `rich` writes
    plain text — the same auto-detection a redirected CLI invocation gets (§5.1).
    """
    buffer = io.StringIO()
    write_human(report, buffer, options)
    return buffer.getvalue()
