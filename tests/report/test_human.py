"""The human surface against REPORT-FORMAT-SPEC §4/§5 and PD-031 (card CLI-03).

Goldens pin *what* was rendered; the assertions below pin the obligations a golden cannot
express — that degradation changes styling only, that the claim class is displayed with every
verdict, that a marker never reads as a pass, that the tally comes off ``gate``.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07).
"""

from __future__ import annotations

import io
import re
from typing import Any

import pytest

from gebra.report import render_human, write_human
from gebra.report.human import TerminalOptions
from gebra.verify.registry import property_entry
from gebra.verify.report import PropertyReport
from gebra.verify.run import StrictPolicy
from tests.report.goldens import compare_golden
from tests.report.variants import CASES, case_report

#: Fixed for the goldens: `rich` wraps at the console width, so a golden pins a width too.
GOLDEN_OPTIONS = TerminalOptions(color=False, width=100)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def _flat(text: str) -> str:
    """``text`` with runs of whitespace collapsed — for prose assertions that `rich` wraps."""
    return " ".join(text.split())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_human_golden(case: Any) -> None:
    """Every catalog variant renders to its committed golden, byte for byte."""
    compare_golden(f"human/{case.name}.txt", render_human(case.report, GOLDEN_OPTIONS))


# ── §5.1 rule 8 / PD-031: degradation changes styling only ───────────────────────────────


@pytest.fixture
def styling_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal with no opinion of its own.

    `rich` honours ``NO_COLOR``, ``TERM=dumb`` and ``FORCE_COLOR`` — PD-031 adopted it partly
    for that — so a test about the *renderer's* styling has to say what the environment is,
    or a CI runner that sets one of them decides the assertion instead. The conventions
    themselves are asserted below, where they are the subject.
    """
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLUMNS"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.usefixtures("styling_environment")
def test_styled_and_plain_differ_only_by_ansi(case: Any) -> None:
    """The rule as an equality: strip the escapes from the styled output and it *is* the plain
    one — no finding dropped, reordered, truncated or reworded."""
    styled = render_human(case.report, TerminalOptions(color=True, width=100))
    plain = render_human(case.report, TerminalOptions(color=False, width=100))
    assert _plain(styled) == plain
    assert styled != plain or not plain.strip(), "forcing color emitted no styling at all"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_plain_output_carries_no_escape_sequences(case: Any) -> None:
    """A redirected CLI run must never write raw ANSI into a log file (§5.1, PD-031)."""
    assert "\x1b" not in render_human(case.report, TerminalOptions(color=False, width=100))


def test_the_default_is_auto_detection_and_a_buffer_is_not_a_terminal() -> None:
    """No flag, a non-tty destination: plain, which is the common CI case (§5.1 row 3)."""
    assert "\x1b" not in render_human(CASES[0].report)


class _FakeTerminal(io.StringIO):
    """A destination that claims to be a tty, so `rich`'s auto-detection has something to
    detect. Without it every test writes to a buffer and the conventions below never fire."""

    def isatty(self) -> bool:
        return True


def _on_a_terminal(options: TerminalOptions) -> str:
    stream = _FakeTerminal()
    write_human(CASES[0].report, stream, options)
    return stream.getvalue()


#: An SGR sequence whose parameters set a foreground/background colour (30-49, 90-107, or the
#: 38/48 extended forms). Attributes like bold (1) and dim (2) are not colour codes.
_COLOR_CODE = re.compile(r"\x1b\[(?P<params>[0-9;]*)m")


def _color_codes(text: str) -> list[str]:
    found = []
    for match in _COLOR_CODE.finditer(text):
        params = [int(value) for value in match.group("params").split(";") if value]
        if any(30 <= value <= 49 or 90 <= value <= 107 for value in params):
            found.append(match.group(0))
    return found


@pytest.mark.usefixtures("styling_environment")
def test_a_real_terminal_gets_styling() -> None:
    """The control for the two conventions below: on a tty with no opinion, colour is used."""
    assert _color_codes(_on_a_terminal(TerminalOptions(width=100)))


@pytest.mark.parametrize(("variable", "value"), [("NO_COLOR", "1"), ("TERM", "dumb")])
@pytest.mark.usefixtures("styling_environment")
def test_the_terminal_conventions_emit_no_color_codes(
    variable: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.1 row 2 / CLI-SPEC §6.2: with no flag, ``NO_COLOR`` and ``TERM=dumb`` mean "no colour
    codes" even on a real terminal — and the content is unchanged, which is the half of the
    rule that matters (§5.1 rule 8)."""
    monkeypatch.setenv(variable, value)
    rendered = _on_a_terminal(TerminalOptions(width=100))
    assert not _color_codes(rendered), f"{variable}={value} still emitted colour"
    # Words, not bytes: `rich` pins a dumb terminal to 80 columns whatever width it is given,
    # so the *wrapping* moves. What may not move is the content.
    assert _plain(rendered).split() == render_human(CASES[0].report, GOLDEN_OPTIONS).split()


@pytest.mark.usefixtures("styling_environment")
def test_forcing_color_overrides_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """§5.1's "``--color``: styling forced on regardless of detection". ``NO_COLOR`` is a
    preference, and an explicit flag is the later, more specific statement of one."""
    monkeypatch.setenv("NO_COLOR", "1")
    assert _color_codes(_on_a_terminal(TerminalOptions(color=True, width=100)))


@pytest.mark.usefixtures("styling_environment")
def test_forcing_color_cannot_undo_a_dumb_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one limit worth stating: ``TERM=dumb`` says the terminal cannot render colour, not
    that the user would rather it did not, so forcing does not reach it."""
    monkeypatch.setenv("TERM", "dumb")
    assert not _color_codes(_on_a_terminal(TerminalOptions(color=True, width=100)))


@pytest.mark.parametrize("case", CASES[:4], ids=lambda case: case.name)
def test_narrowing_the_width_drops_no_content(case: Any) -> None:
    """Wrapping is a layout event; the words are the same ones (§5.1 rule 8's spirit)."""
    wide = render_human(case.report, TerminalOptions(color=False, width=200)).split()
    narrow = render_human(case.report, TerminalOptions(color=False, width=60)).split()
    assert wide == narrow


def test_write_human_writes_to_the_stream_it_is_given() -> None:
    import io

    buffer = io.StringIO()
    write_human(CASES[0].report, buffer, TerminalOptions(color=False, width=100))
    assert buffer.getvalue() == render_human(CASES[0].report, GOLDEN_OPTIONS)


# ── §5.1's own numbered obligations ──────────────────────────────────────────────────────


def test_the_subject_line_identifies_what_was_verified() -> None:
    """Rule 1: the source, the digest as a recognizable prefix, ir_version, and the label."""
    report = next(case.report for case in CASES if case.name == "rich-witnesses")
    text = render_human(report, GOLDEN_OPTIONS)
    subject = report.subject
    assert subject is not None
    flat = _flat(text)
    assert subject.source in flat
    assert "ir_version 1.0" in flat
    assert subject.graph_version[:23] in flat, "the digest prefix must be recognizable"
    assert f"version {subject.version}" in flat, "a snapshot subject shows its V.S.F.E label"


def test_every_finding_carries_its_own_severity_word_and_claim_class() -> None:
    """Rules 2–3 and §4.6 rule 1: the envelope's own word, and a class beside every record."""
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    text = render_human(report, GOLDEN_OPTIONS)
    for outcome in report.properties:
        if not isinstance(outcome, PropertyReport) or outcome.failure is None:
            continue
        failure = outcome.failure
        assert f"{failure.severity}: {failure.property_condition}" in text
        assert failure.claim_class.upper() in text
        for co_failure in failure.co_failures or ():
            assert f"{co_failure.severity}: {co_failure.property_condition}" in text
            assert co_failure.claim_class.upper() in text
        for advisory in failure.advisories or ():
            assert f"advisory from {property_entry(advisory.property).property_id}" in text


def test_fatal_is_not_collapsed_into_error() -> None:
    """Rule 3: the human surface keeps the §0.2 distinction SARIF is forced to lose."""
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    text = render_human(report, GOLDEN_OPTIONS)
    assert "fatal: " in text
    assert "error: " in text


def test_pass_reports_are_shown_with_a_class_and_a_witness_summary() -> None:
    """Rule 4: a reader sees what was checked, not merely that nothing was said."""
    text = render_human(CASES[0].report, GOLDEN_OPTIONS)
    assert "P-01 graph-well-formed — pass" in text
    assert "[DEFENSIBLE]" in text
    assert "witness" in text


def test_markers_are_shown_and_never_as_a_pass() -> None:
    """Rule 5 and §4.6 rule 5: *not checked*, with the status, and explicitly not a pass."""
    text = render_human(CASES[0].report, GOLDEN_OPTIONS)
    assert "P-03 signature-soundness — not checked" in text
    assert "[deferred-to-phase-1]" in text
    assert "this is not a pass" in text
    assert "8 produced no verdict" in text


def test_the_summary_closes_the_run_with_the_gate_it_was_given() -> None:
    """Rule 6, read off ``gate`` rather than recounted (CLI-SPEC §0.1 rule 3)."""
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    text = render_human(report, GOLDEN_OPTIONS)
    counts = report.gate.counts
    assert f"{counts.fatal} fatal | {counts.error} error | {counts.warning} warning" in text
    assert f"exit                    {report.gate.exit_code}" in text
    assert "5 reported | 8 produced no verdict" in text


def test_snapshot_ineligibility_is_stated_with_its_reason() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    assert not report.gate.snapshot_eligible
    flat = _flat(render_human(report, GOLDEN_OPTIONS))
    assert "snapshot not recorded for this run: a FATAL finding is present" in flat


def test_a_snapshot_eligible_run_says_nothing_about_snapshots() -> None:
    """Rule 6 asks for the line "when it is ``false``" — a clean run needs no such sentence."""
    assert "snapshot" not in render_human(CASES[0].report, GOLDEN_OPTIONS).lower()


def test_best_effort_is_stated_where_its_reports_are() -> None:
    """Rule 7: silence here is the failure mode the field exists to prevent."""
    report = next(case.report for case in CASES if case.name == "p01-fatal-best-effort")
    text = render_human(report, GOLDEN_OPTIONS)
    assert report.best_effort
    block, _, summary = text.partition("summary")
    assert "best-effort" in block
    for slug in report.best_effort:
        assert slug in summary
    assert block.count("best-effort") == len(report.best_effort)
    assert "diagnostic" in block


# ── §4.6's copy rules, on the surface a person reads ─────────────────────────────────────


def test_a_promotion_is_rendered_as_a_gate_decision_not_a_finding() -> None:
    """§4.6 rules 6 and 8: the record is unchanged and keeps its own warning grade."""
    report = next(case.report for case in CASES if case.name == "wedge-failures-strict")
    text = render_human(report, GOLDEN_OPTIONS)
    assert report.gate.promotions
    assert "each record is unchanged and keeps its own warning grade" in _flat(text)
    for promotion in report.gate.promotions:
        assert f"({promotion.origin})" in text


def test_a_promoted_note_names_the_identity_it_is_reported_under() -> None:
    """§2.3's `1.1` amendment: P-02's note promotes under a condition ID it is *named* by."""
    report = next(case.report for case in CASES if case.name == "rich-witnesses-strict")
    promotions = [p for p in report.gate.promotions if p.origin == "witness-note"]
    assert promotions
    text = render_human(report, GOLDEN_OPTIONS)
    for promotion in promotions:
        assert promotion.note_kind is not None
        assert promotion.note_kind in text
        if promotion.property_condition is not None:
            assert f"reported under {promotion.property_condition}" in text


def test_a_strict_policy_with_no_promotion_says_so() -> None:
    report = case_report({}, strict=StrictPolicy(mode="all"))
    assert "none — the policy selected no warning-grade record" in _flat(
        render_human(report, GOLDEN_OPTIONS)
    )


def test_a_tool_error_never_reads_as_a_clean_run() -> None:
    """§2.4/§5.5: the stage, the detail, and that no verdict was reached."""
    report = next(case.report for case in CASES if case.name == "tool-error")
    text = render_human(report, GOLDEN_OPTIONS)
    assert "tool error" in text
    assert "no verdict was reached" in text
    assert report.error is not None
    assert report.error.stage in text
    assert "exit                    2" in text


def test_the_determinism_caveat_is_rendered_verbatim_and_adjacent() -> None:
    """§4.3: never in a footnote a reader can miss — it sits with the claims it qualifies."""
    report = next(case.report for case in CASES if case.name == "rich-witnesses")
    text = render_human(report, GOLDEN_OPTIONS)
    assert "provider-seed-reproducibility-not-guaranteed" in text
    claims_at = text.index("declared determinism claim")
    caveat_at = text.index("provider-seed-reproducibility-not-guaranteed")
    assert 0 < caveat_at - claims_at < 600


def test_a_vacuous_determinism_pass_is_not_rendered_as_all_deterministic() -> None:
    text = render_human(CASES[0].report, GOLDEN_OPTIONS)
    assert "no node declared determinism, so nothing was checked" in _flat(text)


def test_none_required_protection_is_not_rendered_as_protected() -> None:
    """§4.3: "never rendered as 'protected'" — the region is the reason, and it is shown."""
    report = next(case.report for case in CASES if case.name == "rich-witnesses")
    flat = _flat(render_human(report, GOLDEN_OPTIONS))
    assert "no protection obligation arose here — acyclic region" in flat


def test_the_two_empty_well_formedness_tuples_are_rendered_as_evidence() -> None:
    """§4.3: "a rendering that drops them loses the claim"."""
    text = render_human(CASES[0].report, GOLDEN_OPTIONS)
    assert "orphan check" in text
    assert "reference check" in text


def test_a_capped_census_is_never_rendered_as_no_cycles() -> None:
    report = next(case.report for case in CASES if case.name == "rich-witnesses")
    flat = _flat(render_human(report, GOLDEN_OPTIONS))
    assert "enumeration stopped at the cap" in flat
    residue = flat.replace("this is not a statement that the graph has no cycles", "")
    assert "no cycles" not in residue


def test_a_vacuous_form_c_carrier_implies_no_finding() -> None:
    report = next(case.report for case in CASES if case.name == "rich-witnesses")
    flat = _flat(render_human(report, GOLDEN_OPTIONS))
    assert "no finding of any severity follows from it" in flat


def test_subsumed_records_are_shown_as_context_not_a_second_charge() -> None:
    report = next(case.report for case in CASES if case.name == "p01-fatal-best-effort")
    flat = _flat(render_human(report, GOLDEN_OPTIONS))
    assert "owned upstream by" in flat
    assert "not a second charge" in flat


def test_p04_extra_diagnostics_are_rendered_as_what_they_are() -> None:
    """§4.4: what makes the finding legible rather than baffling."""
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    text = render_human(report, GOLDEN_OPTIONS)
    assert "writers on other paths" in text
    assert "writers wired after the reader" in text
