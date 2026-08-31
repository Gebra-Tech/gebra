"""The WA-05 golden-lifecycle guard: an unjustified golden diff fails CI (GOV-08).

Two halves, matching the tool's own split:

* the **judgement** — path classification, trailer extraction, the two WA-05 justification
  forms, and the per-commit verdicts — tested as pure functions on synthetic inputs;
* the **plumbing** — the range walk over git and the CLI — tested against a faked
  ``_git`` boundary, plus read-only pins on the ``golden-guard`` job in ``ci.yml``.

WA-07 discipline: nothing here spawns git or any other subprocess — the boundary is
replaced wholesale, and one armed test proves the judgement half runs with subprocess
disabled outright.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import golden_guard
from tools.golden_guard import (
    GOLDEN_PATHS,
    GoldenGuardError,
    check_range,
    evaluate_commit,
    golden_paths_touched,
    justification_trailers,
    main,
    well_formed,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(
    not CI_WORKFLOW.is_file(),
    reason="guard tests describe the source tree; no workflow beside tests/",
)

A_GOLDEN = "tests/version_drift/golden/nodes-spec.canonical.json"
DRIFT_TRAILER = "Golden-Justification: drift-run=33336160085 langgraph 1.2.10 + core 1.5.3"
DEC_TRAILER = "Golden-Justification: DEC-28 ir_version=1.1 dynamic-edge goldens retaken"


# ── The two WA-05 forms ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "drift-run=33336160085 langgraph 1.2.10 + langchain-core 1.5.3",
        "drift-run=123456 langgraph 1.3.0 + langchain-core 1.6.0",
        "DEC-28 ir_version=1.1",
        "DEC-9 ir_version=2 goldens retaken under the ratified change",
        "DEC-31 ir_version=1.2.1",
    ],
)
def test_a_well_formed_justification_is_accepted(value: str) -> None:
    assert well_formed(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "drift-run=",
        "drift-run=abc",
        "drift-run=12345 pair",  # too short to be an Actions run ID
        "drift-run=33336160085",  # §5: the citation is run ID *plus substrate pair*
        "drift run 33336160085 pair",  # not the key=value spelling
        "dec-28 ir_version=1.1",  # the decision record is spelled DEC-
        "DEC-28",  # WA-05 arm 2 requires the ir_version bump alongside the DEC
        "DEC-28 ir_version=",
        "DEC-28 ir_version=one.one",
        "ir_version=1.1 DEC-28",  # order is part of the form
        "see the PR description",
    ],
)
def test_a_malformed_justification_is_refused(value: str) -> None:
    assert not well_formed(value)


# ── Trailer extraction ───────────────────────────────────────────────────────────────────


def test_trailers_are_read_from_column_zero_only() -> None:
    """An indented quotation (a revert body citing the old commit) is not a trailer."""
    message = (
        "revert: undo the golden change [XX-99]\n"
        "\n"
        "    Golden-Justification: drift-run=33336160085\n"
    )
    assert justification_trailers(message) == []


def test_the_trailer_key_is_case_sensitive() -> None:
    assert justification_trailers("golden-justification: drift-run=33336160085\n") == []


def test_every_trailer_line_is_collected() -> None:
    message = f"feat(x): y [XX-01]\n\n{DRIFT_TRAILER}\n{DEC_TRAILER}\n"
    assert justification_trailers(message) == [
        "drift-run=33336160085 langgraph 1.2.10 + core 1.5.3",
        "DEC-28 ir_version=1.1 dynamic-edge goldens retaken",
    ]


# ── Path classification ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tree", sorted(GOLDEN_PATHS))
def test_each_guarded_tree_exists_and_is_populated(tree: str) -> None:
    """A renamed golden directory must fail here rather than silently unguard itself."""
    directory = REPO_ROOT / tree
    assert directory.is_dir(), f"{tree} is guarded but does not exist"
    assert any(directory.iterdir()), f"{tree} is guarded but empty"


def test_files_under_each_guarded_tree_are_classified_golden() -> None:
    files = [f"{tree}some-file.json" for tree in GOLDEN_PATHS]
    assert golden_paths_touched(files) == files


@pytest.mark.parametrize(
    "path",
    [
        "tests/cli/goldens/pass.txt",  # rendering golden — ordinary review, not WA-05
        "tests/report/goldens/human/fail.txt",
        "tests/lineage/golden/lineage-evolved.json",
        "tests/version_drift/test_version_drift.py",
        "tests/ir/golden-adjacent/file.json",  # prefix abuse: not the guarded tree
        "docs/governance/VERSION-COMPAT-RUNBOOK.md",
        "src/gebra/ir/models.py",
    ],
)
def test_paths_outside_the_wa05_classes_are_not_golden(path: str) -> None:
    assert golden_paths_touched([path]) == []


@pytest.mark.parametrize(
    "path",
    [
        "tests/version_drift/golden/README.md",
        "tests/extraction/golden/conformance/README.md",
        "tests/ir/golden/NOTES.md",
    ],
)
def test_documentation_under_a_golden_tree_is_prose_not_golden(path: str) -> None:
    """WA-05 enumerates golden *files*; a README under the tree changes under ordinary
    review, and no ``.md`` can become a golden (the suites pin the filenames exactly).
    Both GOV-08 pre-reviews caught the alternative: a guard that classified prose would
    demand a trailer no WA-05 arm truthfully supports."""
    assert golden_paths_touched([path, A_GOLDEN]) == [A_GOLDEN]


# ── Per-commit verdicts ──────────────────────────────────────────────────────────────────


def test_a_commit_touching_no_golden_needs_no_trailer() -> None:
    assert evaluate_commit(["src/gebra/cli.py", "CHANGELOG.md"], "chore: x [XX-01]") is None


def test_an_unjustified_golden_diff_is_a_violation_naming_both_forms() -> None:
    verdict = evaluate_commit([A_GOLDEN], "feat(x): update goldens [XX-01]")
    assert verdict is not None
    assert A_GOLDEN in verdict
    assert "drift-run=<run id>" in verdict
    assert "DEC-<n> ir_version=<x.y>" in verdict


def test_a_malformed_trailer_is_a_violation_showing_what_was_found() -> None:
    verdict = evaluate_commit(
        [A_GOLDEN], "feat(x): y [XX-01]\n\nGolden-Justification: because tests\n"
    )
    assert verdict is not None
    assert "'because tests'" in verdict


@pytest.mark.parametrize("trailer", [DRIFT_TRAILER, DEC_TRAILER])
def test_a_justified_golden_diff_passes(trailer: str) -> None:
    assert evaluate_commit([A_GOLDEN], f"feat(x): y [XX-01]\n\n{trailer}\n") is None


def test_one_valid_trailer_among_malformed_ones_is_enough() -> None:
    message = f"feat(x): y [XX-01]\n\nGolden-Justification: wip\n{DEC_TRAILER}\n"
    assert evaluate_commit([A_GOLDEN], message) is None


def test_the_judgement_runs_with_subprocess_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pure half spawns nothing — armed, not assumed (WA-07 posture)."""

    def refuse(*arguments: Any, **keywords: Any) -> Any:
        raise AssertionError("the judgement half must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", refuse)
    assert evaluate_commit([A_GOLDEN], f"x\n\n{DRIFT_TRAILER}\n") is None
    assert evaluate_commit([A_GOLDEN], "x") is not None


# ── The range walk, over a faked git boundary ────────────────────────────────────────────


class FakeGit:
    """A behavioural stand-in for the tool's ``_git``: fixed commits, no subprocess."""

    def __init__(self, commits: list[tuple[str, list[str], str]]) -> None:
        #: (sha, changed files, message), oldest first.
        self.commits = commits

    def __call__(self, *arguments: str) -> str:
        joined = " ".join(arguments)
        if arguments[0] == "rev-list" and "--reverse" in arguments:
            return "".join(f"{sha}\n" for sha, _, _ in self.commits)
        if arguments[0] == "rev-list" and "-n" in arguments:
            return f"{self.commits[-1][0]}\n"
        if arguments[0] == "diff-tree":
            # The flags are load-bearing, so the fake refuses their absence: `-c` is what
            # holds a merge commit to its *combined* diff (an evil merge cannot smuggle a
            # golden change), and `--root` is what keeps an initial commit judged.
            for flag in ("-r", "--name-only", "-c", "--root"):
                assert flag in arguments, f"diff-tree lost its {flag} flag: {joined}"
            sha = arguments[-1]
            for known, files, _ in self.commits:
                if known == sha:
                    return "".join(f"{file}\n" for file in files)
            raise GoldenGuardError(f"unknown revision {sha}")
        if arguments[0] == "log":
            sha = arguments[-1]
            for known, _, message in self.commits:
                if known == sha:
                    return message
            raise GoldenGuardError(f"unknown revision {sha}")
        raise GoldenGuardError(f"unexpected git invocation: {joined}")


def test_every_commit_in_the_range_is_judged_on_its_own(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A justified commit in the same push never covers an unjustified one (WA-05 binds
    per commit)."""
    fake = FakeGit(
        [
            ("a" * 40, [A_GOLDEN], "feat(x): quiet golden edit [XX-01]"),
            ("b" * 40, [A_GOLDEN], f"feat(x): justified [XX-02]\n\n{DRIFT_TRAILER}\n"),
        ]
    )
    monkeypatch.setattr(golden_guard, "_git", fake)
    assert check_range("0" * 39 + "1", "b" * 40) == 1
    output = capsys.readouterr().out
    assert ("a" * 12) in output and "FAIL" in output
    assert f"OK    {'b' * 12}" in output


def test_a_clean_range_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGit(
        [
            ("a" * 40, ["src/gebra/cli.py"], "feat(cli): x [XX-01]"),
            ("b" * 40, ["CHANGELOG.md"], "docs: y [XX-02]"),
        ]
    )
    monkeypatch.setattr(golden_guard, "_git", fake)
    assert check_range("1" * 40, "b" * 40) == 0


def test_a_null_base_judges_the_head_commit_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The push that creates a ref has no `before`; the guard narrows loudly, not silently."""
    fake = FakeGit([("c" * 40, [A_GOLDEN], "feat(x): quiet [XX-03]")])
    monkeypatch.setattr(golden_guard, "_git", fake)
    assert check_range("0" * 40, "c" * 40) == 1
    assert "judging the head commit only" in capsys.readouterr().out


def test_an_unwalkable_range_falls_back_to_the_head_commit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A force-push can discard the event's base; the guard narrows loudly, not silently."""
    inner = FakeGit([("d" * 40, [A_GOLDEN], f"feat(x): ok [XX-04]\n\n{DEC_TRAILER}\n")])

    def failing_range(*arguments: str) -> str:
        if arguments[0] == "rev-list" and "--reverse" in arguments:
            raise GoldenGuardError("bad revision")
        return inner(*arguments)

    monkeypatch.setattr(golden_guard, "_git", failing_range)
    assert check_range("e" * 40, "d" * 40) == 0
    assert "judging head only" in capsys.readouterr().out


# ── The CLI ──────────────────────────────────────────────────────────────────────────────


def test_direct_mode_judges_the_given_files_and_message() -> None:
    assert main(["--files", A_GOLDEN, "--message", f"x\n\n{DRIFT_TRAILER}"]) == 0
    assert main(["--files", A_GOLDEN, "--message", "x"]) == 1
    assert main(["--files", "--message", "x"]) == 0  # empty file list: nothing touched


def test_the_two_modes_are_exclusive_and_required() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    with pytest.raises(SystemExit) as excinfo:
        main(["--base", "a" * 40, "--files", A_GOLDEN, "--message", "x"])
    assert excinfo.value.code == 2
    with pytest.raises(SystemExit) as excinfo:
        main(["--base", "a" * 40])  # --head missing
    assert excinfo.value.code == 2


def test_range_mode_reports_the_faked_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGit([("f" * 40, [A_GOLDEN], "feat(x): quiet [XX-05]")])
    monkeypatch.setattr(golden_guard, "_git", fake)
    assert main(["--base", "1" * 40, "--head", "f" * 40]) == 1


def test_an_unevaluable_range_is_exit_two_never_a_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*arguments: str) -> str:
        raise GoldenGuardError("git unavailable")

    monkeypatch.setattr(golden_guard, "_git", broken)
    assert main(["--base", "1" * 40, "--head", "2" * 40]) == 2


def test_the_help_carries_no_bypass_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Same posture as the provenance guard: there is no --skip/--force/--allow/--ignore."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    text = capsys.readouterr().out
    assert not any(flag in text for flag in ("--skip", "--force", "--allow", "--ignore"))


# ── The ci.yml wiring (read-only pins) ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


def test_the_guard_job_runs_the_tool_and_blocks(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["golden-guard"]
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "tools/golden_guard.py" in runs
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])


def test_the_guard_checkout_fetches_history(workflow: dict[str, Any]) -> None:
    """A depth-1 checkout has no parents to diff; the range walk needs history."""
    [checkout] = [
        step
        for step in workflow["jobs"]["golden-guard"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout")
    ]
    assert checkout["with"]["fetch-depth"] == 0


def test_the_guard_runs_only_on_events_that_bring_a_diff(workflow: dict[str, Any]) -> None:
    condition = workflow["jobs"]["golden-guard"]["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.event_name == 'pull_request'" in condition


def test_the_guard_reads_the_event_range(workflow: dict[str, Any]) -> None:
    [guard_step] = [step for step in workflow["jobs"]["golden-guard"]["steps"] if "run" in step]
    env = guard_step["env"]
    assert "github.event.pull_request.base.sha" in env["GUARD_BASE"]
    assert "github.event.before" in env["GUARD_BASE"]
    assert "github.event.pull_request.head.sha" in env["GUARD_HEAD"]
    assert "github.event.after" in env["GUARD_HEAD"]
    assert '--base "$GUARD_BASE" --head "$GUARD_HEAD"' in guard_step["run"]
