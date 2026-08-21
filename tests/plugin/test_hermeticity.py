"""WA-07 tripwire for the pytest plugin, and acceptance box 2 — card TE-06.

The card asks for the plugin to be "importable without langgraph in fixture-only mode
(test-proven)". A transitive import can only be proven absent one way — in a fresh
interpreter where attempting it raises — so that is what happens here: a guarded child
installs a meta-path blocker over every substrate and provider package, replaces the socket
class and the two name-resolution entry points with raisers, and then runs **a whole pytest
session** inside that interpreter.

What runs inside the guard is not a smoke import. It is:

1. ``import gebra.pytest_plugin`` — the ``pytest11`` entry-point module, imported exactly the
   way pytest imports it at the start of every session, with the child reporting what that
   import pulled in;
2. an inner pytest session over a ``@pytest.mark.gebra`` marked function whose target is a
   :class:`~gebra.ir.WorkflowIR` read from an IR document — **fixture-only mode** — producing
   one item per wedge property, each running the whole ``resolve → verify → gate`` path;
3. an inner session over the ``gebra_workflow`` → ``gebra_graph`` → ``gebra_verification`` fixture
   surface on the same document, so both of the plugin's two surfaces are inside the guard
   rather than one.

The document is the **travel-booking agent's own IR** (TE-05), extracted in the parent — which
has the substrate — and handed to the child as JSON. So the claim is not about some minimal
graph: it is that the plugin verifies the card's own acceptance subject with langgraph
unimportable.

**The armed control is what makes the claim non-vacuous.** A guarded run that imports nothing
proves nothing unless something on the same path *would* have tripped it, and here the natural
one is the plugin's own other branch: hand the marker a target that is not a ``WorkflowIR``
and ``resolve_ir`` must reach the extractor, which reaches the substrate. The control child
does exactly that and asserts the blocker fired, the attempt was recorded, and the items
failed. Fixture-only mode reaches no substrate import **because** it takes the branch that
does not, and the other branch is shown to be the one that does.

Every raiser records its attempt *before* raising, so a ``try: import langgraph / except
ImportError: pass`` anywhere on the path still fails the run. There are **four** raisers — the
substrate-import blocker, socket construction, ``getaddrinfo`` and ``create_connection`` — and
each is tripped deliberately by :func:`test_each_blocker_is_armed`; the record-before-raise
ordering is armed separately, by the three tests that swallow the exception and read the
recorded attempt out of the payload instead of the exit code.

**Plugin autoload is off inside the child** (``PYTEST_DISABLE_PLUGIN_AUTOLOAD``), and the
plugin is loaded by ``-p gebra.pytest_plugin`` instead. Not to make the claim easier: the
other ``pytest11`` plugins installed in this environment include one that imports langchain,
and blocking it would say something about that plugin rather than about this one. That the
entry point auto-loads is a separate fact, asserted against the installed metadata in
``tests/plugin/test_plugin.py``.

**Residuals, named rather than implied.** The child blocks neither ``subprocess`` nor file
writes: it writes its own inner test files and the IR document, so a file-write blocker would
have to allow-list itself. ``subprocess`` is absent from the reported closure and the static
scan below keeps it absent. The guarded run proves hermeticity for the validators that are
*registered* — the wedge five — which is the same bound ``tests/testing/test_hermeticity.py``
records for the golden harness. And the static scan has two bounds of its own, stated because
the sentence "the other half of the dynamic blocker" would otherwise overstate it: it reads
only the ``gebra`` modules the child reported, not third-party ones, and it matches literal
``import``/``from`` statements, so a ``__import__("langgraph")`` would be invisible to it
(``importlib.import_module`` is caught, but only because ``_HAZARDOUS_IMPORT`` bans importing
``importlib`` at all). What it *does* catch beyond its name is function-local imports: the
pattern is anchored with ``^\\s*`` under ``MULTILINE``, so an indented one matches too.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gebra import extract
from gebra.ir import dump_json
from tests.sample_workflows import travel_booking

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A module-level import of a substrate package anywhere in the closure the child reports.
#: The child already refuses these dynamically; this catches a *lazy* path that would only
#: import under conditions the child did not happen to reach.
_SUBSTRATE_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:langgraph|langchain|langchain_core|langsmith)\b", re.MULTILINE
)

#: An import of a module whose purpose is to run something, load something by name, or
#: reconstruct an object from bytes. Matched as an import statement so that prose naming one
#: is not a hit.
_HAZARDOUS_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:importlib|imp|subprocess|runpy|ctypes|pickle|marshal|shelve"
    r"|socket|multiprocessing|asyncio)\b",
    re.MULTILINE,
)

#: The guarded interpreter. ``sys.argv[1]`` is a scratch directory the parent prepared, which
#: already holds ``agent.json`` — the travel-booking agent's IR, extracted outside the guard.
_GUARD = '''
import json
import os
import socket
import sys
from pathlib import Path

WORK = Path(sys.argv[1])

BLOCKED = (
    "langgraph", "langchain", "langchain_core", "langsmith",
    "openai", "anthropic", "httpx", "requests", "aiohttp", "urllib3",
)

#: Every tripwire records before it raises, so a caller that swallows still fails the run.
attempts = []


class SubstrateBlocker:
    """Refuse every substrate import, wherever on the plugin path it is attempted."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            attempts.append("import:" + fullname)
            print("WA07-TRIP", file=sys.stderr)
            raise ImportError("WA-07 tripwire: the plugin path imported " + repr(fullname))
        return None


class TripSocket(socket.socket):
    """Subclassed rather than replaced, so `class X(socket.socket)` stays definable."""

    def __new__(cls, *args, **kwargs):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("WA-07 tripwire: the plugin path created a socket")


def trip(label, message):
    def tripped(*args, **kwargs):
        attempts.append(label)
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("WA-07 tripwire: the plugin path " + message)

    return tripped


sys.meta_path.insert(0, SubstrateBlocker())
socket.socket = TripSocket
socket.getaddrinfo = trip("getaddrinfo", "resolved a name")
socket.create_connection = trip("create_connection", "opened a connection")

# ── Leg 1: the entry-point import itself, and what it costs ──────────────────────────────

WATCHED = (
    "gebra.ir",
    "gebra.verify",
    "gebra.extraction",
    "gebra.testing",
    # SD-07's two additions, watched for the same reason as the four above: the freshness
    # marker reaches `gebra.store` (for the store directory's name) and `gebra.audit` (for the
    # check itself) through function-local imports, and moving either to module level would
    # keep `after_import` empty and `loaded` unchanged while quietly putting them in the
    # closure of every pytest session in every environment where gebra is installed.
    "gebra.store",
    "gebra.audit",
)

import gebra.pytest_plugin

after_import = sorted(name for name in WATCHED if name in sys.modules)

# ── The inner sessions ───────────────────────────────────────────────────────────────────

os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
import pytest

MARKED = """
from pathlib import Path

import pytest

from gebra.ir import read_ir

DOCUMENT = Path(__DOC__)


@pytest.mark.gebra(name="travel_agent")
def test_gebra():
    return read_ir(DOCUMENT)
"""

FIXTURES = """
from pathlib import Path

import pytest

from gebra.ir import WorkflowIR, read_ir

DOCUMENT = Path(__DOC__)


@pytest.fixture
def gebra_workflow():
    return read_ir(DOCUMENT)


def test_the_graph_fixture_is_the_document(gebra_graph):
    assert isinstance(gebra_graph, WorkflowIR)
    assert "release_hotel_hold" in {node.id for node in gebra_graph.nodes}


def test_the_report_fixture_answers_for_every_property(gebra_verification):
    assert gebra_verification.report.gate.exit_code == 0
    assert len(gebra_verification.report.properties) == 13
"""

CONTROL = """
import pytest


@pytest.mark.gebra(name="not_ir")
def test_gebra():
    return object()
"""


class Collector:
    """Count the inner session's outcomes; the child reports them rather than parsing text."""

    def __init__(self):
        self.outcomes = []
        self.ids = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            self.outcomes.append(report.outcome)
            self.ids.append(report.nodeid.split("::")[-1])


def run_session(name, body):
    path = WORK / name
    path.write_text(body.replace("__DOC__", repr(str(WORK / "agent.json"))), encoding="utf-8")
    collector = Collector()
    code = pytest.main(
        ["-p", "gebra.pytest_plugin", "-p", "no:cacheprovider", "-q", str(path)],
        plugins=[collector],
    )
    return {"exit": int(code), "outcomes": collector.outcomes, "ids": collector.ids}


marked = run_session("test_marked.py", MARKED)
fixtures = run_session("test_fixtures.py", FIXTURES)


def emit(extra=None):
    payload = {
        "after_import": after_import,
        "marked": marked,
        "fixtures": fixtures,
        "loaded": sorted(name for name in WATCHED if name in sys.modules),
        "leaked": sorted(n for n in sys.modules if n.split(".")[0] in BLOCKED),
        "attempts": list(attempts),
        "sources": sorted(
            module.__file__
            for name, module in list(sys.modules.items())
            if name.split(".")[0] == "gebra" and getattr(module, "__file__", None)
        ),
    }
    payload.update(extra or {})
    print(json.dumps(payload))


emit()
'''

#: The armed control: the plugin's *other* resolution branch, in the same guarded child.
_EXTRACTING_CONTROL = """
control = run_session("test_control.py", CONTROL)
emit({"control": control})
"""


def _run_guarded(work: Path, control: str = "") -> subprocess.CompletedProcess[str]:
    """Run the plugin path in a fresh interpreter with the substrate and sockets tripwired."""
    return subprocess.run(
        [sys.executable, "-c", _GUARD + control, str(work)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _payloads(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    """Every JSON object the guarded child emitted, in order."""
    payloads = []
    for line in result.stdout.splitlines():
        try:
            payloads.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return payloads


@pytest.fixture(scope="module")
def document(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The travel-booking agent's IR as a JSON document, extracted outside the guard.

    Extraction needs the substrate, which is exactly what the child does not have. Doing it
    here is the point rather than a workaround: fixture-only mode is the mode where the IR
    already exists — produced by an earlier run, read from a snapshot, or loaded from a
    property fixture — and this is that IR.
    """
    work = tmp_path_factory.mktemp("gebra-plugin-guard")
    envelope = extract(travel_booking.build_travel_booking_agent())
    (work / "agent.json").write_text(dump_json(envelope.ir), encoding="utf-8")
    assert travel_booking.TRIPPED == []
    return work


@pytest.fixture(scope="module")
def guarded(document: Path) -> dict[str, Any]:
    """One clean guarded run, shared by the assertions that read its report."""
    result = _run_guarded(document)
    assert result.returncode == 0, result.stderr
    payloads = _payloads(result)
    assert payloads, result.stdout
    return payloads[0]


# ── The claim ────────────────────────────────────────────────────────────────────────────


def test_the_plugin_verifies_the_agent_with_the_substrate_unimportable(
    guarded: dict[str, Any],
) -> None:
    """Acceptance box 2: fixture-only mode reaches no substrate import, no socket, no DNS.

    A green child is the claim, and what makes it a claim about *work done* rather than about
    work skipped is the inner session's own report: five items, one per wedge property, all
    passing, over the travel-booking agent's own document. If the plugin had quietly generated
    nothing, or errored every item, the counts below would say so.
    """
    assert guarded["attempts"] == []
    assert guarded["leaked"] == []
    marked = guarded["marked"]
    assert marked["exit"] == 0, marked
    assert marked["outcomes"] == ["passed"] * 5
    assert marked["ids"] == [
        f"test_gebra[travel_agent-{slug}]"
        for slug in (
            "graph-well-formed",
            "termination-witness",
            "dataflow-completeness",
            "effect-safety",
            "determinism-replay",
        )
    ]


def test_the_fixture_surface_is_hermetic_too(guarded: dict[str, Any]) -> None:
    """The other surface, in the same interpreter: ``gebra_graph`` and ``gebra_verification``.

    Two surfaces, two legs — the marker path and the fixture path resolve their target through
    the same function, but a later change could give one of them its own path, and a tripwire
    that covered only the marker would not notice.
    """
    fixtures = guarded["fixtures"]
    assert fixtures["exit"] == 0, fixtures
    assert fixtures["outcomes"] == ["passed", "passed"]


def test_importing_the_entry_point_costs_an_adopter_nothing(guarded: dict[str, Any]) -> None:
    """``import gebra.pytest_plugin`` pulls in neither the IR models nor the validators.

    pytest imports this module at the start of *every* session in an environment that has
    gebra installed, including sessions with nothing gebra-related in them, so the import
    closure is a cost paid by people who are not using the plugin. It is kept at ``pytest``
    plus the standard library; ``gebra.ir`` and ``gebra.verify`` arrive only once something is
    marked, which the second assertion shows happened in this very child.

    The second assertion is an **equality**, not a containment, so it is also what holds the
    freshness marker's two function-local imports (``gebra.store`` for the store directory's
    name, ``gebra.audit`` for the check) where they are: this session marks no function with
    ``@pytest.mark.gebra_freshness``, so neither may appear, and moving either to module level
    fails here rather than silently widening every adopter's session.
    """
    assert guarded["after_import"] == []
    assert guarded["loaded"] == ["gebra.ir", "gebra.verify"]


def test_the_extractor_is_never_reached_from_fixture_only_mode(
    guarded: dict[str, Any],
) -> None:
    """``gebra.extraction`` stays out of ``sys.modules`` across the whole guarded session.

    Stronger than "langgraph was not imported", and the reason the plugin classifies with one
    ``isinstance`` instead of probing the target: a probe that read an attribute to decide
    whether extraction was needed would have imported the extractor to have something to
    compare against.
    """
    assert "gebra.extraction" not in guarded["loaded"]
    assert "gebra.testing" not in guarded["loaded"]


def test_no_module_the_child_loaded_imports_the_substrate(guarded: dict[str, Any]) -> None:
    """A static scan over exactly the closure the child reported, not a hand-kept list.

    The dynamic blocker only refuses what the child actually *reached*. This is what catches
    the rest: a module in the same closure that would import the substrate under a condition
    this run did not take is still a fixture-only-mode hazard, and a lazy import inside a
    function is caught here as well as a module-level one. Its two bounds are in the module
    docstring's residuals paragraph rather than left to be inferred.

    The floor is a "went quiet" tripwire and not a bound: the closure is 24 modules today, and
    a scan that read three of them would pass every assertion below while proving nothing.
    """
    sources = [Path(source) for source in guarded["sources"]]
    assert len(sources) >= 22, f"the closure went quiet: {len(sources)} modules"
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert not _SUBSTRATE_IMPORT.search(text), f"{source} imports the substrate at module level"
        assert not _HAZARDOUS_IMPORT.search(text), f"{source} imports an execution primitive"


# ── The armed controls: a tripwire nobody trips proves nothing ───────────────────────────


def test_the_other_resolution_branch_does_trip_the_guard(document: Path) -> None:
    """The control that makes fixture-only mode a *choice* rather than a coincidence.

    Same interpreter, same guard, same plugin — only the target changes, from a ``WorkflowIR``
    to an object ``resolve_ir`` must hand to ``gebra.extract()``. Reaching for the extractor
    reaches the substrate, the blocker records the attempt and raises, and the items fail. So
    the green run above is green because of the branch it took, and this is the branch it did
    not take.
    """
    result = _run_guarded(document, _EXTRACTING_CONTROL)
    payloads = _payloads(result)
    assert len(payloads) == 2, result.stdout
    control_payload = payloads[1]
    assert "import:langgraph" in control_payload["attempts"]
    control = control_payload["control"]
    assert control["exit"] != 0
    assert control["outcomes"] == ["failed"] * 5


@pytest.mark.parametrize(
    "control",
    [
        "import langgraph\n",
        "import langchain_core\n",
        "import socket\nsocket.socket()\n",
        "import socket\nsocket.getaddrinfo('example.invalid', 80)\n",
        "import socket\nsocket.create_connection(('example.invalid', 80))\n",
    ],
)
def test_each_blocker_is_armed(document: Path, control: str) -> None:
    """Each raiser fires, loudly, when something in the child deliberately reaches for it.

    A blocker nobody trips proves nothing. Five rows, one per raiser, each appended to the
    same guard the green run above uses — so what they arm is that guard and not a copy of it.
    """
    result = _run_guarded(document, control)
    assert result.returncode != 0, result.stdout
    assert "WA07-TRIP" in result.stderr


@pytest.mark.parametrize(
    ("control", "expected"),
    [
        ("try:\n    import langgraph\nexcept ImportError:\n    pass\nemit()\n", "import:langgraph"),
        (
            "import socket\ntry:\n    socket.socket()\nexcept BaseException:\n    pass\nemit()\n",
            "socket",
        ),
        (
            (
                "import socket\ntry:\n    socket.getaddrinfo('example.invalid', 80)\n"
                "except BaseException:\n    pass\nemit()\n"
            ),
            "getaddrinfo",
        ),
    ],
)
def test_a_swallowed_attempt_is_still_recorded(document: Path, control: str, expected: str) -> None:
    """Every raiser records **before** it raises, so swallowing the exception does not hide it.

    Not symmetry with the rows above, and not a nicety. A path that reaches for the substrate
    or a socket inside a ``try`` and carries on would leave a raise-only tripwire silent and
    the child green — and a lazy import guarded by ``try/except ImportError`` is an ordinary
    Python idiom, while ``except Exception`` around a connection attempt is an ordinary
    capability probe. Each control swallows the exception and then emits, so the evidence is
    the emitted ``attempts`` list rather than the exit code: a clean exit with the attempt on
    the record is exactly what the design promises and nothing else would prove.
    """
    result = _run_guarded(document, control)
    payloads = _payloads(result)
    assert len(payloads) == 2, result.stdout
    assert result.returncode == 0, result.stderr
    assert payloads[0]["attempts"] == []
    assert payloads[1]["attempts"] == [expected]
