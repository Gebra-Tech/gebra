"""``gebra snapshot`` — CLI-SPEC §4.2 and §3.2's ``snapshot`` row, through ``main()``.

Every §3.2 cell is exercised through the entry point the console script names: ``0`` on a
recorded snapshot and on the nothing-moved no-op, ``1`` exactly on the §0.2 refusal (a
reached verdict whose FATAL forbids recording — with the store bytes shown untouched), and
``2`` for resolution failures, an eligibility run that reached no verdict, and the engine's
own refusals. The §4.2 sentences with teeth are each pinned: one resolution per invocation
(the ``--call`` ledger in ``test_never_invokes_store.py`` completes that claim), the digest
the store records is the digest the gate saw, no bypass flag exists, and ``--quiet`` writes
the label or nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gebra.ir import read_ir, write_ir
from gebra.ir.models import DynamicEdge, Node, WorkflowIR
from gebra.store import SnapshotStore
from gebra.verify import verify
from tests.cli.conftest import FAILING_FIXTURE as _FAILING
from tests.cli.conftest import RunCli, fixture_ir


def store_bytes(root: Path) -> dict[Path, bytes]:
    """Every file under the store, byte for byte — the untouched-store assertion."""
    store = root / ".gebra"
    if not store.exists():
        return {}
    return {path: path.read_bytes() for path in sorted(store.rglob("*")) if path.is_file()}


# ── Exit 0 — recorded, and the no-op (§3.2, §4.2) ────────────────────────────────────────


def test_the_first_snapshot_records_and_creates_the_store(
    run_cli: RunCli, project_dir: Path
) -> None:
    """A passing document lands as ``1.0.0.0`` in a store created on first write (§2.5)."""
    result = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0
    assert "recorded 1.0.0.0" in result.stdout
    assert ".gebra/snapshots/1.0.0.0.yaml" in result.stdout
    assert "none — the store's first snapshot" in result.stdout
    store = SnapshotStore(project_dir / ".gebra")
    assert store.versions() == ("1.0.0.0",)
    assert store.check().ok


def test_the_digest_the_store_records_is_the_digest_the_gate_saw(
    run_cli: RunCli, project_dir: Path
) -> None:
    """§4.2's one-resolution guarantee, read off the artifacts: the stored digest equals a
    fresh verify run's subject digest over the same document."""
    run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")

    stored = SnapshotStore(project_dir / ".gebra").read("1.0.0.0")
    report = verify(read_ir(project_dir / "pass.ir.yaml"))
    assert report.subject is not None
    assert stored.graph_version == report.subject.graph_version
    assert stored.extracted_from.source == "pass.ir.yaml"


def test_a_changed_document_bumps_from_current_and_reports_the_movement(
    run_cli: RunCli, project_dir: Path
) -> None:
    """The label is the engine's bump over ``current``, and the S/F/E movement is shown."""
    run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")
    result = run_cli("snapshot", "noted.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0
    assert "recorded 1.1.1.1" in result.stdout
    assert "previous" in result.stdout and "1.0.0.0" in result.stdout
    assert "S F E" in result.stdout
    assert "not checked [deferred-to-phase-1]" in result.stdout


def test_an_unchanged_document_is_a_no_op_that_names_the_held_label(
    run_cli: RunCli, project_dir: Path
) -> None:
    """§4.2: a statement that nothing moved, never a fabricated new label — and no byte of
    the store moves either."""
    run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")
    before = store_bytes(project_dir)

    result = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0
    assert "nothing moved — the store already holds this content as 1.0.0.0" in result.stdout
    assert store_bytes(project_dir) == before


def test_the_default_store_is_the_working_directorys_gebra(
    run_cli: RunCli, project_dir: Path
) -> None:
    """§2.5: no ``--store`` means ``./.gebra``, with no upward search."""
    result = run_cli("snapshot", "pass.ir.yaml")

    assert result.exit_code == 0
    assert (project_dir / ".gebra" / "snapshots" / "1.0.0.0.yaml").is_file()


def test_quiet_writes_only_the_recorded_label(run_cli: RunCli, project_dir: Path) -> None:
    """§4.2's ``--quiet``: the label alone on a record, nothing on a no-op."""
    first = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra", "--quiet")
    again = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra", "--quiet")

    assert first.exit_code == 0 and first.stdout == "1.0.0.0\n"
    assert again.exit_code == 0 and again.stdout == ""


# ── Exit 1 — the §0.2 refusal, and only that (§3.2) ──────────────────────────────────────


def test_a_fatal_finding_refuses_recording_with_the_findings_rendered(
    run_cli: RunCli, project_dir: Path
) -> None:
    """The gate's answer is applied, not re-derived: exit ``1``, the FATAL findings on
    stdout so the refusal is legible, the refusal named on stderr, and no store anywhere."""
    result = run_cli("snapshot", "fail.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 1
    assert "cycle-without-termination-witness" in result.stdout
    assert "fatal" in result.stdout
    assert "not recorded" in result.stderr
    assert "1 FATAL finding(s)" in result.stderr
    assert "PROPERTY-CATALOG-SPEC §0.2" in result.stderr
    assert store_bytes(project_dir) == {}


def test_the_refusal_under_quiet_writes_nothing_to_stdout(
    run_cli: RunCli, project_dir: Path
) -> None:
    """``--quiet``'s contract is "nothing when nothing was recorded" — the refusal keeps
    its stderr diagnostic and stdout stays empty."""
    result = run_cli("snapshot", "fail.ir.yaml", "--store", ".gebra", "--quiet")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "not recorded" in result.stderr


def test_a_fatal_working_definition_leaves_an_existing_store_untouched(
    run_cli: RunCli, project_dir: Path
) -> None:
    """The refusal protects a populated store too, byte for byte."""
    run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")
    before = store_bytes(project_dir)

    result = run_cli("snapshot", "fail.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 1
    assert store_bytes(project_dir) == before


# ── Exit 2 — resolution, eligibility and engine refusals (§2.6, §3.2) ────────────────────


def test_an_unresolvable_target_is_exit_2_with_the_stage_named(
    run_cli: RunCli, project_dir: Path
) -> None:
    result = run_cli("snapshot", "missing.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "nothing was recorded" in result.stderr
    assert "stage: input" in result.stderr
    assert store_bytes(project_dir) == {}


def test_an_invalid_document_is_exit_2_at_ir_validation(run_cli: RunCli, project_dir: Path) -> None:
    (project_dir / "not-ir.yaml").write_text("nodes: [1, 2, 3]\n", encoding="utf-8")
    result = run_cli("snapshot", "not-ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert "stage: ir-validation" in result.stderr
    assert store_bytes(project_dir) == {}


def test_an_ir_1_1_document_is_declined_before_the_store_exists(
    run_cli: RunCli, project_dir: Path
) -> None:
    """DEC-28 carried through: the eligibility run reaches no verdict on a ``dynamic``
    document, so the answer is exit ``2`` and the store is never created."""
    dynamic = WorkflowIR(
        ir_version="1.1",
        entry="plan",
        finish="collect",
        state={"legs": "list[str]"},
        nodes=(Node(id="plan"), Node(id="collect")),
        edges=(DynamicEdge(kind="dynamic", **{"from": "plan"}, condition="route"),),
    )
    write_ir(dynamic, project_dir / "dynamic.ir.yaml")

    result = run_cli("snapshot", "dynamic.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert "no verdict" in result.stderr
    assert store_bytes(project_dir) == {}


def test_a_document_repeating_a_node_id_is_refused_at_ir_validation(
    run_cli: RunCli, project_dir: Path
) -> None:
    """IR-SPEC §2.1 (DEC-22): the CLI never gets as far as the recorder with one of these.

    The refusal used to be the snapshot engine's, because the models admitted the document
    and the eligibility run reached a verdict on it. Card IR-07 put the constraint on
    ``WorkflowIR``, so the *loader* refuses it — which is what §2.1's MUST says ("loaders
    MUST reject it") — and the stage the CLI names moves with it: ``ir-validation``, before
    any property runs. Either way it is exit ``2`` with nothing written; what changed is how
    early, and how plainly, a user is told.

    The document is written as text rather than dumped from a model, because the model that
    would dump it can no longer be loaded back.
    """
    (project_dir / "dup.ir.yaml").write_text(
        "ir_version: '1.0'\n"
        "entry: a\n"
        "finish: a\n"
        "nodes:\n"
        "  - id: a\n"
        "  - id: a\n"
        "edges:\n"
        "  - {from: a, to: a}\n",
        encoding="utf-8",
    )

    result = run_cli("snapshot", "dup.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert "nothing was recorded" in result.stderr
    assert "stage: ir-validation" in result.stderr
    assert "declared twice" in result.stderr
    assert store_bytes(project_dir) == {}


def test_a_damaged_store_index_is_exit_2(run_cli: RunCli, project_dir: Path) -> None:
    (project_dir / ".gebra").mkdir()
    (project_dir / ".gebra" / "meta.yaml").write_text("current: [broken\n", encoding="utf-8")

    result = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert "nothing was recorded" in result.stderr


# ── Usage errors (§3.4, §5.3, Appendix A) ────────────────────────────────────────────────


def test_a_version_label_target_is_a_usage_error(run_cli: RunCli, project_dir: Path) -> None:
    """§2.2's per-verb mode rule: a stored version is already a snapshot (§4.2)."""
    result = run_cli("snapshot", "1.0.0.0", "--store", ".gebra")

    assert result.exit_code == 2
    assert "already a snapshot" in result.stderr
    assert result.stdout == ""


def test_the_snapshot_selector_of_verify_does_not_exist_here(
    run_cli: RunCli, project_dir: Path
) -> None:
    """Appendix A: a blank cell is a usage error — ``--snapshot`` is not a snapshot flag."""
    result = run_cli("snapshot", "--snapshot", "1.0.0.0", "--store", ".gebra")

    assert result.exit_code == 2
    assert "unknown option '--snapshot'" in result.stderr


def test_strict_is_refused_because_this_verb_has_no_gate(
    run_cli: RunCli, project_dir: Path
) -> None:
    """§3.3: ``--strict`` is ``gebra verify``'s, under either spelling."""
    canonical = run_cli("snapshot", "pass.ir.yaml", "--strict")
    aliased = run_cli("snapshot", "pass.ir.yaml", "--gebra-strict=p-02")

    for result in (canonical, aliased):
        assert result.exit_code == 2
        assert "accepted by gebra verify only" in result.stderr
        assert result.stdout == ""


def test_everything_independently_wrong_reports_together(
    run_cli: RunCli, project_dir: Path
) -> None:
    """§5.3: the two selectors and the strict token are one diagnostic, not three runs."""
    result = run_cli("snapshot", "--ir", "pass.ir.yaml", "--import", "pkg:attr", "--strict")

    assert result.exit_code == 2
    assert "usage errors, reported together" in result.stderr
    assert "--ir and --import are mutually exclusive" in result.stderr
    assert "accepted by gebra verify only" in result.stderr


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        pytest.param(("snapshot",), "no subject", id="no-subject"),
        pytest.param(("snapshot", "pass.ir.yaml", "noted.ir.yaml"), "one TARGET", id="two-targets"),
        pytest.param(
            ("snapshot", "pass.ir.yaml", "--ir", "noted.ir.yaml"),
            "both name a subject",
            id="target-and-selector",
        ),
        pytest.param(
            ("snapshot", "--ir", "pass.ir.yaml", "--call"),
            "--call applies to an import-reference subject only",
            id="call-on-a-document",
        ),
        pytest.param(
            ("snapshot", "--ir", "pass.ir.yaml", "--sidecar", "gebra.toml"),
            "--sidecar applies to an import-reference subject only",
            id="sidecar-on-a-document",
        ),
    ],
)
def test_usage_problems_are_refused_with_no_store_touched(
    run_cli: RunCli, project_dir: Path, argv: tuple[str, ...], fragment: str
) -> None:
    result = run_cli(*argv)

    assert result.exit_code == 2
    assert fragment in result.stderr
    assert result.stdout == ""
    assert store_bytes(project_dir) == {}


def test_fixture_documents_are_what_this_suite_says_they_are(project_dir: Path) -> None:
    """The premise check: the failing document carries a FATAL, the passing one none."""
    failing = verify(fixture_ir(_FAILING))
    assert failing.gate.counts.fatal > 0 and not failing.gate.snapshot_eligible
    passing = verify(read_ir(project_dir / "pass.ir.yaml"))
    assert passing.gate.snapshot_eligible
