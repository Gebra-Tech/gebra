"""The §3.2/§3.4 matrix at the process boundary — card CLI-07.

CLI-SPEC §7's CLI-07 row asks for "the exit codes of §3.2 on constructed cases for all five
verbs (including at least one ``2`` per stage the verb can reach), the format flags of §4,
the ``--strict`` forms of §3.3, and both styled and plain renderings of one subject
(§5.1)". The unit suites already hold each cell in process; this module re-observes the
matrix **as child processes** — real ``argv``, real streams, real exit codes through the
shipped entry points — which is the claim the brief's "subprocess tests" row names and the
one an in-process runner cannot make.

One §2.6 stage is deliberately exercised in process instead: ``dispatch`` requires a wedge
validator missing from the registry, which only a registry patch can construct — there is
no invocation that deregisters a validator, and shipping one would be a flag CLI-SPEC does
not define. That is the "runner invocation" half of this card's subprocess-vs-runner
decision, and it is the only registry-dependent case in the module.

Subjects are the conftest's corpus fixtures (the all-pass, two-finding-failure and
pass-with-notes documents), written into a module-scoped directory the children run in;
mutating cases (stores) get per-test directories. Every captured stream is swept for banned
phrases by the runner itself (WA-06; acceptance box 3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import gebra
import gebra.ir as gir
from gebra.ir import write_ir
from gebra.store import META_FILENAME, SNAPSHOTS_DIRNAME, STORE_DIRNAME, SnapshotStore
from tests.cli.conftest import (
    FAILING_FIXTURE,
    NOTED_FIXTURE,
    PASSING_FIXTURE,
    RunCli,
    fixture_ir,
)
from tests.cli.integration import console_script, run_gebra
from tools.mermaid_check import mermaid_problems

_ESCAPES = re.compile("\x1b\\[[0-9;]*m")


def _write_documents(directory: Path) -> None:
    """The three corpus subjects plus the two §2.6 refusal shapes, as loose files."""
    write_ir(fixture_ir(PASSING_FIXTURE), directory / "pass.ir.yaml")
    write_ir(fixture_ir(FAILING_FIXTURE), directory / "fail.ir.yaml")
    write_ir(fixture_ir(NOTED_FIXTURE), directory / "noted.ir.yaml")
    (directory / "not-ir.yaml").write_text("just: [a, list]\n", encoding="utf-8")
    dynamic = gir.load_json(
        gir.WorkflowIR,
        json.dumps(
            {
                "ir_version": "1.1",
                "entry": "a",
                "finish": ["a"],
                "nodes": [{"id": "a"}],
                "edges": [{"kind": "dynamic", "from": "a"}],
            }
        ),
    )
    write_ir(dynamic, directory / "dynamic.ir.yaml")


@pytest.fixture(scope="module")
def documents(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A read-only module directory — every test here passes it as the child's cwd."""
    directory = tmp_path_factory.mktemp("cli-matrix")
    _write_documents(directory)
    return directory


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A fresh per-test directory for the cases that write or corrupt a store."""
    _write_documents(tmp_path)
    return tmp_path


# ── verify: §3.2 row, §2.6 stages, §3.3 strict forms, §3.5 format invariance ──────────────


def test_verify_returns_each_gate_code(documents: Path) -> None:
    passing = run_gebra("verify", "pass.ir.yaml", cwd=documents)
    assert passing.exit_code == 0
    assert passing.stderr == ""
    failing = run_gebra("verify", "fail.ir.yaml", cwd=documents)
    assert failing.exit_code == 1


def test_verify_tool_error_stages_at_the_process_level(documents: Path) -> None:
    """One exit-2 per §2.6 stage the verb reaches without a registry patch, stage named."""
    missing = run_gebra("verify", "missing.ir.yaml", cwd=documents)
    assert missing.exit_code == 2
    assert "stage: input" in missing.stderr

    invalid = run_gebra("verify", "not-ir.yaml", cwd=documents)
    assert invalid.exit_code == 2
    assert "stage: ir-validation" in invalid.stderr

    refused = run_gebra("verify", "tests.cli.targets:build_empty_graph", "--call", cwd=documents)
    assert refused.exit_code == 2
    assert "stage: extraction" in refused.stderr


def test_a_missing_wedge_validator_is_a_dispatch_tool_error(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2.6's ``dispatch`` row for the two verbs that dispatch — in process, because only a
    registry patch can construct it (the module docstring's one runner-invocation case)."""
    _write_documents(tmp_path)
    monkeypatch.setattr("gebra.verify.run.is_implemented", lambda slug: False)

    verify_run = run_cli("verify", str(tmp_path / "pass.ir.yaml"))
    assert verify_run.exit_code == 2
    assert "stage: dispatch" in verify_run.stderr

    snapshot_run = run_cli(
        "snapshot", "--ir", str(tmp_path / "pass.ir.yaml"), "--store", str(tmp_path / ".gebra")
    )
    assert snapshot_run.exit_code == 2
    assert SnapshotStore.for_project(tmp_path).versions() == ()


def test_the_three_formats_agree_on_the_exit_code(documents: Path) -> None:
    """§3.5: choosing a surface never changes the answer — both verdicts, all three
    surfaces, as processes; the machine artifacts parse as what they claim to be."""
    for document, expected in (("pass.ir.yaml", 0), ("fail.ir.yaml", 1)):
        codes = set()
        for report_format in ("human", "json", "sarif"):
            result = run_gebra("verify", document, "--format", report_format, cwd=documents)
            codes.add(result.exit_code)
            if report_format == "json":
                assert json.loads(result.stdout)["gate"]["exit_code"] == expected
            if report_format == "sarif":
                assert json.loads(result.stdout)["runs"], document
        assert codes == {expected}, document


def test_the_strict_forms_move_the_gate_as_specified(documents: Path) -> None:
    """§3.3 as processes: bare, per-property (owning and non-owning), the alias, and the
    both-spellings usage error."""
    assert run_gebra("verify", "noted.ir.yaml", cwd=documents).exit_code == 0
    assert run_gebra("verify", "--strict", "noted.ir.yaml", cwd=documents).exit_code == 1
    owning = run_gebra("verify", "--strict=determinism-replay", "noted.ir.yaml", cwd=documents)
    assert owning.exit_code == 1
    unrelated = run_gebra("verify", "--strict=graph-well-formed", "noted.ir.yaml", cwd=documents)
    assert unrelated.exit_code == 0
    assert run_gebra("verify", "--gebra-strict", "noted.ir.yaml", cwd=documents).exit_code == 1

    both = run_gebra("verify", "--strict", "--gebra-strict", "noted.ir.yaml", cwd=documents)
    assert both.exit_code == 2
    assert both.stdout == ""


def test_styled_and_plain_carry_the_same_facts_across_the_process_boundary(
    documents: Path,
) -> None:
    """§5.1 on a real pipe: the default is plain, ``--color`` forces styling regardless of
    detection, and stripping the escapes recovers the plain bytes exactly."""
    plain = run_gebra("verify", "fail.ir.yaml", "--no-color", cwd=documents)
    styled = run_gebra("verify", "fail.ir.yaml", "--color", cwd=documents)
    unflagged = run_gebra("verify", "fail.ir.yaml", cwd=documents)

    assert "\x1b[" in styled.stdout
    assert "\x1b[" not in plain.stdout
    assert unflagged.stdout == plain.stdout
    assert _ESCAPES.sub("", styled.stdout) == plain.stdout


# ── snapshot: §3.2 row and its §2.6 stages ────────────────────────────────────────────────


def test_snapshot_records_then_reports_nothing_moved(project: Path) -> None:
    first = run_gebra("snapshot", "--ir", "pass.ir.yaml", cwd=project)
    assert first.exit_code == 0
    assert "recorded 1.0.0.0" in first.stdout

    again = run_gebra("snapshot", "--ir", "pass.ir.yaml", cwd=project)
    assert again.exit_code == 0
    assert "nothing moved" in again.stdout
    assert SnapshotStore.for_project(project).versions() == ("1.0.0.0",)


def test_snapshot_refuses_the_fatal_subject(project: Path) -> None:
    """§0.2's refusal at the process level: exit 1, the FATAL findings rendered, no write."""
    result = run_gebra("snapshot", "--ir", "fail.ir.yaml", cwd=project)
    assert result.exit_code == 1
    assert "fatal" in result.stdout.lower()
    assert SnapshotStore.for_project(project).versions() == ()


def test_snapshot_tool_error_stages_at_the_process_level(project: Path) -> None:
    missing = run_gebra("snapshot", "--ir", "missing.ir.yaml", cwd=project)
    assert missing.exit_code == 2
    invalid = run_gebra("snapshot", "--ir", "not-ir.yaml", cwd=project)
    assert invalid.exit_code == 2

    store_dir = project / STORE_DIRNAME
    store_dir.mkdir()
    (store_dir / META_FILENAME).write_text("not: [valid", encoding="utf-8")
    unreadable = run_gebra("snapshot", "--ir", "pass.ir.yaml", cwd=project)
    assert unreadable.exit_code == 2


def test_snapshot_extraction_stage_at_the_process_level(project: Path) -> None:
    """§2.6's ``extraction`` row for snapshot: the empty-builder target is refused at
    ``extract()``'s own boundary during the eligibility run, and nothing is written."""
    refused = run_gebra(
        "snapshot", "--import", "tests.cli.targets:build_empty_graph", "--call", cwd=project
    )
    assert refused.exit_code == 2
    assert "stage: extraction" in refused.stderr
    assert SnapshotStore.for_project(project).versions() == ()


def test_snapshot_has_no_format_flag(project: Path) -> None:
    """Appendix A's blank cell is a usage error, not a silently ignored flag (§3.4)."""
    result = run_gebra("snapshot", "--ir", "pass.ir.yaml", "--format", "json", cwd=project)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "--format" in result.stderr
    assert SnapshotStore.for_project(project).versions() == ()


# ── diff: §3.2 row, the opt-in difference signal, and its §2.6 stages ─────────────────────


def test_diff_reports_information_without_failing_on_it(documents: Path) -> None:
    identical = run_gebra("diff", "pass.ir.yaml", "pass.ir.yaml", cwd=documents)
    assert identical.exit_code == 0
    assert "nothing moved" in identical.stdout
    assert "not checked" in identical.stdout

    differing = run_gebra("diff", "pass.ir.yaml", "fail.ir.yaml", cwd=documents)
    assert differing.exit_code == 0
    assert "not checked" in differing.stdout

    signalled = run_gebra("diff", "pass.ir.yaml", "fail.ir.yaml", "--exit-code", cwd=documents)
    assert signalled.exit_code == 1


def test_diff_tool_error_stages_at_the_process_level(project: Path) -> None:
    missing = run_gebra("diff", "missing.ir.yaml", "fail.ir.yaml", cwd=project)
    assert missing.exit_code == 2
    invalid = run_gebra("diff", "not-ir.yaml", "pass.ir.yaml", cwd=project)
    assert invalid.exit_code == 2
    refused = run_gebra(
        "diff", "pass.ir.yaml", "tests.cli.targets:build_empty_graph", "--call", cwd=project
    )
    assert refused.exit_code == 2
    assert "stage: extraction" in refused.stderr


def test_a_tampered_snapshot_fails_its_digest_check(project: Path) -> None:
    """The store's own integrity check surfaces as §3.2's diff exit-2 condition."""
    recorded = run_gebra("snapshot", "--ir", "pass.ir.yaml", cwd=project)
    assert recorded.exit_code == 0
    stored = project / STORE_DIRNAME / SNAPSHOTS_DIRNAME / "1.0.0.0.yaml"
    text = stored.read_text(encoding="utf-8")
    # A parseable, valid-IR content change (a comment or whitespace edit would be exactly
    # what the canonical digest ignores): the fixture's `draft` key retyped.
    assert "draft: str" in text
    stored.write_text(text.replace("draft: str", "draft: int"), encoding="utf-8")

    result = run_gebra("diff", "1.0.0.0", "pass.ir.yaml", cwd=project)
    assert result.exit_code == 2


def test_diff_has_no_format_flag(documents: Path) -> None:
    result = run_gebra("diff", "pass.ir.yaml", "fail.ir.yaml", "--format", "json", cwd=documents)
    assert result.exit_code == 2
    assert result.stdout == ""


# ── display: §3.2 row — emit, decline, and the §4.4 pairing checks ────────────────────────


def test_display_emits_parse_checked_mermaid(documents: Path) -> None:
    result = run_gebra("display", "pass.ir.yaml", cwd=documents)
    assert result.exit_code == 0
    assert result.stderr == ""
    assert mermaid_problems(result.stdout) == []


def test_display_declines_and_refuses_at_its_stages(documents: Path) -> None:
    missing = run_gebra("display", "missing.ir.yaml", cwd=documents)
    assert missing.exit_code == 2
    assert "stage: input" in missing.stderr

    dynamic = run_gebra("display", "dynamic.ir.yaml", cwd=documents)
    assert dynamic.exit_code == 2
    assert "stage: ir-validation" in dynamic.stderr
    assert "dynamic" in dynamic.stderr

    import_shaped = run_gebra("display", "tests.cli.targets:plain_data", cwd=documents)
    assert import_shaped.exit_code == 2
    assert import_shaped.stdout == ""


def test_display_report_pairing_at_the_process_level(project: Path) -> None:
    """An overlay names its own graph: the matching pair renders, the mismatch is refused."""
    written = run_gebra(
        "verify", "fail.ir.yaml", "--format", "json", "-o", "fail-report.json", cwd=project
    )
    assert written.exit_code == 1

    overlaid = run_gebra("display", "fail.ir.yaml", "--report", "fail-report.json", cwd=project)
    assert overlaid.exit_code == 0
    assert mermaid_problems(overlaid.stdout) == []

    mismatched = run_gebra("display", "pass.ir.yaml", "--report", "fail-report.json", cwd=project)
    assert mismatched.exit_code == 2
    assert mismatched.stdout == ""


# ── history: §3.2 row and its refusals ────────────────────────────────────────────────────


def test_history_lists_an_absent_store_as_empty(documents: Path) -> None:
    result = run_gebra("history", cwd=documents)
    assert result.exit_code == 0
    assert "the store holds no versions" in result.stdout


def test_history_formats_agree_and_windows_refuse(project: Path) -> None:
    assert run_gebra("snapshot", "--ir", "pass.ir.yaml", cwd=project).exit_code == 0

    human = run_gebra("history", cwd=project)
    machine = run_gebra("history", "--format", "json", cwd=project)
    assert human.exit_code == 0
    assert machine.exit_code == 0
    assert "1.0.0.0" in human.stdout
    assert json.loads(machine.stdout)["entries"], "the projection lists the recording"

    unknown = run_gebra("history", "--since", "9.9.9.9", cwd=project)
    assert unknown.exit_code == 2


def test_a_corrupt_store_index_is_exit_2(project: Path) -> None:
    store_dir = project / STORE_DIRNAME
    store_dir.mkdir()
    (store_dir / META_FILENAME).write_text("not: [valid", encoding="utf-8")
    result = run_gebra("history", cwd=project)
    assert result.exit_code == 2


# ── The application level, usage errors, and the console script ───────────────────────────


def test_the_application_level_surface(documents: Path) -> None:
    version = run_gebra("--version", cwd=documents)
    assert version.exit_code == 0
    assert version.stdout.startswith("gebra ")
    assert gebra.__version__ in version.stdout
    assert version.stderr == ""

    unknown = run_gebra("trace", cwd=documents)
    assert unknown.exit_code == 2
    assert unknown.stdout == ""


def test_independent_usage_problems_report_together(documents: Path) -> None:
    """§5.3 at the process level: the selector conflict and the unknown flag land in one
    diagnostic, and a usage error emits no run report on any format (§3.4)."""
    result = run_gebra(
        "verify", "--ir", "pass.ir.yaml", "--import", "a:b", "--frmat", "human", cwd=documents
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    for named in ("--ir", "--import", "--frmat"):
        assert named in result.stderr


def test_the_console_script_names_the_same_function(documents: Path) -> None:
    """`gebra` (the generated wrapper) and `python -m gebra.cli` are one surface: same
    version line, and byte-identical artifacts for the same invocation (CLI-SPEC §1.2)."""
    script = console_script()
    module_version = run_gebra("--version", cwd=documents)
    script_version = run_gebra("--version", cwd=documents, program=script)
    assert script_version.exit_code == 0
    assert script_version.stdout == module_version.stdout

    module_run = run_gebra("verify", "pass.ir.yaml", cwd=documents)
    script_run = run_gebra("verify", "pass.ir.yaml", cwd=documents, program=script)
    assert script_run.exit_code == module_run.exit_code == 0
    assert script_run.stdout == module_run.stdout
