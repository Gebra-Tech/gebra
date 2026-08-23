"""WA-07 over the defect family: every body armed, the whole catch run under the guard.

The variants reuse v1's sentinel bodies wherever the defect story says "unchanged" and add
six of their own; the arming test walks every variant's built graph and fires the whole
collected surface — a tripwire nobody trips proves nothing — pinning the fired label sets
to both modules' expected names. The guarded child then re-runs the DoD's catch leg in a
fresh interpreter where name resolution, connection opening and ``StateGraph.compile``
raise from before gebra is imported, and socket *construction* raises once gebra's own
work begins: all five defects are caught, with their condition IDs at their loci, in an
interpreter where nothing could have run — the acceptance claim in a hostile interpreter
rather than a smoke test beside it. Each raiser has an armed control matched on its
**full**, DoD-specific message, so no control can drift onto the evolution child's raisers
and still look green.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.sample_workflows import travel_booking as tb
from tests.sample_workflows import travel_booking_defects as dv

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The six bodies this fixture module defines — five node twins and one router.
DEFECT_BODY_LABELS = frozenset(
    f"travel-booking-defects.{name}"
    for name in (
        "replan_unwitnessed",
        "book_flight_unprotected",
        "classify_request_temperature_unpinned",
        "dispatch_bookings",
        "book_leg",
        "route_legs",
    )
)

#: Every v1 body some variant reuses — all nine nodes and both routers reach at least one
#: variant's graph, so the collected surface is the whole family.
REUSED_V1_LABELS = frozenset(
    f"travel-booking.{name}"
    for name in (
        "classify_request",
        "availability_check",
        "replan",
        "book_flight",
        "book_hotel",
        "check_booking",
        "compile_itinerary",
        "notify_traveler",
        "release_hotel_hold",
        "route_availability",
        "route_booking",
    )
)


def test_every_body_reachable_from_a_variant_is_armed() -> None:
    """Fire the union of every variant's callables — twins and reused v1 bodies alike.

    The callables come off the built graphs and are deduplicated by underlying function
    identity, so a node added to any variant and forgotten here is still fired, once, and
    the fired label set is pinned to the two modules' expected names. The ledger is
    restored at the end, the way the TE-05 arming test does.
    """
    seen: dict[int, Any] = {}
    for defect in dv.DEFECTS:
        builder = defect.build()
        callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
        callables += [spec.path for group in builder.branches.values() for spec in group.values()]
        for runnable in callables:
            function = runnable
            while hasattr(function, "func"):
                function = function.func
            seen.setdefault(id(function), function)

    fired = 0
    for function in seen.values():
        before = len(tb.TRIPPED)
        with pytest.raises(tb.TravelBookingSentinelError):
            function({})
        assert len(tb.TRIPPED) == before + 1
        fired += 1

    assert fired == len(DEFECT_BODY_LABELS) + len(REUSED_V1_LABELS)  # 6 + 11
    assert set(tb.TRIPPED) == DEFECT_BODY_LABELS | REUSED_V1_LABELS
    del tb.TRIPPED[:]


#: The guarded child: v1 verified clean and all five defects caught — condition ID, locus,
#: gate, and the R2 strict leg — in a fresh interpreter under the full raiser set. Socket
#: construction is counted rather than refused during imports for the reason
#: ``tests/extraction/test_dispatch.py`` records (urllib3's IPv6 capability probe), and
#: raises once gebra's own work begins.
_TRIPWIRE = """
import socket, sys

attempts = []
built = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached on the dod path")
    return _seen


class _CountSocket(socket.socket):
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the dod path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

from langgraph.graph.state import StateGraph

StateGraph.compile = _record("StateGraph.compile")

from gebra import extract
from gebra.verify import PropertyReport, RunPolicy, StrictPolicy, verify
from tests.sample_workflows import travel_booking as tb
from tests.sample_workflows import travel_booking_defects as dv

# The import phase is bounded, not excluded — see the note on the constant. From here the
# run is gebra's own work, and socket construction raises too.
assert attempts == [], attempts
socket.socket = _TripSocket

healthy = verify(extract(tb.build_travel_booking_agent()).ir)
assert healthy.gate.exit_code == 0 and healthy.gate.outcome == "pass", healthy.gate

for defect in dv.DEFECTS:
    envelope = extract(defect.build())
    assert envelope.warnings == (), (defect.name, envelope.warnings)
    report = verify(envelope.ir)
    outcome = report.outcome_for(defect.property)
    assert isinstance(outcome, PropertyReport) and outcome.result == "fail", defect.name
    failure = outcome.failure
    assert failure.property_condition == defect.condition, (defect.name, failure)
    if len(defect.locus_nodes) > 1:
        assert set(failure.location.nodes) == set(defect.locus_nodes), defect.name
    else:
        assert failure.location.node == defect.locus_nodes[0], defect.name
    assert report.gate.exit_code == defect.default_exit, defect.name
    if defect.strict_slug is not None:
        strict = verify(
            envelope.ir,
            RunPolicy(
                strict=StrictPolicy(mode="per-property", properties=(defect.strict_slug,))
            ),
        )
        assert strict.gate.exit_code == 1, defect.name
"""

#: Run last, after any probe — an assertion a probe should be able to trip has to come
#: after the probe. The ledger leg, the no-network-client leg (which no socket raiser can
#: arm, so it has its own probe below), and the import-phase socket count, reported.
_REPORT = (
    "assert tb.TRIPPED == [], tb.TRIPPED\n"
    "assert 'langgraph.pregel.remote' not in sys.modules\n"
    "print('import-phase sockets constructed:', len(built))\n"
    "print(attempts)\n"
)


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    """Run the child with ``PYTHONOPTIMIZE`` pinned off — its claims live in ``assert``s."""
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_five_catches_hold_in_a_guarded_interpreter() -> None:
    """The whole catch leg — six extractions, eleven verify runs — with nothing runnable.

    Every body raises if called; ``StateGraph.compile`` raises from before gebra is
    imported (every subject is the builder, so nothing on this path ever compiles);
    nothing resolves a name or opens a connection; and once gebra's work starts,
    constructing a socket raises too. The child re-asserts each catch under the guard.
    """
    finished = _run_guarded()
    assert finished.returncode == 0, finished.stderr
    assert "WA07-TRIP" not in finished.stderr
    assert "import-phase sockets constructed:" in finished.stdout
    assert finished.stdout.strip().endswith("[]")


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created on the dod path"),
        ("socket.getaddrinfo('example.invalid', 443)\n", "getaddrinfo was reached on the dod path"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached on the dod path"),
        (
            "socket.create_connection(('example.invalid', 443))\n",
            "create_connection was reached on the dod path",
        ),
        (
            "StateGraph.compile(dv.build_defect_5_fanout())\n",
            "StateGraph.compile was reached on the dod path",
        ),
    ],
)
def test_the_guarded_run_is_armed(probe: str, expected: str) -> None:
    """A guard nobody trips proves nothing — each raiser the claim rests on is fired,
    matched on its full, DoD-specific message so no control can alias another suite's."""
    finished = _run_guarded(probe)
    assert finished.returncode != 0
    assert "WA07-TRIP" in finished.stderr
    assert expected in finished.stderr


def test_a_swallowed_attempt_still_fails_the_run() -> None:
    """Record-before-raise, exercised: swallowing the exception does not help."""
    finished = _run_guarded(
        "try:\n    socket.getaddrinfo('example.invalid', 443)\nexcept Exception:\n    pass\n"
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip().endswith("['getaddrinfo']")


def test_the_guarded_run_would_see_a_new_body_run() -> None:
    """The ledger leg is live for this module's own twins, not only the reused bodies —
    in both the raising and the swallowed form."""
    fired = _run_guarded("dv.book_leg({})\n")
    assert fired.returncode != 0
    assert "TravelBookingSentinelError" in fired.stderr

    swallowed = _run_guarded(
        "try:\n    dv.dispatch_bookings({})\nexcept BaseException:\n    pass\n"
    )
    assert swallowed.returncode != 0
    assert "travel-booking-defects.dispatch_bookings" in swallowed.stderr


def test_the_no_network_client_leg_is_armed_too() -> None:
    """The one leg no socket probe can arm: importing the module the guard keeps out."""
    finished = _run_guarded("import langgraph.pregel.remote\n")
    assert finished.returncode != 0
    assert "AssertionError" in finished.stderr
