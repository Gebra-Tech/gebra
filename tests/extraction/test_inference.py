"""Shallow inference as extraction sees it — ANNOTATION-API-SPEC §4/§5.

The engine and its closed pattern table are ``tests/annotations/test_inference.py``; so is this
path's WA-07 tripwire, since reading a node's AST is the whole of what it does and the engine
is where that happens. What this module tests is the seam and the sentence the seam exists for:

* **Every inferred or defaulted slot carries its structured warning**, checked through §5's own
  normative lookup rather than by inspecting the records — a slot is heuristic-grade **iff** a
  ``contract-inferred``/``contract-defaulted`` warning names the (node id, slot) pair, and that
  is what a validator will run.
* **The records are the taxonomy's**, so the model's own registry rules apply to them; and the
  ``contract-inferred`` row's licensed slots make a claim about ``deterministic`` structurally
  unbuildable, which is the NEVER-SILENT-UPGRADE rule with a second lock on it.
* **What §4 produces now reaches an IR**, through §3's precedence chain (EX-11): an
  extraction with no declaration anywhere resolves every node to a D-011 default and says so,
  and §5's lookup answers for the slot the IR actually carries. The chain itself is
  ``tests/extraction/test_contracts.py``; what is asserted here is that the seam and the
  lookup agree on one live graph.

Nothing here opens a socket, and no node is called.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import gebra
from gebra.annotations import SlotGrade
from gebra.annotations.inference import (
    INFERENCE_SLOTS,
    NEVER_INFERRED,
    DefaultRule,
    InferenceFinding,
    StateSchema,
    infer_node,
)
from gebra.extraction import (
    ExtractionWarning,
    ExtractionWarningCode,
    contract_warnings,
    slot_grade,
)
from gebra.extraction.inference import FINDING_CODES
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_inference as si

if TYPE_CHECKING:
    from gebra.annotations.inference import Inference

#: The graph's state, as an extraction would supply it.
SCHEMA: Final = StateSchema.of(*si.FULL_STATE_SCHEMAS)

#: The node id the records are filed under here — an ordinary single-segment id.
NODE: Final = "plan_step"


def inferred(name: str) -> Inference:
    """One fixture's inference, run the way its row says."""
    fixture = si.INFERENCE_FIXTURES[name]
    return infer_node(fixture.node, state_schema=SCHEMA if fixture.schema else None)


# ── The §5 grade lookup, which is what the acceptance box is about ───────────────────────


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_every_inferred_or_defaulted_slot_reads_back_as_heuristic_grade(name: str) -> None:
    """§4's "every inferred slot carries a warning", asserted through §5's own lookup.

    Not by inspecting the records — by asking the question a validator asks: "a slot on node
    *n* is declared-grade **iff** no ``contract-inferred``/``contract-defaulted`` warning in
    the extraction envelope names the (node id, slot) pair; otherwise it is heuristic-grade".
    A slot this tier filled that came back ``declared`` would be a heuristic value wearing an
    author's authority, which is the failure §5 is written to prevent.
    """
    inference = inferred(name)

    warnings = contract_warnings(NODE, inference)

    for slot in inference.contract.declared_slots():
        grade = slot_grade(warnings, NODE, slot)
        assert grade.heuristic, slot
        assert grade is (
            SlotGrade.DEFAULTED if slot in ("effect", "pure") else SlotGrade.INFERRED
        ), slot


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_a_slot_this_tier_left_open_reads_back_as_declared(name: str) -> None:
    """The other direction of the same "iff": no record, no grade.

    §5's lookup is what tells a validator that a slot it is about to reason from was written
    by an author. A warning naming a slot inference did not fill would take that away from a
    declaration for no reason.
    """
    inference = inferred(name)

    warnings = contract_warnings(NODE, inference)
    untouched = set(INFERENCE_SLOTS) - set(inference.contract.declared_slots())

    for slot in untouched:
        assert slot_grade(warnings, NODE, slot) is SlotGrade.DECLARED, slot


def test_the_lookup_is_keyed_by_node_as_well_as_slot() -> None:
    """(node id, slot) is the key §5 states — one node's inference grades only that node."""
    warnings = contract_warnings(NODE, inferred("input_subscript"))

    assert slot_grade(warnings, NODE, "input") is SlotGrade.INFERRED
    assert slot_grade(warnings, "act_step", "input") is SlotGrade.DECLARED


# ── The records are the taxonomy's ───────────────────────────────────────────────────────


def test_the_two_grades_map_to_the_two_registry_rows() -> None:
    """§5's heuristic grades and §4's warning rows are the same two things, named twice."""
    assert FINDING_CODES == {
        SlotGrade.INFERRED: ExtractionWarningCode.CONTRACT_INFERRED,
        SlotGrade.DEFAULTED: ExtractionWarningCode.CONTRACT_DEFAULTED,
    }
    assert set(FINDING_CODES) == {SlotGrade.INFERRED, SlotGrade.DEFAULTED}


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_every_finding_becomes_a_valid_taxonomy_record(name: str) -> None:
    """Building the records runs the taxonomy's own registry rules over every fixture.

    :class:`~gebra.extraction.warnings.ExtractionWarning` refuses a ``contract-inferred``
    without a node id, without slots, or naming a slot outside ``input``/``output`` — so a
    table that passes here is a table whose findings the taxonomy admits.
    """
    inference = inferred(name)

    warnings = contract_warnings(NODE, inference)

    assert len(warnings) == len(inference.findings)
    for warning in warnings:
        assert warning.node == NODE
        assert warning.slots
        assert warning.code in set(FINDING_CODES.values())
        assert warning.message


def test_an_inferred_record_cannot_claim_an_upgraded_slot() -> None:
    """The second lock on NEVER-SILENT-UPGRADE, in the taxonomy rather than in the engine.

    §4's licensed-pattern table has exactly two slot rows, so a ``contract-inferred`` record
    claiming ``deterministic`` was inferred is unbuildable — the engine cannot produce one and
    the model would not carry it.
    """
    for slot in NEVER_INFERRED:
        with pytest.raises(ValueError, match="licensed for"):
            ExtractionWarning(
                code=ExtractionWarningCode.CONTRACT_INFERRED,
                message="…",
                node=NODE,
                slots=(slot,),
            )


def test_the_detail_survives_the_reportable_narrowing() -> None:
    """A warning is *reported*, so everything a finding carries has to be JSON data.

    The model narrows ``detail`` on the way in and refuses what a report could not carry; the
    citations map and the blocker list are the two structured values §4's rows ask for, so
    they are the ones checked here.
    """
    inference = inferred("input_subscript")

    (inferred_record, defaulted_record) = contract_warnings(NODE, inference)

    assert inferred_record.detail["patterns"] == {
        "input": {"query": "state-access", "budget": "state-access"},
        "output": {"plan": "return-literal"},
    }
    assert tuple(inferred_record.detail["claims_not_upgraded"]) == NEVER_INFERRED
    assert defaulted_record.detail["rule"] == DefaultRule.WRITES_STATE.value
    # A tuple on the way out, not the list the finding carried: the model gives JSON's one
    # sequence type one representation, so an authored list and a reloaded array compare equal.
    assert defaulted_record.detail["applied"] == {"effect": ("write",)}


def test_a_node_with_nothing_to_infer_produces_no_records() -> None:
    """No finding, no warning: §8's taxonomy is not a log of what was attempted."""
    inference = infer_node(
        si.reads_literal_subscripts, state_schema=SCHEMA, declared=("input", "output", "pure")
    )

    assert inference.contract.declared_slots() == ()
    assert contract_warnings(NODE, inference) == ()


def test_a_record_is_built_for_a_finding_of_either_grade() -> None:
    """Both rows of the table are reachable from a hand-built finding, not only from the
    engine — so the mapping is tested as a mapping."""
    for grade, code in FINDING_CODES.items():
        finding = InferenceFinding(grade=grade, slots=("input",), message="…")

        warning = contract_warnings(NODE, _one(finding))[0]

        assert warning.code is code


def _one(finding: InferenceFinding) -> Inference:
    """An inference carrying exactly ``finding`` and nothing else."""
    from gebra.annotations import NodeContract
    from gebra.annotations.inference import Inference, NodeSource, SourceRule

    return Inference(
        contract=NodeContract(),
        source=NodeSource(rule=SourceRule.OPAQUE),
        findings=(finding,),
    )


# ── The seam, over a live extraction ─────────────────────────────────────────────────────


def test_what_inference_produced_is_what_the_grade_lookup_answers_for() -> None:
    """The §4 tier, the IR slot it filled, and §5's lookup, asserted as one chain.

    This test was the EX-11 marker: it used to assert that nothing §4 produced reached an IR,
    because §3's precedence chain did not exist and a ``contract-defaulted`` naming a slot
    that was absent would have been a false answer to §5's lookup. The chain landed, so the
    marker flips into the property it was standing in for — for every slot the IR carries, the
    grade is heuristic **iff** the tier that filled it was inference, checked through
    :meth:`~gebra.extraction.envelope.ExtractionEnvelope.slot_grade`, which is what a
    validator runs.

    These three nodes declare nothing on any surface and their bodies only ``raise``, so each
    resolves to the decision D-011 default for a body with no write evidence. That is "a
    no-evidence-found result, not a proof" (§4), which is exactly why the grade matters.
    """
    envelope = gebra.extract(sg.build_sentinel_graph())

    assert envelope.warnings_of(ExtractionWarningCode.CONTRACT_INFERRED) == ()
    assert len(envelope.warnings_of(ExtractionWarningCode.CONTRACT_DEFAULTED)) == 3
    for node in envelope.ir.nodes:
        annotations = node.annotations
        assert annotations is not None
        assert annotations.pure is True
        assert envelope.slot_grade(node.id, "pure") is SlotGrade.DEFAULTED
        for slot in ("input", "output", "effect"):
            assert getattr(annotations, slot) is None
            assert envelope.slot_grade(node.id, slot) is SlotGrade.DECLARED
