"""``gebra verify`` — §3.2's verify row on constructed cases, through the entry point.

**Acceptance box 1 of CLI-04 lives here**: exit codes ``0``/``1``/``2`` on constructed
cases, including tool-error ``2`` at every §2.6 stage the verb can reach — ``input``,
``extraction``, ``ir-validation`` (the CLI's own mapping; ``verify()``'s former ir-1.1
refusal is gone since VAL-14, and a ``dynamic``-bearing document now reaches a verdict here),
and ``dispatch``. Alongside it: §3.3's strict forms through the whole shell,
§3.4's usage errors with §5.3's one-diagnostic rule, §3.5's format invariance, and §5.2's
stream discipline (stdout carries the artifact and nothing else).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import gebra
from gebra.ir import write_ir
from gebra.ir.models import DynamicEdge, Edge, Node, NormalEdge, WorkflowIR
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore
from tests.cli.conftest import PASSING_FIXTURE, RunCli, fixture_ir

# ── Exit 0: a verdict of pass ────────────────────────────────────────────────────────────


def test_a_passing_document_is_exit_0_with_the_artifact_on_stdout(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    result = run_cli("verify", "pass.ir.yaml")
    assert result.exit_code == 0
    assert "pass" in result.stdout
    assert result.stderr == ""


def test_a_json_document_resolves_by_suffix(run_cli: RunCli, in_documents_dir: Path) -> None:
    assert run_cli("verify", "pass.ir.json").exit_code == 0


def test_warning_grade_notes_leave_the_exit_code_at_0(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§3.1: WARNING findings are rendered as notes and do not affect the code."""
    result = run_cli("verify", "noted.ir.yaml", "--format", "json")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["gate"]["outcome"] == "pass-with-notes"


# ── Exit 1: a verdict of fail ────────────────────────────────────────────────────────────


def test_a_failing_document_is_exit_1(run_cli: RunCli, in_documents_dir: Path) -> None:
    result = run_cli("verify", "fail.ir.yaml")
    assert result.exit_code == 1
    assert "fail" in result.stdout


def test_strict_promotion_moves_the_gate_to_1(run_cli: RunCli, in_documents_dir: Path) -> None:
    """§3.3: the same subject that passes with notes fails under ``--strict``."""
    assert run_cli("verify", "noted.ir.yaml").exit_code == 0
    assert run_cli("verify", "--strict", "noted.ir.yaml").exit_code == 1


def test_the_gebra_strict_spelling_is_the_same_gate(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    assert run_cli("verify", "--gebra-strict", "noted.ir.yaml").exit_code == 1


def test_a_per_property_strict_flag_promotes_only_the_named_property(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§3.3's second form, both arms: the owning property promotes, another does not."""
    promoted = run_cli("verify", "--strict=determinism-replay", "noted.ir.yaml")
    assert promoted.exit_code == 1
    unrelated = run_cli("verify", "--strict=graph-well-formed", "noted.ir.yaml")
    assert unrelated.exit_code == 0


def test_the_strict_policy_is_recorded_verbatim_in_the_report(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    result = run_cli("verify", "--strict=determinism-replay", "noted.ir.yaml", "--format", "json")
    report = json.loads(result.stdout)
    assert report["gate"]["strict"] == {
        "mode": "per-property",
        "properties": ["determinism-replay"],
    }
    assert report["gate"]["promotions"], "the promotion the flag selected is missing"


# ── Exit 2: tool error, stage by stage (§2.6) ────────────────────────────────────────────


def test_an_unresolvable_target_is_exit_2_stage_input(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    result = run_cli("verify", "no-such-file.ir.yaml")
    assert result.exit_code == 2
    assert "no verdict was reached" in result.stderr
    assert "stage: input" in result.stderr


def test_an_extraction_refusal_is_exit_2_stage_extraction(
    run_cli: RunCli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty builder is refused at extract()'s own boundary (empty-node-set)."""
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    result = run_cli("verify", "--call", "tests.cli.targets:build_empty_graph")
    assert result.exit_code == 2
    assert "stage: extraction" in result.stderr


def test_an_invalid_document_is_exit_2_stage_ir_validation(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("not-ir.ir.yaml").write_text("ir_version: '1.0'\nnodes: []\n", encoding="utf-8")
    result = run_cli("verify", "not-ir.ir.yaml")
    assert result.exit_code == 2
    assert "stage: ir-validation" in result.stderr


def test_an_ir_1_1_document_reaches_a_verdict(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DEC-28's validator semantics landed (VAL-14): a ``dynamic``-bearing document is verified
    like any other, its stamp is reported in the subject, and the nodes only the router reaches
    are surfaced on P-01's witness rather than reported unreachable. Until VAL-14 this was
    ``verify()``'s own ``ir-validation`` refusal at exit ``2``."""
    monkeypatch.chdir(tmp_path)
    write_ir(_dynamic_document(), Path("dynamic.ir.yaml"))
    result = run_cli("verify", "dynamic.ir.yaml", "--format", "json")
    assert result.exit_code == 0
    assert result.stderr == ""
    document = json.loads(result.stdout)
    assert document["subject"]["ir_version"] == "1.1"
    assert document["gate"]["outcome"] == "pass"
    p01 = next(o for o in document["properties"] if o["property"] == "graph-well-formed")
    assert p01["witness"]["dynamic_dependent"] == ["book_leg", "collect"]


def test_a_dispatch_failure_is_exit_2_reported_by_the_run_report(
    run_cli: RunCli, in_documents_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2.6's last row: a wedge validator missing from the registry is a tool error."""
    monkeypatch.setattr("gebra.verify.run.is_implemented", lambda slug: False)
    result = run_cli("verify", "pass.ir.yaml", "--format", "json")
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["error"]["stage"] == "dispatch"
    assert "stage: dispatch" in result.stderr


def test_a_tool_error_report_is_the_artifact_on_the_json_surface(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§5.5: in ``--format json`` an exit-2 run is the tool-error RunReport, properties []."""
    result = run_cli("verify", "no-such-file.ir.yaml", "--format", "json")
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["gate"]["outcome"] == "tool-error"
    assert report["gate"]["exit_code"] == 2
    assert report["properties"] == []
    assert report["error"]["stage"] == "input"
    assert "subject" not in report or report["subject"] is None


def test_a_tool_error_log_on_the_sarif_surface_carries_the_exit_code(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§5.5: the SARIF alternative is a log carrying ``gebra/exitCode: 2``."""
    result = run_cli("verify", "no-such-file.ir.yaml", "--format", "sarif")
    assert result.exit_code == 2
    log = json.loads(result.stdout)
    assert log["runs"][0]["properties"]["gebra/exitCode"] == 2


# ── Snapshot mode (§4.1) ─────────────────────────────────────────────────────────────────


def test_a_stored_version_verifies_with_its_label_in_the_subject(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _store_holding_v1(tmp_path / ".gebra")
    result = run_cli("verify", "1.0.0.0", "--format", "json")
    assert result.exit_code == 0
    subject = json.loads(result.stdout)["subject"]
    assert subject["input_mode"] == "snapshot"
    assert subject["version"] == "1.0.0.0"
    assert subject["source"] == "tests:cli-suite"


def test_the_store_flag_names_another_store_directory(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # the default ./.gebra store stays absent
    _store_holding_v1(tmp_path / "elsewhere")
    assert run_cli("verify", "1.0.0.0").exit_code == 2
    assert (
        run_cli("verify", "--snapshot", "1.0.0.0", "--store", str(tmp_path / "elsewhere")).exit_code
        == 0
    )


# ── §3.4 usage errors, §5.3 one diagnostic ───────────────────────────────────────────────


def test_a_usage_error_emits_no_run_report_on_any_format(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§3.4: the invocation never became a run — a stderr diagnostic and nothing else."""
    for extra in ((), ("--format", "json"), ("--format", "sarif")):
        result = run_cli("verify", "--frmat", "x", "pass.ir.yaml", *extra)
        assert result.exit_code == 2
        assert result.stdout == ""
        assert "usage error" in result.stderr


def test_independent_problems_are_reported_together(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§5.3: two mutually exclusive selectors and an unknown flag are one diagnostic."""
    result = run_cli("verify", "--ir", "pass.ir.yaml", "--import", "pkg:graph", "--frmat", "json")
    assert result.exit_code == 2
    assert "reported together" in result.stderr
    assert "--frmat" in result.stderr
    assert "--ir and --import" in result.stderr
    assert result.stderr.count("Try 'gebra verify --help'.") == 1


def test_an_unknown_flag_suggests_from_the_verbs_own_flags(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    result = run_cli("verify", "--frmat", "json", "pass.ir.yaml")
    assert "Did you mean --format?" in result.stderr


def test_target_plus_selector_is_a_usage_error_naming_both(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    result = run_cli("verify", "pass.ir.yaml", "--ir", "pass.ir.yaml")
    assert result.exit_code == 2
    assert "'pass.ir.yaml'" in result.stderr
    assert "--ir" in result.stderr


def test_two_targets_are_a_usage_error(run_cli: RunCli, in_documents_dir: Path) -> None:
    result = run_cli("verify", "pass.ir.yaml", "fail.ir.yaml")
    assert result.exit_code == 2
    assert "one TARGET" in result.stderr


def test_no_subject_is_a_usage_error(run_cli: RunCli) -> None:
    result = run_cli("verify")
    assert result.exit_code == 2
    assert "no subject" in result.stderr


def test_sidecar_outside_extracted_mode_is_a_usage_error(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§2.4: a usage error rather than a silently ignored flag."""
    result = run_cli("verify", "pass.ir.yaml", "--sidecar", "gebra.toml")
    assert result.exit_code == 2
    assert "--sidecar" in result.stderr
    assert "ir-document" in result.stderr


def test_a_selector_named_mode_survives_an_unknown_flag_beside_it(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§5.3 both ways at once: the unknown flag and the mode-restricted flag are
    independent problems (the selector names the mode outright), and both arrive in the
    one diagnostic."""
    result = run_cli("verify", "--ir", "pass.ir.yaml", "--call", "--frmat", "json")
    assert result.exit_code == 2
    assert "--frmat" in result.stderr
    assert "--call" in result.stderr
    assert "reported together" in result.stderr


def test_an_unknown_format_value_is_a_usage_error_with_a_suggestion(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    result = run_cli("verify", "pass.ir.yaml", "--format", "jsn")
    assert result.exit_code == 2
    assert "Did you mean json?" in result.stderr


def test_help_shows_both_strict_spellings(run_cli: RunCli) -> None:
    """§3.3: a reader who arrived from the frozen spec finds the spelling they typed."""
    result = run_cli("verify", "--help")
    assert result.exit_code == 0
    assert "--strict" in result.stdout
    assert "--gebra-strict" in result.stdout


# ── §3.5: what never moves an exit code ──────────────────────────────────────────────────


@pytest.mark.parametrize("document", ["pass.ir.yaml", "fail.ir.yaml"])
def test_the_three_formats_agree_on_the_exit_code(
    run_cli: RunCli, in_documents_dir: Path, document: str
) -> None:
    codes = {
        run_cli("verify", document, "--format", report_format).exit_code
        for report_format in ("human", "json", "sarif")
    }
    assert len(codes) == 1


def test_color_flags_do_not_move_the_exit_code(run_cli: RunCli, in_documents_dir: Path) -> None:
    plain = run_cli("verify", "fail.ir.yaml", "--no-color")
    styled = run_cli("verify", "fail.ir.yaml", "--color")
    assert plain.exit_code == styled.exit_code == 1
    assert "\x1b[" not in plain.stdout
    assert "\x1b[" in styled.stdout  # §5.1: forced on regardless of detection


# ── §5.2: streams and --output ───────────────────────────────────────────────────────────


def test_the_json_artifact_is_exactly_the_report_bytes(
    run_cli: RunCli, in_documents_dir: Path
) -> None:
    """§5.2: ``--format json > report.json`` writes exactly the report — parse the whole
    stream, not a line of it, and nothing else may be on stdout."""
    result = run_cli("verify", "pass.ir.yaml", "--format", "json")
    report = json.loads(result.stdout)
    assert report["tool"] == {"name": "gebra", "version": gebra.__version__}
    assert not result.stdout.endswith("\n\n")


def test_output_writes_the_artifact_to_the_file_with_a_trailing_newline(
    run_cli: RunCli, in_documents_dir: Path, tmp_path: Path
) -> None:
    """§5.2/§1.5: a report written to a file ends with one trailing newline; stdout stays
    empty because the artifact went to the file."""
    destination = tmp_path / "report.json"
    result = run_cli("verify", "pass.ir.yaml", "--format", "json", "-o", str(destination))
    assert result.exit_code == 0
    assert result.stdout == ""
    text = destination.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    stream = run_cli("verify", "pass.ir.yaml", "--format", "json")
    assert text == stream.stdout + "\n"


def test_an_unwritable_output_path_is_exit_2_with_a_diagnostic(
    run_cli: RunCli, in_documents_dir: Path, tmp_path: Path
) -> None:
    result = run_cli(
        "verify", "pass.ir.yaml", "-o", str(tmp_path / "missing-directory" / "report.txt")
    )
    assert result.exit_code == 2
    assert "cannot write --output" in result.stderr


def test_extraction_warnings_render_on_stderr_and_never_move_the_code(
    run_cli: RunCli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.2: warnings are stderr diagnostics in emission order; §3.5: never an exit-code
    input. The sentinel graph's two undeclared nodes carry inference/default records."""
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    result = run_cli("verify", "tests.sample_workflows.sentinel_cli:graph", "--format", "json")
    assert result.exit_code == 0
    assert "extraction warning [contract-inferred]" in result.stderr
    assert "extraction warning [contract-defaulted]" in result.stderr
    assert json.loads(result.stdout)["subject"]["input_mode"] == "extracted"


def _dynamic_document() -> WorkflowIR:
    """A minimal ir 1.1 document — one ``dynamic`` edge, the DEC-28 shape."""
    edges: list[Edge] = [
        DynamicEdge(kind="dynamic", **{"from": "plan"}, condition="route_legs"),
        NormalEdge(kind="normal", **{"from": "book_leg"}, to="collect"),
    ]
    return WorkflowIR(
        ir_version="1.1",
        entry="plan",
        finish="collect",
        state={"legs": "list[str]"},
        nodes=(Node(id="plan"), Node(id="book_leg"), Node(id="collect")),
        edges=tuple(edges),
    )


def _store_holding_v1(store_dir: Path) -> SnapshotStore:
    store = SnapshotStore(store_dir)
    store.write(
        Snapshot.of(
            fixture_ir(PASSING_FIXTURE),
            version="1.0.0.0",
            extracted_from=ExtractedFrom(
                source="tests:cli-suite",
                extractor_version="0.0.1.dev0",
                extracted_at="2026-08-21T00:00:00Z",
            ),
        )
    )
    return store
