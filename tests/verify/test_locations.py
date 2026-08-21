"""The §0.3 anchor union and the wedge's concrete location subtypes.

The load-bearing claim of this module is the payload → class table: the envelope carries
concrete subtypes that share their anchor's ``kind``, so resolution runs left to right, and
left to right is only safe while every concrete subtype adds a **required** field and every
model forbids extras. The table below is that safety property, written down.

Nothing here executes a workflow, a node, or a network call (WA-07).
"""

from __future__ import annotations

import json
from typing import Any, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from gebra.verify import (
    START,
    AnyLocation,
    CycleLocation,
    DataflowLocation,
    DeterminismNodeLocation,
    EdgeLocation,
    Location,
    NodeLocation,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
    P06NodeLocation,
    PathLocation,
    SccLocation,
    StateKeyLocation,
    validate_location,
)

ANCHOR_ADAPTER: TypeAdapter[Any] = TypeAdapter(Location)

#: One minimal payload per §0.3 anchor — the six ``kind`` values the vocabulary is closed to.
ANCHOR_PAYLOADS: dict[type[Any], dict[str, Any]] = {
    NodeLocation: {"kind": "node", "node": "act"},
    EdgeLocation: {"kind": "edge", "source": "plan"},
    CycleLocation: {"kind": "cycle", "nodes": ["act", "plan"]},
    SccLocation: {"kind": "scc", "nodes": ["act", "plan"]},
    StateKeyLocation: {"kind": "state-key", "key": "itinerary"},
    PathLocation: {"kind": "path", "nodes": [START, "intake"]},
}

#: One payload per concrete wedge subtype, in the shape its §P-nn.3 contract declares.
CONCRETE_PAYLOADS: dict[type[Any], dict[str, Any]] = {
    P01EdgeLocation: {
        "kind": "edge",
        "source": "review_booking",
        "label": "confirm",
        "undefined_target": "send_confirmatoin",
    },
    P02SccLocation: {
        "kind": "scc",
        "nodes": ["act", "plan", "reflect"],
        "representative_cycle": ["act", "reflect", "plan"],
        "exhaustive": False,
    },
    P02CycleLocation: {
        "kind": "cycle",
        "nodes": ["evaluate_rates", "throttle_check", "fetch_rates"],
        "counter_key": "refresh_count",
        "guard_edge": {"source": "throttle_check", "labels": ["immediate", "delayed"]},
    },
    DataflowLocation: {
        "kind": "state-key",
        "key": "booking_id",
        "node": "send_confirmation",
        "path": [START, "check_availability", "send_confirmation"],
    },
    P06NodeLocation: {
        "kind": "node",
        "node": "book_flight",
        "effect": ["irreversible", "billable"],
        "cycle": ["book_flight", "check_booking"],
    },
    DeterminismNodeLocation: {
        "kind": "node",
        "node": "classify_intent",
        "annotation": "deterministic",
        "form": "bare-boolean",
        "effects": ["network", "external"],
    },
}


@pytest.mark.parametrize(
    ("model", "payload"), ANCHOR_PAYLOADS.items(), ids=lambda a: getattr(a, "__name__", "")
)
def test_anchor_union_resolves_on_kind(model: type[Any], payload: dict[str, Any]) -> None:
    """§0.3's ``Location``: six anchors, discriminated on ``kind`` (A6 PC-2)."""
    assert type(ANCHOR_ADAPTER.validate_json(json.dumps(payload))) is model


@pytest.mark.parametrize(
    ("model", "payload"),
    [*ANCHOR_PAYLOADS.items(), *CONCRETE_PAYLOADS.items()],
    ids=lambda a: getattr(a, "__name__", ""),
)
def test_carriage_union_resolves_to_the_exact_class(
    model: type[Any], payload: dict[str, Any]
) -> None:
    """The payload → class table: no anchor payload drifts into a subtype, or vice versa."""
    assert type(validate_location(payload)) is model


def union_members(alias: Any) -> tuple[type[BaseModel], ...]:
    """The model classes of an envelope carriage union, flattening its nested anchor union.

    Derived from the alias rather than listed, so a member added to the union without a
    payload here cannot slip past the invariant tests below.
    """
    members: list[type[BaseModel]] = []
    for member in get_args(get_args(alias)[0]):
        if isinstance(member, type):
            members.append(member)
        else:  # the nested Annotated[Union[...], Field(discriminator=...)] anchor union
            members.extend(get_args(get_args(member)[0]))
    return tuple(members)


def test_the_payload_table_covers_every_union_member() -> None:
    """Every member of `AnyLocation` is exercised — the guard below has no blind spot."""
    assert set(ANCHOR_PAYLOADS) | set(CONCRETE_PAYLOADS) == set(union_members(AnyLocation))


def test_every_concrete_subtype_adds_a_required_field() -> None:
    """The invariant that makes left-to-right resolution deterministic, checked directly.

    Derived from `AnyLocation` itself: a future §P-nn.3 subtype whose added fields were all
    optional would resolve to its anchor instead, which is the class-sensitivity failure
    `P04Failure` exists to avoid — so the check must see every member, not a curated list.
    """
    members = union_members(AnyLocation)
    subtypes = [model for model in members if model.__mro__[1] in members]
    assert len(subtypes) == len(CONCRETE_PAYLOADS)
    for model in subtypes:
        anchor: type[BaseModel] = model.__mro__[1]
        added_required = {
            name
            for name, field in model.model_fields.items()
            if field.is_required()
            and not (name in anchor.model_fields and anchor.model_fields[name].is_required())
        }
        assert added_required, f"{model.__name__} adds no required field over {anchor.__name__}"
        assert set(CONCRETE_PAYLOADS[model]) >= added_required


def test_anchor_refuses_a_concrete_payload() -> None:
    """``extra="forbid"`` is the other half of the invariant."""
    for payload in CONCRETE_PAYLOADS.values():
        with pytest.raises(ValidationError):
            ANCHOR_ADAPTER.validate_json(json.dumps(payload))


def test_kind_vocabulary_is_closed() -> None:
    with pytest.raises(ValidationError):
        validate_location({"kind": "subgraph", "node": "act"})


# ── The individual contracts each subtype carries ────────────────────────────────────────


def test_p01_edge_location_leaves_the_anchor_target_omitted() -> None:
    """§0.3's dangling-label rule: there is no resolved target to name."""
    location = validate_location(CONCRETE_PAYLOADS[P01EdgeLocation])
    assert isinstance(location, P01EdgeLocation)
    assert location.target is None
    assert location.undefined_target == "send_confirmatoin"


def test_p02_scc_location_pins_one_representative_cycle() -> None:
    location = validate_location(CONCRETE_PAYLOADS[P02SccLocation])
    assert isinstance(location, P02SccLocation)
    assert location.exhaustive is False
    assert location.blanket_only is None  # the corpus omits it; strict mode sets it


def test_p02_scc_location_refuses_an_exhaustive_claim() -> None:
    """``exhaustive`` is fixed at false: one representative cycle per residual SCC."""
    with pytest.raises(ValidationError):
        validate_location({**CONCRETE_PAYLOADS[P02SccLocation], "exhaustive": True})


def test_p02_scc_location_carries_the_strict_mode_flag() -> None:
    """T-W-SPEC §6.1: strict promotion reuses the condition ID and distinguishes on this."""
    location = validate_location({**CONCRETE_PAYLOADS[P02SccLocation], "blanket_only": True})
    assert isinstance(location, P02SccLocation)
    assert location.blanket_only is True


def test_dataflow_location_requires_the_reading_node() -> None:
    """The anchor declares ``node`` optional; a dataflow finding always names it (§4.3)."""
    without_node = {
        key: value for key, value in CONCRETE_PAYLOADS[DataflowLocation].items() if key != "node"
    }
    with pytest.raises(ValidationError):
        validate_location(without_node)


def test_dataflow_path_carries_the_start_sentinel() -> None:
    location = validate_location(CONCRETE_PAYLOADS[DataflowLocation])
    assert isinstance(location, DataflowLocation)
    assert location.path[0] == START


def test_p06_location_carries_the_full_declared_effect_set() -> None:
    """Non-trigger tags ride along as evidence; they create no P-06 obligation (§6.3)."""
    location = validate_location(
        {"kind": "node", "node": "send_sms", "effect": ["billable", "network"]}
    )
    assert isinstance(location, P06NodeLocation)
    assert location.effect == ("billable", "network")


def test_p06_location_records_the_keyless_idempotency_evidence() -> None:
    location = validate_location(
        {
            "kind": "node",
            "node": "charge_deposit",
            "effect": ["irreversible", "billable"],
            "idempotent": "keyless",
        }
    )
    assert isinstance(location, P06NodeLocation)
    assert location.idempotent == "keyless"


def test_determinism_location_is_evidence_not_prose() -> None:
    location = validate_location(
        {
            "kind": "node",
            "node": "extract_preferences",
            "annotation": "deterministic",
            "seed": 7,
            "temperature": 0.7,
        }
    )
    assert isinstance(location, DeterminismNodeLocation)
    assert (location.seed, location.temperature) == (7, 0.7)


def test_determinism_location_accepts_an_integral_temperature() -> None:
    """JSON has one number type: ``temperature: 0`` is the pinned-cold case, not a type error."""
    location = validate_location(
        {"kind": "node", "node": "classify", "annotation": "deterministic", "temperature": 0}
    )
    assert isinstance(location, DeterminismNodeLocation)
    assert location.temperature == 0.0


def test_non_wedge_evidence_keys_have_no_subtype_yet() -> None:
    """P-07/P-09/P-12 location shapes land with their own sections (§0.4 RESERVED tier)."""
    with pytest.raises(ValidationError):
        validate_location({"kind": "node", "node": "send_sms", "cycle": ["send_sms", "verify"]})
