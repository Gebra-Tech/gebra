"""Diff output on constructed pairs — the card's first acceptance criterion — and both
run-level claims: determinism across interpreter runs, and WA-07 for this path.

Each row of :data:`PAIRS` is one deliberate edit read against the base workflow of
``tests.versioning.workflows`` (or a router-carrying variant of it), with the exact
expected added/removed/changed sets. The vocabulary deliberately mirrors the SD-02 delta
table — where that suite asserts *which counter* an edit moves, this one asserts *what the
diff says about it* — and every category of the data model is exercised: node
added/removed/renamed-is-new, edge added/removed/retargeted/re-kinded, router label
retargeted/added/removed/renamed, guards rewritten, START/END wiring, ``"END"`` in both of
its spellings' roles, parallels, undeclared references, and the changes that are *not*
topology (contracts, state, router regrouping).

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from gebra.diff import (
    EdgeChanged,
    EdgeRef,
    EdgesDelta,
    NodesDelta,
    TopologyDiff,
    WiringDelta,
    topology_diff,
)
from gebra.ir.canonical import graph_version
from gebra.ir.models import Annotations, ConditionalEdge, NormalEdge, SendEdge, WorkflowIR
from gebra.store import ExtractedFrom, Snapshot
from tests.versioning.workflows import EDGES, NODES, node, with_contract, workflow

REPO_ROOT = Path(__file__).resolve().parents[2]


def router(path_map: dict[str, str], condition: str | None = "route") -> ConditionalEdge:
    """A router on ``plan`` — the conditional-edge base every router case edits."""
    return ConditionalEdge(
        kind="conditional", **{"from": "plan"}, condition=condition, path_map=path_map
    )


def routed(path_map: dict[str, str] | None = None, condition: str | None = "route") -> WorkflowIR:
    """The base workflow with its ``plan → work`` edge replaced by a router."""
    labels = {"go": "work", "skip": "report"} if path_map is None else path_map
    return workflow(edges=(router(labels, condition), EDGES[1]))


class Expected(NamedTuple):
    """What one constructed pair must diff to; unspecified members must be empty."""

    nodes: NodesDelta = NodesDelta()
    entry: WiringDelta = WiringDelta()
    finish: WiringDelta = WiringDelta()
    edges: EdgesDelta = EdgesDelta()
    identical: bool = False


#: (name, before, after, expected). The names read as the edits they are.
PAIRS: list[tuple[str, Callable[[], WorkflowIR], Callable[[], WorkflowIR], Expected]] = [
    # ── Nothing changed: authored differences the canonical form normalizes away ─────────
    ("the same workflow", workflow, workflow, Expected(identical=True)),
    (
        "nodes listed in another order",
        workflow,
        lambda: workflow(nodes=tuple(reversed(NODES))),
        Expected(identical=True),
    ),
    (
        "edges listed in another order",
        workflow,
        lambda: workflow(edges=tuple(reversed(EDGES))),
        Expected(identical=True),
    ),
    (
        "entry written as a singleton list",
        workflow,
        lambda: workflow(entry=("plan",)),
        Expected(identical=True),
    ),
    (
        "entry written with a duplicate",
        workflow,
        lambda: workflow(entry=("plan", "plan")),
        Expected(identical=True),
    ),
    # ── Changed, but not in topology: the honest empty diff ──────────────────────────────
    (
        "a contract edit is not a topology change",
        workflow,
        lambda: workflow(nodes=with_contract("work", Annotations(pure=True, input=("task",)))),
        Expected(),
    ),
    (
        "a state-schema edit is not a topology change",
        workflow,
        lambda: workflow(state={"task": "str", "result": "str", "notes": "str"}),
        Expected(),
    ),
    (
        # Two routers with every labeled route preserved, merged into one authored edge:
        # the digest moves (different `edges[]` members) while the expanded graph does not
        # — the boundary the module docstrings state, held by a test.
        "a router regrouping that preserves every labeled route",
        lambda: workflow(edges=(router({"go": "work"}), router({"skip": "report"}), EDGES[1])),
        lambda: routed(),
        Expected(),
    ),
    # ── Edges: added / removed / retargeted / re-kinded / guarded / parallel ─────────────
    (
        "an edge added",
        workflow,
        lambda: workflow(
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="report"))
        ),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "report"]),
            edges=EdgesDelta.of(added=[EdgeRef("normal", "plan", "report")]),
        ),
    ),
    (
        "an edge removed",
        workflow,
        lambda: workflow(edges=EDGES[:1]),
        Expected(
            nodes=NodesDelta.of(rewired=["report", "work"]),
            edges=EdgesDelta.of(removed=[EdgeRef("normal", "work", "report")]),
        ),
    ),
    (
        # SD-02's "an edge rewired": the one unmatched normal out-edge of a persisting
        # source pairs, so the retarget reads as a change rather than as remove+add.
        "an edge retargeted",
        workflow,
        lambda: workflow(
            edges=(NormalEdge(kind="normal", **{"from": "plan"}, to="report"), EDGES[1])
        ),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "report", "work"]),
            edges=EdgesDelta.of(
                changed=[
                    EdgeChanged(
                        kind="normal",
                        source="plan",
                        label=None,
                        target_before="work",
                        target_after="report",
                    )
                ]
            ),
        ),
    ),
    (
        "a guard added to an edge",
        workflow,
        lambda: workflow(
            edges=(
                NormalEdge(kind="normal", **{"from": "plan"}, to="work", condition="retry < 3"),
                EDGES[1],
            )
        ),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            edges=EdgesDelta.of(
                changed=[
                    EdgeChanged(
                        kind="normal",
                        source="plan",
                        label=None,
                        target_before="work",
                        target_after="work",
                        condition_before=None,
                        condition_after="retry < 3",
                    )
                ]
            ),
        ),
    ),
    (
        # Kind is in the pairing key, so a re-kinded edge never pairs: a send is a fan-out
        # template (T-W-SPEC §1) — a different edge, not a changed one.
        "an edge re-kinded is a removal and an addition",
        workflow,
        lambda: workflow(edges=(SendEdge(kind="send", **{"from": "plan"}, to="work"), EDGES[1])),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            edges=EdgesDelta.of(
                added=[EdgeRef("send", "plan", "work")],
                removed=[EdgeRef("normal", "plan", "work")],
            ),
        ),
    ),
    (
        "a fan-out template added",
        workflow,
        lambda: workflow(edges=(*EDGES, SendEdge(kind="send", **{"from": "plan"}, to="work"))),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            edges=EdgesDelta.of(added=[EdgeRef("send", "plan", "work")]),
        ),
    ),
    (
        # Multiset semantics: the canonical form keeps duplicate edge objects, so a second
        # parallel copy is content — one added entry, though "the same" edge remains too.
        "a parallel copy of an existing edge added",
        workflow,
        lambda: workflow(edges=(*EDGES, EDGES[0])),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            edges=EdgesDelta.of(added=[EdgeRef("normal", "plan", "work")]),
        ),
    ),
    # ── Routers: the (source, label) slot is the one authored edge identity ──────────────
    (
        "a router label retargeted",
        routed,
        lambda: routed({"go": "report", "skip": "report"}),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "report", "work"]),
            edges=EdgesDelta.of(
                changed=[
                    EdgeChanged(
                        kind="conditional",
                        source="plan",
                        label="go",
                        target_before="work",
                        target_after="report",
                        condition_before="route",
                        condition_after="route",
                    )
                ]
            ),
        ),
    ),
    (
        "a router label added",
        routed,
        lambda: routed({"go": "work", "skip": "report", "retry": "plan"}),
        Expected(
            nodes=NodesDelta.of(rewired=["plan"]),
            edges=EdgesDelta.of(
                added=[EdgeRef("conditional", "plan", "plan", label="retry", condition="route")]
            ),
        ),
    ),
    (
        "a router label removed",
        routed,
        lambda: routed({"go": "work"}),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "report"]),
            edges=EdgesDelta.of(
                removed=[EdgeRef("conditional", "plan", "report", label="skip", condition="route")]
            ),
        ),
    ),
    (
        # The label is the edge's name (ledger §4), so a renamed label is a new identity —
        # exactly as a renamed node is (IR-SPEC §5.3) — never a match.
        "a router label renamed is a new label",
        routed,
        lambda: routed({"going": "work", "skip": "report"}),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            edges=EdgesDelta.of(
                added=[EdgeRef("conditional", "plan", "work", label="going", condition="route")],
                removed=[EdgeRef("conditional", "plan", "work", label="go", condition="route")],
            ),
        ),
    ),
    (
        "a router's guard rewritten",
        routed,
        lambda: routed(condition="route_v2"),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "report", "work"]),
            edges=EdgesDelta.of(
                changed=[
                    EdgeChanged(
                        kind="conditional",
                        source="plan",
                        label="go",
                        target_before="work",
                        target_after="work",
                        condition_before="route",
                        condition_after="route_v2",
                    ),
                    EdgeChanged(
                        kind="conditional",
                        source="plan",
                        label="skip",
                        target_before="report",
                        target_after="report",
                        condition_before="route",
                        condition_after="route_v2",
                    ),
                ]
            ),
        ),
    ),
    (
        # "END" in a path_map value is the sentinel (m3), so the retarget reports it as
        # the authored spelling and marks no node rewired by it.
        "a router label retargeted to END",
        routed,
        lambda: routed({"go": "END", "skip": "report"}),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            edges=EdgesDelta.of(
                changed=[
                    EdgeChanged(
                        kind="conditional",
                        source="plan",
                        label="go",
                        target_before="work",
                        target_after="END",
                        condition_before="route",
                        condition_after="route",
                    )
                ]
            ),
        ),
    ),
    # ── START/END wiring ─────────────────────────────────────────────────────────────────
    (
        "START wiring moved",
        workflow,
        lambda: workflow(entry="work"),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "work"]),
            entry=WiringDelta.of(added=["work"], removed=["plan"]),
        ),
    ),
    (
        "END wiring widened",
        workflow,
        lambda: workflow(finish=("report", "work")),
        Expected(
            nodes=NodesDelta.of(rewired=["work"]),
            finish=WiringDelta.of(added=["work"]),
        ),
    ),
    (
        # PD-007: `to: "END"` on a normal edge is an ordinary reference, not END wiring —
        # it reports as an edge to the reference "END", and no finish delta appears.
        "an edge to the reference END is not END wiring",
        workflow,
        lambda: workflow(edges=(*EDGES, NormalEdge(kind="normal", **{"from": "work"}, to="END"))),
        Expected(
            nodes=NodesDelta.of(rewired=["work"]),
            edges=EdgesDelta.of(added=[EdgeRef("normal", "work", "END")]),
        ),
    ),
    # ── Nodes: identity is the id, and a rename is a new identity ────────────────────────
    (
        "a node added",
        workflow,
        lambda: workflow(
            nodes=(*NODES, node("audit", Annotations(pure=True, input=("result",)))),
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "report"}, to="audit")),
        ),
        Expected(
            nodes=NodesDelta.of(added=["audit"], rewired=["report"]),
            edges=EdgesDelta.of(added=[EdgeRef("normal", "report", "audit")]),
        ),
    ),
    (
        "a node removed",
        workflow,
        lambda: workflow(nodes=NODES[:2], edges=EDGES[:1], finish="work"),
        Expected(
            nodes=NodesDelta.of(removed=["report"], rewired=["work"]),
            finish=WiringDelta.of(added=["work"], removed=["report"]),
            edges=EdgesDelta.of(removed=[EdgeRef("normal", "work", "report")]),
        ),
    ),
    (
        # The card's parenthetical, held by a test: identity is per-spec, renames are new
        # nodes. `work` does not match `labour`; the persisting neighbours' edges do.
        "a node renamed is a new node",
        workflow,
        lambda: workflow(
            nodes=(NODES[0], node("labour", None), NODES[2]),
            edges=(
                NormalEdge(kind="normal", **{"from": "plan"}, to="labour"),
                NormalEdge(kind="normal", **{"from": "labour"}, to="report"),
            ),
        ),
        Expected(
            nodes=NodesDelta.of(added=["labour"], removed=["work"], rewired=["plan", "report"]),
            edges=EdgesDelta.of(
                added=[EdgeRef("normal", "labour", "report")],
                removed=[EdgeRef("normal", "work", "report")],
                changed=[
                    EdgeChanged(
                        kind="normal",
                        source="plan",
                        label=None,
                        target_before="work",
                        target_after="labour",
                    )
                ],
            ),
        ),
    ),
    # ── Undeclared references stay visible ───────────────────────────────────────────────
    (
        "an edge to an undeclared reference added",
        workflow,
        lambda: workflow(edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="ghost"))),
        Expected(
            nodes=NodesDelta.of(rewired=["plan"]),
            edges=EdgesDelta.of(added=[EdgeRef("normal", "plan", "ghost")]),
        ),
    ),
    (
        "declaring an already-referenced node is a node addition only",
        lambda: workflow(edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="ghost"))),
        lambda: workflow(
            nodes=(*NODES, node("ghost", None)),
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="ghost")),
        ),
        Expected(nodes=NodesDelta.of(added=["ghost"])),
    ),
    # ── Ambiguity declines to pair: removed/added, never a guessed match ─────────────────
    (
        # Two unmatched out-edges on one side, one on the other: no unique pairing exists
        # under (kind, source), so nothing pairs and both sides report whole.
        "a reshaped fan-out is ambiguous and never guessed",
        lambda: workflow(
            nodes=(*NODES, node("audit", None)),
            edges=(
                NormalEdge(kind="normal", **{"from": "plan"}, to="work"),
                NormalEdge(kind="normal", **{"from": "plan"}, to="report"),
            ),
        ),
        lambda: workflow(
            nodes=(*NODES, node("audit", None)),
            edges=(NormalEdge(kind="normal", **{"from": "plan"}, to="audit"),),
        ),
        Expected(
            nodes=NodesDelta.of(rewired=["audit", "plan", "report", "work"]),
            edges=EdgesDelta.of(
                added=[EdgeRef("normal", "plan", "audit")],
                removed=[
                    EdgeRef("normal", "plan", "report"),
                    EdgeRef("normal", "plan", "work"),
                ],
            ),
        ),
    ),
    (
        # Two routers on one node may share a label, and then the slot key names two edges
        # on one side — not an identity any more, so the slot pairing declines too.
        "duplicated router labels are ambiguous and never guessed",
        lambda: workflow(edges=(router({"go": "work"}), router({"go": "report"}), EDGES[1])),
        lambda: workflow(edges=(router({"go": "plan"}), EDGES[1])),
        Expected(
            nodes=NodesDelta.of(rewired=["plan", "report", "work"]),
            edges=EdgesDelta.of(
                added=[EdgeRef("conditional", "plan", "plan", label="go", condition="route")],
                removed=[
                    EdgeRef("conditional", "plan", "report", label="go", condition="route"),
                    EdgeRef("conditional", "plan", "work", label="go", condition="route"),
                ],
            ),
        ),
    ),
]


def _check(
    before: Callable[[], WorkflowIR], after: Callable[[], WorkflowIR], expected: Expected
) -> TopologyDiff:
    """Assert one constructed pair diffs to exactly its expected sets, and return the diff."""
    diff = topology_diff(before(), after())

    assert diff.nodes == expected.nodes
    assert diff.entry == expected.entry
    assert diff.finish == expected.finish
    assert diff.edges == expected.edges
    assert diff.identical == expected.identical
    assert diff.has_changes == any(
        (expected.nodes, expected.entry, expected.finish, expected.edges)
    )
    return diff


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [pytest.param(before, after, expected, id=name) for name, before, after, expected in PAIRS],
)
def test_a_constructed_pair_diffs_to_its_expected_sets(
    before: Callable[[], WorkflowIR],
    after: Callable[[], WorkflowIR],
    expected: Expected,
) -> None:
    diff = _check(before, after, expected)

    # The graph_version anchor, on every row: the digests of what was actually compared,
    # equal exactly when the row says the pair is identical.
    assert diff.before.graph_version == graph_version(before())
    assert diff.after.graph_version == graph_version(after())
    assert (diff.before.graph_version == diff.after.graph_version) == expected.identical
    assert diff.before.version is None and diff.after.version is None


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [pytest.param(before, after, expected, id=name) for name, before, after, expected in PAIRS],
)
def test_the_reverse_diff_mirrors(
    before: Callable[[], WorkflowIR],
    after: Callable[[], WorkflowIR],
    expected: Expected,
) -> None:
    """Swapping the sides swaps added/removed and the before/after halves of every change —
    the diff reports differences in a direction, never different differences."""
    forward = topology_diff(before(), after())
    reverse = topology_diff(after(), before())

    assert reverse.nodes == NodesDelta.of(
        added=forward.nodes.removed, removed=forward.nodes.added, rewired=forward.nodes.rewired
    )
    assert reverse.entry == WiringDelta.of(added=forward.entry.removed, removed=forward.entry.added)
    assert reverse.finish == WiringDelta.of(
        added=forward.finish.removed, removed=forward.finish.added
    )
    assert reverse.edges == EdgesDelta.of(
        added=forward.edges.removed,
        removed=forward.edges.added,
        changed=[
            EdgeChanged(
                kind=change.kind,
                source=change.source,
                label=change.label,
                target_before=change.target_after,
                target_after=change.target_before,
                condition_before=change.condition_after,
                condition_after=change.condition_before,
            )
            for change in forward.edges.changed
        ],
    )
    assert reverse.before == forward.after and reverse.after == forward.before


@pytest.mark.parametrize(
    ("before", "after"),
    [pytest.param(before, after, id=name) for name, before, after, _expected in PAIRS],
)
def test_diffing_twice_yields_one_value(
    before: Callable[[], WorkflowIR], after: Callable[[], WorkflowIR]
) -> None:
    """In-process determinism: two runs over freshly built models are one value with one
    rendering. (The across-interpreter half of the claim is the seeded children below.)"""
    first = topology_diff(before(), after())
    second = topology_diff(before(), after())

    assert first == second
    assert repr(first) == repr(second)


def test_a_changed_entry_names_what_moved() -> None:
    """``rewired`` is the card's word for a moved target and ``condition_changed`` for a
    moved guard — a renderer branches on these rather than re-deriving them."""
    retargeted = EdgeChanged(
        kind="conditional",
        source="plan",
        label="go",
        target_before="work",
        target_after="report",
        condition_before="route",
        condition_after="route",
    )
    reguarded = EdgeChanged(
        kind="normal",
        source="plan",
        label=None,
        target_before="work",
        target_after="work",
        condition_before=None,
        condition_after="retry < 3",
    )

    assert retargeted.rewired and not retargeted.condition_changed
    assert reguarded.condition_changed and not reguarded.rewired


# ── Anchoring on snapshots ───────────────────────────────────────────────────────────────


def _snapshot(ir: WorkflowIR, version: str) -> Snapshot:
    return Snapshot.of(
        ir,
        version=version,
        extracted_from=ExtractedFrom(
            source="tests/diff/test_topology.py",
            extractor_version="0.0.1.dev0",
            extracted_at="2026-08-04T00:00:00Z",
        ),
    )


def test_snapshot_sides_carry_their_version_labels() -> None:
    edited = workflow(edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="report")))
    diff = topology_diff(_snapshot(workflow(), "1.0.0.0"), _snapshot(edited, "1.1.0.0"))

    assert diff.before.version == "1.0.0.0"
    assert diff.after.version == "1.1.0.0"
    assert diff.before.graph_version == graph_version(workflow())
    assert diff.edges.added == (EdgeRef("normal", "plan", "report"),)


def test_a_snapshot_and_a_bare_ir_mix() -> None:
    diff = topology_diff(_snapshot(workflow(), "1.0.0.0"), workflow(entry="work"))

    assert diff.before.version == "1.0.0.0"
    assert diff.after.version is None
    assert diff.entry == WiringDelta.of(added=["work"], removed=["plan"])


def test_two_snapshots_of_one_content_are_identical_whatever_their_envelopes_say() -> None:
    """The anchor is the digest of the IR actually compared — two labels over one content
    short-circuit to the empty diff, with both labels still reported."""
    diff = topology_diff(
        _snapshot(workflow(), "1.0.0.0"),
        _snapshot(workflow(nodes=tuple(reversed(NODES))), "2.0.0.0"),
    )

    assert diff.identical and not diff.has_changes
    assert (diff.before.version, diff.after.version) == ("1.0.0.0", "2.0.0.0")


def test_a_snapshot_whose_digest_disagrees_with_its_ir_is_refused() -> None:
    """The §6.1 step-9 recompute, extended to snapshots built outside a store: diffing
    under a wrong anchor would misattribute every finding, so the input is refused."""
    tampered = Snapshot(
        version="1.0.0.0",
        extracted_from=ExtractedFrom(
            source="tests/diff/test_topology.py",
            extractor_version="0.0.1.dev0",
            extracted_at="2026-08-04T00:00:00Z",
        ),
        graph_version="sha256:" + "0" * 64,
        ir=workflow(),
    )

    with pytest.raises(ValueError, match="wrong anchor"):
        topology_diff(tampered, workflow())


# ── Determinism across interpreter runs (acceptance: deterministic across runs) ──────────

_ACROSS_RUNS = """\
import hashlib

from gebra.diff import topology_diff
from gebra.ir.models import ConditionalEdge, NormalEdge, SendEdge
from tests.versioning.workflows import EDGES, NODES, node, workflow

before = workflow(
    nodes=(*NODES, node("π/κόμβος", None), node("𝕏", None)),
    edges=(
        *EDGES,
        ConditionalEdge(
            kind="conditional",
            **{"from": "plan"},
            condition="route",
            path_map={"α": "π/κόμβος", "ω": "END", "go": "work"},
        ),
        NormalEdge(kind="normal", **{"from": "𝕏"}, to="work"),
        EDGES[0],
    ),
)
after = workflow(
    nodes=(*NODES, node("π/κόμβος", None), node("audit", None)),
    edges=(
        *EDGES,
        ConditionalEdge(
            kind="conditional",
            **{"from": "plan"},
            condition="route_v2",
            path_map={"α": "END", "go": "work", "retry": "audit"},
        ),
        SendEdge(kind="send", **{"from": "plan"}, to="audit"),
    ),
    finish=("report", "audit"),
)

rendering = repr(topology_diff(before, after)) + "|" + repr(topology_diff(after, before))
print(hashlib.sha256(rendering.encode("utf-8")).hexdigest())
"""


def test_diff_output_is_one_value_across_interpreter_runs() -> None:
    """Four child interpreters under four ``PYTHONHASHSEED`` values diff a pair that leans
    on everything order could leak through — non-BMP ids for the UTF-16 comparator, router
    labels, parallels, both END spellings — and must print one digest of one rendering."""
    runs = {
        seed: subprocess.run(
            [sys.executable, "-c", _ACROSS_RUNS],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        for seed in ("0", "1", "777", "12345")
    }

    for seed, run in runs.items():
        assert run.returncode == 0, (seed, run.stderr)
    printed = {run.stdout.strip() for run in runs.values()}
    assert len(printed) == 1, runs
    assert len(next(iter(printed))) == len(hashlib.sha256().hexdigest())


# ── WA-07: the diff engine reaches no substrate and no network ───────────────────────────

_TRIPWIRE = """\
import socket, sys
attempts = []


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created by the diff engine")


def _trip_dns(*a, **k):
    attempts.append("getaddrinfo")
    print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("a name was resolved by the diff engine")


socket.socket = _TripSocket
socket.getaddrinfo = _trip_dns

from gebra.diff import topology_diff, topology_graph
from tests.diff.test_topology import PAIRS, _check, _snapshot
from tests.versioning.workflows import workflow

for name, before, after, expected in PAIRS:
    _check(before, after, expected)
    topology_graph(before())

# The Snapshot arm of the resolver, under the same guard: envelope reads + digest recompute.
wrapped = topology_diff(_snapshot(workflow(), "1.0.0.0"), _snapshot(workflow(entry="work"), "1.1.0.0"))
assert (wrapped.before.version, wrapped.after.version) == ("1.0.0.0", "1.1.0.0")
assert wrapped.entry.added == ("work",)

assert "networkx" in sys.modules  # the representation the brief mandates — in reach by design
"""

_REPORT = """
print([m for m in sys.modules
       if m.split(".")[0] in {"langgraph", "langchain", "langchain_core"}]
      + attempts)
"""


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_diffing_every_pair_reaches_no_substrate_and_no_socket() -> None:
    """WA-07 for this card's path. The engine takes IR models, so there is no user object
    in reach to invoke; what is checkable is the rest of the invariant — building every
    graph and diffing every constructed pair imports no substrate and opens no connection.
    networkx is deliberately not on the refusal list: it is the graph representation the
    card mandates, and the child asserts it *is* imported, so what this guard allows is
    stated rather than smuggled."""
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_guard_trips_when_something_does_reach_the_substrate() -> None:
    """The armed negative control: a green tripwire is only evidence if it can go red."""
    completed = _run_guarded("import langchain_core\nsocket.getaddrinfo('localhost', 80)\n")

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr
