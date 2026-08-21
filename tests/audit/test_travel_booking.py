"""SD-07's two halves over the live travel-booking agent — the real occupant, audited.

``tests/audit/test_export.py`` states acceptance box 1 over whole hand-built stores, which is
where "every stored version" is exercised at scale; this file is the other kind of evidence,
and brief D-11's DoD line asks for it in terms: "each version has an exported JSON property
report". The IR here is not hand-built — it comes out of the extractor, off the shared TE-05
agent, into a store, and back out as an audit artifact.

Three claims:

1. **The store's version of the agent exports the §6 snapshot profile**, with the digest in the
   export equal to a *freshly recomputed* digest of the agent rather than to what the file says
   about itself.
2. **Freshness answers both ways over real extractions**, and agrees with the recorder on both:
   fresh ⇒ :func:`gebra.snapshot.snapshot` records nothing; stale ⇒ it records, under the label
   whose counters are the ones the freshness message named.
3. **Nothing in the agent runs** (WA-07). Every node body and router raises if called — the
   added ``audit_trail`` node of ``tests/audit/agents.py`` included — so the ledger is asserted
   empty on entry to and exit from every test, and the whole extract → store → export →
   freshness path is run again in a fresh interpreter where name resolution, connection opening
   and ``StateGraph.compile`` all raise.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from gebra import extract
from gebra.audit import Freshness, export_store, export_version, freshness, read_export
from gebra.ir.canonical import graph_version
from gebra.snapshot import SnapshotAction, snapshot
from gebra.store import REPORT_SUFFIX, SnapshotStore
from gebra.verify import PROPERTY_SLUGS, REPORT_FORMAT
from gebra.versioning import Component
from tests.audit.agents import AUDIT_NODE, build_travel_booking_agent_with_audit
from tests.sample_workflows import travel_booking as tb

if TYPE_CHECKING:
    from gebra.ir import WorkflowIR

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The reference a caller who knows what it imported would record (CLI-SPEC §2.1), and — since
#: the export reads it back off the store — what ``subject.source`` says in the audit artifact.
SOURCE = "tests.sample_workflows.travel_booking:build_travel_booking_agent"


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Any:
    """The agent is read, never run — asserted on entry to and exit from every test."""
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """A store holding travel-booking v1 and nothing else."""
    store = SnapshotStore.for_project(tmp_path)
    snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)
    return store


def _agent_ir() -> WorkflowIR:
    """A fresh extraction of v1 — recomputed, never read back off a file."""
    return extract(tb.build_travel_booking_agent()).ir


# ── The export, over the real agent ──────────────────────────────────────────────────────


def test_the_agents_stored_version_exports_the_snapshot_profile(store: SnapshotStore) -> None:
    """Box 1 on the real occupant: the export names the version, hashes to the agent, and lands
    at the PD-012 path.

    The digest is asserted against ``graph_version`` of a **fresh extraction**, so a document
    that merely agreed with the file beside it would not pass. No literal digest is pinned: the
    extraction is a function of the installed substrate and this fixture is extracted on every
    cell of the frozen VERSION-COMPAT matrix.
    """
    outcome = export_version(store, "1.0.0.0")

    assert outcome.path == store.report_path("1.0.0.0")
    assert outcome.path.name == f"1.0.0.0{REPORT_SUFFIX}"
    subject = outcome.report.subject
    assert subject is not None
    assert subject.input_mode == "snapshot"
    assert subject.version == "1.0.0.0"
    assert subject.graph_version == graph_version(_agent_ir())
    assert subject.source == SOURCE
    assert subject.extractor_version is None
    assert outcome.report.report_format == REPORT_FORMAT
    assert tuple(entry.property for entry in outcome.report.properties) == PROPERTY_SLUGS

    assert read_export(store, "1.0.0.0") == outcome.report


def test_the_agents_export_records_a_clean_wedge_run(store: SnapshotStore) -> None:
    """What the audit artifact actually says about this agent, rather than only that it is
    well-formed: TE-05's fixture is clean on the wedge five, so the stored version's gate is a
    pass and the snapshot is eligible under PROPERTY-CATALOG-SPEC §0.2."""
    report = export_version(store, "1.0.0.0").report

    assert report.gate.exit_code == 0
    assert report.gate.counts.fatal == 0
    assert report.gate.snapshot_eligible
    assert report.best_effort == ()
    assert report.error is None


def test_every_stored_version_of_an_evolved_agent_exports(store: SnapshotStore) -> None:
    """Two real versions, both exported — the "per-version" shape of D-11 deliverable 5 on live
    extractions rather than on hand-built IR."""
    second = snapshot(build_travel_booking_agent_with_audit(), store=store, source=SOURCE)
    assert second.action is SnapshotAction.RECORDED

    outcomes = export_store(store)

    assert tuple(outcome.version for outcome in outcomes) == store.versions()
    assert len(outcomes) == 2
    for outcome in outcomes:
        assert outcome.path.is_file()
        assert read_export(store, outcome.version).subject == outcome.report.subject
    later = outcomes[1].report.subject
    assert later is not None
    assert later.graph_version == graph_version(extract(build_travel_booking_agent_with_audit()).ir)


# ── Freshness, over the real agent ───────────────────────────────────────────────────────


def test_the_unchanged_agent_is_fresh_against_its_own_snapshot(store: SnapshotStore) -> None:
    """The extraction is done a second time, from a second build of the agent, so this is a
    freshness answer about the *definition* rather than about an object handed in twice."""
    outcome = freshness(_agent_ir(), store=store)

    assert outcome.fresh
    assert outcome.version == "1.0.0.0"
    assert outcome.diff is None


def test_the_edited_agent_is_stale_and_says_which_counters_moved(store: SnapshotStore) -> None:
    """**Acceptance box 2's subject**: the agent changed and nobody re-snapshotted.

    One added node on a new path — the mildest change brief D-11 calls a safe extension — and
    the check still notices, naming S and F and the node itself.
    """
    outcome = freshness(extract(build_travel_booking_agent_with_audit()).ir, store=store)

    assert outcome.state is Freshness.STALE
    assert outcome.moved == (Component.S, Component.F)
    assert outcome.diff is not None
    assert outcome.diff.topology.nodes.added == (AUDIT_NODE,)
    assert "changed and was not re-snapshotted" in outcome.summary()


def test_the_check_agrees_with_the_recorder_on_the_live_agent(store: SnapshotStore) -> None:
    """Fresh ⇒ the recorder records nothing; stale ⇒ it records, moving the counters the check
    named. A check that disagreed with the recorder would be a red CI with no action that
    clears it, so the two are held together here rather than reasoned about."""
    assert freshness(_agent_ir(), store=store).fresh
    unchanged = snapshot(tb.build_travel_booking_agent(), store=store, source=SOURCE)
    assert unchanged.action is SnapshotAction.UNCHANGED
    assert unchanged.version == "1.0.0.0"

    stale = freshness(extract(build_travel_booking_agent_with_audit()).ir, store=store)
    assert not stale.fresh
    recorded = snapshot(build_travel_booking_agent_with_audit(), store=store, source=SOURCE)

    assert recorded.action is SnapshotAction.RECORDED
    assert recorded.bump_class == frozenset(stale.moved)
    assert recorded.version == "1.1.1.0"
    assert freshness(extract(build_travel_booking_agent_with_audit()).ir, store=store).fresh


def test_a_project_that_has_never_snapshotted_is_not_stale(tmp_path: Path) -> None:
    outcome = freshness(_agent_ir(), store=SnapshotStore.for_project(tmp_path))

    assert outcome.state is Freshness.UNSNAPSHOTTED
    assert "record the first one" in outcome.summary()


# ── WA-07: the whole audit path over the live agent runs nothing ─────────────────────────

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
        raise AssertionError("a socket was created on the audit path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

from langgraph.graph.state import StateGraph

StateGraph.compile = _record("StateGraph.compile")

from gebra import extract
from gebra.audit import Freshness, export_store, freshness, read_export
from gebra.snapshot import SnapshotAction, snapshot
from gebra.store import SnapshotStore
from tests.audit.agents import AUDIT_NODE, build_travel_booking_agent_with_audit
from tests.sample_workflows import travel_booking as tb

# The import phase is bounded, not excluded — the same residual `tests/snapshot` records. From
# here the run is gebra's own work, and socket construction raises too.
assert attempts == [], attempts
socket.socket = _TripSocket

store = SnapshotStore.for_project(tempfile.mkdtemp())
assert snapshot(tb.build_travel_booking_agent(), store=store, source="child:agent").version == \
    "1.0.0.0"

# The export, over the store's only version, written and read back.
exports = export_store(store)
assert [outcome.version for outcome in exports] == ["1.0.0.0"], exports
document = read_export(store, "1.0.0.0")
assert document.subject is not None
assert document.subject.input_mode == "snapshot"
assert document.subject.version == "1.0.0.0"
# Identity, not only success: the export is pinned to *this* agent's digest, recomputed from a
# fresh extraction, so a run that silently stopped reaching the agent fails rather than passes.
assert document.subject.graph_version == extract(tb.build_travel_booking_agent()).graph_version()

# Freshness, both ways, over live extractions.
assert freshness(extract(tb.build_travel_booking_agent()).ir, store=store).fresh
edited = freshness(extract(build_travel_booking_agent_with_audit()).ir, store=store)
assert edited.state is Freshness.STALE, edited
assert edited.diff is not None and edited.diff.topology.nodes.added == (AUDIT_NODE,), edited

"""

#: Run last, after any probe — an assertion a probe should be able to trip has to come after it.
#: The ledger leg catches a probe that fired a node body; the ``langgraph.pregel.remote`` leg is
#: the one substrate module carrying a network client (DEC-19 route 6) and has its own probe,
#: since no socket raiser can arm an import; the socket count is *reported* rather than gated,
#: because the number belongs to whichever third-party import ran a capability probe.
#: Every assertion a parent greps stderr for must carry a message naming what it caught: before
#: Python 3.13, a ``-c`` child's traceback renders no source line, so a bare ``assert`` reports
#: only ``AssertionError`` and the name never reaches stderr.
_REPORT = (
    "assert tb.TRIPPED == [], tb.TRIPPED\n"
    "assert 'langgraph.pregel.remote' not in sys.modules, "
    "'langgraph.pregel.remote entered sys.modules'\n"
    "print('import-phase sockets constructed:', len(built))\n"
    "print(attempts)\n"
)


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    """Run the child with ``PYTHONOPTIMIZE`` pinned off — its whole claim is in ``assert``s."""
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_whole_audit_path_runs_nothing_and_opens_no_socket() -> None:
    """WA-07 for this card's paths, in a fresh interpreter and over the path the card ships.

    Snapshot → export → read back → freshness, both answers, over the sentinel-guarded agent
    and its edited variant, with every node body and router raising if called,
    ``StateGraph.compile`` raising from before gebra is imported, and nothing resolving a name
    or opening a connection at any point. Attempts are recorded before raising, so a swallowed
    exception still fails the run.

    The one residual is named rather than implied: during the import phase socket
    *construction* is counted, not refused — importing the substrate runs urllib3's own IPv6
    capability probe — and the child reports that count instead of collecting it silently.

    All five raisers have their own armed control in ``test_the_guarded_run_is_armed`` below,
    matched on each raiser's full message.
    """
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().endswith("[]"), completed.stdout
    assert "import-phase sockets constructed:" in completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created on the audit path"),
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
    """A guard nobody trips proves nothing — **every** raiser the claim rests on is fired.

    One row per raiser, not one per raiser *class*: ``StateGraph.compile`` is the whole of the
    INTROSPECTION-SPEC §1 rule 2 evidence on this path and socket construction is the whole of
    the post-import network claim, so a table that covered only the DNS raiser would leave the
    two load-bearing ones untested against a substrate that relocates ``compile`` or a refactor
    that stops installing the raiser. Matched on the raiser's **full** message rather than a
    substring, so a control cannot drift onto a different raiser than the one it names and
    still look green. This is SD-03's table, ported: the two children arm the same five things.
    """
    completed = _run_guarded(probe)

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr
    assert expected in completed.stderr


def test_the_guard_trips_when_a_node_body_is_executed() -> None:
    """The armed control for the ledger leg, which no network probe can arm.

    The added ``audit_trail`` node is armed like the fixture's own bodies, and the probe
    *swallows* the exception — so what fails the child is the trailing ``assert tb.TRIPPED ==
    []``, which is the record-before-raise design exercised rather than reviewed.
    """
    completed = _run_guarded(
        "from tests.audit.agents import _write_audit_trail\n"
        "try:\n"
        "    _write_audit_trail(None)\n"
        "except BaseException:\n"
        "    pass\n"
    )

    assert completed.returncode != 0
    assert "audit_trail" in completed.stderr


def test_the_guard_trips_when_the_network_client_module_is_imported() -> None:
    """The armed control for the ``sys.modules`` leg, which no socket probe can arm either: an
    import opens no connection, so only the trailing assertion catches it."""
    completed = _run_guarded("import langgraph.pregel.remote\n")

    assert completed.returncode != 0
    assert "langgraph.pregel.remote" in completed.stderr
