"""The gebra CI-gate driver — everything `.github/actions/gebra-gate` does (card TE-13).

The composite action maps each input onto a ``GEBRA_GATE_*`` environment variable and
runs this file with the adopter's interpreter; the whole gate then happens here, in one
script a test can execute without a GitHub runner: build exactly one ``pytest`` command
from the inputs, stream the run's output while capturing it, translate the exit code
under the declared mode, emit one workflow-command annotation, write the two step
outputs, and append the run's closing ``gebra`` section to the step summary.

Standard library only, deliberately: the driver runs before it is known whether the
environment even has a working ``pytest``, so it must not itself depend on anything the
environment might be missing — a broken environment is reported as a red pytest exit
with its meaning named, never as this script's own traceback.

The mode vocabulary is the rollout ladder ``docs/ci/github-action.md`` documents —
``report-only`` → ``gate`` → ``strict`` — and the exit-code translation is the whole
difference between the rungs: test failures (pytest exit 1) hold the step green only
under ``report-only``; a run that did not complete (interrupted, internal error, usage
error) or that collected nothing (exit 5) fails the step under every mode, because a
gate that silently checked nothing is exactly what a CI gate exists to prevent.

Property slugs are deliberately not validated here. The plugin owns that vocabulary,
and its own configure-time refusal surfaces as ``outcome: error`` (pytest usage
exit 4) — one authority, so this driver and the plugin can never disagree about which
properties exist.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The rollout ladder, in rollout order — the closed vocabulary of the ``mode`` input.
MODES: Final[tuple[str, ...]] = ("report-only", "gate", "strict")

#: The closed vocabulary of the ``outcome`` step output.
OUTCOMES: Final[tuple[str, ...]] = ("pass", "failures", "empty", "error", "refused")

#: pytest's documented exit codes, spelled out for a reader who meets one in red.
EXIT_MEANINGS: Final[dict[int, str]] = {
    0: "every collected test passed",
    1: "tests failed",
    2: "the run was interrupted",
    3: "internal pytest error",
    4: "pytest usage error",
    5: "no tests were collected",
}

#: Longest ``gebra`` section the step summary carries verbatim; anything past the cap
#: is counted in a trailing note, never silently dropped.
SECTION_LINE_CAP: Final[int] = 200

#: The step exit of a refused request — nothing ran, so no pytest code is echoed.
REFUSED_EXIT: Final[int] = 2

#: A pytest terminal separator line (``write_sep``): ``=``-ruled with a spaced title.
_SEPARATOR: Final = re.compile(r"^=+ (?P<title>.+?) =+$")

#: Every input travels as one environment variable under this prefix — the composite
#: step's ``env:`` block is the only bridge, so no input ever becomes shell text.
_ENV_PREFIX: Final = "GEBRA_GATE_"


class GateRefusal(RuntimeError):
    """A request refused before pytest runs — a misconfigured step, said loudly."""


@dataclass(frozen=True)
class GateRequest:
    """One parsed, validated gate request — what the step's inputs asked for."""

    mode: str
    tests: tuple[str, ...]
    pytest_args: tuple[str, ...]
    select: tuple[str, ...]
    skip: tuple[str, ...]
    strict_properties: tuple[str, ...]


def _slugs(value: str, name: str) -> tuple[str, ...]:
    """A comma-separated slug list, split and stripped; an empty member is refused.

    Only the syntax is checked here. Whether a slug names a catalog property is the
    plugin's question, answered in one place at configure time.
    """
    if not value.strip():
        return ()
    members = tuple(member.strip() for member in value.split(","))
    if any(not member for member in members):
        raise GateRefusal(f"`{name}` has an empty member: {value!r}")
    return members


def _tokens(value: str, name: str) -> tuple[str, ...]:
    """A shell-style token list; gebra flags are refused — policy travels as inputs.

    A ``--gebra-*`` flag smuggled in here would state gate policy in a second place,
    where it could contradict the ``mode``/``strict-properties``/``select``/``skip``
    inputs without either statement being wrong on its own.
    """
    tokens = tuple(shlex.split(value))
    for token in tokens:
        if token.startswith("--gebra-"):
            raise GateRefusal(
                f"`{name}` carries {token!r} — gebra policy is declared through the "
                "`mode`, `strict-properties`, `select` and `skip` inputs, in one place."
            )
    return tokens


def request_from_env(environ: Mapping[str, str]) -> GateRequest:
    """Parse the ``GEBRA_GATE_*`` inputs, refusing what cannot be meant.

    Raises:
        GateRefusal: on a mode outside the ladder, strict properties outside strict
            mode, a gebra flag inside ``tests``/``pytest-args``, or an empty slug
            member.
    """
    mode = environ.get(_ENV_PREFIX + "MODE", "").strip() or "gate"
    if mode not in MODES:
        raise GateRefusal(f"unknown mode {mode!r}; one of: {', '.join(MODES)}")
    strict_properties = _slugs(
        environ.get(_ENV_PREFIX + "STRICT_PROPERTIES", ""), "strict-properties"
    )
    if strict_properties and mode != "strict":
        raise GateRefusal(
            f"`strict-properties` only means something under `mode: strict`; mode is {mode!r}"
        )
    return GateRequest(
        mode=mode,
        tests=_tokens(environ.get(_ENV_PREFIX + "TESTS", ""), "tests"),
        pytest_args=_tokens(environ.get(_ENV_PREFIX + "PYTEST_ARGS", ""), "pytest-args"),
        select=_slugs(environ.get(_ENV_PREFIX + "SELECT", ""), "select"),
        skip=_slugs(environ.get(_ENV_PREFIX + "SKIP", ""), "skip"),
        strict_properties=strict_properties,
    )


def command(request: GateRequest) -> list[str]:
    """The one pytest invocation this gate runs, as an argv.

    ``-m pytest`` on this interpreter, so the environment that runs the driver is the
    environment that gets gated. Gebra flags come last: the bare ``--gebra-strict``
    takes an optional value, so a path placed after it would be read as a property
    slug (the plugin documents the argparse hazard) — at the end it has nothing left
    to swallow.
    """
    argv = [sys.executable, "-m", "pytest", *request.tests, *request.pytest_args]
    if request.select:
        argv.append("--gebra-select=" + ",".join(request.select))
    if request.skip:
        argv.append("--gebra-skip=" + ",".join(request.skip))
    if request.mode == "strict":
        if request.strict_properties:
            argv.append("--gebra-strict=" + ",".join(request.strict_properties))
        else:
            argv.append("--gebra-strict")
    return argv


def outcome_for(mode: str, exit_code: int) -> tuple[str, int]:
    """Translate pytest's exit code into ``(outcome, step exit)`` under the mode.

    ``report-only`` forgives exactly one thing: test failures. A run that was
    interrupted, died internally, was misused, or collected nothing is red on every
    rung — a gate that checked nothing must not report green.
    """
    if exit_code == 0:
        return "pass", 0
    if exit_code == 1:
        return "failures", 0 if mode == "report-only" else 1
    if exit_code == 5:
        return "empty", 1
    return "error", exit_code if exit_code > 0 else 1


def gebra_section(output_lines: list[str]) -> list[str] | None:
    """The closing ``gebra`` report of a captured pytest run, if one appeared.

    The plugin prints it under the terminal reporter's ``=``-ruled section header; the
    section ends at the next such header (pytest's own summary blocks) or at the end
    of the output — under ``-q`` the final stats line is undecorated, so end-of-output
    is a normal terminator, not an edge case.
    """
    start: int | None = None
    for index, line in enumerate(output_lines):
        matched = _SEPARATOR.match(line)
        if matched is None:
            continue
        if start is None:
            if matched.group("title") == "gebra":
                start = index
            continue
        return output_lines[start:index]
    if start is None:
        return None
    return output_lines[start:]


def annotation(mode: str, exit_code: int, outcome: str) -> str | None:
    """One single-line workflow-command annotation for the run — none on a pass.

    One per run, deliberately: per-finding annotations would mean re-parsing the human
    report into a second machine shape, and machine formats are the CLI's own surface
    (``gebra verify --format``, PD-015). The full report is in the step summary.
    """
    if outcome == "pass":
        return None
    if outcome == "failures":
        if mode == "report-only":
            return (
                "::warning title=gebra gate::pytest exited 1 (tests failed) — held "
                "green by report-only mode; see the gebra section in the step summary."
            )
        return (
            f"::error title=gebra gate::pytest exited 1 (tests failed) under "
            f"mode={mode} — see the gebra section in the step summary."
        )
    if outcome == "empty":
        return (
            "::error title=gebra gate::no tests were collected — the gate checked "
            "nothing, which never passes; point `tests` at your verification targets."
        )
    meaning = EXIT_MEANINGS.get(exit_code, "unrecognized pytest exit")
    return (
        f"::error title=gebra gate::pytest exited {exit_code} ({meaning}) — the run "
        "did not produce a verdict, which is red under every mode."
    )


def summary_lines(
    request: GateRequest,
    argv: list[str],
    exit_code: int,
    outcome: str,
    step_exit: int,
    output_lines: list[str],
) -> list[str]:
    """The step-summary block: what ran, how it exited, and the gebra section itself."""
    shown = list(argv)
    shown[0] = Path(shown[0]).name
    meaning = EXIT_MEANINGS.get(exit_code, "unrecognized pytest exit")
    verdict = "step green" if step_exit == 0 else "step red"
    lines = [
        "### gebra gate",
        "",
        f"- mode: `{request.mode}`",
        f"- command: `{shlex.join(shown)}`",
        f"- pytest exit: `{exit_code}` — {meaning}",
        f"- outcome: `{outcome}` ({verdict})",
        "",
    ]
    section = gebra_section(output_lines)
    if section is None:
        lines.append(
            "No closing `gebra` section appeared in this run's output — no "
            "gebra-marked target ran, or the run ended before its summary. The full "
            "output is in the job log."
        )
        return lines
    lines.append("```text")
    lines.extend(section[:SECTION_LINE_CAP])
    lines.append("```")
    if len(section) > SECTION_LINE_CAP:
        lines.append(
            f"Truncated: {len(section) - SECTION_LINE_CAP} more line(s) — the full "
            "section is in the job log."
        )
    return lines


def _append_lines(path: str, lines: list[str]) -> None:
    """Append to a runner-provided file (``GITHUB_OUTPUT``/``GITHUB_STEP_SUMMARY``)."""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(environ: Mapping[str, str] | None = None) -> int:
    """Run the gate: parse, run pytest once, translate, annotate, record.

    Args:
        environ: The environment to read inputs and runner file paths from;
            ``os.environ`` when omitted. The pytest child always inherits the real
            process environment — the runner's variables must reach the run's own
            hooks (the DoD suite's step-summary reporter reads one).
    """
    env: Mapping[str, str] = os.environ if environ is None else environ
    output_path = env.get("GITHUB_OUTPUT")
    try:
        request = request_from_env(env)
    except GateRefusal as refusal:
        print(f"::error title=gebra gate::{refusal}")
        if output_path:
            _append_lines(output_path, ["exit-code=", "outcome=refused"])
        return REFUSED_EXIT

    argv = command(request)
    print(f"gebra gate: mode={request.mode}", flush=True)
    print(f"gebra gate: running {shlex.join(argv)}", flush=True)
    captured: list[str] = []
    with subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as process:
        stdout = process.stdout
        if stdout is not None:
            for line in stdout:
                sys.stdout.write(line)
                captured.append(line.rstrip("\n"))
        sys.stdout.flush()
        exit_code = process.wait()

    outcome, step_exit = outcome_for(request.mode, exit_code)
    print(f"gebra gate: pytest exited {exit_code}; outcome={outcome}", flush=True)
    note = annotation(request.mode, exit_code, outcome)
    if note is not None:
        print(note, flush=True)
    if output_path:
        _append_lines(output_path, [f"exit-code={exit_code}", f"outcome={outcome}"])
    summary_path = env.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        _append_lines(
            summary_path,
            summary_lines(request, argv, exit_code, outcome, step_exit, captured),
        )
    return step_exit


if __name__ == "__main__":
    sys.exit(main())
