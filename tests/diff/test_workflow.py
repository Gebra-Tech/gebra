"""The card's two acceptance criteria, on constructed pairs.

**Box 1 — bump classes.** :data:`CASES` is the constructed-pair table. Its first two sections
are the ones the card names: brief D-11's three canonical cases (read-key removal or retype;
termination-witness removal, in each of the three places a witness can live; effect-class
escalation) and its safe extensions (new optional state keys, new nodes, new guarded edges).
The rest is the taxonomy sweep — every category of the three deltas, the authored edits the
canonical form normalizes away, and every combination of S, F and E. Each row asserts the
derived bump class, and asserts it **against the version engine's own answer** for the same
pair: the diff and :func:`~gebra.versioning.changed_components` may not disagree, because a
label is a snapshot's file name (PD-012) and an under-reported component would put two
workflow contents under one file.

*Naming note.* "Breaking case" and "safe extension" are brief D-11's names for these
constructions, and the card's; they are how a reader finds the scenario. They are not what the
engine says about them — see box 2, which is the machine-checked version of that sentence.

**Box 2 — no safe/breaking claim in the output.** P-12 ``evolution-safety`` is out of Phase-0
scope (SOW §8), deferred by owner-signed ruling PD-006 R4, whose checklist §S2 requires diff
output to carry "the deferred-P-12 marker and no safe/breaking wording". The sweep below reads
every string a diff renders — field names and values alike, for every row of the table — and
holds it against a claim vocabulary, with the P-12 slug itself masked out first so that
naming the deferred property is not mistaken for making its claim.

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import NamedTuple

import pytest

from gebra.diff import (
    EVOLUTION_SAFETY_DEFERRED,
    ContractsDelta,
    KeyDeclaration,
    NodeContractChanged,
    NodeContractRef,
    SlotChange,
    StateDelta,
    StateKeyRef,
    WorkflowDiff,
    workflow_diff,
)
from gebra.ir.canonical import graph_version
from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    NormalEdge,
    Runtime,
    StateField,
    Variant,
    WorkflowIR,
)
from gebra.store import ExtractedFrom, Snapshot
from gebra.versioning import Component, Version, changed_components
from tests.diff.test_contracts import RUNTIME_KEPT, WORK, contracts_of, edited
from tests.versioning.workflows import EDGES, NODES, STATE, node, with_contract, workflow

REPO_ROOT = Path(__file__).resolve().parents[2]

S, F, E = Component.S, Component.F, Component.E


# ── Builders: each names the shape it makes, so a row reads as the edit it is ────────────


def looping(condition: str | None = "retry_count < 3") -> WorkflowIR:
    """The base workflow with ``work`` routing back to itself under a counter guard.

    The guard is P-02 witness form (a) — a bounded-counter condition on the continuation
    label-edge (TERMINATION-WITNESS-SPEC via IR-SPEC §2.4) — and it lives in
    ``edges[].condition``, which SD-02 puts under S.
    """
    return workflow(
        edges=(
            EDGES[0],
            ConditionalEdge(
                kind="conditional",
                **{"from": "work"},
                condition=condition,
                path_map={"retry": "work", "done": "report"},
            ),
        )
    )


def with_variant() -> WorkflowIR:
    """The base workflow with a P-02 witness form (c) on ``work`` (IR-SPEC §3.3)."""
    return contracts_of(edited(variant=Variant(key="result", measure="len")))


def guarded_edge() -> WorkflowIR:
    """The base workflow plus one new guarded route — D-11's third safe extension."""
    return workflow(
        edges=(
            *EDGES,
            ConditionalEdge(
                kind="conditional",
                **{"from": "plan"},
                condition="urgent(task)",
                path_map={"expedite": "report"},
            ),
        )
    )


def merged_router() -> WorkflowIR:
    """One router carrying both labels."""
    return workflow(
        edges=(
            ConditionalEdge(
                kind="conditional",
                **{"from": "plan"},
                condition="route",
                path_map={"go": "work", "skip": "report"},
            ),
            EDGES[1],
        )
    )


def split_routers() -> WorkflowIR:
    """The same two labels, authored as two routers — same routes, different ``edges[]``."""
    return workflow(
        edges=(
            ConditionalEdge(
                kind="conditional", **{"from": "plan"}, condition="route", path_map={"go": "work"}
            ),
            ConditionalEdge(
                kind="conditional",
                **{"from": "plan"},
                condition="route",
                path_map={"skip": "report"},
            ),
            EDGES[1],
        )
    )


def audited() -> WorkflowIR:
    """The base workflow with one new node wired in after ``report``."""
    return workflow(
        nodes=(*NODES, node("audit", Annotations(pure=True, input=("result",)))),
        edges=(*EDGES, NormalEdge(kind="normal", **{"from": "report"}, to="audit")),
        finish="audit",
    )


class Case(NamedTuple):
    """One constructed pair and the V.S.F.E components its diff must bump."""

    name: str
    before: Callable[[], WorkflowIR]
    after: Callable[[], WorkflowIR]
    expected: frozenset[Component]


def case(
    name: str,
    before: Callable[[], WorkflowIR],
    after: Callable[[], WorkflowIR],
    *expected: Component,
) -> Case:
    return Case(name, before, after, frozenset(expected))


CASES: list[Case] = [
    # ── Brief D-11's three canonical cases ──────────────────────────────────────────────
    #
    # 1. Read-key removal / retype. Σ moves and no contract does: `report` still declares
    #    input=["result"] after the key it names is gone — D-11's "removed key `return_date`
    #    still read by `book_flight`". Whether anything still reads it is P-04's question
    #    over one IR; this engine reports the schema change and stops.
    case("canonical: a read key removed", workflow, lambda: workflow(state={"task": "str"}), E),
    case(
        "canonical: a read key retyped",
        workflow,
        lambda: workflow(state={"task": "str", "result": "int"}),
        E,
    ),
    # 2. Termination-witness removal — in each of the three places TERMINATION-WITNESS-SPEC
    #    lets a witness live. The three deliberately do not share a component, which is why
    #    no single counter can be read as "witnesses" (SD-02's `runtime` disposition).
    case(
        "canonical: witness form (a), a counter guard rewritten", looping, lambda: looping(None), S
    ),
    case(
        "canonical: witness form (b), the recursion limit removed",
        workflow,
        lambda: workflow(runtime=None),
        F,
    ),
    case("canonical: witness form (c), the variant removed", with_variant, workflow, F),
    # 3. Effect-class escalation — the D-011 vocabulary of IR-SPEC §2.3.
    case(
        "canonical: effect class escalated",
        workflow,
        lambda: contracts_of(edited(effect=("billable", "irreversible"))),
        F,
    ),
    # ── D-11's safe extensions: "new optional state keys, new nodes, new guarded edges" ──
    case(
        "extension: a new optional state key",
        workflow,
        lambda: workflow(state={**STATE, "receipt": StateField(type="str", optional=True)}),
        E,
    ),
    case(
        "extension: a new node, unwired",
        workflow,
        lambda: workflow(nodes=(*NODES, node("audit", None))),
        S,
        F,
    ),
    case("extension: a new node, wired in", workflow, audited, S, F),
    case("extension: a new guarded edge", workflow, guarded_edge, S),
    # ── Nothing changed: authored differences the canonical form normalizes away ────────
    case("the same workflow", workflow, workflow),
    case("nodes listed in another order", workflow, lambda: workflow(nodes=tuple(reversed(NODES)))),
    case("a singleton entry list", workflow, lambda: workflow(entry=("plan",))),
    case("a duplicated entry member", workflow, lambda: workflow(entry=("plan", "plan"))),
    case(
        "a state value written in object form",
        workflow,
        lambda: workflow(state={"task": StateField(type="str"), "result": "str"}),
    ),
    # ── S: topology, including the case the routing graph normalizes away ───────────────
    case(
        "an edge added",
        workflow,
        lambda: workflow(
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="report"))
        ),
        S,
    ),
    case("the entry moved", workflow, lambda: workflow(entry="work"), S),
    case("the finish widened", workflow, lambda: workflow(finish=("report", "work")), S),
    case("two routers merged into one", split_routers, merged_router, S),
    case("one router split into two", merged_router, split_routers, S),
    case(
        "an empty router added",
        workflow,
        lambda: workflow(
            edges=(
                *EDGES,
                ConditionalEdge(
                    kind="conditional", **{"from": "plan"}, condition="route", path_map={}
                ),
            )
        ),
        S,
    ),
    # ── F: contracts and the graph-level runtime block ──────────────────────────────────
    case("a node marked pure", workflow, lambda: contracts_of(edited(pure=False)), F),
    case(
        "a prompt body edited",
        lambda: contracts_of(edited(prompt_digest="sha256:" + "a" * 64)),
        lambda: contracts_of(edited(prompt_digest="sha256:" + "b" * 64)),
        F,
    ),
    case(
        "a contract dropped wholesale",
        workflow,
        lambda: contracts_of(None),
        F,
    ),
    case(
        "the runtime block emptied",
        workflow,
        lambda: workflow(runtime=Runtime()),
        F,
    ),
    # ── E: the state schema ─────────────────────────────────────────────────────────────
    case(
        "a reducer declared",
        workflow,
        lambda: workflow(
            state={"task": "str", "result": StateField(type="str", reducer="operator.add")}
        ),
        E,
    ),
    case("the schema dropped", workflow, lambda: workflow(state=None), E),
    # ── Combinations ────────────────────────────────────────────────────────────────────
    case(
        "an edge added and a key added",
        workflow,
        lambda: workflow(
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "plan"}, to="report")),
            state={**STATE, "receipt": "str"},
        ),
        S,
        E,
    ),
    case(
        "a contract edited and a key added",
        workflow,
        lambda: workflow(
            nodes=with_contract("work", edited(effect=("billable",))),
            state={**STATE, "receipt": "str"},
        ),
        F,
        E,
    ),
    case(
        "a node wired in and a key added",
        workflow,
        lambda: workflow(
            nodes=(*NODES, node("audit", Annotations(pure=True, input=("receipt",)))),
            edges=(*EDGES, NormalEdge(kind="normal", **{"from": "report"}, to="audit")),
            finish="audit",
            state={**STATE, "receipt": "str"},
        ),
        S,
        F,
        E,
    ),
]


# ── Box 1: the bump class on constructed pairs ───────────────────────────────────────────


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CASES])
def test_a_constructed_pair_bumps_exactly_its_components(row: Case) -> None:
    before, after = row.before(), row.after()
    diff = workflow_diff(before, after)

    assert diff.bump_class == row.expected
    # The claim that makes the derivation trustworthy: the diff's categories and the version
    # engine's canonical slices answer the same question the same way.
    assert diff.bump_class == changed_components(before, after)
    assert diff.identical == (row.expected == frozenset())
    assert diff.has_changes == bool(row.expected)
    assert diff.before.graph_version == graph_version(before)
    assert diff.after.graph_version == graph_version(after)


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CASES])
def test_a_bump_class_names_domains_not_a_direction(row: Case) -> None:
    """Diffing the pair the other way round bumps the same components: a bump class says
    which domains moved, never which way they moved."""
    assert workflow_diff(row.after(), row.before()).bump_class == row.expected


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CASES])
def test_the_bump_lands_on_the_expected_label(row: Case) -> None:
    """The bump class applied: each named counter moves by one and nothing resets."""
    current = Version.parse("1.4.2.0")
    bumped = workflow_diff(row.before(), row.after()).bump(current)

    # Spelled out rather than delegated: each named counter moves by exactly one, V is
    # carried through untouched, and nothing resets (D-11 In-Scope 2's "and/or").
    assert bumped == Version(
        v=1,
        s=4 + (S in row.expected),
        f=2 + (F in row.expected),
        e=0 + (E in row.expected),
    )
    assert bumped == current.bump(*row.expected)
    assert (bumped == current) == (row.expected == frozenset())


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CASES])
def test_diffing_twice_yields_one_value(row: Case) -> None:
    """In-process determinism: two runs over freshly built models are one value with one
    rendering. (The across-interpreter half of the claim is the seeded children below.)"""
    first = workflow_diff(row.before(), row.after())
    second = workflow_diff(row.before(), row.after())

    assert first == second
    assert repr(first) == repr(second)


def test_the_three_deltas_are_each_reported_on_their_own() -> None:
    """A pair that moves all three domains reports all three, and the S delta is the one
    SD-04 already built — this engine composes, it does not re-diff."""
    before = workflow()
    after = workflow(
        nodes=(*with_contract("work", edited(effect=("billable",))), node("audit", None)),
        state={**STATE, "receipt": StateField(type="str", optional=True)},
    )
    diff = workflow_diff(before, after)

    assert diff.topology.nodes.added == ("audit",)
    assert diff.contracts.added == (NodeContractRef("audit", None),)
    assert [change.node for change in diff.contracts.changed] == ["work"]
    assert diff.state.added == (
        StateKeyRef(key="receipt", declaration=KeyDeclaration(type="str", optional=True)),
    )
    assert diff.bump_class == frozenset({S, F, E})


def test_an_identical_pair_reports_empty_deltas_and_no_bump() -> None:
    diff = workflow_diff(workflow(), workflow(nodes=tuple(reversed(NODES))))

    assert diff.identical and not diff.has_changes
    assert diff.bump_class == frozenset()
    assert not diff.topology.has_changes
    assert diff.contracts == ContractsDelta()
    assert diff.state == StateDelta()
    assert diff.regrouped is False
    assert diff.bump(Version.parse("1.4.2.0")) == Version.parse("1.4.2.0")


# ── The one S category the routing graph cannot show ─────────────────────────────────────


def test_regrouped_routers_move_the_counter_the_graph_diff_cannot_see() -> None:
    """IR-SPEC §2.4 label-expands routers before any graph algorithm runs, so merging two
    into one preserves every route — the topology diff is right to report nothing. The
    canonical ``edges[]`` array still moved, so S is right to bump, and ``regrouped`` is what
    carries that from one to the other."""
    diff = workflow_diff(split_routers(), merged_router())

    assert not diff.topology.has_changes
    assert diff.regrouped is True
    assert diff.bump_class == frozenset({S})
    assert diff.has_changes and not diff.identical


def test_regrouped_is_about_the_edges_array_and_nothing_else() -> None:
    """A pair whose routes genuinely moved reports through the topology delta; ``regrouped``
    stays false, because the expanded routes are exactly what changed."""
    diff = workflow_diff(merged_router(), workflow())

    assert diff.topology.has_changes
    assert diff.regrouped is False
    assert diff.bump_class == frozenset({S})


# ── Box 2: the deferred-P-12 marker, and no safe/breaking claim in the output ─────────────


def test_every_diff_carries_the_deferred_p12_marker() -> None:
    """PD-006 R4 (owner-signed) defers P-12 to Phase 1 and its checklist §S2 requires the
    marker in diff output. It is the property registry's own marker, not a second shape."""
    marker = workflow_diff(workflow(), workflow(entry="work")).evolution_safety

    assert marker is EVOLUTION_SAFETY_DEFERRED
    assert marker.kind == "not-implemented"
    assert (marker.property, marker.property_id) == ("evolution-safety", "P-12")
    assert marker.status == "deferred-to-phase-1"
    assert "not a pass" in marker.detail


def test_the_marker_rides_every_row_including_the_identical_ones() -> None:
    for row in CASES:
        assert workflow_diff(row.before(), row.after()).evolution_safety.status == (
            "deferred-to-phase-1"
        )


#: Words that would make a diff grade a change rather than describe it. Not a spelling rule —
#: the check below masks the P-12 slug first, so *naming* the deferred property is fine and
#: only *claiming* its verdict is not.
CLAIM_WORDS = (
    "safe",
    "safely",
    "safety",
    "unsafe",
    "breaking",
    "breaks",
    "broken",
    "compatible",
    "incompatible",
    "backwards?",
    "benign",
    "harmless",
    "additive",
)

#: The spellings of the deferred property's own name, masked before the sweep.
_P12_NAMES = ("EVOLUTION_SAFETY_DEFERRED", "evolution-safety", "evolution_safety")


def _claims_in(text: str) -> set[str]:
    """Which claim words ``text`` uses, with the P-12 slug's own spellings masked out."""
    masked = text
    for name in _P12_NAMES:
        masked = masked.replace(name, "<the deferred property>")
    return {
        word
        for word in CLAIM_WORDS
        if re.search(rf"\b{word}\b", masked, flags=re.IGNORECASE) is not None
    }


def _api_vocabulary() -> str:
    """Every public name the diff package exports, and every field of every delta type."""
    import gebra.diff as package

    names = list(package.__all__)
    for exported in package.__all__:
        member = getattr(package, exported)
        if is_dataclass(member) and isinstance(member, type):
            names.extend(field.name for field in fields(member))
            names.extend(attribute for attribute in vars(member) if not attribute.startswith("_"))
    return " ".join(names)


def test_no_diff_output_makes_a_safe_or_breaking_claim() -> None:
    """The card's second acceptance criterion, swept over every row of the table: everything
    a diff renders — field names, slot names, values, and the deferred-P-12 marker's own
    prose — and every public name of the API that renders it."""
    rendered = "\n".join(repr(workflow_diff(row.before(), row.after())) for row in CASES)

    assert _claims_in(rendered) == set()
    assert _claims_in(_api_vocabulary()) == set()
    assert _claims_in(EVOLUTION_SAFETY_DEFERRED.model_dump_json()) == set()


def test_the_claim_sweep_can_go_red() -> None:
    """The armed control: a green sweep is only evidence if the same check catches a claim.
    Both halves matter — the words are found, and masking the P-12 slug does not hide them."""
    assert _claims_in("this change is safe") == {"safe"}
    assert _claims_in("classification: breaking") == {"breaking"}
    assert _claims_in("evolution-safety says it is safe") == {"safe"}
    assert _claims_in("evolution-safety: deferred to phase 1") == set()


def test_the_diff_carries_no_slot_named_for_a_verdict() -> None:
    """A renderer looking for a classification finds the marker in its place, and finds no
    other field to mistake for one."""
    diff = workflow_diff(workflow(), workflow(entry="work"))

    assert [field.name for field in fields(diff)] == [
        "topology",
        "contracts",
        "state",
        "regrouped",
        "evolution_safety",
    ]


# ── Anchoring on snapshots ───────────────────────────────────────────────────────────────


def _snapshot(ir: WorkflowIR, version: str) -> Snapshot:
    return Snapshot.of(
        ir,
        version=version,
        extracted_from=ExtractedFrom(
            source="tests/diff/test_workflow.py",
            extractor_version="0.0.1.dev0",
            extracted_at="2026-08-04T00:00:00Z",
        ),
    )


def test_snapshot_sides_carry_their_labels_and_the_bump_lands_on_the_stored_one() -> None:
    """The whole loop a snapshot writer runs: read the latest snapshot, diff the working IR
    against it, bump its label."""
    stored = _snapshot(workflow(), "1.4.2.0")
    working = workflow(state={**STATE, "receipt": StateField(type="str", optional=True)})
    diff = workflow_diff(stored, working)

    assert (diff.before.version, diff.after.version) == ("1.4.2.0", None)
    assert diff.bump_class == frozenset({E})
    assert str(diff.bump(Version.parse(diff.before.version or ""))) == "1.4.2.1"


def test_a_snapshot_whose_digest_disagrees_with_its_ir_is_refused() -> None:
    """The §6.1 step-9 recompute reaches this engine through the same resolver SD-04 uses:
    a wrong anchor would misattribute every delta and every counter."""
    tampered = Snapshot(
        version="1.0.0.0",
        extracted_from=ExtractedFrom(
            source="tests/diff/test_workflow.py",
            extractor_version="0.0.1.dev0",
            extracted_at="2026-08-04T00:00:00Z",
        ),
        graph_version="sha256:" + "0" * 64,
        ir=workflow(),
    )

    with pytest.raises(ValueError, match="wrong anchor"):
        workflow_diff(tampered, workflow())


def test_two_snapshots_of_one_content_bump_nothing_whatever_their_envelopes_say() -> None:
    diff = workflow_diff(
        _snapshot(workflow(), "1.0.0.0"),
        _snapshot(workflow(nodes=tuple(reversed(NODES))), "2.0.0.0"),
    )

    assert diff.identical and diff.bump_class == frozenset()
    assert (diff.before.version, diff.after.version) == ("1.0.0.0", "2.0.0.0")


# ── Determinism across interpreter runs ──────────────────────────────────────────────────

_ACROSS_RUNS = """\
import hashlib

from gebra.diff import workflow_diff
from tests.diff.test_workflow import CASES

rendering = "|".join(
    repr(workflow_diff(row.before(), row.after())) + repr(sorted(workflow_diff(row.before(), row.after()).bump_class))
    for row in CASES
)
print(hashlib.sha256(rendering.encode("utf-8")).hexdigest())
"""


def test_diff_output_is_one_value_across_interpreter_runs() -> None:
    """Four child interpreters under four ``PYTHONHASHSEED`` values diff every row of the
    table and must print one digest of one rendering. Set and dict iteration order feeds the
    slot lists, the key sets and the bump class, so this is where "deterministic" is
    observable at all."""
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


# ── WA-07: the contract, state and workflow diff paths reach no substrate and no network ──

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

from gebra.diff import contracts_diff, state_diff, workflow_diff
from tests.diff.test_workflow import CASES, _snapshot
from tests.diff.test_contracts import CONTRACTS, contracts_of
from tests.diff.test_state import SCHEMAS
from tests.versioning.workflows import workflow

for row in CASES:
    diff = workflow_diff(row.before(), row.after())
    assert diff.bump_class == row.expected
    assert diff.evolution_safety.status == "deferred-to-phase-1"

for row in CONTRACTS:
    contracts_diff(contracts_of(row.before), contracts_of(row.after))

for row in SCHEMAS:
    state_diff(workflow(state=row.before), workflow(state=row.after))

# The Snapshot arm of the resolver, under the same guard: envelope reads + digest recompute.
wrapped = workflow_diff(_snapshot(workflow(), "1.0.0.0"), _snapshot(workflow(entry="work"), "1.1.0.0"))
assert (wrapped.before.version, wrapped.after.version) == ("1.0.0.0", "1.1.0.0")

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
    """WA-07 for this card's paths. The engines take IR models, so there is no user object in
    reach to invoke; what is checkable is the rest of the invariant — diffing every
    constructed pair of all three tables imports no substrate and opens no connection. This
    card's marker pulls in ``gebra.verify``'s property registry, which is exactly why the
    guard runs the whole table rather than the engine alone. networkx is deliberately not on
    the refusal list: it is the graph representation brief D-11 mandates, and the child
    asserts it *is* imported, so what this guard allows is stated rather than smuggled."""
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_guard_trips_when_something_does_reach_the_network() -> None:
    """The armed negative control for the socket half: a green tripwire is only evidence if
    it can go red."""
    completed = _run_guarded("socket.getaddrinfo('localhost', 80)\n")

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr


def test_the_guard_trips_when_something_does_reach_the_substrate() -> None:
    """The armed negative control for the *other* half, which the network probe cannot arm.

    A substrate import opens no socket, so it never reaches ``WA07-TRIP``: the only thing that
    catches it is the ``sys.modules`` sweep in ``_REPORT``, whose green reading is
    ``stdout == "[]"``. Probing with a raise-free import is what proves that sweep can print a
    non-empty list — without it, a broken sweep would read green forever."""
    completed = _run_guarded("import langchain_core\n")

    assert completed.returncode == 0, completed.stderr
    assert "WA07-TRIP" not in completed.stderr
    assert completed.stdout.strip() != "[]"
    assert "langchain_core" in completed.stdout


def test_the_public_shapes_stay_importable_from_the_package_root() -> None:
    """The engine API brief D-11 In-Scope 3 owes D-12: one import surface, not four."""
    import gebra.diff as package

    for name in ("workflow_diff", "WorkflowDiff", "EVOLUTION_SAFETY_DEFERRED"):
        assert name in package.__all__ and hasattr(package, name)
    assert isinstance(workflow_diff(workflow(), workflow()), WorkflowDiff)
    assert SlotChange(slot="pure", before=None, after="true").added
    assert NodeContractChanged(node="work", present_before=True, present_after=True).slots == ()
    assert RUNTIME_KEPT.present_before and WORK.effect == ("write",)
