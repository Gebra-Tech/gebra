"""Subject resolution — CLI-SPEC §2's grammars, order, and §2.6 stage mapping (CLI-04).

The detection-rule ordering is normative and the card's conformance list (§7) names it: the
three grammars are tested one by one and then against each other, on targets constructed to
sit in the overlaps §2.2's two ordering sentences call out. Everything here is pure
resolution — no CLI shell, no rendering — so a failure names the seam directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gebra.cli.resolve import (
    Refusal,
    detect_mode,
    resolve_ir_document,
    resolve_snapshot,
    store_for,
)
from gebra.ir import write_ir
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore
from tests.cli.conftest import PASSING_FIXTURE, fixture_ir

# ── §2.2: the three grammars ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("target", ["1.4.2.0", "0.0.0.0", "10.20.30.40"])
def test_a_vsfe_label_names_snapshot_mode(target: str) -> None:
    assert detect_mode(target) == "snapshot"


@pytest.mark.parametrize(
    "target",
    [
        "workflow.ir.yaml",
        "build/travel-booking.ir.yaml",
        "w.yml",
        "w.json",
        "UPPER.YAML",  # the suffix rule lowercases, as read_ir's own rule does
    ],
)
def test_an_ir_suffix_names_ir_document_mode(target: str) -> None:
    assert detect_mode(target) == "ir-document"


@pytest.mark.parametrize(
    "target",
    ["travel_booking:build_graph", "pkg.sub.module:graph", "_m:_a"],
)
def test_an_import_reference_names_extracted_mode(target: str) -> None:
    assert detect_mode(target) == "extracted"


# ── §2.2: the normative ordering, tested directly (CLI-SPEC §7's CLI-04 obligation) ──────


def test_rule_1_precedes_rule_2_a_label_is_never_a_file() -> None:
    """``1.4.2.0`` has no recognized suffix, so the ordering is what keeps it a label."""
    assert detect_mode("1.4.2.0") == "snapshot"


def test_rule_2_precedes_rule_3_a_windows_path_with_a_colon_is_a_document() -> None:
    """§2.2's own example: a Windows path can carry a colon; the suffix wins first."""
    assert detect_mode("C:\\workflows\\agent.ir.yaml") == "ir-document"


def test_a_colon_bearing_name_with_an_ir_suffix_is_a_document_not_a_reference() -> None:
    assert detect_mode("odd:name.yaml") == "ir-document"


# ── §2.2 rule 4: no grammar, with the closest shape named ────────────────────────────────


def test_a_three_component_version_is_refused_naming_the_label_shape() -> None:
    with pytest.raises(Refusal) as caught:
        detect_mode("1.4.2")
    assert caught.value.stage == "input"
    assert "V.S.F.E" in caught.value.detail


def test_a_bad_reference_is_refused_naming_the_reference_shape() -> None:
    with pytest.raises(Refusal) as caught:
        detect_mode("module:attr:extra")
    assert caught.value.stage == "input"
    assert "import reference" in caught.value.detail


def test_an_unrecognized_suffix_is_refused_naming_the_suffix_rule() -> None:
    with pytest.raises(Refusal) as caught:
        detect_mode("workflow.toml")
    assert caught.value.stage == "input"
    assert ".yaml" in caught.value.detail
    assert "sniffs" in caught.value.detail


def test_a_shapeless_target_is_refused_naming_all_three_shapes() -> None:
    with pytest.raises(Refusal) as caught:
        detect_mode("just some words")
    detail = caught.value.detail
    assert "V.S.F.E" in detail
    assert "import reference" in detail
    assert ".yaml" in detail or "IR document" in detail


# ── §2.6: the ir-document stage mapping ──────────────────────────────────────────────────


def test_a_missing_document_is_an_input_stage_refusal(tmp_path: Path) -> None:
    with pytest.raises(Refusal) as caught:
        resolve_ir_document(str(tmp_path / "absent.ir.yaml"))
    assert caught.value.stage == "input"


def test_an_unparseable_document_is_an_input_stage_refusal(tmp_path: Path) -> None:
    path = tmp_path / "broken.ir.yaml"
    path.write_text("{ this is [ not yaml", encoding="utf-8")
    with pytest.raises(Refusal) as caught:
        resolve_ir_document(str(path))
    assert caught.value.stage == "input"


def test_a_non_utf8_document_is_an_input_stage_refusal_not_a_crash(tmp_path: Path) -> None:
    """§2.6 files "unreadable" under ``input`` — a binary file included, which raises the
    one ``ValueError`` (``UnicodeDecodeError``) that is neither a parse nor a model fault."""
    path = tmp_path / "binary.ir.yaml"
    path.write_bytes(b"\xff\xfe\x00 not text \x9c")
    with pytest.raises(Refusal) as caught:
        resolve_ir_document(str(path))
    assert caught.value.stage == "input"
    assert "UTF-8" in caught.value.detail


def test_a_parseable_non_ir_document_is_an_ir_validation_refusal(tmp_path: Path) -> None:
    """§2.6: "an IR document did not validate against ir_version 1.0" is its own stage."""
    path = tmp_path / "not-ir.ir.yaml"
    path.write_text("ir_version: '1.0'\nnodes: []\n", encoding="utf-8")
    with pytest.raises(Refusal) as caught:
        resolve_ir_document(str(path))
    assert caught.value.stage == "ir-validation"


def test_a_good_document_resolves_with_the_path_as_given(tmp_path: Path) -> None:
    path = tmp_path / "pass.ir.yaml"
    write_ir(fixture_ir(PASSING_FIXTURE), path)
    resolved = resolve_ir_document(str(path))
    assert resolved.reference.input_mode == "ir-document"
    assert resolved.reference.source == str(path)
    assert resolved.reference.version is None
    assert resolved.warnings == ()


# ── §2.5: the store, and §2.6's snapshot rows ────────────────────────────────────────────


def test_store_for_defaults_to_the_working_directorys_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert store_for(None).path == tmp_path / ".gebra"


def test_store_for_names_the_store_directory_itself(tmp_path: Path) -> None:
    """§2.5: ``--store DIR`` is the store directory, not a project root to append to."""
    assert store_for(str(tmp_path / "custom-store")).path == tmp_path / "custom-store"


def test_a_malformed_label_is_an_input_stage_refusal(tmp_path: Path) -> None:
    with pytest.raises(Refusal) as caught:
        resolve_snapshot("not-a-label", str(tmp_path / ".gebra"))
    assert caught.value.stage == "input"
    assert "V.S.F.E" in caught.value.detail


def test_an_empty_store_names_its_emptiness(tmp_path: Path) -> None:
    with pytest.raises(Refusal) as caught:
        resolve_snapshot("1.0.0.0", str(tmp_path / ".gebra"))
    assert caught.value.stage == "input"
    assert "no versions at all" in caught.value.detail


def test_an_unheld_label_suggests_the_labels_the_store_holds(tmp_path: Path) -> None:
    """§5.4's table: a ``--snapshot`` label suggests from the store's own history."""
    store = _store_holding_v1(tmp_path)
    with pytest.raises(Refusal) as caught:
        resolve_snapshot("1.0.0.1", str(store.path))
    assert caught.value.stage == "input"
    assert "Did you mean 1.0.0.0?" in caught.value.detail


def test_a_held_label_resolves_to_the_stored_document(tmp_path: Path) -> None:
    store = _store_holding_v1(tmp_path)
    resolved = resolve_snapshot("1.0.0.0", str(store.path))
    assert resolved.reference.input_mode == "snapshot"
    assert resolved.reference.version == "1.0.0.0"
    assert resolved.reference.source == "tests:cli-suite"
    assert resolved.ir == fixture_ir(PASSING_FIXTURE)


def test_a_damaged_snapshot_is_an_input_stage_refusal(tmp_path: Path) -> None:
    """§2.6: a snapshot failing its digest check never becomes a verdict."""
    store = _store_holding_v1(tmp_path)
    path = store.snapshot_path("1.0.0.0")
    path.write_text(
        path.read_text(encoding="utf-8").replace("entry:", "entry_:", 1), encoding="utf-8"
    )
    with pytest.raises(Refusal) as caught:
        resolve_snapshot("1.0.0.0", str(store.path))
    assert caught.value.stage == "input"


def _store_holding_v1(tmp_path: Path) -> SnapshotStore:
    store = SnapshotStore(tmp_path / ".gebra")
    store.write(
        Snapshot.of(
            fixture_ir(PASSING_FIXTURE),
            version="1.0.0.0",
            extracted_from=ExtractedFrom(
                source="tests:cli-suite",
                extractor_version="0.0.1.dev0",
                extracted_at="2026-08-21T00:00:00Z",
            ),
        )
    )
    return store
