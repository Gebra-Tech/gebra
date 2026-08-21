"""The pytest plugin, driven as a user drives it — card TE-06.

Every behavioural test here runs a **real inner pytest session** through ``pytester`` rather
than calling the hooks by hand, because what the card asks for is a fact about pytest's
collection and reporting ("yields one test item per wedge property with correct outcomes"),
not about a function's return value. Calling ``pytest_generate_tests`` directly would prove
that the plugin computes five parametrizations; running pytest proves that pytest *collects*
five items, names them the way D-10 spells them, and reports the outcomes the run produced.

The inner sessions load the plugin the way an adopter's CI does — through the ``pytest11``
entry point, with no ``-p`` flag — which is why ``test_the_plugin_loads_from_its_entry_point``
comes first: if the installed distribution's metadata is stale, that test says so in one line
instead of every other test failing with an unregistered marker.

**Targets, and why they are the ones they are.** The live travel-booking agent (TE-05) is the
card's own acceptance subject and is clean on the wedge five, so it is the passing case. The
failing cases are **vendored corpus fixtures**, not defects seeded into the agent: what a
seeded travel-booking variant should emit is SD-09's acceptance box, while a corpus fixture
carries its own R-05-authored ``expected:`` block, so the plugin's item outcome can be
asserted against the fixture's own statement of what the property does rather than against a
prediction made here. Three fixtures cover the three shapes an item outcome can take —
a FATAL owned by the property, a WARNING owned by the property (which must *not* fail the
item), and a FATAL P-01 that makes the other topology items best-effort.

Nothing here executes a node: the agent's bodies are sentinels that record and raise, and
``test_no_node_body_runs_while_the_plugin_verifies_the_agent`` reads that ledger after a full
inner session. The hermetic form of the claim — that fixture-only mode reaches no substrate
import at all — is ``tests/plugin/test_hermeticity.py``'s, in a guarded interpreter.
"""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

import pytest

from gebra.pytest_plugin import (
    BLOCKING_SEVERITIES,
    CHECK_PARAM,
    MARKER,
    GebraCheck,
    ItemOutcome,
    TargetVerification,
    enabled_properties,
    findings_for,
    item_outcome,
    owned_findings,
    resolve_ir,
    verify_target,
)
from gebra.testing import load_corpus, load_fixture
from gebra.verify import (
    PROPERTY_SLUGS,
    WEDGE_SLUGS,
    PropertyReport,
    validate_report,
    verify,
)
from tests.sample_workflows import travel_booking

if TYPE_CHECKING:
    from gebra.ir import WorkflowIR
    from gebra.verify import PropertySlug

pytest_plugins = ["pytester"]

#: The repository root, injected into every generated inner test file so that it can import
#: the shared agent fixture and the vendored corpus regardless of ``pytester``'s tmp cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]

CORPUS = REPO_ROOT / "tests" / "fixtures" / "properties"

#: The five wedge slugs, in catalog order — what a Phase-0 build generates an item for.
EXPECTED_SLUGS: tuple[str, ...] = (
    "graph-well-formed",
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)

_PREAMBLE = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
import pytest
"""


def _agent_source(*, name: str = "travel_agent") -> str:
    """An inner test file marking the live travel-booking agent."""
    return (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.{MARKER}(name={name!r})
def test_gebra():
    return build_travel_booking_agent()
"""
    )


def _fixture_ir(relative: str) -> WorkflowIR:
    """The single IR of a vendored fixture — every fixture used here is a one-IR fixture."""
    fixture = load_fixture(CORPUS / relative)
    ir = fixture.ir
    assert ir is not None, f"{relative} is a pair fixture, not a single-IR one"
    return ir


def _fixture_source(relative: str, *, name: str) -> str:
    """An inner test file whose target is a vendored fixture's IR — fixture-only mode."""
    path = CORPUS / relative
    return (
        _PREAMBLE
        + f"""
from pathlib import Path
from gebra.testing import load_fixture

@pytest.mark.{MARKER}(name={name!r})
def test_gebra():
    return load_fixture(Path({str(path)!r})).ir
"""
    )


# ── A deliberately warning-bearing target, for the INTROSPECTION-SPEC §8 path ────────────
#
# The travel-booking agent extracts with no warning at all — that is TE-05's whole point — so
# nothing in the corpus or in the shared substrate exercises the plugin's §8 note path. One
# undecorated node is the smallest thing that does: ANNOTATION-API-SPEC §5 grades a slot
# declared iff no `contract-inferred`/`contract-defaulted` record names it, so leaving
# `effects` to the D-011 conservative default is exactly one `contract-defaulted` warning.
#
# Sentinel-guarded on the travel-booking pattern: the body records itself and raises a
# `BaseException` subclass, so no `except Exception` on any path can swallow it into a
# warning, and `WIDENER_TRIPPED` is asserted empty by the tests that build it.

WIDENER_TRIPPED: list[str] = []


class _WidenerSentinelError(BaseException):
    """Raised if the undecorated node below is ever invoked. Nothing here may run."""


class _WidenerState(TypedDict):
    request: str
    widened: str


def _widen(state: _WidenerState) -> dict[str, str]:
    """Undecorated on purpose — the `contract-defaulted` warning is the point of this node."""
    WIDENER_TRIPPED.append("widen")
    raise _WidenerSentinelError("'widen' was invoked — nothing here may ever run")


def _build_warning_bearing_agent() -> Any:
    """A one-node ``StateGraph`` whose extraction raises exactly one §8 warning."""
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(_WidenerState)
    builder.add_node("widen", _widen)
    builder.add_edge(START, "widen")
    builder.add_edge("widen", END)
    return builder


@pytest.fixture(autouse=True)
def _the_agent_never_ran() -> Any:
    """Every test in this file leaves the sentinel ledger empty, on entry and on exit.

    On entry as well as on exit, for the reason TE-05's pre-review established: a
    clear-then-check fixture cannot speak for anything a higher-scoped fixture or an earlier
    module already ran. Nothing here may leave a body behind for the next test to blame.
    """
    assert travel_booking.TRIPPED == [], (
        f"a node body ran before this test: {travel_booking.TRIPPED}"
    )
    assert WIDENER_TRIPPED == [], f"a node body ran before this test: {WIDENER_TRIPPED}"
    yield
    assert travel_booking.TRIPPED == [], (
        f"a node body ran during this test: {travel_booking.TRIPPED}"
    )
    assert WIDENER_TRIPPED == [], f"a node body ran during this test: {WIDENER_TRIPPED}"


# ── The plugin is installed the way an adopter installs it ───────────────────────────────


def test_the_plugin_loads_from_its_entry_point() -> None:
    """The installed distribution advertises the plugin under the ``pytest11`` group.

    This is what makes ``pip install gebra`` + ``@pytest.mark.gebra`` the whole adoption
    story (D-10 Definition of Done line 1) — no ``-p gebra``, no conftest wiring. It is
    asserted against the *installed metadata* rather than against ``pyproject.toml``, because
    a declaration that never made it into a dist-info is a declaration that does nothing;
    ``tests/test_packaging.py`` holds the source-side half.
    """
    advertised = {
        entry.name: entry.value for entry in importlib.metadata.entry_points(group="pytest11")
    }
    assert advertised.get("gebra") == "gebra.pytest_plugin", (
        "the gebra pytest11 entry point is not registered in this environment — reinstall "
        "the package (`pip install -e .`) so the declaration in pyproject.toml takes effect"
    )


def test_the_marker_is_registered_so_it_raises_no_unknown_mark_warning(
    pytester: pytest.Pytester,
) -> None:
    """``pytest_configure`` declares the marker; ``--strict-markers`` is the proof."""
    pytester.makepyfile(test_agent=_agent_source())
    result = pytester.runpytest("--strict-markers")
    result.assert_outcomes(passed=len(EXPECTED_SLUGS))


# ── Acceptance box 1: one item per wedge property, with the outcomes the run produced ────


def test_the_marker_yields_one_item_per_wedge_property(pytester: pytest.Pytester) -> None:
    """Collection: five items, named ``<target>-<slug>``, in catalog order.

    The id spelling is D-10 In-Scope 2's own — ``test_gebra[travel_agent-termination-witness]``
    — and it is what makes a CI failure itemize per property instead of collapsing into one
    red test.
    """
    items = pytester.getitems(_agent_source())
    assert [item.name for item in items] == [
        f"test_gebra[travel_agent-{slug}]" for slug in EXPECTED_SLUGS
    ]


def test_the_enabled_set_is_read_off_the_registry(pytester: pytest.Pytester) -> None:
    """The item set is whatever this build registered a validator for — not a literal list.

    Asserted in both directions so the constant above cannot drift from the registry: the
    enabled set *is* the wedge five today, and the generated items *are* the enabled set.
    """
    assert enabled_properties() == EXPECTED_SLUGS
    assert enabled_properties() == WEDGE_SLUGS
    assert set(enabled_properties()) <= set(PROPERTY_SLUGS)
    items = pytester.getitems(_agent_source())
    assert len(items) == len(enabled_properties())


def test_the_travel_booking_agent_passes_every_wedge_item(pytester: pytest.Pytester) -> None:
    """Acceptance box 1, the passing half: the live agent, five green items, exit 0.

    ``-p no:randomly``-style ordering games are unnecessary here; what matters is that the
    plugin's own gate agrees with what ``verify()`` says about this graph, so the run's exit
    code is asserted beside the outcome counts.
    """
    pytester.makepyfile(test_agent=_agent_source())
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=len(EXPECTED_SLUGS), failed=0, errors=0, skipped=0)
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [f"*test_gebra[[]travel_agent-{slug}[]]*PASSED*" for slug in EXPECTED_SLUGS]
    )


def test_no_node_body_runs_while_the_plugin_verifies_the_agent(
    pytester: pytest.Pytester,
) -> None:
    """WA-07 at the plugin's own level: a full inner session leaves the ledger empty.

    The agent's nine node bodies and two routers each record their label and then raise
    (``TravelBookingSentinelError`` derives from ``BaseException`` so no ``except Exception``
    on any path can swallow it into a warning). The inner session builds the graph five times
    and extracts it five times; if the plugin, the extractor or ``verify()`` had called one
    body, the ledger would name it — and the autouse fixture on this file would fail every
    later test too.

    The armed control for this ledger is TE-05's, in ``tests/testing/test_travel_booking.py``,
    which fires all eleven bodies through the built graph and asserts each recorded before it
    raised. This test is the consumer of that arming, not a second arming of it.
    """
    pytester.makepyfile(test_agent=_agent_source())
    result = pytester.runpytest()
    result.assert_outcomes(passed=len(EXPECTED_SLUGS))
    assert travel_booking.TRIPPED == []


def test_the_target_name_defaults_to_the_function_name(pytester: pytest.Pytester) -> None:
    """No ``name=``: the item id carries the function name without its ``test_`` prefix."""
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.{MARKER}
def test_travel_agent():
    return build_travel_booking_agent()
"""
    )
    items = pytester.getitems(source)
    assert [item.name for item in items] == [
        f"test_travel_agent[travel_agent-{slug}]" for slug in EXPECTED_SLUGS
    ]


# ── Acceptance box 1: the outcomes are the run's, not a fixed verdict ────────────────────


def test_a_fatal_finding_fails_exactly_the_item_that_owns_it(
    pytester: pytest.Pytester,
) -> None:
    """A vendored unwitnessed-cycle fixture: P-02's item fails, the other four pass.

    The condition named in the failure message is the fixture's own ``expected:`` block, read
    here rather than restated, so this test asserts the plugin against the R-05 authority for
    what that graph does — not against a prediction written beside it.
    """
    relative = "termination-witness/negative-01-unwitnessed-reflection-loop.yaml"
    fixture = load_fixture(CORPUS / relative)
    expected_failure = fixture.expected_failure
    assert expected_failure is not None
    condition = expected_failure["property_condition"]

    pytester.makepyfile(test_target=_fixture_source(relative, name="reflection_loop"))
    result = pytester.runpytest()
    result.assert_outcomes(passed=4, failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        [
            "*FAILED*test_gebra[[]reflection_loop-termination-witness[]]*",
        ]
    )
    result.stdout.fnmatch_lines([f"*FATAL {condition}*"])


def test_a_warning_grade_finding_is_a_note_and_never_a_failure(
    pytester: pytest.Pytester,
) -> None:
    """The default severity mapping is about **severity**, not about ``result``.

    The sharpest case the corpus offers: a P-08 fixture whose report is ``result: "fail"``
    with a ``severity: "warning"`` record. D-10 In-Scope 2 makes WARNING advisory by default,
    so all five items pass — and the record is attached to the P-08 item's report rather than
    dropped, which is what ``--gebra-strict`` (TE-07) promotes.

    TE-07 changed *how* it is attached and the change is a correction, not a preference: it
    had been rendered under the ``note:`` label, which REPORT-FORMAT-SPEC §5.1 obligation 3
    reserves for witness notes and §2.1 keeps categorically apart from findings — and with the
    severity word printed twice. A WARNING-grade ``Failure`` is a finding, so it renders as
    one, and that it did not gate is stated rather than implied by a label.
    """
    relative = "determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml"
    fixture = load_fixture(CORPUS / relative)
    assert fixture.result == "fail"

    pytester.makepyfile(test_target=_fixture_source(relative, name="classifier"))
    result = pytester.runpytest("-rA")
    result.assert_outcomes(passed=len(EXPECTED_SLUGS), failed=0)
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [
            "*WARNING deterministic-llm-seed-unpinned [[]heuristic[]]*",
            "*advisory under the default mapping*",
        ]
    )


def test_a_fatal_p01_leaves_the_topology_items_marked_best_effort(
    pytester: pytest.Pytester,
) -> None:
    """PROPERTY-CATALOG-SPEC §0.3's precondition, carried into the items that inherit it.

    On an ill-formed topology P-02/P-04/P-06 still answer, but their answers are best-effort
    diagnostics rather than contract-bearing verdicts. They pass here — nothing they own is
    FATAL or ERROR — and the fact that their pass is qualified must not be lost, so the
    plugin says so on the failing P-01 item and the run report says so in ``best_effort``.
    """
    relative = "graph-well-formed/negative-01-unreachable-escalation-node.yaml"
    report = verify(_fixture_ir(relative))
    assert report.best_effort == ("termination-witness", "dataflow-completeness", "effect-safety")

    pytester.makepyfile(test_target=_fixture_source(relative, name="escalation"))
    result = pytester.runpytest("-rA")
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(["*FAILED*test_gebra[[]escalation-graph-well-formed[]]*"])
    # The qualifier rides the three *passing* items — a qualified pass is still qualified —
    # so it is read out of their report sections rather than out of the failure text.
    result.stdout.fnmatch_lines(
        ["*test_gebra[[]escalation-termination-witness[]]*", "*best-effort diagnostic*"]
    )


def test_a_run_that_reached_no_verdict_fails_every_item(pytester: pytest.Pytester) -> None:
    """Exit 2 is never a pass: a tool error fails every item of the target.

    Provoked the only way a user could provoke it here — by taking a wedge validator out of
    the registry, which makes ``verify()`` refuse to assemble the run at all ("a run that
    checked the rest would be a weakened gate wearing a pass", REPORT-FORMAT-SPEC §1.4 rule
    2). Four items are generated, because the unregistered property is no longer answerable
    and so is no longer enabled; all four report the §2.4 stage and detail instead of a
    verdict.

    Run in a **subprocess**, because the registry is process-global: an in-process inner run
    would unregister the validator out from under the outer session. That has a WA-07 cost
    worth paying attention to rather than glossing — the outer ``TRIPPED`` ledger cannot see a
    different process, and this leg does perform a real extraction of the live sentinel-guarded
    agent before ``verify()`` reaches its dispatch error. So the child asserts the ledger
    itself, on its own copy of the module, as its last item.
    """
    pytester.makeconftest(
        """
        from gebra.verify import unregister_validator
        unregister_validator("determinism-replay")
        """
    )
    pytester.makepyfile(
        test_agent=_agent_source()
        + """
def test_zz_no_node_body_ran_in_this_process():
    from tests.sample_workflows.travel_booking import TRIPPED

    assert TRIPPED == []
"""
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, failed=len(EXPECTED_SLUGS) - 1)
    result.stdout.fnmatch_lines(["*no verdict was reached*dispatch*"])


def test_no_registered_validator_is_a_refusal_rather_than_a_green_item(
    pytester: pytest.Pytester,
) -> None:
    """A gebra run that can check nothing must not report a green item.

    The empty-enabled-set case is a collection-time ``UsageError`` rather than pytest's
    generic "got empty parameter set" skip, because a skip reads as "not applicable" and
    this state is "the tool is broken". Unreachable in a normal install; reachable here, and
    therefore worth pinning.
    """
    pytester.makeconftest(
        """
        from gebra.verify import WEDGE_SLUGS, unregister_validator

        for slug in WEDGE_SLUGS:
            unregister_validator(slug)
        """
    )
    pytester.makepyfile(test_agent=_agent_source())
    result = pytester.runpytest_subprocess()
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.assert_outcomes(passed=0, failed=0, errors=1)
    result.stdout.fnmatch_lines(["*UsageError*no property to check*"])


# ── Collection: composition, fixtures, and leaving everything else alone ─────────────────


def test_the_marked_function_receives_its_fixtures(pytester: pytest.Pytester) -> None:
    """A marked function is an ordinary test function: pytest fills its fixtures.

    That is what lets a team build the graph from whatever their conftest already provides —
    a config object, a tmp path, a parametrized builder — instead of a module-level global.
    """
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.fixture
def narrow():
    return True

@pytest.mark.{MARKER}(name="agent")
def test_gebra(narrow):
    assert narrow is True
    return build_travel_booking_agent(narrow_input_schema=narrow)
"""
    )
    pytester.makepyfile(test_agent=source)
    pytester.runpytest().assert_outcomes(passed=len(EXPECTED_SLUGS))


def test_the_marker_works_on_a_test_class_method(pytester: pytest.Pytester) -> None:
    """A marked method inside a test class is a target like any other function.

    Pinned because the plugin calls the function itself rather than letting pytest's own
    ``pytest_pyfunc_call`` do it, and a bound method is where that could quietly go wrong:
    ``_call_target`` reads the signature of ``item.obj``, which for a method is already
    bound, so ``self`` is absent from it and absent from ``funcargs`` alike. Getting that
    backwards would pass ``self`` twice or not at all, and only a class-based suite would
    ever see it.
    """
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

class TestAgent:
    @pytest.mark.{MARKER}(name="travel_agent")
    def test_gebra(self):
        return build_travel_booking_agent()
"""
    )
    pytester.makepyfile(test_agent=source)
    result = pytester.runpytest("test_agent.py")
    result.assert_outcomes(passed=len(EXPECTED_SLUGS))


def test_the_marker_composes_with_the_users_own_parametrize(
    pytester: pytest.Pytester,
) -> None:
    """``@pytest.mark.parametrize`` above the marker multiplies out, each combination verified.

    The counterfactual builder PD-021 D1 named is the natural second parameter here: both
    shapes of the same agent pass the wedge five, and the plugin verifies each on its own
    rather than verifying one and reusing the verdict.

    The gebra component lands **last** in the id, because the plugin's
    ``pytest_generate_tests`` is ``trylast``. That is a decision rather than an accident, and
    it is pinned here: a reader scanning a failure list sees the user's own dimension first
    and the property last.
    """
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.parametrize("narrow", [True, False])
@pytest.mark.{MARKER}(name="agent")
def test_gebra(narrow):
    return build_travel_booking_agent(narrow_input_schema=narrow)
"""
    )
    items = pytester.getitems(source)
    assert {item.name for item in items} == {
        f"test_gebra[{narrow}-agent-{slug}]"
        for narrow in ("True", "False")
        for slug in EXPECTED_SLUGS
    }
    pytester.makepyfile(test_agent=source)
    pytester.runpytest("test_agent.py").assert_outcomes(passed=2 * len(EXPECTED_SLUGS))


def test_the_check_fixture_carries_the_items_declaration(pytester: pytest.Pytester) -> None:
    """A marked function that asks for ``gebra_check`` gets its target and property."""
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

seen = []

@pytest.mark.{MARKER}(name="agent")
def test_gebra({CHECK_PARAM}):
    seen.append(({CHECK_PARAM}.target, {CHECK_PARAM}.property))
    return build_travel_booking_agent()

def test_zz_every_property_was_seen():
    assert [target for target, _ in seen] == ["agent"] * {len(EXPECTED_SLUGS)}
    assert [slug for _, slug in seen] == list({EXPECTED_SLUGS!r})
"""
    )
    pytester.makepyfile(test_agent=source)
    pytester.runpytest().assert_outcomes(passed=len(EXPECTED_SLUGS) + 1)


def test_unmarked_tests_are_left_exactly_alone(pytester: pytest.Pytester) -> None:
    """The plugin loads into every session in the world; it must cost those sessions nothing.

    An ordinary test file collects the ordinary number of items, keeps its own ids, and — the
    part that would be easy to break by taking over ``pytest_pyfunc_call`` too eagerly — a
    test that returns a value still raises pytest's own return-not-none warning, because that
    warning is suppressed *only* for the items this plugin generated.
    """
    source = """
import pytest

def test_plain():
    assert True

@pytest.mark.parametrize("value", [1, 2])
def test_parametrized(value):
    assert value

def test_returns_something():
    return 1
"""
    pytester.makepyfile(test_plain=source)
    collected = pytester.runpytest("test_plain.py", "--collect-only", "-q")
    collected.stdout.fnmatch_lines(
        [
            "test_plain.py::test_plain",
            "test_plain.py::test_parametrized[[]1[]]",
            "test_plain.py::test_parametrized[[]2[]]",
            "test_plain.py::test_returns_something",
        ]
    )
    result = pytester.runpytest("test_plain.py", "-W", "error::pytest.PytestReturnNotNoneWarning")
    result.assert_outcomes(passed=3, failed=1)


# ── Usage errors say what to do ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("marker_args", "expected"),
    [
        ("('travel_agent')", "*takes no positional arguments*"),
        ("(target='x')", "*takes only `name` and `sidecar`*"),
        ("(name=42)", "*non-empty string*"),
        ("(name='')", "*non-empty string*"),
        ("(sidecar=42)", "*non-empty string*"),
    ],
)
def test_marker_misuse_is_refused_at_collection(
    pytester: pytest.Pytester, marker_args: str, expected: str
) -> None:
    """Every unreadable declaration is a collection refusal, never a differently-named item.

    ``@pytest.mark.gebra('travel_agent')`` heads the list because it is the plausible mistake
    — a name where a keyword belongs — and because ``name=`` is the only argument the marker
    has, so a positional one is always a misreading of it. The refusal is scoped to the module
    that carries it (a collection error, not a session abort), so one mis-declared marker does
    not take the rest of a suite down with it.

    Note what is *not* in the list: ``@pytest.mark.gebra(build_agent)``. A ``MarkDecorator``
    called with a single callable is pytest's own bare-decorator form — it marks that callable
    and returns it — so the mistake never reaches this plugin and is pytest's to report.
    """
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.{MARKER}{marker_args}
def test_gebra():
    return build_travel_booking_agent()
"""
    )
    pytester.makepyfile(test_agent=source)
    result = pytester.runpytest("test_agent.py")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([f"*UsageError*{expected.lstrip('*')}"])


def test_a_marked_function_that_returns_nothing_fails_rather_than_passes(
    pytester: pytest.Pytester,
) -> None:
    """A marked function that verified nothing must not look like a green check."""
    source = (
        _PREAMBLE
        + f"""
@pytest.mark.{MARKER}(name="agent")
def test_gebra():
    assert True
"""
    )
    pytester.makepyfile(test_agent=source)
    result = pytester.runpytest()
    result.assert_outcomes(failed=len(EXPECTED_SLUGS))
    result.stdout.fnmatch_lines(["*returned None*"])


def test_an_async_marked_function_is_refused_with_a_message_about_gebra(
    pytester: pytest.Pytester,
) -> None:
    """``async def`` gets gebra's own refusal, not a confusing one from the extractor.

    Taking over ``pytest_pyfunc_call`` displaces pytest's async guard along with everything
    else in that implementation, so the refusal has to be restated here. Without it the
    un-awaited coroutine is not ``None``, travels on to ``gebra.extract()``, and comes back as
    "this object is not a LangGraph StateGraph" — true, useless, and accompanied by a
    ``RuntimeWarning`` about a coroutine that was never awaited. Nothing runs either way; the
    defect is diagnostic quality, and the message says what gebra actually needs.
    """
    source = (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.{MARKER}(name="agent")
async def test_gebra():
    return build_travel_booking_agent()
"""
    )
    pytester.makepyfile(test_agent=source)
    result = pytester.runpytest("test_agent.py")
    result.assert_outcomes(failed=len(EXPECTED_SLUGS))
    result.stdout.fnmatch_lines(["*is async*"])
    result.stdout.no_fnmatch_line("*was never awaited*")


def test_an_unsupported_target_fails_with_the_extraction_refusal(
    pytester: pytest.Pytester,
) -> None:
    """``gebra.extract()`` refuses at the object boundary; the item carries that refusal.

    INTROSPECTION-SPEC §2 makes an unsupported object a typed error naming the type, "never a
    silent partial IR" — so the plugin re-raises it as a target error rather than letting it
    become a green item over an empty document.
    """
    source = (
        _PREAMBLE
        + f"""
@pytest.mark.{MARKER}(name="not_a_graph")
def test_gebra():
    return object()
"""
    )
    pytester.makepyfile(test_agent=source)
    result = pytester.runpytest()
    result.assert_outcomes(failed=len(EXPECTED_SLUGS))
    result.stdout.fnmatch_lines(["*gebra.extract() takes a LangGraph StateGraph*"])


# ── The fixture surface: gebra_workflow → gebra_graph / gebra_verification ─────────────────────


def test_the_gebra_graph_fixture_is_the_extracted_ir(pytester: pytest.Pytester) -> None:
    """The D-10 In-Scope 2 fixture: override the factory, assert against the IR in plain pytest."""
    pytester.makeconftest(
        _PREAMBLE
        + """
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.fixture
def gebra_workflow():
    return build_travel_booking_agent()
"""
    )
    pytester.makepyfile(
        test_graph="""
from gebra.ir import WorkflowIR

def test_the_release_path_is_wired(gebra_graph):
    assert isinstance(gebra_graph, WorkflowIR)
    assert "release_hotel_hold" in {node.id for node in gebra_graph.nodes}
"""
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_the_gebra_verification_fixture_carries_all_thirteen_outcomes(
    pytester: pytest.Pytester,
) -> None:
    """Where the eight deferred properties are visible — as markers, never as passes.

    The marker surface generates no item for them, and this is the reason that is a
    distinction rather than a silence: the run report the plugin holds answers for all
    thirteen, and the eight carry the structured ``NotImplementedMarker`` the registry
    exists to return.
    """
    pytester.makeconftest(
        _PREAMBLE
        + """
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.fixture
def gebra_workflow():
    return build_travel_booking_agent()
"""
    )
    pytester.makepyfile(
        test_report="""
from gebra.verify import NON_WEDGE_SLUGS, PROPERTY_SLUGS, NotImplementedMarker

def test_the_run_answers_for_every_catalog_property(gebra_verification):
    report = gebra_verification.report
    assert tuple(o.property for o in report.properties) == PROPERTY_SLUGS
    deferred = {o.property for o in report.properties if isinstance(o, NotImplementedMarker)}
    assert deferred == set(NON_WEDGE_SLUGS)
    assert report.gate.exit_code == 0
"""
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_gebra_workflow_without_an_override_says_what_to_write(
    pytester: pytest.Pytester,
) -> None:
    """The stub is the documentation: the error names the fixture and shows the override."""
    pytester.makepyfile(
        test_graph="""
def test_needs_a_workflow(gebra_graph):
    assert gebra_graph is not None
"""
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*gebra_workflow*has no default*"])


def test_the_check_fixture_refuses_to_be_requested_outside_a_gebra_item(
    pytester: pytest.Pytester,
) -> None:
    """``gebra_check`` is a parametrization handle; there is nothing for it to mean elsewhere."""
    pytester.makepyfile(
        test_check=f"""
def test_asks_for_the_check({CHECK_PARAM}):
    assert {CHECK_PARAM} is not None
"""
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*only available on an item generated by*"])


# ── The programmatic surface, and the attribution rule the items rest on ─────────────────


def test_a_workflow_ir_target_needs_no_extraction() -> None:
    """Fixture-only mode at the function level: an IR in, the same IR out, ``ir-document``.

    The hermetic form of this claim — that the branch reaches no substrate *import* — is
    ``tests/plugin/test_hermeticity.py``'s. What is asserted here is the behaviour the
    hermeticity depends on: identity, so nothing re-parsed or re-validated the document, and
    the §1.3 input mode the subject will carry.
    """
    ir = _fixture_ir("termination-witness/positive-01-counter-guarded-retry-loop.yaml")
    resolution = resolve_ir(ir)
    assert resolution.ir is ir
    assert resolution.input_mode == "ir-document"
    assert resolution.extractor_version is None
    assert resolution.notes == ()


def test_a_live_workflow_target_is_extracted_and_labelled_extracted() -> None:
    """The other branch: the agent goes through ``gebra.extract()`` and says so in the subject."""
    verification = verify_target(
        travel_booking.build_travel_booking_agent(),
        name="travel_agent",
        source="tests/plugin/test_plugin.py::direct#travel_agent",
    )
    subject = verification.report.subject
    assert subject is not None
    assert subject.input_mode == "extracted"
    assert subject.source == "tests/plugin/test_plugin.py::direct#travel_agent"
    assert subject.graph_version.startswith("sha256:")
    assert subject.extractor_version is not None
    assert verification.extraction_notes == ()
    assert verification.report.gate.exit_code == 0
    assert travel_booking.TRIPPED == []


def test_a_co_failure_is_attributed_to_the_property_that_owns_it() -> None:
    """§2.3's ownership rule, on the vendored shape that states it.

    No wedge validator emits a cross-property co-failure today — the corpus scan below finds
    none, and the three fixtures that carry one are the fidelity matrix's ``PR-2`` rows — so
    the rule cannot be demonstrated end-to-end through an item. It is demonstrated where the
    authority for the shape is: the fixture's own ``expected:`` block, which is a real
    ``PropertyReport`` of exactly the class a validator returns (A6 PC-6).

    Getting this wrong is not cosmetic. ``mixed/02``'s report is P-02's, and the FATAL riding
    it is P-04's: a walk that attributed by host would fail the termination-witness item
    twice and leave the dataflow-completeness item green with a FATAL against its name.
    """
    fixture = load_fixture(CORPUS / "mixed/02-unwitnessed-loop-reading-unwritten-key.yaml")
    report = fixture.expected_report()
    assert isinstance(report, PropertyReport)
    assert report.property == "termination-witness"

    records = owned_findings(report)
    assert [(record.owner, record.origin, record.severity) for record in records] == [
        ("termination-witness", "failure", "fatal"),
        ("dataflow-completeness", "co-failure", "fatal"),
    ]
    assert all(record.blocking for record in records)


def test_every_record_the_walk_finds_is_one_the_gate_counted() -> None:
    """The drift detector: this walk's tally must equal ``verify()``'s own ``gate.counts``.

    The plugin re-walks the envelope rather than importing ``verify()``'s private derivation,
    so the two could drift — a record carrier added to ``Failure`` would be counted by the
    gate and missed by the items, which is a weakened gate wearing a pass. Quantified over
    every vendored fixture that composes to a single IR, so the two stay equal by test rather
    than by hope.
    """
    enabled = set(enabled_properties())
    checked = 0
    records = 0
    for fixture in load_corpus(CORPUS):
        ir = fixture.ir
        if ir is None:
            continue
        report = verify(ir)
        tally = {"fatal": 0, "error": 0, "warning": 0}
        for slug in PROPERTY_SLUGS:
            for record in findings_for(report, slug):
                tally[record.severity] += 1
                records += 1
                # A blocking record whose owner has no item would fail the *run* (exit 1) and
                # leave every item green — the one way the per-item projection can disagree
                # with `gate.exit_code`. §3.2's projection rule licenses a record owned by a
                # property that is out of scope for this build, so the day one is emitted this
                # goes red instead of going quiet.
                assert not record.blocking or record.owner in enabled, (
                    f"{fixture.fixture_id}: a {record.severity} record owned by "
                    f"{record.owner!r} has no item to fail"
                )
        assert tally == {
            "fatal": report.gate.counts.fatal,
            "error": report.gate.counts.error,
            "warning": report.gate.counts.warning,
        }, f"{fixture.fixture_id}: the plugin's per-property tally left the gate's behind"
        checked += 1
    assert checked >= 40, f"only {checked} fixtures reduced to a single IR — the scan went quiet"
    # The tally is only a drift detector if it sees records; a corpus that emitted none would
    # satisfy every assertion above and prove nothing.
    assert records >= 40, f"only {records} records over the corpus — the cross-check went quiet"


def test_an_advisory_is_attributed_to_its_own_property_not_its_host() -> None:
    """The other half of §2.3's ownership rule — the half the corpus cannot reach.

    A co-failure's ownership is demonstrated against a vendored fixture above. An advisory's
    cannot be: no wedge validator emits one today, and the two fixtures whose ``expected:``
    blocks carry one do not compose (the PD-016/TE-04 residue, a known and routed shape rather
    than a fixture defect). So it is demonstrated the way ``tests/verify/test_run.py`` does —
    on a report built from the envelope's own public models, which are the same classes a
    validator returns (A6 PC-6).

    Why it matters is the same reason the co-failure case does, one step further: §0.3 makes an
    advisory the *host* report's carrier for another property's finding, so a walk that read
    the host slug would attribute a P-08 advisory to P-06 — and under ``--gebra-strict``
    (TE-07) that is the difference between which property a promotion names.
    """
    host = validate_report(
        {
            "property": "effect-safety",
            "result": "fail",
            "failure": {
                "property_condition": "unprotected-effect-in-retry-region",
                "location": {"kind": "node", "node": "book_flight"},
                "severity": "error",
                "claim_class": "defensible",
                "advisories": [
                    {
                        "property": "determinism-replay",
                        "property_condition": "deterministic-llm-seed-unpinned",
                        "location": {"kind": "node", "node": "classify_request"},
                        "severity": "warning",
                        "claim_class": "heuristic",
                    }
                ],
            },
        }
    )
    records = owned_findings(host)
    assert [(record.owner, record.origin) for record in records] == [
        ("effect-safety", "failure"),
        ("determinism-replay", "advisory"),
    ]
    assert records[1].blocking is False  # every advisory is WARNING-grade by §0.3
    assert records[0].blocking is True


# ── INTROSPECTION-SPEC §8: extraction warnings are never silently dropped ────────────────


def test_an_extraction_warning_is_carried_under_its_taxonomy_code() -> None:
    """The §8 code, not the Python enum's name — the vocabulary is what a consumer greps.

    ``ExtractionWarningCode`` is a ``(str, Enum)`` mixin, so from Python 3.11 on an f-string
    over a member yields ``ExtractionWarningCode.CONTRACT_DEFAULTED`` and on 3.10 it yields
    the value — a token that is both outside §8's closed ten-code vocabulary and different
    per interpreter. The note carries ``.value``, and this pins it.
    """
    resolution = resolve_ir(_build_warning_bearing_agent())
    assert [note.code for note in resolution.notes] == ["contract-defaulted"]
    note = resolution.notes[0]
    assert note.node == "widen"
    assert note.slots == ("pure",)
    assert note.render().startswith("extraction warning [contract-defaulted] at widen (pure)")
    assert "ExtractionWarningCode" not in note.render()
    assert WIDENER_TRIPPED == []


def test_extraction_warnings_reach_a_default_run_on_both_surfaces(
    pytester: pytest.Pytester,
) -> None:
    """§8: "warnings are never silently droppable" — so a bare ``pytest`` must show them.

    A report section is not enough on its own: pytest prints one for a *failing* item but for
    a passing one only under ``-rA``/``-rP``, and every item here passes. The run's closing
    gebra section is the floor that makes the obligation hold without a flag. Both surfaces
    are checked, because ``gebra_graph`` returns only the IR and would otherwise be the one
    place a warning could vanish without the user's code ever mentioning it.

    **The multiplicity is TE-07's, and it is the better statement.** That card turned the
    closing section into REPORT-FORMAT-SPEC §5's per-target report, so a warning is stated
    once per *target* rather than once per item: the marker's five items share one extraction
    and one block, and the ``gebra_graph`` item has its own. What §8 obliges is that neither
    surface can drop one, which is what is asserted — the count is pinned in both directions
    so a regression that dropped the fixture surface, or one that went back to repeating the
    same warning five times, both fail here.
    """
    pytester.makeconftest(
        _PREAMBLE
        + """
from tests.plugin.test_plugin import _build_warning_bearing_agent

@pytest.fixture
def gebra_workflow():
    return _build_warning_bearing_agent()
"""
    )
    pytester.makepyfile(
        test_widener=_PREAMBLE
        + f"""
from tests.plugin.test_plugin import _build_warning_bearing_agent

@pytest.mark.{MARKER}(name="widener")
def test_gebra():
    return _build_warning_bearing_agent()

def test_graph_fixture(gebra_graph):
    assert gebra_graph.nodes
"""
    )
    result = pytester.runpytest("test_widener.py")
    result.assert_outcomes(passed=len(EXPECTED_SLUGS) + 1, failed=0)
    result.stdout.fnmatch_lines(["*= gebra =*"])
    warnings = [
        line for line in result.stdout.lines if "extraction warning [contract-defaulted]" in line
    ]
    # One per surface: the marker target's report block, and the `gebra_graph` item's own.
    assert len(warnings) == 2, warnings
    result.stdout.fnmatch_lines(
        [
            "*test_widener.py::test_gebra[[]widener[]]*",
            "*extraction warning [[]contract-defaulted[]]*",
        ]
    )
    result.stdout.fnmatch_lines(
        ["*test_widener.py::test_graph_fixture*", "*extraction warning [[]contract-defaulted[]]*"]
    )


def test_an_explicit_sidecar_can_be_declared_on_both_surfaces(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """ANNOTATION-API-SPEC §2's "reproducible/CI extraction SHOULD pass ``sidecar=``".

    Rule 2 walks up from the **current working directory**, and sidecar-filled annotations sit
    inside the ``graph_version`` hash scope — so on the CI surface, of all places, the walk's
    answer must be declarable rather than inherited from wherever pytest happened to start.
    The declaration is observable in the report's own subject (§1.3), which is asserted here
    rather than the resolution being taken on trust.
    """
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_text(
        'schema = "gebra-sidecar-v1"\n\n[nodes.widen]\npure = true\n', encoding="utf-8"
    )
    pytester.makeconftest(
        _PREAMBLE
        + f"""
from tests.plugin.test_plugin import _build_warning_bearing_agent

@pytest.fixture
def gebra_workflow():
    return _build_warning_bearing_agent()

@pytest.fixture
def gebra_sidecar():
    return {str(sidecar)!r}
"""
    )
    pytester.makepyfile(
        test_sidecar=_PREAMBLE
        + f"""
from tests.plugin.test_plugin import _build_warning_bearing_agent

@pytest.mark.{MARKER}(name="widener", sidecar={str(sidecar)!r})
def test_gebra():
    return _build_warning_bearing_agent()

def test_the_fixture_surface_records_it(gebra_verification):
    assert gebra_verification.report.subject.sidecar == {str(sidecar)!r}
"""
    )
    result = pytester.runpytest("test_sidecar.py")
    result.assert_outcomes(passed=len(EXPECTED_SLUGS) + 1, failed=0)
    # The declared sidecar filled the slot the default would have defaulted, so the
    # `contract-defaulted` warning of the test above is gone from every item.
    assert not [line for line in result.stdout.lines if "contract-defaulted" in line]


def test_the_default_mapping_is_severity_and_not_result() -> None:
    """``ItemOutcome.failed`` reads severities, so a WARNING-grade ``fail`` passes its item."""
    assert BLOCKING_SEVERITIES == frozenset({"fatal", "error"})
    ir = _fixture_ir("determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml")
    verification = TargetVerification(target="classifier", report=verify(ir))
    outcome = item_outcome(verification, "determinism-replay")
    assert [record.severity for record in outcome.findings] == ["warning"]
    assert outcome.blocking == ()
    assert len(outcome.notes) == 1
    assert outcome.failed is False


def test_an_outcome_with_no_findings_is_a_pass() -> None:
    """The empty case, pinned so ``failed`` cannot become truthy on an empty tuple."""
    outcome = ItemOutcome(check=GebraCheck(target="t", property="effect-safety"), findings=())
    assert outcome.failed is False
    assert outcome.blocking == ()
    assert outcome.notes == ()


@pytest.mark.parametrize("slug", WEDGE_SLUGS)
def test_the_agent_is_clean_on_every_wedge_property_the_plugin_reports(
    slug: PropertySlug,
) -> None:
    """The programmatic mirror of acceptance box 1, property by property.

    The inner-session test above asserts the pytest surface; this asserts the outcome the
    surface reports, so a green run cannot be green because the plugin computed nothing.
    """
    verification = verify_target(
        travel_booking.build_travel_booking_agent(), name="travel_agent", source="direct"
    )
    outcome = item_outcome(verification, slug)
    assert outcome.findings == ()
    assert outcome.tool_error is None
    assert outcome.best_effort is False
    assert outcome.failed is False
    assert travel_booking.TRIPPED == []


def test_importing_the_plugin_pulls_in_neither_the_extractor_nor_the_substrate() -> None:
    """The plugin's import closure, measured in a child that imports nothing else.

    A ``pytest11`` entry point is imported at the start of every pytest session in every
    environment that has gebra installed, so this is a cost every adopter pays whether or not
    they use the plugin. Kept at ``pytest`` plus the standard library: not even ``gebra.ir``
    or ``gebra.verify``, and certainly not the substrate.

    This is the *measurement*; ``tests/plugin/test_hermeticity.py`` is the **guard**, where an
    import of the substrate raises rather than being counted afterwards.
    """
    import subprocess

    probe = (
        "import sys, gebra.pytest_plugin;"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in "
        "{'langgraph', 'langchain_core', 'networkx', 'yaml'} "
        "or m in {'gebra.ir', 'gebra.verify', 'gebra.extraction', 'gebra.testing'}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout
