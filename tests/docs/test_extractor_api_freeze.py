"""``docs/governance/EXTRACTOR-API-FREEZE.md`` held to the surface it freezes (card EX-15).

The freeze note names three export sets as "the frozen surface" (top-level ``gebra``,
``gebra.extraction``, ``gebra.annotations``) and a ten-row 1.x backlog table, each row
citing a spec anchor and an explicit "needs future DEC" status. This module machine-checks
the parts of that record a test can pin without going stale the moment another card's
status legitimately changes:

* every backtick-quoted symbol §1 names for each of the three surfaces is a real export
  today, in both directions — the note cannot silently drift from what the package
  actually exports, and it cannot omit one either;
* every §2 backlog row names a spec anchor and carries the literal "needs future DEC"
  status — the acceptance criterion this card's second box states;
* the required prose commitments (the D-08 week-12 milestone citation, the PD-023 D6 /
  PD-043 D4 provenance of the EX-05/EX-16 rows, the post-freeze DEC-routing policy, the
  G5-is-not-signed disclaimer) are present verbatim;
* no honest-claims banned phrase appears in the note.

What this module does **not** assert: the live board status of TE-11 or G5 itself — those
are point-in-time facts the note states "as of this writing" and are expected to become
stale the day that card lands; pinning them here would make a correct future edit look
like a regression.

Nothing here executes a workflow node, calls a model, or opens a network connection
(WA-07): it reads one markdown file and inspects already-imported symbols. Importing
``gebra.extraction`` does import the langgraph/langchain-core substrate to dispatch on its
classes (this package's own documented posture, `gebra/__init__.py`); it does not invoke
anything in it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import gebra
import gebra.annotations as annotations_module
import gebra.extraction as extraction_module

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
FREEZE_NOTE: Final = REPO_ROOT / "docs" / "governance" / "EXTRACTOR-API-FREEZE.md"
BANNED_PHRASES_FILE: Final = REPO_ROOT / "tools" / "honest-claims-phrases.txt"

#: §1.1 — the ten names `gebra/__init__.py` resolves lazily.
_EXPECTED_TOP_LEVEL: Final = {
    "extract",
    "ExtractionError",
    "contract",
    "GebraContractError",
    "pure",
    "effect",
    "idempotent",
    "deterministic",
    "variant",
    "compensation",
}

#: §1.2 — every `gebra.extraction.__all__` export, transcribed.
_EXPECTED_EXTRACTION: Final = {
    "ADMITTED_BINDING_CLASSES",
    "ANNOTATION_SLOTS",
    "AnnotationSlot",
    "CarrierRule",
    "CompatClass",
    "CompiledSurfaces",
    "CrossCheck",
    "Declarations",
    "Dispatch",
    "ExtractedFrom",
    "ExtractionEnvelope",
    "ExtractionError",
    "ExtractionErrorReason",
    "ExtractionModel",
    "ExtractionWarning",
    "ExtractionWarningCode",
    "Extractor",
    "FINDING_CODES",
    "FRAGMENT_CLASSES",
    "FoldedDefault",
    "FragmentKind",
    "FragmentReading",
    "GebraVersionWarning",
    "HEURISTIC_GRADE_CODES",
    "NodeContracts",
    "NodeDigests",
    "ObjectFamily",
    "PromptGap",
    "STOCK_BINDING_NAMES",
    "STOCK_BINDING_SUBCLASSES",
    "SlotGrade",
    "StateReading",
    "SubstrateVersions",
    "UNREPRESENTABLE",
    "UNREPRESENTABLE_REDUCER",
    "UNREPRESENTABLE_TYPE",
    "VersionCheck",
    "WARNING_RULES",
    "WRAPPER_MEMBERS",
    "WarningRule",
    "check_version_once",
    "classify",
    "classify_substrate",
    "coerce",
    "config_form",
    "contract_warnings",
    "digests_for",
    "extract",
    "extract_builder",
    "extract_compiled",
    "extract_lcel_fragment",
    "extractor_for",
    "is_binding",
    "kind_of",
    "load_sidecar",
    "out_of_range_warning",
    "prompt_form",
    "read_installed_versions",
    "read_state",
    "register_extractor",
    "resolve_node",
    "sidecar_warnings",
    "slot_grade",
    "state_schema_of",
    "stitch_fragment",
    "to_data",
    "to_json",
    "type_identity",
    "unknown_node_warnings",
    "unregister_extractor",
    "walk",
    "warning_rule",
}

#: §1.3 — every `gebra.annotations.__all__` export, transcribed.
_EXPECTED_ANNOTATIONS: Final = {
    "ANNOTATION_SLOTS",
    "AnnotationSlot",
    "Blocker",
    "CONTRACT_ATTRIBUTE",
    "ContractErrorReason",
    "Contribution",
    "DEFAULT_EFFECT",
    "DefaultRule",
    "EFFECT_TAGS",
    "GebraContractError",
    "IDENTIFIER_SLOTS",
    "INFERENCE_SLOTS",
    "Inference",
    "InferenceFinding",
    "InferredKey",
    "IssueKind",
    "NEVER_INFERRED",
    "NodeContract",
    "NodeSource",
    "PRECEDENCE",
    "Pattern",
    "Resolution",
    "ResolutionIssue",
    "ResolutionRule",
    "SIDECAR_FILENAME",
    "SIDECAR_SCHEMA",
    "SLOT_KEYWORDS",
    "SidecarIssue",
    "SidecarReading",
    "SidecarRule",
    "SidecarSource",
    "SlotGrade",
    "SourceCache",
    "SourceRule",
    "StateSchema",
    "Surface",
    "TIER_SLOTS",
    "carriable",
    "compensation",
    "contract",
    "deterministic",
    "discover_sidecar",
    "effect",
    "idempotent",
    "infer",
    "infer_node",
    "pure",
    "read_contract",
    "read_node_source",
    "read_sidecar",
    "repository_root",
    "resolve",
    "slot_bytes",
    "slot_data",
    "variant",
}

#: §2's ten backlog item names, in table order.
_BACKLOG_ITEMS: Final = (
    "projection",
    "Subgraph child-topology expansion",
    "join_key",
    "codomain",
    "kind: join",
    "Managed-value marker slot",
    "Checkpointer *type*",
    "Tool projection for `BaseTool`-object bindings",
    "Non-mirrored `StateNodeSpec` builder fields",
    "Non-mirrored compiled-level provenance facts",
)


def _text() -> str:
    return FREEZE_NOTE.read_text(encoding="utf-8")


def _backtick_names(text: str) -> set[str]:
    mentioned = set(re.findall(r"`(\w[\w.]*)`", text))
    mentioned |= set(re.findall(r"`(\w[\w.]*)\(", text))
    return mentioned


def test_freeze_note_exists() -> None:
    assert FREEZE_NOTE.is_file(), f"{FREEZE_NOTE} is missing"


def test_expected_top_level_matches_the_live_lazy_exports() -> None:
    assert _EXPECTED_TOP_LEVEL == set(gebra.__all__)


def test_expected_extraction_exports_match_the_live_all_list() -> None:
    assert _EXPECTED_EXTRACTION == set(extraction_module.__all__)


def test_expected_annotations_exports_match_the_live_all_list() -> None:
    assert _EXPECTED_ANNOTATIONS == set(annotations_module.__all__)


def test_every_named_export_is_real() -> None:
    """§1 cannot silently drift from what the three surfaces actually export."""
    live = set(gebra.__all__) | set(extraction_module.__all__) | set(annotations_module.__all__)
    expected = _EXPECTED_TOP_LEVEL | _EXPECTED_EXTRACTION | _EXPECTED_ANNOTATIONS
    missing = expected - live
    assert not missing, f"EXTRACTOR-API-FREEZE.md §1 names symbols no longer exported: {missing}"


def test_named_exports_are_all_mentioned_in_backticks() -> None:
    """The reverse direction: every tracked name is actually quoted in the note."""
    mentioned = _backtick_names(_text())
    expected = _EXPECTED_TOP_LEVEL | _EXPECTED_EXTRACTION | _EXPECTED_ANNOTATIONS
    missing = expected - mentioned
    assert not missing, f"expected in EXTRACTOR-API-FREEZE.md but not found: {missing}"


def test_backlog_table_has_exactly_the_ten_named_items() -> None:
    text = _text()
    for item in _BACKLOG_ITEMS:
        assert item in text, f"backlog item missing from EXTRACTOR-API-FREEZE.md: {item!r}"
    # The table itself: ten data rows, each starting "| N |" for N in 1..10.
    for row_number in range(1, 11):
        assert re.search(rf"^\|\s*{row_number}\s*\|", text, flags=re.MULTILINE), (
            f"backlog table missing row {row_number}"
        )


def test_every_backlog_row_needs_a_future_dec() -> None:
    """Acceptance box 2: each deferred item cites its spec anchor and 'needs future DEC'."""
    text = _text()
    hits = len(re.findall(r"needs future DEC", text))
    # Ten table rows plus the "row 8" cross-reference in the closing §2 paragraph.
    assert hits >= 10, f"expected at least 10 'needs future DEC' statements, found {hits}"


def test_backlog_rows_cite_their_spec_anchors() -> None:
    text = _text()
    for anchor in (
        "INTROSPECTION-SPEC §7.3 item 2",
        "INTROSPECTION-SPEC §4.1",
        "INTROSPECTION-SPEC §7.3 item 5",
        "INTROSPECTION-SPEC §7.3 item 3",
        "INTROSPECTION-SPEC §3",
        "IR-SPEC §3.7",
        "INTROSPECTION-SPEC §7.4 (c)/(d)",
    ):
        assert anchor in text, f"expected spec anchor not found: {anchor!r}"


def test_ex05_and_ex16_provenance_recorded() -> None:
    text = _text()
    assert "PD-023 D6" in text
    assert "PD-043 D4" in text
    assert "DEC-19" in text


def test_d08_freeze_milestone_cited() -> None:
    """The record grounds the freeze in brief D-08's own milestone — cited by name, not by
    quoting the brief's internal schedule (reworded at the PD-050 publication pass)."""
    text = _text()
    assert "Brief D-08" in text
    assert "API-freeze milestone" in text
    assert "API freeze" in text


def test_post_freeze_change_policy_states_dec_routing() -> None:
    text = _text()
    assert "vault decision" in text
    assert "ir_version` bump" in text or "`ir_version` bump" in text


def test_g5_is_not_claimed_signed() -> None:
    text = _text()
    assert "does not claim" in text
    assert "G5" in text
    assert "TE-11" in text


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
    assert not hits, f"banned phrase(s) found in EXTRACTOR-API-FREEZE.md: {hits}"
