"""The rendering layer's WA-07 tripwire — the claim its docstrings make, enforced.

Every module of ``gebra.report`` states that it imports no langgraph, executes nothing and
opens no socket. This is that statement as a test, in the shape ``tests/verify/test_base.py``
already uses for the validator lane: a fresh interpreter with ``socket.socket`` and
``socket.getaddrinfo`` replaced by raisers that record before raising, then ``import
gebra.report``.

Two things make it worth having beyond the validator lane's own copy. The rendering layer is
the first part of the package to depend on `rich` (PD-031), so this pins that dependency as
hermetic too — a future `rich` that reached for the network on import would fail here rather
than in a user's CI. And the SARIF projection writes a `$schema` **URI** into every log it
emits, which is exactly the shape of string that invites someone to fetch it later; this test
is what says the package never does.

Stdlib module *presence* is deliberately not asserted, for the reason VAL-13 recorded: `socket`
enters the closure through version-dependent stdlib internals with no network involved, so
asserting its absence tests interpreter internals while the tripwires catch what WA-07 actually
forbids.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

from gebra.verify import WEDGE_SLUGS, validator_for
from gebra.verify.properties.dataflow_completeness import check_dataflow_completeness
from gebra.verify.properties.determinism_replay import check_determinism_replay
from gebra.verify.properties.effect_safety import check_effect_safety
from gebra.verify.properties.graph_well_formed import check_graph_well_formed
from gebra.verify.properties.termination_witness import check_termination_witness

#: ``tests/report/`` -> the repository root, so a subprocess resolves ``tests.report`` the way
#: the parent process does however pytest was invoked.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The wedge validators as the package registers them at import.
_SHIPPED = {
    "graph-well-formed": check_graph_well_formed,
    "termination-witness": check_termination_witness,
    "dataflow-completeness": check_dataflow_completeness,
    "effect-safety": check_effect_safety,
    "determinism-replay": check_determinism_replay,
}


def test_importing_the_rendering_layer_pulls_in_no_substrate_and_opens_no_socket() -> None:
    """WA-07 for `gebra.report` and, with it, for `rich`."""
    script = (
        "import socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created while importing gebra.report')\n"
        "def _trip_dns(*a, **k):\n"
        "    attempts.append('getaddrinfo'); print('WA07-TRIP', file=sys.stderr)\n"
        "    raise AssertionError('DNS resolved while importing gebra.report')\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip_dns\n"
        "import gebra.report\n"
        "print([m for m in sys.modules if m.split('.')[0] in\n"
        "       {'langgraph', 'langchain', 'langchain_core', 'networkx'}] + attempts)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_rendering_a_report_opens_no_socket() -> None:
    """Not only the import: the surfaces themselves, including the one that writes a URI."""
    script = (
        "import socket, sys\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created while rendering')\n"
        "def _trip_dns(*a, **k):\n"
        "    print('WA07-TRIP', file=sys.stderr)\n"
        "    raise AssertionError('DNS resolved while rendering')\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip_dns\n"
        "from tests.report.variants import CASES\n"
        "from gebra.report import REPORT_FORMATS, render\n"
        "for case in CASES:\n"
        "    for surface in REPORT_FORMATS:\n"
        "        assert render(case.report, surface)\n"
        "print('rendered', len(CASES))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("rendered "), completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_variant_catalog_restores_the_shipped_validators() -> None:
    """``variants.py`` stubs the wedge five at import; a leak would silently re-verdict every
    test collected after it, and still go green. So the restoration is asserted, not assumed."""
    for slug in WEDGE_SLUGS:
        assert validator_for(slug) is _SHIPPED[slug], f"{slug} is still stubbed"
