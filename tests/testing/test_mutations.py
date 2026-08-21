"""The mutation-operator library held to its own contract — TE-10, brief D-10 W7.

:mod:`gebra.testing.mutations` is the substrate
``tests/testing/test_metaproperties_contract.py`` quantifies over, so a defect here would not
fail a metaproperty — it would make one quantify over the wrong documents, or over nothing at
all, and stay green. This file is the other half: the rewrite helpers on hand-built input where
the expected document can be written out in full, every refusal the operators make, and the
import guard.

Three kinds of test, and the split matters:

1. **The rewrites**, on a fixed three-node workflow. A helper that rebuilds a document through
   the constructors either produces the document a reader can predict or it does not, and that
   is not a claim about a distribution.
2. **The refusals.** Each operator that states a precondition raises on its own violation —
   which is what keeps a prediction in :class:`~gebra.testing.mutations.Mutation` a prediction
   rather than a hope.
3. **The library's own seams**: memoization (a per-example rebuild would triple the metaproperty
   suite's runtime without failing anything), the named-subset selector, and the fact that
   importing the module without ``hypothesis`` fails with a message naming *this* module.

Everything here is pure data (WA-07): frozen pydantic values in, frozen pydantic values out.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import Phase, find, settings

from gebra.ir import (
    Annotations,
    Checkpointer,
    ConditionalEdge,
    IdempotentKey,
    Node,
    NormalEdge,
    RecursionLimit,
    Runtime,
    StateField,
    Variant,
    WorkflowIR,
)
from gebra.testing.mutations import (
    DATAFLOW_OPERATORS,
    DETERMINISM_OPERATORS,
    EFFECT_SAFETY_OPERATORS,
    OPERATORS,
    PROBE_HOOK,
    PROBE_KEY,
    PROBE_LABEL,
    PROBE_NODE,
    TERMINATION_OPERATORS,
    WELL_FORMEDNESS_OPERATORS,
    Mutation,
    bare_claim,
    chain_wiring,
    compensation_hook,
    counter_guard_without_exit,
    dangling_hook,
    dataflow_mutations,
    dead_end_node,
    determinism_mutations,
    effect_safety_mutations,
    mutations,
    orphan_node,
    permute_nodes,
    removed_variant,
    severed_edge,
    star_wiring,
    undefined_edge_source,
    undefined_edge_target,
    undefined_path_map_target,
    unpinned_temperature,
    unprotected_cycle,
    unwritten_read,
    update_contract,
    wired_leaf,
    with_edge,
    with_node,
    with_recursion_limit,
    with_self_loop,
    with_state_field,
    with_wiring,
    without_determinism,
    without_edge,
    without_effects,
    without_reads,
    without_witnesses,
)
from gebra.testing.strategies import workflow_irs
from gebra.verify.graph import build_graph_model
from gebra.verify.locations import P01EdgeLocation, P02SccLocation
from gebra.verify.properties.graph_well_formed import check_graph_well_formed

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The budget the two ``find`` calls below get; the same profile the metaproperty suite uses.
REACH = settings(
    max_examples=3000, deadline=None, database=None, derandomize=True, phases=(Phase.generate,)
)

#: A fixed workflow with one of everything the operators read: a router, a state schema with an
#: optional key, a keyed idempotency marker bound to its node's input, and a trigger tag.
WORKFLOW = WorkflowIR(
    ir_version="1.0",
    entry="plan",
    finish=("audit",),
    state={"draft": "str", "seed": StateField(type="int", optional=True)},
    nodes=(
        Node(id="plan", annotations=Annotations(output=("draft",))),
        Node(
            id="book",
            annotations=Annotations(
                input=("draft",),
                effect=("billable", "external"),
                idempotent=IdempotentKey(key="draft"),
            ),
        ),
        Node(id="audit", annotations=None),
    ),
    edges=(
        NormalEdge(kind="normal", **{"from": "plan"}, to="book"),
        ConditionalEdge(
            kind="conditional",
            **{"from": "book"},
            condition="route",
            path_map={"done": "audit", "stop": "END"},
        ),
    ),
)


def _rebuilt(ir: WorkflowIR, **changes: object) -> WorkflowIR:
    """``ir`` with ``changes`` applied, rebuilt through the constructor (A6 PC-6)."""
    values: dict[str, object] = {name: getattr(ir, name) for name in WorkflowIR.model_fields}
    values.update(changes)
    return WorkflowIR(**values)  # type: ignore[arg-type]


# ── The rewrites ─────────────────────────────────────────────────────────────────────────


def test_a_contract_update_touches_one_node_and_validates_the_result() -> None:
    """The workhorse: one slot on one node, every other sub-model carried by identity.

    Rebuilding through the constructor rather than ``model_copy`` is what keeps A6 PC-6's ban
    honest — a document that never passed validation would carry silent defects into every
    consumer. The identity assertions are what say the rewrite is *local*: validation rebuilds
    the tuples (strict mode re-checks the container) but the frozen sub-models inside pass
    through untouched, so an untargeted node or edge is the same object, not a copy that a later
    equality assertion would have to trust.
    """
    updated = update_contract(WORKFLOW, "audit", effect=("irreversible",))

    assert updated.nodes[2].annotations == Annotations(effect=("irreversible",))
    assert updated.nodes[0] is WORKFLOW.nodes[0]
    assert updated.edges[0] is WORKFLOW.edges[0]
    assert updated.entry == WORKFLOW.entry
    assert updated.edges == WORKFLOW.edges


def test_a_state_field_can_be_added_and_replaced() -> None:
    """Σ is a mapping, so an operator that introduces a key must also be able to re-declare it."""
    widened = with_state_field(WORKFLOW, PROBE_KEY, "str")
    replaced = with_state_field(widened, PROBE_KEY, StateField(type="str", optional=True))

    assert widened.state == {**(WORKFLOW.state or {}), PROBE_KEY: "str"}
    assert replaced.state is not None
    assert replaced.state[PROBE_KEY] == StateField(type="str", optional=True)
    assert WORKFLOW.state is not None
    assert PROBE_KEY not in WORKFLOW.state, "the original is frozen and must not be mutated"


def test_a_self_loop_is_appended_and_leaves_the_graph_well_formed() -> None:
    """Adding an edge unreaches nothing, creates no sink and orphans nobody (P-01 §1.4)."""
    looped = with_self_loop(WORKFLOW, "book")
    model = build_graph_model(looped)

    assert looped.edges[-1] == NormalEdge(kind="normal", **{"from": "book"}, to="book")
    assert model.has_self_loop("book")
    assert model.components.is_nontrivial("book")
    assert check_graph_well_formed(looped).result == "pass"


def test_a_node_is_appended_undeclared_and_unwired() -> None:
    """:func:`with_node` declares and wires nothing — every P-01 operator starts here.

    Which of §1's conditions the result violates is decided entirely by what the caller adds
    next, so this helper deliberately produces a document that is *not* well-formed: the same
    node is an orphan here, an unreachable node with a ``finish`` membership, and a dead end with
    an inbound edge.
    """
    widened = with_node(WORKFLOW, PROBE_NODE)

    assert widened.nodes[-1] == Node(id=PROBE_NODE, annotations=None)
    assert [node.id for node in widened.nodes[:-1]] == [node.id for node in WORKFLOW.nodes]
    assert check_graph_well_formed(widened).result == "fail"


def test_an_edge_is_appended_and_removed_by_index() -> None:
    """The two halves :func:`severed_edge` is built from, on a document written out in full."""
    extra = NormalEdge(kind="normal", **{"from": "audit"}, to="plan")
    widened = with_edge(WORKFLOW, extra)

    assert widened.edges == (*WORKFLOW.edges, extra)
    assert without_edge(widened, len(widened.edges) - 1).edges == WORKFLOW.edges
    assert without_edge(WORKFLOW, 0).edges == WORKFLOW.edges[1:]


def test_a_wiring_list_gains_ids_in_the_list_surface_form() -> None:
    """``entry``/``finish`` denote sets under (m1)/(m2), so a repeat is not a second edge."""
    rooted = with_wiring(WORKFLOW, "entry", "book")
    finished = with_wiring(WORKFLOW, "finish", "audit", PROBE_NODE)

    assert rooted.entry == ("plan", "book"), "the scalar form has no two-id counterpart (§2.1)"
    assert finished.finish == ("audit", PROBE_NODE)
    assert with_wiring(WORKFLOW, "entry", "plan").entry == ("plan",)


def test_a_recursion_limit_is_declared_without_disturbing_the_other_runtime_slots() -> None:
    """Form (b) is one sub-slot of ``runtime``, and the other two are carried (IR-SPEC §3.5)."""
    checkpointed = _rebuilt(WORKFLOW, runtime=Runtime(checkpointer=Checkpointer(present=True)))

    bounded = with_recursion_limit(checkpointed, 12, "probe")

    assert bounded.runtime is not None
    assert bounded.runtime.recursion_limit == RecursionLimit(value=12, justification="probe")
    assert bounded.runtime.checkpointer == Checkpointer(present=True)
    assert with_recursion_limit(WORKFLOW, 12, "probe").runtime is not None


def test_the_witness_normalizer_drops_both_declared_forms_and_nothing_else() -> None:
    """Forms (b) and (c) are slots; form (a) is a recognized shape and is not stripped.

    The nodes that declared no ``variant`` come through by identity rather than rebuilt with an
    empty contract, so the normalizer changes exactly the documents that declared something.
    """
    witnessed = with_recursion_limit(
        update_contract(WORKFLOW, "book", variant=Variant(key="draft", measure="decreasing")),
        9,
        "probe",
    )

    stripped = without_witnesses(witnessed)

    assert stripped.runtime is not None
    assert stripped.runtime.recursion_limit is None
    assert stripped.nodes[1].annotations is not None
    assert stripped.nodes[1].annotations.variant is None
    assert stripped.nodes[1].annotations.effect == ("billable", "external")
    assert stripped.nodes[2] is witnessed.nodes[2], "a node with no variant is not rebuilt"
    assert stripped.edges == WORKFLOW.edges, "a form-(a) guard lives in a condition string"


def test_rotating_the_node_list_changes_only_the_surface_order() -> None:
    """``nodes[]`` order is a surface fact every validator sorts away (ledger §6)."""
    rotated = permute_nodes(WORKFLOW, 1)

    assert [node.id for node in rotated.nodes] == ["book", "audit", "plan"]
    assert set(rotated.nodes) == set(WORKFLOW.nodes)
    assert permute_nodes(WORKFLOW, len(WORKFLOW.nodes)) == WORKFLOW


@pytest.mark.parametrize("rewiring", [star_wiring, chain_wiring])
def test_both_rewirings_are_p01_clean_and_keep_every_contract(rewiring: object) -> None:
    """The two poles §8.7's topology-independence property compares P-08's report across.

    A star (every node an entry *and* a finish, no edges) and a chain (one entry, one finish, a
    normal edge per consecutive pair) are about as far apart as two topologies over one node set
    get, and both are P-01 clean: (m1) makes every node reachable and (m2) or the chain gives
    every node an outgoing edge.
    """
    rewired = rewiring(WORKFLOW)  # type: ignore[operator]

    assert check_graph_well_formed(rewired).result == "pass"
    assert rewired.nodes == WORKFLOW.nodes
    assert rewired.state == WORKFLOW.state


def test_the_star_and_the_chain_are_the_shapes_they_say_they_are() -> None:
    star, chain = star_wiring(WORKFLOW), chain_wiring(WORKFLOW)

    assert star.entry == star.finish == ("plan", "book", "audit")
    assert star.edges == ()
    assert chain.entry == "plan"
    assert chain.finish == "audit"
    assert [(edge.from_, edge.to) for edge in chain.edges] == [  # type: ignore[union-attr]
        ("plan", "book"),
        ("book", "audit"),
    ]


def test_a_single_node_workflow_survives_both_rewirings() -> None:
    """The degenerate floor: a chain over one node has no edges, and the star is the same shape."""
    single = WorkflowIR(
        ir_version="1.0", entry="only", finish="only", nodes=(Node(id="only"),), edges=()
    )

    assert chain_wiring(single).edges == ()
    assert star_wiring(single).entry == ("only",)
    assert check_graph_well_formed(chain_wiring(single)).result == "pass"


# ── The normalizers ──────────────────────────────────────────────────────────────────────


def test_dropping_the_reads_drops_the_keyed_idempotency_marker_with_them() -> None:
    """§2.3 scopes ``idempotent.key`` to ``input``, so a marker left behind would dangle.

    The boolean forms stay: ``idempotent: true`` is a claim about the node, not about a key, and
    P-06's Phase 1 reads exactly that form.
    """
    keyed = without_reads(WORKFLOW)
    boolean = without_reads(update_contract(WORKFLOW, "book", idempotent=True))

    assert all(node.annotations is None or node.annotations.input is None for node in keyed.nodes)
    assert keyed.nodes[1].annotations is not None
    assert keyed.nodes[1].annotations.idempotent is None
    assert boolean.nodes[1].annotations is not None
    assert boolean.nodes[1].annotations.idempotent is True


def test_dropping_the_effects_and_the_claims_leaves_every_other_slot_alone() -> None:
    """Each normalizer clears exactly the slot its property quantifies over."""
    stripped = without_effects(WORKFLOW)
    unclaimed = without_determinism(update_contract(WORKFLOW, "audit", deterministic=True))

    assert all(
        node.annotations is None or node.annotations.effect is None for node in stripped.nodes
    )
    assert stripped.nodes[1].annotations is not None
    assert stripped.nodes[1].annotations.input == ("draft",)
    assert unclaimed.nodes[2].annotations == Annotations()


# ── Fresh names ──────────────────────────────────────────────────────────────────────────


def test_a_probe_key_that_the_schema_already_declares_is_suffixed() -> None:
    """The collision path, which no generated draw can reach — and that is why it is tested.

    :func:`~gebra.testing.strategies.state_schemas` draws four lowercase characters at most, so
    the probe name cannot collide with a drawn key. The operators are handed IR from elsewhere
    too (a fixture, a snapshot, a later card's generator), and a silently-reused key would make
    a "no node writes it" prediction false.
    """
    occupied = with_state_field(WORKFLOW, PROBE_KEY, "str")

    mutation = unwritten_read(occupied, "book")

    assert mutation.key == PROBE_KEY + "_"
    assert mutation.ir.state is not None
    assert mutation.ir.state[PROBE_KEY] == "str"


def test_a_dangling_hook_probe_that_names_a_declared_node_is_suffixed() -> None:
    """Same rule for the hook: a probe that resolved would be protection, not a dangling hook."""
    collided = WorkflowIR(
        ir_version="1.0",
        entry=PROBE_HOOK,
        finish=PROBE_HOOK,
        nodes=(Node(id=PROBE_HOOK),),
        edges=(),
    )

    mutation = dangling_hook(collided, PROBE_HOOK, "billable")
    contract = mutation.ir.nodes[0].annotations

    assert contract is not None
    assert contract.compensation is not None
    assert contract.compensation.hook == PROBE_HOOK + "_"


# ── The refusals ─────────────────────────────────────────────────────────────────────────


def test_a_rewrite_that_names_no_declared_node_is_refused() -> None:
    """A typo would otherwise rewrite nothing and leave the prediction pointing at a ghost.

    Both entry points that a caller reaches with an id refuse it: the two rewrites, and an
    operator that reads a slot off the node before rewriting it (every P-08 operator does, since
    it extends the effect tuple rather than replacing it).
    """
    with pytest.raises(KeyError, match="not a declared node"):
        update_contract(WORKFLOW, "ghost", effect=("billable",))
    with pytest.raises(KeyError, match="not a declared node"):
        with_self_loop(WORKFLOW, "ghost")
    with pytest.raises(KeyError, match="not a declared node"):
        bare_claim(WORKFLOW, "ghost", "external")


def test_a_compensation_hook_naming_no_node_is_refused_as_protection() -> None:
    """The coherent operator refuses the incoherent input rather than predicting a pass for it."""
    with pytest.raises(KeyError, match="that is dangling_hook"):
        compensation_hook(WORKFLOW, "book", "billable", "ghost")


def test_a_pinned_temperature_is_refused_by_the_unpinned_operator() -> None:
    """``temperature: 0`` is C-3's coherent case, so predicting a failure for it would be wrong."""
    with pytest.raises(ValueError, match="that is pinned_claim"):
        unpinned_temperature(WORKFLOW, "book", "external", 7, 0.0)

    assert unpinned_temperature(WORKFLOW, "book", "external", 7, 0.5).breaking


def test_the_cycle_operator_refuses_a_node_that_is_already_cyclic() -> None:
    """Its ``region == "cycle"`` prediction rests on the precondition, so it is checked.

    A node already inside a non-trivial component may sit in a structural retry region (DEC-13),
    and then adding a self-loop would leave the region ``retry`` while the operator predicted
    ``cycle`` — a wrong prediction rather than a missing one, which is the worse failure.
    """
    cyclic = find(workflow_irs(), _has_cycle, settings=REACH)
    node = next(
        node.id
        for node in cyclic.nodes
        if build_graph_model(cyclic).components.is_nontrivial(node.id)
    )

    with pytest.raises(ValueError, match="already lies on a cycle"):
        unprotected_cycle(cyclic, node, "billable")


def test_the_structural_rewrites_refuse_what_would_make_a_prediction_false() -> None:
    """Four preconditions, each protecting a *stated* prediction rather than a taste.

    A duplicate id is a §2.1 violation the models do not catch, and it would make "the finding is
    anchored at the new node" ambiguous. An out-of-range edge index would silently delete the
    wrong edge, or none. A wiring field that is neither of the two §2.1 lists is a typo that would
    otherwise land as a ``WorkflowIR`` keyword error three frames away. And a source id naming no
    node would turn a reachability injection into a condition-(iv) one.
    """
    with pytest.raises(ValueError, match="already declared"):
        with_node(WORKFLOW, "book")
    with pytest.raises(IndexError, match="does not exist"):
        without_edge(WORKFLOW, 7)
    with pytest.raises(ValueError, match="not a wiring list"):
        with_wiring(WORKFLOW, "nodes", "book")
    for operator in (
        severed_edge,
        dead_end_node,
        wired_leaf,
        undefined_edge_source,
        undefined_edge_target,
        undefined_path_map_target,
        removed_variant,
    ):
        with pytest.raises(KeyError, match="not a declared node"):
            operator(WORKFLOW, "ghost")


def test_the_termination_operators_refuse_a_node_that_is_already_cyclic() -> None:
    """Their origin has to **pass** P-02, and a drawn cycle is what would stop it.

    The same precondition ``unprotected_cycle`` carries, for a different reason: here it is not
    the region that would come out wrong but the falsifiability of the whole pair — on a draw that
    already carried an unwitnessed cycle the origin would fail P-02, and "removing the witness
    broke it" would be a claim about nothing.
    """
    cyclic = find(workflow_irs(), _has_cycle, settings=REACH)
    node = next(
        node.id
        for node in cyclic.nodes
        if build_graph_model(cyclic).components.is_nontrivial(node.id)
    )

    with pytest.raises(ValueError, match="already lies on a cycle"):
        removed_variant(cyclic, node)
    with pytest.raises(ValueError, match="already lies on a cycle"):
        counter_guard_without_exit(cyclic, node)


def test_the_well_formed_flag_is_a_breaking_p01_mutation_and_nothing_else() -> None:
    """The scope flag every cross-cutting metaproperty reads, held to both directions.

    §0.3 defines P-02's, P-04's and P-06's results only over P-01-clean topology, so this flag is
    what stops a claim about "every operator" from quietly asserting cross-validator agreement on
    ill-formed input. A *coherent* P-01 mutation is still well-formed — the repair is the point of
    it — which is why the flag is not simply ``target != "graph-well-formed"``.
    """
    broken = orphan_node(WORKFLOW)
    repaired = wired_leaf(WORKFLOW, "plan")
    contractual = unwritten_read(WORKFLOW, "book")

    assert not broken.well_formed
    assert check_graph_well_formed(broken.ir).result == "fail"
    assert repaired.well_formed
    assert check_graph_well_formed(repaired.ir).result == "pass"
    assert contractual.well_formed and contractual.breaking


def test_a_structural_prediction_carries_its_whole_anchor() -> None:
    """Hand-off (a): one location-valued slot, not a scalar per anchor field.

    §1.3 anchors a P-01 reference finding at an *edge* and §2.3 anchors a P-02 finding at an SCC
    or a cycle, neither of which ``node`` and ``key`` can express — so the record carries the
    whole location and a metaproperty compares it to the emitted one rather than picking it
    apart.
    """
    dangling = undefined_path_map_target(WORKFLOW, "plan")
    unwitnessed = removed_variant(WORKFLOW, "audit")

    assert isinstance(dangling.location, P01EdgeLocation)
    assert dangling.location.label == PROBE_LABEL
    assert dangling.location.undefined_target not in {node.id for node in WORKFLOW.nodes}
    assert isinstance(unwitnessed.location, P02SccLocation)
    assert unwitnessed.location.representative_cycle == ("audit",)
    assert unwitnessed.location.blanket_only is None


def test_an_unknown_operator_name_is_refused() -> None:
    """A typo in a metaproperty's ``operators=`` would otherwise silently widen its scope."""
    with pytest.raises(ValueError, match="are not dataflow-completeness operators"):
        dataflow_mutations(operators=("unwritten-reed",))
    with pytest.raises(ValueError, match="no operator selected"):
        effect_safety_mutations(operators=())


# ── The library's seams ──────────────────────────────────────────────────────────────────


def test_the_operator_tables_name_every_operator_exactly_once() -> None:
    """The tables are what a metaproperty selects with and what the reachability suite iterates.

    All five wedge properties have a family since TE-09; names are unique **across** the tables,
    not only inside one, because :func:`~gebra.testing.mutations._selected` resolves a name
    against one property's table and a name in two of them would make ``operators=`` ambiguous to
    a reader even where it is not to the code.
    """
    tables = (
        DATAFLOW_OPERATORS,
        EFFECT_SAFETY_OPERATORS,
        DETERMINISM_OPERATORS,
        WELL_FORMEDNESS_OPERATORS,
        TERMINATION_OPERATORS,
    )
    every = [name for table in tables for name in table]

    assert len(set(every)) == len(every)
    assert set(OPERATORS) == {
        "dataflow-completeness",
        "termination-witness",
        "graph-well-formed",
        "effect-safety",
        "determinism-replay",
    }
    assert tuple(OPERATORS.values()) == tables


def test_a_named_subset_is_offered_in_table_order() -> None:
    """Selection order is the table's, not the caller's, so shrinking is stable across callers."""
    chosen = find(
        dataflow_mutations(operators=("foreign-read", "unwritten-read")),
        lambda mutation: True,
        settings=REACH,
    )

    assert chosen.operator == "unwritten-read", "the earlier table row is what shrinks to"


def test_the_mutation_strategy_builders_are_memoized() -> None:
    """The same composition decision TE-08 pinned, for the same reason.

    A ``@st.composite`` body runs once per example, so a strategy rebuilt inside one is rebuilt a
    thousand times per metaproperty — and there are thirty of them.
    """
    assert dataflow_mutations() is dataflow_mutations()
    assert effect_safety_mutations(operators=["bound-key"]) is effect_safety_mutations(
        operators=("bound-key",)
    )
    assert determinism_mutations() is determinism_mutations()
    assert mutations() is mutations()
    assert dataflow_mutations() is not dataflow_mutations(operators=("self-write",))


def test_the_breaking_flag_is_the_condition_being_present() -> None:
    """One record, one invariant: a coherent mutation predicts a pass and names no condition."""
    breaking = bare_claim(WORKFLOW, "book", "external")
    coherent = compensation_hook(WORKFLOW, "book", "billable", "audit")

    assert isinstance(breaking, Mutation)
    assert breaking.breaking and breaking.condition is not None
    assert not coherent.breaking and coherent.condition is None


def _has_cycle(ir: WorkflowIR) -> bool:
    return bool(build_graph_model(ir).components.nontrivial)


# ── hypothesis stays an optional dependency of gebra.testing ─────────────────────────────

#: Import the module in a fresh interpreter where hypothesis is unavailable, and report how it
#: failed. The guard has to fire *before* the ``gebra.testing.strategies`` import below it, or
#: the message would name the wrong module and send a reader to the wrong install line.
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
    import gebra.testing.mutations
except ImportError as error:
    report["error"] = str(error)
else:
    report["error"] = None
print(json.dumps(report))
'''


def test_importing_gebra_testing_needs_no_hypothesis() -> None:
    """``gebra.testing`` must not pull the mutation library in — hypothesis is a dev dependency.

    Proven the only way a transitive import can be: in an interpreter where importing hypothesis
    raises. The loader, the lint and the harness keep working; only
    ``gebra.testing.mutations`` is unavailable, and it says so in its own name rather than
    failing with hypothesis's message or with the sibling module's.
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
    assert report["error"] is not None
    assert "gebra.testing.mutations" in report["error"]
