"""Extraction notes through the shipped CLI — card CLI-12, end to end.

What extraction says about a live target — its warnings, and the disclosures INTROSPECTION-SPEC
§8 admits beside them — reaches every surface a ``gebra verify`` run writes: stderr, as CLI-SPEC
§5.2 has always rendered the warnings, with each disclosure under its own label; and, since
``report_format`` 1.4, the run report itself as ``extraction_notes`` (REPORT-FORMAT-SPEC §1.2;
PROPERTY-CATALOG-SPEC §0.6 item 8), so the human rendering, the native JSON and the SARIF
projection carry them too. The subjects are the subgraph-bearing builder of
:mod:`tests.sample_workflows.sentinel_subgraphs` — the mount EX-20 discloses — and the
compiled loop of :mod:`tests.sample_workflows.sentinel_runtime` that binds a recursion limit
and declares none, which fails P-02 and discloses the binding (DEC-36 §3.3).

**Notes never move an exit code** (CLI-SPEC §3.5). Held directly: the same IR verified live,
where it carries its notes, and as an IR document, where it carries none, returns one exit
code on every surface and under strict mode, with the same gate.

Never-invokes (WA-07): the targets are resolved through ``--call``, which calls the factory —
fixture code that builds a graph — and nothing else; every node body is a sentinel that records
into ``sentinel_graph.TRIPPED`` and raises, and the autouse guard asserts the ledger empty
after every test. The goldens normalize ``tool.version`` and nothing else (CLI-SPEC §7).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from gebra import extract
from gebra.ir import write_ir
from gebra.verify import RunReport
from tests.cli.conftest import RunCli
from tests.cli.goldens import compare_golden
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_runtime as sr
from tests.sample_workflows import sentinel_subgraphs as ss

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A builder whose node ``legs`` is bound to a compiled subgraph: the direct mount, which the
#: builder's direct-mount read sees (DEC-36 §3.6) — a pass with three contract-defaulted
#: warnings and one ``subgraph-read-as-one-node`` disclosure.
SUBGRAPH = "tests.sample_workflows.sentinel_subgraphs:build_direct_mount_parent"

#: A compiled two-node loop that binds ``recursion_limit`` through ``with_config`` and declares
#: none: P-02 fails (exit 1), and extraction discloses the binding.
BOUND_LOOP = "tests.sample_workflows.sentinel_runtime:bind_undeclared_loop"

SURFACES = [("human", "txt"), ("json", "json"), ("sarif", "sarif.json")]


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """No node body ran: a factory builds a graph, and extraction reads it."""
    sg.TRIPPED.clear()
    yield
    assert sg.TRIPPED == []


@pytest.fixture
def in_scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run from an empty directory, with the repository importable and no ``gebra.toml``
    within the discovery walk — so ``subject.sidecar`` stays absent and the goldens stable."""
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _report(stdout: str) -> RunReport:
    return RunReport.model_validate_json(stdout)


# ── Every surface carries the notes ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("report_format", "suffix"), SURFACES)
def test_a_subgraph_bearing_target_carries_its_notes_on_every_surface(
    run_cli: RunCli, in_scratch: Path, report_format: str, suffix: str
) -> None:
    """The card's third box, through the shell: human, JSON and SARIF each show the notes,
    goldened byte for byte, and stderr carries the same notes under the same labels."""
    result = run_cli("verify", "--call", SUBGRAPH, "--format", report_format)

    assert result.exit_code == 0
    compare_golden(f"notes/subgraph.{suffix}", result.stdout)
    compare_golden("notes/subgraph.stderr.txt", result.stderr)


def test_stderr_carries_the_warnings_then_each_disclosure_under_its_own_label(
    run_cli: RunCli, in_scratch: Path
) -> None:
    """CLI-SPEC §5.2 as amended at CLI-12: the warnings first, in emission order, under
    ``extraction warning``; then the disclosures, under ``extraction disclosure`` — never a
    warning's prefix (INTROSPECTION-SPEC §8; DEC-36 §4)."""
    result = run_cli("verify", "--call", SUBGRAPH, "--format", "json")

    lines = result.stderr.splitlines()
    assert [line.split("]")[0] + "]" for line in lines] == [
        "extraction warning [contract-defaulted]",
        "extraction warning [contract-defaulted]",
        "extraction warning [contract-defaulted]",
        "extraction disclosure [subgraph-read-as-one-node]",
    ]
    assert "node `legs` mounts or reaches a compiled subgraph" in lines[-1]


def test_the_report_carries_exactly_what_extraction_emitted_in_its_order(
    run_cli: RunCli, in_scratch: Path
) -> None:
    """``extraction_notes`` is the envelope's warnings then its disclosures, field for field —
    nothing reworded, dropped or summarized (DEC-35 §3.8's emission order; DEC-36 §4)."""
    envelope = extract(ss.build_direct_mount_parent())
    report = _report(run_cli("verify", "--call", SUBGRAPH, "--format", "json").stdout)

    carried = [(note.code, note.node, note.message) for note in report.extraction_notes]
    warned = [(record.code.value, record.node, record.message) for record in envelope.warnings]
    disclosed = [
        (record.code.value, record.node, record.message) for record in envelope.disclosures
    ]
    assert carried == warned + disclosed
    assert [note.is_disclosure for note in report.extraction_notes] == [False] * 3 + [True]


# ── Notes never move an exit code (CLI-SPEC §3.5) ────────────────────────────────────────


def _document(target: str, path: Path) -> str:
    """The IR the live run verifies, written as a document — the same subject with no notes."""
    factory = ss.build_direct_mount_parent if target == SUBGRAPH else sr.bind_undeclared_loop
    write_ir(extract(factory()).ir, path)
    return path.name


@pytest.mark.parametrize(("target", "expected_exit"), [(SUBGRAPH, 0), (BOUND_LOOP, 1)])
@pytest.mark.parametrize("strict", [(), ("--strict",)], ids=["strict-off", "strict-all"])
@pytest.mark.parametrize("report_format", ["human", "json", "sarif"])
def test_the_exit_code_is_the_same_with_and_without_the_notes(
    run_cli: RunCli,
    in_scratch: Path,
    target: str,
    expected_exit: int,
    strict: tuple[str, ...],
    report_format: str,
) -> None:
    """The live run carries notes and the document run cannot (§0.6 item 8: present only when
    the run extracted); every surface and both strict settings return one code for the two."""
    document = _document(target, in_scratch / "subject.ir.yaml")

    live = run_cli("verify", "--call", target, *strict, "--format", report_format)
    stored = run_cli("verify", document, *strict, "--format", report_format)

    assert live.exit_code == stored.exit_code == expected_exit
    assert stored.stderr == ""  # an IR document is not an extraction: nothing to say


@pytest.mark.parametrize("strict", [(), ("--strict",)], ids=["strict-off", "strict-all"])
@pytest.mark.parametrize("target", [SUBGRAPH, BOUND_LOOP])
def test_the_gate_is_identical_with_and_without_the_notes(
    run_cli: RunCli, in_scratch: Path, target: str, strict: tuple[str, ...]
) -> None:
    """Not a count, not a promotion, not an outcome moves: a note is never a finding."""
    document = _document(target, in_scratch / "subject.ir.yaml")

    live = _report(run_cli("verify", "--call", target, *strict, "--format", "json").stdout)
    stored = _report(run_cli("verify", document, *strict, "--format", "json").stdout)

    assert live.extraction_notes, "the live run carries its notes"
    assert stored.extraction_notes == ()
    assert live.gate == stored.gate
    assert live.properties == stored.properties
    assert live.best_effort == stored.best_effort


# ── A run that reached no verdict keeps what extraction said ─────────────────────────────


def test_a_tool_error_after_extraction_keeps_its_notes(
    run_cli: RunCli, in_scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dispatch tool error follows a successful extraction: the run extracted, so its report
    carries the notes (§0.6 item 8), and the human surface states them before the error."""
    monkeypatch.setattr("gebra.verify.run.is_implemented", lambda slug: False)

    as_json = run_cli("verify", "--call", SUBGRAPH, "--format", "json")
    as_human = run_cli("verify", "--call", SUBGRAPH)

    assert as_json.exit_code == as_human.exit_code == 2
    report = _report(as_json.stdout)
    assert report.error is not None and report.error.stage == "dispatch"
    assert [note.code for note in report.extraction_notes][-1] == "subgraph-read-as-one-node"
    text = as_human.stdout
    assert text.index("extraction notes") < text.index("tool error")
    assert "stage: dispatch" in as_human.stderr


# ── The other verbs that extract ─────────────────────────────────────────────────────────


def test_a_refused_snapshot_renders_its_eligibility_report_with_the_notes(
    run_cli: RunCli, in_scratch: Path
) -> None:
    """``gebra snapshot`` renders the eligibility report when §0.2 refuses the write; that
    report is an extracted run's like any other, so it carries the notes it was given."""
    result = run_cli("snapshot", "--call", BOUND_LOOP, "--store", ".gebra")

    assert result.exit_code == 1
    assert "extraction notes" in result.stdout
    assert "extraction disclosure [recursion-limit-bound-without-justification]" in result.stdout
    assert "extraction disclosure [recursion-limit-bound-without-justification]" in result.stderr
    assert "not recorded" in result.stderr


def test_a_diff_side_that_extracts_writes_its_disclosures_to_stderr(
    run_cli: RunCli, in_scratch: Path
) -> None:
    """``gebra diff`` writes no run report, and its stderr carries every note of an
    import-reference side — the disclosure included, under its own label (§5.2)."""
    document = _document(SUBGRAPH, in_scratch / "subject.ir.yaml")

    result = run_cli("diff", document, SUBGRAPH, "--call")

    assert result.exit_code == 0
    assert "extraction disclosure [subgraph-read-as-one-node]" in result.stderr
    assert "extraction warning [subgraph-read-as-one-node]" not in result.stderr
