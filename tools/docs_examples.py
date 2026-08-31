"""Executable-examples harness for the published documentation (card DOC-01; WA-07/WA-12).

WA-12 asks that nothing published describe unbuilt behaviour, and the enforceable half of
that is: **a documented example is the code CI runs.** This module is the mechanism. A page
marks an example with an HTML comment, and the harness discovers it, executes the fenced
block *verbatim* in a fresh interpreter, and compares what it printed against the page's own
expected-output block. A marked example's prose and behaviour cannot drift apart, because
the bytes in the page are the bytes that ran.

Marking an example — two directives, both invisible in every Markdown renderer::

    <!-- gebra:example id=first-verify -->
    ```python
    import gebra
    print("hello")
    ```

    <!-- gebra:output id=first-verify -->
    ```text
    hello
    ```

The output block is optional and its absence is not a hole: an example with no declared
output must print nothing. Every example's stdout is pinned either way.

**The WA-07 guard.** Documentation examples read workflow definitions; they never run them.
Each example executes in a child interpreter where name resolution and connection opening
raise from the first line, ``StateGraph.compile`` raises from before ``gebra`` is imported,
every ``Runnable.invoke``/``stream``/``batch`` override loaded at that point raises, and
constructing a socket raises once the example's own code begins. Connecting raises
throughout — only socket *construction* is tolerated during the guard's own imports, for
the reason ``tests/extraction/test_dispatch.py`` records.

The sample graphs the examples are written against arm the other half: every node body and
router in ``tests/sample_workflows/`` raises if it is called, and records the call in the
module's ``TRIPPED`` ledger before raising, so a sentinel a ``try`` block swallowed still
fails the run. That sweep is **fail-closed** — a sample-workflow module keeping no ledger is
reported as unledgered and fails the example, rather than reading as clean. It covers three
kinds of module: ``tests/sample_workflows/``, the example's own ``__main__``, and any module
the example **wrote into the child's working directory and imported**, which a page needs when
what the extractor reads off a node body depends on that body living in a file. The child
reports the attempt list, the ledger and the unledgered set on stderr; a non-empty any of
the three is a failure, as is importing langgraph's network client.
:mod:`tests.docs.test_doc_examples` fires a control probe at every raiser, because a guard
nobody trips proves nothing.

Three boundaries, stated rather than implied. Arming ``StateGraph.compile`` excludes the
compiled path and only that one — extracting an LCEL ``Runnable`` compiles nothing — so this
harness admits builder-path, LCEL and document-path examples; an example needing a compiled
graph needs the guard extended, deliberately a change to this file with its own controls and
never a per-example opt-out. The armed surface is the sample workflows **and the example's
own ``__main__``**: a body a page defines is its author's code, which the invoke family does
not reach — extraction unwraps to the bare callable — so a page that defines the graph it
shows arms its own bodies, recording into a module-level ``TRIPPED`` before raising, exactly
as a sample workflow does. Pages that need a ready-made graph build against
``tests/sample_workflows/`` instead. And the guard lives in
one interpreter — a subprocess an example spawns inherits none of it, and the private
interpreter internals behind the guarded modules are not patched. This catches a page that
innocently reaches out; it is not built against a page written to get around it.

Usage::

    python tools/docs_examples.py --list      # what is marked, and where
    python tools/docs_examples.py --report    # run them all, counted; exit 1 on any failure

The scan itself imports nothing and executes nothing: it reads Markdown and matches text.
Execution happens only in the child interpreters :func:`run_example` starts.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The repository root — this file lives in ``tools/``.
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: Where examples may be marked. The published site plus the README, which is the one page
#: outside ``docs/`` a reader meets first; it matches the honest-claims lint's prose scope.
DEFAULT_INCLUDE: Final[tuple[str, ...]] = ("docs/**/*.md", "README.md")

#: The directive vocabulary. An unrecognised ``gebra:`` directive is an error rather than a
#: silent skip — a typo must not quietly remove an example from CI.
EXAMPLE_DIRECTIVE: Final = "example"
OUTPUT_DIRECTIVE: Final = "output"
KNOWN_DIRECTIVES: Final[frozenset[str]] = frozenset({EXAMPLE_DIRECTIVE, OUTPUT_DIRECTIVE})


def directive_pattern(namespace: str) -> re.Pattern[str]:
    """The directive regex for one comment namespace — ``<!-- <namespace>:<kind> … -->``.

    Parameterised because a second harness marks its own blocks in the same pages under its
    own namespace (``gebra-quickstart:``, :mod:`tools.readme_quickstart`). Keeping the two
    vocabularies disjoint is deliberate: an unknown ``gebra:`` directive is an error here, so
    a namespace that overlapped would make each harness refuse the other's markup.
    """
    return re.compile(
        rf"^<!--\s*{re.escape(namespace)}:"
        r"(?P<kind>[a-z][a-z-]*)\s*(?P<attrs>[^>]*?)-->\s*$"
    )


_DIRECTIVE_RE: Final = directive_pattern("gebra")
_ATTR_RE: Final = re.compile(r"(?P<key>[a-z][a-z-]*)=(?P<value>[^\s]+)")
FENCE_RE: Final = re.compile(r"^(?P<fence>`{3,}|~{3,})\s*(?P<info>.*?)\s*$")
ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: What the child prints on stderr once the example has finished — the guard's own verdict.
ATTEMPTS_MARK: Final = "WA07-ATTEMPTS"
LEDGER_MARK: Final = "WA07-LEDGER"
UNLEDGERED_MARK: Final = "WA07-UNLEDGERED"
IMPORT_SOCKETS_MARK: Final = "WA07-IMPORT-SOCKETS"
TRIP_MARK: Final = "WA07-TRIP"

#: What the child interpreter inherits. An allowlist rather than the parent's environment:
#: a contributor with ``LANGCHAIN_TRACING_V2`` or a provider key exported would otherwise
#: hand both to every example, and a tracing client that starts a background uploader is a
#: connection attempt racing the trailer rather than one the guard reports cleanly.
INHERITED_ENV: Final[tuple[str, ...]] = (
    "PATH",
    "HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    # Windows' home-directory triple: without them `Path.home()` misbehaves on a contributor's
    # machine. CI runs this job on Linux, so they are ergonomics rather than a gate.
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
)


class DocExampleError(RuntimeError):
    """A page's example markup is malformed — reported with its file and line."""


@dataclass(frozen=True)
class DocExample:
    """One marked example: the code a page shows, and what the page says it prints.

    Attributes:
        path: The page, relative to the repository root.
        example_id: The page-unique ``id=`` the two directives share.
        line: The 1-based line of the code block's opening fence.
        code: The fenced block's body, verbatim — this is what runs.
        expected_output: The declared stdout, or ``""`` when the page declares none.
        output_line: The 1-based line of the output block's opening fence, or ``None``.
    """

    path: str
    example_id: str
    line: int
    code: str
    expected_output: str
    output_line: int | None

    @property
    def name(self) -> str:
        """``page.md::id`` — the identity a test item and a report line both use."""
        return f"{self.path}::{self.example_id}"


@dataclass(frozen=True)
class ExampleResult:
    """What one guarded run did. :attr:`ok` is the whole verdict; :attr:`problems` says why."""

    example: DocExample
    returncode: int
    stdout: str
    stderr: str
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def report(self) -> str:
        """A failure message a reader can act on without re-running anything."""
        lines = [f"{self.example.name} (line {self.example.line})"]
        lines += [f"  - {problem}" for problem in self.problems]
        if self.stderr.strip():
            lines.append("  child stderr:")
            lines += [f"    {line}" for line in self.stderr.rstrip().splitlines()]
        return "\n".join(lines)


# ── Discovery: read Markdown, match text, execute nothing ────────────────────────────────


def parse_attrs(attrs: str, *, path: str, line_no: int) -> dict[str, str]:
    """Parse ``key=value`` directive attributes, refusing anything that is not one."""
    parsed: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attrs):
        parsed[match.group("key")] = match.group("value")
    consumed = "".join(match.group(0) for match in _ATTR_RE.finditer(attrs))
    if len(consumed) != len(attrs.replace(" ", "")):
        raise DocExampleError(f"{path}:{line_no}: unparsable directive attributes: {attrs!r}")
    return parsed


def closing_fence(lines: list[str], opening_index: int, fence: str) -> int:
    """The index of the line closing the fence opened at ``opening_index``, or ``len(lines)``.

    A closing fence is a run of the opening character at least as long as the opening one and
    nothing else, so a three-backtick block nested inside a four-backtick block does not close
    it — which is what lets a page show this harness's own markup inside a fenced example.
    """
    for index in range(opening_index + 1, len(lines)):
        stripped = lines[index].strip()
        if len(stripped) >= len(fence) and not stripped.strip(fence[0]):
            return index
    return len(lines)


def read_fence(
    lines: list[str], start: int, *, path: str, directive: str, namespace: str = "gebra"
) -> tuple[str, int, int]:
    """Read the fenced block that must follow a directive at ``start`` (0-based).

    Args:
        lines: The page, split into lines.
        start: The 0-based index of the directive line.
        path: The page's path, for the message.
        directive: The directive's kind, for the message.
        namespace: The directive's comment namespace, for the message — the second harness
            marks its blocks under its own (:mod:`tools.readme_quickstart`), and a message
            naming the wrong one sends a reader to the wrong vocabulary.

    Returns:
        The block body, the 1-based line of its opening fence, and the 0-based index of the
        line after its closing fence.

    Raises:
        DocExampleError: if no fence opens on the next non-blank line, or none closes it.
    """
    index = start + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        raise DocExampleError(
            f"{path}:{start + 1}: {namespace}:{directive} directive ends the file"
        )
    opening = FENCE_RE.match(lines[index])
    if opening is None:
        raise DocExampleError(
            f"{path}:{index + 1}: {namespace}:{directive} must be followed by a fenced code "
            f"block, found {lines[index].strip()!r}"
        )
    fence = opening.group("fence")
    body_start = index + 1
    closing = closing_fence(lines, index, fence)
    if closing >= len(lines):
        raise DocExampleError(f"{path}:{index + 1}: unclosed fenced code block")
    body = "".join(f"{line}\n" for line in lines[body_start:closing])
    return body, index + 1, closing + 1


def parse_markdown(text: str, *, path: str) -> list[DocExample]:
    """Extract every marked example from one page's source.

    A directive *inside* a fenced block is markup being shown rather than an example being
    declared, and is skipped — otherwise a page could not document this notation.

    Raises:
        DocExampleError: on an unknown directive, a missing or duplicate ``id``, an output
            block naming no example, a second output for one example, or a directive that
            is not followed by a fenced code block.
    """
    lines = text.splitlines()
    codes: dict[str, tuple[str, int]] = {}
    outputs: dict[str, tuple[str, int]] = {}
    order: list[str] = []

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
            raise DocExampleError(
                f"{path}:{line_no}: unknown directive gebra:{kind} — "
                f"expected one of {', '.join(sorted(KNOWN_DIRECTIVES))}"
            )
        attrs = parse_attrs(directive.group("attrs"), path=path, line_no=line_no)
        example_id = attrs.pop("id", "")
        if attrs:
            raise DocExampleError(
                f"{path}:{line_no}: gebra:{kind} takes only id=, got {sorted(attrs)}"
            )
        if not ID_RE.match(example_id):
            raise DocExampleError(
                f"{path}:{line_no}: gebra:{kind} needs id=<lowercase-slug>, got {example_id!r}"
            )
        body, fence_line, index = read_fence(lines, index, path=path, directive=kind)
        if kind == EXAMPLE_DIRECTIVE:
            if example_id in codes:
                raise DocExampleError(f"{path}:{line_no}: duplicate example id {example_id!r}")
            codes[example_id] = (body, fence_line)
            order.append(example_id)
        else:
            if example_id not in codes:
                raise DocExampleError(
                    f"{path}:{line_no}: gebra:output id={example_id!r} names no example "
                    "declared above it"
                )
            if example_id in outputs:
                raise DocExampleError(f"{path}:{line_no}: duplicate output for {example_id!r}")
            outputs[example_id] = (body, fence_line)

    examples = []
    for example_id in order:
        code, fence_line = codes[example_id]
        declared = outputs.get(example_id)
        examples.append(
            DocExample(
                path=path,
                example_id=example_id,
                line=fence_line,
                code=code,
                expected_output=declared[0] if declared else "",
                output_line=declared[1] if declared else None,
            )
        )
    return examples


def discover(
    root: Path = REPO_ROOT, *, include: tuple[str, ...] = DEFAULT_INCLUDE
) -> list[DocExample]:
    """Every marked example under ``root``, in page then document order."""
    pages: list[Path] = []
    for pattern in include:
        pages += sorted(root.glob(pattern))
    examples: list[DocExample] = []
    for page in sorted(set(pages)):
        relative = page.relative_to(root).as_posix()
        examples += parse_markdown(page.read_text(encoding="utf-8"), path=relative)
    return examples


# ── Execution: one guarded child interpreter per example ─────────────────────────────────

#: The guard, run before the page's code. Network primitives raise from the first line;
#: socket *construction* is only counted until the substrate is imported, for the reason
#: ``tests/extraction/test_dispatch.py`` records (urllib3 probes IPv6 capability at import),
#: and raises from there on. ``StateGraph.compile`` raises from before ``gebra`` is imported.
#: The gebra surface an example may use is imported here so that the example's own imports
#: reach modules already in ``sys.modules`` rather than the armed socket.
GUARD_PROLOGUE: Final = """\
import os as _gebra_os, socket as _gebra_socket, sys as _gebra_sys

_gebra_attempts = []
_gebra_built = []


def _gebra_record(name):
    def _seen(*args, **kwargs):
        _gebra_attempts.append(name)
        print("WA07-TRIP", file=_gebra_sys.stderr)
        raise AssertionError(name + " was reached from a documentation example")

    return _seen


class _GebraCountSocket(_gebra_socket.socket):
    # Construction is counted rather than refused during the import phase; *connecting* is
    # refused even there, because the reason construction is tolerated (urllib3's IPv6
    # capability probe) only ever constructs.
    def __new__(cls, *args, **kwargs):
        _gebra_built.append(args)
        return super().__new__(cls, *args, **kwargs)

    connect = _gebra_record("socket.connect")
    connect_ex = _gebra_record("socket.connect_ex")


class _GebraTripSocket(_gebra_socket.socket):
    def __new__(cls, *args, **kwargs):
        _gebra_attempts.append("socket")
        print("WA07-TRIP", file=_gebra_sys.stderr)
        raise AssertionError("a socket was created from a documentation example")


_gebra_socket.socket = _GebraCountSocket
_gebra_socket.getaddrinfo = _gebra_record("getaddrinfo")
_gebra_socket.gethostbyname = _gebra_record("gethostbyname")
_gebra_socket.create_connection = _gebra_record("create_connection")

from langgraph.graph.state import StateGraph as _GebraStateGraph

_GebraStateGraph.compile = _gebra_record("StateGraph.compile")

import gebra
import gebra.annotations
import gebra.audit
import gebra.diff
import gebra.extraction
import gebra.ir
import gebra.lineage
import gebra.snapshot
import gebra.store
import gebra.verify
import gebra.versioning
import langchain_core.runnables

# Imported for the sweep below rather than for the examples: it puts `BaseChatModel` and
# `BaseLLM` in the tree, so a model call is armed on its own account. Without it, only a
# model that reached the network would trip anything, and a local or stubbed one would not.
import langchain_core.language_models

# INTROSPECTION-SPEC §1 rule 1 names `Runnable.invoke/stream/batch` beside node functions
# and routers, and arming `StateGraph.compile` does not reach them: an LCEL chain is invoked
# without anything being compiled. Every override loaded at this point is armed, base class
# included, so an unswept subclass that does not override still lands on the base raiser.
# `Pregel` is inside this tree too (`PregelProtocol` subclasses `Runnable`), so a compiled
# graph obtained by any route other than `StateGraph.compile` is still unrunnable.
def _gebra_arm_runnables(cls, seen):
    if id(cls) in seen:
        return
    seen.add(id(cls))
    for _name in ("invoke", "ainvoke", "stream", "astream", "batch", "abatch"):
        if _name in vars(cls):
            setattr(cls, _name, _gebra_record(cls.__name__ + "." + _name))
    for _sub in cls.__subclasses__():
        _gebra_arm_runnables(_sub, seen)


_gebra_arm_runnables(langchain_core.runnables.base.Runnable, set())

assert _gebra_attempts == [], _gebra_attempts
_gebra_socket.socket = _GebraTripSocket

# ── the page's own code, verbatim, from here ─────────────────────────────────────────────
"""

#: Reported after the example (and after any control probe) so a probe can still be seen.
#: It goes to stderr on purpose: the example's stdout is compared against the page and must
#: carry nothing the page does not show.
GUARD_EPILOGUE: Final = """
# ── the harness trailer ──────────────────────────────────────────────────────────────────
# The ledger sweep is fail-closed. A sample-workflow module keeping no ``TRIPPED`` is
# reported as unledgered rather than read as clean: its bodies raise, but a raise a ``try``
# block swallowed would leave nothing behind, and "nothing behind" must not be the same
# answer as "nothing ran".
#
# ``__main__`` — the example's own code — is swept too, because a page may define the graph
# it shows rather than import one (the README does, and a README a reader cannot reproduce
# would fail WA-12). Its bodies then have to arm themselves the way a sample workflow does.
# It is exempt from the *unledgered* leg alone: most examples define no body at all, and a
# ledger they would never write to is noise. Which pages owe one is a page-level rule with
# its own test (``tests/docs/test_doc_examples.py``), not a guess made here.
#
# And so is any module the example **wrote and imported**, identified by its ``__file__``
# resolving inside the child's own working directory — a fresh temporary tree nothing else
# can reach. A page may need its graph in a real module rather than in ``__main__``, because
# what the extractor can read off a node body depends on the body being in a file (a tutorial
# whose transcript came from a string-compiled ``__main__`` would not be the transcript its
# reader gets). Such a module is named neither ``__main__`` nor ``tests.sample_workflows.*``,
# so without this clause it would be swept by nothing and its ledger would fail *open*. It
# takes the unledgered leg as well: a written module keeping no ``TRIPPED`` is reported,
# exactly as a sample workflow is, so the fail-closed property holds without asking the page
# to cooperate.
_gebra_ledger = []
_gebra_unledgered = []
_gebra_here = _gebra_os.path.realpath(_gebra_os.getcwd()) + _gebra_os.sep


def _gebra_written_here(module):
    \"\"\"Whether this module's source file is one the example itself put in the child's cwd.\"\"\"
    _path = getattr(module, "__file__", None)
    if not _path:
        return False
    try:
        return _gebra_os.path.realpath(_path).startswith(_gebra_here)
    except OSError:
        return False


for _gebra_name, _gebra_module in sorted(_gebra_sys.modules.items()):
    if _gebra_module is None:
        continue
    _gebra_swept = (
        _gebra_name.startswith("tests.sample_workflows.")
        or _gebra_name == "__main__"
        or _gebra_written_here(_gebra_module)
    )
    if not _gebra_swept:
        continue
    _gebra_short = _gebra_name.rpartition(".")[2]
    _gebra_tripped = getattr(_gebra_module, "TRIPPED", None)
    if _gebra_tripped is None:
        if _gebra_name != "__main__":
            _gebra_unledgered.append(_gebra_short)
        continue
    for _gebra_label in _gebra_tripped:
        _gebra_ledger.append(_gebra_short + ":" + str(_gebra_label))
print("WA07-ATTEMPTS", _gebra_attempts, file=_gebra_sys.stderr)
print("WA07-LEDGER", _gebra_ledger, file=_gebra_sys.stderr)
print("WA07-UNLEDGERED", _gebra_unledgered, file=_gebra_sys.stderr)
print("WA07-IMPORT-SOCKETS", len(_gebra_built), file=_gebra_sys.stderr)
assert "langgraph.pregel.remote" not in _gebra_sys.modules, "a network client was imported"
"""


def child_program(example: DocExample, *, probe: str = "") -> str:
    """The exact source the child interpreter runs: guard, page code, probe, trailer."""
    return GUARD_PROLOGUE + example.code + probe + GUARD_EPILOGUE


def _last_reported(stderr: str, mark: str) -> str | None:
    """The trailer's own line for ``mark``, or ``None`` if the child never reached it.

    The *last* matching line, not any matching line: an example's own stderr is written
    before the trailer, so a page that printed ``WA07-LEDGER []`` itself cannot satisfy the
    check on the harness's behalf.
    """
    reported = [line for line in stderr.splitlines() if line.startswith(f"{mark} ")]
    return reported[-1] if reported else None


def _guard_problems(stdout: str, stderr: str, returncode: int) -> list[str]:
    """What the guard says about a finished child, independently of the expected output."""
    problems: list[str] = []
    if returncode != 0:
        problems.append(f"the example exited {returncode} (see the child stderr below)")
    if TRIP_MARK in stderr:
        problems.append("WA-07: a guarded operation was reached")
    for mark in (ATTEMPTS_MARK, LEDGER_MARK):
        reported = _last_reported(stderr, mark)
        if reported != f"{mark} []":
            problems.append(
                f"WA-07: {reported or f'{mark} (not reported — the child did not reach the trailer)'}"
            )
    unledgered = _last_reported(stderr, UNLEDGERED_MARK)
    if unledgered is not None and unledgered != f"{UNLEDGERED_MARK} []":
        problems.append(
            f"WA-07: {unledgered} — that sample workflow keeps no TRIPPED ledger, so a "
            "sentinel a try block swallowed would leave no trace. Give the module a ledger "
            "(or re-export the one its bodies record into) before an example imports it."
        )
    if _last_reported(stderr, IMPORT_SOCKETS_MARK) is None:
        problems.append("the child did not reach the harness trailer")
    return problems


def run_example(example: DocExample, *, root: Path = REPO_ROOT, probe: str = "") -> ExampleResult:
    """Execute one example in a guarded child and check it against its page.

    The child runs in a fresh temporary directory, so an example that writes a ``.gebra/``
    store writes it there and the repository is untouched, while ``PYTHONPATH`` keeps the
    sample workflows importable. It inherits :data:`INHERITED_ENV` and nothing else, so a
    provider key or a tracing switch left exported in a contributor's shell never reaches an
    example. ``PYTHONOPTIMIZE`` is pinned off because the guard's claims live in ``assert``
    statements.

    Args:
        example: What to run.
        root: The repository root, put on the child's ``PYTHONPATH``.
        probe: Extra source appended after the example — the control tests' way of firing a
            raiser inside the very run that made the claim. Empty for a real run.
    """
    environment = {name: os.environ[name] for name in INHERITED_ENV if name in os.environ}
    environment["PYTHONOPTIMIZE"] = "0"
    environment["PYTHONPATH"] = str(root)
    with tempfile.TemporaryDirectory(prefix="gebra-doc-example-") as workdir:
        finished = subprocess.run(
            [sys.executable, "-c", child_program(example, probe=probe)],
            cwd=workdir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    problems = _guard_problems(finished.stdout, finished.stderr, finished.returncode)
    if finished.stdout.rstrip("\n") != example.expected_output.rstrip("\n"):
        where = (
            f"line {example.output_line}"
            if example.output_line is not None
            else "no gebra:output block, so the example must print nothing"
        )
        problems.append(
            f"printed output does not match the page ({where}):\n"
            f"    expected: {example.expected_output.rstrip(chr(10))!r}\n"
            f"    actual:   {finished.stdout.rstrip(chr(10))!r}"
        )
    return ExampleResult(
        example=example,
        returncode=finished.returncode,
        stdout=finished.stdout,
        stderr=finished.stderr,
        problems=tuple(problems),
    )


# ── The command-line surface CI runs ─────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """``--list`` what is marked, or ``--report`` a counted run. Exit 1 on any failure."""
    parser = argparse.ArgumentParser(description=__doc__, add_help=True)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to scan")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list the marked examples and exit")
    mode.add_argument("--report", action="store_true", help="run every example, counted")
    arguments = parser.parse_args(argv)

    try:
        examples = discover(arguments.root)
    except DocExampleError as error:
        print(f"documentation example markup is malformed: {error}", file=sys.stderr)
        return 1

    if arguments.list:
        for example in examples:
            declared = "output pinned" if example.output_line else "prints nothing"
            print(f"{example.name} (line {example.line}, {declared})")
        print(f"{len(examples)} example(s) marked")
        return 0

    failures = []
    for example in examples:
        result = run_example(example, root=arguments.root)
        print(f"{'ok  ' if result.ok else 'FAIL'} {example.name}")
        if not result.ok:
            failures.append(result)

    print(f"\n{len(examples) - len(failures)}/{len(examples)} documentation example(s) green")
    for failure in failures:
        print(f"\n{failure.report()}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover — the CI entry point, exercised by tests/docs
    raise SystemExit(main())
