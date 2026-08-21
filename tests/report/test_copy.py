"""CLI-03 acceptance box 3 — the TE-15 honest-claims lint over *rendered* copy (card CLI-03).

The file-level lint (`tools/honest_claims_lint.py`, the CI `honest-claims` job) already scans
``src/**/*.py``, so this package's templates are in scope. That is not the whole of §4.6 rule 4,
which says the ban reaches "strings a renderer assembles at run time" and that "a template that
composes a banned phrase from parts is still a violation". A phrase split across two f-strings,
or completed by a node id, passes the file scan and fails the rule.

So this module runs the lint's **own** matcher — the same
``tools/honest-claims-phrases.txt``, loaded by the same loader — over the text every §4 variant
actually renders, on all three surfaces. Composition is then covered by construction.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest

import tools.honest_claims_lint as lint_module
from gebra.report import REPORT_FORMATS, ReportFormat, render
from gebra.report.human import TerminalOptions
from gebra.report.rules import SARIF_RULE_ENTRIES, rule_copy
from tests.report.variants import CASES
from tools.honest_claims_lint import load_phrases

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PHRASES_PATH: Final = REPO_ROOT / "tools" / "honest-claims-phrases.txt"
PHRASES: Final = load_phrases(PHRASES_PATH)

#: **No banned phrase is spelled anywhere in this file.** This module is repo-authored prose
#: like any other, and a test that quoted the list to prove the list was loaded would be the
#: exact thing WA-06 scans for. Every phrase this module needs comes out of :data:`PHRASES` at
#: run time, which is also the stronger check: the assertions track the file CI reads rather
#: than a copy of it that can go stale.


def _violations(text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in PHRASES if phrase in lowered]


def test_the_phrase_list_is_the_one_ci_enforces() -> None:
    """The matcher below is worth exactly the list it loads, so it loads the CI job's own.

    ``tools/honest_claims_lint.py`` defaults to the file beside it, and the ``honest-claims``
    workflow job runs that script with no ``--phrases``; this asserts the path resolved here is
    that same default, so widening the list widens this suite too.
    """
    default_phrases = Path(lint_module.__file__).resolve().parent / "honest-claims-phrases.txt"
    assert PHRASES_PATH == default_phrases
    assert len(PHRASES) >= 5
    assert all(phrase and phrase == phrase.lower() for phrase in PHRASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("report_format", REPORT_FORMATS)
def test_rendered_output_carries_no_banned_phrase(case: Any, report_format: ReportFormat) -> None:
    """Acceptance box 3, on the rendered text rather than on the templates that made it."""
    text = render(case.report, report_format, terminal=TerminalOptions(color=False, width=100))
    assert not _violations(text), f"{case.name}/{report_format}: {_violations(text)}"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_styled_rendering_carries_no_banned_phrase(case: Any) -> None:
    """Styling inserts escapes between characters, so the styled text is scanned too."""
    text = render(case.report, "human", terminal=TerminalOptions(color=True, width=100))
    assert not _violations(text)


def test_the_rule_catalog_copy_carries_no_banned_phrase() -> None:
    """A.3's prose is repo-authored and is held to §4.6 like every other string."""
    for entry in SARIF_RULE_ENTRIES:
        copy = rule_copy(entry.id)
        text = f"{copy.short_description} {copy.full_description} {copy.help_text}"
        assert not _violations(text), entry.id


def test_the_matcher_reports_a_violation_when_one_is_present() -> None:
    """The negative control for box 3: a matcher that never reported anything would make every
    assertion above vacuous.

    The probe is composed from the loaded list at run time rather than written out, for the
    reason recorded at the top of this module — and it is the sharper test either way, since it
    exercises whichever entries the list actually holds.
    """
    for phrase in PHRASES:
        probe = f"a sentence carrying {phrase} in the middle of it"
        assert phrase in _violations(probe)
    assert not _violations("a sentence that overstates nothing at all")


def test_no_rendering_calls_a_marker_a_pass() -> None:
    """§4.6 rule 5, checked as copy rather than as layout."""
    for case in CASES:
        text = render(case.report, "human", terminal=TerminalOptions(color=False, width=100))
        flat = " ".join(text.split())
        if "not checked" in flat:
            assert "this is not a pass" in flat


def test_no_rendering_claims_a_property_was_verified_at_runtime() -> None:
    """§4.6 rule 3: the subject is the definition; gebra observes no run (D-018)."""
    banned = ("at runtime", "while running", "during execution", "the agent behaves")
    for case in CASES:
        for report_format in REPORT_FORMATS:
            flat = " ".join(render(case.report, report_format).split()).lower()
            for phrase in banned:
                assert phrase not in flat, f"{case.name}/{report_format}: {phrase}"
