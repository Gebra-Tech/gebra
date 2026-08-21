"""The strategy library held to the well-formedness it claims — TE-08, brief D-10 W6.

Four kinds of test, because a generator can fail in four different ways and only the first is
about the values it produces:

1. **The well-formedness properties** — the six-item list
   :mod:`gebra.testing.strategies` opens with, one named test each, so a regression names the
   invariant it broke rather than "the strategy". These run at hypothesis's default example
   count; the same conjunction runs at a thousand examples below.
2. **At scale** — the whole conjunction over each of the three envelopes at
   :data:`AT_SCALE_EXAMPLES` examples, with no health check suppressed. This is the card's
   first acceptance box, and the reason it is a *separate* test from the eleven above is that
   the box is about the strategies surviving a thousand draws, not about any one invariant.
3. **Non-vacuity** — a generator that only ever produced the single-node graph would pass
   every property above. Each interesting shape (a cycle, a self-loop, parallel edges, a
   router to ``"END"``, a fan-out template, a nested id, a non-BMP id, every contract slot,
   every runtime slot) is therefore asserted *reachable*, with :func:`hypothesis.find` rather
   than a coverage counter: the failure mode is then a ``NoSuchExample`` naming the shape that
   went missing, instead of a count that drifts under a different seed.
4. **Shrinking** — the minimal well-formed workflow is pinned, which is what makes a
   counterexample from any suite built on this one readable. This is the one place the shrink
   phase is the subject; the reachability finds above run generation only, since "can this be
   produced" does not need the *smallest* witness.

Everything here is pure data (WA-07): the strategies build frozen pydantic values, and the one
thing executed is P-01, a hermetic in-repo function over serialized IR. The runtime tripwire is
``tests/testing/test_hermeticity.py``, whose guarded child generates from this module's subject
and runs P-01 over each draw with substrate imports, sockets and name resolution all raising.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st

from gebra.ir import dump_json, load_json
from gebra.ir.canonical import I_JSON_MAX_INT, graph_version
from gebra.ir.identity import (
    RESERVED_SEGMENTS,
    SYNTHETIC_KINDS,
    SegmentKind,
    is_valid_node_id,
    parse_node_id,
    split_node_id,
    unescape_segment,
)
from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    DeterministicSpec,
    DynamicEdge,
    IdempotentKey,
    NormalEdge,
    Runtime,
    SendEdge,
    StateField,
    WorkflowIR,
)
from gebra.testing.strategies import (
    CONTRACT_SLOTS,
    DEFAULT_ENVELOPE,
    END_LITERAL,
    MINIMAL_ENVELOPE,
    RUNTIME_SLOTS,
    WIDE_ENVELOPE,
    SizeEnvelope,
    digests,
    node_contracts,
    node_id_sets,
    node_ids,
    nodes,
    runtimes,
    source_names,
    state_schemas,
    synthetic_segments,
    topologies,
    user_segments,
    workflow_irs,
)
from gebra.verify.graph import END_VERTEX, START_VERTEX, build_graph_model
from gebra.verify.properties.graph_well_formed import PROPERTY_SLUG, check_graph_well_formed
from gebra.verify.witnesses import WellFormednessWitness

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The example count the card's first acceptance box asks for ("1000+ examples"). Named, and
#: floored by a test of its own, so a later quiet reduction fails the suite rather than passing
#: a weaker claim under the same test names.
AT_SCALE_EXAMPLES: Final = 1000

#: The at-scale profile. Two deliberate choices:
#:
#: * ``suppress_health_check`` is left at its default empty tuple. The acceptance box says
#:   "without health-check failures", so suppressing one would answer a different question —
#:   and ``filter_too_much``/``too_slow``/``data_too_large`` are exactly the failure modes a
#:   generator built out of ``filter`` and ``assume`` would hit.
#: * The deadline is raised rather than removed. At the measured cost of a few milliseconds an
#:   example, one second is a factor of two hundred of headroom — comfortably outside the range
#:   CI scheduling noise moves an example into, and still a real bound: a strategy that became
#:   pathologically slow would fail here instead of merely making the suite slower.
AT_SCALE: Final = settings(max_examples=AT_SCALE_EXAMPLES, deadline=timedelta(seconds=1))

#: The budget a reachability :func:`hypothesis.find` gets. Generous on examples because the
#: rarest shape asserted below (a ``variant`` contract, which needs both a state key and that
#: slot drawn) lands in a few per cent of draws, and a reachability assertion that flakes is
#: worse than a slow one — but the shrink phase is dropped, because "can this shape be
#: produced at all" does not need the *smallest* witness and shrinking it is most of the cost.
#:
#: ``derandomize`` is on here and on :data:`SEARCH` for the same reason: these are existence and
#: shrink-quality assertions, not a hunt for defects, and hypothesis promises shrinking is
#: *good* rather than globally minimal — so a pin on what a witness looks like has to run on a
#: fixed generation sequence or it is a coin flip in CI. The randomized coverage is the at-scale
#: properties above; nothing here is trying to be a second one.
REACH: Final = settings(
    max_examples=2000,
    deadline=None,
    database=None,
    derandomize=True,
    phases=(Phase.generate,),
)

#: The budget the two shrink-audit tests get. Shrinking is the subject there, so it stays on.
SEARCH: Final = settings(max_examples=2000, deadline=None, database=None, derandomize=True)


# ── The well-formedness properties (item by item) ─────────────────────────────────────────


@given(ir=workflow_irs())
def test_every_draw_is_a_validated_workflow_at_ir_version_1_0(ir: WorkflowIR) -> None:
    """Item 1: the draw is a ``WorkflowIR``, and it survives the documented ingestion path.

    Re-validating through ``dump_json`` → ``load_json`` is the stronger form of "it validates":
    the constructor already ran, so what this adds is that the *document* the draw serializes
    to loads back into the identical model — which is how a generated IR reaches a snapshot
    store or a fixture in the first place.
    """
    assert isinstance(ir, WorkflowIR)
    assert ir.ir_version == "1.0"
    assert load_json(WorkflowIR, dump_json(ir)) == ir


@given(ir=workflow_irs())
def test_every_node_id_is_grammatical_and_distinct(ir: WorkflowIR) -> None:
    """Item 2: IR-SPEC §5.1 — a valid id per node, pairwise distinct, no reserved segment."""
    identifiers = [node.id for node in ir.nodes]
    assert identifiers, "IR-SPEC §2.1 makes nodes[] 1*, so a draw always has one"
    assert len(set(identifiers)) == len(identifiers)
    for node_id in identifiers:
        assert is_valid_node_id(node_id)
        assert not set(split_node_id(node_id)) & RESERVED_SEGMENTS


@given(ir=workflow_irs())
def test_every_reference_names_a_declared_node(ir: WorkflowIR) -> None:
    """Item 3, re-derived from the surface rather than read off the shared graph.

    The five reference sites IR-SPEC §2.3 leaves unconstrained by the models, checked here
    because "the models admit it" is precisely why a generator has to get it right: ``entry``,
    ``finish``, an edge's ``from``, a ``normal``/``send`` edge's ``to``, and every ``path_map``
    value. Only a ``path_map`` value may be the ``"END"`` literal (PD-007 Q2).
    """
    declared = {node.id for node in ir.nodes}
    for node_id in _wiring_ids(ir.entry) + _wiring_ids(ir.finish):
        assert node_id in declared
    for edge in ir.edges:
        assert edge.from_ in declared
        if isinstance(edge, ConditionalEdge):
            for target in edge.path_map.values():
                assert target in declared or target == END_LITERAL
        else:
            # The strategies generate ir 1.0 documents, so the fourth kind cannot appear here;
            # the assertion states that rather than narrowing past it silently.
            assert not isinstance(edge, DynamicEdge), "the 1.0 strategies emit no dynamic edge"
            assert edge.to in declared, "a normal/send `to` is a node id, never the END literal"


@given(ir=workflow_irs())
def test_the_shared_graph_model_records_no_unresolved_reference(ir: WorkflowIR) -> None:
    """Item 3 again, from the other side: VAL-03's model is the authority, not this suite.

    Asserted under *both* degradation conventions of PROPERTY-CATALOG-SPEC §0.3 — P-01's
    (drop) and P-02's/P-04's (carry) — because on clean topology the parameter makes no
    difference at all, and that non-difference is what the item claims.
    """
    for carry in (False, True):
        model = build_graph_model(ir, carry_unresolved_references=carry)
        assert model.unresolved == ()
        assert model.carried == frozenset()


@given(ir=workflow_irs())
def test_p01_passes_on_every_draw(ir: WorkflowIR) -> None:
    """Item 4: the validator that owns well-formedness agrees, and its witness is the full set.

    This is the load-bearing property of the whole module: "well-formed" is not this suite's
    definition but PROPERTY-CATALOG-SPEC §1's, and VAL-05 implements it. The witness is read
    rather than only the verdict, so a *vacuous* pass — one whose ``reachable_from_start``
    omitted a node — would fail here too.

    Mutating a draw to break one of the four conditions is deliberately not done here; that is
    TE-09's card, and it is what this property is the baseline for.
    """
    report = check_graph_well_formed(ir)

    assert report.result == "pass", report.failure
    assert report.property == PROPERTY_SLUG
    witness = report.witness
    assert isinstance(witness, WellFormednessWitness)
    assert set(witness.reachable_from_start) == {node.id for node in ir.nodes}
    assert witness.orphan_nodes == ()
    assert witness.unresolved_targets == ()


@given(ir=workflow_irs())
def test_no_node_is_a_sink_outside_finish(ir: WorkflowIR) -> None:
    """Item 4's condition (ii), re-derived — the constraint that shapes ``finish``.

    A node with no outgoing edge in $G^*$ strands execution unless ``finish`` supplies its edge
    to ``__end__`` (IR-SPEC §4.1 (m2)). Stated separately from the P-01 property because it is
    the one condition the generator satisfies by *derivation* rather than by construction, so
    it is the one an edit to :func:`~gebra.testing.strategies.topologies` is most likely to
    break.
    """
    sources = {edge.from_ for edge in ir.edges}
    finish = set(_wiring_ids(ir.finish))
    for node in ir.nodes:
        assert node.id in sources or node.id in finish


@given(ir=workflow_irs())
def test_every_contract_key_is_a_state_key(ir: WorkflowIR) -> None:
    """Item 5: the IR-SPEC §2.3 cross-field obligations the models deliberately do not check.

    §2.3 puts ``input``/``output`` inside ``keys(state)`` and ``idempotent.key`` inside
    ``input``; §3.3 reads ``variant.key`` as the state key that progresses. The models leave
    all three to the validators — "a document that violates one has to *load* before anything
    can report it" — which is exactly why a well-formed *generator* has to honour them.
    """
    keys = set(ir.state or {})
    for contract in _contracts(ir):
        assert set(contract.input or ()) <= keys
        assert set(contract.output or ()) <= keys
        if isinstance(contract.idempotent, IdempotentKey):
            assert contract.idempotent.key in set(contract.input or ())
        if contract.variant is not None:
            assert contract.variant.key in keys


@given(ir=workflow_irs())
def test_every_node_valued_slot_names_a_declared_node(ir: WorkflowIR) -> None:
    """Item 3's remaining two sites: ``runtime.interrupts`` (§3.7) and ``compensation.hook``.

    Neither is read by P-01, and the models constrain neither, so nothing else in the suite
    would notice a generator that pointed them at a node that does not exist.
    """
    declared = {node.id for node in ir.nodes}
    for contract in _contracts(ir):
        if contract.compensation is not None:
            assert contract.compensation.hook in declared
    interrupts = None if ir.runtime is None else ir.runtime.interrupts
    if interrupts is not None:
        assert set(interrupts.before or ()) <= declared
        assert set(interrupts.after or ()) <= declared


@given(ir=workflow_irs())
def test_every_draw_canonicalizes_to_a_stable_digest(ir: WorkflowIR) -> None:
    """Item 6: ``graph_version`` accepts every draw, and the surface round trip is digest-safe.

    Canonicalization is where an out-of-range integer or a non-finite double becomes an error
    (IR-SPEC §6.3; PD-004), so a digest that computes at all is most of item 6. The second
    assertion is the one that would catch a generator emitting content that *survives*
    canonicalization but not serialization.
    """
    digest = graph_version(ir)

    assert digest.startswith("sha256:")
    assert graph_version(ir) == digest
    assert graph_version(load_json(WorkflowIR, dump_json(ir))) == digest


@given(ir=workflow_irs())
def test_every_generated_number_is_exactly_representable(ir: WorkflowIR) -> None:
    """Item 6 again, named at the slots rather than inferred from the digest succeeding.

    IR-SPEC §6.3 bounds integers to ±(2^53−1) and forbids non-finite doubles; §6.3 also reads
    an *integral* double as an integer, which is why a float is bounded to the same range
    rather than merely required finite.
    """
    for number in _numbers(ir):
        if isinstance(number, bool):
            continue
        if isinstance(number, int):
            assert abs(number) <= I_JSON_MAX_INT
        else:
            assert math.isfinite(number)
            assert abs(number) <= I_JSON_MAX_INT


@given(ir=workflow_irs())
def test_entry_is_never_empty(ir: WorkflowIR) -> None:
    """The one ratified surface form the well-formed envelope excludes, stated as a property.

    DEC-18 makes ``entry: []`` a value — "no statically known sentinel wiring" — and with it
    every node is unreachable from ``START``, so P-01's condition (i) fails on every node.
    That makes it a mutation, not a well-formed draw, and the exclusion is written down here so
    a future reader does not take its absence for an oversight. ``finish`` carries no such
    exclusion: the empty form is what a router-terminated workflow looks like.
    """
    assert _wiring_ids(ir.entry), "a well-formed draw always wires at least one entry"


@given(topology=topologies())
def test_the_topology_seam_agrees_with_the_workflow_it_is_built_into(topology: Any) -> None:
    """The mutation seam is self-consistent before any content is attached to it.

    ``Topology`` is what a mutation operator will rewrite, so its two convenience views have to
    agree with the surface forms it carries, and the edge set has to be built from its own ids.
    """
    assert topology.entry_ids and set(topology.entry_ids) <= set(topology.node_ids)
    assert set(topology.finish_ids) <= set(topology.node_ids)
    for edge in topology.edges:
        assert edge.from_ in topology.node_ids


# ── At scale: the card's first acceptance box ─────────────────────────────────────────────


@AT_SCALE
@given(ir=workflow_irs())
def test_the_default_envelope_is_well_formed_at_scale(ir: WorkflowIR) -> None:
    """A thousand draws from :data:`DEFAULT_ENVELOPE`, every item of the list at once."""
    _assert_well_formed(ir)


@AT_SCALE
@given(ir=workflow_irs(envelope=WIDE_ENVELOPE))
def test_the_wide_envelope_is_well_formed_at_scale(ir: WorkflowIR) -> None:
    """The same at :data:`WIDE_ENVELOPE`: denser graphs, deeper ids, fuller contracts.

    Run at the same thousand examples rather than fewer, because this is the envelope where a
    ``too_slow`` health check or a deadline would show up first if the generator regressed.
    """
    _assert_well_formed(ir)


@AT_SCALE
@given(ir=workflow_irs(envelope=MINIMAL_ENVELOPE))
def test_the_minimal_envelope_is_well_formed_at_scale(ir: WorkflowIR) -> None:
    """And at the floor, where the degenerate single-node graph is the *only* shape.

    §1.3's splitter case — one node, ``entry == finish == n``, no edges — is a P-01 *pass*
    under Reading A (DEC-11), and this is where the strategies meet it a thousand times.
    """
    _assert_well_formed(ir)

    assert len(ir.nodes) == 1
    assert ir.edges == ()
    assert ir.state in (None, {})
    assert ir.nodes[0].annotations in (None, Annotations())
    assert ir.runtime in (None, Runtime())


def test_the_at_scale_profile_is_what_the_acceptance_box_asks_for() -> None:
    """The box says "1000+ examples without health-check failures"; this pins both halves."""
    assert AT_SCALE_EXAMPLES >= 1000
    assert AT_SCALE.max_examples == AT_SCALE_EXAMPLES
    assert AT_SCALE.suppress_health_check == ()
    assert set(HealthCheck) - set(AT_SCALE.suppress_health_check) == set(HealthCheck)


def test_the_suite_governs_under_its_own_profile() -> None:
    """No ambient profile edits the tables: conftest registers and force-loads ``gebra``.

    Hypothesis loads its own "ci" profile whenever the ``CI`` env var is set, and that
    profile suppresses ``too_slow`` — which would silently rewrite every derived
    ``settings(...)`` above. The first assertion pins the registered profile's facts; the
    second pins that it is actually the one governing, since a fresh ``settings()`` inherits
    from whichever profile is loaded.
    """
    assert settings.get_profile("gebra").suppress_health_check == ()
    assert settings().suppress_health_check == ()


# ── Non-vacuity: every interesting shape is reachable ─────────────────────────────────────


def _has_cycle(ir: WorkflowIR) -> bool:
    return bool(build_graph_model(ir).components.nontrivial)


def _has_self_loop(ir: WorkflowIR) -> bool:
    return any(edge.source == edge.target for edge in build_graph_model(ir).edges)


def _has_parallel_edges(ir: WorkflowIR) -> bool:
    incidences = [
        (edge.source, edge.target, edge.kind, edge.label) for edge in build_graph_model(ir).edges
    ]
    return len(incidences) != len(set(incidences))


def _reaches_end(ir: WorkflowIR) -> bool:
    return END_VERTEX in {edge.target for edge in build_graph_model(ir).edges}


def _has_end_only_router(ir: WorkflowIR) -> bool:
    return any(
        isinstance(edge, ConditionalEdge) and set(edge.path_map.values()) == {END_LITERAL}
        for edge in ir.edges
    )


def _has_multi_label_router(ir: WorkflowIR) -> bool:
    return any(isinstance(edge, ConditionalEdge) and len(edge.path_map) > 1 for edge in ir.edges)


def _has_send_edge(ir: WorkflowIR) -> bool:
    return any(isinstance(edge, SendEdge) for edge in ir.edges)


def _has_router_condition(ir: WorkflowIR) -> bool:
    return any(edge.condition is not None for edge in ir.edges)


#: One entry per shape a suite built on these strategies needs to be able to reach. A generator
#: that stopped producing any of them would still satisfy every property above, which is what
#: makes this table the non-vacuity half of the card's second acceptance box.
SHAPES: Final[tuple[tuple[str, Any], ...]] = (
    ("a cycle", _has_cycle),
    ("a self-loop", _has_self_loop),
    ("parallel edges", _has_parallel_edges),
    ("an edge into END", _reaches_end),
    ("a router whose only label is END", _has_end_only_router),
    ("a router with several labels", _has_multi_label_router),
    ("a send fan-out template", _has_send_edge),
    ("a declared router condition", _has_router_condition),
    ("an empty finish", lambda ir: not ir.finish),
    ("a scalar entry", lambda ir: isinstance(ir.entry, str)),
    ("a list entry", lambda ir: not isinstance(ir.entry, str)),
    ("two entry ids", lambda ir: not isinstance(ir.entry, str) and len(ir.entry) > 1),
    ("four or more nodes", lambda ir: len(ir.nodes) >= 4),
    ("a nested node id", lambda ir: any("/" in node.id for node in ir.nodes)),
    ("an escaped or synthetic segment", lambda ir: any("%" in node.id for node in ir.nodes)),
    (
        "a non-BMP node id",
        lambda ir: any(ord(character) > 0xFFFF for node in ir.nodes for character in node.id),
    ),
    ("a populated state schema", lambda ir: bool(ir.state)),
    (
        "a state field in object form",
        lambda ir: any(isinstance(value, StateField) for value in (ir.state or {}).values()),
    ),
    (
        "a keyed idempotence marker",
        lambda ir: any(
            isinstance(contract.idempotent, IdempotentKey) for contract in _contracts(ir)
        ),
    ),
    (
        "a seeded determinism spec",
        lambda ir: any(
            isinstance(contract.deterministic, DeterministicSpec) for contract in _contracts(ir)
        ),
    ),
)


@pytest.mark.parametrize(("description", "predicate"), SHAPES, ids=[name for name, _ in SHAPES])
def test_the_default_envelope_can_produce(description: str, predicate: Any) -> None:
    """``find`` locates a minimal witness, or raises ``NoSuchExample`` naming this shape."""
    witness = find(workflow_irs(), predicate, settings=REACH)

    assert predicate(witness), description
    _assert_well_formed(witness)


@pytest.mark.parametrize("slot", CONTRACT_SLOTS)
def test_every_contract_slot_is_reachable(slot: str) -> None:
    """All fourteen §2.3/§3 slots, one test each — including the two the slot budget makes
    conditional on other content (``variant`` needs a state key, ``compensation`` a node id)."""
    witness = find(
        workflow_irs(),
        lambda ir: any(getattr(contract, slot) is not None for contract in _contracts(ir)),
        settings=REACH,
    )

    assert any(getattr(contract, slot) is not None for contract in _contracts(witness))


@pytest.mark.parametrize("slot", RUNTIME_SLOTS)
def test_every_runtime_slot_is_reachable(slot: str) -> None:
    """All three §3.5/§3.7 sub-slots."""
    witness = find(
        workflow_irs(),
        lambda ir: ir.runtime is not None and getattr(ir.runtime, slot) is not None,
        settings=REACH,
    )

    assert witness.runtime is not None
    assert getattr(witness.runtime, slot) is not None


def test_the_slot_tables_match_the_live_models() -> None:
    """A field added to the IR without a row in the slot tables goes ungenerated — silently.

    Read off the live models rather than transcribed, so that is a failure here instead.
    """
    assert set(CONTRACT_SLOTS) == set(Annotations.model_fields)
    assert CONTRACT_SLOTS == tuple(Annotations.model_fields)
    assert RUNTIME_SLOTS == tuple(Runtime.model_fields)


# ── Shrinking ────────────────────────────────────────────────────────────────────────────


def test_the_shrink_target_is_the_minimal_well_formed_workflow() -> None:
    """What a counterexample from any suite built on this one looks like once shrunk.

    Pinned rather than described: the draws in
    :func:`~gebra.testing.strategies.workflow_irs` are ordered so that the floor is the
    degenerate single-node graph, and a reordering that moved the floor — say by making a
    non-empty contract the simpler branch — would make every downstream counterexample harder
    to read without failing any property. That is the kind of regression only a pin catches.
    """
    minimal = find(workflow_irs(), lambda ir: True, settings=SEARCH)

    assert len(minimal.nodes) == 1
    identifier = minimal.nodes[0].id
    assert minimal.entry == identifier
    assert minimal.finish == identifier
    assert minimal.edges == ()
    assert minimal.state is None
    assert minimal.nodes[0].annotations is None
    assert minimal.runtime is None


def test_a_seeded_failure_shrinks_to_a_readable_counterexample() -> None:
    """The audit the strategies exist for: a property that fails on two nodes shrinks to two.

    Without this, "shrinking works" is an assertion about hypothesis rather than about these
    strategies — the shrink quality that matters is whether *this* composition converges, and a
    composite that drew its sizes after its content would not.
    """
    witness = find(workflow_irs(), lambda ir: len(ir.nodes) >= 2, settings=SEARCH)

    assert len(witness.nodes) == 2
    assert len(witness.edges) == 1, "one spanning edge, and no extra edges beyond it"
    assert witness.edges[0].condition is None


# ── The size envelope ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "floor"),
    [
        ("max_nodes", 1),
        ("max_entry_ids", 1),
        ("max_id_segments", 1),
        ("max_path_map_labels", 1),
        ("max_extra_edges", 0),
        ("max_extra_finish", 0),
        ("max_state_keys", 0),
        ("max_contract_keys", 0),
        ("max_contract_slots", 0),
        ("max_effect_tags", 0),
        ("max_retry_on", 0),
        ("max_args_schema_keys", 0),
        ("max_interrupts", 0),
        ("max_runtime_slots", 0),
    ],
)
def test_an_envelope_below_a_structural_floor_is_refused(field: str, floor: int) -> None:
    """Every bound has a floor, and every floor is enforced at construction."""
    with pytest.raises(ValueError, match="structural floor"):
        SizeEnvelope(**{field: floor - 1})

    assert getattr(SizeEnvelope(**{field: floor}), field) == floor


def test_the_three_presets_are_ordered_and_legal() -> None:
    """MINIMAL ≤ DEFAULT ≤ WIDE on every bound, so a suite can widen without surprises."""
    fields = [name for name in SizeEnvelope.__dataclass_fields__]
    for name in fields:
        assert getattr(MINIMAL_ENVELOPE, name) <= getattr(DEFAULT_ENVELOPE, name), name
        assert getattr(DEFAULT_ENVELOPE, name) <= getattr(WIDE_ENVELOPE, name), name


@given(identifiers=node_id_sets(envelope=WIDE_ENVELOPE))
def test_the_node_count_bound_is_respected(identifiers: tuple[str, ...]) -> None:
    assert 1 <= len(identifiers) <= WIDE_ENVELOPE.max_nodes
    assert len(set(identifiers)) == len(identifiers)


@given(schema=state_schemas(envelope=DEFAULT_ENVELOPE))
def test_the_state_key_bound_is_respected(schema: dict[str, Any]) -> None:
    assert len(schema) <= DEFAULT_ENVELOPE.max_state_keys


@given(contract=node_contracts(state_keys=("alpha", "beta"), hook_ids=("n",)))
def test_the_contract_slot_bound_is_respected(contract: Annotations) -> None:
    """One member may ride along past the bound, and the bound names which one.

    A keyed ``idempotent`` marker populates ``input`` too when ``input`` was not itself drawn,
    because §2.3 scopes the key to it. Asserting the allowance *conditionally* is what keeps
    it the documented single exception rather than slack in the bound.
    """
    populated = [slot for slot in CONTRACT_SLOTS if getattr(contract, slot) is not None]
    marker = contract.idempotent

    assert len(populated) <= DEFAULT_ENVELOPE.max_contract_slots + (
        1 if isinstance(marker, IdempotentKey) else 0
    )
    assert set(contract.input or ()) <= {"alpha", "beta"}
    if isinstance(marker, IdempotentKey):
        assert marker.key in (contract.input or ())
    if contract.compensation is not None:
        assert contract.compensation.hook == "n"


@given(block=runtimes(interrupt_ids=("n",)))
def test_the_runtime_slot_bound_is_respected(block: Runtime) -> None:
    populated = [slot for slot in RUNTIME_SLOTS if getattr(block, slot) is not None]

    assert len(populated) <= DEFAULT_ENVELOPE.max_runtime_slots
    if block.recursion_limit is not None:
        assert block.recursion_limit.value >= 1


# ── The building blocks, on their own ─────────────────────────────────────────────────────


@given(name=source_names())
def test_a_source_name_never_escapes_to_a_reserved_segment(name: str) -> None:
    """The one thing the id layer has to refuse: ``__start__``/``__end__`` at any level."""
    assert name
    assert name not in RESERVED_SEGMENTS


@given(node_id=node_ids(envelope=WIDE_ENVELOPE))
def test_a_drawn_node_id_parses_at_every_depth(node_id: str) -> None:
    segments = split_node_id(node_id)

    assert 1 <= len(segments) <= WIDE_ENVELOPE.max_id_segments
    assert "/".join(segments) == node_id


@given(segment=user_segments())
def test_a_user_segment_is_a_one_segment_node_id(segment: str) -> None:
    """The escaped form is a whole id on its own — which is what makes it a segment."""
    assert split_node_id(segment) == (segment,)
    assert set(unescape_segment(segment)) - {"/", "%"} or unescape_segment(segment)


@given(segment=synthetic_segments())
def test_a_synthetic_segment_carries_a_1_0_kind_and_a_non_empty_selector(segment: str) -> None:
    """IR-SPEC §5.2: the ``kind`` vocabulary is closed and the selector is never empty."""
    parsed = parse_node_id(segment).segments[0]

    assert parsed.kind is SegmentKind.SYNTHETIC
    assert parsed.synthetic_kind in SYNTHETIC_KINDS
    assert parsed.selector


@given(digest=digests())
def test_a_drawn_digest_has_the_section_3_6_shape(digest: str) -> None:
    """``"sha256:" 64HEXDIG`` — nothing in 1.0 reads the value, so only the shape is fixed."""
    algorithm, _, hexadecimal = digest.partition(":")

    assert algorithm == "sha256"
    assert len(hexadecimal) == 64
    assert set(hexadecimal) <= set("0123456789abcdef")


@given(node=nodes(state_keys=("alpha",), hook_ids=("n",), envelope=DEFAULT_ENVELOPE))
def test_a_drawn_node_carries_a_grammatical_id(node: Any) -> None:
    assert is_valid_node_id(node.id)


def test_a_topology_over_no_ids_is_refused() -> None:
    """``nodes[]`` is ``1*`` (IR-SPEC §2.1), so an empty id strategy is an error, not an
    empty graph — the one way a caller can misuse the ``ids`` seam."""
    with pytest.raises(ValueError, match="at least one node id"):
        find(topologies(ids=st.just(())), lambda topology: True, settings=REACH)


def test_the_strategy_builders_are_memoized() -> None:
    """The composition decision, pinned: building a strategy is not a per-example cost.

    A ``@st.composite`` body runs once per example, so a tree rebuilt inside one is rebuilt a
    thousand times over a thousand-example run — measured at roughly two thirds of the cost of
    :func:`~gebra.testing.strategies.workflow_irs` before the builders were memoized. That
    matters here and it matters much more to the ≥20 metaproperties this module is the
    substrate for, so identity is asserted rather than left as a comment someone can delete.
    """
    assert workflow_irs() is workflow_irs()
    assert workflow_irs(envelope=WIDE_ENVELOPE) is workflow_irs(envelope=WIDE_ENVELOPE)
    assert workflow_irs() is not workflow_irs(envelope=WIDE_ENVELOPE)
    assert topologies() is topologies()
    assert node_ids() is node_ids()
    assert state_schemas() is state_schemas()
    assert node_contracts(state_keys=["a"]) is node_contracts(state_keys=("a",))
    assert runtimes(interrupt_ids=["n"]) is runtimes(interrupt_ids=("n",))


# ── hypothesis stays an optional dependency of gebra.testing ──────────────────────────────

#: Import ``gebra.testing`` in a fresh interpreter and report whether hypothesis came with it.
_WITHOUT_HYPOTHESIS = '''
import json
import sys


class Blocker:
    """Refuse hypothesis, the way an environment that never installed it would."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] == "hypothesis":
            raise ImportError("no module named " + repr(fullname))
        return None


sys.meta_path.insert(0, Blocker())

import gebra.testing

report = {"loader": hasattr(gebra.testing, "load_corpus"), "leaked": "hypothesis" in sys.modules}
try:
    import gebra.testing.strategies
except ImportError as error:
    report["strategies_error"] = str(error)
else:
    report["strategies_error"] = None
print(json.dumps(report))
'''


def test_importing_gebra_testing_needs_no_hypothesis() -> None:
    """The package body must not import this module: hypothesis is a dev dependency.

    Proven the only way a transitive import can be — in an interpreter where importing
    hypothesis raises. The loader, the lint and the harness keep working; only
    ``gebra.testing.strategies`` is unavailable, and it says why rather than failing with
    hypothesis's own message.
    """
    result = subprocess.run(
        [sys.executable, "-c", _WITHOUT_HYPOTHESIS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["loader"] is True
    assert report["leaked"] is False
    assert report["strategies_error"] is not None
    assert "hypothesis" in report["strategies_error"]
    assert "gebra.testing.strategies" in report["strategies_error"]


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _wiring_ids(wiring: str | tuple[str, ...]) -> tuple[str, ...]:
    """``entry``/``finish`` as a tuple, whichever of the two §2.1 surface forms it is in."""
    return (wiring,) if isinstance(wiring, str) else wiring


def _contracts(ir: WorkflowIR) -> Iterator[Annotations]:
    """Every contract the workflow declares, skipping the nodes that carry none."""
    for node in ir.nodes:
        if node.annotations is not None:
            yield node.annotations


def _numbers(ir: WorkflowIR) -> Iterator[float]:
    """Every number a draw can carry, including the foreign ``args_schema`` interior."""
    if ir.runtime is not None and ir.runtime.recursion_limit is not None:
        yield ir.runtime.recursion_limit.value
    for contract in _contracts(ir):
        if contract.retry_policy is not None:
            yield contract.retry_policy.max_attempts
        if isinstance(contract.deterministic, DeterministicSpec):
            yield contract.deterministic.seed
            if contract.deterministic.temperature is not None:
                yield contract.deterministic.temperature
        yield from _numbers_in(contract.args_schema)


def _numbers_in(value: object) -> Iterator[float]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _numbers_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _numbers_in(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield value


def _assert_well_formed(ir: WorkflowIR) -> None:
    """Every item of the module's well-formedness list, for the at-scale and ``find`` tests.

    The named properties above are what a *regression* should fail; this is the conjunction the
    acceptance box is judged against, so it deliberately repeats them rather than sampling.
    """
    assert isinstance(ir, WorkflowIR)
    assert ir.ir_version == "1.0"
    assert load_json(WorkflowIR, dump_json(ir)) == ir

    declared = {node.id for node in ir.nodes}
    assert len(declared) == len(ir.nodes)
    for node_id in declared:
        assert is_valid_node_id(node_id)
        assert not set(split_node_id(node_id)) & RESERVED_SEGMENTS

    entry = _wiring_ids(ir.entry)
    finish = _wiring_ids(ir.finish)
    assert entry, "a well-formed draw always wires at least one entry"
    assert set(entry) <= declared
    assert set(finish) <= declared
    sources = {edge.from_ for edge in ir.edges}
    for edge in ir.edges:
        assert edge.from_ in declared
        if isinstance(edge, ConditionalEdge):
            assert edge.path_map
            for target in edge.path_map.values():
                assert target in declared or target == END_LITERAL
        else:
            assert isinstance(edge, (NormalEdge, SendEdge))
            assert edge.to in declared
    for node_id in declared:
        assert node_id in sources or node_id in set(finish)

    model = build_graph_model(ir)
    assert model.unresolved == ()
    assert START_VERTEX in model.vertices and END_VERTEX in model.vertices
    report = check_graph_well_formed(ir)
    assert report.result == "pass", report.failure
    assert isinstance(report.witness, WellFormednessWitness)
    assert set(report.witness.reachable_from_start) == declared

    keys = set(ir.state or {})
    for contract in _contracts(ir):
        assert set(contract.input or ()) <= keys
        assert set(contract.output or ()) <= keys
        if isinstance(contract.idempotent, IdempotentKey):
            assert contract.idempotent.key in set(contract.input or ())
        if contract.variant is not None:
            assert contract.variant.key in keys
        if contract.compensation is not None:
            assert contract.compensation.hook in declared

    assert graph_version(ir).startswith("sha256:")
