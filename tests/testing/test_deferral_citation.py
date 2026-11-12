"""Where the SOW §8 citation lives once the skip's own copy no longer carries it (PD-072 §1).

The acceptance checklist's C2 clause (3) asks that every deferred component be "an explicit
structured skip naming the property and citing SOW §8". DEC-35 §3.1 moved that citation out of
the skip's copy — the harness's deferral outcome now states the charter's copy for the token —
"into the registry's docstring and the governance records, where it remains the reason the
token exists". PD-072 §1, ratified with the clause re-signed and its wording unchanged, pins the
reading this repository now checks: the skip carries the ``deferred-to-phase-1`` token, names
its property and states the charter's words, and SOW §8 is named as the reason the token exists
at four sites — the registry's docstring, VALIDATOR-API-FREEZE §4's entry for the change, the
fidelity matrix's status table and the R3.3 line ``tools/corpus_green.py`` prints.

This module holds those four sites to the sentence, and holds every text that says R3's clauses
hold as written to naming PD-072 for R3.3, the way R3.1's finding names its own re-sign. A site
that loses the sentence, or a text that goes back to claiming the clause holds as first written,
fails here by name.

Nothing here executes a workflow node, calls a model or opens a network connection (WA-07): it
reads two governance files and four docstrings, and has the corpus-green gate assemble its
R3.3 lines over an empty run and a hand-built one, and its verdict over a hand-built report.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import gebra.verify.registry as registry_module
from gebra.testing.harness import CorpusRun, Obligation, Outcome
from tools.corpus_green import ClauseResult, GreenReport, _clause_r33, format_report

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
FREEZE_RECORD: Final = REPO_ROOT / "docs" / "governance" / "VALIDATOR-API-FREEZE.md"
FIDELITY_MATRIX: Final = REPO_ROOT / "docs" / "governance" / "FIDELITY-MATRIX.md"

#: The sentence each site carries, compared with backticks dropped and whitespace folded, so a
#: Markdown span, a reStructuredText literal and a wrapped line all read the same.
CITATION: Final = "SOW §8 is the reason the deferred-to-phase-1 token exists"


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", ""))


def _cites(text: str) -> bool:
    return CITATION in _plain(text)


def _val16_entry() -> str:
    """VALIDATOR-API-FREEZE §4's entry for VAL-16, alone."""
    section = FREEZE_RECORD.read_text(encoding="utf-8").split(
        "**Amendments landed under this policy.**"
    )[1]
    (entry,) = [item for item in section.split("\n- ") if item.startswith("**VAL-16 ")]
    return entry.split("\n## ")[0]


def _matrix_status_row() -> str:
    """The fidelity matrix's status-table row for ``deferred-to-phase-1``."""
    (row,) = [
        line
        for line in FIDELITY_MATRIX.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `deferred-to-phase-1` |")
    ]
    return row


def _matrix_as_written_paragraph() -> str:
    """The fidelity matrix's paragraph that quotes PD-006 R3's four clauses as written."""
    text = FIDELITY_MATRIX.read_text(encoding="utf-8")
    (paragraph,) = [
        block
        for block in text.split("\n\n")
        if block.startswith("The acceptance reading this implements is PD-006 R3")
    ]
    return paragraph


# ── The four sites (PD-072 §1, item 2) ───────────────────────────────────────────────────


def test_the_registry_docstring_names_sow_8_as_the_reason_the_token_exists() -> None:
    assert registry_module.__doc__ is not None
    assert _cites(registry_module.__doc__)


def test_the_freeze_records_entry_names_sow_8_as_the_reason_the_token_exists() -> None:
    """The entry used to say only that the citation moved there; it now carries the clause."""
    entry = _val16_entry()
    assert _cites(entry)
    assert "PD-072" in entry


def test_the_fidelity_matrix_status_table_names_sow_8_as_the_reason_the_token_exists() -> None:
    assert _cites(_matrix_status_row())


def test_the_r33_line_the_gate_prints_names_sow_8_as_the_reason_the_token_exists() -> None:
    """R3.3's first line, printed on every run, met or not — an empty run prints it too."""
    assert _cites(_clause_r33(CorpusRun(())).findings[0])
    assert _cites(_clause_r33(_failing_run()).findings[0])


def test_the_citation_test_sees_a_missing_sentence() -> None:
    """Arms the four tests above: the old wording, which named no reason, does not pass."""
    assert not _cites(
        "with the SOW §8 citation moved into the registry's docstring and this record"
    )
    assert _cites("SOW §8 is the reason the ``deferred-to-phase-1``\n  token exists")


# ── Every text that says R3's clauses hold as written names PD-072 for R3.3 ──────────────


def test_the_verdict_line_names_the_re_signs() -> None:
    met = format_report(GreenReport([ClauseResult("R3.3", "skip layer")]))
    (verdict,) = [line for line in met.splitlines() if line.startswith("verdict:")]
    assert "criterion 2 MET" in verdict
    assert "PD-072" in verdict and "PD-039" in verdict


def test_the_two_met_docstrings_name_the_re_signs() -> None:
    for owner in (ClauseResult, GreenReport):
        doc = owner.__dict__["met"].__doc__  # the property object, not its value
        assert isinstance(doc, str), owner
        assert "PD-072" in doc, owner
        assert "literally" not in doc, owner


def test_r33_names_pd_072_in_its_finding_and_its_docstring() -> None:
    """The re-signed reading is claimed by the line that says R3.3 is MET, and only there."""
    first, met = _clause_r33(CorpusRun(())).findings
    assert "PD-072" not in first
    assert met.startswith("R3.3 is MET as re-signed") and "PD-072" in met
    assert _clause_r33.__doc__ is not None and "PD-072" in _clause_r33.__doc__


def _failing_run() -> CorpusRun:
    """One deferred obligation reported as a comparison — the shape R3.3 refuses."""
    obligation = Obligation(
        "retry-coherence/negative-01-nonidempotent-fare-poll-reentry.yaml",
        "retry-coherence",
        "report",
    )
    return CorpusRun((Outcome(obligation, "matched", "forged"),))


def test_a_failing_r33_claims_no_re_signed_reading() -> None:
    """Like R3.1's "MET as re-signed", R3.3's is printed only when the clause has no violation.

    A run whose deferred component is not a skip prints the violation, the SOW §8 line and
    nothing that says the clause holds — never a claim beside a FAIL mark.
    """
    clause = _clause_r33(_failing_run())
    assert clause.violations and not clause.met
    assert len(clause.findings) == 1
    assert "MET" not in clause.findings[0] and "PD-072" not in clause.findings[0]
    report = format_report(GreenReport([clause]))
    assert "re-signed" not in report.split("violations")[0]
    assert "criterion 2 MET" not in report


def test_the_matrix_paragraph_quoting_r3_as_written_names_pd_072_for_r33() -> None:
    paragraph = _plain(_matrix_as_written_paragraph())
    assert "citing SOW §8" in paragraph  # the clause is still quoted as signed
    assert "PD-072" in paragraph
