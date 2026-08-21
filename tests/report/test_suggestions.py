"""Did-you-mean suggestions against CLI-SPEC §5.4 (card CLI-03, per §7's obligation list).

The rules are short and each is testable: `difflib` only, closed vocabularies only, at most
three candidates above a threshold, and display-only — a suggestion never selects anything.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07).
"""

from __future__ import annotations

import pytest

from gebra.report import REPORT_FORMATS
from gebra.report.suggestions import (
    MAX_SUGGESTIONS,
    SIMILARITY_THRESHOLD,
    did_you_mean,
    suggestion_sentence,
)
from gebra.verify import PROPERTY_SLUGS

#: §1.1's closed verb set — the vocabulary §5.4's first row suggests from.
VERBS = ("verify", "snapshot", "diff", "display", "history")


def test_a_near_miss_on_a_verb_is_suggested() -> None:
    assert did_you_mean("verfiy", VERBS) == ("verify",)


def test_a_retired_name_is_not_resurrected_by_a_suggestion() -> None:
    """PD-033 retired `trace` rather than aliasing it; the vocabulary is the five verbs."""
    assert "trace" not in did_you_mean("trace", VERBS)


def test_case_is_ignored_on_the_way_in_and_preserved_on_the_way_out() -> None:
    assert did_you_mean("VERIFY", VERBS) == ("verify",)


def test_a_near_miss_on_a_property_slug_is_suggested() -> None:
    """§5.4 row 2: `--strict=<slug>` ranges over `gebra.verify.PROPERTY_SLUGS`."""
    assert did_you_mean("determinism-reply", PROPERTY_SLUGS) == ("determinism-replay",)


def test_a_near_miss_on_a_format_value_is_suggested() -> None:
    """§5.4 row 3: a verb's own value set (CLI-SPEC §4.1's `{human,json,sarif}`)."""
    assert did_you_mean("sarrif", REPORT_FORMATS) == ("sarif",)


def test_nothing_close_enough_suggests_nothing() -> None:
    """A suggestion that fires on anything is noise; silence is a legitimate answer."""
    assert did_you_mean("zzzzzzzz", VERBS) == ()


def test_an_empty_vocabulary_suggests_nothing() -> None:
    assert did_you_mean("verify", ()) == ()


def test_at_most_three_candidates() -> None:
    """§5.4's own cap."""
    crowded = tuple(f"verify{index}" for index in range(10))
    assert len(did_you_mean("verify", crowded)) == MAX_SUGGESTIONS == 3


def test_the_threshold_is_a_similarity_ratio() -> None:
    assert 0.0 < SIMILARITY_THRESHOLD <= 1.0
    assert did_you_mean("v", VERBS, threshold=0.01)
    assert did_you_mean("v", VERBS, threshold=0.99) == ()


def test_candidates_come_back_closest_first() -> None:
    assert did_you_mean("displa", ("display", "diff"))[0] == "display"


@pytest.mark.parametrize(
    ("suggestions", "expected"),
    [
        ((), ""),
        (("verify",), "Did you mean verify?"),
        (("verify", "history"), "Did you mean verify or history?"),
        (("a", "b", "c"), "Did you mean a, b or c?"),
    ],
)
def test_the_sentence_is_a_question_never_an_instruction(
    suggestions: tuple[str, ...], expected: str
) -> None:
    """§5.4: display-only. A sentence that reads like an instruction invites being followed."""
    assert suggestion_sentence(suggestions) == expected


def test_suggestions_never_reach_a_machine_surface() -> None:
    """§5.4: "never appears in a machine format" — checked as an import fact, not a promise."""
    from gebra.report import native, sarif

    for module in (native, sarif):
        source = (module.__file__ or "").rsplit("/", 1)[-1]
        assert source
        assert "suggestions" not in module.__dict__
        assert "did_you_mean" not in module.__dict__
