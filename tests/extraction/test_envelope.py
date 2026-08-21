"""The provenance envelope: what rides around the core IR, and what can never reach the digest.

Normative authority: IR-SPEC §4.1 (the core-IR/envelope split and the envelope field names),
§6.4 (the digest's inclusion/exclusion table), INTROSPECTION-SPEC §8 and ANNOTATION-API-SPEC
§4 (warnings ride the envelope, outside hash scope), ANNOTATION-API-SPEC §2 (the recorded
sidecar path) and §5 (the grade lookup a validator runs against the envelope).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import gebra
from gebra.extraction import (
    ExtractedFrom,
    ExtractionEnvelope,
    ExtractionModel,
    ExtractionWarning,
    ExtractionWarningCode,
    ObjectFamily,
    SlotGrade,
    to_data,
    to_json,
)
from gebra.ir import IRModel, WorkflowIR, graph_version

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "ir" / "golden"


def golden_ir() -> WorkflowIR:
    """Golden vector 001 (IR-SPEC §6.5), loaded from its committed canonical bytes."""
    return WorkflowIR.model_validate_json((GOLDEN_DIR / "vector-001.canonical.json").read_bytes())


def golden_digest() -> str:
    return (GOLDEN_DIR / "vector-001.digest").read_text(encoding="ascii").strip()


def sample_warnings() -> tuple[ExtractionWarning, ...]:
    """One warning per scope — node-and-slot, node-only, graph-wide."""
    return (
        ExtractionWarning(
            code=ExtractionWarningCode.CONTRACT_INFERRED,
            message="writes inferred from a literal return",
            node="plan",
            slots=("output",),
            detail={"pattern": "literal-return", "keys": ("task",)},
        ),
        ExtractionWarning(
            code=ExtractionWarningCode.CONTRACT_DEFAULTED,
            message="no write evidence: D-011 default applied",
            node="act",
            slots=("effect",),
        ),
        ExtractionWarning(
            code=ExtractionWarningCode.COMPILED_ONLY_EXTRACTION,
            message="extracted compiled-only: no builder backreference",
            detail={"object_type": "langgraph:Pregel"},
        ),
    )


def envelope(**overrides: object) -> ExtractionEnvelope:
    fields: dict[str, object] = {
        "ir": golden_ir(),
        "extracted_from": ExtractedFrom(source="langgraph:StateGraph", family=ObjectFamily.BUILDER),
        "warnings": sample_warnings(),
    }
    fields.update(overrides)
    return ExtractionEnvelope(**fields)  # type: ignore[arg-type]


# ── The §4.1 split ───────────────────────────────────────────────────────────────────────


def test_the_envelope_wraps_the_core_ir_rather_than_extending_it() -> None:
    """§4.1: the envelope is "metadata wrapped *around* the core IR — outside the model".

    Held to structurally, not by convention: the envelope is not an IR model, so no envelope
    member can arrive inside a ``WorkflowIR`` by inheritance, and the IR it carries is the
    same object a validator would be handed.
    """
    wrapped = envelope()

    assert isinstance(wrapped.ir, WorkflowIR)
    assert not issubclass(ExtractionEnvelope, IRModel)
    assert issubclass(ExtractionEnvelope, ExtractionModel)


def test_the_snapshot_envelopes_own_fields_are_not_here() -> None:
    """§4.1 gives ``version`` (V.S.F.E) to brief D-11: it is *derived from diffs* of digested
    content, which one extraction cannot compute. ``extra="forbid"`` is what keeps a caller
    from filling it in here anyway."""
    with pytest.raises(ValidationError):
        envelope(version="1.2.0.3")


def test_warnings_never_perturb_the_graph_version() -> None:
    """§6.4 EXCLUDE, checked against golden vector 001 rather than against ourselves.

    The digest of an envelope carrying three warnings is the frozen §6.5 digest of the IR
    alone — the same string a caller gets from ``gebra.ir.graph_version(ir)``. This is the
    property the whole split exists for: a prompt edit moves ``graph_version`` and a warning
    never does, so a digest that moved is always a change in the workflow.
    """
    warned = envelope()
    silent = envelope(warnings=())

    assert warned.graph_version() == golden_digest()
    assert silent.graph_version() == golden_digest()
    assert warned.graph_version() == graph_version(warned.ir)


def test_the_extraction_provenance_does_not_move_the_digest_either() -> None:
    """Same rule, one row up: ``extracted_from`` is provenance — "how/when it was made"."""
    from_builder = envelope()
    from_compiled = envelope(
        extracted_from=ExtractedFrom(
            source="langgraph:CompiledStateGraph",
            family=ObjectFamily.COMPILED,
            sidecar="/repo/gebra.toml",
        )
    )

    assert from_builder.graph_version() == from_compiled.graph_version() == golden_digest()


# ── What the provenance records ──────────────────────────────────────────────────────────


def test_provenance_records_the_source_the_family_and_the_extractor() -> None:
    """§4.1 ``extracted_from``: "source reference, extractor version"."""
    provenance = envelope().extracted_from

    assert provenance.source == "langgraph:StateGraph"
    assert provenance.family is ObjectFamily.BUILDER
    assert provenance.extractor_version == gebra.__version__
    assert provenance.sidecar is None


def test_the_sidecar_path_is_recorded_or_recorded_absent() -> None:
    """ANNOTATION §2: the envelope "MUST record the absolute sidecar path used (or its
    absence) so digest divergence is diagnosable" — sidecar-filled annotations sit *inside*
    the hash scope while discovery walks up from the working directory."""
    used = ExtractedFrom(
        source="langgraph:StateGraph",
        family=ObjectFamily.BUILDER,
        sidecar="/repo/services/gebra.toml",
    )

    assert used.sidecar == "/repo/services/gebra.toml"
    assert to_data(used)["sidecar"] == "/repo/services/gebra.toml"
    assert "sidecar" not in to_data(envelope().extracted_from)


# ── Warnings are enumerable off the envelope, and answer the §5 lookup ───────────────────


def test_warnings_are_enumerable_and_keep_their_order() -> None:
    """§8: warnings "are never silently droppable" — so they are carried in the return value,
    where a logging filter cannot drop them, in the order they were emitted."""
    wrapped = envelope()

    assert len(wrapped.warnings) == 3
    assert [warning.code.value for warning in wrapped.warnings] == [
        "contract-inferred",
        "contract-defaulted",
        "compiled-only-extraction",
    ]
    assert [warning.node for warning in wrapped.warnings] == ["plan", "act", None]


def test_warnings_can_be_read_by_node_and_by_code() -> None:
    wrapped = envelope()

    assert [warning.code.value for warning in wrapped.warnings_for("plan")] == ["contract-inferred"]
    assert wrapped.warnings_for("report") == ()
    assert len(wrapped.warnings_of(ExtractionWarningCode.COMPILED_ONLY_EXTRACTION)) == 1


def test_the_envelope_answers_the_declared_versus_heuristic_lookup() -> None:
    """ANNOTATION §5: "a slot on node *n* is declared-grade **iff** no
    ``contract-inferred``/``contract-defaulted`` warning in the extraction envelope names the
    (node id, slot) pair". The lookup is normative for the P-01…P-13 validators, and this is
    where §5 says to run it — the serialized IR deliberately carries no per-slot provenance.
    """
    wrapped = envelope()

    assert wrapped.slot_grade("plan", "output") is SlotGrade.INFERRED
    assert wrapped.slot_grade("act", "effect") is SlotGrade.DEFAULTED
    assert wrapped.slot_grade("plan", "input") is SlotGrade.DECLARED
    assert wrapped.slot_grade("report", "input") is SlotGrade.DECLARED
    assert wrapped.slot_grade("plan", "output").heuristic


# ── Serialization profile ────────────────────────────────────────────────────────────────


def test_the_envelope_serializes_as_reportable_data() -> None:
    """The A6 PC-4 profile :func:`gebra.verify.base.to_data` uses: definition order, nulls
    dropped, tuples as arrays, enums as their values. Surface data — never hashed (§6.4)."""
    data = to_data(envelope())

    assert list(data) == ["ir", "extracted_from", "warnings"]
    assert data["extracted_from"]["family"] == "builder"
    assert data["warnings"][2] == {
        "code": "compiled-only-extraction",
        "message": "extracted compiled-only: no builder backreference",
        "slots": [],
        "detail": {"object_type": "langgraph:Pregel"},
    }
    assert json.loads(to_json(envelope())) == data
    assert to_json(envelope(), indent=None).count("\n") == 0


def test_the_envelope_reloads_equal_to_itself() -> None:
    """Model equality, field by field — the same comparison SOW §2 criterion 6 makes of IR."""
    original = envelope()

    reloaded = ExtractionEnvelope.model_validate_json(to_json(original))

    assert reloaded == original
    assert reloaded.graph_version() == original.graph_version()


def test_the_envelope_is_frozen_and_never_built_unvalidated() -> None:
    wrapped = envelope()

    with pytest.raises(ValidationError):
        wrapped.warnings = ()
    with pytest.raises(NotImplementedError, match="model_construct"):
        ExtractionEnvelope.model_construct(ir=golden_ir())
