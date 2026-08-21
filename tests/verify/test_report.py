"""``PropertyReport``, the failure side, and the ingestion path.

Two rules carry most of this module. **Witness XOR failure** (§0.3) is the invariant that
makes a report readable without branching on absence: a pass has a witness and no failure,
a fail has a failure and no witness, and no other combination validates. **One property,
one report** (§0.3 packaging rule, ratified envelope-wide at walkthrough #2 — DEC-11):
further same-property findings ride ``co_failures``, cross-property WARNING-class side
findings ride ``advisories``, and every record carries its own severity and claim class.

Nothing here executes a workflow, a node, or a network call (WA-07).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from gebra.verify import (
    START,
    Advisory,
    AnyFailure,
    CoFailure,
    DataflowLocation,
    Failure,
    NodeLocation,
    P01EdgeLocation,
    P04Failure,
    P06NodeLocation,
    PropertyReport,
    WellFormednessWitness,
    to_data,
    validate_failure,
    validate_report,
    validate_witness,
)
from tests.verify.test_locations import union_members

CLEAN_WITNESS: dict[str, Any] = {
    "kind": "well-formedness",
    "reachable_from_start": ["extract_text", "ingest_document"],
    "terminal_nodes": ["extract_text"],
    "orphan_nodes": [],
    "unresolved_targets": [],
}
UNREACHABLE_FAILURE: dict[str, Any] = {
    "property_condition": "node-unreachable-from-start",
    "location": {"kind": "node", "node": "escalate_to_human"},
    "severity": "fatal",
    "claim_class": "defensible",
}


# ── §0.3: witness XOR failure ────────────────────────────────────────────────────────────


def test_pass_carries_a_witness() -> None:
    report = validate_report(
        {"property": "graph-well-formed", "result": "pass", "witness": CLEAN_WITNESS}
    )
    assert report.failure is None
    assert isinstance(report.witness, WellFormednessWitness)


def test_fail_carries_a_failure() -> None:
    report = validate_report(
        {"property": "graph-well-formed", "result": "fail", "failure": UNREACHABLE_FAILURE}
    )
    assert report.witness is None
    assert report.failure is not None
    assert report.failure.property_condition == "node-unreachable-from-start"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"result": "pass"}, "witness present iff result == pass"),
        ({"result": "fail"}, "failure present iff result == fail"),
        ({"result": "pass", "failure": UNREACHABLE_FAILURE}, "witness present iff result == pass"),
        ({"result": "fail", "witness": CLEAN_WITNESS}, "witness present iff result == pass"),
        (
            {"result": "pass", "witness": CLEAN_WITNESS, "failure": UNREACHABLE_FAILURE},
            "failure present iff result == fail",
        ),
        (
            {"result": "fail", "witness": CLEAN_WITNESS, "failure": UNREACHABLE_FAILURE},
            "witness present iff result == pass",
        ),
    ],
)
def test_every_other_combination_is_refused(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_report({"property": "graph-well-formed", **payload})


def test_constructors_satisfy_the_xor_rule_by_construction() -> None:
    witness = validate_witness(CLEAN_WITNESS)
    failure = validate_failure(UNREACHABLE_FAILURE)
    passing = PropertyReport.passing("graph-well-formed", witness)
    failing = PropertyReport.failing("graph-well-formed", failure)
    assert (passing.result, passing.failure) == ("pass", None)
    assert (failing.result, failing.witness) == ("fail", None)


def test_the_xor_rule_survives_a_copy() -> None:
    """``model_copy`` is the one route around a model validator; the report must not use it."""
    report = PropertyReport.passing("graph-well-formed", validate_witness(CLEAN_WITNESS))
    smuggled = report.model_copy(update={"result": "fail"})
    with pytest.raises(ValidationError, match="witness present iff result == pass"):
        validate_report(to_data(smuggled))


# ── §0.3: the packaging rule ─────────────────────────────────────────────────────────────


def test_same_property_findings_ride_co_failures() -> None:
    """``graph-well-formed/negative-03``: the (iv) primary with its (i) cascade."""
    report = validate_report(
        {
            "property": "graph-well-formed",
            "result": "fail",
            "failure": {
                "property_condition": "path-map-target-undefined",
                "location": {
                    "kind": "edge",
                    "source": "review_booking",
                    "label": "confirm",
                    "undefined_target": "send_confirmatoin",
                },
                "severity": "fatal",
                "claim_class": "defensible",
                "co_failures": [
                    {
                        "property": "graph-well-formed",
                        "property_condition": "node-unreachable-from-start",
                        "location": {"kind": "node", "node": "send_confirmation"},
                        "severity": "fatal",
                        "claim_class": "defensible",
                    }
                ],
            },
        }
    )
    assert report.failure is not None
    assert isinstance(report.failure.location, P01EdgeLocation)
    assert report.failure.co_failures is not None
    (cascade,) = report.failure.co_failures
    assert cascade.property == "graph-well-formed"
    assert isinstance(cascade.location, NodeLocation)


def test_cross_property_advisories_are_warning_class() -> None:
    """``mixed/03``: P-08 findings ride a P-09 primary as advisories, never as co-failures."""
    advisory = Advisory(
        property="determinism-replay",
        property_condition="deterministic-llm-seed-unpinned",
        severity="warning",
        claim_class="heuristic",
        location=NodeLocation(kind="node", node="market_analysis"),
    )
    assert advisory.severity == "warning"
    with pytest.raises(ValidationError):
        Advisory.model_validate_json(json.dumps({**to_data(advisory), "severity": "error"}))


def test_every_record_carries_its_own_claim_class() -> None:
    """§0.1: a consumer can never mistake a HEURISTIC advisory for a proof-backed finding."""
    for model in (Failure, CoFailure, Advisory):
        assert {"severity", "claim_class"} <= set(model.model_fields)
        assert model.model_fields["claim_class"].is_required()


def test_subsumed_by_names_the_owning_property() -> None:
    """DEC-05 D2, the ``mixed/04`` precedent: one root cause, one report, no double-blame."""
    co_failure = CoFailure(
        property="dataflow-completeness",
        property_condition="read-key-never-written-on-path",
        location=NodeLocation(kind="node", node="compliance_log"),
        severity="fatal",
        claim_class="defensible-a",
        subsumed_by="P-01",
        note="owned entirely by the P-01 finding above",
    )
    assert co_failure.subsumed_by == "P-01"
    with pytest.raises(ValidationError):
        CoFailure.model_validate_json(json.dumps({**to_data(co_failure), "subsumed_by": "P-99"}))


def test_a_co_failure_may_carry_another_propertys_location_subtype() -> None:
    """``mixed/02``: a P-02 primary carrying a P-04 co-failure with its own location shape."""
    co_failure = CoFailure.model_validate_json(
        json.dumps(
            {
                "property": "dataflow-completeness",
                "property_condition": "read-key-never-written-on-path",
                "location": {
                    "kind": "state-key",
                    "key": "style_guide",
                    "node": "summarize",
                    "path": [START, "gather", "summarize"],
                },
                "severity": "fatal",
                "claim_class": "defensible-a",
            }
        )
    )
    assert isinstance(co_failure.location, DataflowLocation)


# ── §4.3: P04Failure, and why it resolves on its location ────────────────────────────────


def test_p04_failure_carries_the_kept_diagnostics() -> None:
    """DEC-11 pin 3: both extras stay, emitted only when non-empty, never verdict-bearing."""
    failure = validate_failure(
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
        }
    )
    assert isinstance(failure, P04Failure)
    assert failure.writers_on_other_paths == ("book_flight",)
    assert failure.downstream_writers is None
    assert "downstream_writers" not in to_data(failure)


def test_a_p04_failure_without_extras_is_still_a_p04_failure() -> None:
    """The location discriminates, so fixture-loaded and validator-built agree on the class.

    Resolving on the optional extras alone would make a diagnostics-free P-04 failure load
    as a base ``Failure`` while a validator constructs ``P04Failure`` — and pydantic
    equality is class-sensitive, so PC-6 would break on exactly those cases.
    """
    failure = validate_failure(
        {
            "property_condition": "read-key-never-written-on-path",
            "location": {
                "kind": "state-key",
                "key": "compliance_token",
                "node": "send_reply",
                "path": [START, "intake", "send_reply"],
            },
            "severity": "fatal",
            "claim_class": "defensible-a",
        }
    )
    assert isinstance(failure, P04Failure)


def test_a_non_dataflow_failure_is_the_base_failure() -> None:
    failure = validate_failure(UNREACHABLE_FAILURE)
    assert type(failure) is Failure


def test_the_base_failure_refuses_the_p04_extras() -> None:
    """``extra="forbid"`` is what makes the subtype necessary in the first place (§4.3)."""
    with pytest.raises(ValidationError):
        Failure.model_validate_json(
            json.dumps({**UNREACHABLE_FAILURE, "writers_on_other_paths": ["book_flight"]})
        )


def test_p04_failure_keeps_the_base_field_order() -> None:
    """PC-4 serializes in definition order; the subtype appends rather than reshuffles."""
    assert list(P04Failure.model_fields)[: len(Failure.model_fields)] == list(Failure.model_fields)


def test_every_failure_subtype_adds_a_required_field() -> None:
    """The left-to-right invariant for `AnyFailure`, derived from the union, not listed.

    A future concrete failure subtype whose additions were all optional would let a base
    payload resolve to it (or the reverse), and pydantic equality is class-sensitive — the
    exact PC-6 break `P04Failure`'s narrowed `location` was introduced to prevent.
    """
    members = union_members(AnyFailure)
    assert Failure in members
    for model in members:
        anchor = model.__mro__[1]
        if anchor not in members:
            continue
        added_required = {
            name
            for name, field in model.model_fields.items()
            if field.is_required()
            and not (name in anchor.model_fields and anchor.model_fields[name].is_required())
        }
        narrowed = {
            name
            for name, field in model.model_fields.items()
            if name in anchor.model_fields
            and field.annotation is not anchor.model_fields[name].annotation
        }
        assert added_required or narrowed, (
            f"{model.__name__} neither adds a required field nor narrows one over "
            f"{anchor.__name__}, so a base payload could resolve to it"
        )


# ── Ingestion: parsed document data, validated in JSON mode ──────────────────────────────


def test_python_mode_validation_would_reject_parsed_document_data() -> None:
    """Why ``validate_report`` exists: strict models do not take a ``list`` for a tuple.

    A YAML or JSON parse produces lists, so §0.3's ``PropertyReport.model_validate({...})``
    only works through the JSON-mode path — the same one IR-SPEC §2.5 note 4 forces on the
    IR models.
    """
    data = {"property": "graph-well-formed", "result": "pass", "witness": CLEAN_WITNESS}
    with pytest.raises(ValidationError):
        PropertyReport.model_validate(data)
    assert validate_report(data).result == "pass"


def test_report_round_trips_through_the_serialization_profile() -> None:
    report = validate_report(
        {"property": "graph-well-formed", "result": "fail", "failure": UNREACHABLE_FAILURE}
    )
    assert validate_report(to_data(report)) == report


def test_property_slug_is_closed_to_the_thirteen_catalog_slugs() -> None:
    with pytest.raises(ValidationError):
        validate_report(
            {"property": "graph-wellformed", "result": "pass", "witness": CLEAN_WITNESS}
        )


def test_condition_id_is_closed_to_the_registry() -> None:
    """§0.4's registry is closed, so an unregistered string is not a loadable report either.

    The registry lives in :mod:`gebra.verify.conditions`; what the envelope owes it is that
    ``property_condition`` cannot hold a non-member — here on the failure side, and by the
    same annotation on ``CoFailure`` and ``Advisory``.
    """
    with pytest.raises(ValidationError):
        validate_failure({**UNREACHABLE_FAILURE, "property_condition": "not-a-registry-member"})


def test_remediation_is_display_only_prose() -> None:
    failure = validate_failure(
        {
            "property_condition": "deterministic-llm-seed-unpinned",
            "location": {
                "kind": "node",
                "node": "classify_intent",
                "annotation": "deterministic",
                "form": "bare-boolean",
            },
            "severity": "warning",
            "claim_class": "heuristic",
            "remediation": "Pin the configuration, or drop the claim.",
        }
    )
    assert failure.remediation == "Pin the configuration, or drop the claim."


def test_a_warning_finding_keeps_its_severity_in_the_record() -> None:
    """§0.2: strict promotion changes the gate, never the record — nothing here reads a flag."""
    failure = validate_failure(
        {
            "property_condition": "deterministic-llm-temperature-unpinned",
            "location": {
                "kind": "node",
                "node": "extract_preferences",
                "annotation": "deterministic",
                "seed": 7,
                "temperature": 0.7,
            },
            "severity": "warning",
            "claim_class": "heuristic",
        }
    )
    assert (failure.severity, failure.claim_class) == ("warning", "heuristic")
    assert "strict" not in set(P04Failure.model_fields) | set(PropertyReport.model_fields)


def test_p06_location_rides_a_base_failure() -> None:
    failure = validate_failure(
        {
            "property_condition": "unprotected-effect-in-retry-region",
            "location": {
                "kind": "node",
                "node": "send_sms",
                "cycle": ["send_sms", "verify_delivery"],
                "effect": ["billable", "network"],
            },
            "severity": "error",
            "claim_class": "defensible-a",
        }
    )
    assert type(failure) is Failure
    assert isinstance(failure.location, P06NodeLocation)
