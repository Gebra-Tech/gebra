"""SD-03's two acceptance boxes, over the live travel-booking agent.

Brief D-11's week-4 milestone is "``gebra snapshot`` engine wired to D-08's
``gebra.extract()``; travel-booking agent v1 extracted and snapshotted **for real**", and
"for real" is the whole difference between this file and ``tests/snapshot/test_engine.py``:
the IR here is not hand-built. It comes out of the extractor, off the shared TE-05 agent, and
lands in a store as that store's first occupant.

Three claims:

1. **The store holds travel-booking v1 under the correct ``graph_version``** — correct
   meaning *the digest of the IR the extractor produced*, recomputed here from the agent
   rather than read back off the file the engine just wrote, and equal at all three places it
   is recorded (the snapshot document, the store index, and the outcome). No literal digest is
   pinned: the extraction is a function of the installed substrate, and this fixture is
   extracted on every cell of the frozen VERSION-COMPAT matrix.
2. **Snapshotting the unchanged agent twice records nothing and reports the same version** —
   the policy of ``gebra.snapshot.engine``, over a live object this time, with the store's
   bytes asserted unchanged rather than its return value trusted.
3. **Nothing in the agent runs** (WA-07). Every node body and router in the fixture raises if
   it is called, so the ledger is asserted empty on entry to and exit from every test here,
   and the whole ``extract`` → store path is run again in a fresh interpreter where name
   resolution, connection opening, socket construction and ``StateGraph.compile`` all raise —
   with each of those raisers armed by a control that proves it can go red.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gebra import extract
from gebra.extraction import ExtractionEnvelope
from gebra.ir.canonical import graph_version
from gebra.lineage import lineage
from gebra.snapshot import SnapshotAction, record, snapshot
from gebra.store import SnapshotStore
from gebra.verify import verify
from tests.sample_workflows import travel_booking as tb

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The reference a caller who knows what it imported would record (CLI-SPEC §2.1).
SOURCE = "tests.sample_workflows.travel_booking:build_travel_booking_agent"


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Any:
    """The agent is read, never run — asserted on entry to and exit from every test.

    Entry as well as exit, for the reason ``tests/testing/test_travel_booking.py`` records:
    module-scoped fixtures are built before the first test's own setup, so a fixture that
    *cleared* the ledger here would erase exactly the evidence it exists to keep.
    """
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


@pytest.fixture(scope="module")
def envelope() -> ExtractionEnvelope:
    """The v1 extraction — the builder level, which PD-023's call makes the subject."""
    return extract(tb.build_travel_booking_agent())


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """An empty store of its own per test — nothing exists until the first write."""
    return SnapshotStore.for_project(tmp_path)


# ── Acceptance box 2 — the store holds v1 under the right digest ─────────────────────────


def test_the_agent_is_the_first_occupant_of_the_store(
    store: SnapshotStore, envelope: ExtractionEnvelope
) -> None:
    """**Acceptance box 2.** v1 lands at ``1.0.0.0`` carrying the extractor's own digest.

    The digest is recomputed from the extracted IR — not read back off the file the engine
    wrote, which would make this a test of the store's own consistency check — and asserted
    equal at every place a store records it: the outcome, the snapshot document, and the
    index row that lets a reader answer "what versions exist and what do they hash to"
    without opening a snapshot file.
    """
    outcome = snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)
    expected = graph_version(envelope.ir)

    assert outcome.action is SnapshotAction.RECORDED
    assert outcome.version == "1.0.0.0"
    assert outcome.first and outcome.previous is None
    assert outcome.graph_version == expected

    assert store.versions() == ("1.0.0.0",)
    assert store.read("1.0.0.0").graph_version == expected
    assert store.read_meta().history[0].graph_version == expected
    assert store.read_meta().current == "1.0.0.0"
    assert store.check().ok


def test_the_stored_snapshot_reloads_to_the_ir_it_was_made_from(
    store: SnapshotStore, envelope: ExtractionEnvelope
) -> None:
    """D-11's DoD line: "a deterministic file that reloads to an IR equal to its source".

    Equality of the *model*, not of a rendering: the snapshot read back off disk carries the
    same ``WorkflowIR`` value the extractor returned, nine nodes and all. Byte-stability of
    the file itself is SD-01's, held there over hand-built fixtures; what this adds is that
    an extraction survives the round trip unchanged.
    """
    snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)
    reloaded = store.read("1.0.0.0")

    assert reloaded.ir == envelope.ir
    assert tuple(node.id for node in reloaded.ir.nodes) == tuple(sorted(tb.NODE_IDS))
    assert reloaded.extracted_from.source == SOURCE
    assert reloaded.extracted_from.extractor_version == envelope.extracted_from.extractor_version
    assert reloaded.extracted_from.sidecar_path is None


def test_the_recorded_subject_is_the_builder_not_the_compiled_graph(
    store: SnapshotStore, envelope: ExtractionEnvelope
) -> None:
    """PD-023 D4 at the store: the two levels are two documents, and v1 is the builder's.

    TE-05 chose the builder as v1's subject because ``runtime.checkpointer`` says what
    compiling configured rather than what the definition is. That choice is invisible until
    something stores a digest — so this is where it is pinned: the digest in the store is the
    builder extraction's, and the compiled extraction's is a different one, which would have
    landed as a different version had it been the subject.
    """
    snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)
    compiled = extract(tb.compile_travel_booking_agent())

    assert store.read("1.0.0.0").graph_version == graph_version(envelope.ir)
    assert store.read("1.0.0.0").graph_version != graph_version(compiled.ir)
    assert store.read("1.0.0.0").ir.runtime is None


# ── Acceptance box 1 — re-snapshotting the unchanged agent ───────────────────────────────


def test_snapshotting_the_unchanged_agent_twice_is_a_no_op_at_the_same_version(
    store: SnapshotStore,
) -> None:
    """**Acceptance box 1**, over a live object: nothing written, same label reported.

    The two calls build the agent independently, so the second is a genuinely fresh
    extraction of an unchanged definition rather than the same object handed in twice — which
    is the case the policy is actually about. Asserted on the store's bytes: every file in it
    is byte-identical afterwards, and the history gained no row.
    """
    first = snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)
    before = {path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()}

    second = snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)

    assert second.action is SnapshotAction.UNCHANGED
    assert not second.recorded
    assert second.version == first.version == "1.0.0.0"
    assert second.previous == "1.0.0.0"
    assert second.bump_class == frozenset()
    assert second.diff is not None and second.diff.identical
    assert {
        path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()
    } == (before)
    assert store.versions() == ("1.0.0.0",)
    assert lineage(store).total == 1


def test_a_second_extraction_is_the_same_document(envelope: ExtractionEnvelope) -> None:
    """The premise the no-op rests on, stated here rather than borrowed.

    The policy compares digests, so "the agent did not change" only means "no new version"
    because extracting the unchanged agent twice produces one document. TE-05 pins that too;
    it is repeated here because it is *this* card's premise, and a drift in it would show up
    here as a spurious second version rather than as a puzzle.
    """
    again = extract(tb.build_travel_booking_agent())

    assert graph_version(again.ir) == graph_version(envelope.ir)


# ── The pipeline shape SD-09 will run ────────────────────────────────────────────────────


def test_verify_then_snapshot_records_v1_with_its_eligibility_established(
    store: SnapshotStore, envelope: ExtractionEnvelope
) -> None:
    """extract → verify → snapshot, in that order, with the §0.2 field actually applied.

    The wedge five pass clean on v1 (TE-05's box 2), so ``gate.snapshot_eligible`` is true and
    the write goes ahead. The engine reads that one field and re-derives nothing; handing it
    the report is what makes "no snapshot is recorded for a FATAL" hold for a caller that
    never touches the CLI. One extraction feeds both, which is the "one resolution, one IR"
    ``docs/specs/CLI-SPEC.md`` §4.2 requires — the digest the gate saw is the digest stored.
    """
    report = verify(envelope.ir)
    assert report.gate.exit_code == 0
    assert report.gate.snapshot_eligible

    outcome = record(envelope, store=store, source=SOURCE, eligibility=report)

    assert outcome.recorded
    assert outcome.graph_version == graph_version(envelope.ir)
    assert store.read("1.0.0.0").ir == envelope.ir


# ── Acceptance box 3 of TE-05, inherited: nothing runs on this path ───────────────────────

#: The guarded child: the whole ``extract`` → store path over the agent, in a fresh
#: interpreter where resolving a name or opening a connection raises from the first line, and
#: where ``StateGraph.compile`` is taken away **before gebra is imported at all** — this card's
#: subject is the builder, so unlike TE-05's child nothing here ever needs to compile.
#: Socket *construction* is counted rather than refused during imports for the reason
#: ``tests/extraction/test_dispatch.py`` records: importing the substrate runs urllib3's own
#: IPv6 capability probe, which builds a loopback socket and closes it without connecting.
_TRIPWIRE = """
import socket, sys, tempfile

attempts = []
built = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _CountSocket(socket.socket):
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the snapshot path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

from langgraph.graph.state import StateGraph

StateGraph.compile = _record("StateGraph.compile")

from gebra import extract
from gebra.snapshot import SnapshotAction, snapshot
from gebra.store import SnapshotStore
from tests.sample_workflows import travel_booking as tb

# The import phase is bounded, not excluded — see the note on the constant. From here the run
# is gebra's own work, and socket construction raises too.
assert attempts == [], attempts
socket.socket = _TripSocket

store = SnapshotStore.for_project(tempfile.mkdtemp())

first = snapshot(tb.build_travel_booking_agent(), store=store, source="child:agent")
assert first.action is SnapshotAction.RECORDED, first
assert first.version == "1.0.0.0", first

# Identity, not only success: a snapshot of some *other* document would satisfy the checks
# above, so the stored document is pinned to this agent's node set and to the digest a fresh
# extraction produces — the acceptance box, asserted under the guard as well as outside it.
held = store.read("1.0.0.0")
assert tuple(node.id for node in held.ir.nodes) == tuple(sorted(tb.NODE_IDS)), held.ir.nodes
assert held.graph_version == extract(tb.build_travel_booking_agent()).graph_version()

second = snapshot(tb.build_travel_booking_agent(), store=store, source="child:agent")
assert second.action is SnapshotAction.UNCHANGED, second
assert second.version == "1.0.0.0", second
assert store.versions() == ("1.0.0.0",), store.versions()
assert store.check().ok, store.check()

"""

#: Run last, after any probe. Three things ride here rather than in the body, all for the same
#: reason: an assertion a probe should be able to trip has to come *after* the probe.
#:
#: The **ledger assertion**, so a probe firing a node body is caught by this leg too.
#:
#: The **no-network-client assertion**. What is asserted absent is the one substrate module
#: that carries a network client: ``langgraph.pregel.remote``, whose ``RemoteGraph`` is DEC-19
#: drawing route 6, the same module ``tests/extraction/test_compiled.py`` keeps out of
#: ``sys.modules``. No socket raiser can arm this leg — importing a module opens no connection
#: — so it has its own probe. (A blanket "urllib is unimported" claim would be false and
#: uninformative here: importing the substrate pulls ``urllib.request`` transitively without
#: ever calling it, which is why the guards are on the primitives and not on imports.) That
#: langgraph *is* in reach on this path is measured separately, in
#: :func:`test_importing_the_engine_imports_the_substrate_and_no_network_client`, where the
#: child imports nothing else — here the child's own ``from langgraph.graph.state import …``
#: would satisfy such an assertion whatever gebra did.
#:
#: The **import-phase socket count**, *reported* rather than gated: construction is counted,
#: not refused, while the substrate imports, and reporting it keeps that residual a checked
#: statement instead of a collected-and-ignored list. Deliberately not bounded — the number
#: belongs to whichever third-party import ran a capability probe.
_REPORT = (
    "assert tb.TRIPPED == [], tb.TRIPPED\n"
    "assert 'langgraph.pregel.remote' not in sys.modules\n"
    "print('import-phase sockets constructed:', len(built))\n"
    "print(attempts)\n"
)


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    """Run the child, with ``PYTHONOPTIMIZE`` pinned off.

    Pinned rather than inherited: nearly everything the child states — its own claims and the
    ledger check in :data:`_REPORT` — is stated in an ``assert``, and ``-O`` deletes those. An
    inherited ``PYTHONOPTIMIZE=1`` would not make this suite green under a broken invariant
    (the seeded-execution control below asserts a non-zero exit that would stop happening), but
    a guard should not depend on another test to notice it was switched off.
    """
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_whole_snapshot_path_runs_nothing_and_opens_no_socket() -> None:
    """WA-07 for this card's path, in a fresh interpreter and over the path the card ships.

    Four claims at once. Every node function and router in the agent raises if it is called,
    so an extraction that reached one would fail the child; ``StateGraph.compile`` raises from
    before gebra is imported, so INTROSPECTION-SPEC §1 rule 2 is checked rather than reviewed;
    nothing resolves a name or opens a connection at any point, imports included; and nothing
    so much as constructs a socket once gebra's own work starts. Attempts are recorded before
    raising, so a swallowed exception still fails the run.

    **One residual, named rather than implied.** During the import phase socket *construction*
    is counted, not refused — importing the substrate runs urllib3's own IPv6 capability
    probe, which builds a loopback socket and closes it without connecting. The child reports
    that count rather than collecting it silently, and deliberately does not gate on it: the
    number belongs to whichever third-party import ran a probe.
    """
    finished = _run_guarded()
    assert finished.returncode == 0, finished.stderr
    assert "WA07-TRIP" not in finished.stderr
    assert "import-phase sockets constructed:" in finished.stdout
    assert finished.stdout.strip().endswith("[]")


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created on the snapshot path"),
        ("socket.getaddrinfo('example.invalid', 443)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 443))\n", "create_connection was reached"),
        (
            "StateGraph.compile(tb.build_travel_booking_agent())\n",
            "StateGraph.compile was reached",
        ),
    ],
)
def test_the_guarded_run_is_armed(probe: str, expected: str) -> None:
    """A guard nobody trips proves nothing — each raiser the claim rests on is fired.

    Matched on the raiser's **full** message rather than a substring, so a control cannot
    drift onto a different raiser than the one the claim rests on and still look green.
    """
    finished = _run_guarded(probe)
    assert finished.returncode != 0
    assert "WA07-TRIP" in finished.stderr
    assert expected in finished.stderr


def test_a_swallowed_attempt_still_fails_the_run() -> None:
    """The record-before-raise design, exercised: swallowing the exception does not help.

    A path that reached a network primitive inside a ``try/except`` would raise nothing a
    caller could see, so each raiser appends to ``attempts`` *before* raising and the child
    prints that list last. The probe runs to completion — exit 0 — and the ledger it printed
    is what fails the assertion here.
    """
    finished = _run_guarded(
        "try:\n    socket.getaddrinfo('example.invalid', 443)\nexcept Exception:\n    pass\n"
    )

    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip().endswith("['getaddrinfo']")


def test_the_guarded_run_would_see_a_node_body_run() -> None:
    """The child's ledger leg is live too: firing a body there fails that run.

    The probe is appended *before* ``_REPORT``, which is where the child's
    ``assert tb.TRIPPED == []`` lives, so this exercises that assertion and not only the
    sentinel's raise. The swallowed form is what the record-before-raise ledger is for.
    """
    fired = _run_guarded("tb.classify_request({})\n")
    assert fired.returncode != 0
    assert "TravelBookingSentinelError" in fired.stderr

    swallowed = _run_guarded("try:\n    tb.book_flight({})\nexcept BaseException:\n    pass\n")
    assert swallowed.returncode != 0
    assert "travel-booking.book_flight" in swallowed.stderr


def test_the_no_network_client_leg_is_armed_too() -> None:
    """The one leg no socket probe can arm: importing the module the guard keeps out.

    ``assert "langgraph.pregel.remote" not in sys.modules`` is a claim about an *import*, and
    a substrate import opens no connection — so none of the raisers above can turn it red. It
    gets its own probe, the same way ``tests/lineage/test_engine.py`` arms the ``sys.modules``
    half of its guard separately from the network half.
    """
    finished = _run_guarded("import langgraph.pregel.remote\n")

    assert finished.returncode != 0
    assert "AssertionError" in finished.stderr


#: The closure probe: a fresh interpreter that imports **only** ``gebra.snapshot`` and reports
#: what that pulled in. Separate from the guarded child on purpose — there, the child's own
#: ``from langgraph.graph.state import StateGraph`` (needed to arm ``compile``) would satisfy
#: any "langgraph is imported" assertion regardless of what gebra did.
_CLOSURE_PROBE = """
import sys

import gebra.snapshot

print("langgraph", "langgraph" in sys.modules)
print("remote", "langgraph.pregel.remote" in sys.modules)
"""

#: The same probe for the store, whose own tripwire asserts the opposite. Run here as the
#: control: without it, "importing gebra.snapshot imports the substrate" would be a claim about
#: this interpreter rather than about this package.
_STORE_CLOSURE_PROBE = """
import sys

import gebra.store
import gebra.diff
import gebra.versioning
import gebra.lineage

print("langgraph", "langgraph" in sys.modules)
"""


def test_importing_the_engine_imports_the_substrate_and_no_network_client() -> None:
    """What "wired to extract" costs, measured rather than assumed — with its own control.

    ``import gebra.snapshot`` pulls the extractor and with it langgraph, which is the stated
    consequence in this package's docstring and in ``tests/never_invokes_audit.md`` §4. The
    second child is what makes that a measurement of *this* package: the store, diff, version
    and lineage engines together pull no langgraph at all, so the difference is attributable.
    Neither child imports the substrate itself. What the engine does **not** pull either way is
    ``langgraph.pregel.remote``, the one substrate module carrying a network client.
    """
    engine = subprocess.run(
        [sys.executable, "-c", _CLOSURE_PROBE],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )
    siblings = subprocess.run(
        [sys.executable, "-c", _STORE_CLOSURE_PROBE],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert engine.returncode == 0, engine.stderr
    assert "langgraph True" in engine.stdout
    assert "remote False" in engine.stdout
    assert siblings.returncode == 0, siblings.stderr
    assert "langgraph False" in siblings.stdout
