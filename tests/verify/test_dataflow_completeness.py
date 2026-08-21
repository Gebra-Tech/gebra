"""P-04 ``dataflow-completeness`` against the vendored corpus (PROPERTY-CATALOG-SPEC §4).

The must-write analysis: every reachable node's declared reads, checked against the
every-``START``-path quantification of the catalog statement, asserted as **model equality**
against the fixtures' own ``expected:`` blocks (A6 PC-6). The golden harness owns that
comparison corpus-wide (:mod:`gebra.testing.harness`); as in ``test_graph_well_formed.py``
this module reaches the fixtures through PyYAML and the models directly, so it is an
*independent* second path to the same assertion rather than a caller of the harness that would
pass whenever the harness agreed with itself.

Four things this module is careful about, because each is a place P-04 could look right and be
wrong:

* **The two algorithm forms are cross-checked against each other, over the whole corpus.**
  §4.4 offers the MFP fixpoint and A8 §7.2's per-key writer-avoiding reachability as
  interchangeable (T1+T2+T5), and D-09 "may implement either". The validator runs the fixpoint
  for the verdict; :func:`test_the_fixpoint_and_the_reachability_reference_form_agree_on_every_
  corpus_obligation` re-derives every obligation in the corpus with a reachability
  implementation written here from A8 §7.2 alone, and the two agree key for key. That is T5
  machine-checked rather than cited.
* **SCC non-collapse is demonstrated on the pair the corpus lacks.** §4.6 records the gap in
  its own words — "no cycle-entry pair (entry-at-reader negative vs entry-at-writer positive,
  A8 §8.4)". Both graphs are built here, and the discriminating fact is asserted directly:
  they have the *same* SCC with the *same* union of intra-SCC writes, so any collapse gives
  them one answer, while P-04 gives them opposite ones.
* **The offending path is re-checked against the graph, not just compared.** A path that
  happened to match a fixture string would still be wrong if it were not a real ``START``-path
  avoiding the key's other writers, so every emitted path is walked edge by edge.
* **The two mixed residues are ledgered, not smoothed over.** ``mixed/04`` and ``mixed/08``
  are the two obligations where the validator and the vendored block differ; each has its own
  named test asserting the difference in *both* directions, so a change on either side goes
  red immediately. Their dispositions are `FM-008`/`FM-009` in
  ``docs/governance/FIDELITY-MATRIX.md``.

WA-07: nothing here executes a workflow, a node, or a network call. Fixtures are read with
PyYAML's safe loader; the ``ir:`` block is validated into the frozen IR models and read as
data; ``source_snippet`` is never touched.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import deque
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.ir import WorkflowIR
from gebra.verify import (
    CoFailure,
    DataflowLocation,
    DataflowWitness,
    P04Failure,
    PropertyReport,
    build_graph_model,
    check_graph_well_formed,
    condition,
    is_implemented,
    models_equivalent,
    run_property,
    to_data,
    validate_location,
    validate_report,
)
from gebra.verify.graph import END_VERTEX, START_VERTEX, GraphModel
from gebra.verify.properties import dataflow_completeness
from gebra.verify.properties.dataflow_completeness import (
    PROPERTY_SLUG,
    READ_KEY_NEVER_WRITTEN_ON_PATH,
    check_dataflow_completeness,
)
from tests.conftest import FIXTURES_DIR

#: The six P-04 property fixtures (§4.6), by path.
FIXTURES: tuple[str, ...] = (
    "dataflow-completeness/positive-01-linear-itinerary-pipeline.yaml",
    "dataflow-completeness/positive-02-conditional-both-branches-write.yaml",
    "dataflow-completeness/positive-03-parallel-fanout-reduced-results.yaml",
    "dataflow-completeness/negative-01-express-path-skips-writer.yaml",
    "dataflow-completeness/negative-02-writer-downstream-of-reader.yaml",
    "dataflow-completeness/negative-03-fan-in-missing-branch-writer.yaml",
)

POSITIVES: tuple[str, ...] = FIXTURES[:3]
NEGATIVES: tuple[str, ...] = FIXTURES[3:]

#: The four mixed-corpus members §4.6 names as exercising P-04.
MIXED_02 = "mixed/02-unwitnessed-loop-reading-unwritten-key.yaml"
MIXED_04 = "mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml"
MIXED_05 = "mixed/05-evolution-drops-witness-and-state-field.yaml"
MIXED_08 = "mixed/08-express-path-skips-gate-writer-and-witnessed-exit.yaml"


# ── Fixture loading (§0.3's rule, spelled out — the second, independent path) ────────────


def _load(relative: str) -> dict[str, Any]:
    document = yaml.safe_load((FIXTURES_DIR / relative).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _ir_of(relative: str, key: str = "ir") -> WorkflowIR:
    """A fixture's IR block, validated into the frozen models (JSON mode, §2.5 note 4)."""
    return WorkflowIR.model_validate_json(json.dumps(_load(relative)[key]))


def _expected_report(relative: str) -> PropertyReport:
    """The fixture's ``expected:`` block as P-04's report — §0.3's loading rule verbatim."""
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


CORPUS: list[tuple[str, WorkflowIR]] = _corpus_irs()
CORPUS_IDS: list[str] = [identity for identity, _ in CORPUS]


# ── Building IRs by hand, for the §4.7 edge cases the corpus does not carry ──────────────


def _ir(
    *,
    entry: str | list[str],
    finish: str | list[str],
    state: dict[str, Any] | None = None,
    nodes: dict[str, tuple[list[str], list[str]]],
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowIR:
    """An IR carrying only what §4.3 lists: topology, Σ, and per-node ``input``/``output``."""
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": entry,
                "finish": finish,
                **({"state": state} if state is not None else {}),
                "nodes": [
                    {"id": name, "annotations": {"input": reads, "output": writes}}
                    for name, (reads, writes) in nodes.items()
                ],
                "edges": edges if edges is not None else [],
            }
        )
    )


def _chain(*names: str) -> list[dict[str, Any]]:
    """``normal`` edges wiring ``names`` into a chain."""
    return [{"from": one, "to": other} for one, other in pairwise(names)]


# ── Acceptance box 1: the corpus reproduces, model for model ─────────────────────────────


@pytest.mark.parametrize("relative", FIXTURES, ids=[name.split("/")[1][:11] for name in FIXTURES])
def test_the_validator_reproduces_the_fixture_report(relative: str) -> None:
    """§0.3/A6 PC-6: one model, two duties — the validator's output and the fixture's
    ``expected:`` block validate into the same class and compare as models.

    Compared against the **raw** block, nothing normalized on either side, so a validator that
    only agreed after a helper had massaged it would fail here.
    """
    produced = check_dataflow_completeness(_ir_of(relative))

    assert models_equivalent(produced, _expected_report(relative)), to_data(produced)


@pytest.mark.parametrize("relative", FIXTURES, ids=[name.split("/")[1][:11] for name in FIXTURES])
def test_the_report_is_spec_shaped_and_round_trips(relative: str) -> None:
    """PC-4: the report serializes in definition order with ``None``-valued optionals dropped,
    and reloads into an equal model — the property a fixture's ``expected:`` block depends on.
    """
    produced = check_dataflow_completeness(_ir_of(relative))

    reloaded = validate_report({"property": PROPERTY_SLUG, **to_data(produced)})
    assert reloaded == produced
    assert (produced.witness is None) == (produced.result == "fail")


def test_the_grades_are_read_off_the_registry_never_restated() -> None:
    """§4.3: "exactly one" condition ID, and §0.4 pins its grade — FATAL, DEFENSIBLE-A.

    Asserted against the registry rather than against literals, so the module cannot drift from
    the catalog by restating a grade it does not own.
    """
    entry = condition(READ_KEY_NEVER_WRITTEN_ON_PATH)

    assert (entry.severity, entry.claim_class) == ("fatal", "defensible-a")
    assert entry.property_slug == PROPERTY_SLUG
    for relative in NEGATIVES:
        failure = check_dataflow_completeness(_ir_of(relative)).failure
        assert failure is not None
        assert (failure.severity, failure.claim_class) == (entry.severity, entry.claim_class)
        assert failure.property_condition == READ_KEY_NEVER_WRITTEN_ON_PATH


def test_no_p04_report_carries_a_remediation() -> None:
    """§4.4 renders none, and P-04 has no Appendix B grammar to render one from.

    Pinned because it is an absence: an invented remediation string would break model equality
    on every negative, and nothing else in the suite would say why.
    """
    for relative in NEGATIVES + (MIXED_02, MIXED_08):
        failure = check_dataflow_completeness(_ir_of(relative)).failure
        assert failure is not None
        assert failure.remediation is None


def test_every_failure_is_the_p04_subtype_carrying_the_dataflow_location() -> None:
    """§4.3 declares ``P04Failure`` with a ``DataflowLocation``; pydantic equality is
    class-sensitive, so building the base ``Failure`` would silently lose PC-6 identity on
    exactly the fixtures that carry neither optional diagnostic."""
    for relative in NEGATIVES + (MIXED_02, MIXED_08):
        failure = check_dataflow_completeness(_ir_of(relative)).failure
        assert type(failure) is P04Failure
        assert type(failure.location) is DataflowLocation
        assert failure.location.node and failure.location.path


def test_the_two_optional_diagnostics_appear_exactly_where_the_corpus_pins_them() -> None:
    """DEC-11 pin 3: both are kept, "emitted only when non-empty", "never part of the verdict".

    The corpus fixes which is which — ``writers_on_other_paths`` on ``negative-01``/``-03``,
    ``downstream_writers`` on ``negative-02`` (§4.3's own precedent list) — and the absence of
    the other on each is asserted too, because a diagnostic emitted when empty would serialize
    as ``[]`` and break model equality.
    """
    expectations = {
        NEGATIVES[0]: (("book_flight",), None),
        NEGATIVES[1]: (None, ("publish_itinerary",)),
        NEGATIVES[2]: (("fetch_loyalty_profile",), None),
    }
    for relative, (upstream, downstream) in expectations.items():
        failure = check_dataflow_completeness(_ir_of(relative)).failure
        assert isinstance(failure, P04Failure)
        assert failure.writers_on_other_paths == upstream
        assert failure.downstream_writers == downstream
        # And the fixture says the same, off its own block rather than off this table.
        block = _load(relative)["expected"]["failure"]
        assert block.get("writers_on_other_paths") == (list(upstream) if upstream else None)
        assert block.get("downstream_writers") == (list(downstream) if downstream else None)


def test_the_start_sentinel_marks_exactly_the_boundary_set() -> None:
    """§4.2 "Graph inputs": a key with ``optional: true`` in ``state`` is $I_0$, treated as
    written at ``START``; §4.3 makes the display sentinel in ``satisfied_by`` equivalent to it.

    Both sides come off the fixture — the boundary from its ``state`` block, the sentinel from
    the produced witness — so neither is a transcription of the other.
    """
    for relative in POSITIVES:
        document = _load(relative)
        boundary = {
            key
            for key, field in (document["ir"].get("state") or {}).items()
            if isinstance(field, dict) and field.get("optional")
        }
        witness = check_dataflow_completeness(_ir_of(relative)).witness
        assert isinstance(witness, DataflowWitness)
        assert boundary  # the three positives all declare a graph input
        for entry in witness.coverage:
            assert ("START" in entry.satisfied_by) == (entry.key in boundary), entry


def test_the_coverage_list_is_one_entry_per_reachable_reader_and_sigma_key() -> None:
    """§4.3: "one entry per (reachable reader, read key)". Derived from the IR here, never
    restated from the fixture, so a witness that dropped or duplicated an obligation fails."""
    for relative in POSITIVES:
        ir = _ir_of(relative)
        graph = build_graph_model(ir, carry_unresolved_references=True)
        reach = graph.descendants(START_VERTEX) | {START_VERTEX}
        keys = set(ir.state or {})
        expected = {
            (node.id, key)
            for node in ir.nodes
            if node.id in reach
            for key in (node.annotations.input or () if node.annotations else ())
            if key in keys
        }
        witness = check_dataflow_completeness(ir).witness
        assert isinstance(witness, DataflowWitness)

        assert {(entry.node, entry.key) for entry in witness.coverage} == expected
        assert len(witness.coverage) == len(expected)


@pytest.mark.parametrize(
    "relative", NEGATIVES + (MIXED_02, MIXED_08), ids=lambda name: name.split("/")[1][:11]
)
def test_the_offending_path_is_a_real_start_path_that_avoids_the_other_writers(
    relative: str,
) -> None:
    """§4.4 Step 4: ``shortest_path(H, START, v)`` over $G$ with $W_k \\setminus \\{v\\}$ removed.

    Re-checked against the graph rather than against a string: every consecutive pair is a real
    edge, the walk starts at ``START`` and ends at the reading node, and no interior vertex
    writes the key. A path that merely matched the fixture text would still be evidence of
    nothing if it were not a path.
    """
    ir = _ir_of(relative)
    graph = build_graph_model(ir, carry_unresolved_references=True)
    failure = check_dataflow_completeness(ir).failure
    assert isinstance(failure, P04Failure)
    walk = tuple(vertex if vertex != "START" else START_VERTEX for vertex in failure.location.path)
    writers = {
        node.id
        for node in ir.nodes
        if node.annotations and failure.location.key in (node.annotations.output or ())
    }

    assert walk[0] == START_VERTEX
    assert walk[-1] == failure.location.node
    assert len(set(walk)) == len(walk)  # a path, not a walk that revisits
    for tail, head in pairwise(walk):
        assert graph.has_edge(tail, head), (tail, head)
    assert writers.isdisjoint(walk[:-1])


def test_the_offending_path_is_the_shortest_one() -> None:
    """§4.4 Step 4 says "BFS-shortest"; asserted by re-deriving the distance independently.

    Length rather than identity, because several shortest paths may exist and which one a BFS
    returns is an engineering choice (this module's is: expand successors in ledger §6 order).
    """
    for relative in NEGATIVES + (MIXED_02, MIXED_08):
        ir = _ir_of(relative)
        graph = build_graph_model(ir, carry_unresolved_references=True)
        failure = check_dataflow_completeness(ir).failure
        assert isinstance(failure, P04Failure)
        writers = {
            node.id
            for node in ir.nodes
            if node.annotations and failure.location.key in (node.annotations.output or ())
        }
        restricted = graph.subgraph(graph.vertex_set - (writers - {failure.location.node}))

        distance = _distance(restricted, START_VERTEX, failure.location.node)
        assert len(failure.location.path) == distance, (relative, failure.location.path)


def _distance(graph: GraphModel, source: str, target: str) -> int:
    """Vertices on a shortest ``source`` → ``target`` path, or 0 if there is none."""
    seen = {source: 1}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        if current == target:
            return seen[current]
        for successor in graph.successors(current):
            if successor not in seen:
                seen[successor] = seen[current] + 1
                queue.append(successor)
    return 0


# ── The two §4.4 algorithm forms agree — A8 T5, machine-checked ──────────────────────────


def _reference_violation(graph: GraphModel, writers: frozenset[str], vertex: str, key: str) -> bool:
    """A8 §7.2/T5, implemented here from the statement alone: $(v,k)$ is violated **iff**
    ``START`` reaches $v$ avoiding $W_k \\setminus \\{v\\}$.

    Written as its own BFS over the shared model rather than by calling anything in the
    validator, so the cross-check below is two implementations meeting, not one talking to
    itself. ``key`` is unused by the search and named only so a failure message can say which
    obligation disagreed.
    """
    del key
    removed = writers - {vertex}
    if START_VERTEX in removed:
        return False  # every START-path is written at its first vertex
    seen = {START_VERTEX}
    queue = deque([START_VERTEX])
    while queue:
        current = queue.popleft()
        if current == vertex:
            return True
        for successor in graph.successors(current):
            if successor not in seen and successor not in removed:
                seen.add(successor)
                queue.append(successor)
    return False


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_the_fixpoint_and_the_reachability_reference_form_agree(
    identity: str, ir: WorkflowIR
) -> None:
    """§4.4's two sanctioned algorithms give the same verdict on every corpus obligation.

    "Provably interchangeable with per-key writer-avoiding reachability (A8 §7.2) — D-09 may
    implement either" (§4.4 header), by A8 T1 + T2 + T5. The validator implements the fixpoint;
    this re-derives every obligation with the reachability form and asserts they agree, over
    all 67 IR snapshots in the corpus. It is the check that would catch a fixpoint that had
    converged to the wrong solution while still producing plausible reports.
    """
    graph = build_graph_model(ir, carry_unresolved_references=True)
    contracts = dataflow_completeness._contracts(ir, graph)
    reach = graph.descendants(START_VERTEX) | {START_VERTEX}
    inn = dataflow_completeness._fixpoint(graph, reach, contracts)

    checked = 0
    for node in ir.nodes:
        if node.id not in reach:
            continue
        for key in contracts.reads[node.id]:
            mask = contracts.bit.get(key)
            if mask is None:
                continue
            checked += 1
            fixpoint_says_violated = not inn[node.id] & mask
            reference_says_violated = _reference_violation(
                graph, contracts.writers[key], node.id, key
            )
            assert fixpoint_says_violated == reference_says_violated, (identity, node.id, key)
    assert checked or not ir.state


# ── Acceptance box 2: SCCs are never collapsed (§4.1 warning; A8 T3) ─────────────────────

#: A8 §8.4's cycle-entry pair, which §4.6 records as a corpus gap. Both graphs have the same
#: two-node SCC and the same union of intra-SCC writes; only the entry point differs.
_ENTRY_AT_READER = _ir(
    entry="reader",
    finish="exit_node",
    state={"seed": {"type": "str", "optional": True}, "shared": "str"},
    nodes={
        "reader": (["shared"], []),
        "writer": (["seed"], ["shared"]),
        "exit_node": (["seed"], []),
    },
    edges=[
        {"from": "reader", "to": "writer"},
        {
            "from": "writer",
            "kind": "conditional",
            "path_map": {"again": "reader", "out": "exit_node"},
        },
    ],
)

_ENTRY_AT_WRITER = _ir(
    entry="writer",
    finish="exit_node",
    state={"seed": {"type": "str", "optional": True}, "shared": "str"},
    nodes={
        "reader": (["shared"], []),
        "writer": (["seed"], ["shared"]),
        "exit_node": (["seed"], []),
    },
    edges=[
        {"from": "writer", "to": "reader"},
        {
            "from": "reader",
            "kind": "conditional",
            "path_map": {"again": "writer", "out": "exit_node"},
        },
    ],
)


def test_an_entry_at_reader_cycle_fails() -> None:
    """A8 T3's counterexample, and §4.1's warning in executable form.

    Entering the cycle *at* the reader means the first arrival sees ``shared`` unwritten, which
    is §4.2's first-arrival semantics — "a node's own write never satisfies its own read …
    matching the runtime fact that the first iteration of an entry-at-reader loop sees the key
    unwritten". An implementation that collapsed the SCC into a supernode with **unioned
    writes** would report a pass here: the union contains ``shared``, because ``writer`` is in
    the same component.
    """
    report = check_dataflow_completeness(_ENTRY_AT_READER)

    assert report.result == "fail"
    failure = report.failure
    assert isinstance(failure, P04Failure)
    assert (failure.location.node, failure.location.key) == ("reader", "shared")
    assert failure.location.path == ("START", "reader")
    # The writer is inside the reader's own SCC and reaches it, so it is a real "other path".
    assert failure.writers_on_other_paths == ("writer",)
    assert failure.downstream_writers == ("writer",)


def test_an_entry_at_writer_cycle_passes() -> None:
    """The dual, which the *other* collapse gets wrong.

    Entering at the writer means every ``START``-path to ``reader`` passes through ``writer``,
    so the read is covered — even though reader and writer share an SCC. An implementation that
    handled the T3 unsoundness by **ignoring intra-SCC writes** would report a false positive
    here, which §4.1 names as the incomplete dual.
    """
    report = check_dataflow_completeness(_ENTRY_AT_WRITER)

    assert report.result == "pass"
    witness = report.witness
    assert isinstance(witness, DataflowWitness)
    assert any(
        (entry.node, entry.key, entry.satisfied_by) == ("reader", "shared", ("writer",))
        for entry in witness.coverage
    )


def test_the_cycle_entry_pair_is_indistinguishable_to_any_scc_collapse() -> None:
    """The discriminating fact, asserted rather than argued — this is the acceptance box.

    The two graphs have the **same** non-trivial SCC over the same members, and the members
    write the same keys, so *every* summary that replaces the component by its members' writes
    (in either direction) assigns them the same value. P-04 nevertheless returns ``fail`` for
    one and ``pass`` for the other, so the analysis cannot be reading such a summary: the
    node-level equations of §4.4 Step 3 are the semantics and the condensation is only the
    order they are evaluated in.
    """
    reader_first = build_graph_model(_ENTRY_AT_READER)
    writer_first = build_graph_model(_ENTRY_AT_WRITER)
    component = ("reader", "writer")

    assert reader_first.components.members_of("reader") == component
    assert writer_first.components.members_of("reader") == component
    assert reader_first.components.is_nontrivial("reader")
    assert writer_first.components.is_nontrivial("reader")
    assert check_dataflow_completeness(_ENTRY_AT_READER).result == "fail"
    assert check_dataflow_completeness(_ENTRY_AT_WRITER).result == "pass"


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_the_condensation_supplies_order_only(identity: str, ir: WorkflowIR) -> None:
    """§4.1: "Reverse postorder over ``nx.condensation`` is a legitimate *worklist order*; the
    node-level equations are the semantics."

    Re-solving the same equations under a deliberately hostile schedule — the worklist order
    reversed, which puts every component after its successors — reaches the identical fixpoint
    on every corpus snapshot. A solution that depended on the order would be reading the
    condensation as a semantics, which is exactly what §4.1 forbids.
    """
    graph = build_graph_model(ir, carry_unresolved_references=True)
    contracts = dataflow_completeness._contracts(ir, graph)
    reach = graph.descendants(START_VERTEX) | {START_VERTEX}
    order = tuple(v for v in graph.worklist_order if v in reach and v != START_VERTEX)

    assert dataflow_completeness._fixpoint(graph, reach, contracts) == _solve(
        graph, contracts, tuple(reversed(order))
    ), identity


def _solve(graph: GraphModel, contracts: Any, order: tuple[str, ...]) -> dict[str, int]:
    """The §4.4 Step 3 equations under an arbitrary round-robin schedule."""
    inn = dict.fromkeys(graph.vertices, contracts.universe)
    out = dict.fromkeys(graph.vertices, contracts.universe)
    out[START_VERTEX] = contracts.boundary
    while dataflow_completeness._sweep(graph, order, contracts, inn, out):
        pass
    return inn


def test_a_cyclic_corpus_fixture_still_decides_node_by_node() -> None:
    """``mixed/08`` carries a five-member SCC and a real P-04 violation inside it.

    The reads that *are* covered inside the component stay covered and the one that is not
    still fails, which a collapse in either direction would flatten into one verdict for the
    whole component.
    """
    ir = _ir_of(MIXED_08)
    graph = build_graph_model(ir, carry_unresolved_references=True)
    component = graph.components.members_of("draft_reply")

    assert component == (
        "compliance_gate",
        "draft_reply",
        "final_check",
        "polish",
        "quality_gate",
    )
    failure = check_dataflow_completeness(ir).failure
    assert isinstance(failure, P04Failure)
    assert (failure.location.node, failure.location.key) == ("send_reply", "compliance_token")
    assert failure.co_failures is None  # the in-component reads of `reply` are all covered


# ── Acceptance box 3: the D2 subsumption — an unreachable reader is P-01's alone ─────────

#: A reader stranded off the ``START`` closure, reading a key nothing writes. No dangling
#: reference is involved, so P-01's and P-04's graphs agree about it exactly.
_STRANDED = _ir(
    entry="ingest",
    finish=["publish", "orphaned_reader"],
    state={"seed": {"type": "str", "optional": True}, "never_written": "str"},
    nodes={
        "ingest": (["seed"], []),
        "publish": (["seed"], []),
        "orphaned_reader": (["never_written"], []),
    },
    edges=_chain("ingest", "publish"),
)


def test_an_unreachable_reader_generates_no_p04_obligation() -> None:
    """DEC-05 D2, mechanized by ⊤-initialization plus the reachable-only loop (A8 T4).

    "A node unreachable from ``START`` generates **no** P-04 obligations, and its reads are
    P-01's findings exclusively" (the catalog statement's Scope paragraph). So P-04 passes, and
    — the sharper half — its witness names no coverage entry for the stranded node either: the
    obligation is not satisfied, it is never generated.
    """
    report = check_dataflow_completeness(_STRANDED)

    assert report.result == "pass"
    witness = report.witness
    assert isinstance(witness, DataflowWitness)
    assert {entry.node for entry in witness.coverage} == {"ingest", "publish"}
    assert all(entry.key != "never_written" for entry in witness.coverage)


def test_the_same_read_fails_the_moment_the_node_is_reachable() -> None:
    """The negative control: without it, the pass above could be vacuous — the read might be
    covered, or the key might not be in Σ. Wiring one edge flips it to the FATAL finding."""
    wired = _ir(
        entry="ingest",
        finish=["publish", "orphaned_reader"],
        state={"seed": {"type": "str", "optional": True}, "never_written": "str"},
        nodes={
            "ingest": (["seed"], []),
            "publish": (["seed"], []),
            "orphaned_reader": (["never_written"], []),
        },
        edges=[*_chain("ingest", "publish"), {"from": "ingest", "to": "orphaned_reader"}],
    )

    report = check_dataflow_completeness(wired)

    assert report.result == "fail"
    failure = report.failure
    assert isinstance(failure, P04Failure)
    assert (failure.location.node, failure.location.key) == ("orphaned_reader", "never_written")


def test_p01_owns_the_unreachable_reader_alone() -> None:
    """ "One root cause yields one report with no double-blame" — asserted across both
    validators on the same IR, which is the only place the claim is checkable.

    P-01 reports the node unreachable; P-04 reports nothing at all. The subsumption is that
    asymmetry, and ``subsumed_by: P-01`` is how a run-level report records it (§0.3 puts the
    field on the record, and REPORT-FORMAT-SPEC owns the wrapper that composes one).
    """
    topology = check_graph_well_formed(_STRANDED)
    dataflow = check_dataflow_completeness(_STRANDED)

    assert topology.result == "fail"
    assert topology.failure is not None
    assert topology.failure.property_condition == "node-unreachable-from-start"
    assert topology.failure.location.node == "orphaned_reader"  # type: ignore[union-attr]
    assert dataflow.result == "pass"


def test_the_corpus_records_the_subsumption_as_subsumed_by_p01() -> None:
    """``mixed/04`` is DEC-05 D2's own fixture: the P-04 read of ``legal_hold_ref`` under an
    unreachable node rides the P-01 report as a co-failure marked ``subsumed_by: P-01``, and
    the harness reads that as "no P-04 obligation" (projection rule PR-2).

    Read off the vendored block, so the reading is the corpus's and not this module's.
    """
    records = _load(MIXED_04)["expected"]["failure"]["co_failures"]
    subsumed = [record for record in records if record["property"] == PROPERTY_SLUG]

    assert len(subsumed) == 1
    assert subsumed[0]["subsumed_by"] == "P-01"
    assert subsumed[0]["property_condition"] == READ_KEY_NEVER_WRITTEN_ON_PATH
    assert subsumed[0]["location"]["node"] == "compliance_log"
    assert subsumed[0]["location"]["key"] == "legal_hold_ref"


# ── The two ledgered residues (FIDELITY-MATRIX §3) ───────────────────────────────────────


def test_mixed_04_is_the_degradation_convention_residue_fm_008() -> None:
    """``FM-008``, with its fork closed at DEC-26: the phantom no longer leaks into the path.

    ``mixed/04`` is P-01-**dirty** topology, where §0.3 defines no P-04 result. P-04's own
    §0.3 convention is "carries the phantom vertex with an empty contract", and that fixture
    carries a second dangling reference — an edge whose ``from`` names the same missing node
    — so carrying it re-wires ``compliance_log`` into the ``START`` closure and its read of
    ``legal_hold_ref`` becomes a live obligation. The fork FM-008 recorded — the carried
    phantom appearing inside ``DataflowLocation.path`` — was closed by DEC-26's §0.3
    phantom-leak rule (2026-08-09): a phantom is walk-internal, never report evidence, so
    the emitted path elides ``legal_hold_review`` while verdict, condition, key and node
    anchor are exactly as before.

    Asserted in **both** directions — what P-04 emits (phantom-free path), and that the
    fixture's block does not state a P-04 obligation — so a change on either side reopens
    the row rather than passing silently.
    """
    report = check_dataflow_completeness(_ir_of(MIXED_04))
    failure = report.failure
    assert isinstance(failure, P04Failure)

    assert report.result == "fail"
    assert (failure.location.node, failure.location.key) == ("compliance_log", "legal_hold_ref")
    assert failure.location.path == (
        "START",
        "intake",
        "triage",
        # DEC-26: the carried phantom (legal_hold_review) is elided from the emitted path
        "compliance_log",
    )
    assert "legal_hold_review" not in failure.location.path
    assert failure.co_failures is None
    # And the corpus states it as subsumed, which PR-2 reads as no obligation at all.
    assert _load(MIXED_04)["expected"]["failure"]["co_failures"][1]["subsumed_by"] == "P-01"


def test_mixed_08_matches_the_vendored_block_exactly_fm_009_closed() -> None:
    """``FM-009``, closed at DEC-24 (2026-08-08): the vendored block now carries the
    ``writers_on_other_paths`` diagnostic and the produced record matches it exactly.

    The open row's own basis became the revision: §4.4 Step 4 computes ``upstream ≠ ∅`` here
    — ``compliance_gate`` is the sole writer of ``compliance_token``, is reachable, and
    reaches ``send_reply`` along the standard path — and §4.3 emits the field whenever it is
    non-empty, exactly as ``negative-01``/``-03`` (carry it) and ``negative-02``/``mixed/02``
    (omit it) already encoded. The M13 owner action added the one key to the vault master
    (`Gebra-Tech/initial-documents@7be81a9`); this pin holds produced and vendored to each
    other so any regression on either side goes red immediately.
    """
    produced = check_dataflow_completeness(_ir_of(MIXED_08))
    failure = produced.failure
    assert isinstance(failure, P04Failure)
    block = _load(MIXED_08)["expected"]["failure"]

    assert failure.writers_on_other_paths == ("compliance_gate",)
    assert block["writers_on_other_paths"] == ["compliance_gate"]
    expected = validate_report(
        {
            "property": PROPERTY_SLUG,
            "result": "fail",
            "failure": {key: value for key, value in block.items() if key != "co_failures"},
        }
    )
    assert to_data(produced)["failure"] == to_data(expected)["failure"]
    assert models_equivalent(failure.location, expected.failure.location)  # type: ignore[union-attr]


def test_mixed_02_reproduces_the_cross_property_co_failure_record() -> None:
    """``mixed/02``'s P-04 share (projection rule PR-2): the same condition ID and the same
    location as the record riding P-02's report, down to the offending path."""
    produced = check_dataflow_completeness(_ir_of(MIXED_02))
    failure = produced.failure
    assert isinstance(failure, P04Failure)
    record = _load(MIXED_02)["expected"]["failure"]["co_failures"][0]

    assert record["property"] == PROPERTY_SLUG
    assert failure.property_condition == record["property_condition"]
    assert failure.location == validate_location(record["location"])
    assert failure.co_failures is None


def test_mixed_05_carries_a_snapshot_key_no_location_models_fm_006() -> None:
    """``FM-006``, unchanged by this card: the P-04 record on the evolution pair carries
    ``snapshot: ir_after``, which every §0.3 location refuses under ``extra="forbid"``.

    Pinned here because VAL-09 is the card that would otherwise be expected to close it: the
    obligation is ``unmodelled`` **before** any validator runs, so registering P-04 does not
    move it. What P-04 says about ``ir_after`` is asserted too, since that is the answer a
    future corpus revision would be compared against.
    """
    record = _load(MIXED_05)["expected"]["failure"]["co_failures"][2]
    assert record["property"] == PROPERTY_SLUG
    assert record["location"]["snapshot"] == "ir_after"

    failure = check_dataflow_completeness(_ir_of(MIXED_05, "ir_after")).failure
    assert isinstance(failure, P04Failure)
    assert (failure.location.node, failure.location.key) == ("fetch_data", "auth_token")
    assert failure.location.path == ("START", "fetch_data")
    assert check_dataflow_completeness(_ir_of(MIXED_05, "ir_before")).result == "pass"


# ── §0.3 packaging: one property, one report ─────────────────────────────────────────────


def test_several_findings_are_one_report_in_ledger_order() -> None:
    """§0.3: the deterministically-first finding fills ``failure`` and every further
    same-property finding rides ``co_failures`` — "findings are never dropped".

    §4.4's ordering rule is the ledger §6 comparator over the reading node, then the read key,
    so the primary here is ``alpha``/``missing_one`` and the other three follow in that order.
    """
    ir = _ir(
        entry="alpha",
        finish="omega",
        state={
            "seed": {"type": "str", "optional": True},
            "missing_one": "str",
            "missing_two": "str",
        },
        nodes={
            "alpha": (["missing_one", "missing_two"], []),
            "omega": (["missing_two", "missing_one"], []),
        },
        edges=_chain("alpha", "omega"),
    )

    failure = check_dataflow_completeness(ir).failure
    assert isinstance(failure, P04Failure)
    assert (failure.location.node, failure.location.key) == ("alpha", "missing_one")
    assert failure.co_failures is not None
    assert [
        (record.location.node, record.location.key)  # type: ignore[union-attr]
        for record in failure.co_failures
    ] == [("alpha", "missing_two"), ("omega", "missing_one"), ("omega", "missing_two")]


def test_a_co_failure_carries_its_own_grade_and_no_diagnostics() -> None:
    """§0.1: every record classifies its own claim. §4.4 packages the non-primary findings as
    plain ``CoFailure``s, which have no field for the two optional diagnostics — so those ride
    the primary alone, by the envelope's shape rather than by a choice made here."""
    ir = _ir(
        entry="alpha",
        finish="omega",
        state={"seed": {"type": "str", "optional": True}, "late": "str"},
        nodes={"alpha": (["late"], []), "omega": ([], ["late"])},
        edges=_chain("alpha", "omega"),
    )

    failure = check_dataflow_completeness(ir).failure
    assert isinstance(failure, P04Failure)
    assert failure.downstream_writers == ("omega",)
    assert failure.co_failures is None
    assert {field for field in CoFailure.model_fields} == {
        "property",
        "property_condition",
        "location",
        "severity",
        "claim_class",
        "subsumed_by",
        "note",
        "notes",  # structured same-property notes, DEC-23 (PD-037 Q2) — never a diagnostic
    }


def test_p04_emits_no_record_another_property_owns() -> None:
    """§0.4's ownership rule, enforced at the emission constructors: a P-04 report carries only
    ``read-key-never-written-on-path`` and only for ``dataflow-completeness``."""
    for _, ir in CORPUS:
        failure = check_dataflow_completeness(ir).failure
        if failure is None:
            continue
        assert failure.property_condition == READ_KEY_NEVER_WRITTEN_ON_PATH
        assert failure.advisories is None
        for record in failure.co_failures or ():
            assert record.property == PROPERTY_SLUG
            assert record.property_condition == READ_KEY_NEVER_WRITTEN_ON_PATH


def test_a_duplicated_node_id_yields_one_obligation_not_two() -> None:
    """The IR models admit a repeated ``nodes[].id``; the obligation loop iterates the vertex
    *set* in ledger §6 order rather than the ``nodes`` list, so a duplicate is one finding.

    That is §4.4's consistent reading rather than a liberty: Step 1 already keys ``reads`` and
    ``writes`` by id, so two entries with the same id are indistinguishable by the time Step 4
    runs, and "ordered by the ledger-§6 id comparator" has no meaning over a list carrying the
    same id twice. Whether the IR should admit one at all is the IR track's question, not this
    validator's; what is pinned here is that P-04 does not double-blame for it.
    """
    contract = {"id": "twice", "annotations": {"input": ["missing"], "output": []}}
    document: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "twice",
        "finish": "twice",
        "state": {"seed": {"type": "str", "optional": True}, "missing": "str"},
        "nodes": [contract],
        "edges": [],
    }
    ir = WorkflowIR.model_validate_json(json.dumps(document))
    doubled = WorkflowIR.model_validate_json(
        json.dumps({**document, "nodes": [contract, contract]})
    )

    assert [node.id for node in doubled.nodes] == ["twice", "twice"]
    failure = check_dataflow_completeness(doubled).failure
    assert isinstance(failure, P04Failure)
    assert failure.co_failures is None
    assert failure == check_dataflow_completeness(ir).failure


# ── §4.7's enumerated edge cases ─────────────────────────────────────────────────────────


def test_an_entry_only_graph_passes_with_an_empty_coverage() -> None:
    """§4.7: "empty/entry-only graph (no obligations ⇒ pass, empty coverage)"."""
    report = check_dataflow_completeness(_ir(entry="only", finish="only", nodes={"only": ([], [])}))

    assert report.result == "pass"
    assert report.witness == DataflowWitness(kind="dataflow", coverage=())


def test_a_graph_with_no_state_block_generates_no_obligation() -> None:
    """Σ absent ⇒ ``K = ∅`` ⇒ every declared read falls to the ``k ∉ K`` continue (§4.4 Step
    4), which is P-03's finding. A pass with an empty witness, never a crash."""
    report = check_dataflow_completeness(
        _ir(entry="only", finish="only", nodes={"only": (["undeclared"], [])})
    )

    assert report.result == "pass"
    assert report.witness == DataflowWitness(kind="dataflow", coverage=())


def test_a_read_key_outside_sigma_is_p03s_finding_not_p04s() -> None:
    """§4.4 Step 4: ``if k ∉ K: continue  # Σ-membership is P-03's finding``.

    The key is read by a reachable node and written by nobody — the exact shape of a P-04
    violation — and P-04 still says nothing, because it is not in Σ.
    """
    report = check_dataflow_completeness(
        _ir(
            entry="only",
            finish="only",
            state={"declared": {"type": "str", "optional": True}},
            nodes={"only": (["declared", "undeclared"], [])},
        )
    )

    assert report.result == "pass"
    witness = report.witness
    assert isinstance(witness, DataflowWitness)
    assert [(entry.node, entry.key) for entry in witness.coverage] == [("only", "declared")]


def test_the_entry_and_finish_list_forms_are_both_read() -> None:
    """§4.4 Step 0 wires ``as_list(ir.entry)`` and ``as_list(ir.finish)`` (ledger §1), so a
    graph with two entries has two boundary paths — and a key written on only one of them is
    uncovered at the merge."""
    ir = _ir(
        entry=["left", "right"],
        finish="merge",
        state={"seed": {"type": "str", "optional": True}, "only_left": "str"},
        nodes={
            "left": ([], ["only_left"]),
            "right": ([], []),
            "merge": (["only_left"], []),
        },
        edges=[{"from": "left", "to": "merge"}, {"from": "right", "to": "merge"}],
    )

    failure = check_dataflow_completeness(ir).failure
    assert isinstance(failure, P04Failure)
    assert failure.location.path == ("START", "right", "merge")
    assert failure.writers_on_other_paths == ("left",)


def test_a_path_map_target_of_end_resolves_to_the_sentinel() -> None:
    """IR-SPEC §4.1 (m3): the literal ``"END"`` in a ``path_map`` value is the exit sentinel,
    not a node — so a router labelled to END adds no obligation and strands nothing."""
    ir = _ir(
        entry="router",
        finish="router",
        state={"seed": {"type": "str", "optional": True}},
        nodes={"router": (["seed"], []), "onward": (["seed"], [])},
        edges=[
            {"from": "router", "kind": "conditional", "path_map": {"go": "onward", "stop": "END"}},
            {"from": "onward", "to": "router"},
        ],
    )

    report = check_dataflow_completeness(ir)

    assert report.result == "pass"
    graph = build_graph_model(ir, carry_unresolved_references=True)
    assert graph.has_edge("router", END_VERTEX)


def test_a_self_writing_reader_does_not_satisfy_its_own_read() -> None:
    """§4.2's first-arrival semantics and §4.4's endpoint exemption ``W[k] ∖ {v}``.

    The node writes the very key it reads and nothing upstream does; ``IN[v]`` is the state
    *before* it runs, so the obligation is violated and the attribution path still ends at it —
    which is what the exemption exists for: removing ``v`` too would leave no path at all.
    """
    ir = _ir(
        entry="loop_body",
        finish="loop_body",
        state={"seed": {"type": "str", "optional": True}, "accumulator": "str"},
        nodes={"loop_body": (["accumulator"], ["accumulator"])},
        edges=[{"from": "loop_body", "to": "loop_body"}],
    )

    failure = check_dataflow_completeness(ir).failure
    assert isinstance(failure, P04Failure)
    assert failure.location.path == ("START", "loop_body")
    assert failure.writers_on_other_paths is None  # `∖ {v}` removes the only writer
    assert failure.downstream_writers is None  # nor is it its own downstream writer


def test_the_first_node_sees_the_boundary_set_and_an_unreached_one_keeps_top() -> None:
    """§4.4 Step 3's two initialization rules, asserted apart because confusing them is how a
    must-write analysis silently passes everything.

    ⊤-initialization is *everywhere*, but ``OUT[START] := I0`` overrides it at the source and
    ``START`` is excluded from the update set — so the entry node's ``IN`` is $I_0$, strictly
    below ⊤. A vertex outside ``Reach`` is never updated and keeps ⊤, which is what makes it
    neutral in any meet it appears in. The empty-meet rule itself ("empty meet ≡ ⊤ = K") is the
    fold's identity rather than a branch: among reachable vertices only ``START`` has no
    predecessor, and it is not updated.
    """
    graph = build_graph_model(_STRANDED, carry_unresolved_references=True)
    contracts = dataflow_completeness._contracts(_STRANDED, graph)
    reach = graph.descendants(START_VERTEX) | {START_VERTEX}

    inn = dataflow_completeness._fixpoint(graph, reach, contracts)
    assert "orphaned_reader" not in reach
    assert inn["ingest"] == contracts.boundary != contracts.universe
    assert inn["orphaned_reader"] == contracts.universe
    assert all(graph.predecessors(vertex) for vertex in reach if vertex != START_VERTEX)


def test_the_attribution_builds_one_search_tree_per_restriction_not_per_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§4.5's two bounds are not the same bound, and this pins which one the code meets —
    including against the memo that *looks* like it meets it and does not.

    Read literally, "one $O(|V|+|E|)$ BFS per finding" is quadratic in the input: a workflow
    whose nodes each read many unwritten keys has ``|V| · |Σ|`` findings and rebuilds the
    restricted graph for each. The bound the code meets instead is §4.5's other one, stated
    for this very algorithm: "|Σ| independent reachability problems, O(|Σ| · (|V|+|E|)) total".

    **The second half is the regression guard, and it is the case a naive memo gets wrong.**
    Keying the cache on ``W[k] ∖ {v}`` — the restriction as §4.4 Step 4 literally writes it —
    makes it depend on ``v`` as well as ``k`` for every reader that writes what it reads, so a
    graph of self-writing readers defeats it completely: one tree per finding again, and now
    *retained* for the whole of Step 4 rather than transient. Measured at 102 400 trees, 54 s
    and 2.8 GB on a 1.9 MB document before the fix (never-invokes pre-review, VAL-09). Keying
    on ``W[k]`` alone and applying the exemption at read-out makes the count independent of how
    many readers write what they read, which is what the third block asserts.

    Counted structurally rather than timed: a wall-clock assertion would be a flaky budget
    rather than the invariant.
    """
    keys = [f"key_{index}" for index in range(5)]
    readers = [f"r_{index}" for index in range(12)]
    writers = [f"w_{index}" for index in range(5)]
    built: list[frozenset[str]] = []
    original = dataflow_completeness._shortest_path_tree

    def counting(graph: GraphModel) -> dataflow_completeness._SearchTree:
        built.append(graph.vertex_set)
        return original(graph)

    monkeypatch.setattr(dataflow_completeness, "_shortest_path_tree", counting)

    def graph_of(reader_writes: dict[str, list[str]]) -> WorkflowIR:
        """Readers on a chain off a splitter; each key's sole writer on its own side branch,
        so every reader misses every key and the five writer sets are pairwise distinct."""
        nodes: dict[str, tuple[list[str], list[str]]] = {"split": ([], [])}
        nodes |= {name: ([], [keys[index]]) for index, name in enumerate(writers)}
        nodes |= {name: (keys, reader_writes.get(name, [])) for name in readers}
        return _ir(
            entry="split",
            finish=[*writers, readers[-1]],
            state=dict.fromkeys(keys, "str"),
            nodes=nodes,
            edges=[
                *({"from": "split", "to": name} for name in writers),
                {"from": "split", "to": readers[0]},
                *_chain(*readers),
            ],
        )

    failure = check_dataflow_completeness(graph_of({})).failure
    assert isinstance(failure, P04Failure)
    assert 1 + len(failure.co_failures or ()) == len(readers) * len(keys) == 60
    assert len(built) == len(keys) == 5

    # One self-writing reader: still one tree per key. Its own read of the key it writes is
    # still a finding — the `∖ {v}` exemption — and the path is read off the shared tree.
    built.clear()
    produced = check_dataflow_completeness(graph_of({readers[6]: [keys[0]]}))
    records = [produced.failure, *(produced.failure.co_failures or ())]  # type: ignore[union-attr]

    assert len(built) == len(keys) == 5
    assert any(
        (record.location.node, record.location.key) == (readers[6], keys[0]) for record in records
    )

    # The shape that defeated the `W[k] ∖ {v}` key entirely: every reader writes every key it
    # reads. The tree count must not move — the whole point of applying the exemption at
    # read-out. Under the old key this was one tree per finding.
    built.clear()
    check_dataflow_completeness(graph_of(dict.fromkeys(readers, keys)))

    assert len(built) == len(keys) == 5


# ── The shared model, and the degradation convention it is asked for ─────────────────────


def test_a_model_built_with_p01s_convention_is_refused() -> None:
    """§0.3 gives P-04 "carries the phantom vertex with an empty contract" and P-01 "drops
    dangling-target edges"; the two disagree on ill-formed input by design, so a caller that
    hands P-04 P-01's model gets a ``ValueError`` rather than a quietly different answer."""
    ir = _ir_of(MIXED_04)

    with pytest.raises(ValueError, match="carries the phantom vertex"):
        check_dataflow_completeness(ir, model=build_graph_model(ir))


def test_a_shared_model_on_clean_topology_changes_no_result() -> None:
    """The reason ``verify()`` may build one model and hand it round: on P-01-clean topology
    the two builds are equal values, so the convention is unobservable."""
    for relative in FIXTURES:
        ir = _ir_of(relative)
        shared = build_graph_model(ir, carry_unresolved_references=True)

        assert shared == build_graph_model(ir)
        assert check_dataflow_completeness(ir, model=shared) == check_dataflow_completeness(ir)


def test_the_validator_is_registered_and_reachable_through_dispatch() -> None:
    """Registration happens at import, and dispatch is what ``verify()`` will drive."""
    assert is_implemented(PROPERTY_SLUG)

    dispatched = run_property(PROPERTY_SLUG, _ir_of(FIXTURES[0]))
    assert isinstance(dispatched, PropertyReport)
    assert dispatched.property == PROPERTY_SLUG
    assert dispatched.result == "pass"


def test_the_public_surface_is_re_exported_from_the_package() -> None:
    """``check_dataflow_completeness`` reaches consumers as ``from gebra.verify import ...``,
    which is how the harness and ``verify()`` take it."""
    import gebra.verify as package

    for name in dataflow_completeness.__all__:
        assert getattr(package, name, None) is getattr(dataflow_completeness, name) or name in (
            "PROPERTY_SLUG",
            "READ_KEY_NEVER_WRITTEN_ON_PATH",
        )
    assert package.check_dataflow_completeness is check_dataflow_completeness
    assert "check_dataflow_completeness" in package.__all__


# ── §4.5's complexity claim, demonstrated rather than asserted ───────────────────────────


def _diamond_chain(links: int, *, writer_on_both: bool) -> WorkflowIR:
    """A chain of ``links`` diamonds — 2^links distinct START→sink simple paths.

    Each diamond splits to ``a_i``/``b_i`` and merges at ``join_{i+1}``. With
    ``writer_on_both`` the key is written on both arms of the first diamond and the sink's read
    is covered; with only one arm writing it, exactly one obligation is violated and the
    attribution path is the arm that skips the writer.
    """
    nodes: dict[str, tuple[list[str], list[str]]] = {"join_0": ([], [])}
    edges: list[dict[str, Any]] = []
    for index in range(links):
        left, right, following = f"a_{index}", f"b_{index}", f"join_{index + 1}"
        writes = ["carried"] if index == 0 else []
        nodes[left] = ([], writes)
        nodes[right] = ([], writes if writer_on_both else [])
        nodes[following] = ([], [])
        edges += [
            {"from": f"join_{index}", "to": left},
            {"from": f"join_{index}", "to": right},
            {"from": left, "to": following},
            {"from": right, "to": following},
        ]
    nodes[f"join_{links}"] = (["carried"], [])
    return _ir(
        entry="join_0",
        finish=f"join_{links}",
        state={"carried": "str"},
        nodes=nodes,
        edges=edges,
    )


@pytest.mark.parametrize("covered", (True, False), ids=("covered", "violated"))
def test_a_graph_with_two_to_the_sixty_paths_is_analysed_without_enumerating_them(
    covered: bool,
) -> None:
    """§4.5 bounds the fixpoint at ``O((|V|+|E|)·⌈|Σ|/w⌉)`` word-operations per pass, over
    ``≤ depth + 2`` passes — a *lattice* iteration, never a path enumeration.

    Sixty chained diamonds carry 2^60 distinct ``START``→sink simple paths over 181 nodes. An
    implementation that quantified over paths directly could not return at all; this returns
    the right verdict either way. It is not a timing budget and must not be read as a timing
    regression test — the claim is that the analysis terminates, which enumeration would not.
    """
    report = check_dataflow_completeness(_diamond_chain(60, writer_on_both=covered))

    assert report.result == ("pass" if covered else "fail")
    if not covered:
        failure = report.failure
        assert isinstance(failure, P04Failure)
        assert failure.location.path[:3] == ("START", "join_0", "b_0")
        assert failure.writers_on_other_paths == ("a_0",)


# ── WA-07 — never-invokes, on the import *and* the call leg ──────────────────────────────

#: VAL-06's list, unchanged: the execution substrate plus the HTTP and LLM clients whose
#: presence in the closure would mean a validator had grown a way to reach the network.
_FORBIDDEN = (
    "{'langgraph', 'langgraph_sdk', 'langchain', 'langchain_core', 'langchain_openai', "
    "'langchain_anthropic', 'langsmith', 'litellm', 'networkx', 'openai', "
    "'anthropic', 'httpx', 'requests', 'aiohttp', 'urllib3'}"
)


def _tripwire_script(probe: str = "") -> str:
    """The guarded child: patch, import, run P-04 over every corpus snapshot, report.

    ``probe`` arms the raiser; the tripwire and its negative controls share this one script so
    a control cannot drift onto a different raiser from the one the real test relies on.
    """
    return (
        "import glob, json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the dataflow path')\n"
        "def _trip(name):\n"
        "    def _raise(*a, **k):\n"
        "        attempts.append(name); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError(name + ' reached on the dataflow path')\n"
        "    return _raise\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip('getaddrinfo')\n"
        "socket.gethostbyname = _trip('gethostbyname')\n"
        "socket.create_connection = _trip('create_connection')\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify import check_dataflow_completeness\n"
        "seen = failed = 0\n"
        f"for path in sorted(glob.glob({str(FIXTURES_DIR)!r} + '/*/*.yaml')):\n"
        "    with open(path, encoding='utf-8') as handle:\n"
        "        document = yaml.safe_load(handle)\n"
        "    for key in ('ir', 'ir_before', 'ir_after'):\n"
        "        block = document.get(key)\n"
        "        if not block:\n"
        "            continue\n"
        "        ir = WorkflowIR.model_validate_json(json.dumps(block))\n"
        "        report = check_dataflow_completeness(ir)\n"
        "        failed += report.result == 'fail'\n"
        "        seen += 1\n"
        "assert (seen, failed) == (67, 9), (seen, failed)\n"
        f"{probe}"
        f"print([m for m in sys.modules if m.split('.')[0] in {_FORBIDDEN}] + attempts)\n"
    )


def test_running_p04_over_the_corpus_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the P-04 path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter, because another test in this session may have imported anything.
    Three claims, separately enforced: no execution-substrate or HTTP/LLM-client package enters
    the import closure; no socket is created and no name resolved, either while importing the
    module or while validating every IR snapshot in the vendored corpus; and a swallowed
    exception still fails the run, because every attempt is recorded before the raise and also
    announced on stderr. The child asserts its own counts (67 snapshots, 9 failing) so a glob
    that silently stopped matching would fail the tripwire rather than pass it vacuously.

    One residual, named rather than left implicit, the same one VAL-03/VAL-05/VAL-06 recorded:
    the package leg is a post-hoc ``sys.modules`` scan, not an import blocker.
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
    tripwire passing for the wrong reason. Arming it after the sweep has already run isolates
    the raiser: the green run above got that far too.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script(probe)],
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the expected result here, not an error
    )

    assert completed.returncode != 0, completed.stdout
    assert "WA07-TRIP" in completed.stderr, completed.stderr


def test_the_validator_contains_no_evaluation_primitive() -> None:
    """P-04 never reads a declared ``condition`` string, and it must never gain a way to.

    Every ``ast.Name`` in any context is collected, not only call targets, so an aliased
    ``_e = eval; _e(text)`` cannot slip past; the imports are pinned as an exact set, which is
    what closes ``ast.literal_eval`` (whose callee is an ``Attribute``, not a ``Name``).
    The attribute-name check is the second half and is deliberately an AST scan rather than a
    substring one: the fixture's builder snippet, a router's guard string and ``runtime`` are
    the three IR members §4.3 leaves out, and what matters is that the module never *accesses*
    them, not that their names never appear in a sentence about them.
    """
    source = Path(dataflow_completeness.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
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

    assert named.isdisjoint(
        {"eval", "exec", "compile", "literal_eval", "__import__", "getattr", "globals", "vars"}
    )
    assert imported == {"__future__", "collections", "dataclasses", "typing", "gebra"}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert attributes.isdisjoint({"condition", "source_snippet", "runtime"})


def test_the_module_reads_only_the_section_4_3_fields() -> None:
    """§4.3's "Fields read" list, enforced against the IR models rather than by inspection.

    A recording proxy over a validated ``WorkflowIR`` records every attribute the validator
    touches; the set is exactly ``entry``/``finish``/``state``/``nodes``/``edges`` plus the
    per-node and per-edge members those lead to. ``runtime`` is P-02's and is never read.
    """
    ir = _ir_of(MIXED_08)
    touched: set[str] = set()

    class _Recorder:
        def __init__(self, wrapped: Any) -> None:
            object.__setattr__(self, "_wrapped", wrapped)

        def __getattr__(self, name: str) -> Any:
            touched.add(name)
            return getattr(object.__getattribute__(self, "_wrapped"), name)

    check_dataflow_completeness(_Recorder(ir))  # type: ignore[arg-type]

    assert touched == {"entry", "finish", "state", "nodes", "edges"}
