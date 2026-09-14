"""``gebra display`` — CLI-SPEC §4.4 and §3.2's ``display`` row, through ``main()``.

Every §2.6 stage the verb can reach returns ``2`` with the stage named on stderr; the one
success shape is exit ``0`` with the Mermaid artifact alone on stdout — parse-checked here
by the guide's §9 conformance checker, so "the diagram was emitted" always means "a valid
one". The never-invokes pins for this verb (an import-shaped target refused with the module
demonstrably unimported; the substrate-blocked run) live in ``test_never_invokes.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gebra.ir import write_ir
from tests.cli.conftest import RunCli
from tests.cli.goldens import compare_golden
from tools.mermaid_check import check_mermaid

pytestmark = pytest.mark.usefixtures("project_dir")


def _report_file(run_cli: RunCli, document: str, path: str) -> str:
    result = run_cli("verify", "--ir", document, "--format", "json", "--output", path)
    assert result.exit_code in (0, 1)
    return path


# ── Exit 0: the diagram was emitted (§3.2) ───────────────────────────────────────────────


def test_a_document_target_emits_the_diagram_on_stdout_and_nothing_else(
    run_cli: RunCli,
) -> None:
    result = run_cli("display", "pass.ir.yaml")
    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout.startswith("%% gebra display:")
    assert "%% subject: pass.ir.yaml (ir-document)" in result.stdout
    check_mermaid(result.stdout)


def test_the_ir_selector_names_the_same_subject(run_cli: RunCli) -> None:
    assert (
        run_cli("display", "--ir", "pass.ir.yaml").stdout
        == run_cli("display", "pass.ir.yaml").stdout
    )


def test_a_stored_version_displays_in_snapshot_mode(run_cli: RunCli, evolved_project: Path) -> None:
    positional = run_cli("display", "1.0.0.0", "--store", ".gebra")
    assert positional.exit_code == 0
    assert "(snapshot)" in positional.stdout
    check_mermaid(positional.stdout)
    selector = run_cli("display", "--snapshot", "1.0.0.0", "--store", ".gebra")
    assert selector.stdout == positional.stdout


def test_an_overlay_report_paints_and_the_artifact_still_parses(run_cli: RunCli) -> None:
    report = _report_file(run_cli, "fail.ir.yaml", "report.json")
    result = run_cli("display", "--ir", "fail.ir.yaml", "--report", report)
    assert result.exit_code == 0
    assert "%% overlay: run report for graph_version sha256:" in result.stdout
    assert "gebra findings overlay" in result.stdout
    check_mermaid(result.stdout)


def test_a_snapshot_mode_report_overlays_its_own_stored_version(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """The §4.1 pairing on the snapshot path end to end: a snapshot-mode verify report
    records the stored digest, and displaying the same stored version accepts it."""
    verified = run_cli(
        "verify",
        "--snapshot",
        "1.0.0.0",
        "--store",
        ".gebra",
        "--format",
        "json",
        "--output",
        "stored.json",
    )
    assert verified.exit_code in (0, 1)
    result = run_cli(
        "display", "--snapshot", "1.0.0.0", "--store", ".gebra", "--report", "stored.json"
    )
    assert result.exit_code == 0
    assert "%% overlay: run report for graph_version sha256:" in result.stdout
    check_mermaid(result.stdout)
    other = run_cli(
        "display", "--snapshot", "1.1.1.0", "--store", ".gebra", "--report", "stored.json"
    )
    assert other.exit_code == 2
    assert "differs from the displayed IR's digest" in other.stderr


def test_color_flags_move_nothing_on_the_artifact(run_cli: RunCli) -> None:
    plain = run_cli("display", "pass.ir.yaml", "--no-color")
    forced = run_cli("display", "pass.ir.yaml", "--color")
    assert plain.exit_code == forced.exit_code == 0
    assert plain.stdout == forced.stdout


def test_output_writes_the_same_bytes_the_stream_carries(run_cli: RunCli, tmp_path: Path) -> None:
    streamed = run_cli("display", "pass.ir.yaml")
    written = run_cli("display", "pass.ir.yaml", "--output", "diagram.mmd")
    assert written.exit_code == 0
    assert written.stdout == ""
    assert Path("diagram.mmd").read_text(encoding="utf-8") == streamed.stdout


def test_an_unwritable_output_is_exit_2_with_no_artifact_anywhere(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml", "--output", "no-such-dir/diagram.mmd")
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "cannot write --output" in result.stderr


# ── Exit 2: resolution failures (§2.6) ───────────────────────────────────────────────────


def test_a_missing_document_is_the_input_stage(run_cli: RunCli) -> None:
    result = run_cli("display", "absent.ir.yaml")
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "no diagram was emitted (stage: input)" in result.stderr


def test_a_document_that_is_not_an_ir_is_the_ir_validation_stage(run_cli: RunCli) -> None:
    Path("not-ir.yaml").write_text("just: prose\n", encoding="utf-8")
    result = run_cli("display", "not-ir.yaml")
    assert result.exit_code == 2
    assert "no diagram was emitted (stage: ir-validation)" in result.stderr


def test_an_unheld_label_is_refused_with_the_stores_own_vocabulary(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("display", "9.9.9.9", "--store", ".gebra")
    assert result.exit_code == 2
    assert "no diagram was emitted (stage: input)" in result.stderr
    assert "holds no version" in result.stderr


def test_a_no_grammar_target_is_a_resolution_failure_not_a_usage_error(
    run_cli: RunCli,
) -> None:
    result = run_cli("display", "1.2.3")
    assert result.exit_code == 2
    assert "no diagram was emitted (stage: input)" in result.stderr
    assert "V.S.F.E" in result.stderr


# ── Exit 0: the ir 1.1 document (CLI-11) ─────────────────────────────────────────────────

#: A dynamically dispatching router authored ahead of a cycle with no termination witness —
#: the document the two 1.1 goldens draw. It exercises both halves of the card at once: the
#: headless edge's own drawing, and the §4.4 paints whose link indices it must not move.
DYNAMIC_DOCUMENT = {
    "ir_version": "1.1",
    "entry": "plan",
    "finish": ["collect"],
    "nodes": [{"id": "plan"}, {"id": "book_leg"}, {"id": "check"}, {"id": "collect"}],
    "edges": [
        {"kind": "dynamic", "from": "plan", "condition": "route_legs"},
        {"from": "book_leg", "to": "check"},
        {
            "kind": "conditional",
            "from": "check",
            "path_map": {"retry": "book_leg", "done": "collect"},
        },
    ],
}


def _write_dynamic_document(name: str = "dynamic.ir.yaml") -> str:
    """The 1.1 document on disk, through the documented ingestion path."""
    import gebra.ir as gir

    write_ir(gir.load_json(gir.WorkflowIR, json.dumps(DYNAMIC_DOCUMENT)), name)
    return name


def test_a_dynamic_bearing_document_emits_a_diagram(run_cli: RunCli) -> None:
    """The decline CLI-06 landed on DIAGRAM-STYLE-GUIDE §3.4 is lifted (PD-060): the
    headless router edge is carried on its source — a marker and a dispatch note — so the
    verb draws the document instead of reporting a tool error."""
    result = run_cli("display", _write_dynamic_document())
    assert result.exit_code == 0
    assert result.stderr == ""
    assert "%% ir_version: 1.1" in result.stdout
    assert '  n_plan["plan [D1]"]' in result.stdout
    assert (
        "dynamic dispatch - plan: 1 dynamic router, targets not statically known" in result.stdout
    )
    assert "-.->" not in result.stdout, "a headless edge was drawn as an arrow"
    check_mermaid(result.stdout)


def test_the_dynamic_documents_own_report_overlays_it(run_cli: RunCli) -> None:
    """Acceptance box 2's overlay half: a run report over *this* document paints onto it,
    and every §4.4 paint names a link the drawing has."""
    document = _write_dynamic_document()
    report = _report_file(run_cli, document, "dynamic-report.json")
    result = run_cli("display", "--ir", document, "--report", report)
    assert result.exit_code == 0
    assert "%% overlay: run report for graph_version sha256:" in result.stdout
    assert "gebra dynamic dispatch" in result.stdout
    assert "gebra findings overlay" in result.stdout
    links = [line for line in result.stdout.split("\n") if "-->" in line]
    for line in result.stdout.split("\n"):
        if line.startswith("  linkStyle "):
            assert int(line.split()[1]) < len(links)
    check_mermaid(result.stdout)


# ── Exit 2: the --report refusals (§4.4) ─────────────────────────────────────────────────


def test_a_missing_report_is_refused(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml", "--report", "absent.json")
    assert result.exit_code == 2
    assert "cannot read --report" in result.stderr


def test_a_non_json_report_is_refused(run_cli: RunCli) -> None:
    Path("garbage.json").write_text("not json at all", encoding="utf-8")
    result = run_cli("display", "pass.ir.yaml", "--report", "garbage.json")
    assert result.exit_code == 2
    assert "not a readable run report" in result.stderr


def test_a_document_with_no_report_format_member_is_refused_by_that_fact(
    run_cli: RunCli,
) -> None:
    Path("shapeless.json").write_text('{"anything": true}', encoding="utf-8")
    result = run_cli("display", "pass.ir.yaml", "--report", "shapeless.json")
    assert result.exit_code == 2
    assert "no report_format member" in result.stderr


def test_an_unknown_major_is_refused_before_any_model_runs(run_cli: RunCli) -> None:
    Path("future.json").write_text('{"report_format": "2.0"}', encoding="utf-8")
    result = run_cli("display", "pass.ir.yaml", "--report", "future.json")
    assert result.exit_code == 2
    assert "a MAJOR this build does not know" in result.stderr
    assert "'1.3'" in result.stderr


def test_a_minor_this_build_does_not_read_is_refused_naming_the_one_it_does(
    run_cli: RunCli,
) -> None:
    Path("older.json").write_text('{"report_format": "1.0"}', encoding="utf-8")
    result = run_cli("display", "pass.ir.yaml", "--report", "older.json")
    assert result.exit_code == 2
    assert "which this build does not read" in result.stderr
    assert "REPORT-FORMAT-SPEC §1.6" in result.stderr


def test_a_known_format_that_is_not_a_run_report_is_refused_by_the_model(
    run_cli: RunCli,
) -> None:
    Path("hollow.json").write_text('{"report_format": "1.3"}', encoding="utf-8")
    result = run_cli("display", "pass.ir.yaml", "--report", "hollow.json")
    assert result.exit_code == 2
    assert "not a valid run report" in result.stderr


def test_a_subjectless_tool_error_report_is_refused(run_cli: RunCli) -> None:
    result = run_cli("verify", "--ir", "absent.ir.yaml", "--format", "json", "-o", "err.json")
    assert result.exit_code == 2
    refusal = run_cli("display", "pass.ir.yaml", "--report", "err.json")
    assert refusal.exit_code == 2
    assert "carries no subject" in refusal.stderr
    assert "no findings to paint" in refusal.stderr


def test_a_report_about_another_workflow_is_refused_on_the_digest(run_cli: RunCli) -> None:
    report = _report_file(run_cli, "fail.ir.yaml", "fail-report.json")
    result = run_cli("display", "pass.ir.yaml", "--report", report)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "differs from the displayed IR's digest" in result.stderr


# ── Usage errors (§3.4, §5.3) ────────────────────────────────────────────────────────────


def test_an_import_shaped_target_is_a_usage_error_saying_what_to_do_instead(
    run_cli: RunCli,
) -> None:
    result = run_cli("display", "travel_booking:build_graph")
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "usage error" in result.stderr
    assert "no live-target mode" in result.stderr
    assert "refused before any import happens" in result.stderr


def test_the_import_selector_does_not_exist_here(run_cli: RunCli) -> None:
    result = run_cli("display", "--import", "pkg:attr")
    assert result.exit_code == 2
    assert "unknown option '--import'" in result.stderr


@pytest.mark.parametrize("flag", ["--call", "--sidecar"])
def test_extraction_flags_do_not_exist_here(run_cli: RunCli, flag: str) -> None:
    argv = ["display", "pass.ir.yaml", flag]
    if flag == "--sidecar":
        argv.append("gebra.toml")
    result = run_cli(*argv)
    assert result.exit_code == 2
    assert f"unknown option '{flag}'" in result.stderr


def test_strict_is_refused_because_display_has_no_gate(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml", "--strict")
    assert result.exit_code == 2
    assert "display has no gate for a promotion to move" in result.stderr


def test_the_format_value_set_is_mermaid_alone(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml", "--format", "plantuml")
    assert result.exit_code == 2
    assert "--format 'plantuml' is not one of mermaid" in result.stderr


def test_format_mermaid_is_the_explicit_spelling_of_the_default(run_cli: RunCli) -> None:
    assert (
        run_cli("display", "pass.ir.yaml", "--format", "mermaid").stdout
        == run_cli("display", "pass.ir.yaml").stdout
    )


def test_two_selectors_are_refused_together(run_cli: RunCli) -> None:
    result = run_cli("display", "--ir", "pass.ir.yaml", "--snapshot", "1.0.0.0")
    assert result.exit_code == 2
    assert "mutually exclusive mode selectors" in result.stderr


def test_a_target_beside_a_selector_is_refused(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml", "--ir", "fail.ir.yaml")
    assert result.exit_code == 2
    assert "both name a subject" in result.stderr


def test_no_subject_is_a_usage_error_not_a_guess(run_cli: RunCli) -> None:
    result = run_cli("display")
    assert result.exit_code == 2
    assert "no subject" in result.stderr


def test_two_targets_are_refused(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml", "fail.ir.yaml")
    assert result.exit_code == 2
    assert "display takes one TARGET" in result.stderr


def test_an_unknown_flag_gets_a_suggestion_from_this_verbs_own_flags(
    run_cli: RunCli,
) -> None:
    result = run_cli("display", "pass.ir.yaml", "--repory", "x.json")
    assert result.exit_code == 2
    assert "unknown option '--repory'" in result.stderr
    assert "--report" in result.stderr


def test_independent_problems_report_together(run_cli: RunCli) -> None:
    result = run_cli("display", "--ir", "pass.ir.yaml", "--snapshot", "1.0.0.0", "--format", "svg")
    assert result.exit_code == 2
    assert "usage errors, reported together" in result.stderr
    assert "mutually exclusive" in result.stderr
    assert "--format 'svg'" in result.stderr


# ── Goldens — byte-stable artifacts through the entry point ──────────────────────────────


def test_golden_plain_document(run_cli: RunCli) -> None:
    result = run_cli("display", "pass.ir.yaml")
    assert result.exit_code == 0
    compare_golden("display/document-pass.mmd", result.stdout)


def test_golden_overlaid_document(run_cli: RunCli) -> None:
    report = _report_file(run_cli, "fail.ir.yaml", "report.json")
    result = run_cli("display", "--ir", "fail.ir.yaml", "--report", report)
    assert result.exit_code == 0
    compare_golden("display/document-fail-overlaid.mmd", result.stdout)


def test_golden_stored_version(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("display", "--snapshot", "1.0.0.0", "--store", ".gebra")
    assert result.exit_code == 0
    compare_golden("display/snapshot-oldest.mmd", result.stdout)


def test_golden_plain_dynamic_document(run_cli: RunCli) -> None:
    result = run_cli("display", _write_dynamic_document())
    assert result.exit_code == 0
    compare_golden("display/document-dynamic.mmd", result.stdout)


def test_golden_overlaid_dynamic_document(run_cli: RunCli) -> None:
    document = _write_dynamic_document()
    report = _report_file(run_cli, document, "dynamic-report.json")
    result = run_cli("display", "--ir", document, "--report", report)
    assert result.exit_code == 0
    compare_golden("display/document-dynamic-overlaid.mmd", result.stdout)
