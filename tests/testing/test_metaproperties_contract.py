"""Metaproperty suite II — the contract and advisory validators under mutation (TE-10, D-10 W7/W10).

A *metaproperty* is a claim about a **validator**, quantified over generated input, rather than
a claim about one workflow. The corpus says what P-04, P-06 and P-08 answer on seventy-one authored
documents; this suite says what they answer on documents nobody authored, and — through
:mod:`gebra.testing.mutations` — on documents built to break exactly one of them at exactly one
point.

**The acceptance box, and how it is discharged.** D-10 Deliverable 5 and its DoD ask for "20+
hypothesis metaproperties … all passing at 1000+ examples" plus "mutation strategies … for every
property with fixtures". :data:`METAPROPERTIES` is the machine-checked count:
:func:`test_the_metaproperty_table_is_the_suite` holds it to the module — every ``@given`` test
here has a row, every row names a test that exists, and every one of them runs under
:data:`AT_SCALE`, so a later quiet reduction of the example count, or a quietly deleted
metaproperty, fails a test instead of weakening a claim that keeps its name.

**Suite I is not in this file.** TE-09 owns the *structural* metaproperties (P-01, P-02) and
lives in ``tests/testing/test_metaproperties_structural.py``; when this file was written that
card was blocked on VAL-07, so the ≥20 combined target was met here alone, and it still is. The
overlap policy is recorded on both cards and realized in the code: this suite owns the shared
:class:`~gebra.testing.mutations.Mutation` record, the operator library, and the cross-cutting
metaproperties (``MP-X-*``) that quantify over *every* registered operator whatever its target;
suite I adds structural operators to the same library and its own rows.

**What that cost when suite I landed**, recorded rather than smoothed over, because the
prediction here was "no edit": three things. :data:`VALIDATORS` gained P-02, which had not been
registered when this file was written — without it the ``MP-X-*`` rows would raise on a P-02
mutation rather than quantify over it. And ``MP-X-5``/``MP-X-6``/``MP-X-7`` gained a scope on
:attr:`~gebra.testing.mutations.Mutation.well_formed`, because a breaking P-01 mutant is
P-01-*dirty* by design and §0.3 defines the other four results only over P-01-clean topology.
Each narrowing is what §0.3 already said; each is stated at its row.

**Four kinds of claim**, and the ids say which:

* ``MP-04-*`` — P-04 ``dataflow-completeness``: the must-write analysis, its boundary set, its
  first-arrival semantics, and the validity of the path it attributes a violation to.
* ``MP-06-*`` — P-06 ``effect-safety``: the protection lattice, the region rule, and the reality
  of every cycle it names.
* ``MP-08-*`` — P-08 ``determinism-replay``: the advisory, its C-1 evidence gate, its mandatory
  caveat, and §8.7's "must not couple to topology" as a property rather than a review note.
* ``MP-X-*`` — every operator at once, this file's and suite I's: determinism, §0.4 registry
  closure, §0.3 envelope conformance and packaging, the shared-model seam, and the one that makes
  D-10's "break exactly one property" checkable — between a mutation's ``origin`` and its ``ir``,
  the only verdict that moves is its target's.

Everything here is pure data (WA-07): the strategies build frozen pydantic values, the operators
rewrite them into new frozen pydantic values, and everything executed is in-repo and hermetic —
the five wedge validators, VAL-03's shared graph pre-analysis, canonical serialization and the
§0.3 envelope models, each a function over serialized IR. The runtime tripwire is
``tests/testing/test_hermeticity.py``, whose guarded child draws a mutation from each family and
runs the validator that owns it with substrate imports, sockets and name resolution all raising.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise
from typing import Any, Final

import pytest
from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st

from gebra.ir import Annotations, WorkflowIR, dump_json, load_json
from gebra.ir.canonical import graph_version
from gebra.testing.mutations import (
    DATAFLOW_OPERATORS,
    DETERMINISM_OPERATORS,
    EFFECT_SAFETY_OPERATORS,
    OPERATORS,
    Mutation,
    bound_key,
    boundary_read,
    chain_wiring,
    compensation_hook,
    dataflow_mutations,
    determinism_mutations,
    effect_safety_mutations,
    local_claim,
    mutations,
    permute_nodes,
    pinned_claim,
    star_wiring,
    unbound_key,
    update_contract,
    with_self_loop,
    with_state_field,
)
from gebra.testing.strategies import DEFAULT_ENVELOPE, workflow_irs
from gebra.verify.base import ConditionId, PropertySlug, from_display
from gebra.verify.conditions import condition, is_emittable, property_for_condition
from gebra.verify.graph import (
    START_VERTEX,
    GraphModel,
    build_graph_model,
    ledger_sort_key,
)
from gebra.verify.locations import (
    AnyLocation,
    DeterminismNodeLocation,
    P06NodeLocation,
)
from gebra.verify.properties.dataflow_completeness import (
    READ_KEY_NEVER_WRITTEN_ON_PATH,
    check_dataflow_completeness,
)
from gebra.verify.properties.determinism_replay import (
    CAVEAT,
    LLM_EVIDENCE_TAGS,
    SEED_UNPINNED,
    TEMPERATURE_UNPINNED,
    WARNING_HEADER,
    check_determinism_replay,
    render_remediation,
    render_warning,
)
from gebra.verify.properties.effect_safety import (
    IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
    TRIGGER_TAGS,
    UNPROTECTED_EFFECT_IN_CYCLE,
    UNPROTECTED_EFFECT_IN_RETRY_REGION,
    check_effect_safety,
)
from gebra.verify.properties.graph_well_formed import check_graph_well_formed
from gebra.verify.properties.termination_witness import check_termination_witness
from gebra.verify.report import P04Failure, PropertyReport, validate_report
from gebra.verify.witnesses import (
    DataflowWitness,
    DeterminismWitness,
    EffectSafetyWitness,
)

#: The example count the card's acceptance box asks for ("1000+ examples"). Named, and floored
#: by :func:`test_the_metaproperty_table_is_the_suite`, so a later quiet reduction fails the
#: suite rather than passing a weaker claim under the same test names.
AT_SCALE_EXAMPLES: Final = 1000

#: How many metaproperties the combined library must hold, per D-10 Deliverable 5.
COMBINED_TARGET: Final = 20

#: The profile every metaproperty runs under, taken from TE-08's suite point for point:
#: no health check is suppressed (the box says the suite is green, and ``filter_too_much`` /
#: ``too_slow`` / ``data_too_large`` are exactly what a badly-composed mutation strategy would
#: trip), and the deadline is *raised* rather than removed — a mutation plus one validator run
#: measures a few milliseconds, so one second is a wide margin over CI scheduling noise while a
#: pathological slowdown still trips it.
AT_SCALE: Final = settings(max_examples=AT_SCALE_EXAMPLES, deadline=timedelta(seconds=1))

#: The budget a reachability :func:`hypothesis.find` gets — generous on examples because the
#: rarest shape below (a reader drawn onto an entry node with every node writing the key) lands
#: in a few per cent of draws, and derandomized because these are existence assertions rather
#: than a hunt for defects. The shrink phase is dropped: "can this shape be produced" does not
#: need the smallest witness, and shrinking it is most of the cost.
REACH: Final = settings(
    max_examples=3000,
    deadline=None,
    database=None,
    derandomize=True,
    phases=(Phase.generate,),
)

#: All five wedge validators, by slug. P-02 joined at TE-09, when VAL-07 landed and the
#: structural operators did: every ``MP-X-*`` row below reads this table by
#: :attr:`~gebra.testing.mutations.Mutation.target`, so a family whose target is missing here is
#: a ``KeyError`` rather than a quiet gap — which is how the row that says "exactly one verdict
#: moves" stays a claim about *every* registered validator rather than about whichever four this
#: file happened to name.
VALIDATORS: Final[dict[PropertySlug, Callable[[WorkflowIR], PropertyReport]]] = {
    "graph-well-formed": check_graph_well_formed,
    "termination-witness": check_termination_witness,
    "dataflow-completeness": check_dataflow_completeness,
    "effect-safety": check_effect_safety,
    "determinism-replay": check_determinism_replay,
}

#: The three this file is *suite II* for. Written out rather than read off
#: :data:`~gebra.testing.mutations.OPERATORS`, because the point of the distinction is that the
#: operator table grows when TE-09 lands and this file's per-property rows do not.
CONTRACT_AND_ADVISORY: Final[tuple[PropertySlug, ...]] = (
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)


# ── The table the acceptance box is counted from ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Metaproperty:
    """One row of the metaproperty library.

    Attributes:
        id: Stable identifier; the prefix names the target (``MP-04``/``MP-06``/``MP-08``/
            ``MP-X``).
        target: The property slug the claim is about, or ``"*"`` for a cross-cutting claim that
            quantifies over every operator whatever its target.
        test: The name of the test function in this module that runs it.
        claim: The claim in one line — what a reader of a CI failure needs before the traceback.
    """

    id: str
    target: PropertySlug | str
    test: str
    claim: str


#: The library. One row per ``@given`` metaproperty in this module, in file order; the row and
#: the function are held to each other by :func:`test_the_metaproperty_table_is_the_suite`.
METAPROPERTIES: Final[tuple[Metaproperty, ...]] = (
    Metaproperty(
        "MP-04-1",
        "dataflow-completeness",
        "test_an_unwritten_read_is_reported_at_that_reader_and_key",
        "a declared read no path writes is one finding, anchored at (reader, key)",
    ),
    Metaproperty(
        "MP-04-2",
        "dataflow-completeness",
        "test_the_boundary_set_is_what_covers_an_otherwise_unwritten_read",
        "optional: true puts the key in I0 and covers the read; false violates it",
    ),
    Metaproperty(
        "MP-04-3",
        "dataflow-completeness",
        "test_a_universally_written_key_is_covered_unless_the_reader_is_an_entry",
        "with every node writing k, the read is covered iff the reader is not in entry",
    ),
    Metaproperty(
        "MP-04-4",
        "dataflow-completeness",
        "test_a_nodes_own_write_never_covers_its_own_read",
        "first arrival: writing k at v does not satisfy v's own read of k",
    ),
    Metaproperty(
        "MP-04-5",
        "dataflow-completeness",
        "test_every_offending_path_is_a_real_start_path_avoiding_the_other_writers",
        "the attributed path is a real simple START-path whose interior writes nothing",
    ),
    Metaproperty(
        "MP-04-6",
        "dataflow-completeness",
        "test_a_read_of_a_key_outside_the_schema_is_not_p04s_finding",
        "a read outside Σ raises no P-04 obligation (§4.4 Step 4)",
    ),
    Metaproperty(
        "MP-04-7",
        "dataflow-completeness",
        "test_the_witness_and_the_findings_partition_the_obligations",
        "coverage ∪ findings is exactly the reachable (reader, key ∈ Σ) obligations",
    ),
    Metaproperty(
        "MP-04-8",
        "dataflow-completeness",
        "test_removing_a_write_never_repairs_a_dataflow_violation",
        "the analysis is monotone in the declared writes",
    ),
    Metaproperty(
        "MP-04-9",
        "dataflow-completeness",
        "test_dataflow_is_stable_under_irrelevant_mutation",
        "a self-loop, a node rotation and an unread Σ key leave the report equal",
    ),
    Metaproperty(
        "MP-06-1",
        "effect-safety",
        "test_an_unprotected_trigger_in_a_retry_region_is_reported_there",
        "a retry_policy makes the region retry whatever the topology",
    ),
    Metaproperty(
        "MP-06-2",
        "effect-safety",
        "test_an_unprotected_trigger_on_a_fresh_cycle_is_reported_with_that_cycle",
        "a self-loop makes the region cycle, and the anchor is the loop itself",
    ),
    Metaproperty(
        "MP-06-3",
        "effect-safety",
        "test_the_forbidden_combination_is_fatal_wherever_it_sits",
        "irreversible + keyless idempotent is FATAL and cycle-independent",
    ),
    Metaproperty(
        "MP-06-4",
        "effect-safety",
        "test_an_idempotency_key_protects_exactly_when_it_binds",
        "the key discharges iff it is among the node's declared reads",
    ),
    Metaproperty(
        "MP-06-5",
        "effect-safety",
        "test_a_compensation_hook_protects_exactly_when_it_resolves",
        "a hook naming a node discharges; one naming nothing rides as evidence",
    ),
    Metaproperty(
        "MP-06-6",
        "effect-safety",
        "test_every_cycle_p06_names_is_a_real_canonically_rotated_cycle",
        "every witness cycle and every anchor is a real simple cycle through its node",
    ),
    Metaproperty(
        "MP-06-7",
        "effect-safety",
        "test_p06_accounts_for_exactly_the_trigger_tagged_nodes",
        "records and findings cover the trigger-tagged nodes and nothing else",
    ),
    Metaproperty(
        "MP-06-8",
        "effect-safety",
        "test_effect_safety_is_stable_under_irrelevant_mutation",
        "a non-trigger tag, an unread Σ key and a node rotation keep the verdict",
    ),
    Metaproperty(
        "MP-08-1",
        "determinism-replay",
        "test_a_bare_claim_on_an_llm_backed_node_is_seed_unpinned",
        "deterministic: true plus LLM evidence pins no seed (C-2)",
    ),
    Metaproperty(
        "MP-08-2",
        "determinism-replay",
        "test_pinning_the_temperature_to_zero_repairs_the_claim",
        "absent or nonzero temperature fires C-3; zero is the coherent pinning",
    ),
    Metaproperty(
        "MP-08-3",
        "determinism-replay",
        "test_dropping_the_llm_evidence_makes_the_same_claim_coherent",
        "C-1 is the gate: the same annotation is fine on pure local computation",
    ),
    Metaproperty(
        "MP-08-4",
        "determinism-replay",
        "test_determinism_replay_does_not_couple_to_topology_or_the_schema",
        "rewiring the graph and widening Σ leave the report identical (§8.7)",
    ),
    Metaproperty(
        "MP-08-5",
        "determinism-replay",
        "test_the_claim_inventory_is_exactly_the_declared_claims",
        "claims ∪ findings == the non-false claims; the caveat rides iff one is LLM-backed",
    ),
    Metaproperty(
        "MP-08-6",
        "determinism-replay",
        "test_every_advisory_renders_the_appendix_b_warning_grammar",
        "each finding renders header, diagnosis and remediation naming its node and evidence",
    ),
    Metaproperty(
        "MP-X-1",
        "*",
        "test_every_validator_is_deterministic",
        "same IR, same report — twice, on the mutant and on its origin",
    ),
    Metaproperty(
        "MP-X-2",
        "*",
        "test_every_emitted_condition_id_is_registered_and_correctly_graded",
        "every record's condition is §0.4-registered, emittable, owned, and graded as pinned",
    ),
    Metaproperty(
        "MP-X-3",
        "*",
        "test_every_report_round_trips_through_the_result_envelope",
        "a report re-validated from its own JSON is the identical model",
    ),
    Metaproperty(
        "MP-X-4",
        "*",
        "test_every_report_follows_the_one_property_one_report_packaging",
        "pass ⇔ witness, fail ⇔ failure, co-failures same-property, no advisories",
    ),
    Metaproperty(
        "MP-X-5",
        "*",
        "test_sharing_a_graph_model_changes_no_result",
        "the model= seam agrees with the self-built model, under either §0.3 convention",
    ),
    Metaproperty(
        "MP-X-6",
        "*",
        "test_a_mutation_moves_exactly_its_own_targets_verdict",
        "only the target's verdict moves, iff breaking, and with the predicted condition",
    ),
    Metaproperty(
        "MP-X-7",
        "*",
        "test_every_mutant_is_still_well_formed_and_canonicalizable",
        "a mutant round-trips and hashes, and is P-01 clean iff it claims to be",
    ),
)


def test_the_metaproperty_table_is_the_suite() -> None:
    """The count the acceptance box is judged on, held to the code rather than to prose.

    Four ways the table and the module can drift apart, all closed here: a row naming a test
    that does not exist; a ``@given`` test with no row (which would make the count an
    understatement, but also means an unnamed claim); a duplicated id; and — the one that
    matters most — a metaproperty that quietly stopped running at a thousand examples, or that
    started suppressing a health check to stay green. The settings are read off the decorated
    function rather than trusted, because ``@AT_SCALE`` on the wrong side of ``@given``, or
    simply forgotten, is silent otherwise.
    """
    assert len(METAPROPERTIES) >= COMBINED_TARGET
    assert COMBINED_TARGET >= 20
    assert AT_SCALE_EXAMPLES >= 1000
    assert AT_SCALE.max_examples == AT_SCALE_EXAMPLES
    assert AT_SCALE.suppress_health_check == ()
    assert set(HealthCheck) - set(AT_SCALE.suppress_health_check) == set(HealthCheck)

    identifiers = [row.id for row in METAPROPERTIES]
    targets = {row.target for row in METAPROPERTIES}
    assert len(set(identifiers)) == len(identifiers)
    # Containment, not equality: when TE-09 adds a structural family to `OPERATORS` this file
    # gains no row — the `MP-X-*` layer already quantifies over every operator — so an equality
    # here would fail on a change that is exactly what the overlap policy asks for.
    assert targets <= {*OPERATORS, "*"}
    assert targets == {*CONTRACT_AND_ADVISORY, "*"}

    scope = dict(globals())
    generated = {
        name
        for name, value in scope.items()
        if name.startswith("test_") and getattr(value, "is_hypothesis_test", False)
    }
    assert {row.test for row in METAPROPERTIES} == generated

    for row in METAPROPERTIES:
        profile = getattr(scope[row.test], "_hypothesis_internal_use_settings", None)
        assert profile is not None, row.id
        assert profile.max_examples >= 1000, row.id
        assert profile.suppress_health_check == (), row.id


# ── MP-04-* — P-04 dataflow-completeness (PROPERTY-CATALOG-SPEC §4) ──────────────────────


@AT_SCALE
@given(mutation=dataflow_mutations(operators=("unwritten-read",)))
def test_an_unwritten_read_is_reported_at_that_reader_and_key(mutation: Mutation) -> None:
    """MP-04-1. The defect P-04 exists to find, injected at one point and read back.

    The origin declares no reads at all, so P-04 passes vacuously there; the mutant declares
    exactly one, of a key no node writes and ``state`` does not mark ``optional``. So the report
    is a *single* finding — no co-failures — and both DEC-11 diagnostics are absent, because the
    key has no other writer to cover another path with and the reader is not its own downstream
    writer.
    """
    assert check_dataflow_completeness(mutation.origin).result == "pass"

    failure = _p04_failure(check_dataflow_completeness(mutation.ir))

    assert failure.property_condition == READ_KEY_NEVER_WRITTEN_ON_PATH
    assert failure.location.node == mutation.node
    assert failure.location.key == mutation.key
    assert failure.co_failures is None
    assert failure.writers_on_other_paths is None
    assert failure.downstream_writers is None


@AT_SCALE
@given(mutation=dataflow_mutations(operators=("boundary-read",)))
def test_the_boundary_set_is_what_covers_an_otherwise_unwritten_read(
    mutation: Mutation,
) -> None:
    """MP-04-2. $I_0$, observed as the one field that separates a pass from a failure.

    §4.2 "Graph inputs" reads ``optional: true`` as written at ``START``, so the *same* document
    — same topology, same reader, same key, same absence of any writer — passes with the key
    optional and fails without it. The pass is checked all the way to its witness: one coverage
    entry, and its ``satisfied_by`` is exactly the display sentinel, because no node writes the
    key and the boundary is the only thing that can have covered it.
    """
    node = _node(mutation)
    covered = check_dataflow_completeness(boundary_read(mutation.origin, node, optional=True).ir)
    violated = check_dataflow_completeness(boundary_read(mutation.origin, node, optional=False).ir)

    coverage = _dataflow_witness(covered).coverage
    assert len(coverage) == 1
    assert coverage[0].node == node
    assert coverage[0].key == mutation.key
    assert coverage[0].satisfied_by == ("START",)

    assert _p04_failure(violated).location.node == node


@AT_SCALE
@given(mutation=dataflow_mutations(operators=("universal-write",)))
def test_a_universally_written_key_is_covered_unless_the_reader_is_an_entry(
    mutation: Mutation,
) -> None:
    """MP-04-3. Every node writes the key; the verdict then turns on one structural fact.

    If the reader is not in ``entry``, every ``START``-path to it runs through some entry node
    first and that node writes the key — covered, whatever the topology, and ``satisfied_by``
    names writers rather than the boundary. If the reader *is* in ``entry``, the one-step path
    ``START → v`` has no interior at all, so nothing writes the key before $v$ reads it. The
    attributed path is then exactly ``("START", v)``: the reachability form removes
    $W_k \\setminus \\{v\\}$, which here is every other node, so the only route left is the
    sentinel wiring.
    """
    node = _node(mutation)
    report = check_dataflow_completeness(mutation.ir)

    if mutation.breaking:
        assert node in _wiring_ids(mutation.ir.entry)
        failure = _p04_failure(report)
        assert failure.location.path == ("START", node)
        assert failure.location.key == mutation.key
    else:
        assert node not in _wiring_ids(mutation.ir.entry)
        coverage = _dataflow_witness(report).coverage
        assert len(coverage) == 1
        assert coverage[0].satisfied_by
        assert "START" not in coverage[0].satisfied_by


@AT_SCALE
@given(mutation=dataflow_mutations(operators=("self-write",)))
def test_a_nodes_own_write_never_covers_its_own_read(mutation: Mutation) -> None:
    """MP-04-4. First-arrival semantics, stated as the case that would pass if ``IN`` were ``OUT``.

    ``IN[v]`` is the state *before* $v$ runs (§4.2), which is the runtime fact that the first
    lap of a loop whose entry is the reader sees the key unwritten. A validator that solved for
    ``OUT`` instead would report this document clean. ``downstream_writers`` stays absent for
    the same reason ``descendants`` excludes its own source: a self-writing reader is not wired
    after itself.
    """
    failure = _p04_failure(check_dataflow_completeness(mutation.ir))

    assert failure.location.node == mutation.node
    assert failure.location.key == mutation.key
    assert failure.downstream_writers is None
    assert failure.writers_on_other_paths is None


@AT_SCALE
@given(mutation=dataflow_mutations(operators=("unwritten-read", "self-write")))
def test_every_offending_path_is_a_real_start_path_avoiding_the_other_writers(
    mutation: Mutation,
) -> None:
    """MP-04-5. The attribution is checked against the graph, not taken on trust.

    §4.4 Step 4 defines the emitted path as a shortest ``START`` → reader path in the graph with
    $W_k \\setminus \\{v\\}$ removed, and A8 T5 makes the existence of such a path *equivalent*
    to the fixpoint's verdict — so this is the independent second opinion the two halves of P-04
    are supposed to meet on. Four things make it a real path: it starts at the sentinel, ends at
    the reader, every consecutive pair is an edge of the model, and it is simple. The fifth is
    the one the restriction buys: no interior vertex writes the key.
    """
    key = mutation.key
    assert key is not None
    path = _p04_failure(check_dataflow_completeness(mutation.ir)).location.path
    model = build_graph_model(mutation.ir, carry_unresolved_references=True)
    writers = {node.id for node in mutation.ir.nodes if key in _slot(node, "output")}

    assert path[0] == "START"
    assert path[-1] == mutation.node
    assert len(set(path)) == len(path)
    for tail, head in pairwise(path):
        assert model.has_edge(from_display(tail), from_display(head))
    assert not set(path[1:-1]) & writers


@AT_SCALE
@given(mutation=dataflow_mutations(operators=("foreign-read",)))
def test_a_read_of_a_key_outside_the_schema_is_not_p04s_finding(mutation: Mutation) -> None:
    """MP-04-6. The ``continue`` in §4.4 Step 4, and the reason it is written there.

    "Σ-membership is P-03's finding", never P-04's — so a read of an undeclared key raises no
    obligation: not a failure, and not a coverage entry claiming something covered it. Both
    halves are asserted, because a validator that reported the key *and* one that invented a
    coverage entry for it would each be minting a verdict for a property outside the wedge.
    """
    report = check_dataflow_completeness(mutation.ir)

    assert report.result == "pass"
    assert _dataflow_witness(report).coverage == ()


@AT_SCALE
@given(mutation=dataflow_mutations())
def test_the_witness_and_the_findings_partition_the_obligations(mutation: Mutation) -> None:
    """MP-04-7. Nothing is dropped and nothing is invented, over every operator at once.

    The obligation set is re-derived here from the surface — every (reachable reader, declared
    read that names a Σ key) pair — and the report is held to covering it exactly once: a
    coverage entry or a finding, never both and never neither. That is the completeness half of
    §0.3's "findings are never dropped" together with the soundness half a coverage count alone
    would miss. Every ``satisfied_by`` is checked too: each member is ``START`` exactly when the
    key is a boundary key, and every other member is an ancestor of the reader that writes it.
    """
    report = check_dataflow_completeness(mutation.ir)
    obligations = _obligations(mutation.ir)
    reported = {(_located(failure).node, _dataflow_key(failure)) for failure in _records(report)}
    entries = _dataflow_witness(report).coverage if report.witness is not None else ()
    covered = {(entry.node, entry.key) for entry in entries}

    assert covered | reported == obligations
    assert not covered & reported

    model = build_graph_model(mutation.ir, carry_unresolved_references=True)
    boundary = _boundary_keys(mutation.ir)
    for entry in entries:
        assert ("START" in entry.satisfied_by) == (entry.key in boundary)
        for writer in entry.satisfied_by:
            if writer == "START":
                continue
            assert entry.key in _writes(mutation.ir, writer)
            assert entry.node in model.descendants(writer)


@AT_SCALE
@given(mutation=dataflow_mutations(), position=st.integers(min_value=0, max_value=15))
def test_removing_a_write_never_repairs_a_dataflow_violation(
    mutation: Mutation, position: int
) -> None:
    """MP-04-8. The framework is gen-only, so the analysis is monotone in the declared writes.

    §4.4 Step 3 has no kill: ``OUT[v] = IN[v] ∪ writes(v)``. Dropping a node's ``output`` can
    therefore only shrink what reaches a reader, so the set of violated obligations can only
    grow — a pass may become a failure, a failure never becomes a pass, and no obligation that
    was violated becomes covered. Monotonicity is what makes P-04's verdict a property of the
    declared contract rather than of the order the analysis happened to converge in.
    """
    node = mutation.ir.nodes[position % len(mutation.ir.nodes)].id
    stripped = update_contract(mutation.ir, node, output=None)
    before = _violated(check_dataflow_completeness(mutation.ir))
    after = _violated(check_dataflow_completeness(stripped))

    assert before <= after


@AT_SCALE
@given(ir=workflow_irs(envelope=DEFAULT_ENVELOPE))
def test_dataflow_is_stable_under_irrelevant_mutation(ir: WorkflowIR) -> None:
    """MP-04-9. Three edits P-04's semantics say cannot matter, held to saying nothing.

    A **self-loop** adds the constraint ``IN[v] ⊆ IN[v] ∪ writes(v)``, which every solution
    already satisfies, so the greatest fixpoint does not move. A **rotation of ``nodes[]``**
    changes only a surface order the analysis sorts away (§4.4 Step 4 iterates the vertex set in
    the ledger §6 comparator). A **fresh Σ key nobody reads or writes** adds a bit to the lattice
    that no obligation quantifies over. Each is a different way a validator could accidentally
    depend on something §4.3 does not list among its fields.
    """
    baseline = check_dataflow_completeness(ir)
    looped = with_self_loop(ir, ir.nodes[0].id)
    widened = with_state_field(ir, _fresh_key(ir), "str")

    assert check_dataflow_completeness(looped) == baseline
    assert check_dataflow_completeness(permute_nodes(ir, 1)) == baseline
    assert check_dataflow_completeness(widened) == baseline


# ── MP-06-* — P-06 effect-safety (PROPERTY-CATALOG-SPEC §6) ──────────────────────────────


@AT_SCALE
@given(mutation=effect_safety_mutations(operators=("unprotected-retry-region",)))
def test_an_unprotected_trigger_in_a_retry_region_is_reported_there(mutation: Mutation) -> None:
    """MP-06-1. Arm (a) of ``retry_region`` decides the region without consulting the graph.

    §6.3 makes a declared ``retry_policy`` sufficient on its own — the runtime re-executes the
    node whether or not the graph loops back to it — so the condition is
    ``unprotected-effect-in-retry-region`` for every topology the draw produces, and the anchor
    carries a cycle only when the node happens to lie on one. §6.7 edge case 5 names this shape
    and DEC-13 left its corpus fixture open as a WA-04 item, so this is the only adversarial
    coverage it has.
    """
    location = _p06_location(check_effect_safety(mutation.ir))
    in_cycle = build_graph_model(mutation.ir).components.is_nontrivial(_node(mutation))

    assert location.node == mutation.node
    assert TRIGGER_TAGS & set(location.effect)
    assert location.idempotent is None
    assert (location.cycle is not None) == in_cycle


@AT_SCALE
@given(mutation=effect_safety_mutations(operators=("unprotected-cycle",)))
def test_an_unprotected_trigger_on_a_fresh_cycle_is_reported_with_that_cycle(
    mutation: Mutation,
) -> None:
    """MP-06-2. The other ERROR condition, on a cycle the operator built itself.

    The draw is acyclic and the operator adds one ``normal`` self-loop, so §6.4 Phase 2 makes
    the node's component non-trivial and DEC-13's Phase 3 rule — which seeds only on
    *conditional* intra-component edges — admits nothing. Region ``cycle`` rather than ``retry``
    therefore holds by construction, and the anchor is the shortest cycle there is: the loop.
    """
    node = _node(mutation)
    location = _p06_location(check_effect_safety(mutation.ir))

    assert location.node == node
    assert location.cycle == (node,)
    assert build_graph_model(mutation.ir).has_self_loop(node)


@AT_SCALE
@given(mutation=effect_safety_mutations(operators=("forbidden-combination",)))
def test_the_forbidden_combination_is_fatal_wherever_it_sits(mutation: Mutation) -> None:
    """MP-06-3. D-012's combination, and the two things §6.4 Phase 1 says about it.

    It is **cycle-independent** — the scan runs before any graph analysis, because a bare "the
    provider dedups" claim that no input field pins is a design error wherever it sits — and it
    **dominates the node**: DEC-05 D2's one-root-cause rule means Phase 4 emits no second,
    lesser finding about the same node, so the report carries exactly one record however the
    draw wired it.
    """
    report = check_effect_safety(mutation.ir)
    location = _p06_location(report)

    assert _condition_of(report) == IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT
    assert condition(IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT).severity == "fatal"
    assert location.node == mutation.node
    assert location.idempotent == "keyless"
    assert location.cycle is None
    assert len(_records(report)) == 1


@AT_SCALE
@given(mutation=effect_safety_mutations(operators=("bound-key",)))
def test_an_idempotency_key_protects_exactly_when_it_binds(mutation: Mutation) -> None:
    """MP-06-4. Protection is a binding test, not a presence test (§6.4 Phase 4).

    The two mutants differ in one place: whether the declared key is among the node's reads.
    ``mixed/06`` is the in-corpus precedent for the negative — a reference minted fresh on every
    lap stabilises nothing — and this pair says the same thing over generated topologies. The
    positive is read all the way to its record, so a validator that passed for some *other*
    reason would fail here.
    """
    node, key = _node(mutation), mutation.key
    bound = check_effect_safety(bound_key(mutation.origin, node, "billable").ir)
    unbound = check_effect_safety(unbound_key(mutation.origin, node, "billable").ir)

    records = _effect_witness(bound).effects
    assert len(records) == 1
    assert records[0].node == node
    assert records[0].protection == "idempotency_key"
    assert records[0].key == key
    assert records[0].region == "retry"

    assert _p06_location(unbound).node == node
    assert _condition_of(unbound) == UNPROTECTED_EFFECT_IN_RETRY_REGION


@AT_SCALE
@given(mutation=effect_safety_mutations(operators=("dangling-hook",)))
def test_a_compensation_hook_protects_exactly_when_it_resolves(mutation: Mutation) -> None:
    """MP-06-5. DEC-05 D7's side condition, both ways round.

    §6.1 restates the positive normatively — "a declared compensation hook discharges the P-06
    obligation exactly as a keyed idempotency declaration does" — and DEC-13 ratified the
    negative verbatim: a hook naming no node discharges nothing, the node falls through to the
    ordinary unprotected condition, and the bad id rides along as evidence rather than as a new
    condition ID. Keeping the §0.4 registry closed is the point of that last clause, so the
    evidence field is asserted rather than only the verdict.
    """
    node = _node(mutation)
    resolved = compensation_hook(mutation.origin, node, "billable", node)
    dangling = check_effect_safety(mutation.ir)

    records = _effect_witness(check_effect_safety(resolved.ir)).effects
    assert len(records) == 1
    assert records[0].protection == "compensation_hook"
    assert records[0].hook == node

    location = _p06_location(dangling)
    assert location.node == node
    assert location.dangling_compensation_hook is not None
    assert location.dangling_compensation_hook not in {n.id for n in mutation.ir.nodes}


@AT_SCALE
@given(mutation=effect_safety_mutations())
def test_every_cycle_p06_names_is_a_real_canonically_rotated_cycle(mutation: Mutation) -> None:
    """MP-06-6. D-10's named example — "every returned cycle witness names a real cycle".

    Three places P-06 can name a cycle, all checked the same way: the witness's inventory (one
    canonical anchor per non-trivial component, §6.4 Phase 5), a record's ``cycle``, and a
    failing location's ``cycle``. A named cycle must be simple, must close over real edges of
    the model, and must be rotated so its least id comes first (§0.3's ``CycleLocation``) — and
    where it anchors a node, that node must lie on it.
    """
    report = check_effect_safety(mutation.ir)
    model = build_graph_model(mutation.ir)

    if report.witness is not None:
        inventory = _effect_witness(report).cycles
        assert len(inventory) == len(model.components.nontrivial)
        for cycle in inventory:
            _assert_real_cycle(model, cycle)
        for record in _effect_witness(report).effects:
            # §6.3: the anchor is "absent iff the node lies on no cycle" — which is also why a
            # `retry_policy`-only region carries none.
            assert (record.cycle is not None) == _anchored(model, record.node)
            if record.cycle is not None:
                _assert_real_cycle(model, record.cycle)
                assert record.node in record.cycle
    for failure in _records(report):
        anchor = _located(failure)
        assert isinstance(anchor, P06NodeLocation)
        if anchor.cycle is not None:
            _assert_real_cycle(model, anchor.cycle)
            assert anchor.node in anchor.cycle


@AT_SCALE
@given(mutation=effect_safety_mutations())
def test_p06_accounts_for_exactly_the_trigger_tagged_nodes(mutation: Mutation) -> None:
    """MP-06-7. The obligation set is the trigger tags and nothing else (§6.3).

    ``{billable, irreversible}`` is the whole trigger set; ``network``, ``external``, ``audit``
    and user tags ride the evidence tuple and create no obligation. So a passing report records
    exactly the trigger-tagged nodes — never a node whose only tags are evidence, and never
    silently omitting one — and a failing report anchors every finding at a trigger-tagged node.
    Every operator here leaves exactly one such node, which is what makes the count assertable
    rather than merely the membership.
    """
    triggers = {node.id for node in mutation.ir.nodes if TRIGGER_TAGS & set(_slot(node, "effect"))}
    report = check_effect_safety(mutation.ir)

    assert len(triggers) == 1
    if report.witness is not None:
        assert {record.node for record in _effect_witness(report).effects} == triggers
    else:
        assert {_located(failure).node for failure in _records(report)} == triggers


@AT_SCALE
@given(ir=workflow_irs())
def test_effect_safety_is_stable_under_irrelevant_mutation(ir: WorkflowIR) -> None:
    """MP-06-8. Three edits §6.3 puts outside P-06's field list, held to changing no verdict.

    A **non-trigger effect tag** is evidence context, so it may widen the ``effect`` tuple a
    record echoes but can create no obligation. A **fresh Σ key** cannot matter at all: §6.3
    never reads ``state``. A **rotation of ``nodes[]``** is a surface order §6.4 sorts away in
    Phases 1 and 4. The verdict is what is compared rather than the whole report, precisely
    because the first edit *is* meant to show up in the evidence.
    """
    baseline = check_effect_safety(ir).result
    tagged = update_contract(ir, ir.nodes[0].id, effect=(*_slot(ir.nodes[0], "effect"), "audit"))

    assert check_effect_safety(tagged).result == baseline
    assert check_effect_safety(with_state_field(ir, _fresh_key(ir), "str")).result == baseline
    assert check_effect_safety(permute_nodes(ir, 1)) == check_effect_safety(ir)


# ── MP-08-* — P-08 determinism-replay (PROPERTY-CATALOG-SPEC §8, Appendix B) ─────────────


@AT_SCALE
@given(mutation=determinism_mutations(operators=("bare-claim",)))
def test_a_bare_claim_on_an_llm_backed_node_is_seed_unpinned(mutation: Mutation) -> None:
    """MP-08-1. Appendix B C-2, with the evidence §8.3 says the anchor carries.

    A bare ``deterministic: true`` pins no seed anywhere, so on a node whose effects evidence a
    remote provider call the claim is incoherent. The record stays WARNING and HEURISTIC
    whatever a CI gate does with it — §0.2's "strict mode changes the gate, never the record" —
    and the anchor names the declared form and the effect set that triggered C-1.
    """
    report = check_determinism_replay(mutation.ir)
    location = _p08_location(report)

    assert _condition_of(report) == SEED_UNPINNED
    assert location.node == mutation.node
    assert location.form == "bare-boolean"
    assert location.effects is not None
    assert LLM_EVIDENCE_TAGS & set(location.effects)
    assert _records(report)[0].severity == "warning"
    assert _records(report)[0].claim_class == "heuristic"


@AT_SCALE
@given(mutation=determinism_mutations(operators=("unpinned-temperature",)))
def test_pinning_the_temperature_to_zero_repairs_the_claim(mutation: Mutation) -> None:
    """MP-08-2. C-3 in both directions, on one node and one annotation slot.

    Absent temperature (the tutorial §7 case) and any nonzero value both fire; the comparison is
    numeric, so ``0`` and ``0.0`` are the same pinned value. The repair is read to its witness:
    a coherent LLM-backed claim carries the pinned pair, D-013's divergence-handling echo, and
    the mandatory provider caveat that says what a pinned declaration does *not* settle.
    """
    node = _node(mutation)
    broken = check_determinism_replay(mutation.ir)
    repaired = check_determinism_replay(pinned_claim(mutation.origin, node, "external", 7).ir)

    assert _condition_of(broken) == TEMPERATURE_UNPINNED
    location = _p08_location(broken)
    assert location.temperature is None or location.temperature != 0

    witness = _determinism_witness(repaired)
    assert len(witness.claims) == 1
    assert witness.claims[0].node == node
    assert witness.claims[0].llm_backed is True
    assert witness.claims[0].temperature == 0
    assert witness.claims[0].divergence_handling == "logged"
    assert witness.caveat == CAVEAT


@AT_SCALE
@given(mutation=determinism_mutations(operators=("bare-claim",)))
def test_dropping_the_llm_evidence_makes_the_same_claim_coherent(mutation: Mutation) -> None:
    """MP-08-3. C-1 is the gate, so the same annotation is fine without the evidence tags.

    The mutant and the repair declare the identical ``deterministic: true``; only the effect set
    differs. Pure local computation carries no pinning obligation, so the claim is recorded with
    its basis and — by §8.3's iff — the witness carries no caveat, because nothing in it depends
    on a provider honouring anything.
    """
    node = _node(mutation)
    assert check_determinism_replay(mutation.ir).result == "fail"

    witness = _determinism_witness(check_determinism_replay(local_claim(mutation.origin, node).ir))

    assert len(witness.claims) == 1
    assert witness.claims[0].llm_backed is False
    assert witness.claims[0].basis == "pure-local-computation"
    assert witness.claims[0].pinning_required is False
    assert witness.caveat is None


@AT_SCALE
@given(mutation=determinism_mutations())
def test_determinism_replay_does_not_couple_to_topology_or_the_schema(
    mutation: Mutation,
) -> None:
    """MP-08-4. §8.7's negative — "the validator must not couple to topology" — mechanized.

    P-08 is C(n)-local: §8.3 lists ``nodes[].id`` and two annotation slots as the fields read,
    and §8.7 states the exclusion deliberately. So rewiring the graph to a star (every node an
    entry and a finish, no edges) or to a chain, and widening $\\Sigma$ with a key nothing
    mentions, must all leave the report *identical* — not merely the same verdict. Both
    rewirings stay P-01 clean, so this is a claim about coupling rather than about how a
    validator behaves on a broken graph.
    """
    baseline = check_determinism_replay(mutation.ir)
    star = star_wiring(mutation.ir)
    chain = chain_wiring(mutation.ir)

    assert check_graph_well_formed(star).result == "pass"
    assert check_graph_well_formed(chain).result == "pass"
    assert check_determinism_replay(star) == baseline
    assert check_determinism_replay(chain) == baseline
    assert (
        check_determinism_replay(with_state_field(mutation.ir, _fresh_key(mutation.ir), "str"))
        == baseline
    )


@AT_SCALE
@given(mutation=determinism_mutations())
def test_the_claim_inventory_is_exactly_the_declared_claims(mutation: Mutation) -> None:
    """MP-08-5. Every declared claim is accounted for exactly once, and no other node is.

    §8.4 skips a node with no ``deterministic`` annotation **and** one carrying the explicit
    disclaimer ``deterministic: false`` — an author who writes the disclaimer is saying
    something, and what P-08 records about it is nothing. So the claiming nodes partition into
    the witness's ``claims`` and the report's findings, and the §8.3 caveat rides exactly when
    one of the recorded claims is LLM-backed.
    """
    claiming = {
        node.id
        for node in mutation.ir.nodes
        if _slot_value(node, "deterministic") not in (None, False)
    }
    report = check_determinism_replay(mutation.ir)
    reported = {_located(failure).node for failure in _records(report)}
    witness = report.witness
    claims = _determinism_witness(report).claims if witness is not None else ()

    assert {claim.node for claim in claims} | reported == claiming
    if witness is not None:
        assert (_determinism_witness(report).caveat is not None) == any(
            claim.llm_backed for claim in claims
        )
        assert _determinism_witness(report).claim_class == "heuristic"


@AT_SCALE
@given(mutation=determinism_mutations(operators=("bare-claim", "unpinned-temperature")))
def test_every_advisory_renders_the_appendix_b_warning_grammar(mutation: Mutation) -> None:
    """MP-08-6. The one place a P-08 report speaks to a person, held to §B.3's shape.

    Three paragraphs — the header that states the severity *and* the claim class so a reader
    cannot mistake a HEURISTIC advisory for a proof-backed finding, the diagnosis naming the
    node and the evidence tag that made C-1 fire, and the closing remediation §8.4 stores in
    ``Failure.remediation``. The evidence set is passed in rather than read off the anchor
    because §8.3 scopes ``effects`` to the seed-unpinned location; the temperature-unpinned
    anchor's evidence is the seed and temperature it declares.
    """
    node = _node(mutation)
    report = check_determinism_replay(mutation.ir)
    condition_id = _condition_of(report)
    effects = next(_slot(n, "effect") for n in mutation.ir.nodes if n.id == node)

    text = render_warning(condition_id, _p08_location(report), effects)
    paragraphs = text.split("\n\n")

    assert len(paragraphs) == 3
    assert paragraphs[0] == WARNING_HEADER
    assert node in paragraphs[1]
    assert any(tag in paragraphs[1] for tag in LLM_EVIDENCE_TAGS & set(effects))
    assert paragraphs[2] == render_remediation(condition_id)
    assert _records(report)[0].remediation == render_remediation(condition_id)


# ── MP-X-* — every operator at once ──────────────────────────────────────────────────────


@AT_SCALE
@given(mutation=mutations())
def test_every_validator_is_deterministic(mutation: Mutation) -> None:
    """MP-X-1. D-10's first named metaproperty: same IR, same verdict *and* same witness.

    Run twice on the mutant and twice on its origin, compared as whole models rather than as
    verdicts — a validator whose witness order depended on ``dict`` iteration or on ``hash``
    randomization would pass a verdict-only check and fail this one. Determinism is what makes
    a report diffable at all, which is the whole of the snapshot track's premise.
    """
    check = VALIDATORS[mutation.target]

    assert check(mutation.ir) == check(mutation.ir)
    assert check(mutation.origin) == check(mutation.origin)


@AT_SCALE
@given(mutation=mutations())
def test_every_emitted_condition_id_is_registered_and_correctly_graded(
    mutation: Mutation,
) -> None:
    """MP-X-2. §0.4 closure, checked on the records rather than on the source.

    A validator may never emit a condition ID the registry does not hold, and may never emit one
    the registry holds but has not ratified for emission (a PROPOSED or RESERVED name is a name
    and nothing more). Beyond membership, every record must carry the severity and claim class
    §0.4 *pins* for it — read off the registry here, so a regrade moves the expectation with the
    table instead of leaving a restated grade behind. And the emitting property must own the
    name: a report that borrowed another property's condition would be a cross-property finding,
    which §0.3 routes through ``advisories``, never through a same-property record.

    **What this does not attest.** It holds each *record* to the registry table, not the table
    to §0.4 — that is ``tests/verify/test_conditions.py``'s, which transcribes the section, plus
    the corpus comparison the golden harness runs. Today every finding is built through
    :mod:`gebra.verify.conditions`, which reads the grades off the table itself, so the teeth
    here are against a future validator that constructed a ``Failure`` directly: the models take
    ``severity`` and ``claim_class`` as ordinary fields, and nothing else would stop it.
    """
    report = VALIDATORS[mutation.target](mutation.ir)

    for record in _records(report):
        entry = condition(record.property_condition)
        assert is_emittable(record.property_condition)
        assert property_for_condition(record.property_condition) == mutation.target
        assert record.severity == entry.severity
        assert record.claim_class == entry.claim_class


@AT_SCALE
@given(mutation=mutations())
def test_every_report_round_trips_through_the_result_envelope(mutation: Mutation) -> None:
    """MP-X-3. A report validates as the §0.3 envelope it claims to be.

    D-10's list ends with "shrunk counterexamples still validate against the IR schema"; the
    same discipline applies on the way out, and it is what makes A6 PC-6 true — the *same*
    classes validate a fixture's ``expected:`` block and a validator's output, so a report that
    did not re-validate would be a shape no fixture could ever state. Re-validated from its own
    serialized form, so the union discrimination and the PC-4 profile are exercised rather than
    the in-memory object being handed back.
    """
    report = VALIDATORS[mutation.target](mutation.ir)

    assert validate_report(report.model_dump(by_alias=True, exclude_none=True)) == report


@AT_SCALE
@given(mutation=mutations())
def test_every_report_follows_the_one_property_one_report_packaging(
    mutation: Mutation,
) -> None:
    """MP-X-4. §0.3's packaging rule, over generated input rather than over the corpus.

    One property, one report: a witness exactly when the verdict is a pass, a failure exactly
    when it is not, and every further finding on ``co_failures`` rather than dropped or
    re-packaged.

    **Scope, because the envelope is wider than this row.** What is quantified here is a
    *single-property validator's own output*: it emits records for its own property and nothing
    else, so its co-failures are same-property and it writes no advisory — ``advisories`` is for
    cross-property WARNING findings (the ``mixed/03`` precedent, where P-08 findings ride a P-09
    primary), and a validator that put its own finding there would be describing itself as a
    bystander. The envelope itself admits both cross-property forms — ``mixed/01`` carries a
    ``retry-coherence`` co-failure on an effect-safety report — and composing them is the
    run-level wrapper's, which §0.3's scope boundary hands to REPORT-FORMAT-SPEC. VAL-11's
    composed report is therefore not held to this row.
    """
    report = VALIDATORS[mutation.target](mutation.ir)

    assert (report.result == "pass") == (report.witness is not None)
    assert (report.result == "fail") == (report.failure is not None)
    assert report.property == mutation.target
    if report.failure is not None:
        assert report.failure.advisories is None
        for co_failure in report.failure.co_failures or ():
            assert co_failure.property == mutation.target


@AT_SCALE
@given(mutation=mutations())
def test_sharing_a_graph_model_changes_no_result(mutation: Mutation) -> None:
    """MP-X-5. The seam ``verify()`` will pay for the graph build once through.

    P-04 and P-06 accept a pre-built model, and §0.3 gives each a *different* degradation
    convention for unresolved references — P-04 carries the phantom, P-06 skips the edge. §0.3
    warns in terms that those conventions are local and that "cross-validator agreement on
    ill-formed input is NOT promised"; what makes them agree *here* is that the input is
    P-01-clean, so there is no unresolved reference for either convention to act on and the flag
    is vacuous. All four combinations must therefore agree — each validator with its own
    convention and each with the other's — and that non-difference is what licenses one shared
    model per run. P-01 also takes a ``model=``; it is left out because its own suite pins it,
    and VAL-11 will be the card that shares one model across all four.

    **Scoped on ``well_formed`` since TE-09**, and by exactly the sentence above: a breaking P-01
    mutation produces a document with an unresolved reference, the flag stops being vacuous, and
    each validator's ``_model_for`` *refuses* a model built to the other's convention rather than
    silently mis-analysing it. So on that family the four combinations are not merely allowed to
    disagree — two of them are a documented ``ValueError``. Suite I holds the structural
    operators to their own claims.
    """
    if not mutation.well_formed:
        return
    for carry in (False, True):
        model = build_graph_model(mutation.ir, carry_unresolved_references=carry)
        assert check_dataflow_completeness(mutation.ir, model=model) == (
            check_dataflow_completeness(mutation.ir)
        )
        assert check_effect_safety(mutation.ir, model=model) == check_effect_safety(mutation.ir)


@AT_SCALE
@given(mutation=mutations())
def test_a_mutation_moves_exactly_its_own_targets_verdict(mutation: Mutation) -> None:
    """MP-X-6. D-10's "mutation strategies target exactly one property each", made checkable.

    The claim cannot be about the mutant alone — a random draw may already fail the property
    under test, and then "the mutation broke it" is unfalsifiable. It is about the *pair*: every
    operator normalizes its draw first, so the target passes on ``origin``, and what this
    quantifies is that between ``origin`` and ``ir`` the set of verdicts that moved is exactly
    ``{target}`` when the operator is breaking and empty when it is coherent. P-01 is in the
    comparison too, which is what says a contract or advisory mutation never quietly damages the
    topology the other verdicts are defined over (§0.3's P-01-clean precondition).

    The **condition ID** is asserted here rather than only the verdict, and that is what puts a
    test behind the operators' finer predictions: P-06 chooses between its two ERROR conditions
    *by region* (§6.4 Phase 4), so `unprotected-effect-in-cycle` versus
    `unprotected-effect-in-retry-region` is the observable difference between DEC-13's Phase 3
    rule holding and quietly not holding. Without it a region misclassification would leave
    every other assertion in the suite green.

    **What "exactly" means when the mutant is not well-formed.** A breaking P-01 mutation puts
    the document outside the surface §0.3 defines the other four results over, so the sweep is
    not run there: unreaching a node can legitimately move P-04's verdict (an unreachable reader
    raises no obligation), and asserting otherwise would be asserting agreement §0.3 declines to
    promise. What survives on that family is the half that is still the operator's own claim —
    the target's verdict moved, under the predicted condition — and suite I asserts the finding
    set in full.
    """
    report = VALIDATORS[mutation.target](mutation.ir)

    assert VALIDATORS[mutation.target](mutation.origin).result == "pass"
    if mutation.well_formed:
        moved = {
            slug
            for slug, check in VALIDATORS.items()
            if check(mutation.origin).result != check(mutation.ir).result
        }
        assert moved == ({mutation.target} if mutation.breaking else set())
    else:
        assert report.result == "fail"
    if mutation.breaking:
        assert report.failure is not None
        assert report.failure.property_condition == mutation.condition


@AT_SCALE
@given(mutation=mutations())
def test_every_mutant_is_still_well_formed_and_canonicalizable(mutation: Mutation) -> None:
    """MP-X-7. A mutant is a document, not a wreck — which is what makes the verdict mean something.

    Two claims, and only one of them is universal. **Every** mutant of every family stays a
    document: it serializes, loads back to the identical model, and canonicalizes to a
    ``graph_version``. Without that a counterexample could not be pasted into a fixture, put in a
    snapshot, or handed to anyone — and a P-01-*dirty* mutant needs it most, since an
    unresolvable reference is precisely the shape someone will want to paste somewhere.

    The **P-01-clean** half holds for every family but one: this file's operators break a
    *contract*, never the graph, so the mutant stays inside the surface §0.3 defines P-04's,
    P-06's and P-08's results over. TE-09's ``WELL_FORMEDNESS_OPERATORS`` break the graph on
    purpose, and :attr:`~gebra.testing.mutations.Mutation.well_formed` is what says so — asserted
    in *both* directions here, so an operator that claimed to break P-01 and did not (or the
    reverse) fails rather than quietly narrowing the row.
    """
    for candidate in (mutation.origin, mutation.ir):
        assert load_json(WorkflowIR, dump_json(candidate)) == candidate
        assert graph_version(candidate).startswith("sha256:")

    assert check_graph_well_formed(mutation.origin).result == "pass"
    assert (check_graph_well_formed(mutation.ir).result == "pass") == mutation.well_formed


# ── Non-vacuity: the shapes the operators have to be able to reach ───────────────────────


def _reaches_condition(condition_id: ConditionId) -> Callable[[Mutation], bool]:
    return lambda mutation: mutation.condition == condition_id


def _entry_reader(mutation: Mutation) -> bool:
    return mutation.operator == "universal-write" and mutation.breaking


def _non_entry_reader(mutation: Mutation) -> bool:
    return mutation.operator == "universal-write" and not mutation.breaking


def _cyclic_mutant(mutation: Mutation) -> bool:
    return bool(build_graph_model(mutation.ir).components.nontrivial)


def _absent_temperature(mutation: Mutation) -> bool:
    if mutation.operator != "unpinned-temperature":
        return False
    node = next(n for n in mutation.ir.nodes if n.id == mutation.node)
    return _slot_value(node, "deterministic").temperature is None


def _positive_temperature(mutation: Mutation) -> bool:
    if mutation.operator != "unpinned-temperature":
        return False
    node = next(n for n in mutation.ir.nodes if n.id == mutation.node)
    temperature = _slot_value(node, "deterministic").temperature
    return temperature is not None and temperature > 0


#: One entry per shape the suite above would pass vacuously without. A generator that stopped
#: producing any of them still satisfies every metaproperty — which is what makes this table the
#: quality gate D-10's risk register asks for ("coverage assertions on generated corpora").
SHAPES: Final[tuple[tuple[str, Callable[[Mutation], bool]], ...]] = (
    (
        "a fatal irreversible + keyless finding",
        _reaches_condition(IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT),
    ),
    (
        "an unprotected effect in a retry region",
        _reaches_condition(UNPROTECTED_EFFECT_IN_RETRY_REGION),
    ),
    ("an unprotected effect in a plain cycle", _reaches_condition(UNPROTECTED_EFFECT_IN_CYCLE)),
    ("a dataflow violation", _reaches_condition(READ_KEY_NEVER_WRITTEN_ON_PATH)),
    ("a seed-unpinned advisory", _reaches_condition(SEED_UNPINNED)),
    ("a temperature-unpinned advisory", _reaches_condition(TEMPERATURE_UNPINNED)),
    ("a coherent mutation", lambda mutation: not mutation.breaking),
    ("a reader that is an entry node", _entry_reader),
    ("a reader that is not an entry node", _non_entry_reader),
    ("a mutant carrying a cycle", _cyclic_mutant),
    ("a claim with no temperature at all", _absent_temperature),
    ("a claim with a positive temperature", _positive_temperature),
    ("a mutant over three or more nodes", lambda mutation: len(mutation.ir.nodes) >= 3),
    ("a mutant with a populated state schema", lambda mutation: bool(mutation.ir.state)),
)


@pytest.mark.parametrize(("description", "predicate"), SHAPES, ids=[name for name, _ in SHAPES])
def test_the_operator_library_can_produce(
    description: str, predicate: Callable[[Mutation], bool]
) -> None:
    """``find`` locates a witness, or raises ``NoSuchExample`` naming the shape that went missing."""
    witness = find(mutations(), predicate, settings=REACH)

    assert predicate(witness), description


@pytest.mark.parametrize(
    "operator", [*DATAFLOW_OPERATORS, *EFFECT_SAFETY_OPERATORS, *DETERMINISM_OPERATORS]
)
def test_every_operator_is_reachable_by_name(operator: str) -> None:
    """Every row of :data:`~gebra.testing.mutations.OPERATORS` really produces its mutation.

    The named-subset seam is what the sharp metaproperties above select with, so an operator
    that silently stopped being offered would make one of them quantify over nothing while
    still passing.
    """
    slug = next(name for name, table in OPERATORS.items() if operator in table)
    strategy = {
        "dataflow-completeness": dataflow_mutations,
        "effect-safety": effect_safety_mutations,
        "determinism-replay": determinism_mutations,
    }[slug](operators=(operator,))

    witness = find(strategy, lambda mutation: True, settings=REACH)

    assert witness.operator == operator
    assert witness.target == slug


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _node(mutation: Mutation) -> str:
    """The anchor node an operator injected at — every operator in this suite names one."""
    assert mutation.node is not None
    return mutation.node


def _slot(node: Any, name: str) -> tuple[str, ...]:
    """One tuple-valued annotation slot of ``node``, empty when absent (omit-normalized)."""
    value = _slot_value(node, name)
    return value or ()


def _slot_value(node: Any, name: str) -> Any:
    """One annotation slot of ``node``, or ``None`` when it carries no contract."""
    annotations: Annotations | None = node.annotations
    return None if annotations is None else getattr(annotations, name)


def _wiring_ids(wiring: str | tuple[str, ...]) -> tuple[str, ...]:
    """``entry``/``finish`` as a tuple, whichever of the two §2.1 surface forms it is in."""
    return (wiring,) if isinstance(wiring, str) else wiring


def _fresh_key(ir: WorkflowIR) -> str:
    """A state key the workflow does not declare and no contract mentions."""
    candidate = "gebra_inert_key"
    while candidate in (ir.state or {}):
        candidate += "_"
    return candidate


def _records(report: PropertyReport) -> list[Any]:
    """Every emitted record of a report: the primary failure and each co-failure (§0.3)."""
    if report.failure is None:
        return []
    return [report.failure, *(report.failure.co_failures or ())]


def _located(record: Any) -> Any:
    """The location a record anchors at, whatever concrete subtype it is."""
    location: AnyLocation = record.location
    return location


def _condition_of(report: PropertyReport) -> ConditionId:
    """The primary finding's condition ID."""
    assert report.failure is not None, report
    return report.failure.property_condition


def _violated(report: PropertyReport) -> set[tuple[str, str]]:
    """Every (reader, key) obligation a P-04 report says is violated."""
    return {(_located(record).node, _located(record).key) for record in _records(report)}


def _dataflow_key(record: Any) -> str:
    key: str = record.location.key
    return key


def _p04_failure(report: PropertyReport) -> P04Failure:
    failure = report.failure
    assert isinstance(failure, P04Failure), report
    return failure


def _dataflow_witness(report: PropertyReport) -> DataflowWitness:
    witness = report.witness
    assert isinstance(witness, DataflowWitness), report
    return witness


def _p06_location(report: PropertyReport) -> P06NodeLocation:
    assert report.failure is not None, report
    location = report.failure.location
    assert isinstance(location, P06NodeLocation), report
    return location


def _effect_witness(report: PropertyReport) -> EffectSafetyWitness:
    witness = report.witness
    assert isinstance(witness, EffectSafetyWitness), report
    return witness


def _p08_location(report: PropertyReport) -> DeterminismNodeLocation:
    assert report.failure is not None, report
    location = report.failure.location
    assert isinstance(location, DeterminismNodeLocation), report
    return location


def _determinism_witness(report: PropertyReport) -> DeterminismWitness:
    witness = report.witness
    assert isinstance(witness, DeterminismWitness), report
    return witness


def _writes(ir: WorkflowIR, node_id: str) -> tuple[str, ...]:
    """One node's declared ``output``, empty when absent."""
    return next(_slot(node, "output") for node in ir.nodes if node.id == node_id)


def _boundary_keys(ir: WorkflowIR) -> set[str]:
    """$I_0$ — the keys ``state`` declares ``optional: true`` (§4.2 "Graph inputs")."""
    return {
        key
        for key, field in (ir.state or {}).items()
        if not isinstance(field, str) and bool(field.optional)
    }


def _obligations(ir: WorkflowIR) -> set[tuple[str, str]]:
    """Every (reachable reader, declared read naming a Σ key) pair — §4.4 Steps 2 and 4."""
    model = build_graph_model(ir, carry_unresolved_references=True)
    reachable = model.descendants(START_VERTEX) | {START_VERTEX}
    declared = set(ir.state or {})
    return {
        (node.id, key)
        for node in ir.nodes
        if node.id in reachable
        for key in _slot(node, "input")
        if key in declared
    }


def _anchored(model: GraphModel, node_id: str) -> bool:
    """Whether ``node_id`` lies on a cycle — P-06's ``in_cycle`` (§6.4 Phase 2)."""
    return model.components.is_nontrivial(node_id)


def _assert_real_cycle(model: GraphModel, cycle: tuple[str, ...]) -> None:
    """A named cycle is simple, closes over real edges, and is canonically rotated (§0.3).

    The rotation is checked against §0.3's rule — "lexicographically-least id first", under the
    ledger §6 comparator — rather than against ``canonical_rotation``'s own output, which would
    only attest that the validator's helper is idempotent.
    """
    assert cycle
    assert len(set(cycle)) == len(cycle)
    assert cycle[0] == min(cycle, key=ledger_sort_key)
    for tail, head in zip(cycle, (*cycle[1:], cycle[0])):
        assert model.has_edge(tail, head), (tail, head, cycle)
