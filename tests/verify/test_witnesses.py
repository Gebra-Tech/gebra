"""The five wedge witness models and the §0.3 ``Witness`` union.

A witness is structured, re-checkable evidence — the invariants each section fixes are
enforced by the models rather than left to the validator that fills them in: P-02's
form ↦ (element, source, discharges) mapping, and P-08's caveat-iff-LLM-backed rule.

Nothing here executes a workflow, a node, or a network call (WA-07).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from gebra.verify import (
    END,
    START,
    CycleCensus,
    DataflowWitness,
    DeterminismWitness,
    EffectSafetyWitness,
    TerminationWitness,
    WellFormednessWitness,
    Witness,
    WitnessInventoryEntry,
    to_data,
    validate_witness,
)

WITNESS_ADAPTER: TypeAdapter[Any] = TypeAdapter(Witness)

COUNTER_ENTRY: dict[str, Any] = {
    "form": "a",
    "element": {
        "kind": "edge",
        "source": "check_response",
        "target": "call_service",
        "label": "retry",
    },
    "source": {
        "guard_edge": {"source": "check_response", "label": "retry"},
        "counter_key": "retry_count",
        "bound": 3,
    },
    "discharges": "all-simple-cycles-through-element",
}
BLANKET_ENTRY: dict[str, Any] = {
    "form": "b",
    "source": {"recursion_limit": {"value": 25, "justification": "concierge UX caps at 12 turns"}},
    "discharges": "blanket",
}
VARIANT_ENTRY: dict[str, Any] = {
    "form": "c",
    "element": {"kind": "node", "node": "quote_next_hotel"},
    "source": {"variant": {"key": "hotel_shortlist", "measure": "len(hotel_shortlist) decreases"}},
    "discharges": "all-simple-cycles-through-element",
}

#: One payload per wedge member — the ``kind`` vocabulary the union is discriminated on.
WITNESS_PAYLOADS: dict[type[Any], dict[str, Any]] = {
    WellFormednessWitness: {
        "kind": "well-formedness",
        "reachable_from_start": ["archive_summary", "extract_text"],
        "terminal_nodes": ["archive_summary"],
        "orphan_nodes": [],
        "unresolved_targets": [],
    },
    TerminationWitness: {
        "kind": "termination",
        "inventory": [COUNTER_ENTRY],
        "certificate": [START, "call_service", "check_response", END],
    },
    DataflowWitness: {
        "kind": "dataflow",
        "coverage": [{"node": "parse_request", "key": "request", "satisfied_by": [START]}],
    },
    EffectSafetyWitness: {
        "kind": "effect-safety",
        "cycles": [["book_hotel", "verify_hold"]],
        "effects": [
            {
                "node": "book_hotel",
                "effect": ["billable"],
                "region": "cycle",
                "cycle": ["book_hotel", "verify_hold"],
                "protection": "idempotency_key",
                "key": "hotel_offer_id",
            }
        ],
    },
    DeterminismWitness: {
        "kind": "determinism",
        "claims": [
            {
                "node": "normalize_fares",
                "llm_backed": False,
                "basis": "pure-local-computation",
                "pinning_required": False,
            }
        ],
        "claim_class": "heuristic",
    },
}


@pytest.mark.parametrize(
    ("model", "payload"), WITNESS_PAYLOADS.items(), ids=lambda a: getattr(a, "__name__", "")
)
def test_union_has_one_member_per_wedge_property(model: type[Any], payload: dict[str, Any]) -> None:
    assert type(WITNESS_ADAPTER.validate_json(json.dumps(payload))) is model
    assert type(validate_witness(payload)) is model


@pytest.mark.parametrize(
    ("model", "payload"), WITNESS_PAYLOADS.items(), ids=lambda a: getattr(a, "__name__", "")
)
def test_every_witness_round_trips(model: type[Any], payload: dict[str, Any]) -> None:
    witness = validate_witness(payload)
    assert validate_witness(to_data(witness)) == witness


def test_union_is_closed_to_the_declared_kinds() -> None:
    with pytest.raises(ValidationError, match="union_tag_not_found|does not match any"):
        validate_witness({"kind": "signature", "undeclared_reads": []})


# ── P-01: the 5-key form (DEC-11 pin 1) ──────────────────────────────────────────────────


def test_wellformedness_witness_is_the_five_key_form() -> None:
    assert list(WellFormednessWitness.model_fields) == [
        "kind",
        "reachable_from_start",
        "terminal_nodes",
        "orphan_nodes",
        "unresolved_targets",
    ]


def test_wellformedness_witness_requires_all_five_keys() -> None:
    """The 4-key drift the corpus reconciles away from is not a valid witness."""
    with pytest.raises(ValidationError):
        validate_witness(
            {
                "kind": "well-formedness",
                "entry": "a",
                "finish": "b",
                "unreachable_nodes": [],
                "dangling_refs": [],
            }
        )


# ── P-02: the inventory entry's form fixes the rest of the entry ─────────────────────────


@pytest.mark.parametrize("payload", [COUNTER_ENTRY, BLANKET_ENTRY, VARIANT_ENTRY])
def test_inventory_entry_accepts_each_form(payload: dict[str, Any]) -> None:
    entry = WitnessInventoryEntry.model_validate_json(json.dumps(payload))
    assert entry.form == payload["form"]


def test_blanket_form_discharges_no_element() -> None:
    """Form (b) is a blanket over E — attaching an element would misdescribe it."""
    with pytest.raises(ValidationError, match="discharges no element"):
        WitnessInventoryEntry.model_validate_json(
            json.dumps({**BLANKET_ENTRY, "element": {"kind": "node", "node": "a"}})
        )


def test_counter_form_discharges_an_edge_not_a_node() -> None:
    with pytest.raises(ValidationError, match="form \\(a\\) discharges an element of type Edge"):
        WitnessInventoryEntry.model_validate_json(
            json.dumps({**COUNTER_ENTRY, "element": {"kind": "node", "node": "check_response"}})
        )


def test_variant_form_discharges_the_carrier_node() -> None:
    with pytest.raises(ValidationError, match="form \\(c\\) discharges an element of type Node"):
        WitnessInventoryEntry.model_validate_json(
            json.dumps({**VARIANT_ENTRY, "element": {"kind": "edge", "source": "a", "target": "b"}})
        )


def test_form_and_source_must_agree() -> None:
    with pytest.raises(ValidationError, match="sourced from a CounterGuardSource"):
        WitnessInventoryEntry.model_validate_json(
            json.dumps({**COUNTER_ENTRY, "source": BLANKET_ENTRY["source"]})
        )


def test_discharges_reads_blanket_only_for_form_b() -> None:
    with pytest.raises(ValidationError, match="reads 'blanket' for form"):
        WitnessInventoryEntry.model_validate_json(
            json.dumps({**COUNTER_ENTRY, "discharges": "blanket"})
        )
    with pytest.raises(ValidationError, match="reads 'blanket' for form"):
        WitnessInventoryEntry.model_validate_json(
            json.dumps({**BLANKET_ENTRY, "discharges": "all-simple-cycles-through-element"})
        )


def test_vacuous_element_carries_a_structured_empty_set() -> None:
    """T-W-SPEC §6.2: a form-(c) carrier on no cycle stays in the inventory, discharging ().

    The marker is the empty set, never a string — declared content is surfaced without any
    finding following from it.
    """
    entry = WitnessInventoryEntry.model_validate_json(
        json.dumps({**VARIANT_ENTRY, "discharges": []})
    )
    assert entry.discharges == ()
    assert to_data(entry)["discharges"] == []


def test_only_a_variant_carrier_can_be_vacuous() -> None:
    """T-W-SPEC §6.2/§4: a form-(a) element always lies on a cycle — its gated edge is in an SCC."""
    with pytest.raises(ValidationError, match="only a form-\\(c\\) carrier can be vacuous"):
        WitnessInventoryEntry.model_validate_json(json.dumps({**COUNTER_ENTRY, "discharges": []}))


def test_termination_witness_carries_a_recheckable_certificate() -> None:
    witness = validate_witness(WITNESS_PAYLOADS[TerminationWitness])
    assert isinstance(witness, TerminationWitness)
    assert witness.certificate[0] == START
    assert witness.notes == ()
    assert witness.cycles is None


def test_census_exists_only_when_it_completed() -> None:
    """§2.5/T-W-SPEC §6.3: an aborted census omits the list and becomes a note instead."""
    census = CycleCensus.model_validate_json(
        json.dumps({"exhaustive": True, "cycles": [["call_service", "check_response"]]})
    )
    assert census.cycles == (("call_service", "check_response"),)
    with pytest.raises(ValidationError):
        CycleCensus.model_validate_json(json.dumps({"exhaustive": False, "cycles": []}))


def test_witness_note_kinds_are_closed_and_are_not_condition_ids() -> None:
    witness = validate_witness(
        {
            **WITNESS_PAYLOADS[TerminationWitness],
            "notes": [
                {
                    "kind": "scc-covered-only-by-recursion-limit",
                    "severity": "warning",
                    "locations": [
                        {
                            "kind": "scc",
                            "nodes": ["judge_fare", "poll_fare"],
                            "representative_cycle": ["judge_fare", "poll_fare"],
                            "exhaustive": False,
                            "blanket_only": True,
                        }
                    ],
                }
            ],
        }
    )
    assert isinstance(witness, TerminationWitness)
    assert witness.notes[0].severity == "warning"

    with pytest.raises(ValidationError):
        validate_witness(
            {
                **WITNESS_PAYLOADS[TerminationWitness],
                "notes": [{"kind": "cycle-without-termination-witness"}],
            }
        )


def test_a_note_is_never_gate_bearing() -> None:
    """§2.3: notes are never gate-bearing, and §0.2 knows only WARNING-grade ones."""
    with pytest.raises(ValidationError):
        validate_witness(
            {
                **WITNESS_PAYLOADS[TerminationWitness],
                "notes": [{"kind": "cycle-census-capped", "severity": "fatal"}],
            }
        )
    witness = validate_witness(
        {
            **WITNESS_PAYLOADS[TerminationWitness],
            "notes": [{"kind": "cycle-census-capped"}],
        }
    )
    assert isinstance(witness, TerminationWitness)
    assert witness.notes[0].severity is None


# ── P-08: the caveat is required exactly when a claim is LLM-backed ──────────────────────


def test_caveat_required_when_a_claim_is_llm_backed() -> None:
    llm_claim = {"node": "classify_request", "llm_backed": True, "seed": 42, "temperature": 0}
    with pytest.raises(ValidationError, match="caveat present iff"):
        validate_witness({"kind": "determinism", "claims": [llm_claim], "claim_class": "heuristic"})

    witness = validate_witness(
        {
            "kind": "determinism",
            "claims": [llm_claim],
            "caveat": "provider-seed-reproducibility-not-guaranteed",
            "claim_class": "heuristic",
        }
    )
    assert isinstance(witness, DeterminismWitness)
    assert witness.caveat == "provider-seed-reproducibility-not-guaranteed"


def test_caveat_refused_when_no_claim_is_llm_backed() -> None:
    with pytest.raises(ValidationError, match="caveat present iff"):
        validate_witness(
            {
                **WITNESS_PAYLOADS[DeterminismWitness],
                "caveat": "provider-seed-reproducibility-not-guaranteed",
            }
        )


def test_vacuous_determinism_pass_needs_no_caveat() -> None:
    witness = validate_witness({"kind": "determinism", "claims": [], "claim_class": "heuristic"})
    assert isinstance(witness, DeterminismWitness)
    assert witness.claims == ()


# ── P-06: protection is named, not merely asserted ───────────────────────────────────────


def test_effect_record_names_what_protected_it() -> None:
    witness = validate_witness(WITNESS_PAYLOADS[EffectSafetyWitness])
    assert isinstance(witness, EffectSafetyWitness)
    record = witness.effects[0]
    assert (record.protection, record.key, record.hook) == (
        "idempotency_key",
        "hotel_offer_id",
        None,
    )


def test_compensation_hook_is_protection() -> None:
    """DEC-05 D7, confirmed as a DEC-11 applied resolution."""
    witness = validate_witness(
        {
            "kind": "effect-safety",
            "cycles": [["place_hotel_hold", "review_hold"]],
            "effects": [
                {
                    "node": "place_hotel_hold",
                    "effect": ["billable"],
                    "region": "cycle",
                    "cycle": ["place_hotel_hold", "review_hold"],
                    "protection": "compensation_hook",
                    "hook": "release_hotel_hold",
                }
            ],
        }
    )
    assert isinstance(witness, EffectSafetyWitness)
    assert witness.effects[0].hook == "release_hotel_hold"
