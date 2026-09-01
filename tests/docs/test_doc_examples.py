"""The executable-examples harness, and the WA-07 guard every documented example runs under.

Three claims live here (card DOC-01). First, the markup: what a page may declare, and what
the harness refuses rather than silently skipping — a mis-marked example that vanished from
CI would leave WA-12's "examples executed verbatim" enforcing nothing. Second, every example
marked anywhere in the documentation runs, and prints exactly what its page shows; each is
its own test item, so a failure names the page and the block. Third, the guard: the examples
read workflow definitions and never run them, and every raiser that claim rests on is fired
by a control probe inside the very run that made it — a tripwire nobody trips reports
nothing.

The module itself reads Markdown and starts child interpreters. It executes no workflow
node, calls no model and opens no connection, and neither does anything it starts.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.sample_workflows import (
    travel_booking,
    travel_booking_defects,
    travel_booking_evolution,
)
from tools.docs_examples import (
    DEFAULT_INCLUDE,
    INHERITED_ENV,
    DocExample,
    DocExampleError,
    child_program,
    discover,
    main,
    parse_markdown,
    run_example,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "tools" / "docs_examples.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: Every example the documentation marks, discovered once at collection time.
EXAMPLES: list[DocExample] = discover(REPO_ROOT)

#: The example the control probes ride along with. Any example would do — the guard is the
#: same for all of them — and taking the first discovered one rather than naming an id keeps
#: the controls alive when the pages that carry examples change.
CONTROL_EXAMPLE = EXAMPLES[0] if EXAMPLES else None

requires_an_example = pytest.mark.skipif(
    CONTROL_EXAMPLE is None, reason="no documented example to carry the control probes"
)


# ── The markup: what a page may declare ──────────────────────────────────────────────────


def _page(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_an_example_with_a_declared_output_parses() -> None:
    parsed = parse_markdown(
        _page(
            "# A page",
            "",
            "<!-- gebra:example id=hello -->",
            "```python",
            'print("hi")',
            "```",
            "",
            "<!-- gebra:output id=hello -->",
            "```text",
            "hi",
            "```",
        ),
        path="page.md",
    )

    assert len(parsed) == 1
    example = parsed[0]
    assert (example.example_id, example.code, example.expected_output) == (
        "hello",
        'print("hi")\n',
        "hi\n",
    )
    assert (example.line, example.output_line) == (4, 9)
    assert example.name == "page.md::hello"


def test_an_example_with_no_declared_output_must_print_nothing() -> None:
    """The absence of an output block is a claim, not a hole: stdout is pinned to empty."""
    (example,) = parse_markdown(
        _page("<!-- gebra:example id=quiet -->", "```python", "x = 1", "```"), path="page.md"
    )

    assert example.expected_output == ""
    assert example.output_line is None


def test_directives_inside_a_fenced_block_are_shown_markup_not_declarations() -> None:
    """A page must be able to document this notation without declaring an example by doing so."""
    parsed = parse_markdown(
        _page(
            "````markdown",
            "<!-- gebra:example id=illustration -->",
            "```python",
            'print("not run")',
            "```",
            "````",
            "",
            "<!-- gebra:example id=real -->",
            "```python",
            "pass",
            "```",
        ),
        path="page.md",
    )

    assert [example.example_id for example in parsed] == ["real"]


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        pytest.param(
            _page("<!-- gebra:sample id=x -->", "```python", "pass", "```"),
            "unknown directive gebra:sample",
            id="unknown-directive",
        ),
        pytest.param(
            _page("<!-- gebra:example -->", "```python", "pass", "```"),
            "needs id=<lowercase-slug>",
            id="missing-id",
        ),
        pytest.param(
            _page("<!-- gebra:example id=Bad_Id -->", "```python", "pass", "```"),
            "needs id=<lowercase-slug>",
            id="malformed-id",
        ),
        pytest.param(
            _page("<!-- gebra:example id=x lang=python -->", "```python", "pass", "```"),
            "takes only id=",
            id="extra-attribute",
        ),
        pytest.param(
            _page("<!-- gebra:example id=x nonsense -->", "```python", "pass", "```"),
            "unparsable directive attributes",
            id="unparsable-attributes",
        ),
        pytest.param(
            _page(
                "<!-- gebra:example id=x -->",
                "```python",
                "pass",
                "```",
                "<!-- gebra:example id=x -->",
                "```python",
                "pass",
                "```",
            ),
            "duplicate example id",
            id="duplicate-example",
        ),
        pytest.param(
            _page("<!-- gebra:output id=orphan -->", "```text", "hi", "```"),
            "names no example declared above it",
            id="orphan-output",
        ),
        pytest.param(
            _page(
                "<!-- gebra:example id=x -->",
                "```python",
                "pass",
                "```",
                "<!-- gebra:output id=x -->",
                "```text",
                "",
                "```",
                "<!-- gebra:output id=x -->",
                "```text",
                "",
                "```",
            ),
            "duplicate output",
            id="duplicate-output",
        ),
        pytest.param(
            _page("<!-- gebra:example id=x -->", "not a fence"),
            "must be followed by a fenced code block",
            id="no-fence",
        ),
        pytest.param(
            _page("<!-- gebra:example id=x -->", "```python", "pass"),
            "unclosed fenced code block",
            id="unclosed-fence",
        ),
        pytest.param(
            _page("<!-- gebra:example id=x -->"),
            "directive ends the file",
            id="directive-at-eof",
        ),
    ],
)
def test_malformed_markup_is_refused_rather_than_skipped(page: str, expected: str) -> None:
    """Every way of mis-marking an example is an error, so none of them removes it from CI."""
    with pytest.raises(DocExampleError, match=expected):
        parse_markdown(page, path="page.md")


def test_discovery_reads_the_published_site_and_the_readme() -> None:
    assert DEFAULT_INCLUDE == ("docs/**/*.md", "README.md")


def test_the_environment_allowlist_names_no_credential_or_tracing_variable() -> None:
    assert "LANGCHAIN_TRACING_V2" not in INHERITED_ENV
    assert not [name for name in INHERITED_ENV if "KEY" in name or "TOKEN" in name]


# ── The examples themselves ──────────────────────────────────────────────────────────────


def test_the_documentation_marks_at_least_one_example() -> None:
    """The floor under the claim: a harness with nothing to run would pass vacuously."""
    assert EXAMPLES, "no documented example is marked — the WA-12 harness has nothing to check"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.name)
def test_a_documented_example_runs_and_prints_what_its_page_shows(example: DocExample) -> None:
    """The whole of WA-12's executable half, once per example, under the guard."""
    result = run_example(example, root=REPO_ROOT)

    assert result.ok, result.report()


# ── WA-07: the guard, and a control for every raiser it rests on ─────────────────────────


@requires_an_example
@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        pytest.param(
            "_gebra_socket.socket()\n",
            "a socket was created from a documentation example",
            id="socket",
        ),
        pytest.param(
            "_gebra_socket.getaddrinfo('example.invalid', 443)\n",
            "getaddrinfo was reached from a documentation example",
            id="getaddrinfo",
        ),
        pytest.param(
            "_gebra_socket.gethostbyname('example.invalid')\n",
            "gethostbyname was reached from a documentation example",
            id="gethostbyname",
        ),
        pytest.param(
            "_gebra_socket.create_connection(('example.invalid', 443))\n",
            "create_connection was reached from a documentation example",
            id="create_connection",
        ),
        pytest.param(
            "_GebraStateGraph.compile(None)\n",
            "StateGraph.compile was reached from a documentation example",
            id="compile",
        ),
        # Connecting is refused even inside the import window where socket *construction* is
        # merely counted, so the tolerance that window buys cannot be spent on a connection.
        # Fired through the class because by this point `socket.socket` is the raising one.
        pytest.param(
            "_GebraCountSocket.connect(None, ('example.invalid', 443))\n",
            "socket.connect was reached from a documentation example",
            id="connect",
        ),
        pytest.param(
            "_GebraCountSocket.connect_ex(None, ('example.invalid', 443))\n",
            "socket.connect_ex was reached from a documentation example",
            id="connect_ex",
        ),
        # INTROSPECTION-SPEC §1 rule 1 names the invoke family beside nodes and routers, and
        # arming `StateGraph.compile` does not reach it: an LCEL chain runs without anything
        # being compiled. Both an override (`RunnableLambda.invoke`) and a method inherited
        # from the armed base are fired, so the sweep is shown to cover the class tree.
        pytest.param(
            "from langchain_core.runnables import RunnableLambda\n"
            "RunnableLambda(lambda value: value).invoke(1)\n",
            ".invoke was reached from a documentation example",
            id="lcel-invoke",
        ),
        pytest.param(
            "from langchain_core.runnables import RunnableLambda\n"
            "RunnableLambda(lambda value: value).batch([1])\n",
            ".batch was reached from a documentation example",
            id="lcel-batch",
        ),
        # A model call is armed on its own account, not only through the socket raisers: a
        # local or stubbed model reaches no network, and "no connection was opened" would
        # otherwise be the whole of the no-LLM-call claim.
        pytest.param(
            "from langchain_core.language_models.fake_chat_models import FakeListChatModel\n"
            "FakeListChatModel(responses=['x']).invoke('hi')\n",
            "BaseChatModel.invoke was reached from a documentation example",
            id="model-invoke",
        ),
        # And a tool call, for the same reason and with one more: `BaseTool` overrides
        # `invoke`, so it would shadow the armed base if it entered the tree after the sweep.
        # A page showing a tool as a node (the annotation tutorial's tool-carried tier) is
        # exactly when that matters, which is why the guard names the module rather than
        # relying on the extractor having imported it first.
        pytest.param(
            "from langchain_core.tools import StructuredTool\n"
            "StructuredTool(\n"
            "    name='t',\n"
            "    description='never invoked',\n"
            "    args_schema={'type': 'object'},\n"
            "    func=lambda: '',\n"
            ").invoke({})\n",
            "BaseTool.invoke was reached from a documentation example",
            id="tool-invoke",
        ),
    ],
)
def test_each_raiser_the_guard_rests_on_is_armed(probe: str, expected: str) -> None:
    """Fired after the example's own code, so each raiser is proven live in that same run."""
    assert CONTROL_EXAMPLE is not None
    result = run_example(CONTROL_EXAMPLE, root=REPO_ROOT, probe=probe)

    assert not result.ok
    assert "WA-07: a guarded operation was reached" in result.problems
    assert expected in result.stderr


@requires_an_example
def test_an_attempt_a_try_block_swallowed_still_fails_the_example() -> None:
    """Record-before-raise, exercised: catching the exception does not hide the attempt."""
    assert CONTROL_EXAMPLE is not None
    result = run_example(
        CONTROL_EXAMPLE,
        root=REPO_ROOT,
        probe=(
            "try:\n"
            "    _gebra_socket.getaddrinfo('example.invalid', 443)\n"
            "except BaseException:\n"
            "    pass\n"
        ),
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any("WA07-ATTEMPTS ['getaddrinfo']" in problem for problem in result.problems)


#: How an example names a sample workflow. Three forms, because a page that used a fourth must
#: fail loudly rather than be read as importing none — which is what
#: `test_every_example_importing_a_sample_workflow_is_controlled` holds by asserting that a page
#: mentioning the package yields at least one module here.
SAMPLE_WORKFLOW_IMPORTS = (
    re.compile(r"^from tests\.sample_workflows\.(?P<module>\w+) import", re.MULTILINE),
    re.compile(r"^import tests\.sample_workflows\.(?P<module>\w+)", re.MULTILINE),
    re.compile(r"^from tests\.sample_workflows import (?P<names>[^\n(]+)", re.MULTILINE),
)


def _sample_workflows_in(code: str) -> set[str]:
    """Every `tests/sample_workflows/` module `code` imports, by any of the three forms."""
    found: set[str] = set()
    for pattern in SAMPLE_WORKFLOW_IMPORTS:
        for match in pattern.finditer(code):
            if "module" in match.groupdict():
                found.add(match.group("module"))
                continue
            for name in match.group("names").split(","):
                bare = name.strip().split()[0] if name.strip() else ""
                if bare:
                    found.add(bare)
    return found


#: One fired control per sample workflow the pages build against: the module, a body of it, and
#: the ledger entry that body leaves. Named rather than derived, because the point of a control is
#: that someone chose a body and a call the page's own workflow would plausibly make — and held to
#: the *discovered* set by the test below, so a page importing a fourth fixture cannot land with a
#: ledger leg nobody has ever fired.
SAMPLE_WORKFLOW_LEDGER_CONTROLS = (
    # A sample workflow the pages on this site import. A control on some *other* fixture
    # would prove the sweep works where it is not used and could not fail where it is —
    # which is the shape of a tripwire that reports nothing. (The carrier example is
    # whichever one sorts first; the probe imports its own fixture either way.)
    pytest.param(
        "sentinel_graph",
        "plan_step({'query': 'x'})",
        "sentinel_graph:node 'plan_step' was invoked",
        id="sentinel-graph",
    ),
    pytest.param(
        "travel_booking",
        "classify_request({})",
        "travel_booking:travel-booking.classify_request",
        id="travel-booking",
    ),
    # The seeded-defect variants, which the concepts page and the verify tutorial import. Their
    # bodies record into the v1 family ledger, which this module re-exports under its own name;
    # the control is here to prove the sweep reads *this* module rather than only reaching the
    # same list by its other name.
    pytest.param(
        "travel_booking_defects",
        "classify_request_temperature_unpinned({})",
        "travel_booking_defects:travel-booking-defects.classify_request_temperature_unpinned",
        id="travel-booking-defects",
    ),
    # The evolution sequence, which the snapshot/diff guide walks version by version. Same
    # re-exported family ledger, same reason for a control of its own — and the body chosen is
    # one only this module defines, so a control that stopped reaching it could not pass by
    # landing on v1's twin of the same name.
    pytest.param(
        "travel_booking_evolution",
        "join_waitlist({})",
        "travel_booking_evolution:travel-booking-evolution.join_waitlist",
        id="travel-booking-evolution",
    ),
)


def test_every_example_importing_a_sample_workflow_carries_a_fired_ledger_control() -> None:
    """WA-07's same-change rule for the third ledger-bearing shape, made mechanical.

    A page that builds against `tests/sample_workflows/` inherits that module's ledger, and the
    trailer sweeps it by name. Whether that leg is *live* rather than vacuous depends on a control
    having fired one of the module's bodies inside a real guarded run — and which modules those
    were was a hand-maintained table beside a growing set of pages. The two analogous rules already
    derive their obligation from `EXAMPLES` (`SELF_DEFINED_MARKERS`, `WRITES_A_MODULE`); this is the
    third, and it is fail-closed in both directions: an import form this file cannot parse fails
    rather than reading as importing nothing.
    """
    controlled = {control.values[0] for control in SAMPLE_WORKFLOW_LEDGER_CONTROLS}

    for example in EXAMPLES:
        imported = _sample_workflows_in(example.code)
        if "tests.sample_workflows" in example.code:
            assert imported, f"{example.name} names the sample workflows in a form unknown here"
        uncontrolled = sorted(imported - controlled)
        assert not uncontrolled, f"{example.name}: no fired ledger control for {uncontrolled}"


@requires_an_example
@pytest.mark.parametrize(("module", "call", "expected"), SAMPLE_WORKFLOW_LEDGER_CONTROLS)
def test_a_sample_workflow_body_that_ran_is_reported_by_its_ledger(
    module: str, call: str, expected: str
) -> None:
    """The node-execution leg, which no socket probe can arm — and swallowing it does not help."""
    assert CONTROL_EXAMPLE is not None
    result = run_example(
        CONTROL_EXAMPLE,
        root=REPO_ROOT,
        probe=(
            f"from tests.sample_workflows import {module} as _fixture\n"
            "try:\n"
            f"    _fixture.{call}\n"
            "except BaseException:\n"
            "    pass\n"
        ),
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any(expected in problem for problem in result.problems)


#: Examples that build their own graph rather than importing a sample workflow. Extraction
#: unwraps a node to the bare callable, so the armed `invoke` family never sees a call on one
#: of these bodies — the body has to arm itself, and the trailer sweeps `__main__` for it.
SELF_DEFINED_MARKERS = ("add_node(", "add_conditional_edges(")


def test_an_example_that_builds_its_own_graph_arms_its_own_node_bodies() -> None:
    """The page-level half of the sweep's fail-closed rule, which the trailer cannot guess.

    `__main__` is exempt from the *unledgered* leg, because most examples define no body and
    a ledger they never write to is noise. What decides which pages owe one is this: a page
    that registers a node it defined must keep a `TRIPPED` list and record into it.
    """
    owing = [
        example
        for example in EXAMPLES
        if any(marker in example.code for marker in SELF_DEFINED_MARKERS)
    ]

    for example in owing:
        assert "TRIPPED" in example.code, f"{example.name} builds a graph and keeps no ledger"
        assert "TRIPPED.append(" in example.code, f"{example.name} keeps a ledger nothing writes"


@requires_an_example
def test_a_body_an_example_defined_itself_is_reported_by_the_ledger() -> None:
    """The other half of that rule, fired: `__main__`'s ledger is swept, and swallowing fails.

    Named rather than taken from `EXAMPLES[0]`, because this control is about a specific
    page's own body — the sample-workflow controls above are the ones that must stay alive
    as the carrier changes.
    """
    example = next((item for item in EXAMPLES if item.name == "README.md::readme-library"), None)
    assert example is not None, "the README's library example is gone — re-point this control"

    result = run_example(
        example,
        root=REPO_ROOT,
        probe="try:\n    plan({'query': 'x'})\nexcept BaseException:\n    pass\n",
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any("WA07-LEDGER ['__main__:plan']" in problem for problem in result.problems)


def test_a_callable_an_example_only_annotates_is_armed_too() -> None:
    """The shape neither floor test finds: a page that decorates callables but builds no graph.

    `docs/tutorials/contracts-and-annotations.md`'s decoration-time example registers nothing
    and writes no module, so `SELF_DEFINED_MARKERS` and `WRITES_A_MODULE` both pass it by — yet
    its whole subject is applying decorators to callables, and §1's "returns the function
    unchanged, never invokes it" is exactly the claim a reader takes from it. The example
    therefore arms its own targets, and this fires one: a decorator that called what it was
    handed would leave a ledger entry and fail the page rather than printing a clean transcript.
    """
    name = "docs/tutorials/contracts-and-annotations.md::decoration-time-rules"
    example = next((item for item in EXAMPLES if item.name == name), None)
    assert example is not None, f"{name} is gone — re-point this control"

    result = run_example(
        example,
        root=REPO_ROOT,
        probe="try:\n    VendoredStep()({})\nexcept BaseException:\n    pass\n",
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any("WA07-LEDGER ['__main__:VendoredStep']" in problem for problem in result.problems)


#: An example that writes a module and imports it back — ``Path("name.py").write_text(…)``.
#: Not the mechanism that covers such a module (the trailer sweeps it by ``__file__``, needing
#: no cooperation from the page); this is how the controls below find the pages that owe one.
WRITES_A_MODULE = re.compile(r"""Path\(["'](?P<module>[a-z_][a-z0-9_]*)\.py["']\)\.write_text\(""")


#: The examples that build their graph in a module they wrote, each with one node of that
#: module and the state a caller would plausibly hand it. Named rather than derived, because
#: the claim each makes is about a specific page — and held to the discovered set by the test
#: below, so a new page of this shape cannot land without one. The state differs per page
#: because the graphs do; it is carried here rather than shared so that each control calls its
#: node the way that page's workflow would, and never a shape only this file knows about.
WRITTEN_MODULE_LEDGER_CONTROLS = (
    (
        "docs/tutorials/extract-your-first-ir.md::your-first-ir",
        "research_agent",
        "plan",
        "{'question': 'q', 'notes': [], 'answer': ''}",
    ),
    (
        "docs/tutorials/extract-your-first-ir.md::knowability-classes",
        "research_agent",
        "triage",
        "{'question': 'q', 'notes': [], 'answer': ''}",
    ),
    (
        "docs/tutorials/contracts-and-annotations.md::declaring-contracts",
        "research_agent",
        "search",
        "{'question': 'q', 'notes': [], 'answer': ''}",
    ),
    (
        "docs/tutorials/contracts-and-annotations.md::wrapped-declarations",
        "wrapped_agent",
        "lost",
        "{'query': 'q', 'hits': ''}",
    ),
    (
        "docs/tutorials/contracts-and-annotations.md::the-sidecar",
        "trip_agent",
        "book_flight",
        "{'itinerary': 'i', 'budget': 1, 'booking_ref': '', 'notes': ''}",
    ),
    (
        "docs/tutorials/contracts-and-annotations.md::precedence",
        "booking_agent",
        "price_flight",
        "{'itinerary': 'i', 'budget': 1, 'booking_ref': '', 'notes': ''}",
    ),
    (
        "docs/tutorials/contracts-and-annotations.md::never-silent-upgrade",
        "cache_agent",
        "lookup",
        "{'query': 'weather', 'hits': ''}",
    ),
)

#: The same controls for the probe that hands a node no state at all, which needs no state.
WRITTEN_MODULE_NODES = tuple(
    (name, module, node) for name, module, node, _state in WRITTEN_MODULE_LEDGER_CONTROLS
)


def test_every_example_that_writes_a_module_carries_a_fired_ledger_control() -> None:
    """WA-07's same-change rule, made mechanical for the next page rather than the last one.

    A page that writes its own module is the one shape whose ledger the trailer covers by
    inspecting ``__file__`` rather than by name, so the coverage is easy to assume and hard to
    see. Every such example must appear below, where a control fires one of its node bodies.
    """
    owing = {
        example.name for example in EXAMPLES if WRITES_A_MODULE.search(example.code) is not None
    }
    controlled = {name for name, _module, _node in WRITTEN_MODULE_NODES}

    assert owing <= controlled, f"no fired ledger control for {sorted(owing - controlled)}"


@pytest.mark.parametrize(("name", "module", "node", "state"), WRITTEN_MODULE_LEDGER_CONTROLS)
def test_a_body_in_a_module_an_example_wrote_is_reported_by_the_ledger(
    name: str, module: str, node: str, state: str
) -> None:
    """The sweep's third kind of module, fired: swallowing a body call still fails the example.

    A module an example writes at run time is named neither ``__main__`` nor
    ``tests.sample_workflows.*``. Without the trailer's ``__file__`` clause this leg is dead —
    the body records and raises, a ``try`` block swallows it, and the trailer reports an empty
    ledger because it never looked at the module the raise came from.
    """
    example = next((item for item in EXAMPLES if item.name == name), None)
    assert example is not None, f"{name} is gone — re-point this control"

    result = run_example(
        example,
        root=REPO_ROOT,
        probe=f"try:\n    {module}.{node}({state})\nexcept BaseException:\n    pass\n",
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any(f"WA07-LEDGER ['{module}:{node}']" in problem for problem in result.problems)


@pytest.mark.parametrize(("name", "module", "node"), WRITTEN_MODULE_NODES)
def test_a_node_called_with_a_state_it_cannot_read_is_still_recorded(
    name: str, module: str, node: str
) -> None:
    """Why every body records on its *first* line, fired at the shape that finds out.

    ``node({})`` is the likeliest accidental invocation — a caller probing a callable to see
    what it returns has no real state to hand it. A body that read its state before arming
    itself would raise ``KeyError`` from the subscript, never reach the ledger, and leave
    nothing behind for a caller that swallowed the exception. Recording first is what makes
    this case indistinguishable from any other call, and this is that claim fired.
    """
    example = next((item for item in EXAMPLES if item.name == name), None)
    assert example is not None, f"{name} is gone — re-point this control"

    result = run_example(
        example,
        root=REPO_ROOT,
        probe=f"try:\n    {module}.{node}({{}})\nexcept BaseException:\n    pass\n",
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any(f"WA07-LEDGER ['{module}:{node}']" in problem for problem in result.problems)


def test_the_tool_a_page_shows_as_a_node_is_armed_like_any_other_body() -> None:
    """The other kind of body a page can register: a tool, whose implementation is not a node
    function and is therefore reached by a different route.

    `docs/tutorials/contracts-and-annotations.md` shows a `StructuredTool` as a node, because
    the tool-carried `args_schema` tier is what it is for, and says on the page that the tool
    "is read for its schema and never invoked". Extraction reads the schema off the class and
    never touches `func`, so the empty ledger on the real run is what holds that sentence —
    and this is the control that keeps the ledger from being vacuous. `run()` is deliberately
    the route: it is *not* in the armed invoke family, so it reaches the implementation, and
    the implementation's own first statement is what reports the call.
    """
    name = "docs/tutorials/contracts-and-annotations.md::precedence"
    example = next((item for item in EXAMPLES if item.name == name), None)
    assert example is not None, f"{name} is gone — re-point this control"

    result = run_example(
        example,
        root=REPO_ROOT,
        probe=(
            "try:\n"
            "    booking_agent.find_hotels.run({'destination': 'x', 'nights': 1})\n"
            "except BaseException:\n"
            "    pass\n"
        ),
    )

    assert result.returncode == 0, "the probe swallowed the raise, so the child finished"
    assert not result.ok
    assert any(
        "WA07-LEDGER ['booking_agent:find_hotels.impl']" in problem for problem in result.problems
    )


#: Examples that assign to an attribute of an imported module — ``compat.read = …``. The
#: fourth derived rule, and the newest: DOC-18's compatibility page needs to show what
#: ``extract()`` does on a substrate the machine running the example does not have, and does it
#: by pointing the version check's metadata reader at a value the page names inline. That is
#: safe — the target reads ``importlib.metadata`` and its result reaches nothing but the
#: classifier and two message builders — but nothing about the *shape* is: the same statement
#: aimed at ``Runnable.invoke`` would rebind a raiser this harness armed, and the trailer would
#: report a clean run because the raiser it counts is the one it installed. So the shape is
#: allowlisted by (example, dotted target) rather than permitted, and every other rebinding
#: fails here. Fired by the control below, which disarms exactly that way.
ATTRIBUTE_REBINDING_ALLOWED: dict[str, tuple[str, ...]] = {
    "docs/guides/install-and-compatibility.md::the-version-warning": (
        "compat.read_installed_versions",
    ),
    "docs/guides/install-and-compatibility.md::treating-the-warning-as-an-error": (
        "compat.read_installed_versions",
    ),
    "docs/guides/install-and-compatibility.md::an-out-of-range-substrate": (
        "compat.read_installed_versions",
    ),
}


def _rebound_attributes(code: str) -> set[str]:
    """Every dotted attribute target an example assigns to, by AST rather than by text."""
    targets: set[str] = set()
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigned: list[ast.expr] = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            assigned = [node.target]
        else:
            continue
        for target in assigned:
            if isinstance(target, ast.Attribute):
                targets.add(ast.unparse(target))
    return targets


def test_no_example_rebinds_an_attribute_outside_the_allowlist() -> None:
    """The fourth page-level rule, for the shape that can silently disarm the guard.

    The three rules above ask a page to *add* something (a ledger, a control). This one
    refuses something: an example may not rebind a module attribute unless it is named here,
    because the guard's raisers are module attributes too and rebinding one is indistinguishable
    from ordinary Python. The trailer cannot catch it — it reports the attempts its own raisers
    recorded, and a replaced raiser records nothing — so the rule has to live at discovery time.
    """
    for example in EXAMPLES:
        allowed = set(ATTRIBUTE_REBINDING_ALLOWED.get(example.name, ()))
        rebound = _rebound_attributes(example.code)
        assert rebound <= allowed, (
            f"{example.name} rebinds {sorted(rebound - allowed)}. A documentation example may "
            "not assign to a module attribute unless ATTRIBUTE_REBINDING_ALLOWED names it: the "
            "WA-07 guard's raisers are module attributes, and the trailer cannot tell a "
            "replaced raiser from one nothing tripped."
        )


def test_the_allowlist_names_examples_that_exist_and_really_rebind() -> None:
    """The other direction: a stale entry would license a rebinding nobody looked at."""
    by_name = {example.name: example for example in EXAMPLES}

    for name, targets in ATTRIBUTE_REBINDING_ALLOWED.items():
        example = by_name.get(name)
        assert example is not None, f"{name} is gone — drop its allowlist entry"
        assert set(targets) <= _rebound_attributes(example.code), (
            f"{name} no longer rebinds {sorted(set(targets) - _rebound_attributes(example.code))}"
        )


@requires_an_example
def test_a_rebinding_that_disarms_a_raiser_is_what_the_rule_refuses() -> None:
    """The rule fired: the disarm it exists to refuse really is invisible to the trailer.

    Appended to a real example, this rebinds an armed ``invoke`` and then calls it. The child
    finishes green with empty attempts and an empty ledger — the guard reports nothing, because
    the raiser it counts is the one this probe replaced. That is why the refusal is a
    discovery-time rule over the page's source rather than a run-time check.
    """
    assert CONTROL_EXAMPLE is not None
    probe = (
        "import langchain_core.runnables as _probe_runnables\n"
        "_probe_runnables.RunnableLambda.invoke = lambda self, value, *a, **k: value\n"
        "_probe_runnables.RunnableLambda(lambda value: value).invoke({'k': 1})\n"
    )

    result = run_example(CONTROL_EXAMPLE, root=REPO_ROOT, probe=probe)

    assert result.ok, "the disarm is invisible to the trailer — that is the finding"
    assert _rebound_attributes(probe) == {"_probe_runnables.RunnableLambda.invoke"}


@requires_an_example
def test_a_written_module_with_no_ledger_fails_rather_than_reads_clean() -> None:
    """The fail-closed leg, extended to the module kind this change introduced.

    A written module keeping no ``TRIPPED`` must be reported unledgered exactly as a sample
    workflow is: "nothing was recorded" must not give the same answer as "nothing ran".
    """
    assert CONTROL_EXAMPLE is not None
    result = run_example(
        CONTROL_EXAMPLE,
        root=REPO_ROOT,
        probe=(
            "from pathlib import Path as _ProbePath\n"
            '_ProbePath("ledgerless.py").write_text("VALUE = 1\\n")\n'
            "import ledgerless\n"
        ),
    )

    assert result.returncode == 0
    assert not result.ok
    assert any("WA07-UNLEDGERED ['ledgerless']" in problem for problem in result.problems)
    assert any("keeps no TRIPPED ledger" in problem for problem in result.problems)


def test_the_family_re_exports_are_the_family_ledger_itself() -> None:
    """Each re-export is a second *name* for one list, never a second list.

    ``travel_booking_defects`` and ``travel_booking_evolution`` both record into the v1 family
    ledger and re-export it so the fail-closed sweep finds a ledger under their own names too.
    Identity is the whole point: a rebinding (rather than an in-place clear) would leave the
    sweep reading an empty list that nothing writes to, which is the silent-vacuity case the
    sweep exists to refuse.
    """
    assert travel_booking_defects.TRIPPED is travel_booking.TRIPPED
    assert travel_booking_evolution.TRIPPED is travel_booking.TRIPPED


@requires_an_example
def test_a_sample_workflow_with_no_ledger_fails_rather_than_reads_clean() -> None:
    """Fail-closed: a fixture that could not report a swallowed sentinel is refused outright.

    Without this, importing a ledger-less sample workflow would make the ledger leg silently
    vacuous for that example — green because nothing could have been recorded, not because
    nothing ran.
    """
    assert CONTROL_EXAMPLE is not None
    result = run_example(
        CONTROL_EXAMPLE, root=REPO_ROOT, probe="import tests.sample_workflows.sentinel_contracts\n"
    )

    assert result.returncode == 0
    assert not result.ok
    assert any("WA07-UNLEDGERED ['sentinel_contracts']" in p for p in result.problems)
    assert any("keeps no TRIPPED ledger" in problem for problem in result.problems)


@requires_an_example
def test_a_page_cannot_answer_the_guard_on_its_own_behalf() -> None:
    """The trailer's own line is the last one, so an example printing a clean mark is ignored."""
    assert CONTROL_EXAMPLE is not None
    result = run_example(
        CONTROL_EXAMPLE,
        root=REPO_ROOT,
        probe=(
            "import sys as _spoof_sys\n"
            "from tests.sample_workflows import sentinel_graph as _fixture\n"
            "try:\n"
            "    _fixture.plan_step({'query': 'x'})\n"
            "except BaseException:\n"
            "    pass\n"
            "print('WA07-LEDGER []', file=_spoof_sys.stderr)\n"
        ),
    )

    assert result.returncode == 0
    assert not result.ok
    assert any("sentinel_graph:node 'plan_step' was invoked" in p for p in result.problems)


@requires_an_example
def test_importing_the_network_client_fails_the_example() -> None:
    """The one leg with nothing to raise: langgraph's remote client must stay unimported."""
    assert CONTROL_EXAMPLE is not None
    result = run_example(CONTROL_EXAMPLE, root=REPO_ROOT, probe="import langgraph.pregel.remote\n")

    assert not result.ok
    assert "a network client was imported" in result.stderr


@requires_an_example
def test_the_guard_runs_before_the_page_code_and_the_trailer_after_it() -> None:
    """The assembled child, in order — a guard spliced in after the code would guard nothing."""
    assert CONTROL_EXAMPLE is not None
    program = child_program(CONTROL_EXAMPLE, probe="# probe\n")

    assert program.index("_GebraStateGraph.compile = ") < program.index(CONTROL_EXAMPLE.code)
    assert program.index("_gebra_arm_runnables(") < program.index(CONTROL_EXAMPLE.code)
    assert program.index(CONTROL_EXAMPLE.code) < program.index("# probe\n")
    assert program.index("# probe\n") < program.index("WA07-ATTEMPTS")


def test_the_child_inherits_an_allowlisted_environment_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider key or a tracing switch in a contributor's shell reaches no example.

    The two are set here rather than assumed absent, so the control fails if the allowlist is
    ever replaced by the parent environment — the state this test exists to prevent.
    """
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")

    result = run_example(
        DocExample(
            path="synthetic.md",
            example_id="environment",
            line=1,
            code=(
                "import os\n"
                "families = {'LANGCHAIN', 'LANGSMITH', 'OPENAI', 'ANTHROPIC', 'AWS'}\n"
                "print(sorted(n for n in os.environ if n.split('_')[0] in families))\n"
            ),
            expected_output="[]\n",
            output_line=2,
        ),
        root=REPO_ROOT,
    )

    assert result.ok, result.report()


# ── The comparison itself ────────────────────────────────────────────────────────────────


def test_output_that_does_not_match_the_page_is_a_failure() -> None:
    """The check that gives every other example its meaning."""
    result = run_example(
        DocExample(
            path="synthetic.md",
            example_id="drifted",
            line=1,
            code='print("what the code prints")\n',
            expected_output="what the page claims\n",
            output_line=5,
        ),
        root=REPO_ROOT,
    )

    assert not result.ok
    assert any("printed output does not match the page (line 5)" in p for p in result.problems)


def test_an_example_declaring_no_output_may_not_print() -> None:
    result = run_example(
        DocExample(
            path="synthetic.md",
            example_id="chatty",
            line=1,
            code='print("unannounced")\n',
            expected_output="",
            output_line=None,
        ),
        root=REPO_ROOT,
    )

    assert not result.ok
    assert any("must print nothing" in problem for problem in result.problems)


def test_an_example_that_raises_is_a_failure() -> None:
    result = run_example(
        DocExample(
            path="synthetic.md",
            example_id="broken",
            line=1,
            code="raise ValueError('boom')\n",
            expected_output="",
            output_line=None,
        ),
        root=REPO_ROOT,
    )

    assert not result.ok
    assert any("exited 1" in problem for problem in result.problems)
    assert "boom" in result.report()


def test_an_example_writes_outside_the_repository() -> None:
    """Examples run in a temporary directory, so a stored snapshot never lands in the tree."""
    result = run_example(
        DocExample(
            path="synthetic.md",
            example_id="writes",
            line=1,
            code=(
                "from pathlib import Path\n"
                "Path('scratch.txt').write_text('x', encoding='utf-8')\n"
                "print(Path.cwd() == Path.cwd().resolve())\n"
            ),
            expected_output="True\n",
            output_line=2,
        ),
        root=REPO_ROOT,
    )

    assert result.ok, result.report()
    assert not (REPO_ROOT / "scratch.txt").exists()


# ── The command-line surface, and its wiring ─────────────────────────────────────────────


def _run_harness(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the harness exactly as CI does — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(HARNESS), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_list_mode_names_every_marked_example() -> None:
    listed = _run_harness("--list")

    assert listed.returncode == 0, listed.stderr
    for example in EXAMPLES:
        assert example.name in listed.stdout
    assert f"{len(EXAMPLES)} example(s) marked" in listed.stdout


def test_the_report_mode_is_green_on_this_repository() -> None:
    """The proof CI is entitled to: the command in ci.yml, run, exiting zero."""
    reported = _run_harness("--report")

    assert reported.returncode == 0, reported.stdout + reported.stderr
    assert f"{len(EXAMPLES)}/{len(EXAMPLES)} documentation example(s) green" in reported.stdout


def test_malformed_markup_makes_the_harness_exit_one(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "broken.md").write_text(
        "<!-- gebra:example id=x -->\nnot a fence\n", encoding="utf-8"
    )

    assert main(["--root", str(tmp_path), "--report"]) == 1


def test_ci_builds_the_site_and_runs_the_examples() -> None:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "docs" in workflow["jobs"], "the documentation gates need their own CI job"
    steps = [
        step["run"]
        for step in workflow["jobs"]["docs"]["steps"]
        if isinstance(step.get("run"), str)
    ]
    assert any("mkdocs build --strict" in step for step in steps)
    assert any("tools/docs_examples.py --report" in step for step in steps)
    assert any("docs/requirements.txt" in step for step in steps)
