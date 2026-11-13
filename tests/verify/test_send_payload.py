"""P-04 over ``Send`` payloads — DEC-37's payload arm (PROPERTY-CATALOG-SPEC §4.4 Steps 2 and 4).

LangGraph's ``Send(node, arg)`` invokes its target with ``arg`` as that node's input, and the
IR's ``send`` edge is a branch template that records neither ``arg``'s keys nor the fan-out's N
(IR-SPEC §2.4). DEC-37 (ratified 2026-10-28; PD-065) rules what P-04 says about a read performed
by the target of such an edge: along its **send arm** a payload reader's declared reads are
reads of the payload, which the IR does not carry — no obligation is raised and nothing is
decided, and the reader is named on the optional ``payload_readers`` member; over its **state
arm** (every other in-edge from ``Reach``) it is decided as any reachable reader is. Before the
ruling, the field record's payload-only key failed ``read-key-never-written-on-path`` — the
record the dossier's Gemini quickstart card carries — because the send target's reads were
decided against its sender's state.

What this module pins, in the card's own order:

* **The dossier shape** (box 1): the field record as hand-authored IR — a ``Send`` target
  reading a key that arrives in the payload and is written by no node — reaches the ruled
  outcome, a pass with the target named on ``payload_readers``; the undeclared payload read
  still surfaces on every surface of the report (no declaration carrier exists at G10 — DEC-37
  deferred option (a) — so every payload read is the undeclared case); and the hintless control
  (a ``Send`` router with no return hint extracts as ``conditional``) still fails as before,
  because the ruling reaches a fan-out extracted as ``kind: send`` only (DEC-37 §3.4, §5 row 10).
* **The three ruling fixtures as data** — DEC-37 §3.5's trio, vendored by class B during this
  card (PD-062 §3) and held here as literal data too, pinned to the vendored files so the two
  cannot drift.
* **The same-source shape** (box 4; PD-065 §9 item 5, the critique's probe S2): one source
  wired to the reader by a ``send`` edge *and* an ordinary edge puts it on both arms, so its
  state read is decided — read off the multigraph, never off merged pairs.
* **The loop shape** (box 5; DEC-37 §3.3, §4, §5 row 9; probes S1/S6): a loop re-entering a
  payload reader through its state arm fails at that reader with a walk-shaped path that visits
  it twice — the first visit the payload instance, the last the state-arm entry.
* **The arm form, cross-checked.** An independent reference implementation of §4.4 Steps 2 and
  4 written here from DEC-37 §3.1–§3.3 alone — arms read off ``ir.edges``/``entry``, the
  decision as A8 T5 at each state-arm predecessor — agrees with the validator obligation by
  obligation over the whole corpus, the hand-built shapes and generated send-bearing documents.

WA-07: nothing here executes a workflow, a node, a model or a network call. Every document is a
literal dictionary validated into the frozen IR models, or a vendored fixture read with
PyYAML's safe loader; generated documents come from :mod:`gebra.testing.strategies`, which
builds frozen values only.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable, Mapping
from itertools import pairwise
from typing import Any

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from gebra.ir import WorkflowIR
from gebra.ir.models import ConditionalEdge, DynamicEdge, NormalEdge, SendEdge
from gebra.report import TerminalOptions, render
from gebra.testing.strategies import workflow_irs
from gebra.verify import (
    DataflowLocation,
    DataflowWitness,
    P04Failure,
    PropertyReport,
    models_equivalent,
    to_data,
    validate_report,
    verify,
)
from gebra.verify.graph import START_VERTEX, build_graph_model, ledger_sort_key
from gebra.verify.properties import dataflow_completeness
from gebra.verify.properties.dataflow_completeness import (
    PROPERTY_SLUG,
    READ_KEY_NEVER_WRITTEN_ON_PATH,
    check_dataflow_completeness,
)
from tests.conftest import FIXTURES_DIR

# ── Building IR by hand (data only) ──────────────────────────────────────────────────────


def _ir(document: Mapping[str, Any]) -> WorkflowIR:
    """A literal document validated into the frozen models (JSON mode, IR-SPEC §2.5 note 4)."""
    return WorkflowIR.model_validate_json(json.dumps(document))


def _p04(document: Mapping[str, Any] | WorkflowIR) -> PropertyReport:
    ir = document if isinstance(document, WorkflowIR) else _ir(document)
    return check_dataflow_completeness(ir)


def _witness(report: PropertyReport) -> DataflowWitness:
    assert report.result == "pass", to_data(report)
    assert isinstance(report.witness, DataflowWitness)
    return report.witness


def _failure(report: PropertyReport) -> P04Failure:
    assert report.result == "fail", to_data(report)
    assert isinstance(report.failure, P04Failure)
    return report.failure


def _decided(report: PropertyReport) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """``(covered, violated)`` as (node, key) pairs, read off any P-04 report."""
    if report.witness is not None:
        assert isinstance(report.witness, DataflowWitness)
        return {(entry.node, entry.key) for entry in report.witness.coverage}, set()
    failure = _failure(report)
    locations = [failure.location, *(co.location for co in failure.co_failures or ())]
    violated = set()
    for location in locations:
        assert isinstance(location, DataflowLocation)
        violated.add((location.node, location.key))
    return set(), violated


def _payload_readers(report: PropertyReport) -> tuple[str, ...] | None:
    carrier = report.witness if report.witness is not None else report.failure
    assert isinstance(carrier, (DataflowWitness, P04Failure))
    return carrier.payload_readers


#: DEC-37 §5 row 1 — the dossier's field record (OSS-Adoption-Dossier §3.10) on hand-authored
#: IR: ``generate_query →send→ web_research → reflection``; ``web_research`` reads
#: ``search_query`` and ``id``; ``id`` is in Σ because every key of a node's input schema
#: becomes a channel, and no node writes it.
DOSSIER: dict[str, Any] = {
    "ir_version": "1.0",
    "entry": "generate_query",
    "finish": "reflection",
    "state": {
        "messages": {"type": "list", "optional": True},
        "search_query": "list",
        "id": "int",
        "web_research_result": {"type": "list", "reducer": "operator.add"},
    },
    "nodes": [
        {
            "id": "generate_query",
            "annotations": {"input": ["messages"], "output": ["search_query"]},
        },
        {
            "id": "web_research",
            "annotations": {"input": ["search_query", "id"], "output": ["web_research_result"]},
        },
        {"id": "reflection", "annotations": {"input": ["web_research_result"], "output": []}},
    ],
    "edges": [
        {"from": "generate_query", "to": "web_research", "kind": "send"},
        {"from": "web_research", "to": "reflection"},
    ],
}


def _hintless(document: Mapping[str, Any]) -> dict[str, Any]:
    """The same document with its ``send`` edge in the form a hintless ``Send`` router takes.

    INTROSPECTION-SPEC §6: "a ``Send`` fan-out with no return hint extracts as
    ``conditional``" — one label per declared target, so the target has no send arm.
    """
    rewritten: dict[str, Any] = json.loads(json.dumps(document))
    rewritten["edges"] = [
        {"from": edge["from"], "kind": "conditional", "path_map": {edge["to"]: edge["to"]}}
        if edge.get("kind") == "send"
        else edge
        for edge in rewritten["edges"]
    ]
    return rewritten


def _travel(
    edges: list[dict[str, Any]],
    *,
    reads: Mapping[str, list[str]] | None = None,
    writes: Mapping[str, list[str]] | None = None,
    entry: str | list[str] = "plan_legs",
    finish: str | list[str] = "confirm_itinerary",
) -> dict[str, Any]:
    """The probe shapes of PD-065's critique, in DEC-37's travel domain.

    Every node any edge names is declared; ``book_leg`` reads ``search_plan`` and the
    payload-only ``leg_id`` unless ``reads`` says otherwise, and nothing writes ``leg_id``
    unless ``writes`` does.
    """
    contracts: dict[str, tuple[list[str], list[str]]] = {
        "plan_legs": (["request"], ["search_plan"]),
        "review_plan": (["search_plan"], []),
        "book_leg": (["search_plan", "leg_id"], ["bookings"]),
        "retry_check": (["bookings"], []),
        "confirm_itinerary": (["bookings", "request"], ["itinerary"]),
    }
    for node, value in (reads or {}).items():
        contracts[node] = (value, contracts[node][1])
    for node, value in (writes or {}).items():
        contracts[node] = (contracts[node][0], value)
    named = {entry} if isinstance(entry, str) else set(entry)
    named |= {finish} if isinstance(finish, str) else set(finish)
    for edge in edges:
        named.add(edge["from"])
        if "to" in edge:
            named.add(edge["to"])
        named |= set(edge.get("path_map", {}).values()) - {"END"}
    return {
        "ir_version": "1.0",
        "entry": entry,
        "finish": finish,
        "state": {
            "request": {"type": "str", "optional": True},
            "search_plan": "str",
            "leg_id": "str",
            "bookings": {"type": "list", "reducer": "operator.add"},
            "itinerary": "str",
        },
        "nodes": [
            {"id": node, "annotations": {"input": node_reads, "output": node_writes}}
            for node, (node_reads, node_writes) in contracts.items()
            if node in named
        ],
        "edges": edges,
    }


# ── Box 1: the dossier shape, the undeclared read surfacing, the hintless control ────────


def test_the_dossier_shape_passes_with_its_send_target_named_on_payload_readers() -> None:
    """DEC-37 §3.1/§3.2 on the field record: a pass, never the pre-DEC-37 failure.

    ``web_research`` is a send-only target, so every read it declares arrives in the payload:
    no obligation is raised for ``search_query`` or ``id``, no coverage entry claims either is
    covered, and the reader is named on ``payload_readers`` — neither silence nor a verdict.
    The two state readers are decided as before: ``generate_query`` reads a graph input and
    ``reflection`` reads what the send target writes, which reaches it through the fixpoint
    (§4.4 Step 3 is unchanged — a ``send`` target's writes land in the graph state).
    """
    witness = _witness(_p04(DOSSIER))

    assert witness.payload_readers == ("web_research",)
    assert {(entry.node, entry.key) for entry in witness.coverage} == {
        ("generate_query", "messages"),
        ("reflection", "web_research_result"),
    }
    covered = {(entry.node, entry.key): entry.satisfied_by for entry in witness.coverage}
    assert covered[("reflection", "web_research_result")] == ("web_research",)
    assert covered[("generate_query", "messages")] == ("START",)
    assert witness.outside_static_coverage is None and witness.contained_readers is None


def test_the_undeclared_payload_read_still_surfaces_on_the_native_and_human_reports() -> None:
    """The undeclared payload read is never a silent pass (DEC-37 §1; DEC-28 clause 2's rule).

    No carrier for declared payload keys exists at G10 — DEC-37 deferred option (a) to an IR
    carrier — so the field record's ``id`` is the undeclared case, and what keeps it visible is
    the member: on the native JSON (the witness serialized), on the human profile (an evidence
    line naming the reader and saying its reads were not decided), and through ``verify()``,
    whose gate passes with the member on P-04's outcome. A pass witness has no SARIF home
    (REPORT-FORMAT-SPEC A.1 loss 1); on a failure the member rides the SARIF property bag, which
    ``tests/report/test_findings.py`` pins.
    """
    report = verify(_ir(DOSSIER))
    outcome = report.outcome_for(PROPERTY_SLUG)

    assert report.gate.exit_code == 0
    assert isinstance(outcome, PropertyReport)
    assert _payload_readers(outcome) == ("web_research",)
    native = json.loads(render(report, "json"))
    (wire,) = [entry for entry in native["properties"] if entry["property"] == PROPERTY_SLUG]
    assert wire["witness"]["payload_readers"] == ["web_research"]
    # The human profile wraps long values at the terminal width; read it whitespace-folded.
    human = " ".join(render(report, "human", terminal=TerminalOptions(color=False)).split())
    lead = "payload readers 1 reachable node entered through a send edge"
    assert human.count(lead) == 1
    line = human.split(lead)[1]
    assert "none was decided" in line.split("P-05")[0]
    assert "web_research" in line.split("P-05")[0]
    assert "web_research reads" not in human  # no coverage line claims its reads


def test_the_hintless_control_is_not_reached_and_fails_as_the_field_record_did() -> None:
    """DEC-37 §3.4 and §5 row 10: the ruling reaches a fan-out extracted as ``kind: send`` only.

    A ``Send`` router with no return hint extracts as a label-expanded ``conditional`` edge
    (INTROSPECTION-SPEC §6), so its target has no send arm and is decided as a state reader —
    the field record's finding, unchanged: ``id`` at ``web_research`` on ``START →
    generate_query → web_research``, with no ``payload_readers`` at all. The adopter's remedy
    is the true declaration, a ``-> list[Send]`` hint on the router (DOC-22).
    """
    report = _p04(_hintless(DOSSIER))
    failure = _failure(report)

    assert failure.property_condition == READ_KEY_NEVER_WRITTEN_ON_PATH
    assert (failure.location.node, failure.location.key) == ("web_research", "id")
    assert failure.location.path == ("START", "generate_query", "web_research")
    assert failure.payload_readers is None
    assert failure.co_failures is None


# ── DEC-37 §3.5's trio, as data (vendored by class B, pinned to the corpus files) ────────

#: ``positive-05-send-template-payload-reader`` — the field shape in the travel domain.
_POSITIVE_05: dict[str, Any] = {
    "ir": {
        "ir_version": "1.0",
        "entry": "plan_legs",
        "finish": "confirm_itinerary",
        "state": {
            "request": {"type": "str", "optional": True},
            "search_plan": "str",
            "leg_id": "str",
            "bookings": {"type": "list", "reducer": "operator.add"},
            "itinerary": "str",
        },
        "nodes": [
            {
                "id": "plan_legs",
                "annotations": {"pure": True, "input": ["request"], "output": ["search_plan"]},
            },
            {
                "id": "book_leg",
                "annotations": {
                    "effect": ["network"],
                    "idempotent": {"key": "leg_id"},
                    "input": ["search_plan", "leg_id"],
                    "output": ["bookings"],
                },
            },
            {
                "id": "confirm_itinerary",
                "annotations": {
                    "pure": True,
                    "input": ["bookings", "request"],
                    "output": ["itinerary"],
                },
            },
        ],
        "edges": [
            {"from": "plan_legs", "to": "book_leg", "kind": "send"},
            {"from": "book_leg", "to": "confirm_itinerary"},
        ],
    },
    "expected": {
        "result": "pass",
        "witness": {
            "kind": "dataflow",
            "coverage": [
                {"node": "confirm_itinerary", "key": "bookings", "satisfied_by": ["book_leg"]},
                {"node": "confirm_itinerary", "key": "request", "satisfied_by": ["START"]},
                {"node": "plan_legs", "key": "request", "satisfied_by": ["START"]},
            ],
            "payload_readers": ["book_leg"],
        },
    },
}


def _negative_05() -> dict[str, Any]:
    """``negative-05-payload-key-read-from-state-downstream`` — a payload key is no state write."""
    document: dict[str, Any] = json.loads(json.dumps(_POSITIVE_05))
    document["ir"]["nodes"][2]["annotations"]["input"] = ["bookings", "leg_id", "request"]
    document["expected"] = {
        "result": "fail",
        "failure": {
            "property_condition": READ_KEY_NEVER_WRITTEN_ON_PATH,
            "location": {
                "kind": "state-key",
                "node": "confirm_itinerary",
                "key": "leg_id",
                "path": ["START", "plan_legs", "book_leg", "confirm_itinerary"],
            },
            "severity": "fatal",
            "claim_class": "defensible-a",
            "payload_readers": ["book_leg"],
        },
    }
    return document


def _negative_06() -> dict[str, Any]:
    """``negative-06-mixed-arm-reader-state-arm-unwritten`` — the arm-aware document."""
    document: dict[str, Any] = json.loads(json.dumps(_POSITIVE_05))
    document["ir"]["nodes"].insert(
        1,
        {
            "id": "review_plan",
            "annotations": {"pure": True, "input": ["search_plan"], "output": []},
        },
    )
    document["ir"]["edges"] = [
        {"from": "plan_legs", "to": "book_leg", "kind": "send"},
        {"from": "plan_legs", "to": "review_plan"},
        {"from": "review_plan", "to": "book_leg"},
        {"from": "book_leg", "to": "confirm_itinerary"},
    ]
    document["expected"] = {
        "result": "fail",
        "failure": {
            "property_condition": READ_KEY_NEVER_WRITTEN_ON_PATH,
            "location": {
                "kind": "state-key",
                "node": "book_leg",
                "key": "leg_id",
                "path": ["START", "plan_legs", "review_plan", "book_leg"],
            },
            "severity": "fatal",
            "claim_class": "defensible-a",
            "payload_readers": ["book_leg"],
        },
    }
    return document


TRIO: dict[str, dict[str, Any]] = {
    "positive-05": _POSITIVE_05,
    "negative-05": _negative_05(),
    "negative-06": _negative_06(),
}


@pytest.mark.parametrize("name", sorted(TRIO))
def test_the_ruling_trio_reproduces_its_expected_blocks(name: str) -> None:
    """DEC-37 §3.5: each document held to its own expected block by model equality.

    These are the class-B fixtures VAL-D8 staged, vendored into the corpus during this card
    (PD-062 §3), where the golden harness holds them too. The literal copies keep each shape
    beside the tests that read it, and the next test pins them to the vendored files.
    """
    document = TRIO[name]
    produced = _p04(document["ir"])
    expected = validate_report({"property": PROPERTY_SLUG, **document["expected"]})

    assert models_equivalent(produced, expected), to_data(produced)


#: The trio's vendored files, under the corpus's ``dataflow-completeness/`` directory.
_TRIO_FILES: dict[str, str] = {
    "positive-05": "positive-05-send-template-payload-reader.yaml",
    "negative-05": "negative-05-payload-key-read-from-state-downstream.yaml",
    "negative-06": "negative-06-mixed-arm-reader-state-arm-unwritten.yaml",
}


@pytest.mark.parametrize("name", sorted(TRIO))
def test_the_literal_trio_is_the_vendored_trio(name: str) -> None:
    """Each literal copy above is its vendored fixture's ``ir`` and ``expected`` blocks, exactly.

    Read with PyYAML's safe loader and compared as data, so an edit to a copy here, or a
    re-vendor that moved a block, fails by name rather than leaving two versions of one ruling.
    """
    path = FIXTURES_DIR / "dataflow-completeness" / _TRIO_FILES[name]
    vendored = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert {"ir": vendored["ir"], "expected": vendored["expected"]} == TRIO[name]


def test_negative_05_carries_one_finding_where_the_whole_node_reading_carried_two() -> None:
    """DEC-37 §3.5 item 2: the payload read is abstained, so the one finding is the state read.

    The send arm's abstention adds no writer: ``leg_id`` delivered in ``book_leg``'s payload is
    not written to state, so ``confirm_itinerary``'s state read of it fails on the one path,
    with no co-failure and neither DEC-11 diagnostic (nothing writes the key anywhere).
    """
    failure = _failure(_p04(TRIO["negative-05"]["ir"]))

    assert failure.co_failures is None
    assert failure.writers_on_other_paths is None and failure.downstream_writers is None


def test_negative_06_is_failed_on_the_state_arm_path_never_the_send_arm() -> None:
    """DEC-37 §3.3: the offending path ends on a state-arm edge.

    The shorter route ``START → plan_legs → book_leg`` runs through the send edge, along which
    ``book_leg`` reads its payload, so it is not an offending path; the one through
    ``review_plan`` is. ``search_plan`` is covered on the state arm, which is why the report
    carries one finding. The whole-node skip DEC-37 §2 rejects would pass this document.
    """
    failure = _failure(_p04(TRIO["negative-06"]["ir"]))

    assert failure.location.path[-2:] == ("review_plan", "book_leg")
    assert failure.co_failures is None


# ── Box 4: the same-source shape (PD-065 §9 item 5; probe S2; DEC-37 §5 row 8) ───────────


def test_a_source_wired_by_send_and_by_an_ordinary_edge_puts_the_reader_on_both_arms() -> None:
    """One source, two wirings: ``plan_legs →send→ book_leg`` and ``plan_legs → book_leg``.

    The model is a multigraph (ledger §4): the two authored edges are two in-edges with their
    own kinds, so ``book_leg`` has a non-empty send arm *and* a non-empty state arm, and its
    state read of the unwritten ``leg_id`` is decided — a failure at ``book_leg``, never the
    silent pass the first-staged ``E(G) ∖ send_arm`` reading gave over merged pairs (the
    critique's probe S2). The reader is still named for its send arm.
    """
    document = _travel(
        [
            {"from": "plan_legs", "to": "book_leg", "kind": "send"},
            {"from": "plan_legs", "to": "book_leg"},
        ],
        finish="book_leg",
    )
    failure = _failure(_p04(document))

    assert failure.property_condition == READ_KEY_NEVER_WRITTEN_ON_PATH
    assert (failure.location.node, failure.location.key) == ("book_leg", "leg_id")
    assert failure.location.path == ("START", "plan_legs", "book_leg")
    assert failure.payload_readers == ("book_leg",)
    assert failure.co_failures is None  # search_plan is covered on the state arm


def test_the_same_source_obligation_comes_from_the_ordinary_edge_alone() -> None:
    """The control for the test above: drop the ordinary edge and the document passes.

    With the ``send`` edge alone ``book_leg`` is a send-only target and raises no obligation,
    so the finding above is the ordinary edge's — the state arm the merged-pair reading lost.
    And the model the validator reads keeps both in-edges, each with its kind.
    """
    both = _travel(
        [
            {"from": "plan_legs", "to": "book_leg", "kind": "send"},
            {"from": "plan_legs", "to": "book_leg"},
        ],
        finish="book_leg",
    )
    send_only = _travel(
        [{"from": "plan_legs", "to": "book_leg", "kind": "send"}], finish="book_leg"
    )

    assert _witness(_p04(send_only)).payload_readers == ("book_leg",)
    in_edges = build_graph_model(_ir(both), carry_unresolved_references=True).in_edges("book_leg")
    assert sorted((edge.source, edge.kind) for edge in in_edges) == [
        ("plan_legs", "normal"),
        ("plan_legs", "send"),
    ]


# ── Box 5: the loop shape (DEC-37 §3.3, §4, §5 row 9; probes S1/S6) ──────────────────────

#: ``plan_legs →send→ book_leg → retry_check``, ``retry_check →conditional→ book_leg``.
_LOOP_EDGES: list[dict[str, Any]] = [
    {"from": "plan_legs", "to": "book_leg", "kind": "send"},
    {"from": "book_leg", "to": "retry_check"},
    {
        "from": "retry_check",
        "kind": "conditional",
        "path_map": {"retry": "book_leg", "done": "END"},
    },
]


def test_a_loop_re_entering_a_payload_reader_fails_it_with_a_walk_that_visits_it_twice() -> None:
    """DEC-37 §3.3: the offending path on a state-arm re-entry is a walk.

    Nothing writes ``leg_id``. ``book_leg`` is entered by the ``send`` edge (its payload
    instance) and re-entered by ``retry_check``'s ``retry`` label (its state arm). When the
    reader does not write the key the search graph keeps it, so the shortest ``START → u`` route
    to the state-arm predecessor ``retry_check`` runs through ``book_leg`` itself, and the
    emitted path visits it twice — the first visit the payload instance, the last the state-arm
    entry. That is the execution the finding describes, and ``DataflowLocation.path`` admits it.
    """
    failure = _failure(_p04(_travel(_LOOP_EDGES, finish="book_leg")))

    path = ("START", "plan_legs", "book_leg", "retry_check", "book_leg")
    assert (failure.location.node, failure.location.key) == ("book_leg", "leg_id")
    assert failure.location.path == path
    assert failure.location.path.count("book_leg") == 2
    assert failure.payload_readers == ("book_leg",)
    location = DataflowLocation(kind="state-key", key="leg_id", node="book_leg", path=path)
    assert location.path == path


def test_the_walk_enters_by_the_send_arm_first_and_by_the_state_arm_last() -> None:
    """The two visits are the two arms: the first in-edge is the ``send`` template, the last a
    ``path_map`` label — so the finding's last edge is a state-arm edge, never the send arm."""
    ir = _ir(_travel(_LOOP_EDGES, finish="book_leg"))
    path = _failure(_p04(ir)).location.path
    kinds = {
        (edge.source, edge.target): edge.kind
        for vertex in ("book_leg", "retry_check")
        for edge in build_graph_model(ir).in_edges(vertex)
    }

    assert kinds[("plan_legs", "book_leg")] == "send"
    assert kinds[(path[-2], path[-1])] == "conditional"


def test_a_self_loop_re_entry_is_the_same_walk_one_hop_shorter() -> None:
    """Probe S6's shape: the reader re-enters itself through its own router's label."""
    edges: list[dict[str, Any]] = [
        {"from": "plan_legs", "to": "book_leg", "kind": "send"},
        {
            "from": "book_leg",
            "kind": "conditional",
            "path_map": {"again": "book_leg", "done": "END"},
        },
    ]
    failure = _failure(_p04(_travel(edges, finish="book_leg")))

    assert failure.location.path == ("START", "plan_legs", "book_leg", "book_leg")
    assert failure.payload_readers == ("book_leg",)


def test_a_self_writing_payload_reader_on_a_loop_is_covered_by_its_own_earlier_visit() -> None:
    """The critique's probe S5: first-arrival holds, because the first state-arm arrival follows
    the payload instance — which wrote the key.

    ``book_leg`` writes ``leg_id`` here. Every state-arm arrival comes through ``retry_check``,
    after a ``book_leg`` visit, so ``leg_id`` is in ``IN_state`` and the read is covered.
    §4.4 Step 4's ``upstream`` excludes the reader itself (``W[k] ∖ {v, START}``) and the key
    is not a graph input, so ``satisfied_by`` is empty: the record names no writer other than
    the reader, which is exactly what §4.4 computes.
    """
    document = _travel(_LOOP_EDGES, finish="book_leg", writes={"book_leg": ["bookings", "leg_id"]})
    witness = _witness(_p04(document))
    covered = {(entry.node, entry.key): entry.satisfied_by for entry in witness.coverage}

    assert covered[("book_leg", "leg_id")] == ()
    assert covered[("book_leg", "search_plan")] == ("plan_legs",)
    assert witness.payload_readers == ("book_leg",)


def test_the_human_profile_spells_an_empty_cover_as_what_it_is() -> None:
    """The coverage line for the shape above names no writer, and says why rather than "covered
    by (nothing)": §4.4 lists no writer other than the reader itself, so the line says that."""
    document = _travel(_LOOP_EDGES, finish="book_leg", writes={"book_leg": ["bookings", "leg_id"]})
    human = " ".join(render(verify(_ir(document)), "human").split())

    assert (
        "book_leg reads leg_id <- covered, with no writer other than the reader itself upstream "
        "of it"
    ) in human
    assert "(nothing)" not in human


def test_a_writer_on_the_loop_covers_the_state_arm_and_is_named_upstream_through_it() -> None:
    """The arm-form attribution: ``retry_check`` writes ``leg_id`` and is the state-arm source,
    so it covers the re-entry and is ``satisfied_by`` "upstream through the state arm" — even
    though it is not upstream of the send arm's instance."""
    document = _travel(_LOOP_EDGES, finish="book_leg", writes={"retry_check": ["leg_id"]})
    witness = _witness(_p04(document))
    covered = {(entry.node, entry.key): entry.satisfied_by for entry in witness.coverage}

    assert covered[("book_leg", "leg_id")] == ("retry_check",)


# ── The §4.7 edge-case rows DEC-37 added ─────────────────────────────────────────────────


def test_a_send_target_also_listed_in_entry_is_decided_over_the_start_wiring() -> None:
    """The critique's probe S4: the ``entry`` wiring is a state-arm edge (IR-SPEC §4.2 (m1)),
    so the reader is decided over it — the one-step path ``START → book_leg``."""
    document = _travel(
        [{"from": "plan_legs", "to": "book_leg", "kind": "send"}],
        entry=["book_leg", "plan_legs"],
        finish="book_leg",
    )
    failure = _failure(_p04(document))

    assert (failure.location.node, failure.location.key) == ("book_leg", "leg_id")
    assert failure.location.path == ("START", "book_leg")
    assert failure.payload_readers == ("book_leg",)


def test_a_send_edge_from_an_unreachable_source_is_no_arm() -> None:
    """§4.4 Step 2 keeps only sources in ``Reach``: a ``send`` edge out of a node no ``START``-
    path reaches delivers nothing on any path, so its target is decided as a state reader and
    is not a payload reader. (The unreachable node itself is P-01's finding.)"""
    document = _travel(
        [
            {"from": "plan_legs", "to": "book_leg"},
            {"from": "review_plan", "to": "book_leg", "kind": "send"},
        ],
        finish="book_leg",
        reads={"book_leg": ["search_plan"]},
    )
    witness = _witness(_p04(document))

    assert witness.payload_readers is None
    assert ("book_leg", "search_plan") in {(entry.node, entry.key) for entry in witness.coverage}


def test_a_send_edge_whose_target_resolves_to_no_node_names_no_payload_reader() -> None:
    """§4.7: a carried phantom has an empty contract and is never a member of $V$ (DEC-26), so
    it is never a payload reader. (A single-property run on P-01-dirty topology is outside the
    defined result surface — §0.3 — and this asserts only the member's domain.)"""
    document = _travel(
        [{"from": "plan_legs", "to": "ghost", "kind": "send"}],
        finish="plan_legs",
    )
    witness = _witness(_p04(document))

    assert witness.payload_readers is None


def test_a_payload_readers_read_outside_sigma_is_still_listed() -> None:
    """DEC-37 §3.2: "declared reads" is ``annotations.input`` as declared, Σ-membership aside —
    a payload reader's read of a key outside Σ is P-03's finding, and the reader is listed."""
    document = _travel(
        [{"from": "plan_legs", "to": "book_leg", "kind": "send"}],
        finish="book_leg",
        reads={"book_leg": ["not_a_state_key"]},
    )
    witness = _witness(_p04(document))

    assert witness.payload_readers == ("book_leg",)


def test_a_send_target_with_no_declared_read_is_not_a_payload_reader() -> None:
    """§4.4 Step 2: ``reads(v) ≠ ∅`` — a target that declares no read has nothing to abstain on."""
    document = _travel(
        [{"from": "plan_legs", "to": "book_leg", "kind": "send"}],
        finish="book_leg",
        reads={"book_leg": []},
    )

    assert _witness(_p04(document)).payload_readers is None


def test_the_three_coverage_cost_diagnostics_are_disjoint_on_one_document() -> None:
    """DEC-37 §3.2: ``payload_readers`` quantifies inside ``Reach`` and the two siblings outside
    it, so on a document carrying all three — a reachable ``dynamic`` router, a contained reader
    no static path reaches, and a send target — each names its own reader and none is shared."""
    document: dict[str, Any] = {
        "ir_version": "1.1",
        "entry": "plan",
        "finish": ["worker", "late"],
        "state": {"k": "str", "seed": {"type": "str", "optional": True}},
        "nodes": [
            {"id": "plan", "annotations": {"input": ["seed"], "output": []}},
            {"id": "plan/x", "annotations": {"input": ["k"], "output": []}},
            {"id": "worker", "annotations": {"input": ["k"], "output": []}},
            {"id": "late", "annotations": {"input": ["k"], "output": []}},
        ],
        "edges": [
            {"from": "plan", "kind": "dynamic"},
            {"from": "plan", "to": "worker", "kind": "send"},
        ],
    }
    witness = _witness(_p04(document))

    assert witness.outside_static_coverage == ("late",)
    assert witness.contained_readers == ("plan/x",)
    assert witness.payload_readers == ("worker",)


def test_on_a_failure_the_member_rides_the_primary_alone() -> None:
    """PD-057 D2: the primary ``P04Failure`` is the one carrier a failing report has; a
    co-failure is a plain ``CoFailure`` and admits no extras."""
    document = _travel(
        [
            {"from": "plan_legs", "to": "book_leg", "kind": "send"},
            {"from": "book_leg", "to": "confirm_itinerary"},
        ],
        reads={"confirm_itinerary": ["leg_id", "itinerary"]},
    )
    failure = _failure(_p04(document))

    assert failure.payload_readers == ("book_leg",)
    assert failure.co_failures is not None
    for co_failure in failure.co_failures:
        assert "payload_readers" not in to_data(co_failure)


def test_no_document_without_a_send_edge_carries_the_member() -> None:
    """Present iff non-empty (DEC-11 discipline): every corpus document with no ``send`` edge
    serializes without it, which is how every existing expected block stays byte-identical."""
    checked = 0
    for identity, ir in _corpus_irs():
        if any(isinstance(edge, SendEdge) for edge in ir.edges):
            continue
        checked += 1
        assert "payload_readers" not in json.dumps(to_data(_p04(ir))), identity
    assert checked


def test_the_two_send_bearing_documents_outside_p04s_directory_keep_their_p04_pass() -> None:
    """DEC-37 §3.4 and §5 row 4: ``mixed/09`` and ``parallel-safety/negative-02`` carry the
    corpus's ``send`` edges outside the P-04 directory, and no P-04 expected block. Each still
    passes P-04; each send target is a send-only reader, so its read is abstained — named on
    ``payload_readers`` — and no coverage entry claims it. (Measured against the pre-DEC-37
    module, each also lost the one coverage entry its send target's read had held; DEC-37
    §3.4's "gain only the member" leaves that out.)"""
    expected = {
        "mixed/09-send-fanout-billable-no-idempotency-in-retry:ir": "book_segment",
        "parallel-safety/negative-02-send-fanout-reducerless-findings:ir": "research_destination",
    }
    found = {}
    for identity, ir in _corpus_irs():
        if identity.startswith("dataflow-completeness/"):
            continue  # DEC-37's own trio, held to its expected blocks wherever it is vendored
        if any(isinstance(edge, SendEdge) for edge in ir.edges):
            witness = _witness(_p04(ir))
            found[identity] = witness.payload_readers
            reader = expected[identity]
            assert reader not in {entry.node for entry in witness.coverage}
    assert found == {identity: (reader,) for identity, reader in expected.items()}


# ── The arm form, cross-checked by an independent reference implementation ───────────────


def _corpus_irs() -> list[tuple[str, WorkflowIR]]:
    """Every IR snapshot in the vendored corpus, both members of each evolution pair."""
    found: list[tuple[str, WorkflowIR]] = []
    for path in sorted(FIXTURES_DIR.glob("*/*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if block:
                found.append((f"{path.parent.name}/{path.stem}:{key}", _ir(block)))
    return found


class _Reference:
    """§4.4 Steps 2 and 4 in arm form, written here from DEC-37 §3.1–§3.3 alone.

    Deliberately independent of the validator and of the shared graph model: the label-expanded
    edge list, ``Reach``, both arms and every reachability question are re-derived from
    ``ir.edges``/``ir.entry`` as DEC-37 §3.1 says the arms are read ("off ``ir.edges`` and
    ``entry``"), and each obligation is decided as A8 T5 at a state-arm predecessor: $(v, k)$ is
    violated iff some state-arm source $u$ is not a writer of $k$ and ``START`` reaches $u$
    avoiding every writer of $k$ — which, with no send arm, is the classic T5 statement at $v$.
    Phantoms are carried with an empty contract, as P-04's §0.3 degradation convention has it.
    """

    def __init__(self, ir: WorkflowIR) -> None:
        self.nodes = {node.id for node in ir.nodes}
        self.reads: dict[str, set[str]] = {}
        self.writes: dict[str, set[str]] = {}
        for node in ir.nodes:
            annotations = node.annotations
            self.reads[node.id] = set(annotations.input or ()) if annotations else set()
            self.writes[node.id] = set(annotations.output or ()) if annotations else set()
        state = ir.state or {}
        self.sigma = set(state)
        self.boundary = {
            key for key, field in state.items() if not isinstance(field, str) and field.optional
        }
        # (source, target, arm) — one entry per authored wiring, labels expanded.
        self.edges: list[tuple[str, str, str]] = []
        entries = (ir.entry,) if isinstance(ir.entry, str) else ir.entry
        self.edges.extend((START_VERTEX, entry, "state") for entry in entries)
        for edge in ir.edges:
            if isinstance(edge, DynamicEdge):
                continue
            if isinstance(edge, ConditionalEdge):
                for target in edge.path_map.values():
                    self.edges.append(
                        (edge.from_, "__end__" if target == "END" else target, "state")
                    )
            elif isinstance(edge, SendEdge):
                self.edges.append((edge.from_, edge.to, "send"))
            else:
                assert isinstance(edge, NormalEdge)
                self.edges.append((edge.from_, edge.to, "state"))
        mentioned = {tail for tail, _, _ in self.edges} | {head for _, head, _ in self.edges}
        self.phantoms = mentioned - self.nodes - {START_VERTEX, "__end__"}
        self.reach = self._closure(START_VERTEX, frozenset())

    def _closure(self, source: str, removed: frozenset[str]) -> frozenset[str]:
        """Every vertex reachable from ``source`` without entering ``removed`` (source kept)."""
        if source in removed:
            return frozenset()
        seen = {source}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for tail, head, _ in self.edges:
                if tail == current and head not in seen and head not in removed:
                    seen.add(head)
                    queue.append(head)
        return frozenset(seen)

    def arms(self, vertex: str) -> tuple[set[str], set[str]]:
        send = {t for t, h, arm in self.edges if h == vertex and arm == "send" and t in self.reach}
        state = {
            t for t, h, arm in self.edges if h == vertex and arm == "state" and t in self.reach
        }
        return send, state

    def writers(self, key: str) -> frozenset[str]:
        found = {node for node, keys in self.writes.items() if key in keys}
        return frozenset(found | ({START_VERTEX} if key in self.boundary else set()))

    def payload_readers(self) -> tuple[str, ...]:
        readers = [v for v in self.nodes if v in self.reach and self.reads[v] and self.arms(v)[0]]
        return tuple(sorted(readers, key=ledger_sort_key))

    def decide(self) -> tuple[dict[tuple[str, str], set[str]], set[tuple[str, str]]]:
        """``(covered → expected satisfied_by, violated)`` over every decided obligation."""
        covered: dict[tuple[str, str], set[str]] = {}
        violated: set[tuple[str, str]] = set()
        for vertex in self.nodes & self.reach:
            send, state = self.arms(vertex)
            if send and not state:
                continue  # a send-only target: every read is a payload read
            for key in self.reads[vertex] & self.sigma:
                writers = self.writers(key)
                reached = self._closure(START_VERTEX, writers)
                if any(source not in writers and source in reached for source in state):
                    violated.add((vertex, key))
                    continue
                upstream = {
                    writer
                    for writer in writers - {vertex, START_VERTEX}
                    if writer in self.reach
                    and any(
                        source == writer or source in self._closure(writer, frozenset())
                        for source in state
                    )
                }
                covered[(vertex, key)] = upstream | ({"START"} if key in self.boundary else set())
        return covered, violated

    def shortest_offending_length(self, vertex: str, key: str) -> int:
        """Vertices on the shortest ``START → u → v`` route with ``u`` on the state arm."""
        writers = self.writers(key)
        _, state = self.arms(vertex)
        best: int | None = None
        for source in state - writers:
            depth = self._depth(source, writers)
            if depth is not None and (best is None or depth + 1 < best):
                best = depth + 1
        assert best is not None
        return best

    def _depth(self, target: str, removed: frozenset[str]) -> int | None:
        if START_VERTEX in removed:
            return None
        depth = {START_VERTEX: 1}
        queue = deque([START_VERTEX])
        while queue:
            current = queue.popleft()
            if current == target:
                return depth[current]
            for tail, head, _ in self.edges:
                if tail == current and head not in depth and head not in removed:
                    depth[head] = depth[current] + 1
                    queue.append(head)
        return None


def _assert_agrees_with_the_reference(ir: WorkflowIR, identity: str = "") -> None:
    """The validator and :class:`_Reference` decide every obligation alike.

    Two views, because a report shows only one side: a pass carries its covered obligations
    (``coverage``) and a failure its violated ones (§0.3 gives a report exactly one of witness
    and failure). So every decision is first compared on Step 4's own output — the coverage
    entries *and* the findings, whatever the verdict, with each ``satisfied_by`` set and a real
    state-arm route for every finding — and then the report itself is held to the same answer.
    """
    reference = _Reference(ir)
    expected_covered, expected_violated = reference.decide()
    coverage, findings = _step_four(ir)

    assert {(entry.node, entry.key) for entry in coverage} == set(expected_covered), identity
    assert {(f.location.node, f.location.key) for f in findings} == expected_violated, identity
    for entry in coverage:
        assert set(entry.satisfied_by) == expected_covered[(entry.node, entry.key)], identity
    for finding in findings:
        _assert_a_real_state_arm_route(reference, finding.location, identity)

    report = _p04(ir)
    covered, violated = _decided(report)
    assert _payload_readers(report) == (reference.payload_readers() or None), identity
    assert report.result == ("fail" if expected_violated else "pass"), identity
    if report.witness is not None:
        assert covered == set(expected_covered), identity
        _assert_decided_or_abstained(reference, report, identity)
    else:
        assert violated == expected_violated, identity


def _step_four(ir: WorkflowIR) -> tuple[list[Any], list[Any]]:
    """§4.4 Step 4's coverage entries and findings, both, whatever the verdict.

    Read off the module's own Step 2–4 functions, the way ``test_dataflow_completeness.py``
    reads its fixpoint, because the public report shows one side of the decision only.
    """
    graph = build_graph_model(ir, carry_unresolved_references=True)
    contracts = dataflow_completeness._contracts(ir, graph)
    reach = graph.descendants(START_VERTEX) | {START_VERTEX}
    inn = dataflow_completeness._fixpoint(graph, reach, contracts)
    arms = dataflow_completeness._send_arms(graph, reach)
    return dataflow_completeness._obligations(graph, reach, contracts, inn, arms)


def _assert_a_real_state_arm_route(
    reference: _Reference, location: DataflowLocation, identity: str
) -> None:
    """The emitted path is a real route: ``START`` first, the reader last, every step an edge,
    the last edge on the state arm, no writer of the key before the reader's last visit, and
    as short as the arm-form search allows.

    Not asked on P-01-dirty topology: there a carried phantom is walk-internal and elided from
    the emitted path (§0.3's DEC-26 phantom-leak rule), so the path is a projection of the
    route rather than the route — ``mixed/04`` is the corpus's one such document.
    """
    if reference.phantoms:
        return
    path = tuple(START_VERTEX if step == "START" else step for step in location.path)
    edges = {(tail, head) for tail, head, _ in reference.edges}
    writers = reference.writers(location.key)
    _, state = reference.arms(location.node)

    assert path[0] == START_VERTEX and path[-1] == location.node, identity
    for tail, head in pairwise(path):
        assert (tail, head) in edges, (identity, tail, head)
    assert path[-2] in state, identity
    assert not set(path[:-1]) & writers, identity
    assert len(path) == reference.shortest_offending_length(location.node, location.key), identity


def _assert_decided_or_abstained(
    reference: _Reference, report: PropertyReport, identity: str
) -> None:
    """DEC-37 §3.2: "On every pass the entries of ``coverage`` and the members of
    ``payload_readers`` together name every reachable declared reader's keys" — decided or
    abstained, never dropped."""
    covered, violated = _decided(report)
    listed = set(_payload_readers(report) or ())
    for vertex in reference.nodes & reference.reach:
        for key in reference.reads[vertex] & reference.sigma:
            assert (vertex, key) in covered | violated or vertex in listed, (identity, vertex, key)


_CORPUS: list[tuple[str, WorkflowIR]] = _corpus_irs()


@pytest.mark.parametrize(("identity", "ir"), _CORPUS, ids=[identity for identity, _ in _CORPUS])
def test_the_validator_agrees_with_the_arm_form_reference_on_every_corpus_document(
    identity: str, ir: WorkflowIR
) -> None:
    """The whole corpus, both evolution members included: every obligation decided alike."""
    _assert_agrees_with_the_reference(ir, identity)


HAND_SHAPES: dict[str, dict[str, Any]] = {
    "dossier": DOSSIER,
    "hintless": _hintless(DOSSIER),
    "same-source": _travel(
        [
            {"from": "plan_legs", "to": "book_leg", "kind": "send"},
            {"from": "plan_legs", "to": "book_leg"},
        ],
        finish="book_leg",
    ),
    "loop": _travel(_LOOP_EDGES, finish="book_leg"),
    "self-writing-loop": _travel(
        _LOOP_EDGES, finish="book_leg", writes={"book_leg": ["bookings", "leg_id"]}
    ),
    **{f"trio-{name}": document["ir"] for name, document in TRIO.items()},
}


@pytest.mark.parametrize("name", sorted(HAND_SHAPES))
def test_the_validator_agrees_with_the_arm_form_reference_on_every_hand_shape(name: str) -> None:
    """The shapes above, held to the reference as a whole rather than field by field."""
    _assert_agrees_with_the_reference(_ir(HAND_SHAPES[name]), name)


def _with_send_edges(ir: WorkflowIR, flips: Iterable[bool]) -> WorkflowIR:
    """``ir`` with each ``normal`` edge turned into a ``send`` edge where ``flips`` says so."""
    document: dict[str, Any] = json.loads(ir.model_dump_json(by_alias=True, exclude_none=True))
    flips = iter(flips)
    for edge in document["edges"]:
        if edge.get("kind", "normal") == "normal" and next(flips, False):
            edge["kind"] = "send"
    return _ir(document)


#: The Σ the send-heavy documents draw their contracts from — small, so reads and writes meet.
_KEYS: tuple[str, ...] = ("k0", "k1", "k2", "k3")


@st.composite
def _send_heavy_documents(draw: st.DrawFn) -> WorkflowIR:
    """Small documents built to exercise the payload arm: every edge kind equally likely.

    A spanning edge into each later node keeps every node reachable, extra edges between any
    two nodes add loops, self-loops and parallel pairs (a ``send`` and an ordinary edge from one
    source is the same-source shape), and every node reads and writes a few keys of a four-key
    Σ, some of them graph inputs — so send-only targets, mixed arms, loop re-entries and
    self-writing payload readers all arise in a few hundred draws.
    """
    count = draw(st.integers(min_value=1, max_value=6))
    names = [f"n{index}" for index in range(count)]
    optional = draw(st.sets(st.sampled_from(_KEYS), max_size=2))
    kinds = st.sampled_from(("normal", "send", "conditional"))
    edges: list[dict[str, Any]] = []

    def wire(source: str, target: str) -> None:
        kind = draw(kinds)
        if kind == "conditional":
            edges.append(
                {"from": source, "kind": "conditional", "path_map": {f"l{len(edges)}": target}}
            )
        else:
            edges.append({"from": source, "to": target, "kind": kind})

    for index in range(1, count):
        wire(draw(st.sampled_from(names[:index])), names[index])
    for _ in range(draw(st.integers(min_value=0, max_value=5))):
        wire(draw(st.sampled_from(names)), draw(st.sampled_from(names)))
    contracts = st.lists(st.sampled_from(_KEYS), unique=True, max_size=3)
    sources = {edge["from"] for edge in edges}
    return _ir(
        {
            "ir_version": "1.0",
            "entry": names[0],
            "finish": [name for name in names if name not in sources] or [names[-1]],
            "state": {
                key: {"type": "str", "optional": True} if key in optional else "str"
                for key in _KEYS
            },
            "nodes": [
                {"id": name, "annotations": {"input": draw(contracts), "output": draw(contracts)}}
                for name in names
            ],
            "edges": edges,
        }
    )


@settings(max_examples=500, deadline=None)
@given(ir=_send_heavy_documents())
def test_the_validator_agrees_with_the_arm_form_reference_on_send_heavy_documents(
    ir: WorkflowIR,
) -> None:
    """Send-only targets, mixed arms, same-source pairs, loops through a payload reader and
    self-writing payload readers, generated — every obligation decided alike."""
    _assert_agrees_with_the_reference(ir)


@settings(max_examples=300, deadline=None)
@given(ir=workflow_irs(), flips=st.lists(st.booleans(), max_size=16))
def test_the_validator_agrees_with_the_arm_form_reference_on_generated_workflows(
    ir: WorkflowIR, flips: list[bool]
) -> None:
    """The library's own workflow strategy, with some ``normal`` edges turned into ``send``
    edges: the full IR surface (routers with several labels, ``END`` labels, list-form wirings)
    under the same cross-check."""
    _assert_agrees_with_the_reference(_with_send_edges(ir, flips))


@settings(max_examples=300, deadline=None)
@given(ir=_send_heavy_documents())
def test_the_arm_form_is_the_pre_dec_37_analysis_wherever_no_reader_has_a_send_arm(
    ir: WorkflowIR,
) -> None:
    """Turning every ``send`` edge into a ``normal`` one moves nothing for a reader no ``send``
    edge enters: its state arm is every in-edge, ``IN_state`` is ``IN`` (§4.4 Step 3 does not
    read edge kinds), and its coverage entries and findings are the same records, path and
    diagnostics included — the pre-DEC-37 analysis, unchanged where DEC-37 does not reach."""
    document: dict[str, Any] = json.loads(ir.model_dump_json(by_alias=True, exclude_none=True))
    for edge in document["edges"]:
        if edge.get("kind") == "send":
            edge["kind"] = "normal"
    targets = {edge.to for edge in ir.edges if isinstance(edge, SendEdge)}

    def records(document: WorkflowIR) -> set[Any]:
        coverage, findings = _step_four(document)
        return {entry for entry in coverage if entry.node not in targets} | {
            finding for finding in findings if finding.location.node not in targets
        }

    assert records(ir) == records(_ir(document))
