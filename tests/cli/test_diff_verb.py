"""``gebra diff`` — CLI-SPEC §4.3 and §3.2's ``diff`` row, through ``main()``.

The two acceptance sentences this card owes the diff verb are both pinned here: **the
output shows the S/F/E class** (a ``bump class`` line read off ``WorkflowDiff.bump_class``,
asserted per constructed pair), and **the deferred-P-12 marker is rendered honestly** —
*not checked* with its status on every outcome, with no ``safe``/``breaking`` labelling
anywhere in the captured output. Exit codes: ``0`` on a completed comparison whatever it
found, ``1`` only under ``--exit-code`` when the sides differ, ``2`` when a side fails to
resolve or a stored snapshot fails its digest check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gebra.ir import write_ir
from gebra.ir.models import DynamicEdge, Node, WorkflowIR
from tests.cli.conftest import RunCli

#: The evolved store's labels (derived by the diff engine — tests/lineage/stores.py).
OLDEST, AUDIT_ADDED, ESCALATED, RECEIPT_ADDED, NEWEST = (
    "1.0.0.0",
    "1.1.1.0",
    "1.1.2.0",
    "1.1.2.1",
    "1.2.2.1",
)


# ── The comparison, completed (§3.2 exit 0) ──────────────────────────────────────────────


def test_two_stored_versions_diff_with_both_labels_on_the_anchors(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra")

    assert result.exit_code == 0
    assert re.search(rf"before\s+{re.escape(OLDEST)}\s+sha256:", result.stdout)
    assert re.search(rf"after\s+{re.escape(NEWEST)}\s+sha256:", result.stdout)
    assert result.stderr == ""


def test_the_bump_class_line_shows_the_s_f_e_class(run_cli: RunCli, evolved_project: Path) -> None:
    """**Acceptance:** diff output shows the S/F/E class, per pair, exactly the engine's.

    The pairs are the evolved store's own stages, so each expected class is the one the
    fixture's label derivation already proved: an audit node wired in is S F, an effect
    escalation is F, a new optional key is E, and the whole span is S F E.
    """
    span = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra")
    audit = run_cli("diff", OLDEST, AUDIT_ADDED, "--store", ".gebra")
    escalation = run_cli("diff", AUDIT_ADDED, ESCALATED, "--store", ".gebra")
    receipt = run_cli("diff", ESCALATED, RECEIPT_ADDED, "--store", ".gebra")

    assert re.search(r"bump class\s+S F E", span.stdout)
    assert re.search(r"bump class\s+S F\n", audit.stdout)
    assert re.search(r"bump class\s+F\n", escalation.stdout)
    assert re.search(r"bump class\s+E\n", receipt.stdout)


def test_the_deferred_p12_marker_renders_honestly_on_every_outcome(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """**Acceptance:** the marker is *not checked* with its status — and no diff is
    labelled safe or breaking, on a changed pair or an identical one (§4.3)."""
    changed = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra")
    identical = run_cli("diff", OLDEST, OLDEST, "--store", ".gebra")

    for result in (changed, identical):
        assert "evolution-safety" in result.stdout
        assert "not checked [deferred-to-phase-1]" in result.stdout
        for verdict in ("safe\n", " safe ", "breaking", "unsafe"):
            assert verdict not in result.stdout.lower()
    # The one licensed appearance of the word: the denial itself, stated with the marker.
    assert "never safety" in changed.stdout


def test_an_identical_pair_says_the_counters_did_not_move(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """§4.3: a diff that changed nothing says the counters did not move — a different
    sentence from a clean bill, and the phrase "no issues" appears nowhere."""
    result = run_cli("diff", NEWEST, NEWEST, "--store", ".gebra")

    assert result.exit_code == 0
    assert "nothing moved: both sides carry one graph_version" in result.stdout
    assert "none — the counters do not move" in result.stdout
    assert "no issues" not in result.stdout.lower()


def test_the_deltas_render_what_the_engine_reports(run_cli: RunCli, evolved_project: Path) -> None:
    """One span, every section: the audit node and its wiring under topology, its contract
    and the escalation under contracts, the receipt key under state, END wiring widened."""
    result = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra")

    assert "topology" in result.stdout
    assert "+ node audit" in result.stdout
    assert "+ finish wiring audit -> END" in result.stdout
    assert "contracts" in result.stdout
    assert "+ node contract audit" in result.stdout
    assert "billable" in result.stdout  # work's escalated effect, canonical JSON
    assert "state schema" in result.stdout
    assert "+ key receipt: str (optional=true)" in result.stdout
    assert "canonical JSON" in result.stdout  # the not-the-authored-spelling caption


def test_swapping_the_sides_swaps_added_and_removed(run_cli: RunCli, evolved_project: Path) -> None:
    forward = run_cli("diff", OLDEST, AUDIT_ADDED, "--store", ".gebra")
    backward = run_cli("diff", AUDIT_ADDED, OLDEST, "--store", ".gebra")

    assert "+ node audit" in forward.stdout
    assert "- node audit" in backward.stdout
    assert re.search(r"bump class\s+S F\n", backward.stdout)


def test_a_stored_side_mixes_with_a_document_side(run_cli: RunCli, evolved_project: Path) -> None:
    """§4.3: a version label and an IR document mix freely; the bare side has no label."""
    result = run_cli("diff", OLDEST, "final.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0
    assert re.search(rf"before\s+{re.escape(OLDEST)}\s+sha256:", result.stdout)
    assert re.search(r"after\s+sha256:", result.stdout)
    assert "+ node audit" in result.stdout


def test_an_identical_stored_and_document_pair_completes_with_nothing_moved(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("diff", NEWEST, "final.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0
    assert "nothing moved" in result.stdout


# ── --exit-code (§3.2 exit 1: a difference signal, never a verdict) ──────────────────────


def test_exit_code_flags_a_difference_and_only_then(run_cli: RunCli, evolved_project: Path) -> None:
    without_flag = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra")
    with_flag = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra", "--exit-code")
    identical = run_cli("diff", OLDEST, OLDEST, "--store", ".gebra", "--exit-code")

    assert without_flag.exit_code == 0
    assert with_flag.exit_code == 1
    assert identical.exit_code == 0


# ── Exit 2 — a side that fails, a store that lies (§2.6, §3.2) ───────────────────────────


def test_an_unheld_label_names_its_side_with_a_suggestion(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("diff", "1.0.0.1", NEWEST, "--store", ".gebra")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "no comparison was made" in result.stderr
    assert "BEFORE" in result.stderr
    assert "Did you mean" in result.stderr


def test_a_missing_document_side_names_its_side(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("diff", OLDEST, "missing.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert "AFTER" in result.stderr
    assert "stage: input" in result.stderr


def test_a_tampered_snapshot_fails_its_digest_check(run_cli: RunCli, evolved_project: Path) -> None:
    """§4.3: stored sides are read with the digest check on — a snapshot whose bytes no
    longer hash to their recorded digest is refused, never diffed under a wrong anchor."""
    victim = evolved_project / ".gebra" / "snapshots" / f"{NEWEST}.yaml"
    victim.write_text(
        victim.read_text(encoding="utf-8").replace("id: audit", "id: audit2"), encoding="utf-8"
    )

    result = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra")

    assert result.exit_code == 2
    assert "no comparison was made" in result.stderr
    assert "digest" in result.stderr


def test_an_ir_1_1_document_side_is_declined(run_cli: RunCli, evolved_project: Path) -> None:
    """PD-044 D11 / DEC-28: the diff engine declines a ``dynamic`` document; the verb
    reports the decline as exit ``2`` rather than dropping the edge."""
    dynamic = WorkflowIR(
        ir_version="1.1",
        entry="plan",
        finish="collect",
        state={"legs": "list[str]"},
        nodes=(Node(id="plan"), Node(id="collect")),
        edges=(DynamicEdge(kind="dynamic", **{"from": "plan"}, condition="route"),),
    )
    write_ir(dynamic, evolved_project / "dynamic.ir.yaml")

    result = run_cli("diff", OLDEST, "dynamic.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 2
    assert "no comparison was made" in result.stderr


# ── --output (§5.2) ──────────────────────────────────────────────────────────────────────


def test_output_writes_the_rendering_to_a_file_and_stdout_stays_clean(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra", "-o", "delta.txt")

    assert result.exit_code == 0
    assert result.stdout == ""
    written = (evolved_project / "delta.txt").read_text(encoding="utf-8")
    assert "bump class" in written and "+ node audit" in written


def test_an_unwritable_output_is_exit_2_with_no_fallback_to_stdout(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("diff", OLDEST, NEWEST, "--store", ".gebra", "-o", "no-such-dir/delta.txt")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "cannot write --output" in result.stderr


# ── Usage errors (§3.4, §4.3) ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        pytest.param(("diff",), "exactly two positional targets", id="no-sides"),
        pytest.param(("diff", "1.0.0.0"), "exactly two positional targets", id="one-side"),
        pytest.param(
            ("diff", "1.0.0.0", "1.1.1.0", "1.2.2.1"),
            "exactly two positional targets",
            id="three-sides",
        ),
        pytest.param(
            ("diff", "1.0.0.0", "1.1.1.0", "--strict"),
            "accepted by gebra verify only",
            id="strict-refused",
        ),
        pytest.param(
            ("diff", "1.0.0.0", "1.1.1.0", "--sidecar", "gebra.toml"),
            "--sidecar applies to an import-reference side, and exactly one",
            id="sidecar-with-zero-import-sides",
        ),
        pytest.param(
            ("diff", "pkg:one", "pkg:two", "--sidecar", "gebra.toml"),
            "this invocation has 2",
            id="sidecar-with-two-import-sides",
        ),
        pytest.param(
            ("diff", "1.0.0.0", "base.ir.yaml", "--call"),
            "neither side is one",
            id="call-with-zero-import-sides",
        ),
        pytest.param(
            ("diff", "1.0.0.0", "1.1.1.0", "--format", "json"),
            "unknown option '--format'",
            id="no-format-flag-oi3",
        ),
    ],
)
def test_usage_problems_are_refused_before_anything_resolves(
    run_cli: RunCli, evolved_project: Path, argv: tuple[str, ...], fragment: str
) -> None:
    result = run_cli(*argv)

    assert result.exit_code == 2
    assert fragment in result.stderr
    assert result.stdout == ""
