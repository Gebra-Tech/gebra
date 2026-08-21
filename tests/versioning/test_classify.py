"""Bump-category selection on constructed deltas — the card's second acceptance criterion.

Each row of :data:`DELTAS` is one deliberate edit to the base workflow of
``tests.versioning.workflows`` and the component set the S/F/E definitions say it should
select. The definitions being matched are brief D-11's, quoted in
:mod:`gebra.versioning.classify`: **S** — "topology changes (nodes; edges of kind normal |
conditional | send; START/END wiring)"; **F** — node contracts, plus the graph-level
``runtime`` block this card placed there; **E** — "state-schema Σ changes".

Every row is checked twice over. Once against the expected component set, and once against
the digest: an edit that selects no component must leave ``graph_version`` alone, and an
edit that changes ``graph_version`` must select at least one. That second assertion is what
keeps the version engine and the content digest from ever disagreeing about whether a
workflow changed — one workflow content, one label.

Everything here is pure data (WA-07): the deltas are IR models built by hand, and the
comparison is a function of two of them. Nothing extracts, and there is no user object in
reach to invoke.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from gebra.ir.canonical import graph_version
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    IdempotentKey,
    Interrupts,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    SendEdge,
    StateField,
    Variant,
    WorkflowIR,
)
from gebra.versioning import (
    Component,
    Version,
    changed_components,
    component_bytes,
    component_slice,
    components_for_path,
    next_version,
)
from tests.versioning.workflows import (
    EDGES,
    NODES,
    STATE,
    contract_of,
    node,
    with_contract,
    workflow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

S = Component.S
F = Component.F
E = Component.E

#: (name, the edited workflow, the components the definitions select).
DELTAS: list[tuple[str, Callable[[], WorkflowIR], frozenset[Component]]] = [
    # ── Nothing changed: authored differences the canonical form normalizes away ─────────
    ("the same workflow", workflow, frozenset()),
    (
        "nodes listed in another order",
        lambda: workflow(nodes=tuple(reversed(NODES))),
        frozenset(),
    ),
    ("edges listed in another order", lambda: workflow(edges=tuple(reversed(EDGES))), frozenset()),
    (
        "state keys written in another order",
        lambda: workflow(state={"result": "str", "task": "str"}),
        frozenset(),
    ),
    ("entry written as a singleton list", lambda: workflow(entry=("plan",)), frozenset()),
    ("entry written with a duplicate", lambda: workflow(entry=("plan", "plan")), frozenset()),
    (
        "a state value written in its object form",
        lambda: workflow(state={"task": StateField(type="str"), "result": "str"}),
        frozenset(),
    ),
    (
        "a contract carrying an empty effect list",
        lambda: workflow(
            nodes=with_contract("report", Annotations(pure=True, input=("result",), effect=()))
        ),
        frozenset(),
    ),
    # ── S: topology — nodes, edges, START/END wiring ─────────────────────────────────────
    (
        "an edge added",
        lambda: workflow(
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="report"))
        ),
        frozenset({S}),
    ),
    ("an edge removed", lambda: workflow(edges=EDGES[:1]), frozenset({S})),
    (
        "an edge rewired",
        lambda: workflow(
            edges=(NormalEdge(kind="normal", **{"from": "plan"}, to="report"), EDGES[1])
        ),
        frozenset({S}),
    ),
    (
        "an edge changed kind",
        lambda: workflow(
            edges=(
                ConditionalEdge(kind="conditional", **{"from": "plan"}, path_map={"go": "work"}),
                EDGES[1],
            )
        ),
        frozenset({S}),
    ),
    (
        "a router's path_map retargeted",
        lambda: workflow(
            edges=(
                ConditionalEdge(kind="conditional", **{"from": "plan"}, path_map={"go": "report"}),
                EDGES[1],
            )
        ),
        frozenset({S}),
    ),
    (
        "a fan-out template added",
        lambda: workflow(edges=(*EDGES, SendEdge(kind="send", **{"from": "plan"}, to="work"))),
        frozenset({S}),
    ),
    (
        # `condition` is declared content, so it has a colourable claim to F; it is where an
        # edge routes on, so this card put it under S with the rest of `edges`.
        "a guard rewritten",
        lambda: workflow(
            edges=(
                ConditionalEdge(
                    kind="conditional",
                    **{"from": "plan"},
                    condition="retry_count < 3",
                    path_map={"go": "work"},
                ),
                EDGES[1],
            )
        ),
        frozenset({S}),
    ),
    ("START wiring changed", lambda: workflow(entry="work"), frozenset({S})),
    ("END wiring changed", lambda: workflow(finish="work"), frozenset({S})),
    (
        "END wiring widened",
        lambda: workflow(finish=("report", "work")),
        frozenset({S}),
    ),
    # ── S and F together: a node's presence is topology, its contract is a contract ──────
    (
        "a node added",
        lambda: workflow(
            nodes=(*NODES, node("audit", Annotations(pure=True, input=("result",)))),
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "report"}, to="audit")),
        ),
        frozenset({S, F}),
    ),
    (
        "a node added carrying no contract at all",
        lambda: workflow(
            nodes=(*NODES, node("audit", None)),
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "report"}, to="audit")),
        ),
        frozenset({S, F}),
    ),
    (
        "a node removed",
        lambda: workflow(nodes=NODES[:2], edges=EDGES[:1], finish="work"),
        frozenset({S, F}),
    ),
    (
        "a node renamed",
        lambda: workflow(
            nodes=(NODES[0], node("labour", contract_of("work")), NODES[2]),
            edges=(
                NormalEdge(kind="normal", **{"from": "plan"}, to="labour"),
                NormalEdge(kind="normal", **{"from": "labour"}, to="report"),
            ),
        ),
        frozenset({S, F}),
    ),
    # ── F: node contracts ────────────────────────────────────────────────────────────────
    (
        "an effect class escalated",
        lambda: workflow(
            nodes=with_contract(
                "work", Annotations(effect=("network",), input=("task",), output=("result",))
            )
        ),
        frozenset({F}),
    ),
    (
        "a node declared pure",
        lambda: workflow(
            nodes=with_contract("work", Annotations(pure=True, input=("task",), output=("result",)))
        ),
        frozenset({F}),
    ),
    (
        "a determinism claim added",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    deterministic=DeterministicSpec(seed=7),
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "an idempotency claim added",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",), input=("task",), output=("result",), idempotent=True
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "an idempotency claim given a key",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    idempotent=IdempotentKey(key="task"),
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "a retry policy declared",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    retry_policy=RetryPolicy(max_attempts=3, retry_on=("TimeoutError",)),
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "an argument schema attached",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    args_schema={"type": "object", "properties": {"task": {"const": True}}},
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "a compensation hook named",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    compensation=Compensation(hook="report"),
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "a read key dropped from a contract",
        lambda: workflow(
            nodes=with_contract("work", Annotations(effect=("write",), output=("result",)))
        ),
        frozenset({F}),
    ),
    (
        "a termination witness of form (c) added",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    variant=Variant(key="task", measure="len"),
                ),
            )
        ),
        frozenset({F}),
    ),
    (
        "a prompt body edited",
        lambda: workflow(
            nodes=with_contract(
                "work",
                Annotations(
                    effect=("write",),
                    input=("task",),
                    output=("result",),
                    prompt_digest="sha256:" + "a" * 64,
                ),
            )
        ),
        frozenset({F}),
    ),
    # ── F: the graph-level runtime block (this card's disposition) ───────────────────────
    (
        "a termination witness of form (b) removed",
        lambda: workflow(runtime=None),
        frozenset({F}),
    ),
    (
        "a recursion limit's justification rewritten",
        lambda: workflow(
            runtime=Runtime(recursion_limit=RecursionLimit(value=10, justification="still short"))
        ),
        frozenset({F}),
    ),
    (
        "an interrupt gate placed",
        lambda: workflow(
            runtime=Runtime(
                recursion_limit=RecursionLimit(
                    value=10, justification="the line is three nodes long"
                ),
                interrupts=Interrupts(before=("work",)),
            )
        ),
        frozenset({F}),
    ),
    (
        "a checkpointer declared",
        lambda: workflow(
            runtime=Runtime(
                recursion_limit=RecursionLimit(
                    value=10, justification="the line is three nodes long"
                ),
                checkpointer=Checkpointer(present=True),
            )
        ),
        frozenset({F}),
    ),
    # ── E: the state schema Σ ────────────────────────────────────────────────────────────
    (
        "a state key added",
        lambda: workflow(state={**STATE, "notes": "str"}),
        frozenset({E}),
    ),
    ("a state key removed", lambda: workflow(state={"task": "str"}), frozenset({E})),
    (
        "a state key retyped",
        lambda: workflow(state={**STATE, "result": "list[str]"}),
        frozenset({E}),
    ),
    (
        "a reducer declared on a state key",
        lambda: workflow(state={**STATE, "result": StateField(type="str", reducer="operator.add")}),
        frozenset({E}),
    ),
    (
        "a state key marked optional",
        lambda: workflow(state={**STATE, "task": StateField(type="str", optional=True)}),
        frozenset({E}),
    ),
    ("the state schema emptied", lambda: workflow(state={}), frozenset({E})),
    (
        # Distinct from the row above: §6.3 keeps an absent slot and an empty one apart, and
        # so does the comparison.
        "the state schema removed entirely",
        lambda: workflow(state=None),
        frozenset({E}),
    ),
    # ── Combinations ─────────────────────────────────────────────────────────────────────
    (
        "topology and schema together",
        lambda: workflow(entry="work", state={**STATE, "notes": "str"}),
        frozenset({S, E}),
    ),
    (
        "a contract and the schema together",
        lambda: workflow(
            nodes=with_contract("work", Annotations(pure=True, input=("task",))),
            state={**STATE, "notes": "str"},
        ),
        frozenset({F, E}),
    ),
    (
        "all three at once",
        lambda: workflow(
            entry="work",
            nodes=with_contract("work", Annotations(pure=True, input=("task",))),
            state={**STATE, "notes": "str"},
        ),
        frozenset({S, F, E}),
    ),
]


@pytest.mark.parametrize(
    ("edited", "expected"),
    [pytest.param(build, expected, id=name) for name, build, expected in DELTAS],
)
def test_a_delta_selects_the_components_the_definitions_name(
    edited: Callable[[], WorkflowIR], expected: frozenset[Component]
) -> None:
    assert changed_components(workflow(), edited()) == expected


@pytest.mark.parametrize(
    ("edited", "expected"),
    [pytest.param(build, expected, id=name) for name, build, expected in DELTAS],
)
def test_a_delta_moves_the_digest_exactly_when_it_moves_a_component(
    edited: Callable[[], WorkflowIR], expected: frozenset[Component]
) -> None:
    """The engine and the content digest agree about whether a workflow changed. If they
    could disagree, one workflow content would end up under two labels — or two contents
    under one."""
    unchanged = graph_version(workflow()) == graph_version(edited())

    assert unchanged == (expected == frozenset())


@pytest.mark.parametrize(
    ("edited", "expected"),
    [pytest.param(build, expected, id=name) for name, build, expected in DELTAS],
)
def test_a_delta_is_symmetric(
    edited: Callable[[], WorkflowIR], expected: frozenset[Component]
) -> None:
    """Which components a change touched does not depend on which way round it is read —
    the engine reports domains, not directions. (Whether the change was an addition or a
    removal is the diff engine's to report, SD-04/SD-05.)"""
    assert changed_components(edited(), workflow()) == expected


def test_v_is_never_selected_by_a_workflow_change() -> None:
    for _name, edited, _expected in DELTAS:
        assert Component.V not in changed_components(workflow(), edited())


def test_the_version_engine_never_asks_for_a_v_slice() -> None:
    """V has no slice to compare, because no part of an IR is what it counts."""
    with pytest.raises(ValueError, match="V is not derived"):
        component_slice({}, Component.V)

    with pytest.raises(ValueError, match="V is not derived"):
        component_bytes({}, Component.V)


def test_a_json_schema_value_retyped_is_a_change() -> None:
    """The regression pin for a defect the SD-02 pre-review caught. ``args_schema`` is a
    JSON Schema carried verbatim (IR-SPEC §3.1) — the one place in ir 1.0 where the JSON
    *type* at a path is unconstrained — so ``{"const": true}`` and ``{"const": 1}`` are two
    contents with two digests. Python's ``==`` says they are one (``True == 1``), which is
    why the comparison is by canonical bytes and not by parsed value: the alternative put
    two workflow contents under one label, and PD-012 makes a label a file name."""
    schema_true = workflow(nodes=with_contract("work", Annotations(args_schema={"c": True})))
    schema_one = workflow(nodes=with_contract("work", Annotations(args_schema={"c": 1})))

    assert graph_version(schema_true) != graph_version(schema_one)
    assert changed_components(schema_true, schema_one) == frozenset({F})


def test_an_empty_slot_and_an_absent_one_are_different_workflows() -> None:
    """The comparison's null-normalization keeps "the slot is empty" apart from "the slot
    is not there", exactly as the canonical form does."""
    assert changed_components(workflow(state={}), workflow(state=None)) == frozenset({E})
    assert changed_components(workflow(runtime=Runtime()), workflow(runtime=None)) == frozenset({F})


# ── The engine's one-call surface ────────────────────────────────────────────────────────


def test_next_version_applies_the_selected_bumps() -> None:
    current = Version.parse("1.4.2.0")
    edited = workflow(entry="work", state={**STATE, "notes": "str"})

    assert str(next_version(current, workflow(), edited)) == "1.5.2.1"


def test_next_version_of_an_unchanged_workflow_is_the_same_version() -> None:
    """Whether an unchanged workflow is re-snapshot at all is SD-03's idempotency policy;
    what this engine says is that it is not a new version."""
    current = Version.parse("1.4.2.0")

    assert next_version(current, workflow(), workflow(nodes=tuple(reversed(NODES)))) == current


def test_a_sequence_of_edits_walks_the_version_forward() -> None:
    """Brief D-11 In-Scope 2 end to end: compare the working IR against the latest
    snapshot, bump accordingly, and repeat as the workflow evolves."""
    history = [(Version.initial(), workflow())]
    for edited in (
        workflow(entry="work"),
        workflow(entry="work", nodes=with_contract("work", Annotations(pure=True))),
        workflow(entry="work", nodes=with_contract("work", Annotations(pure=True)), state={}),
    ):
        current, previous = history[-1]
        history.append((next_version(current, previous, edited), edited))

    assert [str(version) for version, _ir in history] == [
        "1.0.0.0",
        "1.1.0.0",
        "1.1.1.0",
        "1.1.1.1",
    ]
    assert [version for version, _ir in history] == sorted(version for version, _ir in history)


# ── The S/F/E definition as a table ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (("entry",), {S}),
        (("finish",), {S}),
        (("edges",), {S}),
        (("edges", "from"), {S}),
        (("edges", "to"), {S}),
        (("edges", "kind"), {S}),
        (("edges", "path_map"), {S}),
        # Declared content, but it is what an edge routes on — this card's disposition.
        (("edges", "condition"), {S}),
        # A node's presence is topology and its contract hangs from its identity, so a
        # node arriving, leaving or being renamed moves both.
        (("nodes",), {S, F}),
        (("nodes", "id"), {S, F}),
        (("nodes", "annotations"), {F}),
        (("nodes", "annotations", "pure"), {F}),
        (("nodes", "annotations", "effect"), {F}),
        (("nodes", "annotations", "variant", "measure"), {F}),
        # The six new-in-1.0 §3 slots land with the rest of the contract.
        (("nodes", "annotations", "prompt_digest"), {F}),
        (("nodes", "annotations", "args_schema"), {F}),
        (("nodes", "annotations", "compensation", "hook"), {F}),
        (("runtime",), {F}),
        (("runtime", "recursion_limit"), {F}),
        (("runtime", "recursion_limit", "justification"), {F}),
        (("runtime", "interrupts", "before"), {F}),
        (("runtime", "checkpointer", "present"), {F}),
        (("state",), {E}),
        (("state", "task"), {E}),
        # A format migration is not a workflow migration (IR-SPEC §8).
        (("ir_version",), set()),
    ],
)
def test_a_core_ir_field_belongs_to_the_components_the_definitions_give_it(
    path: tuple[str, ...], expected: set[Component]
) -> None:
    assert components_for_path(path) == expected


@pytest.mark.parametrize(
    ("path", "edited"),
    [
        (("entry",), lambda: workflow(entry="work")),
        (("finish",), lambda: workflow(finish="work")),
        (("edges",), lambda: workflow(edges=EDGES[:1])),
        (
            ("edges", "condition"),
            lambda: workflow(
                edges=(
                    NormalEdge(
                        kind="normal", **{"from": "plan"}, to="work", condition="retry_count < 3"
                    ),
                    EDGES[1],
                )
            ),
        ),
        (("nodes",), lambda: workflow(nodes=(*NODES, node("audit", None)))),
        (
            ("nodes", "id"),
            lambda: workflow(nodes=(NODES[0], node("labour", contract_of("work")), NODES[2])),
        ),
        (
            ("nodes", "annotations"),
            lambda: workflow(nodes=with_contract("work", Annotations(pure=True))),
        ),
        (("runtime",), lambda: workflow(runtime=None)),
        (("state",), lambda: workflow(state={**STATE, "notes": "str"})),
    ],
)
def test_the_table_predicts_what_an_edit_at_that_path_moves(
    path: tuple[str, ...], edited: Callable[[], WorkflowIR]
) -> None:
    """The bridge between the definition and the comparator, and the contract SD-05 reads:
    what the table says a field belongs to is what editing that field actually moves."""
    assert changed_components(workflow(), edited()) == components_for_path(path)


@pytest.mark.parametrize("path", [(), ("nope",), ("nodes.id",), ("annotations",)])
def test_a_path_that_is_not_a_core_ir_field_is_refused(path: tuple[str, ...]) -> None:
    """The ``ir_version`` 1.0 field set is closed (frozen by DEC-09), so an unrecognised
    path is a caller's mistake — reported rather than silently classified."""
    with pytest.raises(KeyError):
        components_for_path(path)


# ── WA-07: the version engine reaches no substrate and no network ────────────────────────


_TRIPWIRE = """\
import socket, sys
attempts = []


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created by the version engine")


def _trip_dns(*a, **k):
    attempts.append("getaddrinfo")
    print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("a name was resolved by the version engine")


socket.socket = _TripSocket
socket.getaddrinfo = _trip_dns

from gebra.versioning import Version, changed_components, next_version
from tests.versioning.test_classify import DELTAS
from tests.versioning.workflows import workflow

current = Version.initial()
for name, build, expected in DELTAS:
    assert changed_components(workflow(), build()) == expected, name
    current = next_version(current, workflow(), build())
"""

_REPORT = """
print([m for m in sys.modules
       if m.split(".")[0] in {"langgraph", "langchain", "langchain_core", "networkx"}]
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


def test_classifying_every_delta_reaches_no_substrate_and_no_socket() -> None:
    """WA-07 for this card's path. The engine takes IR *models*, so there is no user object
    in reach to invoke; what is checkable is the rest of the invariant — that comparing and
    bumping imports no substrate and opens no connection."""
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_guard_trips_when_something_does_reach_the_substrate() -> None:
    """The armed negative control: a green tripwire is only evidence if it can go red."""
    completed = _run_guarded("import langchain_core\nsocket.getaddrinfo('localhost', 80)\n")

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr
