"""Behaviour of the envelope base: the A6 conventions, the sentinels, comparison, dumping.

Where :mod:`tests.verify.test_locations` and :mod:`tests.verify.test_witnesses` check *what
the models are*, this module checks *how they behave* — the frozen / ``extra="forbid"`` /
strict / hashable base (PROPERTY-CATALOG-SPEC §0.3, A6 PC-1/PC-3), the ``model_construct()``
ban, the START/END display-sentinel convention, the set-comparison rule, and the PC-4
serialization profile.

Nothing here executes a workflow, a node, or a network call (WA-07).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from gebra.verify import (
    END,
    START,
    DataflowCoverage,
    DataflowWitness,
    EffectSafetyWitness,
    NodeLocation,
    P06EffectRecord,
    P06NodeLocation,
    PathLocation,
    ReportModel,
    SetCompared,
    from_display,
    models_equivalent,
    set_compared_fields,
    to_data,
    to_display,
    to_json,
)

# ── A6 PC-1/PC-3: frozen, extra="forbid", strict, hashable ───────────────────────────────


def test_models_are_frozen() -> None:
    location = NodeLocation(kind="node", node="act")
    with pytest.raises(ValidationError):
        location.node = "plan"


def test_unknown_member_is_refused() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        NodeLocation.model_validate_json('{"kind": "node", "node": "act", "colour": "red"}')


def test_strict_mode_refuses_coercion() -> None:
    """No value is coerced across types — a stringified node id is not a node id."""
    with pytest.raises(ValidationError):
        NodeLocation.model_validate_json('{"kind": "node", "node": 7}')


def test_envelope_models_are_hashable() -> None:
    """Unlike the IR models, no envelope model carries a dict — so a witness is a set member.

    This is what makes set-comparison (§0.3) possible at all, and what lets a consumer
    deduplicate findings without serializing them first.
    """
    first = NodeLocation(kind="node", node="act")
    second = NodeLocation(kind="node", node="act")
    assert {first, second} == {first}


def test_model_construct_is_banned() -> None:
    """A6 PC-6: skipping validation would skip the invariants the envelope exists to carry."""
    with pytest.raises(NotImplementedError, match="witness-XOR-failure"):
        NodeLocation.model_construct(kind="node", node="act")


def test_value_equality_is_field_equality() -> None:
    assert NodeLocation(kind="node", node="act") == NodeLocation(kind="node", node="act")
    assert NodeLocation(kind="node", node="act") != NodeLocation(kind="node", node="plan")


# ── §0.3: the START/END display-sentinel convention ──────────────────────────────────────


def test_display_sentinels_are_the_corpus_spelling() -> None:
    assert (START, END) == ("START", "END")


@pytest.mark.parametrize(
    ("graph_side", "report_side"),
    [("__start__", START), ("__end__", END), ("act", "act"), ("sub/__inner__", "sub/__inner__")],
)
def test_projection_is_exactly_the_two_sentinels(graph_side: str, report_side: str) -> None:
    """§0.3 fixes the projection as ``__start__ ↦ "START"``, ``__end__ ↦ "END"``, no more."""
    assert to_display(graph_side) == report_side
    assert from_display(report_side) == graph_side


@pytest.mark.parametrize("reserved", ["__start__", "__end__"])
def test_reserved_spellings_never_reach_a_report(reserved: str) -> None:
    """§0.3: the reserved-segment spellings never appear in a serialized report.

    The envelope's node-id annotation *is* the frozen IR-SPEC §5 grammar, which refuses the
    reserved segments — so the rule is a validation error rather than a convention a
    validator could forget. A validator holding a sentinel projects it first.
    """
    with pytest.raises(ValidationError):
        NodeLocation.model_validate_json(json.dumps({"kind": "node", "node": reserved}))
    with pytest.raises(ValidationError):
        PathLocation.model_validate_json(json.dumps({"kind": "path", "nodes": [reserved]}))

    projected = PathLocation.model_validate_json(
        json.dumps({"kind": "path", "nodes": [to_display(reserved)]})
    )
    assert projected.nodes == (to_display(reserved),)


def test_display_sentinels_are_admitted_where_the_spec_puts_them() -> None:
    """``PathLocation.nodes`` may include the sentinels (§0.3)."""
    path = PathLocation.model_validate_json(
        json.dumps({"kind": "path", "nodes": [START, "intake", END]})
    )
    assert path.nodes == (START, "intake", END)


# ── §0.3: comparison is model equality, set-comparison where order is not normative ──────


def test_set_compared_fields_are_exactly_the_marked_ones() -> None:
    """Marked only where a spec passage says the order is not normative — nowhere else."""
    assert set_compared_fields(DataflowWitness) == {"coverage"}
    assert set_compared_fields(P06NodeLocation) == {"effect"}
    assert set_compared_fields(P06EffectRecord) == {"effect"}
    assert set_compared_fields(NodeLocation) == frozenset()
    assert set_compared_fields(EffectSafetyWitness) == frozenset()


def test_every_mark_carries_its_citation() -> None:
    for model in (DataflowWitness, P06NodeLocation, P06EffectRecord):
        for name in set_compared_fields(model):
            marks = [
                mark for mark in model.model_fields[name].metadata if isinstance(mark, SetCompared)
            ]
            assert marks and all("PROPERTY-CATALOG-SPEC" in mark.reason for mark in marks)


def _coverage(node: str, key: str, *writers: str) -> DataflowCoverage:
    return DataflowCoverage(node=node, key=key, satisfied_by=writers)


def test_marked_field_compares_as_a_multiset() -> None:
    one = DataflowWitness(
        kind="dataflow",
        coverage=(_coverage("a", "x", START), _coverage("b", "y", "a")),
    )
    reordered = DataflowWitness(
        kind="dataflow",
        coverage=(_coverage("b", "y", "a"), _coverage("a", "x", START)),
    )
    assert one != reordered  # `==` stays the stricter comparison
    assert models_equivalent(one, reordered)


def test_multiset_comparison_still_counts_duplicates() -> None:
    entry = _coverage("a", "x", START)
    assert not models_equivalent(
        DataflowWitness(kind="dataflow", coverage=(entry, entry)),
        DataflowWitness(kind="dataflow", coverage=(entry,)),
    )


def test_unmarked_order_is_normative() -> None:
    """Each property section fixes its own finding order; only marked fields are relaxed."""
    first = P06EffectRecord(
        node="a", effect=("billable",), region="acyclic", protection="none_required"
    )
    second = P06EffectRecord(
        node="b", effect=("billable",), region="acyclic", protection="none_required"
    )
    ordered = EffectSafetyWitness(kind="effect-safety", cycles=(), effects=(first, second))
    swapped = EffectSafetyWitness(kind="effect-safety", cycles=(), effects=(second, first))
    assert not models_equivalent(ordered, swapped)


def test_marked_field_nested_in_an_unmarked_one_is_still_relaxed() -> None:
    ordered = EffectSafetyWitness(
        kind="effect-safety",
        cycles=(),
        effects=(
            P06EffectRecord(
                node="a",
                effect=("billable", "network"),
                region="acyclic",
                protection="none_required",
            ),
        ),
    )
    swapped = EffectSafetyWitness(
        kind="effect-safety",
        cycles=(),
        effects=(
            P06EffectRecord(
                node="a",
                effect=("network", "billable"),
                region="acyclic",
                protection="none_required",
            ),
        ),
    )
    assert ordered != swapped
    assert models_equivalent(ordered, swapped)


def test_models_of_different_classes_are_never_equivalent() -> None:
    assert not models_equivalent(NodeLocation(kind="node", node="a"), "a")
    assert not models_equivalent("a", NodeLocation(kind="node", node="a"))
    assert not models_equivalent(
        NodeLocation(kind="node", node="a"),
        P06NodeLocation(kind="node", node="a", effect=()),
    )


def test_scalars_compare_by_type_and_value() -> None:
    assert models_equivalent(1, 1)
    assert not models_equivalent(1, True)
    assert models_equivalent(None, None)
    assert models_equivalent(("a", "b"), ("a", "b"))
    assert not models_equivalent(("a", "b"), ("b", "a"))


# ── A6 PC-4: the serialization profile ───────────────────────────────────────────────────


def test_dump_drops_none_and_keeps_definition_order() -> None:
    record = P06EffectRecord(
        node="book_hotel",
        effect=("billable",),
        region="cycle",
        cycle=("book_hotel", "verify_hold"),
        protection="idempotency_key",
        key="hotel_offer_id",
    )
    data = to_data(record)
    assert list(data) == ["node", "effect", "region", "cycle", "protection", "key"]
    assert "hook" not in data  # unset optionals are omitted, not serialized as null


def test_dump_json_is_the_same_profile_as_text() -> None:
    location = P06NodeLocation(kind="node", node="charge_deposit", effect=("irreversible",))
    assert json.loads(to_json(location)) == to_data(location)
    assert to_json(location, indent=None) == json.dumps(to_data(location), separators=(", ", ": "))


def test_dump_is_json_data_only() -> None:
    """Tuples become arrays; nothing exotic survives — the report is a JSON document."""
    witness = DataflowWitness(kind="dataflow", coverage=(_coverage("a", "x", START),))
    data: Any = to_data(witness)
    assert data == {
        "kind": "dataflow",
        "coverage": [{"node": "a", "key": "x", "satisfied_by": [START]}],
    }


# ── Hermeticity: the envelope is IR-and-pydantic only ────────────────────────────────────


def test_importing_the_envelope_pulls_in_no_langgraph() -> None:
    """The validator lane consumes serialized IR plus these models, never langgraph.

    Checked in a fresh interpreter because another test in this session may already have
    imported langgraph for its own reasons. Two claims, separately enforced (WA-07):
    execution-substrate packages stay out of the import closure entirely, and no socket
    is ever CREATED or RESOLVED while importing. Stdlib module PRESENCE is deliberately
    not asserted: ``socket`` enters the closure through version-dependent stdlib
    internals with no network involved (on CPython 3.10 the chain is
    ``pydantic.plugin._loader -> importlib.metadata -> email.message -> email.utils ->
    socket``; traced at VAL-13 after the presence check turned CI red), so asserting
    absence tests interpreter internals, while the tripwires catch exactly what WA-07
    forbids. Attempts are recorded before raising, so a swallowed exception still fails
    the test; the raiser subclasses the real class in ``__new__`` so a future
    ``class SSLSocket(socket)`` in the closure stays definable; ``getaddrinfo`` is
    patched because DNS resolution is network activity that precedes socket creation.
    Residual gap, accepted and named for honesty: code calling the C-level
    ``_socket.socket`` directly would evade the wrapper — nothing in this dependency
    closure does, and the substrate-absence assertion keeps it that way.
    """
    script = (
        "import socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created while importing gebra.verify')\n"
        "def _trip_dns(*a, **k):\n"
        "    attempts.append('getaddrinfo'); print('WA07-TRIP', file=sys.stderr)\n"
        "    raise AssertionError('DNS resolved while importing gebra.verify')\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip_dns\n"
        "import gebra.verify\n"
        "print([m for m in sys.modules if m.split('.')[0] in\n"
        "       {'langgraph', 'langchain', 'langchain_core', 'networkx'}] + attempts)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_reportmodel_is_the_shared_base() -> None:
    for model in (NodeLocation, DataflowWitness, P06EffectRecord, PathLocation):
        assert issubclass(model, ReportModel)
