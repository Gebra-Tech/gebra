"""P-01 ``graph-well-formed`` against the vendored corpus (PROPERTY-CATALOG-SPEC §1).

The topology gate: the four §1 conditions over the sentinel-augmented graph, asserted as
**model equality** against the fixtures' own ``expected:`` blocks (A6 PC-6), never as string
or dict comparison. The golden harness owns that comparison corpus-wide
(:mod:`gebra.testing.harness`); as in ``test_determinism_replay.py`` this module reaches the
fixtures through PyYAML and the models directly, so it is an *independent* second path to the
same assertion rather than a caller of the harness that would pass whenever the harness agreed
with itself.

Three things this module is careful about, because each is a place P-01 could look right and
be wrong:

* **The root-cause order is the verdict's shape, not a detail.** §1.4 Step 5 fixes
  ``findings = F_iv ++ F_iii ++ F_i ++ F_ii``, and ``findings[0]`` is what fills ``failure``.
  DEC-12 added a leading key inside F_iv so the primary stays at an *actionable* edit site.
  Both are pinned here directly, not inferred from a fixture that happens to have one finding.
* **The complexity claim is demonstrated, not asserted.** §1.5 bounds P-01 at
  O(|V| log |V| + |E*|) and §1.1 makes it cycle-agnostic. Two independent tests carry that:
  one structural (no SCC, condensation or anchor-cycle primitive is ever materialized on the
  model) and one at scale (a graph carrying 2^60 simple cycles verifies with a bounded number
  of adjacency requests).
* **``mixed/04`` is the ruling's own fixture.** VAL-D1/DEC-12 disposed four open items there;
  each disposition has its own named test, and the one place the validator and the vendored
  block do not agree — the *order* of the merged co-failure list — is ledgered below and
  asserted in both directions rather than smoothed over. That difference no longer costs the
  fixture its harness obligation (REPORT-FORMAT-SPEC §3.3; ``FM-007`` closed at TE-04), which
  is precisely why the assertions here matter more than before: they are what still hold P-01
  to §1.4 Step 5.

WA-07: nothing here executes a workflow, a node, or a network call. Fixtures are read with
PyYAML's safe loader; the ``ir:`` block is validated into the frozen IR models and read as
data; ``source_snippet`` is never touched.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from gebra.ir import WorkflowIR
from gebra.verify import (
    CoFailure,
    Failure,
    NodeLocation,
    P01EdgeLocation,
    PropertyReport,
    WellFormednessWitness,
    build_graph_model,
    is_implemented,
    models_equivalent,
    run_property,
    to_data,
    validate_report,
    validate_witness,
)
from gebra.verify.graph import GraphModel
from gebra.verify.properties.graph_well_formed import (
    DEAD_END_NODE_NOT_WIRED_TO_END,
    EDGE_TARGET_UNDEFINED,
    NODE_UNREACHABLE_FROM_START,
    ORPHAN_NODE,
    PATH_MAP_TARGET_UNDEFINED,
    PROPERTY_SLUG,
    check_graph_well_formed,
)
from tests.conftest import FIXTURES_DIR

#: The seven P-01 property fixtures (§1.6's six + the DEC-16 orphan negative, TE-14), by path.
FIXTURES: tuple[str, ...] = (
    "graph-well-formed/positive-01-linear-document-pipeline.yaml",
    "graph-well-formed/positive-02-support-triage-branching.yaml",
    "graph-well-formed/positive-03-travel-parent-graph-with-booking-subgraph.yaml",
    "graph-well-formed/negative-01-unreachable-escalation-node.yaml",
    "graph-well-formed/negative-02-dead-end-review-branch.yaml",
    "graph-well-formed/negative-03-path-map-typo-dangling-target.yaml",
    "graph-well-formed/negative-04-unwired-orphan-node.yaml",
)

POSITIVES: tuple[str, ...] = FIXTURES[:3]
NEGATIVES: tuple[str, ...] = FIXTURES[3:]

MIXED_04 = "mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml"
MIXED_10 = "mixed/10-all-properties-pass-healthy-research-pipeline.yaml"


# ── Fixture loading (§0.3's rule, spelled out — the second, independent path) ────────────


def _load(relative: str) -> dict[str, Any]:
    document = yaml.safe_load((FIXTURES_DIR / relative).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _ir_of(relative: str) -> WorkflowIR:
    """The fixture's IR block, validated into the frozen models (JSON mode, §2.5 note 4)."""
    return WorkflowIR.model_validate_json(json.dumps(_load(relative)["ir"]))


def _expected_report(relative: str) -> PropertyReport:
    """The fixture's ``expected:`` block as P-01's report — §0.3's loading rule verbatim."""
    return validate_report({"property": PROPERTY_SLUG, **_load(relative)["expected"]})


# ── Building IRs by hand, for the §1.7 edge cases the corpus does not carry ──────────────


def _ir(
    *,
    entry: str | list[str],
    finish: str | list[str],
    nodes: list[str],
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowIR:
    """A topology-only IR — P-01 reads nothing else (§1.3 "Not read")."""
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": entry,
                "finish": finish,
                "nodes": [{"id": node_id} for node_id in nodes],
                "edges": edges or [],
            }
        )
    )


def _failure(report: PropertyReport) -> Failure:
    assert report.result == "fail"
    assert report.failure is not None
    return report.failure


def _witness(report: PropertyReport) -> WellFormednessWitness:
    assert report.result == "pass", to_data(report)
    assert isinstance(report.witness, WellFormednessWitness)
    return report.witness


def _records(report: PropertyReport) -> list[tuple[str, Any]]:
    """Every finding of a failing report as ``(condition ID, location)``, primary first."""
    failure = _failure(report)
    records: list[tuple[str, Any]] = [(failure.property_condition, failure.location)]
    records.extend((co.property_condition, co.location) for co in failure.co_failures or ())
    return records


def _conditions(report: PropertyReport) -> list[str]:
    return [condition for condition, _ in _records(report)]


# ── Acceptance box 1: every graph-well-formed fixture, as model equality ─────────────────


@pytest.mark.parametrize("relative", FIXTURES)
def test_the_validator_reproduces_the_fixture_report(relative: str) -> None:
    """The PC-6 identity, on the raw ``expected:`` block with nothing normalized either side.

    Comparison is between :class:`PropertyReport` instances — not dicts, not strings — which
    is what §0.3 means by "a fixture can therefore never drift from the result type".
    """
    produced = check_graph_well_formed(_ir_of(relative))
    expected = _expected_report(relative)
    assert produced == expected, f"{to_data(produced)} != {to_data(expected)}"


@pytest.mark.parametrize("relative", FIXTURES)
def test_the_report_is_spec_shaped_and_round_trips(relative: str) -> None:
    """PC-4 serialization → §0.3 validation → the same model, for every fixture."""
    produced = check_graph_well_formed(_ir_of(relative))
    assert validate_report(to_data(produced)) == produced


@pytest.mark.parametrize("relative", FIXTURES)
def test_no_p01_report_carries_a_remediation(relative: str) -> None:
    """§1.4 renders none, and neither does any fixture.

    P-01 has no Appendix B warning grammar — that is P-08's — so a remediation string here
    would be invented prose that no fixture could pin, and would break model equality on
    every negative. Asserted rather than left to review, because ``remediation`` is optional
    and an absent one is invisible in a passing comparison.
    """
    produced = check_graph_well_formed(_ir_of(relative))
    if produced.result == "fail":
        assert _failure(produced).remediation is None
    assert _load(relative)["expected"].get("failure", {}).get("remediation") is None


@pytest.mark.parametrize("relative", POSITIVES)
def test_the_positives_carry_the_five_key_witness(relative: str) -> None:
    """DEC-11 pin 1: the 5-key form, with (iii) and (iv) evidenced as empty by construction."""
    witness = _witness(check_graph_well_formed(_ir_of(relative)))
    assert witness.kind == "well-formedness"
    assert witness.orphan_nodes == ()
    assert witness.unresolved_targets == ()
    declared = {node["id"] for node in _load(relative)["ir"]["nodes"]}
    assert set(witness.reachable_from_start) == declared
    assert list(witness.reachable_from_start) == sorted(
        witness.reachable_from_start, key=lambda value: value.encode("utf-16-be")
    )


def test_the_grades_are_read_off_the_registry_never_restated() -> None:
    """§1.3: every P-01 finding is ``severity: fatal``, ``claim_class: defensible``.

    The values are the §0.4 registry's, reached through ``emit_failure``/``emit_co_failure``,
    so this asserts the wiring rather than a literal the module could have spelled itself.
    """
    for relative in (*NEGATIVES, MIXED_04):
        failure = _failure(check_graph_well_formed(_ir_of(relative)))
        assert (failure.severity, failure.claim_class) == ("fatal", "defensible")
        for co in failure.co_failures or ():
            assert (co.property, co.severity, co.claim_class) == (
                PROPERTY_SLUG,
                "fatal",
                "defensible",
            )


def test_the_registry_dispatches_p01_now_that_it_has_landed() -> None:
    """Importing the module registers it; ``run_property`` answers with a report, not a marker."""
    assert is_implemented(PROPERTY_SLUG)
    answer = run_property(PROPERTY_SLUG, _ir_of(FIXTURES[0]))
    assert isinstance(answer, PropertyReport)
    assert answer.result == "pass"


def test_the_mixed_10_witness_block_is_reproduced_exactly() -> None:
    """``mixed/10``'s P-01 sub-witness — the over-flagging guard (a cycle that is fine).

    The fixture carries a retry cycle, a parallel fan-out and a conditional router, all
    healthy. P-01 is cycle-agnostic (§1.1), so the cycle must not move its verdict at all.
    """
    entry = _load(MIXED_10)["expected"]["witness"]["properties"][PROPERTY_SLUG]
    produced = check_graph_well_formed(_ir_of(MIXED_10))
    assert produced.result == "pass"
    assert produced.witness == validate_witness(entry)


# ── Acceptance box 3: mixed/04 and the VAL-D1 (PD-007 / DEC-12) ruling ───────────────────

#: The one place P-01's report and ``mixed/04``'s vendored ``expected:`` block disagree.
#:
#: **What differs:** the *order* of the two same-property co-failures, and nothing else. The
#: primary, all three records' condition IDs, locations, severities and claim classes are
#: identical on both sides (:func:`test_mixed_04_differs_from_the_fixture_only_in_list_order`
#: proves that field by field).
#:
#: **Why.** §1.4 Step 5 fixes P-01's own order as ``F_iv ++ F_iii ++ F_i ++ F_ii``, so
#: ``edge-target-undefined`` (condition (iv)) precedes ``node-unreachable-from-start``
#: (condition (i)). ``mixed/04``'s block is a **merged cross-property** list — it carries a
#: ``dataflow-completeness`` record between the two, which ``emit_co_failure``'s ownership
#: check forbids any P-01 validator from emitting — and DEC-12 ratified the new record as
#: *appended* to that merged list. Whose ordering rule governs a merged list is
#: REPORT-FORMAT-SPEC's question under the §0.3 scope boundary, not §1.4's.
#:
#: **It is answered, and this file is the compensating pin.** REPORT-FORMAT-SPEC §3.3 rules
#: that above one property "order carries no meaning", so at TE-04 the harness's `PR-1`
#: projection stopped comparing a *merged* source list positionally and started comparing the
#: restricted records as a multiset. ``FM-007`` closed with it and is now in
#: ``docs/governance/FIDELITY-MATRIX.md`` **§4**, which points a reader back here — because
#: the assertions below are what still hold P-01 to §1.4 Step 5 exactly, and what still
#: witness that the two orders differ. Nothing about the validator changed, and nothing about
#: the corpus did: it is never edited in this repository (WA-04/WA-11). If the two orders ever
#: *agree*, the test below goes red on purpose and this ledger is re-read rather than deleted.
LEDGERED_ORDERING_DEVIATION = (
    "co_failures list order, mixed/04 only — FIDELITY-MATRIX FM-007, closed at TE-04 §4"
)

#: The three findings PD-007/DEC-12 disposed for ``mixed/04``, in §1.4 Step 5 order.
MIXED_04_FINDINGS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        PATH_MAP_TARGET_UNDEFINED,
        {
            "kind": "edge",
            "source": "triage",
            "label": "legal",
            "undefined_target": "legal_hold_review",
        },
    ),
    (
        EDGE_TARGET_UNDEFINED,
        {"kind": "edge", "source": "legal_hold_review", "undefined_target": "legal_hold_review"},
    ),
    (NODE_UNREACHABLE_FROM_START, {"kind": "node", "node": "compliance_log"}),
)


def test_mixed_04_emits_exactly_the_findings_the_ruling_names() -> None:
    """DEC-12's disposition, record by record — nothing more, nothing fewer, nothing merged.

    Three findings for one typo: the dangling ``path_map`` label (the root cause), the edge
    whose ``from`` names the node that was renamed away, and the reader stranded behind it.
    "Emission is complete — no collapse" (DEC-12): each unresolved reference is its own
    finding, per §0.3's findings-are-never-dropped rule.
    """
    produced = check_graph_well_formed(_ir_of(MIXED_04))
    assert [(condition, to_data(location)) for condition, location in _records(produced)] == list(
        MIXED_04_FINDINGS
    )


def test_mixed_04_keeps_the_ratified_primary() -> None:
    """The DEC-12 leading key's whole purpose: an actionable edit site fills ``failure``.

    Without it the ``legal_hold_review`` finding — anchored at a node that does not exist —
    could take the primary from the ``triage`` path-map finding, which is the line a person
    actually fixes. PD-007 finding 5 records that this was verified by trace before
    ratification; it is verified by execution here.
    """
    failure = _failure(check_graph_well_formed(_ir_of(MIXED_04)))
    assert failure.property_condition == PATH_MAP_TARGET_UNDEFINED
    assert isinstance(failure.location, P01EdgeLocation)
    assert (failure.location.source, failure.location.label) == ("triage", "legal")


def test_the_unresolved_source_leaks_no_phantom_node_into_the_graph() -> None:
    """PD-007 finding 5, the defect class DEC-12 closed — asserted on the graph, not the report.

    The frozen pseudocode used to reach ``G.add_edge(e.from, e.to)`` on an edge whose ``from``
    named no node, and ``networkx`` auto-vivifies edge endpoints. DEC-12 replaced that with
    "emit, insert nothing". So ``legal_hold_review`` is in no vertex list, and
    ``compliance_log`` — its only successor — keeps no incoming edge, which is exactly why it
    earns condition (i) by rule rather than by side effect.
    """
    model = build_graph_model(_ir_of(MIXED_04))
    assert "legal_hold_review" not in model.vertex_set
    assert model.carried == frozenset()
    assert model.in_edges("compliance_log") == ()


def test_a_passing_witness_can_never_name_a_node_that_does_not_exist() -> None:
    """The other half of PD-007 finding 5: the ``terminal_nodes`` leak the ruling closed.

    This is the exact shape the finding describes — an unresolvable ``from`` on a router whose
    ``path_map`` names the blessed ``"END"`` literal. Under the pre-DEC-12 pseudocode nothing
    checked that ``from``, ``add_edge`` auto-vivified it, and the edge it inserted made the
    phantom a predecessor of ``__end__``: a **passing** report whose ``terminal_nodes`` carried
    an id outside $V$, with no finding anywhere to explain it. Now the reference emits and
    inserts nothing, so the report fails and the phantom exists in neither the graph nor the
    witness.
    """
    ir = _ir(
        entry="a",
        finish="a",
        nodes=["a"],
        edges=[
            {"from": "ghost", "kind": "conditional", "condition": "…", "path_map": {"stop": "END"}}
        ],
    )
    assert _conditions(check_graph_well_formed(ir)) == [EDGE_TARGET_UNDEFINED]
    model = build_graph_model(ir)
    assert "ghost" not in model.vertex_set
    assert "ghost" not in model.predecessors("__end__")


def test_p01_emits_no_record_another_property_owns() -> None:
    """``mixed/04``'s P-04 co-failure is the *fixture's*, never P-01's output.

    §0.3 packages same-property findings in ``co_failures``, and ``emit_co_failure``'s
    ownership check refuses a condition ID the §0.4 registry holds for another property — so
    the cross-property record in the vendored block is a run-level composition, which is the
    harness's PR-1 projection rule, not something a lone validator produces.
    """
    failure = _failure(check_graph_well_formed(_ir_of(MIXED_04)))
    assert all(co.property == PROPERTY_SLUG for co in failure.co_failures or ())
    assert failure.advisories is None
    assert all(co.subsumed_by is None for co in failure.co_failures or ())


def test_mixed_04_differs_from_the_fixture_only_in_list_order() -> None:
    """The ledgered deviation, asserted in **both** directions (see the constant above).

    Forward: every P-01 record the fixture states is one the validator states, and vice
    versa — as a multiset, field for field. Backward: the two orders really do differ today,
    so if a corpus revision or a spec amendment lands, this test goes red and is updated
    rather than passing in silence. The vendored order is pinned literally for the same
    reason.
    """
    document = _load(MIXED_04)
    vendored = document["expected"]["failure"]["co_failures"]
    assert [record["property_condition"] for record in vendored] == [
        NODE_UNREACHABLE_FROM_START,
        "read-key-never-written-on-path",
        EDGE_TARGET_UNDEFINED,
    ], "the vendored merged order changed — re-check FM-007 (§4) before touching this test"

    projection = dict(document["expected"]["failure"])
    projection["co_failures"] = [
        record for record in vendored if record["property"] == PROPERTY_SLUG
    ]
    expected = validate_report(
        {"property": PROPERTY_SLUG, **document["expected"], "failure": projection}
    )
    produced = check_graph_well_formed(_ir_of(MIXED_04))

    assert not models_equivalent(produced, expected), LEDGERED_ORDERING_DEVIATION
    assert _failure(produced).property_condition == _failure(expected).property_condition
    assert _failure(produced).location == _failure(expected).location
    assert _same_records(_failure(produced).co_failures, _failure(expected).co_failures)


def _same_records(
    produced: tuple[CoFailure, ...] | None, expected: tuple[CoFailure, ...] | None
) -> bool:
    """Whether two co-failure lists hold the same records, order aside."""
    return sorted(to_json_lines(produced)) == sorted(to_json_lines(expected))


def to_json_lines(records: tuple[CoFailure, ...] | None) -> list[str]:
    return [json.dumps(to_data(record), sort_keys=True) for record in records or ()]


# ── Acceptance box 2: the complexity shape — no cycle enumeration, ever ──────────────────

#: Every memoized derivation on :class:`~gebra.verify.graph.GraphModel` that costs a
#: components pass or a cycle walk. A ``cached_property`` writes its value into the instance
#: ``__dict__`` on first access, so the *absence* of these names after a run is direct
#: evidence that P-01 never asked for any of them.
CYCLE_MACHINERY: tuple[str, ...] = (
    "components",
    "condensation",
    "condensation_order",
    "worklist_order",
    "_anchor_cache",
    "_component_subgraph_cache",
)


@pytest.mark.parametrize("relative", (*FIXTURES, MIXED_04, MIXED_10))
def test_no_scc_condensation_or_cycle_primitive_is_ever_materialized(relative: str) -> None:
    """§1.1/§1.5: "P-01 never orders the graph, so no condensation or topological sort".

    Run over every P-01 fixture including ``mixed/10``, which *contains* a retry cycle — so
    this is not passing because the inputs are acyclic.
    """
    model = build_graph_model(_ir_of(relative))
    check_graph_well_formed(_ir_of(relative), model=model)
    assert [name for name in CYCLE_MACHINERY if name in vars(model)] == []


def test_the_no_cycle_machinery_check_is_not_vacuous() -> None:
    """The negative control: asking for the machinery does populate what the test looks at."""
    model = build_graph_model(_ir_of(MIXED_10))
    assert len(model.components) > 0
    assert model.condensation_order
    assert model.worklist_order
    assert [name for name in CYCLE_MACHINERY if name in vars(model)] != []


def _diamond_chain(width: int) -> WorkflowIR:
    """A cycle of ``width`` diamonds: 2 ** ``width`` distinct simple cycles, 3·width+1 nodes.

    ``v0 → {a_i, b_i} → v_{i+1}`` for each ``i``, closed by ``v_width → v0``. Every cycle
    through the back edge picks one of two nodes at each of ``width`` steps, so the simple
    cycles number exactly ``2 ** width`` — the standard witness that a graph's simple-cycle
    count is not polynomial in its size, and why T-W-SPEC and §1.5 both route around
    enumeration rather than capping it.
    """
    stops = [f"v{index:03d}" for index in range(width + 1)]
    branches = [(f"a{index:03d}", f"b{index:03d}") for index in range(width)]
    nodes = [*stops, *(node for pair in branches for node in pair)]
    edges: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(branches):
        for branch in (left, right):
            edges.append({"from": stops[index], "to": branch})
            edges.append({"from": branch, "to": stops[index + 1]})
    edges.append({"from": stops[width], "to": stops[0]})
    return _ir(entry=stops[0], finish=stops[width], nodes=nodes, edges=edges)


def test_a_graph_with_2_to_the_60_simple_cycles_verifies_in_linear_time() -> None:
    """The scale half of the claim: 1.15e18 simple cycles over 181 nodes, and it returns.

    An implementation that enumerated cycles could not return at all, so **that it returns is
    the result** — the assertions below are about the answer, not the clock. The wall-clock
    bound is a backstop with a ~1000× margin (the run takes single-digit milliseconds), there
    only so that a regression to enumeration fails as a red test rather than as a hung CI job.
    It is not a performance budget and must not be tightened into one; what pins the *shape*
    of the work is the instrumented test below.
    """
    ir = _diamond_chain(60)
    started = time.perf_counter()
    report = check_graph_well_formed(ir)
    elapsed = time.perf_counter() - started
    assert report.result == "pass"
    assert len(_witness(report).reachable_from_start) == 181
    assert elapsed < 10.0, f"{elapsed:.3f}s — P-01 is O(|V| log |V| + |E*|) per §1.5"


def test_adjacency_requests_scale_with_the_graph_not_with_its_cycle_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The instrumented half: every adjacency read is counted, for two sizes 2**52 apart.

    §1.5 justifies the bound as "one graph build, one BFS closure, two degree scans". Each of
    those touches a vertex's adjacency a bounded number of times, so the total request count
    is linear in |V| and utterly independent of how many cycles the graph carries — which the
    ratio between the two runs shows: the cycle counts differ by a factor of 2**52, the
    request counts by the ratio of the vertex counts.
    """
    counts: dict[str, int] = {}

    def _instrument(name: str) -> None:
        original = getattr(GraphModel, name)

        def counted(self: GraphModel, vertex: str, **kwargs: Any) -> Any:
            counts[name] = counts.get(name, 0) + 1
            return original(self, vertex, **kwargs)

        monkeypatch.setattr(GraphModel, name, counted)

    for name in ("successors", "out_edges", "in_edges"):
        _instrument(name)

    measured: dict[int, int] = {}
    for width in (8, 60):
        counts.clear()
        model = build_graph_model(_diamond_chain(width))
        check_graph_well_formed(_diamond_chain(width), model=model)
        measured[len(model.vertices)] = sum(counts.values())

    small, large = sorted(measured)
    assert measured[large] <= 8 * large, "adjacency reads must stay a small multiple of |V|"
    ratio = measured[large] / measured[small]
    assert 0.5 * (large / small) < ratio < 2 * (large / small), measured


# ── §1.4 Step 5: the root-cause ordering, pinned directly ───────────────────────────────


def test_the_blocks_are_emitted_in_root_cause_order_iv_iii_i_ii() -> None:
    """§1.4 Step 5, on one IR that violates all four conditions at once.

    ``router`` dangles a label (iv); ``lonely`` participates in nothing (iii); ``stranded``
    is wired onward but nothing routes to it (i); ``sink`` is reachable, participates, and
    goes nowhere (ii). No corpus fixture mixes all four — each is deliberately isolated — so
    the block order is asserted here or nowhere.

    ``lonely`` earns three findings, one per block it falls in, and they are **not** merged:
    §0.3's rule is that findings are never dropped, and each condition is a separate statement
    about the same node. The blocks stay contiguous and in order; within each, ids are sorted.
    """
    report = check_graph_well_formed(
        _ir(
            entry="router",
            finish="done",
            nodes=["router", "done", "lonely", "stranded", "sink", "onward"],
            edges=[
                {
                    "from": "router",
                    "kind": "conditional",
                    "condition": "…",
                    "path_map": {"ok": "done", "typo": "nosuchnode", "bad": "sink"},
                },
                {"from": "stranded", "to": "onward"},
                {"from": "onward", "to": "done"},
            ],
        )
    )
    assert [
        (condition, getattr(location, "node", None)) for condition, location in _records(report)
    ] == [
        (PATH_MAP_TARGET_UNDEFINED, None),  # F_iv — the root cause, and the primary
        (ORPHAN_NODE, "lonely"),  # F_iii
        (NODE_UNREACHABLE_FROM_START, "lonely"),  # F_i, id-sorted
        (NODE_UNREACHABLE_FROM_START, "onward"),
        (NODE_UNREACHABLE_FROM_START, "stranded"),
        (DEAD_END_NODE_NOT_WIRED_TO_END, "lonely"),  # F_ii, id-sorted
        (DEAD_END_NODE_NOT_WIRED_TO_END, "sink"),
    ]


def test_within_a_block_findings_follow_the_ledger_comparator() -> None:
    """Ledger §6 orders ids as **UTF-16 code units**, not Python's default code points.

    The two disagree for ids mixing non-BMP characters with U+E000..U+FFFF, and the order is
    what fixes which finding is the primary — so it is pinned against the difference itself,
    on the condition-(iii) block, where every finding is an id.
    """
    ids = ("\U0001f600", "�", "a")
    assert sorted(ids) != sorted(ids, key=lambda value: value.encode("utf-16-be"))
    report = check_graph_well_formed(_ir(entry="a", finish="a", nodes=["a", *ids[:2]], edges=[]))
    orphans = [
        location.node
        for condition, location in _records(report)
        if condition == ORPHAN_NODE and isinstance(location, NodeLocation)
    ]
    assert orphans == sorted(ids[:2], key=lambda value: value.encode("utf-16-be"))
    assert orphans != sorted(ids[:2])


def test_the_f_iv_leading_key_puts_resolvable_anchors_first() -> None:
    """DEC-12's ordering key, isolated from every other block.

    Both findings are condition (iv); the only thing separating them is whether their
    ``location.source`` is a node a person can open. ``aaa`` sorts before ``zzz`` under the
    plain comparator, so a run without the leading key would put the unresolved-source
    finding first — which is precisely the flip PD-007 verified by trace.
    """
    report = check_graph_well_formed(
        _ir(
            entry="zzz",
            finish="zzz",
            nodes=["zzz"],
            edges=[{"from": "aaa", "to": "zzz"}, {"from": "zzz", "to": "nope"}],
        )
    )
    sources = [location.source for _, location in _records(report)]
    assert sources[:2] == ["zzz", "aaa"]


def test_the_f_iv_key_is_computed_on_the_graph_side_spelling_of_the_start_sentinel() -> None:
    """The sort runs on ``__start__``; only the emitted location is projected to ``"START"``.

    §1.4 Step 1 literally builds ``P01EdgeLocation(kind="edge", source="__start__", …)`` and
    Step 5's leading key tests ``location.source ∈ V ∪ {"__start__"}`` — one spelling, used
    for both. Projecting *before* the sort would invert the key for the most actionable anchor
    there is: ``"START"`` is a member of neither ``V`` nor ``{"__start__"}``, so the entry
    finding would test **false**, drop into the unresolved-source group and sort last. The two
    spellings are not interchangeable in the within-group comparator either — they differ at
    the first code unit — so this is one decision, not two.

    No corpus fixture has an unresolved ``entry`` id alongside another condition-(iv) finding,
    so this is pinned here or nowhere.
    """
    report = check_graph_well_formed(
        _ir(
            entry="ghost",
            finish="intake",
            nodes=["intake"],
            edges=[{"from": "intake", "to": "nope"}],
        )
    )
    anchors = [
        (condition, location.source)
        for condition, location in _records(report)
        if isinstance(location, P01EdgeLocation)
    ]
    assert anchors == [
        (EDGE_TARGET_UNDEFINED, "START"),
        (EDGE_TARGET_UNDEFINED, "intake"),
    ]
    # The two spellings the sort could have used, and why the choice is observable at all.
    assert "START" not in {*build_graph_model(_ir_of(FIXTURES[0])).node_ids, "__start__"}
    assert "START".encode("utf-16-be") != "__start__".encode("utf-16-be")


def test_every_finding_survives_packaging_none_is_dropped_or_collapsed() -> None:
    """§0.3: findings are never dropped, never re-packaged as self-referential advisories."""
    report = check_graph_well_formed(
        _ir(
            entry="a",
            finish="a",
            nodes=["a"],
            edges=[{"from": "a", "to": "x"}, {"from": "a", "to": "y"}, {"from": "a", "to": "z"}],
        )
    )
    failure = _failure(report)
    assert [condition for condition, _ in _records(report)] == [EDGE_TARGET_UNDEFINED] * 3
    assert failure.advisories is None


# ── §1.7 "Edge cases enumerated", one named test each ────────────────────────────────────


def test_an_entry_naming_no_node_is_a_condition_iv_finding_never_a_vacuous_pass() -> None:
    """§1.7 edge case 1, with DEC-12 scope (a). The anchor is the START sentinel.

    §0.3's sentinel-spelling rule projects the graph-side ``__start__`` to the report-side
    ``"START"``; ``NodeId`` refuses the reserved spelling outright, so forgetting the
    projection would be a validation error rather than a quietly non-conforming report.
    """
    report = check_graph_well_formed(_ir(entry="ghost", finish="a", nodes=["a"], edges=[]))
    condition, location = _records(report)[0]
    assert condition == EDGE_TARGET_UNDEFINED
    assert isinstance(location, P01EdgeLocation)
    assert (location.source, location.undefined_target, location.target) == ("START", "ghost", None)


def test_an_empty_node_set_never_reaches_p01_at_all() -> None:
    """§1.7 edge case 1, other half — answered upstream, which is why it cannot pass silently.

    The IR models require at least one node, so an empty node set is an IR-validation error:
    §0.2 makes that exit ``2`` ("extraction or IR validation failed before any property ran …
    never a verification result"), not a P-01 verdict. Asserted here because §1.7 lists the
    case, and the honest answer is *which layer* refuses it — a P-01 test that fabricated a
    finding for it would be documenting behaviour the stack does not have.
    """
    with pytest.raises(ValidationError):
        _ir(entry="a", finish="a", nodes=[], edges=[])


def test_a_finish_naming_no_node_is_a_condition_iv_finding_anchored_at_the_id() -> None:
    """DEC-12 scope (b): the symmetric ``finish`` branch that replaced ``finish_ids ∩ V``.

    Before DEC-12 the frozen pseudocode intersected ``finish`` with $V$ and emitted nothing —
    an unresolved finish id vanished. The anchor is the id itself, not ``__end__``: §1.4's
    symmetric check is written ``source=fid, undefined_target=fid``.
    """
    report = check_graph_well_formed(_ir(entry="a", finish=["a", "ghost"], nodes=["a"], edges=[]))
    condition, location = _records(report)[0]
    assert condition == EDGE_TARGET_UNDEFINED
    assert isinstance(location, P01EdgeLocation)
    assert (location.source, location.undefined_target) == ("ghost", "ghost")


def test_a_normal_edge_target_naming_no_node_is_a_condition_iv_finding() -> None:
    """DEC-12 scope (d) — the case the pre-DEC-12 pseudocode already had."""
    report = check_graph_well_formed(
        _ir(entry="a", finish="a", nodes=["a"], edges=[{"from": "a", "to": "ghost"}])
    )
    condition, location = _records(report)[0]
    assert condition == EDGE_TARGET_UNDEFINED
    assert isinstance(location, P01EdgeLocation)
    assert (location.source, location.undefined_target) == ("a", "ghost")


def test_a_conditional_edge_with_an_unresolved_source_still_has_its_labels_checked() -> None:
    """DEC-12's diagnostic-completeness clause, and its limit.

    "For a ``conditional`` edge the ``path_map`` labels are still resolved and checked …
    but no expansion edges are inserted." A ``normal``/``send`` edge is the deliberate
    asymmetry: §1.4 Step 1 ``continue``s past an unresolved ``from`` before it ever looks at
    the ``to``, so exactly one finding comes back from that shape (asserted alongside).

    Both findings anchor at the same unresolvable ``ghost``, so the leading key groups them
    together and the within-group comparator decides: the edge-source finding carries no
    label, and ``"" < "typo"``.
    """
    ir = _ir(
        entry="a",
        finish="a",
        nodes=["a"],
        edges=[
            {
                "from": "ghost",
                "kind": "conditional",
                "condition": "…",
                "path_map": {"here": "a", "typo": "nosuch"},
            }
        ],
    )
    report = check_graph_well_formed(ir)
    assert _conditions(report) == [EDGE_TARGET_UNDEFINED, PATH_MAP_TARGET_UNDEFINED]
    assert [location.label for _, location in _records(report)] == [None, "typo"]
    # "…but no expansion edges are inserted": not even for the label that *does* resolve.
    # The entry wiring into ``a`` is (m1)'s and stays; what must be absent is any edge the
    # ghost router contributed.
    assert [edge for edge in build_graph_model(ir).in_edges("a") if edge.origin == "edges"] == []

    normal = check_graph_well_formed(
        _ir(entry="a", finish="a", nodes=["a"], edges=[{"from": "ghost", "to": "alsoghost"}])
    )
    assert _conditions(normal) == [EDGE_TARGET_UNDEFINED]


def test_the_single_node_splitter_passes_which_is_what_makes_it_reading_a() -> None:
    """§1.3's splitter: ``entry == finish == n``, ``edges: []``.

    Reading A passes it — sentinel wiring is edge participation. Reading B would have failed
    ``n`` as ``orphan-node``, and DEC-11 rejected Reading B by name. The two readings are
    distinguishable on exactly this IR, which is why the ruling names it.
    """
    witness = _witness(check_graph_well_formed(_ir(entry="n", finish="n", nodes=["n"])))
    assert (witness.reachable_from_start, witness.terminal_nodes) == (("n",), ("n",))


def test_an_entry_only_node_and_a_finish_only_node_are_both_wired() -> None:
    """Reading A on each sentinel separately — ``negative-03``'s ``send_confirmation`` case.

    That fixture's own note says it: "being listed in finish means it participates in the
    implicit edge to END". Neither membership alone may produce an orphan finding.
    """
    report = check_graph_well_formed(
        _ir(entry=["a", "b"], finish=["a", "b"], nodes=["a", "b"], edges=[])
    )
    assert report.result == "pass"


def test_a_node_wired_to_nothing_at_all_is_the_orphan_case() -> None:
    """Condition (iii) has no negative fixture yet (§1.6) — the reading is pinned here.

    ``lonely`` is in no edge, no ``entry`` and no ``finish``. A node wired to nothing is
    necessarily also unreachable *and* a sink, so it earns all three of conditions (iii), (i)
    and (ii) — emitted separately, because §0.3 drops no finding, and ordered by Step 5 so
    that (iii), the condition that actually describes the defect, is the primary.
    """
    report = check_graph_well_formed(_ir(entry="a", finish="a", nodes=["a", "lonely"], edges=[]))
    assert _conditions(report) == [
        ORPHAN_NODE,
        NODE_UNREACHABLE_FROM_START,
        DEAD_END_NODE_NOT_WIRED_TO_END,
    ]
    assert _failure(report).location == NodeLocation(kind="node", node="lonely")


def test_a_self_loop_only_node_participates_in_an_edge_and_is_not_an_orphan() -> None:
    """§1.7: "self-loop-only non-entry node (participates in an edge — not an orphan; fails (i))".

    The trap this closes is counting a self-loop as no participation. It is also the smallest
    cycle there is, and P-01 stays cycle-agnostic about it — the only finding is (i).
    """
    report = check_graph_well_formed(
        _ir(entry="a", finish="a", nodes=["a", "loop"], edges=[{"from": "loop", "to": "loop"}])
    )
    assert _conditions(report) == [NODE_UNREACHABLE_FROM_START]


def test_an_internally_wired_unreached_component_is_all_i_and_no_iii() -> None:
    """§1.7: the ``negative-01`` isolation, generalized to a whole component.

    Every member is unreachable; not one is an orphan, because they participate in edges with
    each other. Conditions (i) and (iii) are genuinely independent, which is the reason
    ``negative-01`` exists.
    """
    report = check_graph_well_formed(
        _ir(
            entry="a",
            finish="a",
            nodes=["a", "x", "y", "z"],
            edges=[{"from": "x", "to": "y"}, {"from": "y", "to": "z"}, {"from": "z", "to": "a"}],
        )
    )
    assert _conditions(report) == [NODE_UNREACHABLE_FROM_START] * 3


def test_a_path_map_label_valued_end_resolves_to_the_end_sentinel() -> None:
    """§1.7: the ``"END"`` literal, blessed for ``path_map`` values (ledger §1/§4; IR-SPEC m3).

    The branch taking it is neither a dangling reference nor a dead end: it reaches END.
    """
    report = check_graph_well_formed(
        _ir(
            entry="router",
            finish="done",
            nodes=["router", "done"],
            edges=[
                {
                    "from": "router",
                    "kind": "conditional",
                    "condition": "…",
                    "path_map": {"stop": "END", "go": "done"},
                }
            ],
        )
    )
    assert _witness(report).terminal_nodes == ("done", "router")


def test_to_end_on_a_normal_edge_stays_unblessed_and_falls_to_condition_iv() -> None:
    """PD-007 Q2 (VAL-D1, ratified 2026-07-24): the blessing is ``path_map``-only.

    A ``normal``/``send`` edge naming ``"END"`` is looked up in $V$ like any other target and,
    naming no node, falls through to ``edge-target-undefined`` — DEC-12 scope (d). PD-007
    confirmed empirically that no corpus fixture writes the shape; the ruling is what this
    pins, since IR-SPEC §4.1's own (m4) sentence still reads the other way on paper.
    """
    report = check_graph_well_formed(
        _ir(entry="a", finish="a", nodes=["a"], edges=[{"from": "a", "to": "END"}])
    )
    condition, location = _records(report)[0]
    assert condition == EDGE_TARGET_UNDEFINED
    assert isinstance(location, P01EdgeLocation)
    assert location.undefined_target == "END"


def test_a_trap_component_is_deliberately_not_flagged() -> None:
    """PD-007 Q1 (VAL-D1): condition (ii) stays sinks-only, as §1.4 Step 4 is written.

    ``spin`` and ``round`` can never reach END, and neither is a sink, so the catalog-literal
    reading finds nothing. That is a *ruled* scope boundary, not an oversight: the strict
    alternative would overlap P-02's cycle charter (DEC-05 D2, one root cause one report) and
    is drafted as a Phase-1 item instead. A future change here needs its own vault ruling.
    """
    report = check_graph_well_formed(
        _ir(
            entry="a",
            finish="a",
            nodes=["a", "spin", "round"],
            edges=[
                {"from": "a", "to": "spin"},
                {"from": "spin", "to": "round"},
                {"from": "round", "to": "spin"},
            ],
        )
    )
    assert report.result == "pass"
    assert "spin" in _witness(report).reachable_from_start


def test_an_opaque_subgraph_node_is_one_vertex_and_its_interior_is_not_read() -> None:
    """§1.2/§1.7: a compiled subgraph mounted as a node is one vertex (``positive-03``).

    Interior well-formedness is P-10's territory. The IR carries no interior to read, so the
    assertion that matters is that P-01 treats the node like any other — which the fixture's
    pass demonstrates, and its node count pins.
    """
    witness = _witness(check_graph_well_formed(_ir_of(POSITIVES[2])))
    assert "book_travel_subgraph" in witness.reachable_from_start
    assert len(witness.reachable_from_start) == 3


def test_a_finish_node_is_never_reported_as_a_dead_end() -> None:
    """§1.4 Step 4's own comment: "finish nodes carry →__end__, never sinks"."""
    report = check_graph_well_formed(
        _ir(entry="a", finish=["a", "b"], nodes=["a", "b"], edges=[{"from": "a", "to": "b"}])
    )
    assert report.result == "pass"
    assert _witness(report).terminal_nodes == ("a", "b")


# ── §0.3's P-01-clean precondition: the degradation convention is P-01's own ─────────────


def test_a_model_carrying_phantom_vertices_is_refused() -> None:
    """§0.3 gives P-01 "drops dangling-target edges"; carrying is P-02's and P-04's reading.

    Sharing one model across the wedge is safe only while every consumer agrees with how it
    was built, and §0.3 says outright that "cross-validator agreement on ill-formed input is
    NOT promised". So the wrong model is refused loudly rather than analysed quietly: with
    the phantom carried, ``compliance_log`` would be reachable and ``mixed/04``'s condition-(i)
    finding would silently disappear.
    """
    carried = build_graph_model(_ir_of(MIXED_04), carry_unresolved_references=True)
    with pytest.raises(ValueError, match="resolvable subgraph"):
        check_graph_well_formed(_ir_of(MIXED_04), model=carried)


@pytest.mark.parametrize("relative", (*FIXTURES, MIXED_04))
def test_a_shared_model_gives_the_same_answer_as_one_built_here(relative: str) -> None:
    """What makes ``verify()``'s one-build-for-five sharing safe (VAL-03's pinned invariant)."""
    ir = _ir_of(relative)
    assert check_graph_well_formed(ir) == check_graph_well_formed(ir, model=build_graph_model(ir))


# ── WA-07 ────────────────────────────────────────────────────────────────────────────────


#: The execution-substrate and HTTP/LLM-client packages that must stay out of the P-01 import
#: closure. VAL-04's ten plus ``langsmith``, which ``tests/testing/test_hermeticity.py``
#: already blocks and the two validator tripwires had not caught up with.
_FORBIDDEN = (
    "{'langgraph', 'langchain', 'langchain_core', 'langsmith', 'networkx', 'openai', "
    "'anthropic', 'httpx', 'requests', 'aiohttp', 'urllib3'}"
)


def _tripwire_script(probe: str = "") -> str:
    """The guarded child: patch, import, run P-01, report. ``probe`` arms the raiser.

    Shared by the tripwire and its negative controls so that they cannot drift apart — a
    control that armed a *different* raiser from the one the real test relies on would prove
    nothing about the real test.
    """
    fixture = FIXTURES_DIR / MIXED_04
    return (
        "import json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the P-01 path')\n"
        "def _trip_dns(*a, **k):\n"
        "    attempts.append('getaddrinfo'); print('WA07-TRIP', file=sys.stderr)\n"
        "    raise AssertionError('name resolved on the P-01 path')\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip_dns\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify.properties.graph_well_formed import check_graph_well_formed\n"
        f"with open({str(fixture)!r}, encoding='utf-8') as handle:\n"
        "    document = yaml.safe_load(handle)\n"
        "ir = WorkflowIR.model_validate_json(json.dumps(document['ir']))\n"
        "assert check_graph_well_formed(ir).result == 'fail'\n"
        f"{probe}"
        f"print([m for m in sys.modules if m.split('.')[0] in {_FORBIDDEN}] + attempts)\n"
    )


def test_running_p01_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the P-01 path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter, because another test in this session may have imported anything.
    Three claims, separately enforced: no execution-substrate or HTTP/LLM-client package
    enters the import closure; no socket is created and no name resolved, either while
    importing the validator or while *running* it over a real corpus fixture; and a swallowed
    exception still fails the run, because every attempt is recorded before the raise and also
    announced on stderr. The call leg is the part an import-time probe cannot give. Stdlib
    module presence is deliberately not asserted — VAL-13 traced that to version-dependent
    stdlib internals with no network involved.

    One residual, named rather than left implicit: the package leg is a post-hoc ``sys.modules``
    scan, not an import blocker, so a *swallowed* substrate import in an environment where the
    package is absent would go unrecorded here. ``tests/testing/test_hermeticity.py`` closes
    that for this same validator — its guarded child installs a real import blocker and runs
    P-01 through the harness inside it. The two compose; neither alone is sufficient.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script()], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    "probe",
    ("socket.socket()\n", "socket.getaddrinfo('example.invalid', 80)\n"),
    ids=("socket", "getaddrinfo"),
)
def test_the_tripwire_fires_when_the_guarded_path_is_armed(probe: str) -> None:
    """The negative control: prove the raiser is live, on the *same* script the tripwire runs.

    Without this, a patch that silently stopped installing ``_TripSocket`` — a renamed stdlib
    attribute, a reordered import, a typo — would leave the tripwire passing for the wrong
    reason, which is the one failure mode a tripwire must not have. Arming it after the
    validator has already run isolates the raiser: the green run above got that far too, so a
    non-zero exit here can only come from the probe.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script(probe)],
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the expected result here, not an error
    )
    assert completed.returncode != 0, completed.stdout
    assert "WA07-TRIP" in completed.stderr, completed.stderr


def test_p01_reads_no_field_outside_its_io_contract() -> None:
    """§1.3 "Not read": ``state``, ``annotations``, ``runtime``, and router ``condition``s.

    Demonstrated rather than asserted about the source: strip every one of them from
    ``mixed/10`` and the verdict and witness are unchanged. §1.5's "independent of |Σ|" is the
    same claim from the complexity side.
    """
    document = _load(MIXED_10)["ir"]
    stripped = {
        **document,
        "state": {},
        "nodes": [{"id": node["id"]} for node in document["nodes"]],
        "edges": [
            {key: value for key, value in edge.items() if key != "condition"}
            for edge in document["edges"]
        ],
    }
    stripped.pop("runtime", None)
    full = check_graph_well_formed(WorkflowIR.model_validate_json(json.dumps(document)))
    bare = check_graph_well_formed(WorkflowIR.model_validate_json(json.dumps(stripped)))
    assert full == bare
