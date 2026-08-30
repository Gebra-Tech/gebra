"""The gate driver's behavior — construction, translation, refusals, real children.

Behavioral claims are made at two levels on purpose. Unit level, on the driver's pure
functions, because the command built and the ``(outcome, step exit)`` translation are
the action's whole contract and every cell of that matrix should be readable in one
table. End-to-end, through real child pytest sessions in tmp directories — the same
run shape the composite step performs — because "report-only holds a failing run
green" and "an empty collection is red everywhere" are claims about what a run *does*,
and because the ``gebra`` section the summary extractor parses must be the one the
plugin actually prints, not a hand-written imitation.

WA-07: every child but one collects plain assert-style files that mark nothing and
build nothing. The one child that exercises the plugin gate proper marks the shared
sentinel-guarded travel-booking agent (TE-05's fixture — the same target the DoD suite
marks): its node bodies record and raise ``BaseException``-grade sentinels, so a child
in which anything was invoked exits non-zero and that test goes red here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from tests.action.conftest import GATE_SCRIPT, REPO_ROOT

#: What the `dod` job's inputs ask for — the executed reference consumer's request.
DOD_ENV: Final[dict[str, str]] = {
    "GEBRA_GATE_TESTS": "tests/dod tests/evolution",
    "GEBRA_GATE_PYTEST_ARGS": "-q",
}

PASSING: Final = "def test_ok() -> None:\n    assert True\n"
FAILING: Final = "def test_no() -> None:\n    assert False\n"

#: The house preamble for a child that imports the shared sentinel-guarded agent.
AGENT_CHILD: Final = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
import pytest

from tests.sample_workflows.travel_booking import build_travel_booking_agent


@pytest.mark.gebra(name="travel_agent")
def test_gebra():
    return build_travel_booking_agent()
"""


# ── Command construction ─────────────────────────────────────────────────────────────


def _command(gate: ModuleType, env: dict[str, str]) -> list[str]:
    argv: list[str] = gate.command(gate.request_from_env(env))
    assert argv[:3] == [sys.executable, "-m", "pytest"]
    return argv[3:]


def test_the_default_request_is_a_bare_pytest_run(gate: ModuleType) -> None:
    """No inputs → this interpreter's `-m pytest` with no arguments at all."""
    assert _command(gate, {}) == []


def test_the_dod_jobs_request_builds_the_dod_command(gate: ModuleType) -> None:
    """The reference consumer's exact command — the invocation the workflow ran before
    TE-13, byte for byte after the interpreter."""
    assert _command(gate, dict(DOD_ENV)) == ["tests/dod", "tests/evolution", "-q"]


def test_report_only_and_gate_build_the_same_command(gate: ModuleType) -> None:
    """The first two rungs differ only in exit translation, never in what runs."""
    base = dict(DOD_ENV)
    commands = {
        mode: _command(gate, {**base, "GEBRA_GATE_MODE": mode}) for mode in ("report-only", "gate")
    }
    assert commands["report-only"] == commands["gate"]


def test_select_and_skip_map_to_their_flags(gate: ModuleType) -> None:
    """Comma lists pass through whole — one flag each, values joined as typed."""
    env = {
        "GEBRA_GATE_TESTS": "tests/agents",
        "GEBRA_GATE_SELECT": "effect-safety, dataflow-completeness",
        "GEBRA_GATE_SKIP": "determinism-replay",
    }
    assert _command(gate, env) == [
        "tests/agents",
        "--gebra-select=effect-safety,dataflow-completeness",
        "--gebra-skip=determinism-replay",
    ]


def test_bare_strict_is_the_final_token(gate: ModuleType) -> None:
    """The optional-value flag comes last, where argparse has nothing to swallow —
    a path after bare `--gebra-strict` would be read as a property slug."""
    env = {
        "GEBRA_GATE_MODE": "strict",
        "GEBRA_GATE_TESTS": "tests/agents",
        "GEBRA_GATE_PYTEST_ARGS": "-q",
        "GEBRA_GATE_SELECT": "termination-witness",
    }
    argv = _command(gate, env)
    assert argv[-1] == "--gebra-strict"
    assert argv == [
        "tests/agents",
        "-q",
        "--gebra-select=termination-witness",
        "--gebra-strict",
    ]


def test_per_property_strict_uses_the_equals_form(gate: ModuleType) -> None:
    env = {
        "GEBRA_GATE_MODE": "strict",
        "GEBRA_GATE_STRICT_PROPERTIES": "determinism-replay",
    }
    assert _command(gate, env) == ["--gebra-strict=determinism-replay"]


# ── Refusals ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"GEBRA_GATE_MODE": "audit"}, "unknown mode"),
        (
            {"GEBRA_GATE_STRICT_PROPERTIES": "determinism-replay"},
            "only means something under `mode: strict`",
        ),
        (
            {
                "GEBRA_GATE_MODE": "report-only",
                "GEBRA_GATE_STRICT_PROPERTIES": "determinism-replay",
            },
            "only means something under `mode: strict`",
        ),
        ({"GEBRA_GATE_PYTEST_ARGS": "-q --gebra-strict"}, "`pytest-args` carries"),
        ({"GEBRA_GATE_TESTS": "--gebra-select=effect-safety"}, "`tests` carries"),
        ({"GEBRA_GATE_SELECT": "effect-safety,,termination-witness"}, "empty member"),
    ],
    ids=[
        "mode",
        "strict-under-gate",
        "strict-under-report-only",
        "args-flag",
        "tests-flag",
        "empty-member",
    ],
)
def test_a_request_that_cannot_be_meant_is_refused(
    gate: ModuleType, env: dict[str, str], fragment: str
) -> None:
    """Each refusal names its input and its reason — before any pytest runs."""
    with pytest.raises(gate.GateRefusal) as caught:
        gate.request_from_env(env)
    assert fragment in str(caught.value)


def test_an_absent_or_blank_mode_is_the_default_gate(gate: ModuleType) -> None:
    """`gate` is the declared default, so a blank value and an absent one both land
    there — the same rung either way, never a fourth behavior."""
    assert gate.request_from_env({}).mode == "gate"
    assert gate.request_from_env({"GEBRA_GATE_MODE": " "}).mode == "gate"


# ── Exit translation ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mode", "exit_code", "outcome", "step_exit"),
    [
        ("report-only", 0, "pass", 0),
        ("gate", 0, "pass", 0),
        ("strict", 0, "pass", 0),
        ("report-only", 1, "failures", 0),
        ("gate", 1, "failures", 1),
        ("strict", 1, "failures", 1),
        ("report-only", 5, "empty", 1),
        ("gate", 5, "empty", 1),
        ("strict", 5, "empty", 1),
        ("report-only", 2, "error", 2),
        ("report-only", 3, "error", 3),
        ("report-only", 4, "error", 4),
        ("gate", 2, "error", 2),
        ("gate", 3, "error", 3),
        ("gate", 4, "error", 4),
        ("gate", 7, "error", 7),
        ("gate", -11, "error", 1),
    ],
)
def test_the_exit_translation_matrix(
    gate: ModuleType, mode: str, exit_code: int, outcome: str, step_exit: int
) -> None:
    """The whole contract in one table. Report-only forgives exit 1 and nothing else;
    5 (a gate over nothing) and every non-completion code are red on every rung; a
    signal death (negative returncode) is red with a positive step exit."""
    assert gate.outcome_for(mode, exit_code) == (outcome, step_exit)
    assert outcome in gate.OUTCOMES


def test_every_annotation_is_a_single_line(gate: ModuleType) -> None:
    """Workflow commands are line-oriented: one `::`-command per outcome, no newline."""
    for mode in gate.MODES:
        for exit_code in (0, 1, 2, 3, 4, 5, 7):
            outcome, _ = gate.outcome_for(mode, exit_code)
            note = gate.annotation(mode, exit_code, outcome)
            if exit_code == 0:
                assert note is None
                continue
            assert note is not None and "\n" not in note
            expected_kind = "::warning" if (mode, exit_code) == ("report-only", 1) else "::error"
            assert note.startswith(f"{expected_kind} title=gebra gate::")


# ── Section extraction ───────────────────────────────────────────────────────────────


def _transcript(*blocks: list[str]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        lines.extend(block)
    return lines


def test_the_gebra_section_is_extracted_between_separators(gate: ModuleType) -> None:
    body = ["travel_agent", "  P-01 graph-well-formed: pass"]
    lines = _transcript(
        ["collected 5 items", ""],
        ["=========== gebra ==========="],
        body,
        ["=========== 5 passed in 0.10s ==========="],
    )
    assert gate.gebra_section(lines) == ["=========== gebra ==========="] + body


def test_a_run_without_a_section_yields_none(gate: ModuleType) -> None:
    lines = _transcript(["collected 1 item", "", "=========== 1 passed in 0.01s ==========="])
    assert gate.gebra_section(lines) is None


def test_a_section_at_the_end_of_output_runs_to_the_end(gate: ModuleType) -> None:
    """Under `-q` the final stats line is undecorated, so end-of-output terminates."""
    body = ["travel_agent", "  P-02 termination-witness: pass", "5 passed in 0.10s"]
    lines = _transcript(["=========== gebra ==========="], body)
    assert gate.gebra_section(lines) == ["=========== gebra ==========="] + body


def test_an_earlier_foreign_section_is_not_the_start(gate: ModuleType) -> None:
    """Only the section titled exactly `gebra` starts the extraction."""
    lines = _transcript(
        ["====== warnings summary ======", "something"],
        ["====== gebra ======", "the section"],
        ["====== short test summary info ======", "tail"],
    )
    assert gate.gebra_section(lines) == ["====== gebra ======", "the section"]


def test_the_summary_truncates_loudly(gate: ModuleType) -> None:
    """Past the cap the summary counts what it dropped — never a silent cut."""
    cap: int = gate.SECTION_LINE_CAP
    section = ["====== gebra ======"] + [f"line {index}" for index in range(cap + 49)]
    request = gate.request_from_env({})
    lines = gate.summary_lines(request, [sys.executable, "-m", "pytest"], 0, "pass", 0, section)
    assert "Truncated: 50 more line(s)" in "\n".join(lines)
    opener = lines.index("```text")
    closer = len(lines) - 1 - lines[::-1].index("```")
    assert closer - opener - 1 == cap


def test_a_sectionless_summary_says_so(gate: ModuleType) -> None:
    request = gate.request_from_env({})
    lines = gate.summary_lines(
        request, [sys.executable, "-m", "pytest", "-q"], 0, "pass", 0, ["1 passed"]
    )
    text = "\n".join(lines)
    assert "No closing `gebra` section appeared" in text
    assert "```text" not in text


# ── End to end: real children, the composite step's own run shape ────────────────────


def _run_main(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
) -> tuple[int, dict[str, str], Path]:
    """Run `main()` in `tmp_path` with runner files provided, as the step would."""
    monkeypatch.chdir(tmp_path)
    output_file = tmp_path / "github-output"
    summary_file = tmp_path / "github-step-summary"
    code: int = gate.main(
        {
            **env,
            "GITHUB_OUTPUT": str(output_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
        }
    )
    outputs: dict[str, str] = {}
    if output_file.is_file():
        for line in output_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            outputs[key] = value
    return code, outputs, summary_file


def test_a_passing_run_is_green_end_to_end(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "test_ok.py").write_text(PASSING, encoding="utf-8")
    code, outputs, summary = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {"GEBRA_GATE_TESTS": "test_ok.py", "GEBRA_GATE_PYTEST_ARGS": "-q"},
    )
    assert code == 0
    assert outputs == {"exit-code": "0", "outcome": "pass"}
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("### gebra gate")
    assert "No closing `gebra` section appeared" in text
    captured = capsys.readouterr().out
    assert "::error" not in captured and "::warning" not in captured


def test_failures_fail_the_gate_mode(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "test_no.py").write_text(FAILING, encoding="utf-8")
    code, outputs, _ = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {"GEBRA_GATE_TESTS": "test_no.py", "GEBRA_GATE_PYTEST_ARGS": "-q"},
    )
    assert code == 1
    assert outputs == {"exit-code": "1", "outcome": "failures"}
    assert "::error title=gebra gate::pytest exited 1" in capsys.readouterr().out


def test_report_only_holds_failures_green(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The first rung: same red run, warning annotation, green step — and the raw
    exit still on the outputs for anything downstream that wants it."""
    (tmp_path / "test_no.py").write_text(FAILING, encoding="utf-8")
    code, outputs, _ = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {
            "GEBRA_GATE_TESTS": "test_no.py",
            "GEBRA_GATE_MODE": "report-only",
            "GEBRA_GATE_PYTEST_ARGS": "-q",
        },
    )
    assert code == 0
    assert outputs == {"exit-code": "1", "outcome": "failures"}
    captured = capsys.readouterr().out
    assert "::warning title=gebra gate::pytest exited 1" in captured
    assert "::error" not in captured


@pytest.mark.parametrize("mode", ["report-only", "gate"])
def test_an_empty_collection_is_red_under_every_mode(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    """Exit 5 — a gate that checked nothing — is red even on the forgiving rung."""
    code, outputs, _ = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {"GEBRA_GATE_MODE": mode, "GEBRA_GATE_PYTEST_ARGS": "-q"},
    )
    assert code == 1
    assert outputs == {"exit-code": "5", "outcome": "empty"}
    assert "the gate checked nothing" in capsys.readouterr().out


def test_a_plugin_vocabulary_refusal_surfaces_as_error(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The slug vocabulary stays the plugin's: an unknown strict slug is the plugin's
    own configure-time usage refusal (pytest exit 4), surfaced as outcome `error` —
    the driver validated nothing and contradicted nothing."""
    (tmp_path / "test_ok.py").write_text(PASSING, encoding="utf-8")
    code, outputs, _ = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {
            "GEBRA_GATE_TESTS": "test_ok.py",
            "GEBRA_GATE_MODE": "strict",
            "GEBRA_GATE_STRICT_PROPERTIES": "not-a-property",
            "GEBRA_GATE_PYTEST_ARGS": "-q",
        },
    )
    assert code == 4
    assert outputs == {"exit-code": "4", "outcome": "error"}
    assert "pytest exited 4" in capsys.readouterr().out


def test_a_driver_refusal_reports_before_pytest(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Refused requests write the outputs, annotate, and run nothing — no summary
    block exists because no run happened."""
    code, outputs, summary = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {"GEBRA_GATE_MODE": "gate", "GEBRA_GATE_STRICT_PROPERTIES": "determinism-replay"},
    )
    assert code == gate.REFUSED_EXIT
    assert outputs == {"exit-code": "", "outcome": "refused"}
    assert not summary.is_file()
    assert "::error title=gebra gate::" in capsys.readouterr().out


def test_the_plugin_gate_runs_through_the_driver_on_the_live_agent(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consumer-shaped end-to-end: a child session marks the sentinel-guarded
    travel-booking agent, the plugin generates the wedge-five items over it, and the
    driver's summary carries the plugin's real closing section — the same extraction
    the unit tests exercise on canned text, proven against the genuine format.

    WA-07: the agent's node bodies record and raise `BaseException`-grade sentinels
    (TE-05's arming, guarded in depth by `tests/testing/test_travel_booking.py`), so a
    child in which anything was invoked exits non-zero and this test goes red.
    """
    (tmp_path / "test_agent.py").write_text(AGENT_CHILD, encoding="utf-8")
    code, outputs, summary = _run_main(
        gate,
        tmp_path,
        monkeypatch,
        {"GEBRA_GATE_TESTS": "test_agent.py", "GEBRA_GATE_PYTEST_ARGS": "-q"},
    )
    assert code == 0
    assert outputs == {"exit-code": "0", "outcome": "pass"}
    text = summary.read_text(encoding="utf-8")
    assert "```text" in text
    assert "travel_agent" in text
    assert "termination-witness" in text


def test_the_driver_runs_as_a_script(tmp_path: Path) -> None:
    """The step's literal invocation — an interpreter on the file path — works."""
    (tmp_path / "test_ok.py").write_text(PASSING, encoding="utf-8")
    env = {
        **os.environ,
        "GEBRA_GATE_TESTS": "test_ok.py",
        "GEBRA_GATE_PYTEST_ARGS": "-q",
    }
    # Never inherit the runner's own files: inside a real Actions step this suite runs
    # in, the driver would otherwise append a phantom gate block to that step's real
    # output and summary (WA-07 pre-review finding 1).
    env.pop("GITHUB_OUTPUT", None)
    env.pop("GITHUB_STEP_SUMMARY", None)
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "gebra gate: pytest exited 0; outcome=pass" in completed.stdout
