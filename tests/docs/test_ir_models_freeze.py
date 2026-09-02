"""``docs/governance/IR-MODELS-FREEZE.md`` held to the surface it freezes (card IR-06).

The freeze note names a set of exported symbols as "the frozen surface" and states four
obligations: the validator-consumer sign-off ("the IR gives validators what they need"),
the snapshot-consumer sign-off ("serialization stable enough to snapshot and diff"), the
post-freeze DEC-09/`ir_version`-bump change policy, and the joint D-12 promotion trigger
with VAL-12. This module machine-checks the parts of that record a test can pin without
going stale the moment another card's status legitimately changes:

* every backtick-quoted ``gebra.ir`` symbol §1 names is a real export today, so the note
  cannot silently drift from the surface it claims to freeze;
* the required prose commitments (both sign-off wordings, the DEC-09 bump-rule statement,
  the joint IR-06/VAL-12 D-12 trigger, the G5-is-not-signed disclaimer) are present
  verbatim;
* no honest-claims banned phrase appears in the note.

What this module does **not** assert: the live board status of TE-11/EX-15 or G5 itself —
those are point-in-time facts the note states "as of this writing" and are expected to
become stale the day those cards land; pinning them here would make a correct future edit
look like a regression.

Nothing here executes a workflow node, calls a model, or opens a network connection (WA-07):
it reads one markdown file and inspects already-imported symbols.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import gebra.ir as ir_module
from tools.honest_claims_lint import load_phrases

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
FREEZE_NOTE: Final = REPO_ROOT / "docs" / "governance" / "IR-MODELS-FREEZE.md"
BANNED_PHRASES_FILE: Final = REPO_ROOT / "tools" / "honest-claims-phrases.txt"

#: Every real ``gebra.ir`` export, transcribed from ``gebra.ir.__all__`` — §1 must name
#: (in backticks) every one of these, and every one it names must still be exported.
_EXPECTED_EXPORTS: Final = {
    "IR_VERSION",
    "IR_VERSIONS",
    "IR_VERSION_DYNAMIC_EDGES",
    "I_JSON_MAX_INT",
    "I_JSON_MIN_INT",
    "JSON_SUFFIXES",
    "OPENINFERENCE_ID",
    "OPENINFERENCE_NAME",
    "OPENINFERENCE_PARENT_ID",
    "RESERVED_SEGMENTS",
    "SEGMENT_SEPARATOR",
    "SYNTHETIC_KINDS",
    "YAML_SUFFIXES",
    "Annotations",
    "CanonicalizationError",
    "CanonicalizationErrorReason",
    "Checkpointer",
    "Compensation",
    "ConditionalEdge",
    "DeterministicSpec",
    "DynamicEdge",
    "DynamicEdgeUnsupportedError",
    "Edge",
    "IRModel",
    "IRSerializationError",
    "IRSerializationErrorReason",
    "IdempotentKey",
    "Interrupts",
    "IrVersion",
    "Node",
    "NodeId",
    "NodeIdError",
    "NodeIdErrorReason",
    "NodeIdStr",
    "NormalEdge",
    "RecursionLimit",
    "RetryPolicy",
    "Runtime",
    "Segment",
    "SegmentKind",
    "SendEdge",
    "StateField",
    "Variant",
    "WorkflowIR",
    "canonical_annotations_bytes",
    "canonical_bytes",
    "canonical_foreign_bytes",
    "dump_json",
    "dump_yaml",
    "escape_segment",
    "graph_version",
    "is_valid_node_id",
    "join_node_id",
    "load_json",
    "load_yaml",
    "lowest_ir_version",
    "node_id_from_names",
    "openinference_attributes",
    "parse_node_id",
    "read_ir",
    "refuse_dynamic_edges",
    "render_digest",
    "split_node_id",
    "synthetic_segment",
    "unescape_segment",
    "validate_node_id",
    "verify_graph_version",
    "write_ir",
}


def _text() -> str:
    return FREEZE_NOTE.read_text(encoding="utf-8")


def test_freeze_note_exists() -> None:
    assert FREEZE_NOTE.is_file(), f"{FREEZE_NOTE} is missing"


def test_expected_exports_match_the_live_all_list() -> None:
    """Sanity: this test file's own transcription must equal ``gebra.ir.__all__`` today."""
    assert _EXPECTED_EXPORTS == set(ir_module.__all__)


def test_every_named_export_is_real() -> None:
    """§1's frozen surface cannot silently drift from what ``gebra.ir`` actually exports."""
    exported = set(ir_module.__all__)
    missing = _EXPECTED_EXPORTS - exported
    assert not missing, (
        f"IR-MODELS-FREEZE.md §1 names symbols gebra.ir no longer exports: {missing}"
    )


def test_named_exports_are_all_mentioned_in_backticks() -> None:
    """The reverse direction: every name this test tracks is actually quoted in the note."""
    text = _text()
    mentioned = set(re.findall(r"`(\w[\w.]*)`", text))
    mentioned |= set(re.findall(r"`(\w[\w.]*)\(", text))
    missing = _EXPECTED_EXPORTS - mentioned
    assert not missing, f"expected in IR-MODELS-FREEZE.md but not found: {missing}"


def test_freeze_scope_covers_ir_1_1_and_cites_dec_28() -> None:
    text = _text()
    assert "DEC-28" in text
    assert 'Literal["1.0", "1.1"]' in text
    assert "EX-03" in text


def test_spec_defect_pd_048_is_cited_not_hidden() -> None:
    text = _text()
    assert "PD-048" in text
    assert "retry_policy" in text


def test_validator_consumer_sign_off_recorded() -> None:
    text = _text()
    assert "The IR gives validators what they need" in text
    assert "VAL-11" in text
    assert "TE-04" in text


def test_snapshot_consumer_sign_off_recorded() -> None:
    text = _text()
    assert "Serialization is stable enough to snapshot and diff" in text
    assert "SD-01" in text
    assert "SD-04" in text


def test_post_freeze_change_policy_states_dec_09_bump_rule() -> None:
    text = _text()
    assert "ir_version` bump" in text
    assert "DEC-09" in text
    assert "REQUIRES a decision record" in text


def test_d12_promotion_eligibility_is_joint_with_val_12() -> None:
    """Box 3 ("F3 → D-12 promotion armed, jointly with VAL-12")."""
    text = _text()
    assert "VAL-12" in text
    assert "CLI-08" in text
    assert "CLI-02" in text
    assert "all three of CLI-08's named" in text


def test_g5_is_not_claimed_signed() -> None:
    """§5/§6 must not overclaim G5 itself — only the two-card freeze event F3."""
    text = _text()
    assert "does not itself sign gate" in text
    assert "G5 itself remains open" in text
    assert "TE-11" in text
    assert "EX-15" in text


def test_status_frozen_and_dated() -> None:
    text = _text()
    assert "**Status: FROZEN**" in text


def test_no_banned_phrase() -> None:
    # Through the lint's own loader, so the data file's format has one reader (TOOL-04).
    phrases = load_phrases(BANNED_PHRASES_FILE)
    text = _text().lower()
    hits = [phrase for phrase in phrases if phrase in text]
    assert not hits, f"banned phrase(s) found in IR-MODELS-FREEZE.md: {hits}"
