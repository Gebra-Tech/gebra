"""WA-07 for the CLI's live-target path — CLI-SPEC §0.5 item 3, in the shape it fixes.

Two layers, because the claim has two halves.

**The §0.5 item 3 arms, through the entry point.** Every in-process test drives
:func:`gebra.cli.main` — the function the console script names — over
:mod:`tests.sample_workflows.sentinel_cli`, and asserts on the module's **ledgers**, never
on the exit code (§3.4 makes an escaping exception a specified exit ``2``, so the code
cannot distinguish an execution from a refusal; the record can). The four armed points are
the four the spec lists: node callables in the resolved graph, the zero-argument
non-factory attribute without ``--call``, the argument-needing callable under ``--call``,
and the import-time marker — observed, because §2.4 step 1's "top-level code runs" is a
stated concession, not a hope.

**The strong-form guarded children.** The CLI is a seam that hands a live workflow object
to the extractor — the same category as the snapshot engine — so the whole path runs again
in fresh interpreters: one with name resolution, connection opening and
``StateGraph.compile`` raising (and socket construction counted through the import phase,
then refused — the same urllib3 capability-probe residual every guarded child in this suite
records), and one with the **substrate unimportable at all**, which is what holds
``gebra.cli``'s lazy extractor import to its word: verifying an IR document must reach no
langgraph import on any code path. Each raiser has an armed control matched on its full
message, plus the one leg no socket probe can arm — a probe that fires a node body and
swallows the sentinel, so the record-before-raise ledger is what fails the child.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from gebra.cli import main
from tests.sample_workflows import sentinel_cli

REPO_ROOT = Path(__file__).parent.parent.parent

MODULE = "tests.sample_workflows.sentinel_cli"


@pytest.fixture(autouse=True)
def _clean_ledgers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear the ledgers on entry — the idiom for a session-global ledger another test
    (the armed control below) fills on purpose — and make the module importable by the
    reference the tests spell."""
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    sentinel_cli.TRIPPED.clear()
    sentinel_cli.FACTORY_CALLS.clear()
    yield


def _run(*argv: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ── The §0.5 item 3 arms, one by one ─────────────────────────────────────────────────────


def test_resolving_a_module_level_graph_executes_no_node_body(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 1: the graph's node callables. Extraction reads them; the ledger stays empty."""
    code, _, _ = _run("verify", f"{MODULE}:graph", capsys=capsys)
    assert sentinel_cli.TRIPPED == []
    assert sentinel_cli.FACTORY_CALLS == []
    assert code == 0


def test_without_call_no_attribute_is_ever_called(capsys: pytest.CaptureFixture[str]) -> None:
    """Arm 2: a zero-argument callable that is not a factory is refused, not probed, not
    called — `gebra verify pkg:main` cannot start an application by accident (§2.4)."""
    code, _, err = _run("verify", f"{MODULE}:launch_app", capsys=capsys)
    assert sentinel_cli.TRIPPED == []
    assert code == 2
    assert "did not call it" in err
    assert "--call" in err


def test_call_makes_exactly_one_call_and_extraction_still_runs_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """§2.4: with --call, one call with no arguments — and the returned graph's armed
    nodes still never run under the extraction that follows."""
    code, _, _ = _run("verify", "--call", f"{MODULE}:build_graph", capsys=capsys)
    assert sentinel_cli.FACTORY_CALLS == ["build_graph"]
    assert sentinel_cli.TRIPPED == []
    assert code == 0


def test_a_callable_needing_arguments_is_the_exit_2_refusal_with_the_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 3: no signature probe softens the call — it is made with no arguments, the
    TypeError is reported, and the armed body never ran."""
    code, _, err = _run("verify", "--call", f"{MODULE}:needs_args", capsys=capsys)
    assert code == 2
    assert sentinel_cli.TRIPPED == []
    assert "TypeError" in err
    assert "no arguments" in err


def test_the_import_time_concession_is_observed_not_assumed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Arm 4: §2.4 step 1 — importing the named module runs its top-level code, and the
    marker that code left is the observation."""
    _run("verify", f"{MODULE}:graph", capsys=capsys)
    assert sentinel_cli.IMPORTED == [MODULE]


def test_the_cli_performs_the_import_itself_on_a_fresh_module(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arm 4, the stronger half: with the module absent from ``sys.modules``, the CLI's own
    resolution is what imports it — the fresh module object's marker says its top-level code
    ran exactly once, and its armed bodies still never did. (``monkeypatch.delitem`` restores
    the original module afterwards, so the session's ledger bindings stay coherent.)"""
    monkeypatch.delitem(sys.modules, MODULE)
    code, _, _ = _run("verify", f"{MODULE}:graph", capsys=capsys)
    fresh = sys.modules[MODULE]
    assert fresh is not sentinel_cli, "the CLI was handed the cached module, not a fresh one"
    assert fresh.IMPORTED == [MODULE]
    assert fresh.TRIPPED == []
    assert code == 0


def test_a_dict_attribute_is_refused_naming_what_was_found(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, err = _run("verify", f"{MODULE}:not_a_workflow", capsys=capsys)
    assert code == 2
    assert "builtins:dict" in err
    assert sentinel_cli.TRIPPED == []


# ── The controls: a tripwire nobody trips proves nothing ─────────────────────────────────


def test_the_sentinel_records_before_raising() -> None:
    with pytest.raises(sentinel_cli.CliSentinelError):
        sentinel_cli.launch_app()
    assert sentinel_cli.TRIPPED == ["launch_app"]


def test_the_sentinel_is_outside_every_except_exception_guard() -> None:
    assert not issubclass(sentinel_cli.CliSentinelError, Exception)


# ── The guarded children ─────────────────────────────────────────────────────────────────

#: The live-path child: sockets and ``StateGraph.compile`` armed, the whole CLI run twice
#: (a module-level graph, then a ``--call`` factory) through ``main()`` itself.
_LIVE_TRIPWIRE = """
import socket, sys

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
        raise AssertionError("a socket was created on the CLI verify path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

from langgraph.graph.state import StateGraph

StateGraph.compile = _record("StateGraph.compile")

import io, contextlib
from gebra.cli import main
import tests.sample_workflows.sentinel_cli as sc

# The import phase is bounded, not excluded — the count is reported below. From here on
# the run is the CLI's own work, and socket construction raises too.
assert attempts == [], attempts
socket.socket = _TripSocket

out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["verify", "tests.sample_workflows.sentinel_cli:graph"])
assert code == 0, (code, err.getvalue())
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["verify", "--call", "tests.sample_workflows.sentinel_cli:build_graph"])
assert code == 0, (code, err.getvalue())
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["verify", "tests.sample_workflows.sentinel_cli:launch_app"])
assert code == 2, (code, out.getvalue())

"""

#: Run last, after any probe, so a probe can fail each of these legs.
_LIVE_REPORT = (
    "assert sc.TRIPPED == [], sc.TRIPPED\n"
    "assert sc.FACTORY_CALLS == ['build_graph'], sc.FACTORY_CALLS\n"
    "assert sc.IMPORTED == ['tests.sample_workflows.sentinel_cli'], sc.IMPORTED\n"
    "assert 'langgraph.pregel.remote' not in sys.modules\n"
    "print('import-phase sockets constructed:', len(built))\n"
    "print(attempts)\n"
)


def _run_live_child(probe: str = "") -> subprocess.CompletedProcess[str]:
    """The guarded child, with ``PYTHONOPTIMIZE`` pinned off so its asserts are real."""
    return subprocess.run(
        [sys.executable, "-c", _LIVE_TRIPWIRE + probe + _LIVE_REPORT],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_whole_live_path_runs_nothing_and_opens_no_socket() -> None:
    """The strong form for this card's seam: resolution, the ``--call`` opt-in, the
    refusal, and both extractions — under raisers, in a fresh interpreter."""
    finished = _run_live_child()
    assert finished.returncode == 0, finished.stderr
    assert "WA07-TRIP" not in finished.stderr
    assert "import-phase sockets constructed:" in finished.stdout
    assert finished.stdout.strip().endswith("[]")


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created on the CLI verify path"),
        ("socket.getaddrinfo('example.invalid', 443)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 443))\n", "create_connection was reached"),
        ("StateGraph.compile(sc.graph)\n", "StateGraph.compile was reached"),
    ],
)
def test_the_live_guard_is_armed(probe: str, expected: str) -> None:
    """Each raiser fired once, matched on its full message so a control cannot drift."""
    finished = _run_live_child(probe)
    assert finished.returncode != 0
    assert "WA07-TRIP" in finished.stderr
    assert expected in finished.stderr


def test_the_ledger_leg_is_armed_against_swallowed_sentinels() -> None:
    """The leg no socket probe can arm: fire a node body, swallow the sentinel — the
    record-before-raise ledger fails the child anyway."""
    probe = "try:\n    sc.fetch_context({'query': 'q'})\nexcept BaseException:\n    pass\n"
    finished = _run_live_child(probe)
    assert finished.returncode != 0
    assert "fetch_context" in finished.stderr


#: The document-path child: the substrate is unimportable at all, and the whole
#: ir-document run — resolution, all thirteen properties, all three surfaces — completes.
_DOCUMENT_TRIPWIRE = """
import sys


class _SubstrateBlocker:
    prefixes = ("langgraph", "langchain", "langchain_core")

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.prefixes:
            print("WA07-SUBSTRATE " + fullname, file=sys.stderr)
            raise ImportError(
                "substrate import " + repr(fullname) + " blocked: the ir-document "
                "path must not need it"
            )
        return None


sys.meta_path.insert(0, _SubstrateBlocker())

import contextlib, io, tempfile
from pathlib import Path

from gebra.cli import main
from gebra.ir import write_ir
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore
from gebra.testing import load_fixture

fixture = "tests/fixtures/properties/mixed/10-all-properties-pass-healthy-research-pipeline.yaml"
scratch = Path(tempfile.mkdtemp())
document = scratch / "subject.ir.yaml"
ir = load_fixture(fixture).ir
write_ir(ir, document)

for surface in ("human", "json", "sarif"):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["verify", str(document), "--format", surface])
    assert code == 0, (surface, code, err.getvalue())

# The display legs (CLI-06): the whole §4.4 surface — a plain drawing, and one overlaid
# with a run report produced under this same blocker — completes with the substrate
# unimportable, which is what "display reaches no live object on any path" costs to hold.
report_path = scratch / "report.json"
out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["verify", str(document), "--format", "json", "--output", str(report_path)])
assert code == 0, (code, err.getvalue())
for argv in (
    ["display", str(document)],
    ["display", "--ir", str(document), "--report", str(report_path)],
):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    assert code == 0, (argv, code, err.getvalue())
    assert out.getvalue().startswith("%% gebra display:"), argv

# The snapshot leg: the store writes and reads under the same blocker, so the whole
# stored-version path — resolution, digest re-check, all thirteen properties — is held
# substrate-free too, not only claimed so.
store = SnapshotStore(scratch / ".gebra")
store.write(
    Snapshot.of(
        ir,
        version="1.0.0.0",
        extracted_from=ExtractedFrom(
            source="tests:cli-guarded-child",
            extractor_version="0.0.1.dev0",
            extracted_at="2026-08-21T00:00:00Z",
        ),
    )
)
out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["verify", "--snapshot", "1.0.0.0", "--store", str(store.path)])
assert code == 0, (code, err.getvalue())

out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = main(["display", "--snapshot", "1.0.0.0", "--store", str(store.path)])
assert code == 0, (code, err.getvalue())
assert out.getvalue().startswith("%% gebra display:")

"""

_DOCUMENT_REPORT = (
    "polluted = [name for name in sys.modules"
    " if name.split('.')[0] in ('langgraph', 'langchain', 'langchain_core')]\n"
    "assert polluted == [], polluted\n"
    "print('SUBSTRATE-FREE-OK')\n"
)


def _run_document_child(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _DOCUMENT_TRIPWIRE + probe + _DOCUMENT_REPORT],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_document_and_snapshot_paths_never_import_the_substrate() -> None:
    """The lazy extractor import held to its word: with langgraph unimportable, verifying
    an IR document completes on every surface, and a stored snapshot version verifies
    end to end — store write, digest-checked read, all thirteen properties."""
    finished = _run_document_child()
    assert finished.returncode == 0, finished.stderr
    assert "SUBSTRATE-FREE-OK" in finished.stdout
    assert "WA07-SUBSTRATE" not in finished.stderr


def test_the_substrate_blocker_is_armed() -> None:
    finished = _run_document_child("import langgraph\n")
    assert finished.returncode != 0
    assert "WA07-SUBSTRATE langgraph" in finished.stderr
    assert "blocked" in finished.stderr


# ── display: no live object on any path (CLI-06, §4.4) ───────────────────────────────────


def test_display_refuses_an_import_shaped_target_before_any_import(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`display` has no live-target mode, and the refusal is a *usage* error — decided by
    grammar alone, before resolution. The proof is on ``sys.modules``: the named module is
    absent afterwards, so no top-level code ran, no ledger could fill, and §0.5's "reaches
    no live object at all" is an observation rather than a claim."""
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    code, out, err = _run("display", f"{MODULE}:graph", capsys=capsys)
    assert code == 2
    assert out == ""
    assert "usage error" in err and "no live-target mode" in err
    assert MODULE not in sys.modules, "display imported the target it must refuse"
    assert sentinel_cli.TRIPPED == [] and sentinel_cli.FACTORY_CALLS == []


def test_display_refuses_the_import_selector_without_resolving_it(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """There is no ``--import`` on this verb (§4.4): the flag is an unknown option, and the
    would-be reference is never resolved — held on ``sys.modules`` exactly as above."""
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    code, out, err = _run("display", "--import", f"{MODULE}:graph", capsys=capsys)
    assert code == 2
    assert out == ""
    assert "unknown option '--import'" in err
    assert MODULE not in sys.modules
    assert sentinel_cli.TRIPPED == [] and sentinel_cli.FACTORY_CALLS == []
