"""The warnings taxonomy: ratified spellings, structured records, the (node id, slot) lookup.

Normative authority: INTROSPECTION-SPEC §8 (the extraction rows) and ANNOTATION-API-SPEC §4
(the annotation-surface rows and the registry), with §5 for the grade lookup the pairs feed.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from gebra.extraction import (
    ANNOTATION_SLOTS,
    HEURISTIC_GRADE_CODES,
    WARNING_RULES,
    ExtractionWarning,
    ExtractionWarningCode,
    SlotGrade,
    slot_grade,
    to_data,
    warning_rule,
)

#: The taxonomy as the two frozen tables spell it — INTROSPECTION §8's seven rows, then
#: ANNOTATION §4's registry, whose ``contract-inferred``/``contract-defaulted`` rows are the
#: same two warnings under the names DEC-08 ratified. Written out here rather than derived
#: from the enum, so that this is a comparison against the specs and not against the code.
RATIFIED_SPELLINGS = {
    "contract-inferred",
    "contract-defaulted",
    "opaque-lambda",
    "builder-compiled-divergence",
    "compiled-only-extraction",
    "barrier-flattened",
    "unsupported-construct",
    "annotation-conflict",
    "annotation-unknown-node",
    "annotation-invalid",
}


def warning(**overrides: Any) -> ExtractionWarning:
    """A valid ``contract-inferred`` record, with per-test overrides applied on top."""
    fields: dict[str, Any] = {
        "code": ExtractionWarningCode.CONTRACT_INFERRED,
        "message": "reads inferred from literal state access",
        "node": "plan",
        "slots": ("input",),
    }
    fields.update(overrides)
    return ExtractionWarning(**fields)


# ── The vocabulary is the ratified one ───────────────────────────────────────────────────


def test_the_taxonomy_is_exactly_the_ten_ratified_codes() -> None:
    """§8 plus the §4 registry, no more and no fewer.

    Compared as a set against the spellings read off the two tables: a code added without a
    spec addendum lands on one side only, and so does one that was dropped.
    """
    assert {code.value for code in ExtractionWarningCode} == RATIFIED_SPELLINGS


def test_the_unratified_spelling_is_not_in_the_vocabulary() -> None:
    """§4: "INTROSPECTION-SPEC §8's ``inferred-contract`` and this table's
    ``contract-inferred`` name the same warning — DEC-08 ratified the ``contract-inferred``
    spelling". So the draft spelling is not a member and cannot reach a record."""
    assert "inferred-contract" not in {code.value for code in ExtractionWarningCode}

    with pytest.raises(ValidationError):
        ExtractionWarning.model_validate_json(
            json.dumps({"code": "inferred-contract", "message": "x", "node": "n"})
        )


def test_the_two_shared_rows_carry_the_dec_08_names() -> None:
    """The two names ANNOTATION §4 and INTROSPECTION §8 share, spelled once."""
    assert ExtractionWarningCode.CONTRACT_INFERRED.value == "contract-inferred"
    assert ExtractionWarningCode.CONTRACT_DEFAULTED.value == "contract-defaulted"


def test_every_code_has_a_registry_rule() -> None:
    """The rule table is what the model validates against; a code without one is unchecked."""
    assert set(WARNING_RULES) == set(ExtractionWarningCode)
    assert all(warning_rule(code).origin for code in ExtractionWarningCode)


def test_the_annotatable_slot_set_is_the_closed_nine() -> None:
    """ANNOTATION §1: "Exactly nine node-annotation slots … are settable through this spec's
    surfaces", in their IR spellings (``reads``→``input`` and so on)."""
    assert set(ANNOTATION_SLOTS) == {
        "input",
        "output",
        "effect",
        "pure",
        "idempotent",
        "deterministic",
        "args_schema",
        "variant",
        "compensation",
    }
    assert len(ANNOTATION_SLOTS) == 9


# ── Structured records: what each row says it carries ────────────────────────────────────


def test_warnings_are_structured_records_not_strings() -> None:
    """§4: the registry's warnings "carry structured fields — never bare strings"."""
    record = warning(detail={"pattern": "literal-subscript", "keys": ("query",)})

    assert record.code is ExtractionWarningCode.CONTRACT_INFERRED
    assert record.node == "plan"
    assert record.slots == ("input",)
    assert record.detail["keys"] == ("query",)
    assert to_data(record) == {
        "code": "contract-inferred",
        "message": "reads inferred from literal state access",
        "node": "plan",
        "slots": ["input"],
        "detail": {"pattern": "literal-subscript", "keys": ["query"]},
    }


@pytest.mark.parametrize(
    "code",
    [
        ExtractionWarningCode.CONTRACT_INFERRED,
        ExtractionWarningCode.CONTRACT_DEFAULTED,
        ExtractionWarningCode.OPAQUE_LAMBDA,
        ExtractionWarningCode.ANNOTATION_CONFLICT,
    ],
)
def test_the_node_scoped_rows_cannot_be_built_without_a_node(
    code: ExtractionWarningCode,
) -> None:
    """Every one of these registry rows begins "Node id" — so the field is not optional here.

    This is what makes ANNOTATION §5's lookup answerable: a ``contract-inferred`` with no
    node names no pair, and a slot it was meant to downgrade would read as declared-grade.
    """
    assert warning_rule(code).node_required

    with pytest.raises(ValidationError, match="carries a node id"):
        warning(code=code, node=None, slots=("input",))


@pytest.mark.parametrize(
    "code",
    [
        ExtractionWarningCode.CONTRACT_INFERRED,
        ExtractionWarningCode.CONTRACT_DEFAULTED,
        ExtractionWarningCode.ANNOTATION_CONFLICT,
    ],
)
def test_the_slot_scoped_rows_cannot_be_built_without_a_slot(
    code: ExtractionWarningCode,
) -> None:
    """§8: "which slots were inferred"; "the applied D-011 default"; §4: "slot"."""
    assert warning_rule(code).slots_required

    with pytest.raises(ValidationError, match="carries the slot"):
        warning(code=code, slots=())


def test_contract_inferred_is_licensed_for_reads_and_writes_only() -> None:
    """DEC-08 is the *write-inference* ruling, and §4's pattern table has two slot rows.

    The §4 NEVER-SILENT-UPGRADE rule — "inference **never** yields ``idempotent``,
    ``deterministic``, ``variant`` or ``compensation``" — has its structural half here: a
    record claiming one of those was *inferred* cannot be constructed at all.
    """
    assert warning_rule(ExtractionWarningCode.CONTRACT_INFERRED).licensed_slots == frozenset(
        {"input", "output"}
    )

    assert warning(slots=("input", "output")).slots == ("input", "output")
    for forbidden in ("idempotent", "deterministic", "variant", "compensation"):
        with pytest.raises(ValidationError, match="is licensed for"):
            warning(slots=(forbidden,))


def test_a_slot_outside_the_closed_annotatable_set_is_refused() -> None:
    """ANNOTATION §1 closes the set; ``retry_policy`` is extracted, never annotated."""
    for outside in ("retry_policy", "prompt_digest", "reads", "typo"):
        with pytest.raises(ValidationError):
            warning(code=ExtractionWarningCode.ANNOTATION_INVALID, slots=(outside,))


def test_the_graph_and_file_scoped_rows_need_neither() -> None:
    """Not every row names a node: §8's ``compiled-only-extraction`` is once per extraction,
    and §2's malformed-sidecar ``annotation-invalid`` names a file, not a node."""
    graph_scoped = ExtractionWarning(
        code=ExtractionWarningCode.COMPILED_ONLY_EXTRACTION,
        message="extracted compiled-only: no builder backreference",
        detail={"object_type": "langgraph:Pregel", "downgrade": "one knowability class"},
    )
    file_scoped = ExtractionWarning(
        code=ExtractionWarningCode.ANNOTATION_INVALID,
        message="sidecar not loaded: unknown schema value",
        detail={"file": "/repo/gebra.toml", "schema": "gebra-sidecar-v2"},
    )

    assert graph_scoped.node is None
    assert graph_scoped.slots == ()
    assert file_scoped.targets() == ()


def test_the_message_is_never_the_only_carrier() -> None:
    """It is display copy: required to say something, never the thing a consumer reads."""
    with pytest.raises(ValidationError):
        warning(message="")


def test_detail_holds_reportable_data_only() -> None:
    """A warning is reported, so a value that could not be serialized could not be reported.

    Refused where it is introduced rather than where it would be rendered, and with the
    key or index named — the discipline :mod:`gebra.ir.serialization` applies to documents.
    """
    carried = warning(detail={"n": 3, "ok": True, "why": None, "t": 0.5, "seq": (1, ("a",))})

    assert carried.detail["n"] == 3
    assert carried.detail["t"] == 0.5

    with pytest.raises(ValidationError, match="not JSON data"):
        warning(detail={"callable": len})
    with pytest.raises(ValidationError, match="non-string key"):
        warning(detail={"map": {1: "x"}})
    with pytest.raises(ValidationError, match="JSON has no form"):
        warning(detail={"ratio": float("nan")})
    with pytest.raises(ValidationError):
        warning(detail=("not", "a", "mapping"))

    cyclic: dict[str, Any] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValidationError, match="nests deeper"):
        warning(detail={"cycle": cyclic})


def test_detail_sequences_get_one_representation() -> None:
    """JSON has one sequence type, so an authored tuple and a loaded array must not differ.

    Without this, every emitted warning would compare unequal to its own reloaded copy —
    the asymmetry :mod:`gebra.ir.serialization` records for the foreign ``args_schema``,
    which is tolerable in a hand-authored slot and would not be in one extraction writes.
    """
    authored = warning(detail={"targets": ["book_leg", "book_hotel"], "nested": {"n": [1]}})

    assert authored.detail == {"targets": ("book_leg", "book_hotel"), "nested": {"n": (1,)}}
    assert ExtractionWarning.model_validate_json(json.dumps(to_data(authored))) == authored


def test_the_node_id_follows_the_frozen_grammar() -> None:
    """§5's escaped form, byte for byte — reports and warnings never mint their own scheme."""
    assert warning(node="research/tools/web_search").node == "research/tools/web_search"
    assert warning(node="chain/%seq[0]").node == "chain/%seq[0]"

    for malformed in ("__start__", "a//b", "a/%zz", ""):
        with pytest.raises(ValidationError):
            warning(node=malformed)


def test_a_warning_is_frozen_and_never_built_unvalidated() -> None:
    record = warning()

    with pytest.raises(ValidationError):
        record.node = "act"
    with pytest.raises(NotImplementedError, match="model_construct"):
        ExtractionWarning.model_construct(code=ExtractionWarningCode.OPAQUE_LAMBDA)
    with pytest.raises(ValidationError):
        warning(unknown_member="x")


# ── ANNOTATION §5: the (node id, slot) grade lookup ──────────────────────────────────────


def test_targets_enumerates_the_node_slot_pairs() -> None:
    """The pairs §5 says a warning "names" — one per slot, all under the same node."""
    assert warning(slots=("input", "output")).targets() == (("plan", "input"), ("plan", "output"))


def test_an_unwarned_pair_is_declared_grade() -> None:
    """§5: declared-grade **iff** no such warning names the pair."""
    assert slot_grade([], "plan", "input") is SlotGrade.DECLARED
    assert slot_grade([warning()], "plan", "output") is SlotGrade.DECLARED
    assert slot_grade([warning()], "act", "input") is SlotGrade.DECLARED
    assert not SlotGrade.DECLARED.heuristic


def test_a_warned_pair_is_heuristic_grade_and_says_which_kind() -> None:
    """The two §4 origins stay apart: a pattern licensed it, or the D-011 default applied."""
    inferred = warning(slots=("output",))
    defaulted = warning(
        code=ExtractionWarningCode.CONTRACT_DEFAULTED,
        node="act",
        slots=("effect",),
        message="no write evidence: D-011 default applied",
    )

    assert slot_grade([inferred, defaulted], "plan", "output") is SlotGrade.INFERRED
    assert slot_grade([inferred, defaulted], "act", "effect") is SlotGrade.DEFAULTED
    assert SlotGrade.INFERRED.heuristic
    assert SlotGrade.DEFAULTED.heuristic


def test_only_the_two_codes_the_spec_names_downgrade_a_slot() -> None:
    """§5's "iff" names ``contract-inferred`` and ``contract-defaulted``, and only those.

    ``opaque-lambda`` carries a D-011 default too (§8 sends stitched lambdas to it "instead"
    of ``contract-defaulted``), and it is deliberately *not* read here: widening a normative
    "iff" is a spec question, not an implementation one. This test pins the behaviour so the
    question stays visible instead of being settled by accident.
    """
    assert HEURISTIC_GRADE_CODES == (
        ExtractionWarningCode.CONTRACT_INFERRED,
        ExtractionWarningCode.CONTRACT_DEFAULTED,
    )

    lambda_default = ExtractionWarning(
        code=ExtractionWarningCode.OPAQUE_LAMBDA,
        message="opaque lambda body: D-011 default applied",
        node="chain/%lambda[0]",
        slots=("effect",),
    )

    assert slot_grade([lambda_default], "chain/%lambda[0]", "effect") is SlotGrade.DECLARED


def test_a_pair_named_by_both_codes_reads_as_inferred() -> None:
    """A shape the §4 patterns cannot produce; the tie-break is documented rather than
    left to iteration order."""
    inferred = warning()
    defaulted = warning(code=ExtractionWarningCode.CONTRACT_DEFAULTED)

    assert slot_grade([inferred, defaulted], "plan", "input") is SlotGrade.INFERRED
    assert slot_grade([defaulted, inferred], "plan", "input") is SlotGrade.INFERRED
