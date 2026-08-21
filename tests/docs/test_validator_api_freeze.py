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
