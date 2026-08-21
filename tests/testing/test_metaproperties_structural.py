"""Metaproperty suite I — the structural validators under mutation (TE-09, D-10 W7/W10).

A *metaproperty* is a claim about a **validator**, quantified over generated input, rather than
a claim about one workflow. The corpus says what P-01 and P-02 answer on sixty authored
documents; this suite says what they answer on documents nobody authored, and — through
:mod:`gebra.testing.mutations` — on documents built to break the *topology* at exactly one
point, or to carry a cycle whose only termination witness has just been taken away.

**The acceptance box, and how it is discharged.** TE-09 asks for "≥10 structural metaproperties
[passing] at 1000+ examples". :data:`METAPROPERTIES` is the machine-checked count:
:func:`test_the_structural_metaproperty_table_is_the_suite` holds it to the module — every
``@given`` test here has a row, every row names a test that exists, and every one of them runs
under :data:`AT_SCALE`, so a later quiet reduction of the example count, or a quietly deleted
metaproperty, fails a test instead of weakening a claim that keeps its name.

**Suite II is not in this file.** TE-10 owns the contract and advisory metaproperties (P-04,
P-06, P-08) in ``tests/testing/test_metaproperties_contract.py``, together with the shared
:class:`~gebra.testing.mutations.Mutation` record, the operator library, and the cross-cutting
``MP-X-*`` rows that quantify over *every* registered operator whatever its target. Those rows
cover this card's operators the day they land, which is why nothing here restates determinism,
§0.4 registry closure, envelope round-tripping or "exactly one verdict moves". What this file
adds is everything those rows cannot say without knowing which property is under test.

**Three kinds of claim**, and the ids say which:

* ``MP-01-*`` — P-01 ``graph-well-formed``: each of the four §1 conditions injected on its own,
  the §1.4 Step 5 root-cause order, DEC-12's five reference sites, the pass witness read back
  against the graph, and §1.3's "Not read" list quantified as a stability claim.
* ``MP-02-*`` — P-02 ``termination-witness``: each removable witness form taken away, the D4
  wiring pair, the reality of every cycle the validator names, and the acyclicity certificate
  re-checked as a topological order rather than trusted.
* ``MP-S-*`` — both structural validators at once: the findings held to an **independent**
  derivation of the conditions, computed from the surface without the shared graph model.

**The one asymmetry with suite II**, stated because it decides several rows: a breaking P-01
mutation produces a document that is *not* well-formed, and §0.3 defines P-02's, P-04's and
P-06's results only over P-01-clean topology ("cross-validator agreement on ill-formed input is
NOT promised"). So no row here asserts what another validator says about a P-01-dirty mutant,
and :attr:`~gebra.testing.mutations.Mutation.well_formed` is the flag the cross-cutting rows in
suite II scope on.

Everything here is pure data (WA-07): the strategies build frozen pydantic values, the operators
rewrite them into new frozen pydantic values, and everything executed is in-repo and hermetic —
the two structural validators, VAL-03's shared graph pre-analysis, VAL-06's syntactic guard
recognizer (:mod:`re` over declared text, never a parse of Python) and the §0.3 envelope models.
The runtime tripwire is ``tests/testing/test_hermeticity.py``, whose guarded child draws a
structural mutation and runs P-01 and P-02 over both halves with substrate imports, sockets and
name resolution all raising.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

import pytest
from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st

from gebra.ir import (
    Annotations,
    Checkpointer,
    ConditionalEdge,
    DeterministicSpec,
    Node,
    NormalEdge,
    RetryPolicy,
    Runtime,
    WorkflowIR,
)
from gebra.testing.mutations import (
    PROBE_BOUND,
    PROBE_ELSE_LABEL,
    PROBE_THEN_LABEL,
    TERMINATION_OPERATORS,
    WELL_FORMEDNESS_OPERATORS,
    Mutation,
    acyclic_envelope,
    counter_guard_with_exit,
    counter_guard_without_exit,
    dead_end_node,
    termination_mutations,
    well_formedness_mutations,
    wired_leaf,
    with_edge,
    with_self_loop,
    with_state_field,
)
from gebra.testing.strategies import DEFAULT_ENVELOPE, END_LITERAL, workflow_irs
from gebra.verify.base import ConditionId, from_display
from gebra.verify.graph import END_VERTEX, GraphModel, build_graph_model, ledger_sort_key
from gebra.verify.locations import (
    EdgeLocation,
    NodeLocation,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
)
from gebra.verify.properties.graph_well_formed import (
    DEAD_END_NODE_NOT_WIRED_TO_END,
    EDGE_TARGET_UNDEFINED,
    NODE_UNREACHABLE_FROM_START,
    ORPHAN_NODE,
    PATH_MAP_TARGET_UNDEFINED,
    check_graph_well_formed,
)
from gebra.verify.properties.termination_witness import (
    COUNTER_GUARD_WITHOUT_EXIT_EDGE,
    CYCLE_WITHOUT_TERMINATION_WITNESS,
    check_termination_witness,
    strict_promotions,
)
from gebra.verify.report import PropertyReport
from gebra.verify.witnesses import (
    CounterGuardSource,
    GuardEdgeRef,
    TerminationWitness,
    WellFormednessWitness,
)

#: The example count the card's acceptance box asks for ("1000+ examples"). Named, and floored
#: by :func:`test_the_structural_metaproperty_table_is_the_suite`, so a later quiet reduction
#: fails the suite rather than passing a weaker claim under the same test names.
AT_SCALE_EXAMPLES: Final = 1000

#: How many structural metaproperties this card's acceptance box asks for.
STRUCTURAL_TARGET: Final = 10

#: The profile every metaproperty runs under, taken from TE-08's and TE-10's suites point for
#: point: no health check is suppressed (the box says the suite is green, and ``filter_too_much``
#: / ``too_slow`` / ``data_too_large`` are exactly what a badly-composed mutation strategy would
#: trip), and the deadline is *raised* rather than removed — a mutation plus one validator run
#: measures a few milliseconds, so one second is a wide margin over CI scheduling noise while a
#: pathological slowdown still trips it.
AT_SCALE: Final = settings(max_examples=AT_SCALE_EXAMPLES, deadline=timedelta(seconds=1))

#: The budget a reachability :func:`hypothesis.find` gets. Derandomized because these are
#: existence assertions rather than a hunt for defects, and the shrink phase is dropped: "can
#: this shape be produced" does not need the smallest witness, and shrinking it is most of the
#: cost.
REACH: Final = settings(
    max_examples=3000,
    deadline=None,
    database=None,
    derandomize=True,
    phases=(Phase.generate,),
)

#: Where a structural operator hangs its new wiring, when a row needs to build both polarities of
#: one edit from the *same* draw. Bounded rather than drawn from the node list, because the node
#: count is itself drawn — the modulo below is what makes any value legal.
POSITIONS: Final = st.integers(min_value=0, max_value=15)

#: The P-01 operators that inject no unresolved reference. ``MP-S-1``'s hand derivation covers
#: conditions (i)–(iii) only, so it quantifies over exactly these — condition (iv) is
#: ``MP-01-5``'s, where each of DEC-12's five sites is asserted individually.
RESOLVING_OPERATORS: Final[tuple[str, ...]] = (
    "unreachable-node",
    "severed-edge",
    "dead-end-node",
    "orphan-node",
    "empty-entry",
    "wired-leaf",
)

#: The five DEC-12 reference sites, as operator names.
DANGLING_OPERATORS: Final[tuple[str, ...]] = (
    "undefined-entry-id",
    "undefined-finish-id",
    "undefined-edge-source",
    "undefined-edge-target",
    "undefined-path-map-target",
)


# ── The table the acceptance box is counted from ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Metaproperty:
    """One row of the structural metaproperty library.

    The same four fields suite II's row carries, declared here rather than imported from it: a
    test module importing another test module couples two collections for the sake of a record
    with no behaviour, and the two tables are counted independently anyway (the card's box is
    "≥10 structural", TE-10's was "≥20 combined").

    Attributes:
        id: Stable identifier; the prefix names the target (``MP-01``/``MP-02``/``MP-S``).
        target: The property slug the claim is about, or ``"*"`` for a claim that quantifies
            over both structural validators at once.
        test: The name of the test function in this module that runs it.
        claim: The claim in one line — what a reader of a CI failure needs before the traceback.
    """

    id: str
    target: str
    test: str
    claim: str


#: The library. One row per ``@given`` metaproperty in this module, in file order; the row and
#: the function are held to each other by
#: :func:`test_the_structural_metaproperty_table_is_the_suite`.
METAPROPERTIES: Final[tuple[Metaproperty, ...]] = (
    Metaproperty(
        "MP-01-1",
        "graph-well-formed",
        "test_a_node_nothing_wires_to_is_unreachable_and_nothing_else",
        "a declared node with no inbound wiring is one finding, condition (i)",
    ),
    Metaproperty(
        "MP-01-2",
        "graph-well-formed",
        "test_severing_the_only_inbound_edge_unreaches_exactly_that_node",
        "deleting one edge moves exactly one node out of reachable_from_start",
    ),
    Metaproperty(
        "MP-01-3",
        "graph-well-formed",
        "test_a_new_leaf_is_a_dead_end_exactly_when_finish_does_not_carry_it",
        "condition (ii) turns on finish membership and on nothing else",
    ),
    Metaproperty(
        "MP-01-4",
        "graph-well-formed",
        "test_an_orphan_is_primary_over_the_two_conditions_it_cascades_into",
        "the §1.4 Step 5 order (iv)→(iii)→(i)→(ii), on the one shape that shows it",
    ),
    Metaproperty(
        "MP-01-5",
        "graph-well-formed",
        "test_every_unresolved_reference_is_one_finding_at_its_own_site",
        "DEC-12's five sites, each one finding, split across the two condition IDs",
    ),
    Metaproperty(
        "MP-01-6",
        "graph-well-formed",
        "test_emptying_entry_unreaches_exactly_every_declared_node",
        "with no root, the finding set is V in ledger order and nothing else moves",
    ),
    Metaproperty(
        "MP-01-7",
        "graph-well-formed",
        "test_graph_well_formed_reads_only_the_topology",
        "Σ, contracts, runtime and router conditions leave the report equal (§1.3)",
    ),
    Metaproperty(
        "MP-01-8",
        "graph-well-formed",
        "test_the_pass_witness_is_exactly_the_graph_it_describes",
        "the witness re-derives from the surface, and names no id outside V",
    ),
    Metaproperty(
        "MP-01-9",
        "graph-well-formed",
        "test_graph_well_formed_is_cycle_agnostic",
        "adding a self-loop or a back edge leaves the report identical (§1.1)",
    ),
    Metaproperty(
        "MP-02-1",
        "termination-witness",
        "test_removing_a_variant_witness_flips_the_verdict",
        "form (c) discharges its carrier's cycles; without it the SCC is reported",
    ),
    Metaproperty(
        "MP-02-2",
        "termination-witness",
        "test_removing_the_blanket_witness_flips_the_verdict",
        "form (b) passes with the §6.1 WARNING note and one strict promotion",
    ),
    Metaproperty(
        "MP-02-3",
        "termination-witness",
        "test_a_variant_key_outside_the_schema_discharges_nothing_and_is_noted",
        "form (c) is a membership test; the near-miss rides a note on the fail path",
    ),
    Metaproperty(
        "MP-02-4",
        "termination-witness",
        "test_a_counter_guard_discharges_exactly_when_a_label_leaves_its_loop",
        "D4: the gated then-label edge alone enters S, and only with a wired escape",
    ),
    Metaproperty(
        "MP-02-5",
        "termination-witness",
        "test_every_cycle_p02_names_is_a_real_canonically_rotated_cycle",
        "representative, anchor and census cycles all close over real edges",
    ),
    Metaproperty(
        "MP-02-6",
        "termination-witness",
        "test_the_acyclicity_certificate_is_a_topological_order_of_the_residual",
        "the §6.2 certificate is re-checked against the residual, not trusted",
    ),
    Metaproperty(
        "MP-02-7",
        "termination-witness",
        "test_termination_witness_reads_only_its_declared_fields",
        "every contract slot but variant, and every runtime slot but the limit, is inert",
    ),
    Metaproperty(
        "MP-S-1",
        "*",
        "test_the_findings_are_an_independent_derivation_of_the_conditions",
        "reachability, sinks and orphans re-derived from the surface agree exactly",
    ),
)


def test_the_structural_metaproperty_table_is_the_suite() -> None:
    """The count the acceptance box is judged on, held to the code rather than to prose.

    Four ways the table and the module can drift apart, all closed here: a row naming a test
    that does not exist; a ``@given`` test with no row (which would make the count an
    understatement, but also means an unnamed claim); a duplicated id; and — the one that
    matters most — a metaproperty that quietly stopped running at a thousand examples, or that
    started suppressing a health check to stay green. The settings are read off the decorated
    function rather than trusted, because ``@AT_SCALE`` on the wrong side of ``@given``, or
    simply forgotten, is silent otherwise.
    """
    assert len(METAPROPERTIES) >= STRUCTURAL_TARGET
    assert STRUCTURAL_TARGET >= 10
    assert AT_SCALE_EXAMPLES >= 1000
    assert AT_SCALE.max_examples == AT_SCALE_EXAMPLES
    assert AT_SCALE.suppress_health_check == ()
    assert set(HealthCheck) - set(AT_SCALE.suppress_health_check) == set(HealthCheck)

    identifiers = [row.id for row in METAPROPERTIES]
    assert len(set(identifiers)) == len(identifiers)
    assert {row.target for row in METAPROPERTIES} == {
        "graph-well-formed",
        "termination-witness",
        "*",
    }

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


# ── MP-01-* — P-01 graph-well-formed (PROPERTY-CATALOG-SPEC §1) ──────────────────────────


@AT_SCALE
@given(mutation=well_formedness_mutations(operators=("unreachable-node",)))
def test_a_node_nothing_wires_to_is_unreachable_and_nothing_else(mutation: Mutation) -> None:
    """MP-01-1. Condition (i) injected on its own, and read back as a single finding.

    The new node is listed in ``finish``, and that is what isolates the condition rather than
    decorating it: under (m2) the membership gives the node an edge to ``__end__``, so condition
    (ii)'s sink scan passes over it, and under Reading A (DEC-11) the membership *is* edge
    participation, so condition (iii) does too. Nothing wires ``__start__`` to it. So a validator
    that reported anything besides one ``node-unreachable-from-start`` would be reporting
    something the document does not say.
    """
    assert check_graph_well_formed(mutation.origin).result == "pass"

    failure = _failure(check_graph_well_formed(mutation.ir))

    assert failure.property_condition == NODE_UNREACHABLE_FROM_START
    assert failure.location == mutation.location
    assert failure.co_failures is None


@AT_SCALE
@given(mutation=well_formedness_mutations(operators=("severed-edge",)))
def test_severing_the_only_inbound_edge_unreaches_exactly_that_node(mutation: Mutation) -> None:
    """MP-01-2. The card's own example: removing an edge breaks the reachability verdict.

    The pair differs by exactly one member of ``edges`` — the operator attaches a leaf first, so
    that the *origin* is a clean document one node wider than the draw and the deletion has one
    consequence instead of a distribution of them. Both directions are asserted: the leaf is in
    the origin's ``reachable_from_start`` and it is the mutant's one finding. The source keeps
    its other wiring, and if the deletion left it a sink it was already one in the clean draw and
    is therefore in ``finish``, so condition (ii) stays silent there too.
    """
    node = _node(mutation)
    before = check_graph_well_formed(mutation.origin)
    after = check_graph_well_formed(mutation.ir)

    assert len(mutation.origin.edges) == len(mutation.ir.edges) + 1
    assert node in _witness(before).reachable_from_start

    failure = _failure(after)
    assert failure.property_condition == NODE_UNREACHABLE_FROM_START
    assert failure.location == NodeLocation(kind="node", node=node)
    assert failure.co_failures is None


@AT_SCALE
@given(ir=workflow_irs(envelope=DEFAULT_ENVELOPE), position=POSITIONS)
def test_a_new_leaf_is_a_dead_end_exactly_when_finish_does_not_carry_it(
    ir: WorkflowIR, position: int
) -> None:
    """MP-01-3. Both polarities of one field, from one draw — the sink scan, isolated.

    §1.4 Step 4 is a scan over $G^*$, and ``finish`` membership is what supplies the (m2) edge to
    ``__end__``: the *same* new node, reached by the *same* new edge, is a
    ``dead-end-node-not-wired-to-end`` without the membership and clean with it. That is the
    catalog-literal reading, and it is also what says a trap component is out of scope — the
    scan asks about out-degree, never about whether ``__end__`` is reachable (PD-007 Q1, VAL-D1;
    DEC-12's closing line).
    """
    source = ir.nodes[position % len(ir.nodes)].id
    stranded = dead_end_node(ir, source)
    wired = wired_leaf(ir, source)

    failure = _failure(check_graph_well_formed(stranded.ir))
    assert failure.property_condition == DEAD_END_NODE_NOT_WIRED_TO_END
    assert failure.location == NodeLocation(kind="node", node=_node(stranded))
    assert failure.co_failures is None

    repaired = check_graph_well_formed(wired.ir)
    assert repaired.result == "pass"
    assert _node(wired) in _witness(repaired).terminal_nodes


@AT_SCALE
@given(mutation=well_formedness_mutations(operators=("orphan-node",)))
def test_an_orphan_is_primary_over_the_two_conditions_it_cascades_into(
    mutation: Mutation,
) -> None:
    """MP-01-4. §1.4 Step 5's root-cause order, on the one shape that can observe it.

    A node in no edge, in no ``entry`` and in no ``finish`` violates (iii), (i) and (ii) at once,
    and the document cannot make it fewer — so this is the only injection where *which* finding
    is primary is a decision rather than an accident. Step 5's order is
    (iv) → (iii) → (i) → (ii), so ``orphan-node`` fills ``failure`` and the other two ride
    ``co_failures`` in that order, all three anchored at the same node. A validator that ordered
    by condition number would fail exactly the same documents and still be wrong here: the
    primary is what a reader is told to fix first.
    """
    node = _node(mutation)
    failure = _failure(check_graph_well_formed(mutation.ir))

    assert failure.property_condition == ORPHAN_NODE
    assert failure.location == mutation.location
    assert [(co.property_condition, co.location) for co in failure.co_failures or ()] == [
        (NODE_UNREACHABLE_FROM_START, NodeLocation(kind="node", node=node)),
        (DEAD_END_NODE_NOT_WIRED_TO_END, NodeLocation(kind="node", node=node)),
    ]


@AT_SCALE
@given(mutation=well_formedness_mutations(operators=DANGLING_OPERATORS))
def test_every_unresolved_reference_is_one_finding_at_its_own_site(mutation: Mutation) -> None:
    """MP-01-5. DEC-12's scope, quantified: five sites, two condition IDs, one finding each.

    The split is DEC-05 D4's rule read through DEC-12: a dangling ``path_map`` value keeps its
    own ID because it is diagnostically distinct — the anchor names a *label* — while the other
    four sites share ``edge-target-undefined``, since "a reference names a node that does not
    exist" is one defect four ways. Three things are asserted beyond the ID. The anchor is the
    vertex a person would edit, and it differs per site (``START`` for a bad root, the id itself
    for a bad ``finish`` id or an unresolved ``from``, the router for a dangling label). The
    anchor's own ``target`` stays omitted, per §0.3's dangling-label rule. And there is exactly
    one finding even for ``undefined-edge-source``, whose edge carries *two* references — §1.4
    Step 1 ``continue``s past the ``to`` of an edge whose ``from`` is unresolved, so a model that
    helpfully checked it too would emit two.
    """
    assert check_graph_well_formed(mutation.origin).result == "pass"

    failure = _failure(check_graph_well_formed(mutation.ir))
    location = failure.location
    assert isinstance(location, P01EdgeLocation)

    expected = (
        PATH_MAP_TARGET_UNDEFINED
        if mutation.operator == "undefined-path-map-target"
        else EDGE_TARGET_UNDEFINED
    )
    assert failure.property_condition == expected
    assert failure.location == mutation.location
    assert failure.co_failures is None
    assert location.target is None
    assert location.undefined_target not in {node.id for node in mutation.ir.nodes}


@AT_SCALE
@given(mutation=well_formedness_mutations(operators=("empty-entry",)))
def test_emptying_entry_unreaches_exactly_every_declared_node(mutation: Mutation) -> None:
    """MP-01-6. The widest single-field break there is, and its finding set is exactly $V$.

    DEC-18 ratifies the empty list as a *value*, so this is a well-typed document that (m1) wires
    ``__start__`` to nothing: condition (i) fails at every node. Nothing else moves, and that is
    the part worth quantifying — a node with no explicit edge incidence was a sink in the clean
    draw and is therefore in ``finish``, which both keeps condition (ii) silent and keeps it out
    of condition (iii) under Reading A. The emission order is ledger §6 over $V$, so the primary
    is the ledger-least node; ``sorted(...)`` here is the same comparator §1.4 Steps 2–4 iterate.
    """
    declared = [node.id for node in mutation.ir.nodes]
    findings = _findings(check_graph_well_formed(mutation.ir))

    assert [condition for condition, _ in findings] == [NODE_UNREACHABLE_FROM_START] * len(declared)
    assert [location.node for _, location in findings] == sorted(declared, key=ledger_sort_key)
    assert findings[0][1] == mutation.location


@AT_SCALE
@given(ir=workflow_irs(envelope=DEFAULT_ENVELOPE))
def test_graph_well_formed_reads_only_the_topology(ir: WorkflowIR) -> None:
    """MP-01-7. §1.3's "Not read" list, quantified rather than reviewed.

    P-01 reads ``entry``, ``finish``, ``nodes[].id`` and ``edges[].{from,to,kind,path_map}``, and
    §1.3 names the rest by exclusion: ``state``, ``annotations``, ``runtime``, and the
    ``condition`` router strings. Each is edited here in the way most likely to matter to a
    validator that had drifted — a widened Σ, a fully populated contract on every node, a
    ``runtime`` block, and every router's guard rewritten — and the report must be **equal**, not
    merely the same verdict. The router-condition case is the one with teeth: a validator reading
    guards would be reaching into P-02's and P-05's business, and would still pass a
    verdict-level check on almost every draw.
    """
    baseline = check_graph_well_formed(ir)
    # `pure=False` rather than `True`: ANNOTATION-API-SPEC §1 makes `pure: true` and a non-empty
    # `effect` mutually exclusive (decision D-011), and while P-01 reads neither slot, this file
    # names every deliberate cross-field violation at the place it is made — an unnamed one here
    # would be the exception that teaches a reader they are decoration.
    annotated = _annotate(
        ir,
        pure=False,
        effect=("billable", "irreversible"),
        deterministic=DeterministicSpec(seed=1, temperature=0.0),
        retry_policy=RetryPolicy(max_attempts=2, retry_on=("TimeoutError",)),
    )

    assert check_graph_well_formed(with_state_field(ir, _fresh_key(ir), "str")) == baseline
    assert check_graph_well_formed(annotated) == baseline
    assert check_graph_well_formed(_checkpointed(ir, present=True)) == baseline
    assert check_graph_well_formed(_reconditioned(ir)) == baseline


@AT_SCALE
@given(ir=workflow_irs(envelope=DEFAULT_ENVELOPE))
def test_the_pass_witness_is_exactly_the_graph_it_describes(ir: WorkflowIR) -> None:
    """MP-01-8. Witness validity: every field re-derived from the surface, not trusted.

    Every draw is P-01 clean, so every run here is a pass and the witness is the whole output.
    ``reachable_from_start`` is ``sorted(V)`` — §1.4 Step 5 writes it with the comment "==
    reachable on pass", and it is, because a non-reachable id would have filled the finding list
    instead. ``terminal_nodes`` is re-derived here as the two ways a document reaches ``__end__``
    — ``finish`` membership (m2) and a ``path_map`` label valued ``"END"`` (m3) — rather than
    read back off the same model the validator used. The two empty lists are empty by
    construction on this path.

    The last assertion is DEC-12's phantom hole, closed from the other side: **every id the
    witness names is a declared node**. An unresolved reference emits and inserts nothing, so
    there is no phantom to leak — and the way that guarantee would break is a witness naming an
    id no ``nodes[]`` entry declares, which is what this checks.
    """
    declared = {node.id for node in ir.nodes}
    witness = _witness(check_graph_well_formed(ir))

    assert witness.reachable_from_start == tuple(sorted(declared, key=ledger_sort_key))
    assert witness.terminal_nodes == tuple(sorted(_terminals(ir), key=ledger_sort_key))
    assert witness.orphan_nodes == ()
    assert witness.unresolved_targets == ()
    assert set(witness.reachable_from_start) <= declared
    assert set(witness.terminal_nodes) <= declared


@AT_SCALE
@given(ir=workflow_irs(envelope=DEFAULT_ENVELOPE), position=POSITIONS, other=POSITIONS)
def test_graph_well_formed_is_cycle_agnostic(ir: WorkflowIR, position: int, other: int) -> None:
    """MP-01-9. §1.1/§1.5's "cycle-agnostic, and never enumerates cycles", made observable.

    A self-loop and a back edge between two declared nodes are the two smallest ways to put a
    cycle into a clean graph, and neither can change what P-01 says: reachability only grows,
    ``__end__``'s predecessor set is untouched, no node loses edge participation, and a node that
    stops being a sink was in ``finish`` anyway. So the report is **identical**, which is a
    stronger claim than the verdict staying a pass — a validator that had started counting cycles
    into its witness, or ordering findings by cycle membership, fails here.

    The complexity half of §1.5 is not this row's: ``tests/verify/test_graph_well_formed.py``
    asserts it structurally, by showing the SCC and anchor-cycle derivations are never memoized
    on a model P-01 has run over.
    """
    baseline = check_graph_well_formed(ir)
    ids = [node.id for node in ir.nodes]
    source = ids[position % len(ids)]
    target = ids[other % len(ids)]
    back_edge = with_edge(ir, NormalEdge(kind="normal", **{"from": source}, to=target))

    assert check_graph_well_formed(with_self_loop(ir, source)) == baseline
    assert check_graph_well_formed(back_edge) == baseline


# ── MP-02-* — P-02 termination-witness (TERMINATION-WITNESS-SPEC) ────────────────────────


@AT_SCALE
@given(mutation=termination_mutations(operators=("removed-variant",)))
def test_removing_a_variant_witness_flips_the_verdict(mutation: Mutation) -> None:
    """MP-02-1. The card's own example: removing a witness flips the P-02 outcome.

    One annotation slot separates the pair — same graph, same cycle, same Σ — and the two halves
    are the two sides of §4's form-(c) row. With the ``variant``, its carrier leaves the element
    residual entirely (§5's $R = G \\setminus (S_a \\cup S_c)$ deletes an S-node *with its
    incidences*), the residual is acyclic, and Lemma 1 passes with the carrier recorded in the
    inventory as discharging all simple cycles through it. Without it the loop survives, and Step
    5 reports that singleton SCC with the loop as its representative cycle and
    ``exhaustive: false`` — one representative, never an enumeration.

    ``blanket_only`` is asserted **absent** rather than ``false``: §2.3's fail shape omits the
    member, and since ``exclude_none`` drops ``None`` but not ``False``, emitting the literal
    would lose model equality against every residual-SCC fixture in the corpus.
    """
    node = _node(mutation)
    passing = check_termination_witness(mutation.origin)
    assert passing.result == "pass"

    inventory = _termination(passing).inventory
    assert [entry.form for entry in inventory] == ["c"]
    assert inventory[0].element == NodeLocation(kind="node", node=node)
    assert inventory[0].discharges == "all-simple-cycles-through-element"

    failure = _failure(check_termination_witness(mutation.ir))
    location = failure.location
    assert isinstance(location, P02SccLocation)
    assert failure.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert failure.location == mutation.location
    assert failure.co_failures is None
    assert location.representative_cycle == (node,)
    assert location.exhaustive is False
    assert location.blanket_only is None


@AT_SCALE
@given(mutation=termination_mutations(operators=("removed-blanket",)))
def test_removing_the_blanket_witness_flips_the_verdict(mutation: Mutation) -> None:
    """MP-02-2. Form (b), and the §6.1 row that reads its pass back as a strict promotion.

    The blanket never enters residual construction — a blanket over $E$ would make Lemma 1
    vacuous — so the origin *passes with the surviving SCC still in the record*, carried on the
    WARNING-grade ``scc-covered-only-by-recursion-limit`` note with ``blanket_only: true``. That
    is what makes §6.1's third row a lookup rather than a second analysis, and
    :func:`~gebra.verify.properties.termination_witness.strict_promotions` is asserted here to
    select exactly that record, under the *same* condition ID the default profile would have
    used: "the strict promotion reuses the same condition ID … no new condition ID is
    introduced".

    Removing the limit removes the only witness, and the same SCC becomes a FATAL finding — with
    ``blanket_only`` now absent, because there is no blanket for the member to speak about.
    """
    node = _node(mutation)
    passing = check_termination_witness(mutation.origin)
    witness = _termination(passing)
    assert passing.result == "pass"
    assert [entry.form for entry in witness.inventory] == ["b"]
    assert witness.inventory[0].discharges == "blanket"

    notes = [note for note in witness.notes if note.severity == "warning"]
    assert [note.kind for note in notes] == ["scc-covered-only-by-recursion-limit"]
    anchors = [
        location for location in notes[0].locations or () if isinstance(location, P02SccLocation)
    ]
    assert [location.blanket_only for location in anchors] == [True]
    assert [location.nodes for location in anchors] == [(node,)]

    promotions = strict_promotions(passing)
    assert [promotion.property_condition for promotion in promotions] == [
        CYCLE_WITHOUT_TERMINATION_WITNESS
    ]
    assert promotions[0].location.nodes == (node,)

    failure = _failure(check_termination_witness(mutation.ir))
    assert failure.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert failure.location == mutation.location
    assert strict_promotions(check_termination_witness(mutation.ir)) == ()


@AT_SCALE
@given(mutation=termination_mutations(operators=("unqualified-variant",)))
def test_a_variant_key_outside_the_schema_discharges_nothing_and_is_noted(
    mutation: Mutation,
) -> None:
    """MP-02-3. Declared is not qualifying — and the near-miss is surfaced, not swallowed.

    §4's form-(c) row is a *membership* test (``variant.key ∈ keys(Σ)``), so the same annotation
    that discharges the cycle in MP-02-1 discharges nothing once its key names something Σ does
    not declare. The pair is one string apart. What §4 path 2 adds is that the shortfall must be
    reported: the ``variant-key-not-in-state`` note names the node and the key, and DEC-23 puts
    notes on ``Failure.notes`` **unconditionally** on the fail path — so a failing P-02 never
    silently drops the reason a declared witness went unused, which is exactly the case where a
    reader most needs it.
    """
    assert check_termination_witness(mutation.origin).result == "pass"

    failure = _failure(check_termination_witness(mutation.ir))

    assert failure.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert failure.location == mutation.location
    assert [(note.kind, note.node, note.key) for note in failure.notes or ()] == [
        ("variant-key-not-in-state", _node(mutation), mutation.key)
    ]


@AT_SCALE
@given(ir=workflow_irs(envelope=acyclic_envelope(DEFAULT_ENVELOPE)), position=POSITIONS)
def test_a_counter_guard_discharges_exactly_when_a_label_leaves_its_loop(
    ir: WorkflowIR, position: int
) -> None:
    """MP-02-4. DEC-05 D4's wiring defect and its repair, one ``path_map`` value apart.

    A recognized form-(a) guard bounds its counter, but a bound with nowhere to go bounds
    nothing: §2.1's third qualification item is the graph-shaped exit test, and when no label
    leaves the loop the result is the *distinct* condition ``counter-guard-without-exit-edge``,
    anchored on the cycle through the guard's source and carrying the counter key and the guard's
    labels as evidence. Wire the else-label to ``END`` and the same guard discharges.

    Two things beyond the verdict. **Only the gated then-label edge enters $S$** (DEC-23 Q1): the
    inventory names $\\hat{l}$ and never the else-label, which is the over-discharge §4 bans —
    the else-branch is an implicit negation context and is not bounded by the comparison. And the
    recorded ``bound`` is the ``int-literal`` as written, so a recognizer that had normalized the
    mirrored form wrongly would show up here rather than in a verdict.

    The prediction does not turn on whether the validator took DEC-23 Q4's natural loop or its
    $\\mathrm{SCC}_G(u)$ fallback: for a *self*-loop the two agree on every ``path_map`` target,
    since a target $t$ of an edge $v \\to t$ reaches $v$ if and only if $t \\in \\mathrm{SCC}(v)$.
    """
    node = ir.nodes[position % len(ir.nodes)].id
    stranded = counter_guard_without_exit(ir, node)
    wired = counter_guard_with_exit(ir, node)

    failure = _failure(check_termination_witness(stranded.ir))
    location = failure.location
    assert isinstance(location, P02CycleLocation)
    assert failure.property_condition == COUNTER_GUARD_WITHOUT_EXIT_EDGE
    assert failure.location == stranded.location
    assert location.counter_key == stranded.key
    assert location.guard_edge.labels == (PROBE_THEN_LABEL, PROBE_ELSE_LABEL)
    # §2.3's same-SCC subsumption, and the only place it is observable: the residual still
    # carries the self-loop, so a validator emitting both findings would report the base
    # condition alongside this one. DEC-05 D2 (one root cause, one report) is what says it must
    # not — ratified at walkthrough #2 over §4's both-emitted reading.
    assert failure.co_failures is None

    discharged = check_termination_witness(wired.ir)
    inventory = _termination(discharged).inventory
    assert discharged.result == "pass"
    assert [entry.form for entry in inventory] == ["a"]
    assert inventory[0].element == EdgeLocation(
        kind="edge", source=node, target=node, label=PROBE_THEN_LABEL
    )
    source = inventory[0].source
    assert isinstance(source, CounterGuardSource)
    assert source.guard_edge == GuardEdgeRef(source=node, label=PROBE_THEN_LABEL)
    assert source.counter_key == wired.key
    assert source.bound == PROBE_BOUND


@AT_SCALE
@given(mutation=termination_mutations())
def test_every_cycle_p02_names_is_a_real_canonically_rotated_cycle(mutation: Mutation) -> None:
    """MP-02-5. D-10's own metaproperty — "every returned cycle witness names a real cycle".

    Three different cycle-valued fields, all held to the same three things: the walk closes over
    edges that exist in the label-expanded model, it is simple, and it is in §0.3's canonical
    rotation (lexicographically-least id first under the ledger §6 comparator, checked against
    the *rule* rather than against the validator's own rotation helper, which would only attest
    that the helper is idempotent).

    The fields are the residual SCC's ``representative_cycle`` (Step 5, A7 Lemma 3), the D4
    anchor (§2.4's ``cycle_through``), and the pass census (§6.3's B-capped Johnson) — and the
    census carries one more claim, that a *present* list says ``exhaustive: true``, since PD-011
    has an aborted census omit the list and note itself rather than return a partial one.
    """
    for candidate in (mutation.origin, mutation.ir):
        report = check_termination_witness(candidate)
        model = build_graph_model(candidate, carry_unresolved_references=True)
        for record in _records(report):
            location = record.location
            if isinstance(location, P02SccLocation):
                _assert_real_cycle(model, location.representative_cycle)
                assert location.exhaustive is False
                assert set(location.representative_cycle) <= set(location.nodes)
            elif isinstance(location, P02CycleLocation):
                _assert_real_cycle(model, location.nodes)
        if isinstance(report.witness, TerminationWitness) and report.witness.cycles is not None:
            assert report.witness.cycles.exhaustive is True
            for cycle in report.witness.cycles.cycles:
                _assert_real_cycle(model, cycle)


@AT_SCALE
@given(mutation=termination_mutations(operators=("removed-variant",)))
def test_the_acyclicity_certificate_is_a_topological_order_of_the_residual(
    mutation: Mutation,
) -> None:
    """MP-02-6. §6.2's certificate re-checked in O(|N|+|E|), which is the point of having one.

    "Any consumer re-checks it with no trust in the checker" — so this row is that consumer. The
    origin's $S$ is known exactly here: one form-(c) carrier and nothing else, so
    $R = G \\setminus \\{v\\}$ with the node's incidences deleted, and the draw is acyclic
    besides its one injected self-loop. The certificate must therefore list every vertex of the
    model except that node — the two sentinels included, since §0.3 has report-level path lists
    carry the display spellings — exactly once, and every surviving edge must run forward in it.

    A validator that emitted the ledger order, or the authored order, would satisfy the
    membership half and fail the ordering half on any draw whose ids do not happen to be sorted
    topologically.
    """
    node = _node(mutation)
    report = check_termination_witness(mutation.origin)
    certificate = [from_display(reference) for reference in _termination(report).certificate]
    model = build_graph_model(mutation.origin, carry_unresolved_references=True)
    position = {vertex: index for index, vertex in enumerate(certificate)}

    assert len(set(certificate)) == len(certificate)
    assert set(certificate) == set(model.vertices) - {node}
    for vertex in certificate:
        for edge in model.out_edges(vertex):
            if edge.target != node:
                assert position[vertex] < position[edge.target], (vertex, edge.target)


@AT_SCALE
@given(ir=workflow_irs(envelope=DEFAULT_ENVELOPE))
def test_termination_witness_reads_only_its_declared_fields(ir: WorkflowIR) -> None:
    """MP-02-7. §2.3's field list, quantified from the outside.

    P-02 reads ``edges[].{kind, from, condition, path_map}``, ``state``,
    ``runtime.recursion_limit`` and ``nodes[].annotations.variant`` — "§2.3's field list
    exactly". So every *other* contract slot is inert, and so are the other two ``runtime``
    sub-slots: a fully populated contract carrying effects, a determinism claim, a retry policy
    and a purity flag, plus a ``checkpointer``, must leave the report **equal**.

    A widened Σ is asserted inert too, and that one is a narrower claim than it looks: ``state``
    *is* read, for the key membership and declared type of a recognized guard's counter-ref (R1's
    §2.1 half). What holds is that a key **no condition string names** cannot qualify one, and
    the draws' router conditions are opaque names that derive nothing under §3's ``guard``
    production. Both are asserted rather than one, because the two would fail differently.

    **A rotation of ``nodes[]`` is deliberately not in this list.** §2.4's assembly appends
    form-(c) entries "in authored node order", so a rotation legitimately moves the inventory —
    that is the spec's order, not an accidental dependency, and asserting equality under it would
    be asserting the opposite of what §2.4 says.
    """
    baseline = check_termination_witness(ir)
    annotated = _annotate(
        ir,
        pure=False,
        effect=("billable", "network"),
        deterministic=True,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=()),
    )

    assert check_termination_witness(annotated) == baseline
    assert check_termination_witness(_checkpointed(ir, present=False)) == baseline
    assert check_termination_witness(with_state_field(ir, _fresh_key(ir), "int")) == baseline


# ── MP-S-* — both structural validators at once ──────────────────────────────────────────


@AT_SCALE
@given(mutation=well_formedness_mutations(operators=RESOLVING_OPERATORS))
def test_the_findings_are_an_independent_derivation_of_the_conditions(
    mutation: Mutation,
) -> None:
    """MP-S-1. A second opinion on P-01, computed from the surface without the shared model.

    Every row above states what *one* injection produces. This one states the general form: over
    every structural operator that leaves all references resolvable, the full ordered finding
    list equals a derivation written here directly from ``entry``, ``finish``, ``nodes[]`` and
    ``edges[]`` — its own reachability walk, its own sink test, its own Reading A participation
    test, and §1.4 Step 5's block order. Nothing in :func:`_by_hand` calls
    :func:`~gebra.verify.graph.build_graph_model`, so a defect *in the shared model* — a label
    that stopped expanding, a sentinel wiring that stopped being emitted — surfaces here rather
    than being confirmed by the same code that caused it.

    The **ordered** list is compared rather than the set, so this subsumes the root-cause order
    and the ledger §6 order inside each block. Condition (iv) is out of scope by construction:
    the operators quantified over inject no unresolved reference, and the resolution asymmetry
    §1.4 Step 1 carries is stated at :func:`MP-01-5 <
    test_every_unresolved_reference_is_one_finding_at_its_own_site>` instead, where each of
    DEC-12's five sites is asserted individually rather than re-implemented.
    """
    for candidate in (mutation.origin, mutation.ir):
        report = check_graph_well_formed(candidate)
        derived = _by_hand(candidate)

        assert [(condition, location.node) for condition, location in _findings(report)] == derived
        assert (report.result == "pass") == (derived == [])


# ── Non-vacuity: the shapes the structural operators have to be able to reach ────────────


def _reaches_condition(condition_id: ConditionId) -> Callable[[Mutation], bool]:
    return lambda mutation: mutation.condition == condition_id


def _cascade(mutation: Mutation) -> bool:
    report = check_graph_well_formed(mutation.ir)
    return mutation.target == "graph-well-formed" and len(_findings(report)) >= 3


def _census(mutation: Mutation) -> bool:
    witness = check_termination_witness(mutation.origin).witness
    return isinstance(witness, TerminationWitness) and witness.cycles is not None


def _promotable(mutation: Mutation) -> bool:
    return bool(strict_promotions(check_termination_witness(mutation.origin)))


#: One entry per shape the suite above would pass vacuously without. A generator that stopped
#: producing any of them still satisfies every metaproperty — which is what makes this table the
#: quality gate D-10's risk register asks for ("coverage assertions on generated corpora").
SHAPES: Final[tuple[tuple[str, Any, Callable[[Mutation], bool]], ...]] = (
    (
        "an unreachable node",
        well_formedness_mutations,
        _reaches_condition(NODE_UNREACHABLE_FROM_START),
    ),
    ("an orphan node", well_formedness_mutations, _reaches_condition(ORPHAN_NODE)),
    (
        "a dead end off finish",
        well_formedness_mutations,
        _reaches_condition(DEAD_END_NODE_NOT_WIRED_TO_END),
    ),
    (
        "an unresolved reference",
        well_formedness_mutations,
        _reaches_condition(EDGE_TARGET_UNDEFINED),
    ),
    (
        "a dangling path_map label",
        well_formedness_mutations,
        _reaches_condition(PATH_MAP_TARGET_UNDEFINED),
    ),
    ("a three-finding cascade", well_formedness_mutations, _cascade),
    (
        "a witness-free residual SCC",
        termination_mutations,
        _reaches_condition(CYCLE_WITHOUT_TERMINATION_WITNESS),
    ),
    (
        "a counter guard with no exit",
        termination_mutations,
        _reaches_condition(COUNTER_GUARD_WITHOUT_EXIT_EDGE),
    ),
    ("a completed cycle census", termination_mutations, _census),
    ("a promotable blanket-only SCC", termination_mutations, _promotable),
    ("a coherent structural mutation", well_formedness_mutations, lambda m: not m.breaking),
    ("a coherent termination mutation", termination_mutations, lambda m: not m.breaking),
    (
        "a structural mutant over three or more nodes",
        well_formedness_mutations,
        lambda mutation: len(mutation.ir.nodes) >= 3,
    ),
    (
        "a cyclic mutant over two or more nodes",
        termination_mutations,
        lambda mutation: len(mutation.ir.nodes) >= 2,
    ),
)


@pytest.mark.parametrize(
    ("description", "family", "predicate"), SHAPES, ids=[name for name, _, _ in SHAPES]
)
def test_the_structural_operators_can_produce(
    description: str, family: Any, predicate: Callable[[Mutation], bool]
) -> None:
    """``find`` locates a witness, or raises ``NoSuchExample`` naming the shape that went missing."""
    witness = find(family(), predicate, settings=REACH)

    assert predicate(witness), description


@pytest.mark.parametrize("operator", [*WELL_FORMEDNESS_OPERATORS, *TERMINATION_OPERATORS])
def test_every_structural_operator_is_reachable_by_name(operator: str) -> None:
    """Every row of the two new tables really produces its mutation.

    The named-subset seam is what the sharp metaproperties above select with, so an operator that
    silently stopped being offered would make one of them quantify over nothing while still
    passing.
    """
    family = (
        well_formedness_mutations
        if operator in WELL_FORMEDNESS_OPERATORS
        else termination_mutations
    )

    witness = find(family(operators=(operator,)), lambda mutation: True, settings=REACH)

    assert witness.operator == operator


# ── Helpers ──────────────────────────────────────────────────────────────────────────────

#: What :func:`_reconditioned` writes into every router's ``condition``. Shaped like a §3 guard
#: on a key nothing declares, so a validator that had started reading router strings would have
#: the most to say about it.
_REWRITTEN_CONDITION: Final = "'a' if gebra_unread_counter < 9 else 'b'"


def _node(mutation: Mutation) -> str:
    """The node an operator anchored its prediction at — every operator quantified here has one."""
    assert mutation.node is not None
    return mutation.node


def _failure(report: PropertyReport) -> Any:
    """The primary finding of a failing report."""
    assert report.failure is not None, report
    return report.failure


def _records(report: PropertyReport) -> list[Any]:
    """Every emitted record of a report: the primary failure and each co-failure (§0.3)."""
    if report.failure is None:
        return []
    return [report.failure, *(report.failure.co_failures or ())]


def _findings(report: PropertyReport) -> list[tuple[ConditionId, Any]]:
    """Every record as (condition ID, location), in emission order."""
    return [(record.property_condition, record.location) for record in _records(report)]


def _witness(report: PropertyReport) -> WellFormednessWitness:
    witness = report.witness
    assert isinstance(witness, WellFormednessWitness), report
    return witness


def _termination(report: PropertyReport) -> TerminationWitness:
    witness = report.witness
    assert isinstance(witness, TerminationWitness), report
    return witness


def _rebuilt(ir: WorkflowIR, **changes: Any) -> WorkflowIR:
    """``ir`` with ``changes`` applied, rebuilt through the constructor (A6 PC-6)."""
    values: dict[str, Any] = {name: getattr(ir, name) for name in WorkflowIR.model_fields}
    values.update(changes)
    return WorkflowIR(**values)


def _annotate(ir: WorkflowIR, **overrides: Any) -> WorkflowIR:
    """``ir`` with ``overrides`` written into **every** node's contract, slot by slot.

    Merged onto whatever the draw carried rather than replacing it, and that is load-bearing
    rather than tidy: replacing the contract would drop ``annotations.variant``, which is a field
    P-02 *does* read (§2.3), so MP-02-7's equality would be asserting the opposite of what it
    says. No caller populates ``input``/``output`` (Σ subsets under §2.3) or ``variant``, so the
    result is always a valid document whose only difference from ``ir`` is slots the row under
    test claims are unread.
    """
    return _rebuilt(
        ir,
        nodes=tuple(
            Node(id=node.id, annotations=_updated(node.annotations, **overrides))
            for node in ir.nodes
        ),
    )


def _updated(contract: Annotations | None, **overrides: Any) -> Annotations:
    """``contract`` (or an empty one) with ``overrides`` applied, rebuilt through the constructor."""
    current = contract if contract is not None else Annotations()
    values: dict[str, Any] = {name: getattr(current, name) for name in Annotations.model_fields}
    values.update(overrides)
    return Annotations(**values)


def _checkpointed(ir: WorkflowIR, *, present: bool) -> WorkflowIR:
    """``ir`` with ``runtime.checkpointer`` declared, keeping the other two sub-slots.

    ``recursion_limit`` is carried through rather than overwritten because P-02 reads it as the
    form-(b) blanket; dropping a drawn one would move P-02's verdict and MP-02-7 would be
    measuring that instead of what it claims.
    """
    current = ir.runtime
    return _rebuilt(
        ir,
        runtime=Runtime(
            recursion_limit=None if current is None else current.recursion_limit,
            interrupts=None if current is None else current.interrupts,
            checkpointer=Checkpointer(present=present),
        ),
    )


def _reconditioned(ir: WorkflowIR) -> WorkflowIR:
    """``ir`` with every router's ``condition`` rewritten — §1.3's "Not read" entry with teeth."""
    return _rebuilt(
        ir,
        edges=tuple(
            ConditionalEdge(
                kind="conditional",
                **{"from": edge.from_},
                condition=_REWRITTEN_CONDITION,
                path_map=edge.path_map,
            )
            if isinstance(edge, ConditionalEdge)
            else edge
            for edge in ir.edges
        ),
    )


def _fresh_key(ir: WorkflowIR) -> str:
    """A state key the workflow does not declare and no contract mentions."""
    candidate = "gebra_inert_key"
    while candidate in (ir.state or {}):
        candidate += "_"
    return candidate


def _wired(value: str | tuple[str, ...]) -> tuple[str, ...]:
    """``entry``/``finish`` as a tuple, whichever of the two §2.1 surface forms it is in."""
    return (value,) if isinstance(value, str) else value


def _terminals(ir: WorkflowIR) -> set[str]:
    """The declared nodes with an edge to ``__end__`` — (m2) and (m3), derived from the surface.

    The two ways IR-SPEC §4.1 admits: ``finish`` membership, and a ``path_map`` label valued
    ``"END"``. A ``normal``/``send`` edge writing the literal is *not* one — PD-007 Q2 blessed it
    for ``path_map`` values only — so it is deliberately not counted here; on the P-01-clean
    draws this is quantified over, no such edge exists.
    """
    terminals = set(_wired(ir.finish))
    for edge in ir.edges:
        if isinstance(edge, ConditionalEdge) and END_LITERAL in edge.path_map.values():
            terminals.add(edge.from_)
    return terminals


def _targets(edge: Any) -> set[str]:
    """Every vertex one authored edge reaches, as a model vertex (ledger §4; (m3)).

    A ``path_map`` value of ``"END"`` denotes the exit sentinel unconditionally — the literal is
    checked *before* the id lookup in ``build_graph_model``, so it is projected here the same
    way rather than left to collide with a node that happened to be called ``END``. A
    ``normal``/``send`` ``to`` of ``"END"`` gets no such projection (PD-007 Q2), which is why
    only the conditional branch maps it.
    """
    if isinstance(edge, ConditionalEdge):
        return {
            END_VERTEX if target == END_LITERAL else target for target in edge.path_map.values()
        }
    return {edge.to}


def _by_hand(ir: WorkflowIR) -> list[tuple[ConditionId, str]]:
    """Conditions (iii), (i) and (ii) derived from the surface, in §1.4 Step 5's block order.

    Deliberately built from ``ir`` alone — no :func:`~gebra.verify.graph.build_graph_model`, no
    :class:`~gebra.verify.graph.GraphModel` — so that agreement with P-01 is evidence about the
    shared model and not a restatement of it. The three rules, each as §1 states it:

    * **(iii)**, Reading A: a node participates in an edge if it is the ``from`` or a resolvable
      target of one, or a member of ``entry``/``finish`` — sentinel wirings count.
    * **(i)**: reachable from ``__start__`` means reachable from some ``entry`` member by
      declared, resolvable edges.
    * **(ii)**: no outgoing edge in $G^*$ — no authored edge at all, and not in ``finish``. The
      ``"END"`` literal *is* an outgoing edge (m3), which is why targets are counted before they
      are filtered to declared ids.

    Every caller quantifies only over operators that leave references resolvable, so the
    ``& declared`` intersections below never drop anything the validator would have kept; they
    are there because the derivation should be total rather than rely on that.
    """
    declared = {node.id for node in ir.nodes}
    entry = set(_wired(ir.entry)) & declared
    finish = set(_wired(ir.finish)) & declared
    participates = entry | finish
    out: dict[str, set[str]] = {node_id: set() for node_id in declared}
    for edge in ir.edges:
        if edge.from_ not in declared:
            continue
        participates.add(edge.from_)
        out[edge.from_] |= _targets(edge)
        participates |= _targets(edge) & declared

    reachable: set[str] = set()
    frontier = list(entry)
    while frontier:
        vertex = frontier.pop()
        if vertex in reachable:
            continue
        reachable.add(vertex)
        frontier.extend(out[vertex] & declared)

    order = sorted(declared, key=ledger_sort_key)
    return [
        *[(ORPHAN_NODE, node_id) for node_id in order if node_id not in participates],
        *[(NODE_UNREACHABLE_FROM_START, node_id) for node_id in order if node_id not in reachable],
        *[
            (DEAD_END_NODE_NOT_WIRED_TO_END, node_id)
            for node_id in order
            if not out[node_id] and node_id not in finish
        ],
    ]


def _assert_real_cycle(model: GraphModel, cycle: tuple[str, ...]) -> None:
    """A named cycle is simple, closes over real edges, and is canonically rotated (§0.3).

    The rotation is checked against §0.3's rule — "lexicographically-least id first", under the
    ledger §6 comparator — rather than against
    :func:`~gebra.verify.graph.canonical_rotation`'s own output, which would only attest that the
    validator's helper is idempotent.
    """
    assert cycle
    assert len(set(cycle)) == len(cycle)
    assert cycle[0] == min(cycle, key=ledger_sort_key)
    for tail, head in zip(cycle, (*cycle[1:], cycle[0]), strict=True):
        assert model.has_edge(from_display(tail), from_display(head)), (tail, head, cycle)
