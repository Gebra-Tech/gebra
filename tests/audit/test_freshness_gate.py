"""**SD-07 acceptance box 2** — the freshness check fails CI when the agent changes.

"Fails CI" is not a claim a unit test can make about a function's return value, so every test
here runs a **real inner pytest session** through ``pytester``, the way
``tests/plugin/test_plugin.py`` does and for the same reason: what brief D-11 In-Scope 7 asks
for is that a *session* goes red ("fail CI if the workflow definition changed but no ``gebra
snapshot`` was taken"), and the observable for that is pytest's own exit code and its report.
The pytest gate is what CI runs (D-11 deliverable 6: "integrated with the D-10 pytest gate"),
so a red inner session over a changed agent is the acceptance box, observed.

The pairing is the point: every red case here has a green control built from the same store and
the same agent, so a gate that simply failed always would not pass this file.

Nothing here executes a node — the targets are the sentinel-guarded travel-booking agent and
its one-node-added variant, whose bodies record and raise, and
``test_no_node_body_runs_while_the_gate_checks_the_agent`` reads that ledger after a full inner
session.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from gebra.audit import export_store
from gebra.pytest_plugin import FRESHNESS_MARKER
from gebra.snapshot import snapshot
from gebra.store import SnapshotStore
from tests.audit.agents import build_travel_booking_agent_with_audit
from tests.sample_workflows import travel_booking as tb

if TYPE_CHECKING:
    from collections.abc import Iterator

pytest_plugins = ["pytester"]

#: The repository root, injected into every generated inner test file so that it can import the
#: shared agent fixture regardless of ``pytester``'s tmp cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]

_PREAMBLE = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
import pytest
"""

#: What the two agent builders are called from inside a generated test file.
_BUILDERS = {
    "v1": "from tests.sample_workflows.travel_booking import "
    "build_travel_booking_agent as build_agent",
    "edited": "from tests.audit.agents import build_travel_booking_agent_with_audit as build_agent",
}


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """The agent is read, never run — on entry to and exit from every test, inner sessions
    included, since ``pytester``'s ``runpytest`` runs in this same process by default."""
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


def _source(*, agent: str = "v1", marker: str = "", name: str = "travel_agent") -> str:
    """An inner test file whose freshness-marked function returns one of the two agents."""
    argument = f"name={name!r}" + (f", {marker}" if marker else "")
    return (
        _PREAMBLE
        + f"""
{_BUILDERS[agent]}

@pytest.mark.{FRESHNESS_MARKER}({argument})
def test_snapshot_is_current():
    return build_agent()
"""
    )


def _store_at(root: Path, *, agent: str = "v1") -> SnapshotStore:
    """A store under ``root`` holding one of the two agents at ``1.0.0.0``."""
    build = (
        tb.build_travel_booking_agent if agent == "v1" else build_travel_booking_agent_with_audit
    )
    store = SnapshotStore.for_project(root)
    snapshot(build(), store=store, source="tests.audit.test_freshness_gate")
    return store


# ── The box: red on a changed agent, green on an unchanged one ───────────────────────────


def test_the_gate_fails_the_session_when_the_agent_changed_without_a_re_snapshot(
    pytester: pytest.Pytester,
) -> None:
    """**Acceptance box 2.** The store holds v1; the definition has grown a node; CI goes red.

    Asserted three ways, because "fails CI" is all three: the item fails, the session's exit
    code is pytest's own failure code, and the report says *what* moved and what to do about it
    — a red gate whose message did not name the remedy would be a gate a team turns off.
    """
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source(agent="edited"))

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        [
            "*gebra ? travel_agent ? snapshot freshness*",
            "*changed and was not re-snapshotted*",
            "*snapshot 1.0.0.0*",
            "*moved*S, F*",
            "*gebra.snapshot.snapshot(workflow, store=store)*",
        ]
    )


def test_the_gate_passes_when_the_store_holds_this_definition(
    pytester: pytest.Pytester,
) -> None:
    """The green control for the case above, built from the same store and the same marker: an
    unchanged definition passes, silently, as a verdict item should."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source(agent="v1"))

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.OK


def test_the_gate_passes_again_once_the_change_is_recorded(pytester: pytest.Pytester) -> None:
    """The remedy the failing message names actually clears the gate.

    The same red session as the box above, then one ``gebra.snapshot.snapshot`` call, then the
    same session again — which is what makes the failure actionable rather than merely loud.
    """
    store = _store_at(Path(pytester.path))
    pytester.makepyfile(_source(agent="edited"))
    assert pytester.runpytest().ret == pytest.ExitCode.TESTS_FAILED

    recorded = snapshot(build_travel_booking_agent_with_audit(), store=store, source="tests.audit")
    assert recorded.recorded and recorded.version == "1.1.1.0"

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_the_gate_fails_when_nothing_has_ever_been_snapshotted(
    pytester: pytest.Pytester,
) -> None:
    """A store holding nothing is its own event, with its own words and its own remedy — not a
    claim that the definition drifted, which would be false the first time anyone runs it."""
    pytester.makepyfile(_source())

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the store holds no snapshot*", "*record the first one*"])
    assert "changed and was not re-snapshotted" not in result.stdout.str()


# ── Where the store comes from ───────────────────────────────────────────────────────────


def test_the_default_store_is_dot_gebra_under_the_rootdir(pytester: pytest.Pytester) -> None:
    """CLI-SPEC's ``./.gebra`` default, resolved against pytest's rootdir rather than the
    process's working directory — a CI check whose meaning depended on where ``pytest`` was
    invoked from would pass and fail for reasons nobody could see in the log."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source())
    (pytester.path / "sub").mkdir()

    result = pytester.runpytest("--rootdir", str(pytester.path), str(pytester.path))

    result.assert_outcomes(passed=1)


def test_an_explicit_store_is_read_relative_to_the_rootdir(pytester: pytest.Pytester) -> None:
    _store_at(Path(pytester.path) / "elsewhere")
    pytester.makepyfile(_source(marker="store='elsewhere/.gebra'"))

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_an_explicit_store_may_be_absolute(pytester: pytest.Pytester, tmp_path: Path) -> None:
    store = _store_at(tmp_path / "away")
    pytester.makepyfile(_source(marker=f"store={str(store.path)!r}"))

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_an_explicit_store_that_holds_nothing_is_not_silently_the_default_one(
    pytester: pytest.Pytester,
) -> None:
    """A mistyped ``store=`` must not fall back to a store that happens to be fresh: that would
    turn a misconfigured gate into a green one."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source(marker="store='typo/.gebra'"))

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the store holds no snapshot*"])


# ── Declaration errors, and the checks the gate refuses to make ──────────────────────────


def test_the_marker_is_registered_so_strict_markers_accepts_it(
    pytester: pytest.Pytester,
) -> None:
    """Registered at ``pytest_configure`` like the ``gebra`` marker, so a suite running
    ``--strict-markers`` — which many CI configurations do — is not broken by adopting it."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source())

    result = pytester.runpytest("--strict-markers")

    result.assert_outcomes(passed=1)
    assert FRESHNESS_MARKER in pytester.runpytest("--markers").stdout.str()


def test_a_function_that_returns_nothing_is_a_usage_error_not_a_pass(
    pytester: pytest.Pytester,
) -> None:
    """A marked function that checked nothing must not report a green item — the same refusal
    the ``gebra`` marker makes, for the same reason."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(
        _PREAMBLE
        + f"""
@pytest.mark.{FRESHNESS_MARKER}(name="travel_agent")
def test_snapshot_is_current():
    pass
"""
    )

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*returned None*", "*must return the workflow*"])


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        pytest.param('"travel_agent"', "*takes no positional arguments*", id="positional"),
        pytest.param("strict=True", "*takes only `name`, `sidecar` and `store`*", id="unknown"),
        pytest.param("name=7", "*takes a non-empty string*", id="not-a-string"),
    ],
)
def test_an_unreadable_declaration_is_refused(
    pytester: pytest.Pytester, declaration: str, message: str
) -> None:
    """A declaration the plugin cannot read is a usage error, never a silently differently-named
    item or a silently discarded store."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.{FRESHNESS_MARKER}({declaration})
def test_snapshot_is_current():
    return build_travel_booking_agent()
"""
    )

    result = pytester.runpytest()

    result.stdout.fnmatch_lines([message])
    assert result.ret != pytest.ExitCode.OK


@pytest.mark.parametrize(
    "flag",
    ["--gebra-strict", "--gebra-skip=termination-witness", "--gebra-select=effect-safety"],
)
def test_the_property_gate_flags_do_not_reach_the_freshness_item(
    pytester: pytest.Pytester, flag: str
) -> None:
    """The three D-10 gate flags subset and promote *properties*; freshness is not one.

    A ``--gebra-skip`` that quietly removed the freshness item, or a ``--gebra-strict`` that
    changed its verdict, would make the store check depend on a policy about validators. The
    item is generated and answers the same way under all three.
    """
    _store_at(Path(pytester.path), agent="v1")
    pytester.makepyfile(_source(agent="edited"))

    result = pytester.runpytest(flag)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*changed and was not re-snapshotted*"])


def test_both_markers_on_one_function_is_refused(pytester: pytest.Pytester) -> None:
    """The two markers ask different questions of the same function, and the collection order
    would make one of them silently not run — so it is a usage error rather than a resolution."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.gebra(name="travel_agent")
@pytest.mark.{FRESHNESS_MARKER}(name="travel_agent")
def test_both():
    return build_travel_booking_agent()
"""
    )

    result = pytester.runpytest()

    printed = result.stdout.str()

    assert "are both on" in printed
    assert "put them on two functions" in printed
    assert result.ret != pytest.ExitCode.OK
    assert "collected 0 items" in printed


def test_a_damaged_store_is_reported_as_a_fault_not_as_staleness(
    pytester: pytest.Pytester,
) -> None:
    """Reporting a corrupt index as "stale" would ask a reader to re-snapshot their way out of a
    damaged file. The item fails either way; what differs is what it tells them to do."""
    store = _store_at(Path(pytester.path))
    store.meta_path.write_text("current: [not, a, label]\n", encoding="utf-8")
    pytester.makepyfile(_source())

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the freshness check could not be made*"])
    assert "changed and was not re-snapshotted" not in result.stdout.str()


def test_a_target_that_cannot_be_extracted_is_reported_as_such(
    pytester: pytest.Pytester,
) -> None:
    """Nothing was compared, and the item says so rather than reporting a store verdict."""
    _store_at(Path(pytester.path))
    pytester.makepyfile(
        _PREAMBLE
        + f"""
@pytest.mark.{FRESHNESS_MARKER}(name="not_a_graph")
def test_snapshot_is_current():
    return object()
"""
    )

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the working definition could not be obtained*"])


# ── What the gate never does ─────────────────────────────────────────────────────────────


def test_the_gate_writes_nothing_to_the_store(pytester: pytest.Pytester) -> None:
    """A check that recorded the snapshot it was missing would be a gate that always passes, and
    the artifact it wrote would be one nobody reviewed. Asserted on the store's own bytes across
    a red session and a green one."""
    store = _store_at(Path(pytester.path))
    before = {path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()}

    pytester.makepyfile(_source(agent="edited"))
    assert pytester.runpytest().ret == pytest.ExitCode.TESTS_FAILED
    pytester.makepyfile(_source(agent="v1"))
    assert pytester.runpytest().ret == pytest.ExitCode.OK

    after = {path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()}
    assert after == before


def test_the_gate_writes_no_audit_export_either(pytester: pytest.Pytester) -> None:
    """The export is an engine call a pipeline makes deliberately, not a side effect of running
    the test suite: a CI check that wrote files into the repository it is checking would change
    the thing it is reporting on. ``export_store`` is what writes them, and here it is called
    afterwards to show the directory was empty until it was."""
    store = _store_at(Path(pytester.path))
    pytester.makepyfile(_source())

    assert pytester.runpytest().ret == pytest.ExitCode.OK
    assert list(store.reports_dir.glob("*")) == []

    assert [outcome.version for outcome in export_store(store)] == ["1.0.0.0"]
    assert [path.name for path in store.reports_dir.glob("*")] == ["1.0.0.0.report.json"]


def test_no_node_body_runs_while_the_gate_checks_the_agent(pytester: pytest.Pytester) -> None:
    """WA-07 on this surface, read off the agent's own ledger after a full inner session.

    Both sessions: the passing one, where the definition is extracted and compared, and the
    failing one, where it is extracted, compared, diffed against the stored IR and rendered.
    Every node body and router in the fixture raises if called, so an empty ledger after both is
    the claim. (The autouse fixture asserts the same thing on every test in this file; this one
    states it as its own subject.)
    """
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source(agent="v1"))
    assert pytester.runpytest().ret == pytest.ExitCode.OK
    pytester.makepyfile(_source(agent="edited"))
    assert pytester.runpytest().ret == pytest.ExitCode.TESTS_FAILED

    assert tb.TRIPPED == []


def test_the_gate_grades_nothing(pytester: pytest.Pytester) -> None:
    """P-12 ``evolution-safety`` is deferred (SOW §8; PD-006 R4). The failing item reports that
    the content moved and which counters moved with it, and says in terms that it is not a
    verdict about the workflow.

    The test's own name is deliberately free of the vocabulary it sweeps for: ``pytester``
    builds the inner session's rootdir out of it, and the path is printed in the header — so a
    test named for the words it forbids would fail on its own name.
    """
    _store_at(Path(pytester.path))
    pytester.makepyfile(_source(agent="edited"))

    result = pytester.runpytest()
    printed = result.stdout.str()

    result.stdout.fnmatch_lines(["*this is a check on the store, not a verdict*"])
    for verdict in ("breaking", "unsafe", "backward", "benign"):
        assert verdict not in printed.lower()
