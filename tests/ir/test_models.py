"""Behaviour of the ``ir_version`` 1.0 models: the A6 conventions and edge dispatch.

Where :mod:`tests.ir.test_spec_surface` checks *what the fields are*, this module checks
*how the models behave*: the frozen / ``extra="forbid"`` / strict base (A6 PC-1…PC-3), the
``model_construct()`` ban (PC-6), alias serialization (PC-4), and the IR-SPEC §2.5 note 1
rule that a tagless edge object loads as kind ``normal``.

Nothing here executes a workflow, a node, or a network call (WA-07).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from gebra.ir import (
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    Edge,
    IdempotentKey,
    Interrupts,
    IRModel,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    SendEdge,
    StateField,
    Variant,
    WorkflowIR,
)

EDGE_ADAPTER: TypeAdapter[Any] = TypeAdapter(Edge)

#: One minimally-valid payload per model, in Python-mode form (tuples, not lists — PC-2
#: plus strict mode). Every model of the §2.5 stubs appears exactly once.
MINIMAL_PAYLOADS: dict[type[IRModel], dict[str, Any]] = {
    StateField: {"type": "str"},
    IdempotentKey: {"key": "request"},
    DeterministicSpec: {"seed": 7},
    RetryPolicy: {"max_attempts": 3, "retry_on": ("TimeoutError",)},
    Variant: {"key": "worklist", "measure": "length"},
    Compensation: {"hook": "release_hold"},
    Annotations: {"pure": True},
    Node: {"id": "act"},
    NormalEdge: {"kind": "normal", "from": "plan", "to": "act"},
    ConditionalEdge: {"kind": "conditional", "from": "act", "path_map": {"done": "publish"}},
    SendEdge: {"kind": "send", "from": "plan", "to": "act"},
    RecursionLimit: {"value": 25, "justification": "bounded by the retry budget"},
    Interrupts: {"before": ("act",)},
    Checkpointer: {"present": True},
    Runtime: {"checkpointer": {"present": True}},
    WorkflowIR: {
        "ir_version": "1.0",
        "entry": "act",
        "finish": "act",
        "nodes": ({"id": "act"},),
        "edges": (),
    },
}

MODEL_IDS = [model.__name__ for model in MINIMAL_PAYLOADS]


@pytest.mark.parametrize(("model", "payload"), MINIMAL_PAYLOADS.items(), ids=MODEL_IDS)
def test_unknown_member_is_rejected(model: type[IRModel], payload: dict[str, Any]) -> None:
    """A6 PC-3 — ``extra="forbid"``: unknown content is an error, never silently dropped."""
    model.model_validate(payload)  # the payload itself is valid
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate({**payload, "not_a_slot": "x"})
    errors = excinfo.value.errors()
    assert [error["type"] for error in errors] == ["extra_forbidden"]
    assert errors[0]["loc"] == ("not_a_slot",)


@pytest.mark.parametrize(("model", "payload"), MINIMAL_PAYLOADS.items(), ids=MODEL_IDS)
def test_models_are_frozen(model: type[IRModel], payload: dict[str, Any]) -> None:
    """A6 PC-1 — a validated model is immutable; assignment and deletion both fail."""
    instance = model.model_validate(payload)
    field_name = next(iter(type(instance).model_fields))
    with pytest.raises(ValidationError) as excinfo:
        setattr(instance, field_name, None)
    assert [error["type"] for error in excinfo.value.errors()] == ["frozen_instance"]
    with pytest.raises(ValidationError):
        delattr(instance, field_name)


@pytest.mark.parametrize(("model", "payload"), MINIMAL_PAYLOADS.items(), ids=MODEL_IDS)
def test_model_construct_is_banned(model: type[IRModel], payload: dict[str, Any]) -> None:
    """A6 PC-6 — the validation-skipping constructor is refused, on every model."""
    with pytest.raises(NotImplementedError) as excinfo:
        model.model_construct(**payload)
    assert "model_construct() is banned" in str(excinfo.value)


def test_validation_paths_still_work_under_the_construct_ban() -> None:
    """The PC-6 override must not disturb the paths that do validate."""
    node = Node.model_validate({"id": "act"})
    assert Node.model_validate_json('{"id": "act"}') == node
    assert node.model_copy() == node
    assert node.model_copy(update={"id": "plan"}).id == "plan"
    assert node.model_dump() == {"id": "act", "annotations": None}
    assert TypeAdapter(Node).validate_python({"id": "act"}) == node


def test_frozen_models_are_equal_by_value() -> None:
    """A6 PC-1 — frozen models compare by field value, which is what golden tests rest on."""
    assert Node.model_validate({"id": "act"}) == Node(id="act")
    assert Node.model_validate({"id": "act"}) != Node(id="plan")


def test_id_shaped_models_hash_and_dict_carrying_ones_do_not() -> None:
    """IR-SPEC §2.5 note 3 — the hashability caveat, stated as behaviour."""
    assert len({Node(id="act"), Node(id="act"), Node(id="plan")}) == 2
    assert hash(Compensation(hook="release_hold")) == hash(Compensation(hook="release_hold"))
    with pytest.raises(TypeError):
        hash(Annotations(args_schema={"type": "object"}))


# ── IR-SPEC §2.5 note 1 — default-`kind` normalization ────────────────────────────────


def test_tagless_edge_loads_as_kind_normal_in_json_mode() -> None:
    """A tagless edge object loads as kind ``normal`` — the §2.4 surface default."""
    ir = WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": "plan",
                "finish": "act",
                "nodes": [{"id": "plan"}, {"id": "act"}],
                "edges": [{"from": "plan", "to": "act"}],
            }
        )
    )
    edge = ir.edges[0]
    assert isinstance(edge, NormalEdge)
    assert edge.kind == "normal"
    assert (edge.from_, edge.to) == ("plan", "act")


def test_tagless_edge_loads_as_kind_normal_in_python_mode() -> None:
    """The same injection applies to Python-mode validation."""
    ir = WorkflowIR.model_validate(
        {
            "ir_version": "1.0",
            "entry": "plan",
            "finish": "act",
            "nodes": ({"id": "plan"}, {"id": "act"}),
            "edges": ({"from": "plan", "to": "act"},),
        }
    )
    assert isinstance(ir.edges[0], NormalEdge)
    assert ir.edges[0].kind == "normal"


def test_kind_injection_rides_on_the_edge_type_itself() -> None:
    """Validating an edge on its own admits the tagless form too."""
    edge = EDGE_ADAPTER.validate_python({"from": "plan", "to": "act"})
    assert isinstance(edge, NormalEdge)
    assert edge.kind == "normal"


def test_an_explicit_null_kind_is_not_tagless() -> None:
    """``kind: null`` stays an error: §2.5 note 1 injects into *tagless* objects only.

    §2.4 closes the member's domain to ``normal|conditional|send``, and §6.3's
    absent ≡ null ≡ default rule is canonicalization — applied to an already-parsed model,
    not a widening of what §2 admits.
    """
    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python({"from": "plan", "to": "act", "kind": None})
    assert [error["type"] for error in excinfo.value.errors()] == ["union_tag_invalid"]


def test_tagged_edges_dispatch_to_their_own_models() -> None:
    """IR-SPEC §2.4 — the union discriminates on the existing ``kind`` member."""
    normal = EDGE_ADAPTER.validate_python({"kind": "normal", "from": "plan", "to": "act"})
    conditional = EDGE_ADAPTER.validate_python(
        {
            "kind": "conditional",
            "from": "act",
            "condition": "retry_count < 3",
            "path_map": {"again": "act", "done": "END"},
        }
    )
    send = EDGE_ADAPTER.validate_python({"kind": "send", "from": "plan", "to": "act"})
    assert isinstance(normal, NormalEdge)
    assert isinstance(conditional, ConditionalEdge)
    assert isinstance(send, SendEdge)
    assert conditional.path_map == {"again": "act", "done": "END"}


def test_an_unknown_kind_is_reported_as_a_bad_tag() -> None:
    """An unrecognized ``kind`` fails against the declared tag set, not as a mystery union."""
    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python({"kind": "loop", "from": "plan", "to": "act"})
    error = excinfo.value.errors()[0]
    assert error["type"] == "union_tag_invalid"
    assert "'normal', 'conditional', 'send'" in error["msg"]


def test_edge_kind_requiredness_follows_the_kind() -> None:
    """IR-SPEC §2.4 — ``to`` for normal/send; ``path_map`` (and no ``to``) for conditional."""
    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python({"from": "plan"})
    assert [error["type"] for error in excinfo.value.errors()] == ["missing"]

    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python({"kind": "send", "from": "plan"})
    assert [error["type"] for error in excinfo.value.errors()] == ["missing"]

    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python({"kind": "conditional", "from": "act"})
    assert [error["type"] for error in excinfo.value.errors()] == ["missing"]

    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python(
            {"kind": "conditional", "from": "act", "path_map": {"done": "act"}, "to": "act"}
        )
    assert [error["type"] for error in excinfo.value.errors()] == ["extra_forbidden"]


def test_a_prebuilt_edge_model_passes_through_the_injection_untouched() -> None:
    """The before-validator only tags mappings; anything else is pydantic's to judge."""
    edge = NormalEdge.model_validate({"kind": "normal", "from": "plan", "to": "act"})
    assert EDGE_ADAPTER.validate_python(edge) == edge
    with pytest.raises(ValidationError) as excinfo:
        EDGE_ADAPTER.validate_python("plan -> act")
    assert [error["type"] for error in excinfo.value.errors()] == ["model_attributes_type"]


# ── A6 PC-2/PC-3/PC-4 — tuples, strictness, alias output ──────────────────────────────


def test_repeated_members_are_tuples() -> None:
    """A6 PC-2 — repeated members validate into tuples, so the models stay immutable."""
    annotations = Annotations.model_validate_json('{"effect": ["billable"], "input": ["request"]}')
    assert annotations.effect == ("billable",)
    assert isinstance(annotations.input, tuple)


def test_strict_mode_refuses_cross_type_coercion() -> None:
    """A6 PC-3 — no silent coercion: a string is not a bool, a bool is not an int."""
    with pytest.raises(ValidationError) as excinfo:
        Checkpointer.model_validate({"present": "true"})
    assert [error["type"] for error in excinfo.value.errors()] == ["bool_type"]

    with pytest.raises(ValidationError) as excinfo:
        DeterministicSpec.model_validate({"seed": True})
    assert [error["type"] for error in excinfo.value.errors()] == ["int_type"]

    with pytest.raises(ValidationError) as excinfo:
        RecursionLimit.model_validate({"value": "25", "justification": "j"})
    assert [error["type"] for error in excinfo.value.errors()] == ["int_type"]


def test_json_mode_is_the_ingestion_path_for_sequences() -> None:
    """IR-SPEC §2.5 note 4 — a JSON array validates into a tuple in JSON mode only."""
    from_json = RetryPolicy.model_validate_json('{"max_attempts": 3, "retry_on": ["TimeoutError"]}')
    assert from_json.retry_on == ("TimeoutError",)
    with pytest.raises(ValidationError) as excinfo:
        RetryPolicy.model_validate({"max_attempts": 3, "retry_on": ["TimeoutError"]})
    assert [error["type"] for error in excinfo.value.errors()] == ["tuple_type"]


def test_the_from_alias_is_the_wire_name() -> None:
    """IR-SPEC §2.5 note 2 — the field is ``from_``; the surface name is ``from``."""
    edge = EDGE_ADAPTER.validate_python({"kind": "normal", "from": "plan", "to": "act"})
    assert edge.from_ == "plan"
    assert edge.model_dump(by_alias=True) == {
        "kind": "normal",
        "from": "plan",
        "to": "act",
        "condition": None,
    }
    assert json.loads(edge.model_dump_json(by_alias=True, exclude_none=True)) == {
        "kind": "normal",
        "from": "plan",
        "to": "act",
    }


def test_the_python_field_name_is_usable_too() -> None:
    """``populate_by_name=True`` — the Python name ``from_`` populates the field as well.

    A payload uses the wire name; this is the escape hatch for code that holds the field
    name, since ``from`` cannot be typed as a Python keyword argument.
    """
    by_python_name = NormalEdge.model_validate({"kind": "normal", "from_": "plan", "to": "act"})
    assert by_python_name.from_ == "plan"
    assert by_python_name == NormalEdge.model_validate(
        {"kind": "normal", "from": "plan", "to": "act"}
    )


def test_node_ids_are_admitted_as_written() -> None:
    """The §5 grammar is not model validity — id-shaped strings load as authored."""
    assert Node(id="research/tools/web_search").id == "research/tools/web_search"
    assert Node(id="%seq[0]").id == "%seq[0]"


def test_an_empty_annotations_object_is_a_valid_contract() -> None:
    """Every annotation slot is optional, so ``annotations: {}`` is a legal node contract."""
    node = Node.model_validate({"id": "act", "annotations": {}})
    assert node.annotations == Annotations()


def test_runtime_sub_slots_are_independently_optional() -> None:
    """IR-SPEC §3.5/§3.7 — a runtime block may carry any subset of its three slots."""
    runtime = Runtime.model_validate({"interrupts": {"after": ("act",)}})
    assert runtime.recursion_limit is None
    assert runtime.checkpointer is None
    assert runtime.interrupts == Interrupts(after=("act",))


def test_variant_and_retry_policy_reject_partial_objects() -> None:
    """IR-SPEC §3.2/§3.3 — both members of each object are REQUIRED within it."""
    with pytest.raises(ValidationError):
        Variant.model_validate({"key": "worklist"})
    with pytest.raises(ValidationError):
        RetryPolicy.model_validate({"max_attempts": 3})


def test_state_field_object_form_requires_its_type() -> None:
    """IR-SPEC §2.2 — the object form always names a type."""
    assert StateField.model_validate({"type": "list", "reducer": "operator.add"}).type == "list"
    with pytest.raises(ValidationError):
        StateField.model_validate({"reducer": "operator.add"})


def test_idempotent_key_object_form_requires_its_key() -> None:
    """IR-SPEC §2.3 — the object form pins a key."""
    assert IdempotentKey.model_validate({"key": "request"}).key == "request"
    with pytest.raises(ValidationError):
        IdempotentKey.model_validate({})
