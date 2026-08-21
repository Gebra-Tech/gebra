"""The ``ir_version`` 1.0 model surface, checked field by field against the spec.

Two review bases are encoded here as executable tables:

* :data:`SPEC_SURFACE` — every model of the normative IR-SPEC §2.5 stubs with the exact
  field name, serialization alias, and requiredness the spec fixes. Set equality is
  asserted in both directions, so a missing *or* an added field fails.
* :data:`PD003_APPENDIX_A` — the ratified IR-D2 checklist (PD-003 Appendix A): the nine
  new-in-1.0 slots, six on ``annotations`` and three on ``runtime``, all OPTIONAL.

Nothing here executes a workflow, a node, or a network call (WA-07): the tests read model
metadata and validate literal payloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from gebra.ir import (
    IR_VERSION,
    IR_VERSIONS,
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    DynamicEdge,
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
    lowest_ir_version,
)
from tests.conftest import FIXTURES_DIR

#: model -> ((field name, serialization alias, REQUIRED?), …), transcribed from the
#: normative pydantic-v2 stubs of IR-SPEC §2.5. A field whose alias equals its name is
#: written with the name repeated, so the table reads as the wire surface.
SPEC_SURFACE: dict[type[BaseModel], tuple[tuple[str, str, bool], ...]] = {
    StateField: (
        ("type", "type", True),
        ("reducer", "reducer", False),
        ("optional", "optional", False),
    ),
    IdempotentKey: (("key", "key", True),),
    DeterministicSpec: (
        ("seed", "seed", True),
        ("temperature", "temperature", False),
    ),
    RetryPolicy: (
        ("max_attempts", "max_attempts", True),
        ("retry_on", "retry_on", True),
    ),
    Variant: (
        ("key", "key", True),
        ("measure", "measure", True),
    ),
    Compensation: (("hook", "hook", True),),
    Annotations: (
        ("pure", "pure", False),
        ("effect", "effect", False),
        ("idempotent", "idempotent", False),
        ("deterministic", "deterministic", False),
        ("input", "input", False),
        ("output", "output", False),
        ("source", "source", False),
        ("map", "map", False),
        ("args_schema", "args_schema", False),
        ("retry_policy", "retry_policy", False),
        ("variant", "variant", False),
        ("compensation", "compensation", False),
        ("prompt_digest", "prompt_digest", False),
        ("config_digest", "config_digest", False),
    ),
    Node: (
        ("id", "id", True),
        ("annotations", "annotations", False),
    ),
    NormalEdge: (
        ("kind", "kind", True),
        ("from_", "from", True),
        ("to", "to", True),
        ("condition", "condition", False),
    ),
    ConditionalEdge: (
        ("kind", "kind", True),
        ("from_", "from", True),
        ("condition", "condition", False),
        ("path_map", "path_map", True),
    ),
    SendEdge: (
        ("kind", "kind", True),
        ("from_", "from", True),
        ("to", "to", True),
        ("condition", "condition", False),
    ),
    RecursionLimit: (
        ("value", "value", True),
        ("justification", "justification", True),
    ),
    Interrupts: (
        ("before", "before", False),
        ("after", "after", False),
    ),
    Checkpointer: (("present", "present", True),),
    Runtime: (
        ("recursion_limit", "recursion_limit", False),
        ("interrupts", "interrupts", False),
        ("checkpointer", "checkpointer", False),
    ),
    WorkflowIR: (
        ("ir_version", "ir_version", True),
        ("entry", "entry", True),
        ("finish", "finish", True),
        ("state", "state", False),
        ("nodes", "nodes", True),
        ("edges", "edges", True),
        ("runtime", "runtime", False),
    ),
}

#: The ratified IR-D2 checklist — PD-003 Appendix A, nine new-in-1.0 slots:
#: (slot, holder model, the model type the slot resolves to, IR-SPEC section).
PD003_APPENDIX_A: tuple[tuple[str, type[BaseModel], type[Any] | None, str], ...] = (
    ("args_schema", Annotations, None, "§3.1"),  # a JSON Schema object, held as a dict
    ("retry_policy", Annotations, RetryPolicy, "§3.2"),
    ("variant", Annotations, Variant, "§3.3"),
    ("compensation", Annotations, Compensation, "§3.4"),
    ("prompt_digest", Annotations, None, "§3.6"),  # "sha256:<hex>" string
    ("config_digest", Annotations, None, "§3.6"),  # "sha256:<hex>" string
    ("recursion_limit", Runtime, RecursionLimit, "§3.5"),
    ("interrupts", Runtime, Interrupts, "§3.7"),
    ("checkpointer", Runtime, Checkpointer, "§3.7"),
)

#: IR-SPEC §2.5 note 6 — the members that carry no model default, so that
#: omit-normalization can never strip them.
REQUIRED_TOP_LEVEL = ("ir_version", "entry", "finish", "nodes", "edges")


#: Parametrize ids for the surface table, in the spec's own declaration order.
SPEC_SURFACE_IDS = [model.__name__ for model in SPEC_SURFACE]


@pytest.mark.parametrize(("model", "fields"), SPEC_SURFACE.items(), ids=SPEC_SURFACE_IDS)
def test_field_names_aliases_and_requiredness_match_the_spec_stubs(
    model: type[BaseModel], fields: tuple[tuple[str, str, bool], ...]
) -> None:
    """Every §2.5 field is present, with the alias and requiredness the spec fixes."""
    assert set(model.model_fields) == {name for name, _, _ in fields}, (
        f"{model.__name__} field set diverges from IR-SPEC §2.5"
    )
    for name, alias, required in fields:
        info = model.model_fields[name]
        effective_alias = info.serialization_alias or info.alias or name
        assert effective_alias == alias, f"{model.__name__}.{name} serializes as {effective_alias}"
        assert info.is_required() is required, f"{model.__name__}.{name} requiredness diverges"


def test_workflow_ir_carries_exactly_the_seven_top_level_fields() -> None:
    """IR-SPEC §2.1 — seven fields, in the spec's own order."""
    assert tuple(WorkflowIR.model_fields) == (
        "ir_version",
        "entry",
        "finish",
        "state",
        "nodes",
        "edges",
        "runtime",
    )


@pytest.mark.parametrize("name", REQUIRED_TOP_LEVEL)
def test_required_members_carry_no_default(name: str) -> None:
    """IR-SPEC §2.5 note 6 — required members have no model default."""
    info = WorkflowIR.model_fields[name]
    assert info.is_required()
    assert info.default is PydanticUndefined
    assert info.default_factory is None


@pytest.mark.parametrize(
    ("slot", "holder", "slot_type", "section"),
    PD003_APPENDIX_A,
    ids=[f"{holder.__name__}.{slot}" for slot, holder, _, _ in PD003_APPENDIX_A],
)
def test_pd003_appendix_a_slot_present_and_optional(
    slot: str, holder: type[BaseModel], slot_type: type[Any] | None, section: str
) -> None:
    """PD-003 Appendix A — each of the nine new-in-1.0 slots, in its ratified place."""
    assert slot in holder.model_fields, f"{holder.__name__}.{slot} missing ({section})"
    info = holder.model_fields[slot]
    assert not info.is_required(), f"{holder.__name__}.{slot} must be OPTIONAL (DEC-09)"
    assert type(None) in get_args(info.annotation), f"{holder.__name__}.{slot} must admit absence"
    if slot_type is not None:
        assert slot_type in get_args(info.annotation), (
            f"{holder.__name__}.{slot} does not resolve to {slot_type.__name__} ({section})"
        )


def test_pd003_slot_count_is_nine_six_annotation_three_runtime() -> None:
    """PD-003 pins the count at nine: six annotation slots plus three runtime sub-slots."""
    on_annotations = [slot for slot, holder, _, _ in PD003_APPENDIX_A if holder is Annotations]
    on_runtime = [slot for slot, holder, _, _ in PD003_APPENDIX_A if holder is Runtime]
    assert (len(on_annotations), len(on_runtime)) == (6, 3)
    assert set(on_runtime) == set(Runtime.model_fields), "runtime holds exactly its three sub-slots"


def test_the_two_digest_slots_are_independent_fields() -> None:
    """PD-003's ruling: ``prompt_digest`` and ``config_digest`` are two model slots, not one."""
    digest = "sha256:" + "0" * 64
    annotations = Annotations.model_validate({"prompt_digest": digest})
    assert annotations.prompt_digest == digest
    assert annotations.config_digest is None


@pytest.mark.parametrize("model", SPEC_SURFACE, ids=SPEC_SURFACE_IDS)
def test_every_model_sits_on_the_frozen_base(model: type[BaseModel]) -> None:
    """A6 PC-1/PC-3 — one shared base carrying frozen / extra=forbid / strict."""
    assert issubclass(model, IRModel)
    assert model.model_config["frozen"] is True
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["strict"] is True
    assert model.model_config["populate_by_name"] is True


def _ir_blocks() -> list[tuple[str, dict[str, Any]]]:
    """Every IR payload embedded in the vendored fixture corpus, as (label, block)."""
    blocks: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(Path(FIXTURES_DIR).rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        # Pure data load — the corpus is never executed, and nothing here imports it.
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if isinstance(block, dict):
                blocks.append((f"{path.relative_to(FIXTURES_DIR)}::{key}", block))
    return blocks


def test_every_vendored_corpus_ir_payload_validates_against_the_model() -> None:
    """IR-SPEC §1.3 — the fixture corpus is the document-conformance surface.

    Corroboration rather than a card acceptance box: it is the sharpest available check
    that the model surface matches the fixture-proven one it was hardened from. JSON-mode
    validation is the §2.5 note 4 ingestion path (arrays validate into tuples there).
    """
    blocks = _ir_blocks()
    assert blocks, f"no IR payloads found under {FIXTURES_DIR}"
    failures: list[str] = []
    for label, block in blocks:
        try:
            payload = json.dumps(block)
        except TypeError as exc:  # a YAML scalar with no JSON form, e.g. an unquoted date
            failures.append(f"{label}: not JSON-serializable ({exc})")
            continue
        try:
            WorkflowIR.model_validate_json(payload)
        except ValidationError as exc:
            failures.append(f"{label}: {exc.errors()[0]['type']} at {exc.errors()[0]['loc']}")
    assert not failures, "corpus payloads rejected by the IR 1.0 model:\n" + "\n".join(failures)


def test_semantic_cross_field_obligations_are_left_to_the_validators() -> None:
    """§2.3's "``idempotent.key`` MUST appear in ``input``" is not model validity.

    Two vendored negative fixtures (``mixed/06-irreversible-cycle-idempotency-key-not-read``
    and ``retry-coherence/negative-02-email-dedup-key-not-declared-read``) encode exactly
    that violation and expect a validator to report it — so the payload has to load first.
    """
    annotations = Annotations.model_validate(
        {"idempotent": {"key": "refund_ref"}, "input": ("order_id", "amount")}
    )
    assert isinstance(annotations.idempotent, IdempotentKey)
    assert annotations.input is not None and annotations.idempotent.key not in annotations.input


def test_state_admits_both_surface_forms() -> None:
    """IR-SPEC §2.2 — bare type-name string or the object form, in one mapping."""
    ir = WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": "a",
                "finish": "a",
                "state": {"request": "str", "notes": {"type": "list", "reducer": "operator.add"}},
                "nodes": [{"id": "a"}],
                "edges": [],
            }
        )
    )
    assert ir.state is not None
    assert ir.state["request"] == "str"
    notes = ir.state["notes"]
    assert isinstance(notes, StateField)
    assert (notes.type, notes.reducer, notes.optional) == ("list", "operator.add", None)


def test_entry_and_finish_admit_the_scalar_and_list_forms() -> None:
    """IR-SPEC §2.1 — a node id, or a list of node ids."""
    payload: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "a",
        "finish": ["a", "b"],
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [],
    }
    ir = WorkflowIR.model_validate_json(json.dumps(payload))
    assert ir.entry == "a"
    assert ir.finish == ("a", "b")


def test_the_empty_list_form_is_admitted_on_both_members() -> None:
    """IR-SPEC §2.1 (ratified — DEC-18) — ``[]`` means no statically known sentinel wiring.

    On ``entry`` it covers the unwired builder and the dynamically-dispatched entry alike;
    on ``finish`` it is what an ordinary router-terminated workflow serializes to, since
    END reachability then rides (m3) ``path_map`` labels rather than an (m2) member. Both
    members stay REQUIRED, so the empty form is authored explicitly.
    """
    ir = WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": [],
                "finish": [],
                "nodes": [{"id": "a"}],
                "edges": [],
            }
        )
    )

    assert ir.entry == ()
    assert ir.finish == ()


def test_the_empty_string_is_not_a_second_encoding_of_the_empty_set() -> None:
    """IR-SPEC §2.1 (ratified — DEC-18) — "a scalar id is non-empty per §5.1".

    The constraint exists because ``[]`` now means the empty set: an admitted ``""`` would
    be a rival encoding of the same fact, and the two digest differently. A one-member list
    holding ``""`` is a different question — an unresolvable *reference*, which P-01 reports
    — so it is deliberately not refused here (see :data:`~gebra.ir.models.NodeReference`).
    """
    payload: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "a",
        "finish": "a",
        "nodes": [{"id": "a"}],
        "edges": [],
    }

    for member in ("entry", "finish"):
        with pytest.raises(ValidationError) as excinfo:
            WorkflowIR.model_validate_json(json.dumps({**payload, member: ""}))
        # Both union branches are reported: too short for the scalar, not a list for the other.
        assert {error["type"] for error in excinfo.value.errors()} == {
            "string_too_short",
            "tuple_type",
        }

    admitted = WorkflowIR.model_validate_json(json.dumps({**payload, "entry": [""]}))
    assert admitted.entry == ("",)


def test_nodes_carries_at_least_one_node() -> None:
    """IR-SPEC §2.1 — ``nodes`` has minItems 1."""
    with pytest.raises(ValidationError) as excinfo:
        WorkflowIR.model_validate_json(
            json.dumps({"ir_version": "1.0", "entry": "a", "finish": "a", "nodes": [], "edges": []})
        )
    assert "too_short" in {error["type"] for error in excinfo.value.errors()}


def test_edges_is_required_and_an_empty_edge_set_is_authored_explicitly() -> None:
    """IR-SPEC §2.5 note 6 — ``edges`` has no default; ``[]`` is a valid authored value."""
    with pytest.raises(ValidationError) as excinfo:
        WorkflowIR.model_validate_json(
            json.dumps({"ir_version": "1.0", "entry": "a", "finish": "a", "nodes": [{"id": "a"}]})
        )
    assert "missing" in {error["type"] for error in excinfo.value.errors()}

    ir = WorkflowIR.model_validate_json(
        json.dumps(
            {"ir_version": "1.0", "entry": "a", "finish": "a", "nodes": [{"id": "a"}], "edges": []}
        )
    )
    assert ir.edges == ()


def test_ir_version_is_pinned_to_the_frozen_values() -> None:
    """IR-SPEC §2.1 — the member is a closed Literal, and ``0.1`` is outside it.

    ``IR_VERSION`` is the **floor** the frozen 1.0 surface fixed (DEC-09) and is still what an
    ordinary document carries; the domain gained ``"1.1"`` at DEC-28 and is pinned by
    :func:`test_the_ir_version_domain_is_the_two_ratified_minors`. What this test holds is that
    the member stays *closed*: a 0.1-era document is a validation error, not a best-effort load.
    """
    assert IR_VERSION == "1.0"
    with pytest.raises(ValidationError) as excinfo:
        WorkflowIR.model_validate_json(
            json.dumps(
                {
                    "ir_version": "0.1",
                    "entry": "a",
                    "finish": "a",
                    "nodes": [{"id": "a"}],
                    "edges": [],
                }
            )
        )
    assert "literal_error" in {error["type"] for error in excinfo.value.errors()}


def test_runtime_slots_round_out_the_graph_level_block() -> None:
    """IR-SPEC §3.5/§3.7 — the three runtime sub-slots load with their declared shapes."""
    runtime = Runtime.model_validate_json(
        json.dumps(
            {
                "recursion_limit": {"value": 25, "justification": "bounded by the retry budget"},
                "interrupts": {"before": ["act"], "after": []},
                "checkpointer": {"present": False},
            }
        )
    )
    assert runtime.recursion_limit == RecursionLimit(
        value=25, justification="bounded by the retry budget"
    )
    assert runtime.interrupts == Interrupts(before=("act",), after=())
    assert runtime.checkpointer is not None and runtime.checkpointer.present is False


def test_recursion_limit_requires_its_justification() -> None:
    """IR-SPEC §3.5 — the witness is ``{value, justification}``, never a bare number.

    The vendored fixture schema (v2.2) requires only ``value``; IR-SPEC §2.5 is the
    normative model surface and hardens ``justification`` to REQUIRED, which is the
    requiredness this model carries. Recorded here because the schema-lockstep check owns
    that divergence.
    """
    with pytest.raises(ValidationError) as excinfo:
        RecursionLimit.model_validate({"value": 25})
    assert [error["type"] for error in excinfo.value.errors()] == ["missing"]


def test_checkpointer_present_is_required_so_false_survives_normalization() -> None:
    """IR-SPEC §3.7 — ``present`` carries no default, so ``{present: false}`` is distinct."""
    assert Checkpointer.model_validate({"present": False}).present is False
    with pytest.raises(ValidationError) as excinfo:
        Checkpointer.model_validate({})
    assert [error["type"] for error in excinfo.value.errors()] == ["missing"]


def test_union_typed_annotation_slots_admit_both_surface_forms() -> None:
    """IR-SPEC §2.3 — ``idempotent`` and ``deterministic`` are bool-or-object."""
    flat = Annotations.model_validate({"idempotent": True, "deterministic": True})
    assert (flat.idempotent, flat.deterministic) == (True, True)

    structured = Annotations.model_validate(
        {"idempotent": {"key": "request"}, "deterministic": {"seed": 7, "temperature": 0.0}}
    )
    assert structured.idempotent == IdempotentKey(key="request")
    assert structured.deterministic == DeterministicSpec(seed=7, temperature=0.0)


def test_all_nine_new_slots_load_together_on_one_workflow() -> None:
    """PD-003 Appendix A end to end: one document carrying every new-in-1.0 slot."""
    prompt_digest = "sha256:" + "a" * 64
    config_digest = "sha256:" + "b" * 64
    ir = WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": "act",
                "finish": "act",
                "nodes": [
                    {
                        "id": "act",
                        "annotations": {
                            "args_schema": {"type": "object"},
                            "retry_policy": {"max_attempts": 3, "retry_on": ["TimeoutError"]},
                            "variant": {"key": "worklist", "measure": "length"},
                            "compensation": {"hook": "release_hold"},
                            "prompt_digest": prompt_digest,
                            "config_digest": config_digest,
                        },
                    }
                ],
                "edges": [],
                "runtime": {
                    "recursion_limit": {"value": 10, "justification": "worklist is bounded"},
                    "interrupts": {"before": ["act"]},
                    "checkpointer": {"present": True},
                },
            }
        )
    )
    annotations = ir.nodes[0].annotations
    assert annotations is not None
    assert annotations.args_schema == {"type": "object"}
    assert annotations.retry_policy == RetryPolicy(max_attempts=3, retry_on=("TimeoutError",))
    assert annotations.variant == Variant(key="worklist", measure="length")
    assert annotations.compensation == Compensation(hook="release_hold")
    assert (annotations.prompt_digest, annotations.config_digest) == (prompt_digest, config_digest)
    assert ir.runtime is not None
    assert ir.runtime.recursion_limit == RecursionLimit(
        value=10, justification="worklist is bounded"
    )
    assert ir.runtime.interrupts == Interrupts(before=("act",))
    assert ir.runtime.checkpointer == Checkpointer(present=True)


def test_retained_annotation_slots_load_with_their_fixture_proven_shapes() -> None:
    """IR-SPEC §2.3 — the eight retained slots, unchanged from the fixture surface."""
    annotations = Annotations.model_validate_json(
        json.dumps(
            {
                "pure": False,
                "effect": ["irreversible", "billable"],
                "idempotent": {"key": "request"},
                "deterministic": {"seed": 0},
                "input": ["request"],
                "output": ["booking_id"],
                "source": "bookings.csv",
                "map": "row_to_booking",
            }
        )
    )
    assert annotations.pure is False
    assert annotations.effect == ("irreversible", "billable")
    assert annotations.input == ("request",)
    assert annotations.output == ("booking_id",)
    assert (annotations.source, annotations.map) == ("bookings.csv", "row_to_booking")


def test_edge_union_members_and_discriminator_are_the_declared_ones() -> None:
    """IR-SPEC §2.4/§2.5 — four kinds, discriminated on the existing ``kind`` member.

    **The exact union-membership pin DEC-28 mandates** ("with ``tests/ir/test_spec_surface.py``'s
    exact union pin … as tripwires"). Set *equality*, both directions: a fifth kind cannot be
    added without a ratified minor, and none of the four can quietly disappear either. The
    per-kind tag check below is the other half — the discriminator's value is what a document
    writes, and it is inside hash scope.
    """
    members, *metadata = get_args(Edge)
    assert set(get_args(members)) == {NormalEdge, ConditionalEdge, SendEdge, DynamicEdge}
    discriminators = {
        getattr(entry, "discriminator", None)
        for entry in metadata
        if getattr(entry, "discriminator", None) is not None
    }
    assert discriminators == {"kind"}
    for model, tag in (
        (NormalEdge, "normal"),
        (ConditionalEdge, "conditional"),
        (SendEdge, "send"),
        (DynamicEdge, "dynamic"),
    ):
        assert get_args(model.model_fields["kind"].annotation) == (tag,)


def test_the_dynamic_kind_carries_neither_a_target_nor_a_path_map() -> None:
    """IR-SPEC §2.4 as amended: "kind ``dynamic`` carries neither ``to`` nor ``path_map``".

    Stated as a field-set equality rather than two absences, so a member added to the kind in
    passing fails here; and the ``extra="forbid"`` consequence PD-041 names is checked in both
    directions, because "there is no way to construct the ambiguous empty-and-present form on
    the new kind either" is the whole reason the kind was preferred to relaxing requiredness.
    """
    assert set(DynamicEdge.model_fields) == {"kind", "from_", "condition"}
    assert DynamicEdge.model_fields["condition"].default is None
    forbidden_members: tuple[dict[str, Any], ...] = (
        {"to": "b"},
        {"path_map": {}},
        {"path_map": {"a": "b"}},
    )
    for forbidden in forbidden_members:
        with pytest.raises(ValidationError):
            DynamicEdge.model_validate({"kind": "dynamic", "from": "a", **forbidden}, by_alias=True)


def test_the_ir_version_domain_is_the_two_ratified_minors() -> None:
    """IR-SPEC §2.5 — ``ir_version: Literal["1.0", "1.1"]`` (1.1 added at DEC-28).

    And §8's stamping policy, which is a property of the emitter rather than of the model: the
    *model* admits either version on a document it is handed, while everything gebra writes goes
    through :func:`~gebra.ir.models.lowest_ir_version`, whose answer is a function of content.
    """
    assert get_args(WorkflowIR.model_fields["ir_version"].annotation) == ("1.0", "1.1")
    assert IR_VERSIONS == ("1.0", "1.1")
    assert lowest_ir_version(()) == "1.0"
    assert lowest_ir_version((NormalEdge(kind="normal", **{"from": "a"}, to="b"),)) == "1.0"
    assert lowest_ir_version((DynamicEdge(kind="dynamic", **{"from": "a"}),)) == "1.1"
    assert (
        lowest_ir_version(
            (
                NormalEdge(kind="normal", **{"from": "a"}, to="b"),
                DynamicEdge(kind="dynamic", **{"from": "b"}),
            )
        )
        == "1.1"
    )
