"""Every DEC-11-pinned wedge witness/failure example, round-tripped through the models.

DEC-11 (review walkthrough #2, 2026-07-18) pinned the validator I/O shapes so the corpus
reconciliation and the 0.1 → 1.0 migration could execute against frozen targets. This module
is the envelope's side of that record: one example per pin that has an envelope shape,
validated, dumped through the PC-4 profile, and validated back to an equal model.

Which pins have an envelope shape, and which do not:

===== ============================================================ ===========================
pin   ratification                                                 envelope surface
===== ============================================================ ===========================
1     P-01 pass-witness = the 5-key form                           ``WellFormednessWitness``
2     P-02 failure/pass shapes + the enumeration bound B = 16       ``P02SccLocation``,
                                                                    ``TerminationWitness``,
                                                                    ``CycleCensus``
3     P-04 extras are OPTIONAL diagnostics, kept                    ``P04Failure``
4     implicit ``finish→END`` wiring counts toward orphan-hood      pin 1's ``orphan_nodes``
5     condition-ID registry ratified (``orphan-node`` emittable)    ``property_condition``
6     blanket ``recursion_limit`` alone = pass + WARNING-grade note ``WitnessNote``,
                                                                    ``blanket_only``
7     effect-algebra defaults ratified                             none — Appendix A is a
                                                                    commutativity table read
                                                                    by P-09, not a shape
8     four applied resolutions                                     compensation-as-protection
                                                                    (``P06EffectRecord``); the
                                                                    other three are IR-side
===== ============================================================ ===========================

Nothing here executes a workflow, a node, or a network call (WA-07).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

import pytest

from gebra.verify import (
    END,
    START,
    CycleCensus,
    DataflowWitness,
    DeterminismWitness,
    EffectSafetyWitness,
    Failure,
    P02SccLocation,
    P04Failure,
    P06EffectRecord,
    ReportModel,
    TerminationWitness,
    WellFormednessWitness,
    json_text,
    to_data,
    validate_failure,
    validate_witness,
)


def validate_census(data: object) -> CycleCensus:
    """A census is a nested member rather than an envelope entry point — validated in place.

    ``json_text`` is the same JSON-mode ingestion the ``validate_*`` entry points use, so a
    consumer reaching a nested member gets the strict-mode path without re-deriving it.
    """
    return CycleCensus.model_validate_json(json_text(data))


class Pin(NamedTuple):
    """One DEC-11-pinned example and the envelope class it is expected to land in."""

    pin: str
    description: str
    validate: Callable[[object], ReportModel]
    payload: dict[str, Any]
    model: type[ReportModel]


PINS: tuple[Pin, ...] = (
    Pin(
        "1",
        "P-01 pass-witness is the 5-key form (graph-well-formed/positive-* shape)",
        validate_witness,
        {
            "kind": "well-formedness",
            "reachable_from_start": ["archive_summary", "extract_text", "ingest_document"],
            "terminal_nodes": ["archive_summary"],
            "orphan_nodes": [],
            "unresolved_targets": [],
        },
        WellFormednessWitness,
    ),
    Pin(
        "2",
        "P-02 failure: residual-SCC location, one representative cycle, exhaustive false",
        validate_failure,
        {
            "property_condition": "cycle-without-termination-witness",
            "location": {
                "kind": "scc",
                "nodes": ["act", "plan", "reflect"],
                "representative_cycle": ["act", "reflect", "plan"],
                "exhaustive": False,
            },
            "severity": "fatal",
            "claim_class": "defensible",
        },
        Failure,
    ),
    Pin(
        "2",
        "P-02 pass: witness inventory plus acyclicity certificate",
        validate_witness,
        {
            "kind": "termination",
            "inventory": [
                {
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
            ],
            "certificate": [START, "call_service", "check_response", END],
        },
        TerminationWitness,
    ),
    Pin(
        "2",
        "P-02 census: the full cycle list, included only under the B = 16 bound",
        validate_census,
        {"exhaustive": True, "cycles": [["call_service", "check_response"]]},
        CycleCensus,
    ),
    Pin(
        "2",
        "P-02 D4: counter-guard-without-exit-edge, its own condition and cycle anchor",
        validate_failure,
        {
            "property_condition": "counter-guard-without-exit-edge",
            "location": {
                "kind": "cycle",
                "nodes": ["evaluate_rates", "throttle_check", "fetch_rates"],
                "counter_key": "refresh_count",
                "guard_edge": {"source": "throttle_check", "labels": ["immediate", "delayed"]},
            },
            "severity": "fatal",
            "claim_class": "defensible",
        },
        Failure,
    ),
    Pin(
        "3",
        "P-04 writers_on_other_paths kept as an optional diagnostic",
        validate_failure,
        {
            "property_condition": "read-key-never-written-on-path",
            "location": {
                "kind": "state-key",
                "key": "booking_id",
                "node": "send_confirmation",
                "path": [START, "check_availability", "send_confirmation"],
            },
            "severity": "fatal",
            "claim_class": "defensible-a",
            "writers_on_other_paths": ["book_flight"],
        },
        P04Failure,
    ),
    Pin(
        "3",
        "P-04 downstream_writers kept as an optional diagnostic",
        validate_failure,
        {
            "property_condition": "read-key-never-written-on-path",
            "location": {
                "kind": "state-key",
                "key": "itinerary_url",
                "node": "notify_traveler",
                "path": [START, "compile_itinerary", "notify_traveler"],
            },
            "severity": "fatal",
            "claim_class": "defensible-a",
            "downstream_writers": ["publish_itinerary"],
        },
        P04Failure,
    ),
    Pin(
        "3",
        "P-04 pass: one coverage entry per reachable (reader, read key)",
        validate_witness,
        {
            "kind": "dataflow",
            "coverage": [
                {"node": "parse_request", "key": "request", "satisfied_by": [START]},
                {
                    "node": "search_flights",
                    "key": "search_query",
                    "satisfied_by": ["parse_request"],
                },
            ],
        },
        DataflowWitness,
    ),
    Pin(
        "4",
        "Reading A: the single-node splitter graph entry == finish == n reports no orphan",
        validate_witness,
        {
            "kind": "well-formedness",
            "reachable_from_start": ["split_batch"],
            "terminal_nodes": ["split_batch"],
            "orphan_nodes": [],
            "unresolved_targets": [],
        },
        WellFormednessWitness,
    ),
    Pin(
        "5",
        "orphan-node ratified by DEC-11 itself — emittable, on the node anchor",
        validate_failure,
        {
            "property_condition": "orphan-node",
            "location": {"kind": "node", "node": "search_hotels"},
            "severity": "fatal",
            "claim_class": "defensible",
        },
        Failure,
    ),
    Pin(
        "6",
        "blanket recursion_limit alone: pass, with the WARNING-grade structured note",
        validate_witness,
        {
            "kind": "termination",
            "inventory": [
                {
                    "form": "b",
                    "source": {
                        "recursion_limit": {
                            "value": 25,
                            "justification": "one refinement turn is two supersteps; UX caps at 12",
                        }
                    },
                    "discharges": "blanket",
                }
            ],
            "certificate": [START, "propose_itinerary", "collect_feedback", END],
            "notes": [
                {
                    "kind": "scc-covered-only-by-recursion-limit",
                    "severity": "warning",
                    "locations": [
                        {
                            "kind": "scc",
                            "nodes": ["collect_feedback", "propose_itinerary"],
                            "representative_cycle": ["collect_feedback", "propose_itinerary"],
                            "exhaustive": False,
                            "blanket_only": True,
                        }
                    ],
                }
            ],
        },
        TerminationWitness,
    ),
    Pin(
        "6",
        "strict mode reuses the same condition ID and distinguishes on blanket_only",
        validate_failure,
        {
            "property_condition": "cycle-without-termination-witness",
            "location": {
                "kind": "scc",
                "nodes": ["collect_feedback", "propose_itinerary"],
                "representative_cycle": ["collect_feedback", "propose_itinerary"],
                "exhaustive": False,
                "blanket_only": True,
            },
            "severity": "fatal",
            "claim_class": "defensible",
        },
        Failure,
    ),
    Pin(
        "8",
        "compensation-as-protection per DEC-05 D7 (effect-safety/positive-03 shape)",
        validate_witness,
        {
            "kind": "effect-safety",
            "cycles": [["propose_dates", "place_hotel_hold", "review_hold", "release_hotel_hold"]],
            "effects": [
                {
                    "node": "place_hotel_hold",
                    "effect": ["billable"],
                    "region": "cycle",
                    "cycle": [
                        "propose_dates",
                        "place_hotel_hold",
                        "review_hold",
                        "release_hotel_hold",
                    ],
                    "protection": "compensation_hook",
                    "hook": "release_hotel_hold",
                }
            ],
        },
        EffectSafetyWitness,
    ),
    Pin(
        "8",
        "P-08 pass carries the mandatory provider caveat when a claim is LLM-backed",
        validate_witness,
        {
            "kind": "determinism",
            "claims": [
                {
                    "node": "classify_request",
                    "llm_backed": True,
                    "seed": 42,
                    "temperature": 0,
                    "divergence_handling": "logged",
                }
            ],
            "caveat": "provider-seed-reproducibility-not-guaranteed",
            "claim_class": "heuristic",
        },
        DeterminismWitness,
    ),
)

IDS = tuple(f"pin-{pin.pin}: {pin.description}" for pin in PINS)


@pytest.mark.parametrize("pinned", PINS, ids=IDS)
def test_pinned_example_lands_in_its_model(pinned: Pin) -> None:
    assert type(pinned.validate(pinned.payload)) is pinned.model


@pytest.mark.parametrize("pinned", PINS, ids=IDS)
def test_pinned_example_round_trips(pinned: Pin) -> None:
    """data → model → PC-4 dump → model, equal. The PC-6 identity, on the pinned shapes."""
    model = pinned.validate(pinned.payload)
    assert pinned.validate(to_data(model)) == model


@pytest.mark.parametrize("pinned", PINS, ids=IDS)
def test_pinned_example_survives_field_for_field(pinned: Pin) -> None:
    """Nothing declared in the example is rewritten on the way through the model.

    Round-tripping alone would still pass if a value were coerced consistently in both
    directions; this projects the dump back onto the example's own keys and compares.
    """
    dumped = to_data(pinned.validate(pinned.payload))
    assert _projected(dumped, pinned.payload) == pinned.payload


def _projected(dumped: Any, template: Any) -> Any:
    """``dumped`` restricted to the keys ``template`` declares, recursively."""
    if isinstance(template, dict) and isinstance(dumped, dict):
        return {key: _projected(dumped.get(key), value) for key, value in template.items()}
    if isinstance(template, list) and isinstance(dumped, list) and len(template) == len(dumped):
        return [_projected(item, value) for item, value in zip(dumped, template)]
    return dumped


def test_every_pin_with_an_envelope_shape_has_an_example() -> None:
    """Pins 7 and the three IR-side item-8 resolutions have no envelope shape — stated, not skipped.

    Pin 7 ratifies the Appendix A declared-tag commutativity defaults, which P-09 reads and
    the envelope never carries; item 8's other three resolutions (``x-extra`` removed,
    ``checkpointer.present`` explicit, the ``All``/``"*"`` sentinel expanding) are IR-side
    and land in ``gebra.ir``.
    """
    assert {pin.pin for pin in PINS} == {"1", "2", "3", "4", "5", "6", "8"}


def test_the_effect_record_is_the_shape_pin_8_names() -> None:
    """The compensation slot is a protection arm of the record, not an effect tag."""
    assert "compensation_hook" in str(P06EffectRecord.model_fields["protection"].annotation)
    assert "compensated_by" not in P06EffectRecord.model_fields


def test_the_scc_anchor_is_the_shape_pin_2_names() -> None:
    assert P02SccLocation.model_fields["exhaustive"].is_required()
    assert set(P02SccLocation.model_fields) == {
        "kind",
        "nodes",
        "representative_cycle",
        "exhaustive",
        "blanket_only",
    }
