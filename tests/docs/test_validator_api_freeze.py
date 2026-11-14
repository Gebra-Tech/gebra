"""``docs/governance/VALIDATOR-API-FREEZE.md`` held to the surface it freezes (card VAL-12).

The freeze note names a set of exported symbols as "the frozen surface" and states three
obligations: the harness-consumer sign-off ("callable, structured, assertable"), the
post-freeze R-05-routed change policy, and the joint D-12 promotion trigger with IR-06. This
module machine-checks the parts of that record a test can pin without going stale the moment
another card's status legitimately changes:

* every backtick-quoted ``gebra.verify`` symbol §1 names is a real export today, so the note
  cannot silently drift from the surface it claims to freeze;
* the required prose commitments (harness-consumer wording, R-05 routing, the CLI-07
  deferral, the IR-06 joint-trigger statement) are present verbatim;
* no honest-claims banned phrase appears in the note.

What this module does **not** assert: IR-06's live board status. That is a point-in-time fact
the note states "as of this writing" and is expected to become stale the day IR-06 lands —
pinning it here would make a correct future edit look like a regression.

Nothing here executes a workflow node, calls a model, or opens a network connection (WA-07):
it reads one markdown file and inspects already-imported symbols.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import gebra.verify as verify_module

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
FREEZE_NOTE: Final = REPO_ROOT / "docs" / "governance" / "VALIDATOR-API-FREEZE.md"
BANNED_PHRASES_FILE: Final = REPO_ROOT / "tools" / "honest-claims-phrases.txt"

#: Symbols named in backticks in "## 1. What is frozen" that are real ``gebra.verify``
#: exports, as opposed to spec section numbers, model-family prose or file names.
_EXPECTED_EXPORTS: Final = {
    "PropertyReport",
    "Failure",
    "CoFailure",
    "Advisory",
    "to_data",
    "to_json",
    "to_display",
    "json_text",
    "models_equivalent",
    "ConditionId",
    "Severity",
    "ClaimClass",
    "PropertySlug",
    "emittable_condition",
    "is_emittable",
    "property_for_condition",
    "condition",
    "register_validator",
    "unregister_validator",
    "run_property",
    "validator_for",
    "is_registered",
    "is_implemented",
    "not_implemented",
    "emit_failure",
    "emit_co_failure",
    "emit_advisory",
    "check_graph_well_formed",
    "check_termination_witness",
    "check_dataflow_completeness",
    "check_effect_safety",
    "check_determinism_replay",
    "strict_promotions",
    "verify",
    "RunPolicy",
    "SubjectRef",
    "anchor_location",
    "RunReport",
    "Tool",
    "Subject",
    "StrictPolicy",
    "Promotion",
    "SeverityCounts",
    "ToolError",
    "GateOutcome",
    "PropertyOutcome",
}


def _text() -> str:
    return FREEZE_NOTE.read_text(encoding="utf-8")


def test_freeze_note_exists() -> None:
    assert FREEZE_NOTE.is_file(), f"{FREEZE_NOTE} is missing"


def test_every_named_export_is_real() -> None:
    """§1's frozen surface cannot silently drift from what ``gebra.verify`` actually exports."""
    exported = set(verify_module.__all__)
    missing = _EXPECTED_EXPORTS - exported
    assert not missing, (
        f"VALIDATOR-API-FREEZE.md §1 names symbols gebra.verify no longer exports: {missing}"
    )


def test_named_exports_are_all_mentioned_in_backticks() -> None:
    """The reverse direction: every name this test tracks is actually quoted in the note."""
    text = _text()
    # Backtick-quoted bare names, plus the leading identifier of a backtick-quoted call
    # like `` `verify(ir, policy=None)` ``.
    mentioned = set(re.findall(r"`(\w[\w.]*)`", text))
    mentioned |= set(re.findall(r"`(\w[\w.]*)\(", text))
    missing = _EXPECTED_EXPORTS - mentioned
    assert not missing, f"expected in VALIDATOR-API-FREEZE.md but not found: {missing}"


def test_harness_consumer_sign_off_recorded() -> None:
    text = _text()
    assert '"callable, structured, assertable."' in text
    assert "TE-04" in text


def test_post_freeze_change_policy_states_r05_routing() -> None:
    text = _text()
    assert "R-05-routed decision" in text
    assert "R-05 vault sign-off" in text


def test_cli_render_sign_off_is_deferred_not_claimed() -> None:
    text = _text()
    assert "CLI-07" in text
    assert "deliberately deferred" in text
    # The note must not itself assert the CLI-07 sign-off ("renders cleanly") as met.
    assert "renders cleanly" not in text.split("## 3.")[1].split("## 4.")[0] or (
        "sign-off is" in text.split("## 3.")[1].split("## 4.")[0]
    )


def test_d12_promotion_eligibility_is_joint_and_honest_about_ir_06() -> None:
    """Box 3 ("triggered (with IR-06)") — recorded as VAL's half only, never as fully armed."""
    text = _text()
    assert "IR-06" in text
    assert "CLI-08" in text
    assert "VAL-12's half only" in text
    assert "not yet fully eligible" in text


def test_status_frozen_and_dated() -> None:
    text = _text()
    assert "**Status: FROZEN**" in text


def test_no_banned_phrase() -> None:
    phrases = [
        line.strip()
        for line in BANNED_PHRASES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    text = _text().lower()
    hits = [phrase for phrase in phrases if phrase.lower() in text]
    assert not hits, f"banned phrase(s) found in VALIDATOR-API-FREEZE.md: {hits}"


#: The names DEC-35's amendment entry (VAL-16) adds to the frozen surface: the counts and
#: scope views, each derived from the registry table (DEC-35 §3.5 (c)), and the charter's
#: copy as stated constants — the words of §0.6 item 1 and the reason each status states.
_DEC_35_ADDITIONS: Final = {
    "SHIPPED_SCOPES",
    "DEFERRED_READING",
    "MARKER_REASONS",
    "NO_VERDICT",
    "deferred_slugs",
    "shipped_slugs",
    "RegistryCounts",
    "registry_counts",
}


def _amendment(card: str) -> str:
    """The text of one "Amendments landed under this policy" entry, by its card id."""
    section = _text().split("**Amendments landed under this policy.**")[1].split("## 5.")[0]
    (entry,) = [item for item in section.split("\n- ") if item.startswith(f"**{card} ")]
    return entry


def test_the_charter_amendment_is_recorded_with_its_r05_route() -> None:
    """VAL-16's entry: DEC-35 as the R-05 decision, and every surface change it names.

    §4 makes a property's move off `DeferredToPhase1`, a run-level rule and a new field
    R-05-routed; the charter is that decision for the scope token, the registration and
    dispatch rules and the derived counts, and the entry says what did *not* move as plainly
    as what did.
    """
    entry = _amendment("VAL-16")
    assert "DEC-35" in entry
    for change in ("`PropertyScope`", "`catalog`", "`register_validator`", "`verify()`"):
        assert change in entry, change
    mentioned = set(re.findall(r"`(\w+)`", entry))
    assert _DEC_35_ADDITIONS <= mentioned
    assert _DEC_35_ADDITIONS <= set(verify_module.__all__)
    assert "`NotImplementedStatus` keeps exactly the two" in entry
    assert "`report_format` stays `1.3`" in entry


def test_the_dec_42_amendment_is_recorded_with_its_r05_route() -> None:
    """VAL-29's entry: DEC-42 as the R-05 decision, the values it moved, and no shape moved.

    DEC-42 moves the value of a frozen constant, eight registry rows' pointers and the
    docstrings' definition and reading of the deferred scope — no name, signature or shape — so
    the entry quotes the constant's value as it now stands and says what did not move as plainly
    as what did.
    """
    entry = " ".join(_amendment("VAL-29").split())  # wrapped lines read as one
    assert "DEC-42" in entry
    for moved in ("`DEFERRED_READING`", "`spec_ref`", "`deferred-to-phase-1`"):
        assert moved in entry, moved
    assert f'"{verify_module.DEFERRED_READING}"' in entry
    assert "no name, signature or shape" in entry
    assert "`report_format` stays `1.3`" in entry
    assert "no property moved off `DeferredToPhase1`" in entry


#: The names CLI-12's entry adds to the frozen surface: DEC-35 §3.8's member and record model,
#: the record's closed code vocabulary, and the two calls that carry the notes in.
_CLI_12_ADDITIONS: Final = {
    "ExtractionNote",
    "ExtractionNoteCode",
    "extraction_notes_of",
    "with_extraction_notes",
}


def test_the_extraction_notes_amendment_is_recorded_with_its_r05_route() -> None:
    """CLI-12's entry: DEC-35 as the R-05 decision for a field added on a frozen run-level
    model, every name it adds, and the frozen calls it leaves alone, stated as plainly."""
    entry = " ".join(_amendment("CLI-12").split())
    assert "DEC-35" in entry and "DEC-36" in entry
    assert "`RunReport.extraction_notes: tuple[ExtractionNote, ...] = ()`" in entry
    mentioned = set(re.findall(r"`(\w+)`", entry))
    assert _CLI_12_ADDITIONS <= mentioned
    assert _CLI_12_ADDITIONS <= set(verify_module.__all__)
    for unchanged in ("`verify(ir, policy=None)`", "`RunPolicy`", "`SubjectRef`"):
        assert unchanged in entry, unchanged
    assert "are unchanged" in entry
    assert "`report_format` stays `1.4`" in entry
    assert "no property moved off `DeferredToPhase1`" in entry
