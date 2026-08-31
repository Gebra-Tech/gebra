"""The README quickstart harness, and the WA-07 guard its commands run under.

Card DOC-04's quickstart is a promise about what happens to someone who has just installed
the package, so three claims live here. First, the markup: what the README may declare, and
what the harness refuses rather than silently skipping — a mis-marked step that vanished from
CI would leave the promise enforcing nothing. Second, the comparison: a transcript's declared
elisions say which lines are omitted, and every line the page *does* show must be one the
command printed, contiguously and in order. Third, the guard: a quickstart reads a workflow
definition and never runs one, and every raiser that claim rests on is fired by a control
probe in the same environment the quickstart runs in — a tripwire nobody trips reports
nothing.

The module reads Markdown and starts child processes. It executes no workflow node, calls no
model and opens no connection, and neither does anything it starts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.readme_quickstart import (
    DEFAULT_README,
    EXPECTED_ARMED,
    ConsoleStep,
    FileStep,
    QuickstartError,
    StepResult,
    _guard_problems,
    discover,
    main,
    match_transcript,
    parse_markdown,
    run_quickstart,
    split_command,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "tools" / "readme_quickstart.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: The interpreter the control probes run against. In CI the quickstart itself runs against a
#: fresh environment holding only the built wheel; the guard is the same code either way, and
#: firing the probes here keeps them cheap and independent of a build step.
PROBE_PYTHON = Path(sys.executable)


def _page(*lines: str) -> str:
    return "\n".join(lines) + "\n"


# ── The markup: what the README may declare ──────────────────────────────────────────────


def test_a_file_step_and_a_console_step_parse() -> None:
    parsed = parse_markdown(
        _page(
            "<!-- gebra-quickstart:file path=booking.py -->",
            "```python",
            "workflow = None",
            "```",
            "",
            "<!-- gebra-quickstart:console id=verify exit=1 -->",
            "```console",
            "$ gebra verify booking:workflow",
            "P-02 termination-witness — fail",
            "```",
        ),
        path="README.md",
    )

    assert len(parsed) == 2
    written, console = parsed
    assert isinstance(written, FileStep)
    assert (written.path, written.body, written.line) == ("booking.py", "workflow = None\n", 2)
    assert isinstance(console, ConsoleStep)
    assert console.command == "gebra verify booking:workflow"
    assert console.transcript == "P-02 termination-witness — fail\n"
    assert (console.expect_exit, console.step_id) == (1, "verify")


def test_a_console_step_defaults_to_a_zero_exit() -> None:
    (console,) = parse_markdown(
        _page(
            "<!-- gebra-quickstart:console id=version -->",
            "```console",
            "$ gebra --version",
            "gebra 0.0.1.dev0",
            "```",
        ),
        path="README.md",
    )

    assert isinstance(console, ConsoleStep)
    assert console.expect_exit == 0


def test_directives_inside_a_fenced_block_are_shown_markup_not_declarations() -> None:
    """A page must be able to document this notation without declaring a step by doing so."""
    parsed = parse_markdown(
        _page(
            "````markdown",
            "<!-- gebra-quickstart:console id=illustration -->",
            "```console",
            "$ gebra verify",
            "```",
            "````",
            "",
            "<!-- gebra-quickstart:console id=real -->",
            "```console",
            "$ gebra --version",
            "gebra 0.0.1.dev0",
            "```",
        ),
        path="README.md",
    )

    assert [step.step_id for step in parsed if isinstance(step, ConsoleStep)] == ["real"]


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        pytest.param(
            _page("<!-- gebra-quickstart:run id=x -->", "```console", "$ gebra", "```"),
            "unknown directive gebra-quickstart:run",
            id="unknown-directive",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console -->", "```console", "$ gebra", "```"),
            "needs id=<lowercase-slug>",
            id="missing-id",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console id=Bad_Id -->", "```console", "$ g", "```"),
            "needs id=<lowercase-slug>",
            id="malformed-id",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console id=x lang=sh -->", "```console", "$ g", "```"),
            "takes only id=, exit= and python=",
            id="extra-attribute",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console id=x exit=soon -->", "```console", "$ g", "```"),
            "exit= must be a non-negative integer",
            id="non-numeric-exit",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ g",
                "```",
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ g",
                "```",
            ),
            "duplicate step id",
            id="duplicate-id",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console id=x -->", "```console", "gebra", "```"),
            "must open with a '\\$'-prefixed command line",
            id="no-prompt",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ gebra --version",
                "gebra 0.0.1.dev0",
                "$ gebra verify",
                "```",
            ),
            "carries a second command",
            id="two-commands",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ gebra verify | tee report.txt",
                "```",
            ),
            "shell syntax this harness does not interpret",
            id="shell-pipeline",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console id=x -->", "```console", "$ ", "```"),
            "names no command",
            id="empty-command",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ gebra --version",
                "...",
                "```",
            ),
            "pins no output",
            id="elision-only-transcript",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:file path=/etc/passwd -->", "```text", "x", "```"),
            "must be a relative path",
            id="absolute-path",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:file path=../booking.py -->", "```text", "x", "```"),
            "must be a relative path",
            id="parent-escape",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:file id=x -->", "```text", "y", "```"),
            "takes only path=",
            id="file-with-id",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:file path=sitecustomize.py -->", "```py", "x", "```"),
            "the WA-07 guard's own slot",
            id="guard-shadowing-filename",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:file path=pkg/usercustomize.py -->", "```py", "x", "```"),
            "the WA-07 guard's own slot",
            id="guard-shadowing-filename-nested",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x python=maybe -->",
                "```console",
                "$ gebra --version",
                "gebra 0.0.1.dev0",
                "```",
            ),
            "python= must be yes or no",
            id="malformed-python-attribute",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                '$ gebra verify "unbalanced',
                "```",
            ),
            "the command does not parse",
            id="unbalanced-quote",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ PATH=/usr/bin gebra --version",
                "gebra 0.0.1.dev0",
                "```",
            ),
            "sets PATH",
            id="repointed-path",
        ),
        pytest.param(
            _page(
                "<!-- gebra-quickstart:console id=x -->",
                "```console",
                "$ NO_COLOR=1",
                "```",
            ),
            "assignments only",
            id="assignments-only",
        ),
        pytest.param(
            _page("<!-- gebra-quickstart:console id=x -->", "not a fence"),
            "must be followed by a fenced code block",
            id="no-fence",
        ),
    ],
)
def test_malformed_markup_is_refused_rather_than_skipped(page: str, expected: str) -> None:
    """Every way of mis-marking a step is an error, so none of them removes it from CI."""
    with pytest.raises(QuickstartError, match=expected):
        parse_markdown(page, path="README.md")


def test_a_gebra_example_directive_is_not_this_harnesss_business() -> None:
    """The two namespaces are disjoint, so neither harness refuses the other's markup."""
    parsed = parse_markdown(
        _page("<!-- gebra:example id=library -->", "```python", "import gebra", "```"),
        path="README.md",
    )

    assert parsed == []


# ── The command line, and the one shell feature it reproduces ────────────────────────────


@pytest.mark.parametrize(
    ("command", "assignments", "argv"),
    [
        ("gebra --version", {}, ["gebra", "--version"]),
        (
            "PYTHONPATH=. gebra verify booking:workflow",
            {"PYTHONPATH": "."},
            ["gebra", "verify", "booking:workflow"],
        ),
        (
            "NO_COLOR=1 COLUMNS=80 gebra verify",
            {"NO_COLOR": "1", "COLUMNS": "80"},
            ["gebra", "verify"],
        ),
        # An `=` after the command name is an argument, not an assignment.
        (
            "gebra verify --strict=determinism-replay",
            {},
            ["gebra", "verify", "--strict=determinism-replay"],
        ),
    ],
)
def test_leading_assignments_are_split_from_the_command(
    command: str, assignments: dict[str, str], argv: list[str]
) -> None:
    assert split_command(command) == (assignments, argv)


# ── The comparison: declared elisions, and what they do not excuse ───────────────────────


def test_a_transcript_with_no_elision_must_match_line_for_line() -> None:
    assert match_transcript("one\ntwo\n", "one\ntwo\n") is None
    assert match_transcript("one\ntwo\n", "one\nTWO\n") is not None


def test_an_elision_omits_lines_it_does_not_excuse_the_ones_shown() -> None:
    assert match_transcript("one\n...\nfour\n", "one\ntwo\nthree\nfour\n") is None
    assert match_transcript("one\n...\nfour\n", "one\ntwo\nthree\n") is not None


def test_a_shown_run_must_appear_contiguously() -> None:
    """Two lines shown together are a claim that the command printed them together."""
    assert match_transcript("one\ntwo\n", "one\ntwo\n") is None
    assert match_transcript("...\none\ntwo\n", "one\nbetween\ntwo\n") is not None


def test_an_unelided_transcript_pins_the_start_and_the_end() -> None:
    assert match_transcript("two\n", "one\ntwo\n") is not None
    assert match_transcript("one\n", "one\ntwo\n") is not None
    assert match_transcript("...\ntwo\n", "one\ntwo\n") is None
    assert match_transcript("one\n...\n", "one\ntwo\n") is None


def test_an_empty_transcript_says_the_command_prints_nothing() -> None:
    assert match_transcript("", "") is None
    assert match_transcript("", "unannounced\n") is not None


def test_trailing_whitespace_is_not_compared() -> None:
    """A terminal's own line padding is not a claim the page is making."""
    assert match_transcript("one\n", "one   \n") is None


# ── WA-07: the guard, and a control for every raiser it rests on ─────────────────────────

#: One probe per raiser: what to run, the exit it produces, and what the guard must report.
PROBES: tuple[tuple[str, str, int, str], ...] = (
    (
        "socket-connect",
        "python -c \"import socket; socket.socket().connect(('example.invalid', 443))\"",
        1,
        "socket.connect",
    ),
    (
        "socket-connect-ex",
        "python -c \"import socket; socket.socket().connect_ex(('example.invalid', 443))\"",
        1,
        "socket.connect_ex",
    ),
    # The connectionless half: a UDP resolver query or a telemetry emitter never connects, so
    # `connect` alone would leave the widest quiet route open.
    (
        "socket-send",
        "python -c \"import socket; socket.socket().send(b'x')\"",
        1,
        "socket.send",
    ),
    (
        "socket-sendall",
        "python -c \"import socket; socket.socket().sendall(b'x')\"",
        1,
        "socket.sendall",
    ),
    (
        "socket-sendto",
        "python -c \"import socket; socket.socket().sendto(b'x', ('example.invalid', 53))\"",
        1,
        "socket.sendto",
    ),
    (
        "socket-sendmsg",
        "python -c \"import socket; socket.socket().sendmsg([b'x'])\"",
        1,
        "socket.sendmsg",
    ),
    (
        "getaddrinfo",
        "python -c \"import socket; socket.getaddrinfo('example.invalid', 443)\"",
        1,
        "socket.getaddrinfo",
    ),
    (
        "gethostbyname",
        "python -c \"import socket; socket.gethostbyname('example.invalid')\"",
        1,
        "socket.gethostbyname",
    ),
    (
        "gethostbyname-ex",
        "python -c \"import socket; socket.gethostbyname_ex('example.invalid')\"",
        1,
        "socket.gethostbyname_ex",
    ),
    (
        "gethostbyaddr",
        "python -c \"import socket; socket.gethostbyaddr('127.0.0.1')\"",
        1,
        "socket.gethostbyaddr",
    ),
    (
        "getnameinfo",
        "python -c \"import socket; socket.getnameinfo(('127.0.0.1', 80), 0)\"",
        1,
        "socket.getnameinfo",
    ),
    (
        "create-connection",
        "python -c \"import socket; socket.create_connection(('example.invalid', 443))\"",
        1,
        "socket.create_connection",
    ),
    (
        "compile",
        'python -c "from langgraph.graph.state import StateGraph; StateGraph.compile(None)"',
        1,
        "StateGraph.compile",
    ),
    # INTROSPECTION-SPEC §1 rule 1 names the invoke family beside nodes and routers, and
    # arming `StateGraph.compile` does not reach it: an LCEL chain runs without anything being
    # compiled.
    (
        "lcel-invoke",
        (
            'python -c "from langchain_core.runnables import RunnableLambda; '
            'RunnableLambda(lambda value: value).invoke(1)"'
        ),
        1,
        "RunnableLambda.invoke",
    ),
    # The arming tuple is data, so a member nobody fires is a member a typo could delete.
    (
        "lcel-batch",
        (
            'python -c "from langchain_core.runnables import RunnableLambda; '
            'RunnableLambda(lambda value: value).batch([1])"'
        ),
        1,
        # Inherited from the armed base rather than overridden — which is the half of the
        # sweep that would go untested if only overrides were probed.
        ".batch",
    ),
    (
        "lcel-stream",
        (
            'python -c "from langchain_core.runnables import RunnableLambda; '
            'list(RunnableLambda(lambda value: value).stream(1))"'
        ),
        1,
        ".stream",
    ),
    # A model call is armed on its own account: a local or stubbed model reaches no network,
    # and "no connection was opened" would otherwise be the whole of the no-LLM-call claim.
    (
        "model-invoke",
        (
            'python -c "from langchain_core.language_models.fake_chat_models import '
            "FakeListChatModel; FakeListChatModel(responses=['x']).invoke('hi')\""
        ),
        1,
        "BaseChatModel.invoke",
    ),
    # Record-before-raise: catching the exception does not hide the attempt.
    (
        "swallowed",
        (
            "python -c \"import socket\ntry:\n    socket.gethostbyname('example.invalid')\n"
            'except BaseException:\n    pass"'
        ),
        0,
        "socket.gethostbyname",
    ),
)


@pytest.fixture(scope="module")
def probe_results() -> dict[str, StepResult]:
    """Every control probe, fired once, in one guarded environment."""
    steps: list[Any] = [
        ConsoleStep(step_id=probe_id, command=command, transcript="", expect_exit=exit_code, line=0)
        for probe_id, command, exit_code, _ in PROBES
    ]
    results = run_quickstart(steps, python=PROBE_PYTHON, capture=True)
    return {
        result.step.step_id: result for result in results if isinstance(result.step, ConsoleStep)
    }


@pytest.mark.parametrize(
    ("probe_id", "raiser"),
    [pytest.param(probe[0], probe[3], id=probe[0]) for probe in PROBES],
)
def test_each_raiser_the_guard_rests_on_is_armed(
    probe_results: dict[str, StepResult], probe_id: str, raiser: str
) -> None:
    result = probe_results[probe_id]

    assert not result.ok, result.report()
    assert any("WA-07: a guarded operation was reached" in problem for problem in result.problems)
    assert any(raiser in problem for problem in result.problems)


def test_a_swallowed_attempt_still_fails_the_step(probe_results: dict[str, StepResult]) -> None:
    result = probe_results["swallowed"]

    assert result.returncode == 0, "the probe swallowed the raise, so the command finished"
    assert not result.ok


def test_a_command_that_touches_nothing_is_clean() -> None:
    """The positive control: without it, every probe above could be failing for another reason."""
    step = ConsoleStep(
        step_id="benign", command='python -c "print(42)"', transcript="42\n", expect_exit=0, line=0
    )

    (result,) = run_quickstart([step], python=PROBE_PYTHON)

    assert result.ok, result.report()


def test_the_named_environments_own_console_scripts_are_what_run(tmp_path: Path) -> None:
    """A virtual environment's `bin/python` is a symlink to the interpreter it was made from.

    Resolving it would put the *base* installation's `bin` on the child's PATH, and the
    console scripts the quickstart types — the whole point of naming an environment — would
    silently be someone else's, or absent. This is that mistake, held.
    """
    bin_dir = tmp_path / "env" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to(sys.executable)
    tool = bin_dir / "gebra-probe"
    tool.write_text(f"#!{sys.executable}\nprint('from the named environment')\n", encoding="utf-8")
    tool.chmod(0o755)
    step = ConsoleStep(
        step_id="script",
        command="gebra-probe",
        transcript="from the named environment\n",
        expect_exit=0,
        line=0,
    )

    (result,) = run_quickstart([step], python=bin_dir / "python")

    assert result.ok, result.report()


def test_the_guard_cannot_be_shadowed_from_the_working_directory(tmp_path: Path) -> None:
    """`site` imports the first `sitecustomize` on the path, and the guard directory is it.

    The markup refuses a page that names one of those files, so this fires the same attack
    from *outside* the markup — a step that writes the module at run time — and requires the
    guard still to have armed. Both halves matter: the refusal is the door, this is the lock.
    """
    steps: list[Any] = [
        ConsoleStep(
            step_id="plant",
            command=(
                'python -c "from pathlib import Path; '
                "Path('sitecustomize.py').write_text('pass\\n')\""
            ),
            transcript="",
            expect_exit=0,
            line=0,
        ),
        ConsoleStep(
            step_id="after",
            command="PYTHONPATH=. python -c \"import socket; socket.gethostbyname('x.invalid')\"",
            transcript="",
            expect_exit=1,
            line=0,
        ),
    ]

    planted, after = run_quickstart(steps, python=PROBE_PYTHON, capture=True)

    assert planted.ok, planted.report()
    assert not after.ok
    assert any("socket.gethostbyname" in problem for problem in after.problems)


def test_a_step_declaring_python_no_still_runs_under_the_guard() -> None:
    """The opt-out waives the *evidence* requirement, never the guard itself.

    `python=no` says "expect no armed manifest from this one". It must not become a way to
    run Python unguarded, so the guard is still on `PYTHONPATH` and a trip still fails.
    """
    step = ConsoleStep(
        step_id="opted-out",
        command="python -c \"import socket; socket.gethostbyname('example.invalid')\"",
        transcript="",
        expect_exit=1,
        line=0,
        expects_guard=False,
    )

    (result,) = run_quickstart([step], python=PROBE_PYTHON, capture=True)

    assert not result.ok
    assert any("socket.gethostbyname" in problem for problem in result.problems)


def test_the_child_inherits_an_allowlisted_environment_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider key or a tracing switch in a contributor's shell reaches no command.

    Set here rather than assumed absent, so the control fails if the allowlist is ever
    replaced by the parent environment — the state this test exists to prevent.
    """
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    step = ConsoleStep(
        step_id="environment",
        command=(
            "python -c \"import os; families = {'LANGCHAIN', 'LANGSMITH', 'OPENAI', "
            "'ANTHROPIC', 'AWS'}; print(sorted(n for n in os.environ "
            "if n.split('_')[0] in families))\""
        ),
        transcript="[]\n",
        expect_exit=0,
        line=0,
    )

    (result,) = run_quickstart([step], python=PROBE_PYTHON)

    assert result.ok, result.report()


def test_a_python_command_that_armed_nothing_is_a_failure_not_a_pass() -> None:
    """Fail-closed: the guard not having run must never read as the guard having found nothing."""
    problems = _guard_problems([], expects_guard=True)

    assert problems
    assert "'nothing was recorded' is not 'nothing ran'" in problems[0]
    assert "python=no" in problems[0]


def test_a_family_the_guard_could_not_arm_is_a_hole() -> None:
    delta = [f"ARMED {name}" for name in EXPECTED_ARMED] + ["UNARMED Runnable.invoke-family"]

    problems = _guard_problems(delta, expects_guard=True)

    assert problems and "an unarmed family is a hole" in problems[0]


def test_a_step_that_declares_it_runs_no_python_needs_no_armed_manifest() -> None:
    """The only way out of the fail-closed rule, and it is written on the page, not guessed."""
    assert _guard_problems([], expects_guard=False) == []


# ── The README's own quickstart ──────────────────────────────────────────────────────────


def test_the_readme_marks_a_quickstart() -> None:
    """The floor under the claim: a harness with nothing to run would pass vacuously."""
    steps = discover(DEFAULT_README)

    assert [step for step in steps if isinstance(step, FileStep)]
    assert [step for step in steps if isinstance(step, ConsoleStep)]


def test_the_readme_quickstart_runs_and_prints_what_the_page_shows() -> None:
    """The whole claim, once: the commands the README shows, run, against this environment."""
    results = run_quickstart(discover(DEFAULT_README), python=PROBE_PYTHON)

    failed = [result for result in results if not result.ok]
    assert not failed, "\n".join(result.report() for result in failed)


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


def test_the_list_mode_names_every_step() -> None:
    listed = _run_harness("--list")

    assert listed.returncode == 0, listed.stderr
    assert f"{len(discover(DEFAULT_README))} quickstart step(s) marked" in listed.stdout


def test_malformed_markup_makes_the_harness_exit_one(tmp_path: Path) -> None:
    broken = tmp_path / "README.md"
    broken.write_text("<!-- gebra-quickstart:console id=x -->\nnot a fence\n", encoding="utf-8")

    assert main(["--readme", str(broken), "--report"]) == 1


def test_a_readme_marking_no_step_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    empty = tmp_path / "README.md"
    empty.write_text("# nothing to run here\n", encoding="utf-8")

    assert main(["--readme", str(empty), "--report"]) == 1


def test_ci_runs_the_quickstart_against_a_fresh_environment() -> None:
    """The acceptance box, read off the workflow: built wheel, empty environment, verbatim."""
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "readme-quickstart" in workflow["jobs"], "the quickstart needs its own CI job"
    steps = [
        step["run"]
        for step in workflow["jobs"]["readme-quickstart"]["steps"]
        if isinstance(step.get("run"), str)
    ]

    assert any("uv build" in step for step in steps), "the job must build the shipped artifacts"
    install = next(step for step in steps if "venv" in step)
    assert "python -m venv /tmp/readme-quickstart" in install
    assert "pip install --no-cache-dir dist/*.whl" in install
    assert any(
        "tools/readme_quickstart.py --report --python /tmp/readme-quickstart/bin/python" in step
        for step in steps
    )


def test_the_fresh_environment_holds_the_wheel_and_nothing_of_this_checkout() -> None:
    """No `-e`, no dev extra, no lockfile: the quickstart may not lean on the repository."""
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    install = next(
        step["run"]
        for step in workflow["jobs"]["readme-quickstart"]["steps"]
        if isinstance(step.get("run"), str) and "pip install" in step["run"]
    )

    assert "-e" not in install.split()
    assert "[dev]" not in install
    assert "uv sync" not in install
