"""P-02 ``termination-witness`` against the vendored corpus (PROPERTY-CATALOG-SPEC §2).

Witness assembly and verification end to end: the three witness forms, the DEC-23-amended
discharge predicates, mixed node/edge S-assembly, Lemma-1 residual acyclicity, representative-
cycle fail reporting, the blanket-only WARNING note, and the PD-011 census — asserted as
**model equality** against the fixtures' own ``expected:`` blocks (A6 PC-6). The golden
harness owns that comparison corpus-wide (:mod:`gebra.testing.harness`); as in
``test_effect_safety.py`` this module reaches the fixtures through PyYAML and the models
directly, so it is an *independent* second path to the same assertion rather than a caller of
the harness that would pass whenever the harness agreed with itself.

Five things this module is careful about, because each is a place P-02 could look right and be
wrong:

* **The graph is asked of VAL-03, and that is asserted rather than reviewed.** A recording
  proxy over a shared :class:`~gebra.verify.graph.GraphModel` pins the *exact* surface P-02
  reads, and the shared model's own memos are inspected after a run — the Tarjan partition and
  the D4 anchor are found in its caches, which is direct evidence they were asked of it rather
  than recomputed locally.
* **Each DEC-23 ruling is separated by an input that would flip under the rejected reading.**
  Q1: a three-label router whose non-gated label re-enters the loop — all-continuation
  discharge would pass it; only-the-gated-label leaves its cycle failing. Q4: ``positive-04``'s
  inner guard has no label leaving its SCC yet discharges via its natural loop, and an
  irreducible two-header region falls back to the SCC test and refuses the discharge. Q2: both
  near-miss flavours are pinned, on both result paths.
* **Coverage is Lemma 1, and the mandatory path never enumerates.** A ring of chained diamonds
  carrying :math:`2^{60}` simple cycles through one vertex is verdict-checked in linear time on
  both polarities; the census — the one enumerator — aborts cleanly at its cap with the
  structured note, never a hang.
* **The certificate is re-checked, not trusted.** T-W-SPEC §6.2 makes the witness evidence
  because a consumer can re-verify it; the suite is that consumer — every certificate is
  checked to be a topological order of the residual the report implies.
* **The condition-ID registry stays closed.** P-02 owns exactly two RATIFIED strings, and no
  report over the whole corpus carries anything else; the note vocabulary is likewise closed
  at §2.3's five kinds and notes are never gate-bearing.

WA-07: nothing here executes a workflow, a node, or a network call. Fixtures are read with
PyYAML's safe loader; the ``ir:`` block is validated into the frozen IR models and read as
data; ``source_snippet`` is never touched; declared guard strings are matched against the §3
grammar by the VAL-06 recognizer and never evaluated.
"""

from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.ir import ConditionalEdge, WorkflowIR
from gebra.verify import (
    CoFailure,
    CycleCensus,
    Failure,
    GuardEdgeLabels,
    GuardEdgeRef,
    NodeLocation,
    P02CycleLocation,
    P02SccLocation,
    PropertyReport,
    StrictPromotion,
    TerminationWitness,
    WitnessNote,
    build_graph_model,
    check_dataflow_completeness,
    condition,
    conditions_for,
    emit_failure,
    from_display,
    is_emittable,
    is_implemented,
    models_equivalent,
    property_for_condition,
    run_property,
    strict_promotions,
    to_data,
    validate_location,
    validate_report,
)
from gebra.verify.conditions import ConditionOwnershipError
from gebra.verify.graph import GraphModel, ledger_sort_key
from gebra.verify.properties import termination_witness
from gebra.verify.properties.termination_witness import (
    CENSUS_CAP,
    COUNTER_GUARD_WITHOUT_EXIT_EDGE,
    CYCLE_WITHOUT_TERMINATION_WITNESS,
    PROPERTY_SLUG,
    check_termination_witness,
)
from tests.conftest import FIXTURES_DIR
from tools import honest_claims_lint
from tools.honest_claims_lint import load_phrases

#: The flagship 7+5 under ``termination-witness/`` (§2.6's 4+4 + the DEC-16 quartet, TE-14), by path.
FIXTURES: tuple[str, ...] = (
    "termination-witness/positive-01-counter-guarded-retry-loop.yaml",
    "termination-witness/positive-02-justified-recursion-limit-refinement-loop.yaml",
    "termination-witness/positive-03-shrinking-worklist-hotel-quotes.yaml",
    "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml",
    "termination-witness/positive-05-recursion-limit-only-scc-note.yaml",
    "termination-witness/positive-06-cycle-census-capped-overflow.yaml",
    "termination-witness/positive-07-acyclic-graph-vacuous-empty-inventory.yaml",
    "termination-witness/negative-01-unwitnessed-reflection-loop.yaml",
    "termination-witness/negative-02-nested-scc-outer-only-witness.yaml",
    "termination-witness/negative-03-counter-guard-without-wired-exit.yaml",
    "termination-witness/negative-04-supervisor-delegation-scc-no-witness.yaml",
    "termination-witness/negative-05-unwitnessed-self-loop.yaml",
)

POSITIVES: tuple[str, ...] = FIXTURES[:7]
NEGATIVES: tuple[str, ...] = FIXTURES[7:]

#: The mixed-corpus members §2.6 names as exercising P-02 (plus ``mixed/10``'s PR-4 entry;
#: ``mixed/05``'s share is the ruled FM-005 unmodelled record and is asserted as such below).
MIXED_02 = "mixed/02-unwitnessed-loop-reading-unwritten-key.yaml"
MIXED_08 = "mixed/08-express-path-skips-gate-writer-and-witnessed-exit.yaml"
MIXED_10 = "mixed/10-all-properties-pass-healthy-research-pipeline.yaml"

#: The two §0.4 condition IDs P-02 owns — the registry is closed, so the validator may emit
#: no other string (DEC-05 D4 makes them distinct, never overloaded).
P02_CONDITIONS: frozenset[str] = frozenset(
    {CYCLE_WITHOUT_TERMINATION_WITNESS, COUNTER_GUARD_WITHOUT_EXIT_EDGE}
)


# ── Fixture loading (§0.3's rule, spelled out — the second, independent path) ────────────


def _load(relative: str) -> dict[str, Any]:
    document = yaml.safe_load((FIXTURES_DIR / relative).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _ir_of(relative: str, key: str = "ir") -> WorkflowIR:
    """A fixture's IR block, validated into the frozen models (JSON mode, §2.5 note 4)."""
    return WorkflowIR.model_validate_json(json.dumps(_load(relative)[key]))


def _expected_report(relative: str) -> PropertyReport:
    """The fixture's ``expected:`` block as P-02's report — §0.3's loading rule verbatim."""
    return validate_report({"property": PROPERTY_SLUG, **_load(relative)["expected"]})


def _corpus_irs() -> list[tuple[str, WorkflowIR]]:
    """Every IR snapshot in the vendored corpus, both members of each evolution pair."""
    found: list[tuple[str, WorkflowIR]] = []
    for path in sorted(FIXTURES_DIR.glob("*/*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if block:
                identity = f"{path.parent.name}/{path.stem}:{key}"
                found.append((identity, WorkflowIR.model_validate_json(json.dumps(block))))
    return found


CORPUS = _corpus_irs()
CORPUS_IDS = [identity for identity, _ in CORPUS]


def _ir(document: dict[str, Any]) -> WorkflowIR:
    """A hand-built IR payload, validated exactly as a fixture's block is."""
    return WorkflowIR.model_validate_json(json.dumps({"ir_version": "1.0", **document}))


def _loop_ir(**overrides: Any) -> dict[str, Any]:
    """A minimal two-node retry loop, unwitnessed unless an override says otherwise."""
    payload: dict[str, Any] = {
        "entry": "work",
        "finish": "wrap",
        "state": {"item": "str", "spins": {"type": "int"}},
        "nodes": [{"id": "work"}, {"id": "review"}, {"id": "wrap"}],
        "edges": [
            {"from": "work", "to": "review"},
            {
                "from": "review",
                "kind": "conditional",
                "condition": "review judges completeness with no declared bound",
                "path_map": {"again": "work", "done": "wrap"},
            },
        ],
    }
    payload.update(overrides)
    return payload


def _flower(petals: int, *, parallel: int = 1, self_loops: int = 0) -> WorkflowIR:
    """A hub with ``petals`` two-node petals — a graph whose cycle count is arithmetic.

    Each petal contributes one vertex-simple cycle ``(hub, petal)``, carried by ``parallel``
    label-edges back to the hub, so it stands for ``parallel`` **edge-simple** cycles (§6.3's
    parallel-edge expansion). Each ``self_loops`` entry adds one length-1 cycle. The hub and
    the self-loop carriers hold ``variant`` annotations, so every cycle is discharged and the
    report passes — which is the only path Step 6's census runs on.
    """
    carrier = {"variant": {"key": "queue", "measure": "shrinks"}}
    nodes: list[dict[str, Any]] = [{"id": "hub", "annotations": carrier}]
    edges: list[dict[str, Any]] = []
    for index in range(petals):
        petal = f"petal_{index:02d}"
        nodes.append({"id": petal})
        edges.append({"from": "hub", "to": petal})
        edges.append(
            {"from": petal, "to": "hub"}
            if parallel == 1
            else {
                "from": petal,
                "kind": "conditional",
                "condition": "the petal decides opaquely",
                "path_map": {f"back_{choice}": "hub" for choice in range(parallel)},
            }
        )
    for index in range(self_loops):
        looper = f"looper_{index:02d}"
        nodes.append({"id": looper, "annotations": carrier})
        edges.extend([{"from": "hub", "to": looper}, {"from": looper, "to": looper}])
    nodes.append({"id": "out"})
    edges.append({"from": "hub", "to": "out"})
    return _ir(
        {
            "entry": "hub",
            "finish": "out",
            "state": {"queue": "list"},
            "nodes": nodes,
            "edges": edges,
        }
    )


def _blanket_only_ir() -> WorkflowIR:
    """§2.7's recorded gap shape: one unwitnessed loop under one justified blanket.

    No corpus fixture states it (DEC-16/TE-14 own the gap fixtures), and it is the input both
    §6.1 profiles are about — a pass with the WARNING-grade note by default, a fail with
    ``blanket_only: true`` under ``--gebra-strict``.
    """
    return _ir(
        _loop_ir(
            runtime={
                "recursion_limit": {
                    "value": 25,
                    "justification": "verification demo: two supersteps per review turn",
                }
            }
        )
    )


def _two_blanket_sccs_ir() -> WorkflowIR:
    """Two disjoint unwitnessed self-loops under one blanket — two promotable SCCs."""
    return _ir(
        {
            "entry": "alpha_work",
            "finish": "out",
            "state": {},
            "runtime": {
                "recursion_limit": {"value": 9, "justification": "demo budget for two loops"}
            },
            "nodes": [{"id": "alpha_work"}, {"id": "beta_work"}, {"id": "out"}],
            "edges": [
                {"from": "alpha_work", "to": "alpha_work"},
                {"from": "alpha_work", "to": "beta_work"},
                {"from": "beta_work", "to": "beta_work"},
                {"from": "beta_work", "to": "out"},
            ],
        }
    )


def _d4_under_blanket_ir() -> WorkflowIR:
    """A saturated counter guard in one loop and a blanket-covered second loop."""
    return _ir(
        {
            "entry": "alpha_check",
            "finish": "out",
            "state": {"spins": {"type": "int"}},
            "runtime": {
                "recursion_limit": {"value": 25, "justification": "demo budget for both loops"}
            },
            "nodes": [
                {"id": "alpha_check"},
                {"id": "alpha_work"},
                {"id": "beta_check"},
                {"id": "beta_work"},
                {"id": "out"},
            ],
            "edges": [
                {"from": "alpha_work", "to": "alpha_check"},
                {
                    "from": "alpha_check",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'retry'",
                    "path_map": {"again": "alpha_work", "retry": "alpha_work"},
                },
                {"from": "alpha_check", "to": "beta_check"},
                {"from": "beta_work", "to": "beta_check"},
                {
                    "from": "beta_check",
                    "kind": "conditional",
                    "condition": "an opaque reviewer judgement with no declared bound",
                    "path_map": {"again": "beta_work", "done": "out"},
                },
            ],
        }
    )


def _hand_built_shapes() -> tuple[tuple[str, WorkflowIR], ...]:
    """The shapes the corpus does not state, which the sweeps below run beside all 67 of it.

    Every way a ``recursion_limit`` reaches P-02 — covering a cycle alone, covering two, and
    riding a report that fails for another reason — plus the unjustified slot that is no
    blanket at all and the over-cap graph whose census aborts. Between them they reach both
    result paths, both ``blanket_only`` polarities, and the three note kinds a blanket or a
    cap can produce; the two guard-side kinds have their own tests and no bearing on the
    strict path, since neither is WARNING-grade.
    """
    return (
        ("blanket-only", _blanket_only_ir()),
        ("two-blanket-sccs", _two_blanket_sccs_ir()),
        ("d4-under-blanket", _d4_under_blanket_ir()),
        (
            "unjustified-limit",
            _ir(_loop_ir(runtime={"recursion_limit": {"value": 25, "justification": ""}})),
        ),
        ("census-aborted", _flower(CENSUS_CAP + 1)),
    )


def _census_of(ir: WorkflowIR) -> tuple[CycleCensus | None, tuple[WitnessNote, ...]]:
    """The census and notes of a passing report — the public Step 6 path, asserted as one."""
    report = check_termination_witness(ir)
    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    return report.witness.cycles, report.witness.notes


# ── The corpus: every P-02 obligation, model-equal (acceptance box 1) ────────────────────


@pytest.mark.parametrize("relative", FIXTURES, ids=[f.rsplit("/", 1)[1] for f in FIXTURES])
def test_the_flagship_fixture_report_is_model_equal(relative: str) -> None:
    """All eight ``termination-witness/`` fixtures, raw ``expected:`` block vs live report.

    Nothing is normalized on either side: the fixture's block is validated through §0.3's own
    loading rule and the validator's report must equal it as models — inventory, certificate,
    census, location, representative cycle and all.
    """
    produced = check_termination_witness(_ir_of(relative))

    assert models_equivalent(produced, _expected_report(relative))


def test_mixed_02_projects_to_this_validators_own_report() -> None:
    """``mixed/02``'s PR-1 projection: the block minus the P-04 co-failure is P-02's report.

    The restriction rule is FIDELITY-MATRIX §2's: co-failures another property holds are
    dropped (a P-02 validator cannot emit a P-04 record — the ownership gate refuses it), and
    what remains must be reproduced exactly.
    """
    expected = _load(MIXED_02)["expected"]
    failure = dict(expected["failure"])
    assert all(record["property"] != PROPERTY_SLUG for record in failure.pop("co_failures"))
    projected = validate_report({"property": PROPERTY_SLUG, **expected, "failure": failure})

    produced = check_termination_witness(_ir_of(MIXED_02))

    assert models_equivalent(produced, projected)


def test_mixed_08_records_match_the_co_failure_multiset() -> None:
    """``mixed/08``'s PR-2 projection: P-02's own records vs the fixture's P-02 co-failure.

    The fixture packages P-02's finding on a P-04 primary, so only the (condition ID,
    location) records are comparable — and P-02's own report must state exactly that record:
    the full five-node residual SCC with the minimal bypass cycle as its one representative.
    """
    records = [
        (record["property_condition"], validate_location(record["location"]))
        for record in _load(MIXED_08)["expected"]["failure"]["co_failures"]
        if record["property"] == PROPERTY_SLUG
    ]
    assert len(records) == 1

    produced = check_termination_witness(_ir_of(MIXED_08))

    assert produced.failure is not None
    assert produced.failure.co_failures is None
    emitted = (produced.failure.property_condition, produced.failure.location)
    assert emitted[0] == records[0][0]
    assert models_equivalent(emitted[1], records[0][1])


def test_mixed_10_witness_entry_is_this_validators_pass_shape() -> None:
    """``mixed/10``'s PR-4 projection: the multi-property witness entry, as P-02's report.

    The corpus's one all-properties-pass fixture, green since the DEC-23 revision put its
    router guard back inside the §3 grammar (`'retry' if publish failed and attempts < 3
    else 'done'`) — the VAL-06-flagged hazard this card's acceptance box budgeted for,
    resolved on the WA-04 route before this validator registered.
    """
    entry = _load(MIXED_10)["expected"]["witness"]["properties"][PROPERTY_SLUG]
    projected = validate_report({"property": PROPERTY_SLUG, "result": "pass", "witness": entry})

    produced = check_termination_witness(_ir_of(MIXED_10))

    assert models_equivalent(produced, projected)


def test_mixed_05_stays_the_ruled_unmodelled_deviation() -> None:
    """``mixed/05``'s P-02 share is FM-005: `snapshot: ir_after` has no §0.3 location shape.

    Ruled *keep* at DEC-17 (P-12's pair-scoping convention), so P-02 registering moves
    nothing: the obligation is decided before any validator runs. Asserted here so the suite
    states the whole P-02 corpus story rather than the eleven green shares of it.
    """
    record = next(
        entry
        for entry in _load("mixed/05-evolution-drops-witness-and-state-field.yaml")["expected"][
            "failure"
        ]["co_failures"]
        if entry["property"] == PROPERTY_SLUG
    )
    with pytest.raises(Exception, match="snapshot"):
        validate_location(record["location"])


# ── Registration, dispatch, and the closed registry ──────────────────────────────────────


def test_the_validator_is_registered_and_dispatches() -> None:
    """Importing the module registers it, which is what ``run_property`` dispatches on."""
    assert is_implemented(PROPERTY_SLUG)

    dispatched = run_property(PROPERTY_SLUG, _ir_of(MIXED_02))

    assert isinstance(dispatched, PropertyReport)
    assert models_equivalent(dispatched, check_termination_witness(_ir_of(MIXED_02)))


def test_the_two_condition_ids_are_the_registrys_p02_entries() -> None:
    """§2.3's condition table is exactly the two RATIFIED P-02 entries of the §0.4 registry.

    The registry is enumerated in the direction that can fail: ``conditions_for`` returns
    every entry filed against this property, so a third one added to §0.4 without a validator
    change lands on the left-hand side and fails here rather than passing silently.
    """
    filed = {entry.id for entry in conditions_for(PROPERTY_SLUG)}

    assert filed == P02_CONDITIONS
    assert {entry.tier for entry in conditions_for(PROPERTY_SLUG)} == {"ratified"}
    assert {condition(name).severity for name in P02_CONDITIONS} == {"fatal"}
    assert {condition(name).claim_class for name in P02_CONDITIONS} == {"defensible"}


def test_no_corpus_report_carries_a_string_outside_the_two() -> None:
    """Over all 67 snapshots, every emitted condition ID is one of P-02's own two.

    The §0.4 registry discipline made observable: PROPOSED names are not emittable, another
    property's names are refused by the ownership gate, and the note kinds are §2.3's closed
    five — never condition IDs.
    """
    note_kinds = {
        "scc-covered-only-by-recursion-limit",
        "recursion-limit-without-justification",
        "variant-key-not-in-state",
        "counter-key-not-qualified",
        "cycle-census-capped",
    }
    for identity, ir in CORPUS:
        report = check_termination_witness(ir)
        if report.failure is not None:
            emitted = {report.failure.property_condition} | {
                record.property_condition for record in report.failure.co_failures or ()
            }
            assert emitted <= P02_CONDITIONS, identity
            assert {note.kind for note in report.failure.notes or ()} <= note_kinds, identity
        if report.witness is not None:
            assert isinstance(report.witness, TerminationWitness)
            assert {note.kind for note in report.witness.notes} <= note_kinds, identity


def test_another_propertys_condition_is_refused_at_emission() -> None:
    """The ownership gate: P-02 cannot emit a name §0.4 holds for someone else."""
    anchor = P02SccLocation(
        kind="scc", nodes=("a", "b"), representative_cycle=("a", "b"), exhaustive=False
    )
    with pytest.raises(ConditionOwnershipError):
        emit_failure(PROPERTY_SLUG, "read-key-never-written-on-path", anchor)


# ── Graph machinery: cited from VAL-03, not redefined (acceptance box 4) ─────────────────


def test_the_shared_model_supplies_the_partition_and_the_d4_anchor() -> None:
    """ "Cited, not redefined", asserted through VAL-03's own memos.

    :class:`~gebra.verify.graph.GraphModel` memoizes its Tarjan partition and each anchor
    cycle, so their *presence* in a model P-02 has run over is direct evidence they were
    asked of it rather than recomputed locally — a locally computed anchor that happened to
    agree would still leave the cache empty. ``negative-03`` covers the anchor because its
    D4 finding is the one place §2.4's ``cycle_through`` is needed.
    """
    relative = "termination-witness/negative-03-counter-guard-without-wired-exit.yaml"
    shared = build_graph_model(_ir_of(relative), carry_unresolved_references=True)
    assert "components" not in shared.__dict__

    report = check_termination_witness(_ir_of(relative), model=shared)

    assert "components" in shared.__dict__, "the Tarjan pass was not asked of the shared model"
    location = report.failure.location if report.failure else None
    assert isinstance(location, P02CycleLocation)
    assert shared._anchor_cache[location.guard_edge.source] == location.nodes


def test_the_module_asks_the_shared_model_for_exactly_this_surface() -> None:
    """The whole graph surface P-02 reads, pinned — a recording proxy over the shared model.

    Anything P-02 needed and did not find here it would have had to derive itself, so the
    set is the machine-checkable form of the acceptance box. Every member is VAL-03's: the
    convention check (``unresolved``/``carried``), the Tarjan partition, the adjacency views
    behind the dominator pass and the census, the induced subgraphs, the D4 anchor, and the
    raw vertex/edge material the residual is filtered from.

    Two fixtures, unioned, because a single one under-reports: the D4 anchor is asked only
    where a saturated counter guard exists (``negative-03``), and the census's subgraph walk
    runs only on a pass (``positive-04``).
    """
    touched: set[str] = set()
    fixtures = (
        "termination-witness/negative-03-counter-guard-without-wired-exit.yaml",
        "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml",
    )

    for relative in fixtures:
        shared = build_graph_model(_ir_of(relative), carry_unresolved_references=True)

        class _Recorder:
            def __init__(self, wrapped: GraphModel) -> None:
                self._wrapped = wrapped

            def __getattr__(self, name: str) -> Any:
                touched.add(name)
                return getattr(self._wrapped, name)

        report = check_termination_witness(_ir_of(relative), model=_Recorder(shared))  # type: ignore[arg-type]
        assert models_equivalent(report, check_termination_witness(_ir_of(relative)))

    assert touched == {
        "anchor_cycle",
        "carried",
        "components",
        "edges",
        "node_ids",
        "out_edges",
        "predecessors",
        "subgraph",
        "successors",
        "unresolved",
        "vertices",
    }


def test_the_module_imports_its_graph_primitives_and_nothing_else() -> None:
    """The import set is exact, so a second graph implementation cannot arrive unnoticed.

    ``networkx`` is the specific thing this refuses: the catalog's primitive rows are
    implementability checklists, and ``tests/verify/test_base.py`` keeps it out of
    ``import gebra.verify``'s closure entirely. The two stdlib members beside ``typing`` are
    pure-data and carry no substrate — ``collections.abc`` for the ``Mapping``/``Iterator``
    annotations and ``dataclasses`` for :class:`~gebra.verify.StrictPromotion`, the
    ``collections`` half on the ``effect_safety.py`` precedent.
    """
    tree = ast.parse(Path(termination_witness.__file__).read_text(encoding="utf-8"))
    imported = {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported == {"__future__", "collections", "dataclasses", "gebra", "typing"}


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_a_shared_model_and_a_private_one_give_the_same_report(
    identity: str, ir: WorkflowIR
) -> None:
    """``verify()`` will build one model for every topology validator; sharing changes nothing."""
    shared = build_graph_model(ir, carry_unresolved_references=True)

    assert models_equivalent(
        check_termination_witness(ir, model=shared), check_termination_witness(ir)
    ), identity


def test_a_model_built_on_the_drop_convention_is_refused() -> None:
    """§0.3 names P-02's degradation convention; the other one is P-01's and P-06's.

    On clean topology the two builds are identical, so the refusal needs dirty input to be
    observable: a dangling ``path_map`` target that a drop-convention model recorded and did
    not materialize.
    """
    dangling = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "review judges completeness with no declared bound",
                    "path_map": {"again": "work", "done": "phantom"},
                },
            ]
        )
    )
    dropped = build_graph_model(dangling, carry_unresolved_references=False)

    with pytest.raises(ValueError, match="carry_unresolved_references=True"):
        check_termination_witness(dangling, model=dropped)

    carried = build_graph_model(dangling, carry_unresolved_references=True)
    assert models_equivalent(
        check_termination_witness(dangling, model=carried), check_termination_witness(dangling)
    )


# ── DEC-23 Q1 — only the gated then-label edge discharges ────────────────────────────────


def test_a_non_gated_in_scc_label_is_never_discharged() -> None:
    """The input the two Q1 readings disagree on: a router with a second in-loop label.

    ``'retry' if spins < 3 else 'escalate'`` also declares an ``audit`` label that re-enters
    the loop. All-continuation discharge (the corrected §2.4 drafting residue) would remove
    both label-edges and pass; DEC-23's single-gated-label rule removes only ``retry``, so
    the ``audit`` continuation survives the residual and the run fails on it — the
    over-discharge ban made observable.
    """
    ir = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'retry' if spins < 3 else 'escalate'",
                    "path_map": {"retry": "work", "audit": "work", "escalate": "wrap"},
                },
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    location = report.failure.location
    assert isinstance(location, P02SccLocation)
    assert location.nodes == ("review", "work")


def test_the_else_label_is_never_discharged_even_when_it_re_enters() -> None:
    """R6's implicit negation context: an in-SCC else-label is not bounded by the counter.

    ``test`` false can hold with the counter unbounded (the opaque conjunct fails), so
    discharging the else-edge would discharge an unbounded branch. Here the else-label
    re-enters the loop and the then-label exits: the guard qualifies but contributes no
    S-element (the §4 corollary's exit-on-truth wiring), and the cycle fails.
    """
    ir = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'done' if spins < 3 else 'again'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS


def test_a_then_label_missing_from_the_path_map_contributes_nothing() -> None:
    """A recognized guard whose gated label is wired to no edge has nothing to discharge.

    Fail-closed like every §3 exclusion — no S-element and no diagnostic (no note kind
    exists for it) — and the loop fails as unwitnessed.
    """
    ir = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'retry' if spins < 3 else 'done'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.notes is None


def test_only_the_gated_expansion_of_duplicate_routers_is_removed_per_ordinal() -> None:
    """Parallel label-edges are distinct simple cycles; a discharge names one ordinal only.

    Two byte-identical routers wire two parallel ``retry`` edges. Each qualifies and each
    discharges its *own* (ordinal, label) expansion — the residual loses both, but through
    two S-elements, and the inventory says so. Merging parallels (the ``nx.DiGraph``
    hazard §2.4 Step 0 names) would let one discharge stand for both.
    """
    router = {
        "from": "review",
        "kind": "conditional",
        "condition": "'retry' if spins < 3 else 'done'",
        "path_map": {"retry": "work", "done": "wrap"},
    }
    ir = _ir(_loop_ir(edges=[{"from": "work", "to": "review"}, router, dict(router)]))

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    entries = [entry for entry in report.witness.inventory if entry.form == "a"]
    assert len(entries) == 2
    census = report.witness.cycles
    assert census is not None
    assert census.cycles == (("review", "work"), ("review", "work"))


# ── DEC-23 Q4 — the D4 side condition is loop-relative, with the SCC fallback ────────────


def test_positive_04s_inner_guard_discharges_through_its_natural_loop() -> None:
    """The flagship Q4 case: no label of ``validate_quote`` leaves its SCC, yet it passes.

    The inner guard's ``accept`` label exits its own 2-node natural loop
    ``{quote_fares, validate_quote}`` while staying inside the enclosing 4-node SCC — the
    literal (superseded) SCC-relative reading would emit ``counter-guard-without-exit-edge``
    here and flip the flagship positive. The clean pass with both inventory entries is the
    ruled behaviour, and the model-equality test above already pins the full report; this
    test names the discriminating fact.
    """
    relative = "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml"
    ir = _ir_of(relative)
    model = build_graph_model(ir, carry_unresolved_references=True)
    scc = model.components.members_of("validate_quote")
    resolved = {
        target
        for edge in ir.edges
        if isinstance(edge, ConditionalEdge) and edge.from_ == "validate_quote"
        for target in edge.path_map.values()
    }
    assert resolved <= set(scc), "the discriminating fact: no label leaves the SCC"

    report = check_termination_witness(ir)

    assert report.result == "pass"


def test_an_irreducible_region_falls_back_to_the_scc_test() -> None:
    """Two entry arcs into one loop: no single header dominates, so D4 coarsens, fail-closed.

    ``left`` and ``right`` are both wired from START and form a two-node cycle; the guard's
    gated re-entry ``left → right`` has no dominating header (each vertex can be reached
    avoiding the other), so the natural loop is undefined and the side condition falls back
    to SCC membership. The guard's labels both stay inside the SCC, so the fallback refuses
    the discharge and the distinct D4 condition fires — the coarser test can only refuse.
    """
    ir = _ir(
        {
            "entry": ["left", "right"],
            "finish": "out",
            "state": {"spins": {"type": "int"}},
            "nodes": [{"id": "left"}, {"id": "right"}, {"id": "out"}],
            "edges": [
                {"from": "right", "to": "left"},
                {"from": "right", "to": "out"},
                {
                    "from": "left",
                    "kind": "conditional",
                    "condition": "'go' if spins < 5 else 'stay'",
                    "path_map": {"go": "right", "stay": "right"},
                },
            ],
        }
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == COUNTER_GUARD_WITHOUT_EXIT_EDGE
    location = report.failure.location
    assert isinstance(location, P02CycleLocation)
    assert location.nodes == ("left", "right")
    assert location.counter_key == "spins"
    assert location.guard_edge.source == "left"
    assert location.guard_edge.labels == ("go", "stay")


def test_the_natural_loop_is_strictly_narrower_than_the_scc_on_mixed_08() -> None:
    """``mixed/08``'s ``revise`` discharge is licensed by a 2-node loop inside a 5-node SCC.

    The discriminating structure behind the corpus trace: ``quality_gate``'s ``approve``
    label targets ``compliance_gate``, which is *inside* the SCC but outside the natural
    loop ``{draft_reply, quality_gate}`` — so the superseded SCC-relative reading would
    refuse this discharge too and mis-shape the report (a D4 finding instead of the
    residual-SCC finding the fixture pins).
    """
    ir = _ir_of(MIXED_08)
    model = build_graph_model(ir, carry_unresolved_references=True)
    scc = set(model.components.members_of("quality_gate"))
    assert "compliance_gate" in scc

    report = check_termination_witness(ir)

    assert report.failure is not None
    assert report.failure.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS


def test_a_guard_in_an_unreachable_loop_falls_back_to_the_scc_test() -> None:
    """Dominance is defined from START only; an unreachable region has none — so D4 coarsens.

    A loop no START-path reaches is P-01's condition-(i) finding, so this is the §0.3
    best-effort surface — what is pinned is the *direction* of the degradation: the natural
    loop is undefined off the dominator tree, the side condition falls back to the SCC test
    (fail-closed), and a wired escape still discharges rather than the guard being dropped.
    """
    ir = _ir(
        {
            "entry": "solo",
            "finish": "solo",
            "state": {"spins": {"type": "int"}},
            "nodes": [{"id": "solo"}, {"id": "work"}, {"id": "review"}, {"id": "wrap"}],
            "edges": [
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'done'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ],
        }
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    assert [entry.form for entry in report.witness.inventory] == ["a"]


def test_a_self_loop_guard_discharges_itself_when_an_exit_is_wired() -> None:
    """The degenerate natural loop: a gated self-loop's header is its own source.

    ``review → review`` on the gated label is a back edge whose natural loop is
    ``{review}``; the ``done`` label leaves it, so the guard discharges and the self-loop —
    a simple cycle of length 1 (T-W-SPEC §1) — is covered. The census reports it as the
    length-1 cycle.
    """
    ir = _ir(
        _loop_ir(
            nodes=[{"id": "review"}, {"id": "wrap"}],
            entry="review",
            edges=[
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'done'",
                    "path_map": {"again": "review", "done": "wrap"},
                }
            ],
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    census = report.witness.cycles
    assert census is not None
    assert census.cycles == (("review",),)


# ── DEC-05 D4 — the distinct condition, and DEC-11's subsumption ─────────────────────────


def test_negative_03_emits_the_d4_condition_alone() -> None:
    """A saturated counter guard subsumes the base condition for its SCC (DEC-05 D2 via DEC-11).

    Both of ``throttle_check``'s labels re-enter the loop, so the D4 condition fires at
    S-construction — and the same SCC survives the residual, which without the subsumption
    rule would stack ``cycle-without-termination-witness`` on top. The fixture expects the
    D4 condition alone; the model-equality test pins the shape, and this one asserts the
    absence that makes it right.
    """
    report = check_termination_witness(
        _ir_of("termination-witness/negative-03-counter-guard-without-wired-exit.yaml")
    )

    assert report.failure is not None
    assert report.failure.property_condition == COUNTER_GUARD_WITHOUT_EXIT_EDGE
    assert report.failure.co_failures is None


def test_a_d4_finding_stacks_with_an_unrelated_residual_scc_in_merged_order() -> None:
    """Two findings, one merged deterministic order: (anchor-SCC node tuple, condition ID).

    A saturated guard in one loop and a plain unwitnessed second loop: the D4 finding
    anchors at ``{alpha_work, alpha_check}``, the residual finding at ``{beta_work,
    beta_check}`` — the alpha tuple sorts first, so the D4 finding is the primary and the
    base condition rides ``co_failures``.
    """
    ir = _ir(
        {
            "entry": "alpha_check",
            "finish": "out",
            "state": {"spins": {"type": "int"}},
            "nodes": [
                {"id": "alpha_check"},
                {"id": "alpha_work"},
                {"id": "beta_check"},
                {"id": "beta_work"},
                {"id": "out"},
            ],
            "edges": [
                {"from": "alpha_work", "to": "alpha_check"},
                {
                    "from": "alpha_check",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'retry'",
                    "path_map": {"again": "alpha_work", "retry": "alpha_work"},
                },
                {"from": "alpha_check", "to": "beta_check"},
                {"from": "beta_work", "to": "beta_check"},
                {
                    "from": "beta_check",
                    "kind": "conditional",
                    "condition": "an opaque reviewer judgement with no declared bound",
                    "path_map": {"again": "beta_work", "done": "out"},
                },
            ],
        }
    )

    report = check_termination_witness(ir)

    assert report.failure is not None
    assert report.failure.property_condition == COUNTER_GUARD_WITHOUT_EXIT_EDGE
    assert isinstance(report.failure.location, P02CycleLocation)
    assert report.failure.co_failures is not None
    (base,) = report.failure.co_failures
    assert base.property == PROPERTY_SLUG
    assert base.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert base.severity == "fatal"
    assert base.claim_class == "defensible"
    location = base.location
    assert isinstance(location, P02SccLocation)
    assert location.nodes == ("beta_check", "beta_work")


def test_the_d4_guard_edge_labels_ride_in_authored_path_map_order() -> None:
    """`guard_edge.labels` is ``keys(path_map)`` — authored order, not sorted.

    ``negative-03`` pins ``[immediate, delayed]``, which the ledger comparator would
    reverse; asserted directly so a helpful sort cannot creep in.
    """
    report = check_termination_witness(
        _ir_of("termination-witness/negative-03-counter-guard-without-wired-exit.yaml")
    )

    assert report.failure is not None
    location = report.failure.location
    assert isinstance(location, P02CycleLocation)
    assert location.guard_edge.labels == ("immediate", "delayed")


# ── DEC-23 Q2 — the near-miss note, on both result paths ─────────────────────────────────


def test_a_counter_key_absent_from_sigma_notes_the_near_miss_on_the_fail_path() -> None:
    """§4 path 1, first flavour: recognized shape, counter-ref not in keys(Σ).

    The guard contributes no witness, the loop fails — and the failure carries the
    ``counter-key-not-qualified`` note with the gated label-edge and the unmatched
    identifier, unconditionally (DEC-23: no "sole witness attempt" gating). ``declared_type``
    is absent: no type exists for a key that is not there.
    """
    ir = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'again' if spin_count < 3 else 'done'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.notes == (
        WitnessNote(
            kind="counter-key-not-qualified",
            guard_edge=GuardEdgeRef(source="review", label="again"),
            identifier="spin_count",
        ),
    )


def test_a_wrongly_typed_counter_notes_identifier_and_declared_type() -> None:
    """§4 path 1, second flavour: the key exists but its declared type is not ``int``.

    The §2.1 normative enumeration admits nothing else — ``float`` does not qualify — and
    the note carries the declared type alongside the identifier, exactly the evidence
    ``CounterQualification`` computes.
    """
    ir = _ir(
        _loop_ir(
            state={"item": "str", "spins": "float"},
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'done'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ],
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.notes == (
        WitnessNote(
            kind="counter-key-not-qualified",
            guard_edge=GuardEdgeRef(source="review", label="again"),
            identifier="spins",
            declared_type="float",
        ),
    )


def test_a_near_miss_beside_a_real_witness_rides_the_pass_witness() -> None:
    """The same note on the pass path: a misspelled counter never silently shrinks coverage.

    One loop, two guards: the near-missed spelling on an off-cycle router and a qualifying
    one on the loop. The report passes on the real witness and still surfaces the near-miss
    as a ``TerminationWitness.notes`` entry — §4's MUST-emit, on the path where nothing
    failed. (The note is recorded at qualification time, before any wiring is looked at.)
    """
    ir = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'escalate' if spin_count < 3 else 'done'",
                    "path_map": {"escalate": "wrap", "done": "wrap"},
                },
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'done'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    assert [note.kind for note in report.witness.notes] == ["counter-key-not-qualified"]
    assert report.witness.notes[0].identifier == "spin_count"


def test_an_opaque_guard_is_not_a_near_miss() -> None:
    """R5's boundary: an opaque string declared nothing, and gets no diagnostic.

    ``negative-01``'s router names no bounded counter at all — the report carries no notes,
    which is what separates "declared and failed to qualify" from "not declared".
    """
    report = check_termination_witness(
        _ir_of("termination-witness/negative-01-unwitnessed-reflection-loop.yaml")
    )

    assert report.failure is not None
    assert report.failure.notes is None


# ── Form (c) — the variant carrier, its note, and the vacuous entry ──────────────────────


def test_a_variant_key_outside_sigma_notes_and_contributes_nothing() -> None:
    """§4 path 4: the carrier node and the missing key, no witness contribution."""
    ir = _ir(
        _loop_ir(
            nodes=[
                {"id": "work", "annotations": {"variant": {"key": "queue", "measure": "shrinks"}}},
                {"id": "review"},
                {"id": "wrap"},
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.notes == (
        WitnessNote(kind="variant-key-not-in-state", node="work", key="queue"),
    )


def test_a_variant_on_an_acyclic_node_is_a_vacuous_inventory_entry() -> None:
    """§6.2: declared content is surfaced with the explicit empty marker, no finding.

    The carrier lies on no cycle, so ``discharges`` is the structured empty set — never a
    string — and the graph's real loop still needs (and here has) its own witness.
    """
    ir = _ir(
        _loop_ir(
            nodes=[
                {"id": "work"},
                {"id": "review"},
                {"id": "wrap", "annotations": {"variant": {"key": "item", "measure": "shrinks"}}},
            ],
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "'again' if spins < 3 else 'done'",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ],
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    vacuous = [entry for entry in report.witness.inventory if entry.form == "c"]
    assert len(vacuous) == 1
    assert vacuous[0].discharges == ()


def test_a_variant_carrier_discharges_every_cycle_through_it() -> None:
    """Form (c) is node-level: deletion removes all incident edges, exactly right (§4).

    ``positive-03`` pins the corpus shape; here the carrier sits on two interleaved cycles
    and one annotation covers both — one shared S-element legitimately covers every simple
    cycle through it (D1's other half).
    """
    ir = _ir(
        {
            "entry": "hub",
            "finish": "out",
            "state": {"queue": "list"},
            "nodes": [
                {"id": "hub", "annotations": {"variant": {"key": "queue", "measure": "shrinks"}}},
                {"id": "left"},
                {"id": "right"},
                {"id": "out"},
            ],
            "edges": [
                {"from": "hub", "to": "left"},
                {"from": "left", "to": "hub"},
                {"from": "hub", "to": "right"},
                {"from": "right", "to": "hub"},
                {"from": "hub", "to": "out"},
            ],
        }
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    assert [entry.form for entry in report.witness.inventory] == ["c"]
    census = report.witness.cycles
    assert census is not None
    assert census.cycles == (("hub", "left"), ("hub", "right"))


# ── Form (b) — the blanket, the WARNING-grade note, and the unjustified slot ─────────────


def test_the_blanket_only_case_passes_with_the_warning_grade_note() -> None:
    """Acceptance box 3: a justified ``recursion_limit`` alone is PASS with the §2.4 note.

    The corpus has no (b)-only fixture (§2.7 records the gap), so the shape is built here:
    an unwitnessed loop under a justified blanket. The element residual keeps the SCC, and
    the profile gate turns what would be the failure into the WARNING-grade structured note
    — kind ``scc-covered-only-by-recursion-limit``, ``severity: warning`` (the §0.2
    promotable grade; promotion changes the gate, never this record), carrying the residual
    SCC with its representative cycle and ``blanket_only: true`` — §6.1's second row fills
    the payload's ``<justified (b) present?>`` slot for the note exactly as it does for the
    strict row's finding. The inventory still lists the blanket, and the certificate is over
    the element residual, which kept every edge.
    """
    report = check_termination_witness(_blanket_only_ir())

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    assert [entry.form for entry in report.witness.inventory] == ["b"]
    assert report.witness.inventory[0].discharges == "blanket"
    assert report.witness.notes == (
        WitnessNote(
            kind="scc-covered-only-by-recursion-limit",
            severity="warning",
            locations=(
                P02SccLocation(
                    kind="scc",
                    nodes=("review", "work"),
                    representative_cycle=("review", "work"),
                    exhaustive=False,
                    blanket_only=True,
                ),
            ),
        ),
    )


def test_a_blanket_covering_two_sccs_notes_each_residual_scc() -> None:
    """One note per residual non-trivial SCC, in sorted-tuple order — §2.4's per-K payload.

    Two disjoint unwitnessed loops under one blanket: each surviving SCC gets its own
    structured note with its own representative, which is the shape a strict-profile
    promotion turns into per-SCC promotions without re-deriving anything — which
    :func:`test_one_promotion_per_blanket_covered_scc_in_the_records_own_order` is.
    """
    report = check_termination_witness(_two_blanket_sccs_ir())

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    noted: list[tuple[str, tuple[str, ...]]] = []
    for note in report.witness.notes:
        assert note.locations is not None
        (covered,) = note.locations
        assert isinstance(covered, P02SccLocation)
        noted.append((note.kind, covered.nodes))
    assert noted == [
        ("scc-covered-only-by-recursion-limit", ("alpha_work",)),
        ("scc-covered-only-by-recursion-limit", ("beta_work",)),
    ]


def test_element_witnesses_silence_the_blanket_note() -> None:
    """``positive-02``'s shape, asserted from the model side: covered SCCs need no note.

    The blanket is in the inventory, but the element residual is acyclic — no residual SCC
    is (b)-only covered, so no WARNING note is owed (the fixture's own ``notes:`` block says
    exactly this in prose).
    """
    report = check_termination_witness(
        _ir_of("termination-witness/positive-02-justified-recursion-limit-refinement-loop.yaml")
    )

    assert isinstance(report.witness, TerminationWitness)
    assert [entry.form for entry in report.witness.inventory] == ["a", "b"]
    assert report.witness.notes == ()


def test_an_empty_justification_contributes_no_witness_and_notes_itself() -> None:
    """§2.2 defense in depth: the model requires the member, so the empty string is the gap.

    A ``recursion_limit`` whose justification is ``""`` is no blanket: the loop fails, and
    the ``recursion-limit-without-justification`` note rides the failure.
    """
    ir = _ir(_loop_ir(runtime={"recursion_limit": {"value": 25, "justification": ""}}))

    report = check_termination_witness(ir)

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.notes == (WitnessNote(kind="recursion-limit-without-justification"),)


def test_d4_findings_gate_even_under_a_justified_blanket() -> None:
    """§2.4 Step 5's closing rule: the blanket softens residual SCCs, never a D4 defect.

    A saturated counter guard in one loop and a plain unwitnessed second loop, both under a
    justified blanket: the run still **fails** with the distinct D4 condition (the blanket
    is no answer to a wiring defect), the second SCC — which the blanket does cover — rides
    the failure as the WARNING note rather than a second finding, and the D4-subsumed SCC
    itself gets neither note nor base condition (one root cause, one record). Nothing is
    dropped: DEC-23's unconditional fail-path carriage puts the note on ``Failure.notes``.
    """
    report = check_termination_witness(_d4_under_blanket_ir())

    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == COUNTER_GUARD_WITHOUT_EXIT_EDGE
    assert report.failure.co_failures is None
    assert report.failure.notes is not None
    (note,) = report.failure.notes
    assert note.kind == "scc-covered-only-by-recursion-limit"
    assert note.locations is not None
    covered = note.locations[0]
    assert isinstance(covered, P02SccLocation)
    assert covered.nodes == ("beta_check", "beta_work")


# ── Lemma 1 — residual acyclicity, the certificate, and no enumeration ───────────────────


@pytest.mark.parametrize("relative", POSITIVES, ids=[f.rsplit("/", 1)[1] for f in POSITIVES])
def test_the_certificate_is_a_re_checkable_topological_order(relative: str) -> None:
    """T-W-SPEC §6.2: any consumer re-checks the certificate with no trust in the checker.

    This suite is that consumer: the residual is re-derived from the report's own inventory
    (remove each form-(a) label-edge and each form-(c) carrier), and every residual edge
    must run forward in the certificate.
    """
    ir = _ir_of(relative)
    report = check_termination_witness(ir)
    assert isinstance(report.witness, TerminationWitness)
    witness = report.witness

    removed_nodes = {
        entry.element.node  # type: ignore[union-attr]
        for entry in witness.inventory
        if entry.form == "c" and entry.element is not None
    }
    removed_edges = {
        (entry.element.source, entry.element.target, entry.element.label)  # type: ignore[union-attr]
        for entry in witness.inventory
        if entry.form == "a" and entry.element is not None
    }
    blanket = any(entry.form == "b" for entry in witness.inventory)
    position = {
        from_display(reference): index for index, reference in enumerate(witness.certificate)
    }

    model = build_graph_model(ir, carry_unresolved_references=True)
    # §6.2's certificate is over G \ S, so it names every S-surviving vertex exactly once —
    # asserted for every polarity of S, including the blanket case below.
    assert len(witness.certificate) == len(position)
    assert sorted(position) == sorted(
        vertex for vertex in model.vertices if vertex not in removed_nodes
    )
    for edge in model.edges:
        if edge.source in removed_nodes or edge.target in removed_nodes:
            continue
        if (edge.source, edge.target, edge.label) in removed_edges:
            continue
        if blanket:
            # §2.4: S_b = E is layered on top of the element witnesses, so on a
            # blanket-carrying pass the default-profile S contains every edge, G \ S is
            # edgeless, and no edge constrains the order — the recorded blanket-path
            # certificate spelling (FIDELITY-MATRIX §5; `positive-05` pins the bytes).
            continue
        assert position[edge.source] < position[edge.target], (relative, edge)


def test_a_graph_with_two_to_the_sixty_cycles_is_decided_without_enumerating_them() -> None:
    """The §2.5 mandatory-path bound, demonstrated structurally on both polarities.

    Sixty chained diamonds closed into a ring carry :math:`2^{60}` distinct simple cycles
    through every vertex. Unwitnessed, the verdict is one residual Tarjan pass and one
    representative cycle — linear in the graph, not in its cycle count. With a form-(c)
    carrier on the ring the verdict flips to pass, and the one enumerator in the module —
    the census — aborts cleanly at its cap with the structured note instead of the list.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for index in range(60):
        joint, upper, lower, closing = (
            f"joint_{index:02d}",
            f"upper_{index:02d}",
            f"lower_{index:02d}",
            f"joint_{(index + 1) % 60:02d}",
        )
        nodes.extend([{"id": joint}, {"id": upper}, {"id": lower}])
        edges.extend(
            [
                {"from": joint, "to": upper},
                {"from": joint, "to": lower},
                {"from": upper, "to": closing},
                {"from": lower, "to": closing},
            ]
        )
    edges.append({"from": "joint_00", "to": "out"})
    nodes.append({"id": "out"})
    payload = {
        "entry": "joint_00",
        "finish": "out",
        "state": {"queue": "list"},
        "nodes": nodes,
        "edges": edges,
    }

    failing = check_termination_witness(_ir(payload))
    assert failing.result == "fail"
    assert failing.failure is not None
    location = failing.failure.location
    assert isinstance(location, P02SccLocation)
    assert len(location.nodes) == 180
    assert len(location.representative_cycle) == 120

    annotated = json.loads(json.dumps(payload))
    annotated["nodes"][0]["annotations"] = {"variant": {"key": "queue", "measure": "shrinks"}}
    passing = check_termination_witness(_ir(annotated))
    assert passing.result == "pass"
    assert isinstance(passing.witness, TerminationWitness)
    assert passing.witness.cycles is None
    assert [note.kind for note in passing.witness.notes] == ["cycle-census-capped"]


def test_an_acyclic_graph_passes_vacuously_with_an_empty_census() -> None:
    """§2.7's empty-inventory shape: no cycles, the full topological order, a zero census."""
    ir = _ir(
        {
            "entry": "one",
            "finish": "two",
            "state": {},
            "nodes": [{"id": "one"}, {"id": "two"}],
            "edges": [{"from": "one", "to": "two"}],
        }
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    assert report.witness.inventory == ()
    assert report.witness.certificate == ("START", "one", "two", "END")
    assert report.witness.notes == ()
    assert report.witness.cycles == CycleCensus(exhaustive=True, cycles=())


# ── The census (§6.3; PD-011) ────────────────────────────────────────────────────────────


def test_the_census_reproduces_the_pd_011_corpus_counts() -> None:
    """The recorded corpus maximum and the per-fixture counts PD-011 pinned B against.

    The census runs on the pass path only, so the counts are asserted through the verdict
    machinery where the fixture passes and against PD-011's table via the graph where it
    does not: the corpus maximum is ``mixed/08`` at 3, and the four positives' own
    ``cycles:`` lists (1, 1, 1, 2) are already pinned by model equality above. The three
    cycles are PD-011's, in the §0.3 canonical rotation (least id first — PD-011's own
    rendering used enumeration order, which is presentation, not the rotation rule).
    """
    census = termination_witness._capped_census(
        build_graph_model(_ir_of(MIXED_08), carry_unresolved_references=True), CENSUS_CAP
    )

    assert census is not None
    assert census.cycles == (
        ("draft_reply", "quality_gate"),
        ("draft_reply", "polish", "final_check"),
        ("compliance_gate", "polish", "final_check", "draft_reply", "quality_gate"),
    )


def test_the_census_counts_parallel_label_edges_separately() -> None:
    """T-W-SPEC §1: cycles are edge sequences, so ``negative-03``'s node-cycle counts twice.

    Both of the guard's labels re-enter ``fetch_rates``, so the one vertex-simple cycle
    stands for two edge-simple cycles — PD-011's own corrected count for this fixture.
    """
    census = termination_witness._capped_census(
        build_graph_model(
            _ir_of("termination-witness/negative-03-counter-guard-without-wired-exit.yaml"),
            carry_unresolved_references=True,
        ),
        CENSUS_CAP,
    )

    assert census is not None
    assert census.cycles == (
        ("evaluate_rates", "throttle_check", "fetch_rates"),
        ("evaluate_rates", "throttle_check", "fetch_rates"),
    )


def test_the_census_aborts_cleanly_one_past_the_cap() -> None:
    """The abort is exact: seventeen self-loops overflow B=16, sixteen do not."""

    def ring(count: int) -> GraphModel:
        names = [f"node_{index:02d}" for index in range(count)]
        payload = {
            "entry": names[0],
            "finish": names[-1],
            "state": {"queue": "list"},
            "nodes": [
                {"id": name, "annotations": {"variant": {"key": "queue", "measure": "shrinks"}}}
                for name in names
            ],
            "edges": [{"from": name, "to": name} for name in names]
            + [{"from": names[index], "to": names[index + 1]} for index in range(count - 1)],
        }
        return build_graph_model(_ir(payload), carry_unresolved_references=True)

    at_cap = termination_witness._capped_census(ring(CENSUS_CAP), CENSUS_CAP)
    assert at_cap is not None
    assert len(at_cap.cycles) == CENSUS_CAP

    over_cap = termination_witness._capped_census(ring(CENSUS_CAP + 1), CENSUS_CAP)
    assert over_cap is None


def test_the_census_blocking_machinery_prunes_and_unblocks() -> None:
    """Johnson's B-lists on a shape that exercises them: fruitless probes, then the cascade.

    Rooted at ``aa`` (the ledger-least SCC member, which is where the enumeration roots),
    the probes ``cc → dd`` and ``cc → ee`` find only the blocked path back to ``bb`` — no
    way to close to the root — so ``dd``, ``ee`` and then ``cc`` block on their successors,
    with ``cc`` pending on *both* probes. ``bb``'s own circuit unblocks the chain, and the
    cascade reaches ``cc`` twice — the second visit is the already-unblocked revisit the
    walk must skip. The complete census is what proves the pruning dropped no cycle.
    """
    ir = _ir(
        {
            "entry": "aa",
            "finish": "aa",
            "state": {},
            "nodes": [{"id": "aa"}, {"id": "bb"}, {"id": "cc"}, {"id": "dd"}, {"id": "ee"}],
            "edges": [
                {"from": "aa", "to": "bb"},
                {"from": "bb", "to": "aa"},
                {"from": "bb", "to": "cc"},
                {"from": "cc", "to": "dd"},
                {"from": "cc", "to": "ee"},
                {"from": "dd", "to": "bb"},
                {"from": "ee", "to": "bb"},
            ],
        }
    )
    census = termination_witness._capped_census(
        build_graph_model(ir, carry_unresolved_references=True), CENSUS_CAP
    )

    assert census is not None
    assert census.cycles == (("aa", "bb"), ("bb", "cc", "dd"), ("bb", "cc", "ee"))


def test_the_census_orders_shortest_first_then_by_ledger_key() -> None:
    """The repo-authored census order, pinned where the corpus speaks and stated where not.

    ``positive-04`` pins shortest-first (its 2-cycle precedes its 4-cycle, against
    lexicographic order); equal lengths tie-break on the ledger §6 comparator.
    """
    report = check_termination_witness(
        _ir_of("termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml")
    )

    assert isinstance(report.witness, TerminationWitness)
    census = report.witness.cycles
    assert census is not None
    assert [len(cycle) for cycle in census.cycles] == [2, 4]
    lengths_and_keys = [
        (len(cycle), tuple(ledger_sort_key(member) for member in cycle)) for cycle in census.cycles
    ]
    assert lengths_and_keys == sorted(lengths_and_keys)


# ── The B cap at its boundary (VAL-08 acceptance box 1) ──────────────────────────────────


def test_the_census_cap_is_the_pd_011_pin() -> None:
    """B = 16 — DEC-11's ratified default, re-pinned against this corpus by PD-011 (VAL-D4).

    The value is stated in three frozen places (T-W-SPEC §6.3, catalog §2.5, DEC-11) and
    re-verified in one ratified one (PD-011 Finding 2), so a change here is a decision
    record, never an edit. PD-011 also fixes the posture the constant implies: §2.4 Step 6
    calls the census unconditionally on every pass, so there is no flag to assert the absence
    of — the entry point takes no census parameter at all.
    """
    assert CENSUS_CAP == 16
    assert "cap" not in inspect.signature(check_termination_witness).parameters
    assert "census" not in inspect.signature(check_termination_witness).parameters


def test_the_corpus_stays_inside_the_cap_with_room_to_spare() -> None:
    """T-W-SPEC §6.3's stated constraint, re-derived here: B ≥ max c(G), DEC-16-scoped.

    "$B \\ge$ the maximum simple-cycle count across the fixture corpus, so the existing
    fixtures' expected ``cycles:`` lists remain valid" — an obligation on the *cap*, not on
    any one fixture. DEC-16 scopes it in terms: the constraint covers fixtures carrying full
    expected ``cycles:`` lists, and "corpus-conformance lints derived from PD-011 MUST
    exclude capped-census fixtures" — the overflow fixture expects the
    ``cycle-census-capped`` marker instead, and *aborting* is its authorized behaviour, so
    the exclusion is asserted in both directions: every excluded snapshot aborts, every
    other snapshot completes. The completing maximum is PD-011 Finding 2's ``mixed/08`` at
    3, reproduced independently of that record's own networkx computation.
    """
    capped = {
        # DEC-16 item 8 (TE-14, vault e6ea366): 5 strategy × 4 issue-class labels = 20 > B.
        "termination-witness/positive-06-cycle-census-capped-overflow:ir",
    }
    counts = {}
    for identity, ir in CORPUS:
        census = termination_witness._capped_census(
            build_graph_model(ir, carry_unresolved_references=True), CENSUS_CAP
        )
        if identity in capped:
            assert census is None, f"{identity} no longer overflows the cap it exists to pin"
            continue
        assert census is not None, f"{identity} aborted: B is no longer ≥ max c(G)"
        counts[identity] = len(census.cycles)

    assert max(counts.values()) == 3
    assert [identity for identity, count in counts.items() if count == 3] == [
        "mixed/08-express-path-skips-gate-writer-and-witnessed-exit:ir"
    ]


def test_the_census_boundary_is_exact_and_the_abort_is_clean() -> None:
    """The cap at B and at B+1, through the public path — and "clean" spelled out.

    A hub with N two-node petals carries exactly N simple cycles, and the hub's ``variant``
    carrier discharges every one of them, so the report passes and Step 6 runs. At B the list
    is complete and ``exhaustive: true``. At B+1 the abort is clean in four separate senses,
    each asserted: the list is **omitted entirely** rather than truncated (§6.3 — "if
    aborted, omit the list"), the structured ``cycle-census-capped`` note takes its place and
    is the *only* note, the verdict and the witness around it do not move (still a pass, same
    inventory, still a full topological certificate over the residual), and the note carries
    no ``severity`` — §2.3 makes notes "never gate-bearing", so an aborted census can never
    change what a gate does.
    """
    below, _ = _census_of(_flower(CENSUS_CAP - 1))
    assert below is not None
    assert len(below.cycles) == CENSUS_CAP - 1

    at_cap, at_cap_notes = _census_of(_flower(CENSUS_CAP))
    assert at_cap is not None
    assert at_cap.exhaustive is True
    assert len(at_cap.cycles) == CENSUS_CAP
    assert at_cap.cycles[0] == ("hub", "petal_00")
    assert at_cap_notes == ()

    over_report = check_termination_witness(_flower(CENSUS_CAP + 1))
    assert over_report.result == "pass"
    assert isinstance(over_report.witness, TerminationWitness)
    over = over_report.witness
    assert over.cycles is None
    assert over.notes == (WitnessNote(kind="cycle-census-capped"),)
    assert over.notes[0].severity is None
    assert [entry.form for entry in over.inventory] == ["c"]
    # §6.2's certificate is a topological order of G \ S, so the discharged carrier is
    # absent from it — the census aborting changed nothing about that either.
    assert set(over.certificate) == {"START", "END", "out"} | {
        f"petal_{index:02d}" for index in range(CENSUS_CAP + 1)
    }


def test_the_cap_counts_edge_simple_cycles_not_vertex_circuits() -> None:
    """§6.3's two counting caveats decide the boundary, not the circuit count.

    "Emit surviving self-loops directly as length-1 cycles, and expand each vertex-simple
    cycle per choice of parallel edge, **all counting against B**" (§6.3, carrying A7 §5).
    Eight petals whose back-edge is a two-label router are eight *vertex* circuits and
    sixteen *edge-simple* cycles — exactly B, so the list is complete and each vertex pair
    appears twice. Add one self-loop and the same eight circuits overflow: 16 + 1 = 17. Nine
    such petals (18) overflow the other way. A cap applied to vertex circuits would have
    listed all three.
    """
    at_cap, _ = _census_of(_flower(8, parallel=2))
    assert at_cap is not None
    assert len(at_cap.cycles) == CENSUS_CAP
    assert set(at_cap.cycles) == {("hub", f"petal_{index:02d}") for index in range(8)}
    assert all(at_cap.cycles.count(cycle) == 2 for cycle in at_cap.cycles)

    with_self_loop, notes = _census_of(_flower(8, parallel=2, self_loops=1))
    assert with_self_loop is None
    assert [note.kind for note in notes] == ["cycle-census-capped"]

    ninth_petal, _ = _census_of(_flower(9, parallel=2))
    assert ninth_petal is None


def test_the_abort_happens_during_enumeration_never_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§6.3's bound is only honest if the enumerator stops at circuit B+1 — so count them.

    The complete digraph on twelve vertices holds 119,481,284 simple cycles; a census that
    enumerated first and compared afterwards would never return. The blocked search is
    instrumented instead of timed, so the claim is deterministic rather than a benchmark:
    across the whole census the enumerator hands back exactly ``B + 1`` circuits — the
    smallest number that already proves overflow, since every circuit stands for at least one
    cycle — and the census aborts on it. Worst-case cost is then §6.3's $O((|N|+|E|)(B+2))$
    regardless of the true count.
    """
    names = [f"n{index:02d}" for index in range(12)]
    complete = _ir(
        {
            "entry": names[0],
            "finish": "out",
            "state": {},
            "nodes": [{"id": name} for name in names] + [{"id": "out"}],
            "edges": [
                {"from": one, "to": other} for one in names for other in names if one != other
            ]
            + [{"from": names[0], "to": "out"}],
        }
    )
    original = termination_witness._circuits_through
    calls: list[tuple[int, int]] = []

    def recording(subgraph: GraphModel, root: str, limit: int) -> list[tuple[str, ...]]:
        found = original(subgraph, root, limit)
        calls.append((limit, len(found)))
        return found

    monkeypatch.setattr(termination_witness, "_circuits_through", recording)

    census = termination_witness._capped_census(
        build_graph_model(complete, carry_unresolved_references=True), CENSUS_CAP
    )

    assert census is None
    # The caller's own sizing is the mechanism, so pin it and not only its consequence: one
    # call, asked for at most B+1 circuits, answering with exactly that many. A count-then-
    # compare implementation would satisfy the total while never returning at all.
    assert calls == [(CENSUS_CAP + 1, CENSUS_CAP + 1)]


def test_the_abort_can_also_be_taken_in_a_later_enumeration_round() -> None:
    """The outer loop is bounded too, not just the blocked search inside one round.

    The census strips one root per round, so a graph whose cycles are spread across many
    disjoint components aborts on a *later* round rather than inside the first — and the
    round budget is what bounds it there: every round picks a strongly connected group of two
    or more, so it contributes at least one cycle to the count, so at most B+2 rounds run
    whatever the graph looks like. Seventeen disjoint two-node loops is that shape at its
    boundary: sixteen of them fit, the seventeenth overflows.
    """

    def loops(count: int) -> WorkflowIR:
        carrier = {"variant": {"key": "queue", "measure": "shrinks"}}
        nodes: list[dict[str, Any]] = [{"id": "hub", "annotations": carrier}, {"id": "out"}]
        edges: list[dict[str, Any]] = [{"from": "hub", "to": "out"}]
        for index in range(count):
            left, right = f"left_{index:02d}", f"right_{index:02d}"
            nodes.extend([{"id": left, "annotations": carrier}, {"id": right}])
            edges.extend(
                [
                    {"from": "hub", "to": left},
                    {"from": left, "to": right},
                    {"from": right, "to": left},
                ]
            )
        return _ir(
            {
                "entry": "hub",
                "finish": "out",
                "state": {"queue": "list"},
                "nodes": nodes,
                "edges": edges,
            }
        )

    at_cap, _ = _census_of(loops(CENSUS_CAP))
    assert at_cap is not None
    assert len(at_cap.cycles) == CENSUS_CAP

    over_cap, notes = _census_of(loops(CENSUS_CAP + 1))
    assert over_cap is None
    assert [note.kind for note in notes] == ["cycle-census-capped"]


# ── §6.1's third row: what a strict gate promotes (acceptance boxes 2 and 3) ─────────────


def _promotion_condition_ids(report: PropertyReport) -> set[str]:
    """Every condition ID the strict path attaches to a report — the box-3 sweep unit."""
    return {promotion.property_condition for promotion in strict_promotions(report)}


def _strict_gate(report: PropertyReport) -> tuple[int, str]:
    """REPORT-FORMAT-SPEC §2.2's derivation, over one P-02 report under a P-02 strict flag.

    Quoted from the repo-authored run-report spec rather than invented here, and deliberately
    a *test-side* model: the aggregation that owns it is ``verify()`` (VAL-11). What VAL-08
    provides is the input to line 3 of it — the promotion selection — and this function is
    how that input is shown to produce the exit code §6.1's third row calls "the run fails".

    **Not a derivation VAL-11 can lift.** It implements two of §2.2's five rows over one
    report: there is no ``pass-with-notes`` row and no tool-error row, so it would mis-grade
    a non-strict run and has no opinion at all about a run that never reached a verdict.
    """
    findings = []
    if report.failure is not None:
        findings = [
            report.failure.severity,
            *(record.severity for record in report.failure.co_failures or ()),
        ]
    if any(severity in {"fatal", "error"} for severity in findings):
        return 1, "fail"
    if strict_promotions(report):
        return 1, "fail"
    return 0, "pass"


def test_a_strict_run_gates_the_blanket_only_case_to_fail_under_the_pinned_condition() -> None:
    """Acceptance box 2, on §2.7's gap shape — and the half §0.2 insists on alongside it.

    T-W-SPEC §6.1's third row: with a justified (b) present, ``--gebra-strict`` excludes
    $S_b$ from $S$ and the residual SCC the blanket alone covered is reported under **the
    same** condition ID the no-blanket row uses — ``cycle-without-termination-witness``,
    RATIFIED in §0.4 — distinguished only by the structured ``blanket_only: true``. Here that
    is what the promotion carries, and applying REPORT-FORMAT-SPEC §2.2's derivation to it
    gives exit ``1`` / ``fail``: the *gate* flips, which is the thing §6.1 says flips.

    The record does not. §0.2 names this exact note as promotable "with the report, witness,
    and note records unchanged", and DEC-11 item 6 ratified it in those words, so the report
    is asserted to be the same object before and after: still ``result: pass``, still the
    witness, still the note at ``severity: warning``. The promotion's location **is** the
    note's location — not a copy, not a rebuild — because $S_b$ never enters residual
    construction, so there is only ever one residual SCC set to describe.
    """
    report = check_termination_witness(_blanket_only_ir())
    assert isinstance(report.witness, TerminationWitness)
    (note,) = report.witness.notes

    (promotion,) = strict_promotions(report)

    assert isinstance(promotion, StrictPromotion)
    assert not isinstance(promotion, PropertyReport)
    assert promotion.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert promotion.note_kind == "scc-covered-only-by-recursion-limit"
    assert promotion.location.blanket_only is True
    assert promotion.location.nodes == ("review", "work")
    assert promotion.location.representative_cycle == ("review", "work")
    assert promotion.location.exhaustive is False
    assert note.locations is not None
    assert promotion.location is note.locations[0]

    assert _strict_gate(report) == (1, "fail")

    assert report.result == "pass"
    assert note.severity == "warning"
    assert models_equivalent(check_termination_witness(_blanket_only_ir()), report)


def test_the_promotion_reads_its_condition_id_back_through_the_registry() -> None:
    """Acceptance box 3, enforced rather than asserted: §0.4 is on the strict path.

    The identity T-W-SPEC §6.1 gives a promotion is resolved through
    :func:`emittable_condition`, so the strict path inherits the whole §0.4 discipline — an
    unregistered string, a registered-but-unratified one, and another property's name are all
    refused before a promotion can carry them. The ID it does carry is P-02's own RATIFIED
    base condition, the same one a no-blanket residual SCC fails under.

    What the promotion does **not** carry is a grade, and that is deliberate: §0.2 keeps a
    promoted record at its own ``severity: warning``, and the promoted record here is the
    note. Reading §0.4's FATAL off the condition ID and attaching it to the promotion would
    put a FATAL in a run's counts and — via REPORT-FORMAT-SPEC §2.5 — suppress snapshot
    recording under a strict flag, which is the one thing "promotion moves the gate, not the
    ladder" forbids.
    """
    (promotion,) = strict_promotions(check_termination_witness(_blanket_only_ir()))
    entry = condition(promotion.property_condition)

    assert is_emittable(promotion.property_condition)
    assert entry.tier == "ratified"
    assert property_for_condition(promotion.property_condition) == PROPERTY_SLUG
    assert promotion.property_condition in P02_CONDITIONS
    assert not hasattr(promotion, "severity")
    assert not hasattr(promotion, "claim_class")


def test_one_promotion_per_blanket_covered_scc_in_the_records_own_order() -> None:
    """§2.4 Step 5's per-SCC note granularity maps 1:1 onto per-SCC promotions.

    Two disjoint blanket-covered SCCs, so the record carries two notes in sorted-node-tuple
    order and the strict path selects two promotions in that same order — nothing re-sorts
    and nothing merges. This is the shape the FIDELITY-MATRIX §5 entry for the note's
    granularity predicted a strict promotion would map onto, now exercised rather than
    predicted.
    """
    report = check_termination_witness(_two_blanket_sccs_ir())
    assert isinstance(report.witness, TerminationWitness)
    noted = [note.locations[0] for note in report.witness.notes if note.locations]

    promotions = strict_promotions(report)

    assert [promotion.location.nodes for promotion in promotions] == [
        ("alpha_work",),
        ("beta_work",),
    ]
    assert [promotion.location for promotion in promotions] == noted
    assert {promotion.property_condition for promotion in promotions} == {
        CYCLE_WITHOUT_TERMINATION_WITNESS
    }
    assert all(promotion.location.blanket_only is True for promotion in promotions)


def test_the_fail_path_notes_are_promoted_too_and_change_no_exit_code() -> None:
    """DEC-23 puts notes on ``Failure.notes``, so §6.1's row reaches them there as well.

    A saturated counter guard in one loop plus a blanket-covered second loop: the record
    fails with the D4 condition and carries the blanket-covered SCC as a note on the failure
    (VAL-07's ruling, unchanged here). §0.2's reach is about WARNING-grade records "wherever
    they surface", and REPORT-FORMAT-SPEC §2.3's table names ``WitnessNote`` with
    ``severity: warning`` without restricting it to a passing report — so the note is
    selected here too. It changes no exit code: the report already carries a FATAL finding
    and the run is already ``1``. Leaving it unselected would understate what a strict run
    saw, which is the only thing at stake.
    """
    report = check_termination_witness(_d4_under_blanket_ir())
    assert report.failure is not None
    assert report.failure.property_condition == COUNTER_GUARD_WITHOUT_EXIT_EDGE

    (promotion,) = strict_promotions(report)

    assert promotion.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert promotion.location.nodes == ("beta_check", "beta_work")
    assert promotion.location.blanket_only is True
    assert _strict_gate(report) == (1, "fail")
    assert report.failure.notes is not None
    assert [note.kind for note in report.failure.notes] == ["scc-covered-only-by-recursion-limit"]


def test_exactly_the_blanket_only_fixture_is_promoted_across_the_corpus() -> None:
    """The other side of §6.1's row: excluding $S_b$ matters only where $S_b$ was the cover.

    Over every IR snapshot in the vendored corpus, the strict path selects nothing and the
    gate keeps the record's own verdict — including ``positive-02``, which *has* a justified
    ``recursion_limit`` but whose element witnesses already cover its loop — with exactly
    one exception, asserted rather than allowed: the DEC-16 item-7 fixture
    (``positive-05``, TE-14, vault ``e6ea366``) is the corpus's first blanket-only SCC, so
    it selects exactly one promotion (the §6.1 identity, the ``blanket_only`` location) and
    its strict gate is ``1`` while its record stays a pass. That closes §2.7's recorded gap
    and gives the strict witness-note reach its first corpus subject — the residue TE-06 and
    TE-07 both recorded as having none.
    """
    blanket_only = "termination-witness/positive-05-recursion-limit-only-scc-note:ir"
    swept = 0
    for identity, ir in CORPUS:
        report = check_termination_witness(ir)
        promotions = strict_promotions(report)
        if identity == blanket_only:
            assert report.result == "pass", identity
            (promotion,) = promotions
            assert promotion.note_kind == "scc-covered-only-by-recursion-limit"
            assert promotion.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
            assert promotion.location.nodes == ("research_specialist", "supervise")
            assert promotion.location.blanket_only is True
            assert _strict_gate(report) == (1, "fail")
        else:
            assert promotions == (), identity
            assert _strict_gate(report)[0] == (1 if report.result == "fail" else 0), identity
        swept += 1

    assert swept == 78


def test_no_condition_id_but_the_pinned_one_appears_on_the_strict_path() -> None:
    """Acceptance box 3, swept over every input either path can reach.

    §6.1: "the strict promotion reuses the same condition ID … no new condition ID is
    introduced". Swept over the whole corpus plus every hand-built shape, in both directions
    that can fail: no input produces an ID outside the pinned one, and — the direction an
    inclusion alone would not catch — across the whole sweep the pinned one *is* produced, so
    a lookup that had quietly stopped promoting would fail here rather than pass vacuously.
    The note vocabulary needs no companion sweep: the strict path creates no records at all,
    it returns pointers at records already in the report, and
    :func:`test_no_corpus_report_carries_a_string_outside_the_two` is what closes the record's
    own side.
    """
    strict_ids: set[str] = set()
    for identity, ir in [*CORPUS, *_hand_built_shapes()]:
        report = check_termination_witness(ir)
        produced = _promotion_condition_ids(report)
        assert produced <= {CYCLE_WITHOUT_TERMINATION_WITNESS}, identity
        assert produced <= P02_CONDITIONS, identity
        strict_ids |= produced

    assert strict_ids == {CYCLE_WITHOUT_TERMINATION_WITNESS}


def test_a_promotable_kind_with_no_identity_rule_is_refused_not_skipped() -> None:
    """The vocabulary is closed, so a WARNING-grade kind §6.1 does not name is an error.

    §2.3 closes the note vocabulary at five kinds and only one is WARNING-grade; widening
    that is a spec addendum, not a local patch. If one arrived without §6.1's identity rule
    being extended, silently skipping it would drop a promotion a strict gate was owed — so
    the lookup fails closed instead. Unreachable from this validator, and constructible only
    by hand, which is what makes it worth pinning.
    """
    hand_built = PropertyReport.passing(
        PROPERTY_SLUG,
        TerminationWitness(
            kind="termination",
            inventory=(),
            certificate=("START", "END"),
            notes=(WitnessNote(kind="cycle-census-capped", severity="warning"),),
        ),
    )

    with pytest.raises(ValueError, match="no condition ID"):
        strict_promotions(hand_built)


def test_another_propertys_report_is_refused_rather_than_answered_empty() -> None:
    """A foreign report is a category error, and the lookup says so instead of returning ``()``.

    REPORT-FORMAT-SPEC §2.3's reach table matches a ``WitnessNote`` on "the report's own
    property" and §0.3 scopes ``Failure.notes`` to same-property notes, so there is no
    reading under which P-02 answers for another property's promotable records. ``verify()``
    is the caller that will loop over thirteen reports, and a silent empty tuple there would
    read as "nothing to promote" rather than as the mistake it is.
    """
    foreign = check_dataflow_completeness(_ir_of(MIXED_02))

    with pytest.raises(ValueError, match="dataflow-completeness"):
        strict_promotions(foreign)


def test_a_promotion_under_another_propertys_name_is_refused() -> None:
    """The §0.4 ownership gate is on the strict path, not only on the emission path.

    §0.4 holds each name "for their properties" and forbids reuse, so a promotion attributed
    to P-02 may not be reported under a name another property owns. The identity table is a
    literal today, which is exactly why the guard is worth pinning: it is what would catch a
    future row typed against the wrong registry entry, and monkeypatching the table is the
    only way to reach it.
    """
    report = check_termination_witness(_blanket_only_ir())
    monkeypatched = {"scc-covered-only-by-recursion-limit": "read-key-never-written-on-path"}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(termination_witness, "_STRICT_IDENTITY", monkeypatched)
        with pytest.raises(ValueError, match="dataflow-completeness"):
            strict_promotions(report)


def test_a_note_riding_a_co_failure_is_promoted_too() -> None:
    """DEC-23's third carriage channel, pinned ahead of the emission path that will use it.

    §0.3 gives ``CoFailure`` its own structured ``notes`` channel and DEC-23 carries the
    closed vocabulary there unconditionally on the fail path. No P-02 code emits into it yet
    — VAL-07's pre-review flagged it forward to ``verify()``'s run-level composition, where
    DEC-23's second carriage arm (P-02 riding another property's report) becomes
    constructible — so the report here is hand-built. The point is that the strict lookup
    already reads that channel: when the emission path lands, promotions will not need to
    change with it.
    """
    location = P02SccLocation(
        kind="scc",
        nodes=("review", "work"),
        representative_cycle=("review", "work"),
        exhaustive=False,
        blanket_only=True,
    )
    hand_built = PropertyReport.failing(
        PROPERTY_SLUG,
        emit_failure(
            PROPERTY_SLUG,
            COUNTER_GUARD_WITHOUT_EXIT_EDGE,
            P02CycleLocation(
                kind="cycle",
                nodes=("guard",),
                counter_key="spins",
                guard_edge=GuardEdgeLabels(source="guard", labels=("again",)),
            ),
            co_failures=(
                CoFailure(
                    property=PROPERTY_SLUG,
                    property_condition=CYCLE_WITHOUT_TERMINATION_WITNESS,
                    location=location,
                    severity="fatal",
                    claim_class="defensible",
                    notes=(
                        WitnessNote(
                            kind="scc-covered-only-by-recursion-limit",
                            severity="warning",
                            locations=(location,),
                        ),
                    ),
                ),
            ),
        ),
    )

    (promotion,) = strict_promotions(hand_built)

    assert promotion.property_condition == CYCLE_WITHOUT_TERMINATION_WITNESS
    assert promotion.location is location


def test_a_promotable_note_anchored_off_an_scc_is_refused() -> None:
    """``blanket_only`` lives on the residual-SCC anchor, so a promotion needs one."""
    hand_built = PropertyReport.passing(
        PROPERTY_SLUG,
        TerminationWitness(
            kind="termination",
            inventory=(),
            certificate=("START", "END"),
            notes=(
                WitnessNote(
                    kind="scc-covered-only-by-recursion-limit",
                    severity="warning",
                    locations=(NodeLocation(kind="node", node="work"),),
                ),
            ),
        ),
    )

    with pytest.raises(TypeError, match="residual SCCs"):
        strict_promotions(hand_built)


def test_a_promotable_note_with_no_location_at_all_is_refused() -> None:
    """The third fail-closed arm, added at VAL-11's property-spec pre-review (finding N1).

    §0.2's reach is severity-based, so a WARNING-grade note with no ``locations`` *is*
    selected — but §6.1 reports the promoted item on its residual SCC, and this note names
    none. Answering ``()`` would silently cost a strict run the gate it was owed, which is the
    same failure the two arms above refuse; the shape most likely to arrive this way is
    T-W-SPEC §2.4's one-note-listing-every-SCC reading, recorded in FIDELITY-MATRIX §5 as a
    live alternative a future fixture could pin. VAL-11's aggregation turns the refusal into a
    §2.4 tool error rather than letting it escape only under a strict policy.
    """
    hand_built = PropertyReport.passing(
        PROPERTY_SLUG,
        TerminationWitness(
            kind="termination",
            inventory=(),
            certificate=("START", "END"),
            notes=(WitnessNote(kind="scc-covered-only-by-recursion-limit", severity="warning"),),
        ),
    )

    with pytest.raises(ValueError, match="no location"):
        strict_promotions(hand_built)


def test_blanket_only_is_true_under_a_blanket_and_absent_otherwise() -> None:
    """§6.1's ``<justified (b) present?>``, in both directions, and never as ``false``.

    §6.1 builds one payload for all three profile rows with ``blanket_only`` filled from
    "justified (b) present?" — so the default profile's note carries ``true`` (§6.1's second
    row says so in as many words) and a no-blanket failure carries the third row's ``false``.
    The ``false`` is the one spelling not put on the wire: §2.3's fail shape omits the member,
    every residual-SCC fixture omits it, and ``exclude_none`` drops ``None`` but not
    ``False`` — so emitting §6.1 literally would serialize the key onto every P-02 failure
    and lose model equality against six fixtures. DEC-11's own pin-6 example spells the
    note's location with ``blanket_only: True``, which is the spelling this asserts.
    """
    blanket = check_termination_witness(_blanket_only_ir())
    assert isinstance(blanket.witness, TerminationWitness)
    (note,) = blanket.witness.notes
    assert note.locations is not None
    assert all(location.blanket_only is True for location in note.locations)  # type: ignore[union-attr]

    unwitnessed = check_termination_witness(_ir(_loop_ir()))
    assert unwitnessed.failure is not None
    assert isinstance(unwitnessed.failure.location, P02SccLocation)
    assert unwitnessed.failure.location.blanket_only is None

    for identity, ir in [*CORPUS, *_hand_built_shapes()]:
        payload = json.dumps(to_data(check_termination_witness(ir)))
        assert '"blanket_only": false' not in payload, identity


def test_an_aborted_census_cannot_flip_a_strict_gate() -> None:
    """The census note is not gate-bearing, so overflowing B is not a strict failure.

    §2.3 makes note kinds "structured, display-adjacent, **never gate-bearing**", and only
    ``scc-covered-only-by-recursion-limit`` carries the WARNING grade §0.2 promotes — the
    strict path selects on ``severity``, not on kind, so a severity-less note is unselectable
    by any policy. A graph one cycle past the cap therefore stays exit ``0`` under a strict
    flag naming P-02, carrying ``cycle-census-capped`` and nothing else.
    """
    report = check_termination_witness(_flower(CENSUS_CAP + 1))

    assert strict_promotions(report) == ()
    assert _strict_gate(report) == (0, "pass")
    assert isinstance(report.witness, TerminationWitness)
    assert [note.kind for note in report.witness.notes] == ["cycle-census-capped"]
    assert report.witness.notes[0].severity is None


# ── Determinism and packaging ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_two_runs_produce_equal_reports(identity: str, ir: WorkflowIR) -> None:
    """The report is a pure function of the IR — no dict-order or hash-seed residue."""
    assert models_equivalent(check_termination_witness(ir), check_termination_witness(ir)), identity


def test_multiple_residual_sccs_ride_co_failures_in_sorted_tuple_order() -> None:
    """§2.3's packaging rule on the base condition alone: first K fills ``failure``.

    Two disjoint unwitnessed loops: the ``alpha`` SCC sorts before ``beta``, so it is the
    primary and ``beta`` rides ``co_failures`` with its own severity and claim class.
    """
    ir = _ir(
        {
            "entry": "beta_work",
            "finish": "out",
            "state": {},
            "nodes": [{"id": "alpha_work"}, {"id": "beta_work"}, {"id": "out"}],
            "edges": [
                {"from": "beta_work", "to": "beta_work"},
                {"from": "beta_work", "to": "alpha_work"},
                {"from": "alpha_work", "to": "alpha_work"},
                {"from": "alpha_work", "to": "out"},
            ],
        }
    )

    report = check_termination_witness(ir)

    assert report.failure is not None
    primary = report.failure.location
    assert isinstance(primary, P02SccLocation)
    assert primary.nodes == ("alpha_work",)
    assert primary.representative_cycle == ("alpha_work",)
    assert report.failure.co_failures is not None
    (second,) = report.failure.co_failures
    location = second.location
    assert isinstance(location, P02SccLocation)
    assert location.nodes == ("beta_work",)


def test_the_representative_is_the_first_back_edge_of_a_deterministic_dfs() -> None:
    """``negative-04``'s SCC holds two interleaved cycles; the reported one is pinned.

    Root is the ledger-least member, successors expand in ledger order, and the first back
    edge closes ``[flight_worker, supervisor]`` — the fixture's expected representative,
    already asserted by model equality; named here so the determinism rule is stated once
    as a rule rather than left implicit in a fixture diff.
    """
    report = check_termination_witness(
        _ir_of("termination-witness/negative-04-supervisor-delegation-scc-no-witness.yaml")
    )

    assert report.failure is not None
    location = report.failure.location
    assert isinstance(location, P02SccLocation)
    assert location.nodes == ("flight_worker", "hotel_worker", "supervisor")
    assert location.representative_cycle == ("flight_worker", "supervisor")
    assert location.exhaustive is False
    assert location.blanket_only is None


# ── The honest boundary (T-W-SPEC §7; WA-06) ─────────────────────────────────────────────


def _banned_phrases() -> tuple[str, ...]:
    """The WA-06 banned-phrase list, read from the lint's own canonical file.

    Deliberately loaded, never restated: `tools/honest-claims-phrases.txt` is the single
    enforcement surface (`tools/honest_claims_lint.py` reads the same file), so this test
    can neither drift from the ban nor put a banned spelling into the repository in order
    to test for it. T-W-SPEC §7 is the list's P-02 authority; extending it is that file's
    documented process, not this test's.
    """
    phrases = load_phrases(Path(honest_claims_lint.__file__).with_name("honest-claims-phrases.txt"))
    assert len(phrases) >= 5, "the canonical banned-phrase list went missing or empty"
    return phrases


def test_the_modules_own_language_states_witness_presence_only() -> None:
    """Acceptance box 2: no banned phrasing in the module source or any emitted string.

    The source scan covers docstrings and literals; the emitted-string scan covers every
    serialized report field over the whole corpus, so a banned phrase cannot hide in a
    remediation or note the source scan would miss. Both scans use the canonical WA-06
    list (see `_banned_phrases`), matched the way the lint matches: case-insensitive
    substring.
    """
    banned = _banned_phrases()
    source = Path(termination_witness.__file__).read_text(encoding="utf-8").lower()
    for phrase in banned:
        assert phrase not in source, phrase

    for identity, ir in CORPUS:
        rendered = json.dumps(to_data(check_termination_witness(ir))).lower()
        for phrase in banned:
            assert phrase not in rendered, (identity, phrase)


def test_the_attested_components_are_recorded_never_checked() -> None:
    """§1.1's boundary as behaviour: the measure and justification strings are echoed.

    A plainly false variant measure and a plainly inadequate justification still witness —
    Gebra records the declared content and trusts it; nothing here evaluates a claim about
    runtime. (What the strings *say* is the author's; the report only ever claims presence.)
    """
    ir = _ir(
        _loop_ir(
            nodes=[
                {
                    "id": "work",
                    "annotations": {"variant": {"key": "item", "measure": "does not decrease"}},
                },
                {"id": "review"},
                {"id": "wrap"},
            ]
        )
    )

    report = check_termination_witness(ir)

    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    source = report.witness.inventory[0].source
    assert to_data(source) == {"variant": {"key": "item", "measure": "does not decrease"}}


# ── The §2.3 read surface ────────────────────────────────────────────────────────────────


def test_the_module_reads_only_the_section_2_3_fields() -> None:
    """With a shared model in hand, the IR reads are exactly §2.3's field list.

    ``entry``/``finish`` belong to the shared build (VAL-03's Step 0) and are not touched
    when a model is supplied; what P-02 itself reads is ``edges`` (kind, from, condition,
    path_map through the recognizer), ``state``, ``nodes`` (id + ``annotations.variant``)
    and ``runtime`` (``recursion_limit``). ``annotations.pure``, effect tags and the rest
    of the surface are absences here, enforced against the models.
    """
    ir = _ir_of("termination-witness/positive-02-justified-recursion-limit-refinement-loop.yaml")
    shared = build_graph_model(ir, carry_unresolved_references=True)
    touched: set[str] = set()

    class _Recorder:
        def __init__(self, wrapped: WorkflowIR) -> None:
            self._wrapped = wrapped

        def __getattr__(self, name: str) -> Any:
            touched.add(name)
            return getattr(self._wrapped, name)

    report = check_termination_witness(_Recorder(ir), model=shared)  # type: ignore[arg-type]

    assert models_equivalent(report, check_termination_witness(ir))
    assert touched == {"edges", "nodes", "runtime", "state"}


def test_a_guard_string_is_never_evaluated_and_no_evaluation_primitive_exists() -> None:
    """P-02 reads declared ``condition`` strings through the §3 recognizer, and only so.

    The recognizer is one regular-expression pass (VAL-06's tripwires own that claim); this
    module must never gain a host-Python escape hatch around it. Every ``ast.Name`` in any
    context is collected, so an aliased ``_e = eval`` cannot slip past, and the import set
    is pinned by its own test above, which is what closes ``ast.literal_eval``.
    """
    tree = ast.parse(Path(termination_witness.__file__).read_text(encoding="utf-8"))
    named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert named.isdisjoint(
        {"eval", "exec", "compile", "literal_eval", "__import__", "getattr", "globals", "vars"}
    )


def test_a_hostile_guard_string_is_matched_not_executed() -> None:
    """An injection-shaped condition is just an opaque string to the recognizer.

    The payload is inert (L0 rejects it: brackets), and the report is the same failure the
    plain-prose guard produces — the string influenced nothing but the grammar verdict.
    """
    baseline = check_termination_witness(_ir(_loop_ir()))
    hostile = _ir(
        _loop_ir(
            edges=[
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "__import__('os').system('true')",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ]
        )
    )

    assert models_equivalent(check_termination_witness(hostile), baseline)


# ── WA-07 — never-invokes, on the import *and* the call leg ──────────────────────────────

#: VAL-06's list, unchanged: the execution substrate plus the HTTP and LLM clients whose
#: presence in the closure would mean a validator had grown a way to reach the network.
_FORBIDDEN = (
    "{'langgraph', 'langgraph_sdk', 'langchain', 'langchain_core', 'langchain_openai', "
    "'langchain_anthropic', 'langsmith', 'litellm', 'networkx', 'openai', "
    "'anthropic', 'httpx', 'requests', 'aiohttp', 'urllib3'}"
)


def _tripwire_script(probe: str = "") -> str:
    """The guarded child: patch, import, run P-02 over every corpus snapshot, report.

    ``probe`` arms the raiser; the tripwire and its negative controls share this one script
    so a control cannot drift onto a different raiser from the one the real test relies on.
    """
    return (
        "import glob, json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the termination-witness path')\n"
        "def _trip(name):\n"
        "    def _raise(*a, **k):\n"
        "        attempts.append(name); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError(name + ' reached on the termination-witness path')\n"
        "    return _raise\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip('getaddrinfo')\n"
        "socket.gethostbyname = _trip('gethostbyname')\n"
        "socket.create_connection = _trip('create_connection')\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify import check_termination_witness, strict_promotions\n"
        "seen = failed = promoted = 0\n"
        f"for path in sorted(glob.glob({str(FIXTURES_DIR)!r} + '/*/*.yaml')):\n"
        "    with open(path, encoding='utf-8') as handle:\n"
        "        document = yaml.safe_load(handle)\n"
        "    for key in ('ir', 'ir_before', 'ir_after'):\n"
        "        block = document.get(key)\n"
        "        if not block:\n"
        "            continue\n"
        "        ir = WorkflowIR.model_validate_json(json.dumps(block))\n"
        "        report = check_termination_witness(ir)\n"
        "        promoted += len(strict_promotions(report))\n"
        "        failed += report.result == 'fail'\n"
        "        seen += 1\n"
        "assert (seen, failed, promoted) == (78, 23, 1), (seen, failed, promoted)\n"
        # Since DEC-16, one corpus snapshot (positive-05) carries the blanket note, so the
        # sweep above reaches the promotable branch on vendored bytes. The hand-built
        # blanket-only IR below keeps that branch — the severity filter, the identity
        # lookup, the §0.4 resolution and the promotion itself — under the raisers even
        # if a future corpus change moved the vendored subject.
        "blanket = WorkflowIR.model_validate_json(json.dumps({\n"
        "    'ir_version': '1.0', 'entry': 'work', 'finish': 'wrap', 'state': {},\n"
        "    'runtime': {'recursion_limit': {'value': 25,\n"
        "                                    'justification': 'two supersteps per turn'}},\n"
        "    'nodes': [{'id': 'work'}, {'id': 'review'}, {'id': 'wrap'}],\n"
        "    'edges': [{'from': 'work', 'to': 'review'},\n"
        "              {'from': 'review', 'kind': 'conditional',\n"
        "               'condition': 'an opaque reviewer judgement',\n"
        "               'path_map': {'again': 'work', 'done': 'wrap'}}]}))\n"
        "gated = strict_promotions(check_termination_witness(blanket))\n"
        "assert [(p.property_condition, p.location.blanket_only) for p in gated] == [\n"
        "    ('cycle-without-termination-witness', True)], gated\n"
        f"{probe}"
        f"print([m for m in sys.modules if m.split('.')[0] in {_FORBIDDEN}] + attempts)\n"
    )


def test_running_p02_over_the_corpus_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the P-02 path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter, because another test in this session may have imported anything.
    Three claims, separately enforced: no execution-substrate or HTTP/LLM-client package
    enters the import closure; no socket is created and no name resolved, either while
    importing the module or while validating every IR snapshot in the vendored corpus; and
    a swallowed exception still fails the run, because every attempt is recorded before the
    raise and also announced on stderr. The child asserts its own counts — 67 snapshots, 22
    failing: **seven** a fixture states a P-02 failure for (the four `termination-witness/`
    negatives plus `mixed/02`, `mixed/08` and `mixed/05`'s `ir_after`, the last being the
    `unmodelled` `FM-005` record, which is why VAL-07's gloss filed the same 22 as six plus
    sixteen), and **fifteen** snapshot-fails of the quoted-comparison router idiom
    FIDELITY-MATRIX §2 ledgers, none of which carries a P-02 obligation. So a glob that
    silently stopped matching would fail the tripwire rather than pass it vacuously, and the
    sweep demonstrably exercises both result paths.
    The strict path runs inside the same guarded sweep, so §6.1's promotion lookup carries
    its own tripwire rather than inheriting one — and it is exercised on a **live** promotion
    twice over. Since the DEC-16 extension the corpus-wide count is one (``positive-05``, the
    fact :func:`test_exactly_the_blanket_only_fixture_is_promoted_across_the_corpus`
    states), so the sweep itself reaches the lookup's body; the child still also builds one
    blanket-only IR and asserts the promotion it produces, condition ID and ``blanket_only``
    included, so the branch stays covered even against a corpus edit.

    One residual, named rather than left implicit, the same one VAL-03/VAL-05/VAL-06/VAL-09
    recorded: the package leg is a post-hoc ``sys.modules`` scan, not an import blocker.
    ``tests/testing/test_hermeticity.py`` installs a real blocker on the wider path, and it
    runs this validator through the harness.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script()], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    "probe",
    (
        "socket.socket()\n",
        "socket.getaddrinfo('example.invalid', 80)\n",
        "socket.gethostbyname('example.invalid')\n",
        "socket.create_connection(('example.invalid', 80))\n",
    ),
    ids=("socket", "getaddrinfo", "gethostbyname", "create_connection"),
)
def test_the_tripwire_fires_when_the_guarded_path_is_armed(probe: str) -> None:
    """The negative control: prove the raiser is live, on the *same* script the tripwire runs.

    Without this, a patch that silently stopped installing ``_TripSocket`` would leave the
    tripwire passing for the wrong reason. Arming it after the sweep has already run
    isolates the raiser: the green run above got that far too.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script(probe)],
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the expected result here, not an error
    )

    assert completed.returncode != 0, completed.stdout
    assert "WA07-TRIP" in completed.stderr, completed.stderr


# ── The DEC-23 Q2 envelope changes, at the model layer ───────────────────────────────────


def test_failure_notes_round_trip_through_the_envelope() -> None:
    """The new §0.3 ``Failure.notes`` channel loads, serializes and compares as a model."""
    loaded = validate_report(
        {
            "property": PROPERTY_SLUG,
            "result": "fail",
            "failure": {
                "property_condition": CYCLE_WITHOUT_TERMINATION_WITNESS,
                "location": {
                    "kind": "scc",
                    "nodes": ["review", "work"],
                    "representative_cycle": ["review", "work"],
                    "exhaustive": False,
                },
                "severity": "fatal",
                "claim_class": "defensible",
                "notes": [
                    {
                        "kind": "counter-key-not-qualified",
                        "guard_edge": {"source": "review", "label": "again"},
                        "identifier": "spin_count",
                    }
                ],
            },
        }
    )

    assert isinstance(loaded.failure, Failure)
    assert loaded.failure.notes is not None
    assert loaded.failure.notes[0].kind == "counter-key-not-qualified"
    assert "notes" in to_data(loaded.failure)


def test_a_failure_without_notes_serializes_without_the_member() -> None:
    """Absence round-trips: the corpus's expected blocks omit ``notes`` and stay equal."""
    report = check_termination_witness(
        _ir_of("termination-witness/negative-01-unwitnessed-reflection-loop.yaml")
    )

    assert report.failure is not None
    assert "notes" not in to_data(report.failure)
