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

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

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


@requires_an_example
@pytest.mark.parametrize(
    ("module", "call", "expected"),
    [
        # The module the examples on this site actually import. A control on some *other*
        # fixture would prove the sweep works where it is not used and could not fail where
        # it is — which is the shape of a tripwire that reports nothing.
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
    ],
)
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
