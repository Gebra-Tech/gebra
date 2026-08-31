"""README quickstart harness — the shell half of WA-12 (card DOC-04).

:mod:`tools.docs_examples` runs a page's *Python* blocks in the repository's own
environment. A quickstart is a different claim: it is what someone who has just installed
the package types into a shell, and it is only worth anything if the package it runs
against is the one they would have installed. So this harness executes the README's
quickstart against **an environment the caller names** — in CI, a fresh virtual environment
holding nothing but the wheel `uv build` produced — and holds each command's terminal
transcript to what the README shows.

Marking a quickstart — two directives, in a namespace disjoint from the Python harness's
(``gebra:``), so neither refuses the other's markup::

    <!-- gebra-quickstart:file path=booking.py -->
    ```python
    workflow = StateGraph(BookingState)
    ```

    <!-- gebra-quickstart:console id=verify exit=1 -->
    ```console
    $ gebra verify booking:workflow
    P-02 termination-witness — fail  (1 finding: 1 fatal)
    ...
    ```

A ``file`` step writes the block into the working directory, exactly as a reader following
the page would. A ``console`` step runs the one ``$`` command and compares what it printed —
stdout and stderr merged, the way a terminal shows them — against the rest of the block. A
line that is exactly ``...`` marks omitted lines: everything the page *does* show must
appear, in order, and contiguously within each shown run. ``exit=`` pins the exit status,
default ``0``; ``python=no`` says the command runs no Python and so leaves the guard nothing
to report, which is the only way out of the fail-closed rule below.

The command is not handed to a shell. It is split with :mod:`shlex`, leading ``NAME=value``
assignments are applied to the child environment, and anything a shell would interpret —
a pipe, a redirection, a substitution, a glob — is refused rather than approximated, so the
line the page shows and the line that runs cannot mean two different things. ``PATH=`` is
refused too: a command that repoints it is no longer running the environment the harness was
pointed at, which is the one thing the run is claiming.

**The WA-07 guard.** A quickstart reads a workflow definition; it never runs one. Each
command runs with a generated ``sitecustomize.py`` on ``PYTHONPATH``, which every Python
process in that environment imports at startup: name resolution and connection opening
raise, ``StateGraph.compile`` raises, and every ``invoke``/``stream``/``batch`` override in
the ``Runnable`` tree — which contains ``Pregel`` and ``BaseChatModel``, so a compiled graph
and a stubbed model are unrunnable on their own account — raises. Each raiser records into a
log before raising, so an attempt a ``try`` block swallowed still fails the run.

The sweep is **fail-closed** in both directions: the guard writes what it armed, and *every*
command is required to produce the complete armed set unless its directive says
``python=no`` — "nothing was recorded" must never read as "nothing ran". If the substrate
cannot be imported the guard records the family as ``UNARMED``, which fails the same way.
:mod:`tests.docs.test_readme_quickstart` fires a control probe at every raiser.

Three boundaries, stated rather than implied.

The guard lives in the interpreters this harness starts: a subprocess one of them spawns
inherits ``PYTHONPATH`` and so the guard, but a non-Python command does not.

**Arming the ``invoke`` family does not reach a node body by every route.** Extraction
unwraps a node to the innermost user callable (``gebra.extraction.contracts``), so a call on
*that* reference would go past the raisers, which sit on the substrate's own entry points.
The documentation harness closes this by having a page arm the bodies it defines; a
quickstart cannot, because the file it writes is one a reader copies and runs, and a node
that raises is not that. So for ``booking.py`` the covered routes are the substrate's —
``compile``, the ``invoke``/``stream``/``batch`` family, the network — and a direct call on
an unwrapped callable is a stated residual rather than a caught one.

And the harness *writes* to the environment it is given — the guard directory is its own,
but the working directory is a temporary tree, so the environment named by ``--python``
should be one the caller is willing to have commands run inside.

Usage::

    python tools/readme_quickstart.py --list                  # the parsed steps
    python tools/readme_quickstart.py --report                # run them; exit 1 on failure
    python tools/readme_quickstart.py --report --python <venv>/bin/python
    python tools/readme_quickstart.py --capture               # print what the commands print

The scan itself imports nothing and executes nothing: it reads Markdown and matches text.
Execution happens only in the children :func:`run_quickstart` starts.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

if __package__ in (None, ""):  # pragma: no cover - executed as `python tools/…`, as CI does
    # A script's `sys.path[0]` is `tools/`, not the repository root, so the shared readers
    # below would be unimportable. `python -m tools.readme_quickstart` needs no such help.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.docs_examples import (
    FENCE_RE,
    ID_RE,
    INHERITED_ENV,
    DocExampleError,
    closing_fence,
    directive_pattern,
    parse_attrs,
    read_fence,
)

#: The repository root — this file lives in ``tools/``.
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: The one page a quickstart may be marked in. Unlike the Python harness, which scans the
#: whole site, this one has a single subject by design: the quickstart is the README's.
DEFAULT_README: Final = REPO_ROOT / "README.md"

#: The directive namespace, disjoint from ``gebra:`` (:mod:`tools.docs_examples`).
NAMESPACE: Final = "gebra-quickstart"
FILE_DIRECTIVE: Final = "file"
CONSOLE_DIRECTIVE: Final = "console"
KNOWN_DIRECTIVES: Final[frozenset[str]] = frozenset({FILE_DIRECTIVE, CONSOLE_DIRECTIVE})

_DIRECTIVE_RE: Final = directive_pattern(NAMESPACE)

#: A line that is exactly this marks omitted output.
ELISION: Final = "..."

#: The command prompt a console block's command line carries.
PROMPT: Final = "$ "

#: What a shell would interpret and this harness will not approximate.
SHELL_METACHARACTERS: Final = "|&;<>()$`*?\n"

#: Everything the guard must have armed before a command that ran a Python entry point from
#: the environment may count as clean. A missing name is a failure, not a smaller guard.
EXPECTED_ARMED: Final[frozenset[str]] = frozenset(
    {
        "socket.connect",
        "socket.connect_ex",
        # The connectionless half. A UDP resolver query or a telemetry emitter never
        # connects, so refusing `connect` alone would leave the widest quiet route open.
        "socket.send",
        "socket.sendall",
        "socket.sendto",
        "socket.sendmsg",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyname_ex",
        "socket.gethostbyaddr",
        "socket.getnameinfo",
        "socket.create_connection",
        "StateGraph.compile",
        "Runnable.invoke-family",
    }
)


class QuickstartError(RuntimeError):
    """The README's quickstart markup is malformed — reported with its file and line."""


@dataclass(frozen=True)
class FileStep:
    """A file the reader creates, and the harness writes into the working directory."""

    path: str
    body: str
    line: int

    @property
    def name(self) -> str:
        return f"write {self.path}"


@dataclass(frozen=True)
class ConsoleStep:
    """One command the reader types, and the transcript the README says it produced.

    Attributes:
        step_id: The page-unique ``id=``.
        command: The command line, without its ``$`` prompt — this is what runs.
        transcript: The rest of the block: what the page shows the command printing, with
            ``...`` lines marking omissions.
        expect_exit: The pinned exit status.
        line: The 1-based line of the block's opening fence.
        expects_guard: Whether the command runs a Python program from the environment under
            test, and so must leave the guard's complete armed manifest behind. True unless
            the directive says ``python=no`` — fail-closed by default, because the shape of
            the mistake this rules out is a command that quietly ran unguarded.
    """

    step_id: str
    command: str
    transcript: str
    expect_exit: int
    line: int
    expects_guard: bool = True

    @property
    def name(self) -> str:
        return f"$ {self.command}"


Step = FileStep | ConsoleStep


@dataclass(frozen=True)
class StepResult:
    """What running one step did. :attr:`ok` is the whole verdict; :attr:`problems` says why."""

    step: Step
    output: str
    returncode: int | None
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def report(self) -> str:
        """A failure message a reader can act on without re-running anything."""
        lines = [f"{self.step.name} (line {self.step.line})"]
        lines += [f"  - {problem}" for problem in self.problems]
        if self.output.strip():
            lines.append("  what it printed:")
            lines += [f"    {line}" for line in self.output.rstrip().splitlines()]
        return "\n".join(lines)


# ── Discovery: read Markdown, match text, execute nothing ────────────────────────────────


#: Module names ``site`` imports at interpreter startup. A page writing one of these into the
#: working directory would be handing itself the guard's own slot, so the markup refuses it
#: outright — belt to the braces of putting the guard directory first on ``PYTHONPATH``.
RESERVED_FILENAMES: Final[frozenset[str]] = frozenset({"sitecustomize.py", "usercustomize.py"})


def _relative_path(value: str, *, path: str, line_no: int) -> str:
    """A ``path=`` a reader could type: relative, no parent escape, no root."""
    candidate = PurePosixPath(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise QuickstartError(
            f"{path}:{line_no}: {NAMESPACE}:file path={value!r} must be a relative path "
            "inside the working directory"
        )
    if candidate.name in RESERVED_FILENAMES:
        raise QuickstartError(
            f"{path}:{line_no}: {NAMESPACE}:file path={value!r} is a name the interpreter "
            "imports at startup — a page may not write one, because that is the WA-07 "
            "guard's own slot"
        )
    return value


def _console_step(
    body: str, *, step_id: str, expect_exit: int, expects_guard: bool, path: str, fence_line: int
) -> ConsoleStep:
    """Split a console block into its one command and the transcript that followed it."""
    lines = body.splitlines()
    if not lines or not lines[0].startswith(PROMPT):
        raise QuickstartError(
            f"{path}:{fence_line}: gebra-quickstart:console must open with a "
            f"{PROMPT.strip()!r}-prefixed command line"
        )
    command = lines[0][len(PROMPT) :].strip()
    if not command:
        raise QuickstartError(f"{path}:{fence_line}: gebra-quickstart:console names no command")
    later = [line for line in lines[1:] if line.startswith(PROMPT)]
    if later:
        raise QuickstartError(
            f"{path}:{fence_line}: gebra-quickstart:console carries a second command "
            f"({later[0].strip()!r}); one block is one command, so its exit status is unambiguous"
        )
    offending = [character for character in SHELL_METACHARACTERS if character in command]
    if offending:
        raise QuickstartError(
            f"{path}:{fence_line}: the command uses shell syntax this harness does not "
            f"interpret ({''.join(offending)!r}); it runs commands, not shell lines"
        )
    # Split here rather than at run time: an unbalanced quote is malformed markup, and it
    # should read as such instead of surfacing as a traceback out of the middle of a run.
    try:
        assignments, argv = split_command(command)
    except ValueError as error:
        raise QuickstartError(
            f"{path}:{fence_line}: the command does not parse: {error}"
        ) from error
    if not argv:
        raise QuickstartError(
            f"{path}:{fence_line}: the command is assignments only, and runs nothing"
        )
    if "PATH" in assignments:
        raise QuickstartError(
            f"{path}:{fence_line}: the command sets PATH, which would take it out of the "
            "environment this harness was pointed at — the one thing the run is claiming"
        )
    transcript = "".join(f"{line}\n" for line in lines[1:])
    if transcript.strip() and not [line for line in lines[1:] if line.strip() != ELISION]:
        raise QuickstartError(
            f"{path}:{fence_line}: a transcript of nothing but {ELISION!r} pins no output"
        )
    return ConsoleStep(
        step_id=step_id,
        command=command,
        transcript=transcript,
        expect_exit=expect_exit,
        line=fence_line,
        expects_guard=expects_guard,
    )


def parse_markdown(text: str, *, path: str) -> list[Step]:
    """Extract the quickstart's steps from one page's source, in document order.

    A directive *inside* a fenced block is markup being shown rather than a step being
    declared, and is skipped — otherwise a page could not document this notation.

    Raises:
        QuickstartError: on an unknown directive, a missing or malformed attribute, a
            duplicate step id, a console block that does not open with one command, or a
            directive that is not followed by a fenced code block.
    """
    lines = text.splitlines()
    steps: list[Step] = []
    seen_ids: set[str] = set()

    index = 0
    while index < len(lines):
        directive = _DIRECTIVE_RE.match(lines[index])
        if directive is None:
            fence = FENCE_RE.match(lines[index])
            if fence is not None and lines[index].startswith(fence.group("fence")):
                index = closing_fence(lines, index, fence.group("fence")) + 1
                continue
            index += 1
            continue
        kind = directive.group("kind")
        line_no = index + 1
        if kind not in KNOWN_DIRECTIVES:
            raise QuickstartError(
                f"{path}:{line_no}: unknown directive {NAMESPACE}:{kind} — "
                f"expected one of {', '.join(sorted(KNOWN_DIRECTIVES))}"
            )
        # The two shared readers report in `tools.docs_examples`'s own exception; a caller of
        # this harness should see this harness's, with the same message.
        try:
            attrs = parse_attrs(directive.group("attrs"), path=path, line_no=line_no)
            body, fence_line, index = read_fence(
                lines, index, path=path, directive=kind, namespace=NAMESPACE
            )
        except DocExampleError as error:
            raise QuickstartError(str(error)) from error

        if kind == FILE_DIRECTIVE:
            target = attrs.pop("path", "")
            if attrs:
                raise QuickstartError(
                    f"{path}:{line_no}: {NAMESPACE}:file takes only path=, got {sorted(attrs)}"
                )
            steps.append(
                FileStep(
                    path=_relative_path(target, path=path, line_no=line_no),
                    body=body,
                    line=fence_line,
                )
            )
            continue

        step_id = attrs.pop("id", "")
        declared_exit = attrs.pop("exit", "0")
        declared_python = attrs.pop("python", "yes")
        if attrs:
            raise QuickstartError(
                f"{path}:{line_no}: {NAMESPACE}:console takes only id=, exit= and python=, "
                f"got {sorted(attrs)}"
            )
        if declared_python not in {"yes", "no"}:
            raise QuickstartError(
                f"{path}:{line_no}: {NAMESPACE}:console python= must be yes or no, "
                f"got {declared_python!r}"
            )
        if not ID_RE.match(step_id):
            raise QuickstartError(
                f"{path}:{line_no}: {NAMESPACE}:console needs id=<lowercase-slug>, got {step_id!r}"
            )
        if step_id in seen_ids:
            raise QuickstartError(f"{path}:{line_no}: duplicate step id {step_id!r}")
        seen_ids.add(step_id)
        if not declared_exit.isdigit():
            raise QuickstartError(
                f"{path}:{line_no}: {NAMESPACE}:console exit= must be a non-negative "
                f"integer, got {declared_exit!r}"
            )
        steps.append(
            _console_step(
                body,
                step_id=step_id,
                expect_exit=int(declared_exit),
                expects_guard=declared_python == "yes",
                path=path,
                fence_line=fence_line,
            )
        )
    return steps


def discover(readme: Path = DEFAULT_README) -> list[Step]:
    """The quickstart's steps, in the order the README presents them."""
    relative = readme.name
    try:
        relative = readme.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:  # pragma: no cover - a README outside the repository, in tests only
        pass
    return parse_markdown(readme.read_text(encoding="utf-8"), path=relative)


# ── The WA-07 guard, generated into the environment's PYTHONPATH ─────────────────────────

#: The guard's source, with the log path spliced in. ``site`` imports ``sitecustomize`` at
#: interpreter startup, so every Python process this harness starts is armed before its own
#: first line — including the console script the reader types, which is a Python program.
GUARD_SOURCE: Final = '''\
"""WA-07 guard for the README quickstart harness (card DOC-04), imported by `site`."""

import socket as _socket

_LOG = {log!r}
_ARMED = []


def _record(kind, name):
    with open(_LOG, "a", encoding="utf-8") as handle:
        handle.write(kind + " " + name + "\\n")


def _raiser(name):
    def _seen(*args, **kwargs):
        _record("TRIP", name)
        raise AssertionError(name + " was reached from the README quickstart")

    return _seen


class _GuardedSocket(_socket.socket):
    connect = _raiser("socket.connect")
    connect_ex = _raiser("socket.connect_ex")
    send = _raiser("socket.send")
    sendall = _raiser("socket.sendall")
    sendto = _raiser("socket.sendto")
    sendmsg = _raiser("socket.sendmsg")


_socket.socket = _GuardedSocket
_socket.getaddrinfo = _raiser("socket.getaddrinfo")
_socket.gethostbyname = _raiser("socket.gethostbyname")
_socket.gethostbyname_ex = _raiser("socket.gethostbyname_ex")
_socket.gethostbyaddr = _raiser("socket.gethostbyaddr")
_socket.getnameinfo = _raiser("socket.getnameinfo")
_socket.create_connection = _raiser("socket.create_connection")
_ARMED += [
    "socket.connect",
    "socket.connect_ex",
    "socket.send",
    "socket.sendall",
    "socket.sendto",
    "socket.sendmsg",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyname_ex",
    "socket.gethostbyaddr",
    "socket.getnameinfo",
    "socket.create_connection",
]

try:
    from langgraph.graph.state import StateGraph as _StateGraph
except Exception:  # the substrate is missing or broken — say so rather than pass quietly
    _record("UNARMED", "StateGraph.compile")
else:
    _StateGraph.compile = _raiser("StateGraph.compile")
    _ARMED.append("StateGraph.compile")

try:
    # The submodules by name, not the package: `langchain_core.language_models` resolves its
    # exports lazily through `__getattr__`, so importing it leaves `BaseChatModel` out of the
    # subclass tree the sweep walks — and a model call would be armed only through the socket
    # raisers, which a local or stubbed model never reaches.
    import langchain_core.language_models.chat_models  # noqa: F401 - for the tree below
    import langchain_core.language_models.llms  # noqa: F401 - for the tree below
    from langchain_core.runnables.base import Runnable as _Runnable
except Exception:
    _record("UNARMED", "Runnable.invoke-family")
else:

    def _arm(cls, seen):
        if id(cls) in seen:
            return
        seen.add(id(cls))
        for _name in ("invoke", "ainvoke", "stream", "astream", "batch", "abatch"):
            if _name in vars(cls):
                setattr(cls, _name, _raiser(cls.__name__ + "." + _name))
        for _sub in cls.__subclasses__():
            _arm(_sub, seen)

    _arm(_Runnable, set())
    _ARMED.append("Runnable.invoke-family")

for _name in _ARMED:
    _record("ARMED", _name)
'''


def write_guard(directory: Path, log: Path) -> Path:
    """Generate the guard into ``directory``; the caller puts it on ``PYTHONPATH``."""
    guard = directory / "sitecustomize.py"
    guard.write_text(GUARD_SOURCE.format(log=str(log)), encoding="utf-8")
    return guard


# ── Execution: one child per console step, in a temporary working directory ──────────────


def split_command(command: str) -> tuple[dict[str, str], list[str]]:
    """A command line as ``(leading NAME=value assignments, argv)``.

    The assignments are the only shell feature reproduced, because the alternative is a
    README whose commands only work under an environment the page does not show.
    """
    tokens = shlex.split(command)
    assignments: dict[str, str] = {}
    while tokens:
        name, separator, value = tokens[0].partition("=")
        if not separator or not name.replace("_", "").isalnum() or name[:1].isdigit():
            break
        assignments[name] = value
        tokens = tokens[1:]
    return assignments, tokens


def match_transcript(expected: str, actual: str) -> str | None:
    """``None`` when the output matches the page; otherwise why it does not.

    Trailing whitespace is not compared: a Markdown file cannot be relied on to carry it,
    and a terminal's own line padding is not a claim the page is making.
    """
    expected_lines = [line.rstrip() for line in expected.splitlines()]
    actual_lines = [line.rstrip() for line in actual.splitlines()]
    while expected_lines and not expected_lines[-1]:
        expected_lines.pop()
    while actual_lines and not actual_lines[-1]:
        actual_lines.pop()

    if not expected_lines:
        if actual_lines:
            return f"the page shows no output, but the command printed {len(actual_lines)} line(s)"
        return None

    open_start = expected_lines[0] == ELISION
    open_end = expected_lines[-1] == ELISION
    segments: list[list[str]] = []
    current: list[str] = []
    for line in expected_lines:
        if line == ELISION:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(line)
    if current:
        segments.append(current)

    cursor = 0
    for position, segment in enumerate(segments):
        anchored = position == 0 and not open_start
        found = _find_segment(actual_lines, segment, cursor, anchored=anchored)
        if found is None:
            return (
                f"the page shows a line the command did not print, at or after output line "
                f"{cursor + 1}:\n    expected: {segment[0]!r}"
            )
        cursor = found + len(segment)
    if not open_end and cursor != len(actual_lines):
        return (
            f"the command printed {len(actual_lines) - cursor} line(s) the page does not show, "
            f"starting at output line {cursor + 1}: {actual_lines[cursor]!r}"
        )
    return None


def _find_segment(
    actual: list[str], segment: list[str], start: int, *, anchored: bool
) -> int | None:
    """The index at which ``segment`` appears contiguously in ``actual``, at or after ``start``."""
    last = start if anchored else len(actual) - len(segment)
    for index in range(start, last + 1):
        if actual[index : index + len(segment)] == segment:
            return index
    return None


def _environment(*, bin_dir: Path, guard_dir: Path) -> dict[str, str]:
    """What a step's child inherits: an allowlist, the environment's ``bin``, the guard.

    The allowlist is :mod:`tools.docs_examples`'s, for its reason — a contributor with a
    provider key or a tracing switch exported must not hand either to a documented command.
    ``COLUMNS`` is deliberately *not* inherited: the report's width would otherwise depend on
    the terminal the harness happened to run in, and the README shows one width.
    """
    environment = {name: os.environ[name] for name in INHERITED_ENV if name in os.environ}
    environment["PATH"] = os.pathsep.join(
        [str(bin_dir), *([environment["PATH"]] if "PATH" in environment else [])]
    )
    environment["PYTHONPATH"] = str(guard_dir)
    environment["PYTHONOPTIMIZE"] = "0"
    return environment


def _guard_problems(delta: list[str], *, expects_guard: bool) -> list[str]:
    """What the guard says about a finished command, independently of what it printed."""
    problems: list[str] = []
    trips = [line for line in delta if line.startswith("TRIP ")]
    unarmed = [line for line in delta if line.startswith("UNARMED ")]
    armed = {line.split(" ", 1)[1] for line in delta if line.startswith("ARMED ")}
    if trips:
        problems.append(f"WA-07: a guarded operation was reached — {sorted(set(trips))}")
    if unarmed:
        problems.append(
            f"WA-07: the guard could not arm {sorted(set(unarmed))} — an unarmed family is a "
            "hole, not a smaller guard"
        )
    if expects_guard and not EXPECTED_ARMED <= armed:
        problems.append(
            f"WA-07: the guard did not run, or armed less than it must — missing "
            f"{sorted(EXPECTED_ARMED - armed)}. A Python program from this environment ran "
            "without the guard reporting; 'nothing was recorded' is not 'nothing ran'. A "
            "step that genuinely runs no Python says so with python=no."
        )
    return problems


def run_quickstart(steps: list[Step], *, python: Path, capture: bool = False) -> list[StepResult]:
    """Run every step in order, in a temporary working directory, under the guard.

    Args:
        steps: What :func:`discover` parsed.
        python: The interpreter whose environment the commands run against — in CI, a fresh
            virtual environment holding the built wheel.
        capture: When true, a console step's transcript is not compared; the caller prints
            what it saw instead. Everything else — the exit status, the guard — still holds.
    """
    # Absolute, because the commands run in a temporary working directory: a relative entry
    # on the child's PATH would be resolved against *that*, and the environment under test
    # would silently not be the one named. Absolute but *not* resolved: a virtual
    # environment's `bin/python` is a symlink to the interpreter it was made from, so
    # following it would put the base installation's `bin` on PATH and the console scripts
    # under test out of reach.
    bin_dir = Path(os.path.abspath(python)).parent
    results: list[StepResult] = []
    with tempfile.TemporaryDirectory(prefix="gebra-readme-quickstart-") as scratch:
        root = Path(scratch)
        workdir = root / "work"
        workdir.mkdir()
        guard_dir = root / "guard"
        guard_dir.mkdir()
        log = root / "guard.log"
        log.touch()
        write_guard(guard_dir, log)
        environment = _environment(bin_dir=bin_dir, guard_dir=guard_dir)

        for step in steps:
            if isinstance(step, FileStep):
                target = workdir / step.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(step.body, encoding="utf-8")
                results.append(StepResult(step=step, output="", returncode=None, problems=()))
                continue

            before = len(log.read_text(encoding="utf-8").splitlines())
            assignments, argv = split_command(step.command)
            child_environment = dict(environment)
            for name, value in assignments.items():
                # The guard must survive a command that sets PYTHONPATH itself, which the
                # quickstart does: gebra inserts no import path of its own (CLI-SPEC §2.4),
                # so the reader supplies one. The guard directory goes *first*, because
                # `site` imports the first `sitecustomize` on the path — a working directory
                # holding a file of that name would otherwise replace the guard with the
                # page's own code, which is the one thing a page must not be able to do. It
                # holds nothing else, so the reader's entry is first for every other name.
                if name == "PYTHONPATH":
                    child_environment[name] = os.pathsep.join([str(guard_dir), value])
                else:
                    child_environment[name] = value
            problems: list[str] = []
            try:
                finished = subprocess.run(
                    argv,
                    cwd=workdir,
                    env=child_environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            except OSError as error:
                results.append(
                    StepResult(
                        step=step,
                        output="",
                        returncode=None,
                        problems=(f"the command could not be run: {error}",),
                    )
                )
                continue
            delta = log.read_text(encoding="utf-8").splitlines()[before:]
            problems += _guard_problems(delta, expects_guard=step.expects_guard)
            if finished.returncode != step.expect_exit:
                problems.append(
                    f"exited {finished.returncode}, and the page pins exit={step.expect_exit}"
                )
            if not capture:
                mismatch = match_transcript(step.transcript, finished.stdout)
                if mismatch is not None:
                    problems.append(mismatch)
            results.append(
                StepResult(
                    step=step,
                    output=finished.stdout,
                    returncode=finished.returncode,
                    problems=tuple(problems),
                )
            )
    return results


# ── The command-line surface CI runs ─────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """``--list`` the steps, ``--report`` a counted run, or ``--capture`` what they print."""
    parser = argparse.ArgumentParser(description=__doc__, add_help=True)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README, help="the page to read")
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="the interpreter whose environment the commands run against",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list the parsed steps and exit")
    mode.add_argument("--report", action="store_true", help="run every step, counted")
    mode.add_argument("--capture", action="store_true", help="run, and print what each printed")
    arguments = parser.parse_args(argv)

    try:
        steps = discover(arguments.readme)
    except QuickstartError as error:
        print(f"the quickstart markup is malformed: {error}", file=sys.stderr)
        return 1

    if not steps:
        print("no quickstart step is marked in the README", file=sys.stderr)
        return 1

    if arguments.list:
        for step in steps:
            print(f"{step.name} (line {step.line})")
        print(f"{len(steps)} quickstart step(s) marked")
        return 0

    results = run_quickstart(steps, python=arguments.python, capture=arguments.capture)
    failures = [result for result in results if not result.ok]
    for result in results:
        print(f"{'ok  ' if result.ok else 'FAIL'} {result.step.name}")
        if arguments.capture and result.output:
            print("".join(f"    {line}\n" for line in result.output.splitlines()), end="")

    print(f"\n{len(results) - len(failures)}/{len(results)} quickstart step(s) green")
    for failure in failures:
        print(f"\n{failure.report()}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover — the CI entry point, exercised by tests/docs
    raise SystemExit(main())
