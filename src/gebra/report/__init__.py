"""The shared rendering layer — one run report, three surfaces (REPORT-FORMAT-SPEC §0.1).

A verification run produces exactly one logical artifact, the :class:`~gebra.verify.run.RunReport`
that :func:`gebra.verify.verify` returns. This package is the layer that shows it:

============ ====================== ======================================================
Surface      Entry point            What it is
============ ====================== ======================================================
human        :func:`render_human`   A **rendering** (§4, §5) on the CLI-D3 framework
                                    (PD-031, `rich`). Every fact it shows is read off the
                                    run report; it adds none.
json         :func:`render_native`  The run report **itself**, serialized under §1.5.
                                    Lossless.
sarif        :func:`render_sarif`   A **projection** (Appendix A): SARIF 2.1.0, lossy,
                                    findings-only, never round-tripped.
============ ====================== ======================================================

:func:`render` is the one call a caller with a ``--format`` flag makes; the three named
functions are there for a caller that already knows which surface it wants (the pytest plugin
consumes the native report, per §7).

One diagnostics utility lives here too, because CLI-SPEC §7 puts it on this card:
:func:`did_you_mean` and :func:`suggestion_sentence` are §5.4's ``difflib`` suggestions over a
**closed** vocabulary — display-only, and never a selection made on a user's behalf.

**Presentation only.** Nothing here reaches a verdict, invents an exit code, or recomputes a
structural fact: the severity tally is ``gate.counts``, the code is ``gate.exit_code``, the
promotions are ``gate.promotions``, and a finding's severity and claim class are the record's
own (CLI-SPEC §0.1). The copy rules of §4.6 bind every string this package emits, including
the ones it assembles at run time — ``tests/report/test_copy.py`` runs the TE-15 banned-phrase
matcher over the *rendered* output of every §4 variant, not only over these templates.

**Never-invokes.** No module here imports langgraph, executes a workflow node, calls a model
or opens a network connection (WA-07). The input is a validated run report and the output is
text; even the SARIF ``$schema`` URI is a pointer written into the log, never a fetch.

Example — the shape a CLI or a plugin calls::

    from gebra.report import ReportFormat, TerminalOptions, render
    from gebra.verify import verify

    report = verify(ir)
    text = render(report, "human", terminal=TerminalOptions(color=False))
    report.gate.exit_code            # the contract; the rendering never moves it
"""

from __future__ import annotations

from typing import Final, Literal, TextIO, TypeAlias, get_args

from gebra.report.anchors import LogicalAnchor, location_lines, location_phrase, logical_anchor
from gebra.report.evidence import witness_lines, witness_summary
from gebra.report.findings import Finding, FindingOrigin, findings_of, notes_of
from gebra.report.human import TerminalOptions, render_human, write_human
from gebra.report.native import native_data, render_native
from gebra.report.rules import RULE_COPY, RuleCopy, rule_copy
from gebra.report.sarif import (
    SARIF_SCHEMA_URI,
    SARIF_VERSION,
    render_sarif,
    sarif_log,
    subject_slug,
)
from gebra.report.suggestions import (
    MAX_SUGGESTIONS,
    SIMILARITY_THRESHOLD,
    did_you_mean,
    suggestion_sentence,
)
from gebra.verify.run import RunReport

__all__ = [
    "MAX_SUGGESTIONS",
    "REPORT_FORMATS",
    "RULE_COPY",
    "SARIF_SCHEMA_URI",
    "SARIF_VERSION",
    "SIMILARITY_THRESHOLD",
    "Finding",
    "FindingOrigin",
    "LogicalAnchor",
    "ReportFormat",
    "RuleCopy",
    "TerminalOptions",
    "did_you_mean",
    "findings_of",
    "location_lines",
    "location_phrase",
    "logical_anchor",
    "native_data",
    "notes_of",
    "render",
    "render_human",
    "render_native",
    "render_sarif",
    "rule_copy",
    "sarif_log",
    "subject_slug",
    "suggestion_sentence",
    "witness_lines",
    "witness_summary",
    "write",
    "write_human",
]

#: The three surfaces of §0.1, spelled as CLI-SPEC §4.1's ``--format`` values.
ReportFormat: TypeAlias = Literal["human", "json", "sarif"]

#: The same three, for a caller that enumerates them (a flag's closed value set, a
#: did-you-mean candidate list).
REPORT_FORMATS: Final[tuple[ReportFormat, ...]] = get_args(ReportFormat)


def render(
    report: RunReport,
    report_format: ReportFormat = "human",
    *,
    terminal: TerminalOptions | None = None,
    for_file: bool = False,
) -> str:
    """Render ``report`` on one of the three surfaces.

    Args:
        report: The run report to show. It is shown as it stands: a tool-error run renders as
            a tool error on every surface, because §2.4 keeps exit 2 from ever reading as a
            clean run.
        report_format: Which surface — ``human`` is the no-flag default (CLI-SPEC §4.1).
        terminal: Styling and width for the human surface; ignored by the machine surfaces,
            which are not renderings (PD-031 finding 5).
        for_file: Whether the text is destined for a file, which §1.5 ends with a single
            trailing newline. The human surface is a stream rendering and is unaffected.

    Returns:
        The text of the chosen surface.
    """
    if report_format == "human":
        return render_human(report, terminal)
    if report_format == "json":
        return render_native(report, for_file=for_file)
    if report_format == "sarif":
        return render_sarif(report, for_file=for_file)
    raise ValueError(
        f"{report_format!r} is not one of the three surfaces of REPORT-FORMAT-SPEC §0.1: "
        f"{', '.join(REPORT_FORMATS)}"
    )


def write(
    report: RunReport,
    stream: TextIO,
    report_format: ReportFormat = "human",
    *,
    terminal: TerminalOptions | None = None,
) -> None:
    """Write ``report`` to ``stream`` on the chosen surface (CLI-SPEC §5.2: stdout is the artifact).

    The human surface is written through the console so that `rich`'s own capability detection
    sees the real stream — a tty gets styling, a redirected stream does not, and neither is
    decided here (§5.1).
    """
    if report_format == "human":
        write_human(report, stream, terminal)
        return
    stream.write(render(report, report_format))
