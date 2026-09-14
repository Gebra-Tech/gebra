"""``gebra diff`` — CLI-SPEC §4.3 and §3.2's ``diff`` row, through ``main()``.

The two acceptance sentences this card owes the diff verb are both pinned here: **the
output shows the S/F/E class** (a ``bump class`` line read off ``WorkflowDiff.bump_class``,
asserted per constructed pair), and **the deferred-P-12 marker is rendered honestly** —
*not checked* with its status on every outcome, with no ``safe``/``breaking`` labelling
anywhere in the captured output. Exit codes: ``0`` on a completed comparison whatever it
found (a stamp-only pair included, even under ``--exit-code``), ``1`` only under
``--exit-code`` when the sides differ in content, ``2`` when a side fails to resolve, a stored
snapshot fails its digest check, or the engine reports neither a delta nor a stamp move for
two differing digests — the coverage-defect residue, a build defect refused on stderr.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gebra.ir import write_ir
from gebra.ir.models import DynamicEdge, Node, WorkflowIR
from gebra.store import Snapshot, SnapshotStore
from tests.cli.conftest import RunCli
from tests.lineage.stores import STAGES, provenance
from tests.versioning.workflows import restamped

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


def test_an_ir_1_1_document_side_reaches_a_comparison(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """A ``dynamic``-bearing side compares (card SD-13, PD-059): the edge is rendered with its
    absent target spelled out rather than dropped or given an invented head, and a pair that
    differs only in the router's guard renders the persisting identity's moved guard. Until
    SD-13 the engine declined the document and the verb reported exit ``2``."""

    def dynamic(condition: str) -> WorkflowIR:
        return WorkflowIR(
            ir_version="1.1",
            entry="plan",
            finish="collect",
            state={"legs": "list[str]"},
            nodes=(Node(id="plan"), Node(id="collect")),
            edges=(DynamicEdge(kind="dynamic", **{"from": "plan"}, condition=condition),),
        )

    write_ir(dynamic("route"), evolved_project / "dynamic.ir.yaml")
    write_ir(dynamic("route_v2"), evolved_project / "dynamic-v2.ir.yaml")

    against_stored = run_cli("diff", OLDEST, "dynamic.ir.yaml", "--store", ".gebra")
    reguarded = run_cli("diff", "dynamic.ir.yaml", "dynamic-v2.ir.yaml", "--store", ".gebra")

    # The renderer wraps a long line at the terminal width, so the phrases are compared on
    # whitespace-normalized text — the words and their order are the claim, not the folding.
    assert against_stored.exit_code == 0, against_stored.stderr
    assert "+ edge plan -> (targets not statically known) [dynamic] guard route" in " ".join(
        against_stored.stdout.split()
    )
    assert re.search(r"bump class\s+S", against_stored.stdout)
    assert reguarded.exit_code == 0, reguarded.stderr
    # A dynamic pairing carries the guard alone: the kind has no target, and a "target …
    # (unchanged)" clause beside "targets not statically known" would read as a claim about
    # the runtime set (PD-059 close-out item 4).
    assert "~ edge plan [dynamic]: guard route -> route_v2" in " ".join(reguarded.stdout.split())
    assert "(unchanged)" not in reguarded.stdout
    assert re.search(r"bump class\s+S\n", reguarded.stdout)
    assert "no comparison was made" not in reguarded.stderr


# ── The stamp-only pair: named at exit 0, never a crash and never a difference (D7b) ──────


def test_a_pair_differing_in_the_stamp_alone_is_named_and_is_not_a_difference(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """PD-059 D7b as ratified, on the verb: two IR-document sides that differ in their
    ``ir_version`` stamp and in nothing else (an over-stamped twin, admitted by DEC-34) render one
    line naming both stamps and stating that no counter moves, at exit ``0`` — and ``--exit-code``
    stays ``0``, because no content differs. Until the close-out this pair crashed the verb (an
    assertion that the case was unreachable; CLI-SPEC §3.4's traceback, exit 2)."""
    write_ir(restamped(STAGES[0].build(), "1.1"), evolved_project / "stamped.ir.yaml")

    plain = run_cli("diff", "base.ir.yaml", "stamped.ir.yaml", "--store", ".gebra")
    signalled = run_cli(
        "diff", "base.ir.yaml", "stamped.ir.yaml", "--store", ".gebra", "--exit-code"
    )
    reversed_pair = run_cli("diff", "stamped.ir.yaml", "base.ir.yaml", "--store", ".gebra")
    reversed_signalled = run_cli(
        "diff", "stamped.ir.yaml", "base.ir.yaml", "--store", ".gebra", "--exit-code"
    )

    assert plain.exit_code == 0, plain.stderr
    assert plain.stderr == ""
    assert "only the ir_version stamp moved: 1.0 -> 1.1" in " ".join(plain.stdout.split())
    assert "no content differs and no V.S.F.E counter moves" in " ".join(plain.stdout.split())
    assert re.search(r"bump class\s+none — the counters do not move", plain.stdout)
    assert "Traceback" not in plain.stderr and "crash" not in plain.stderr
    assert signalled.exit_code == 0, signalled.stderr
    assert reversed_pair.exit_code == 0, reversed_pair.stderr
    assert "only the ir_version stamp moved: 1.1 -> 1.0" in " ".join(reversed_pair.stdout.split())
    assert reversed_signalled.exit_code == 0, reversed_signalled.stderr


def test_a_diff_with_neither_delta_nor_stamp_move_is_a_build_defect_at_exit_2(
    run_cli: RunCli, evolved_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The residue the assertion used to guard — digests differ, no delta, equal stamps — is a
    shape the engine never produces (its three slices cover every canonical member but the
    stamp), so it is constructed and fed to the verb in the engine's place. Were it ever to
    arise, a comparison over it would be a known build defect: CLI-SPEC §3.4 makes that exit
    ``2`` with the fact on stderr, never a clean run — with or without ``--exit-code``, and
    never rendered as a diff or as a stamp move (PD-059, second-pass ratification)."""
    import gebra.cli.diff as verb
    from gebra.diff import DiffAnchor, TopologyDiff, WorkflowDiff

    residue = WorkflowDiff(
        topology=TopologyDiff(
            before=DiffAnchor("sha256:" + "a" * 64, ir_version="1.0"),
            after=DiffAnchor("sha256:" + "b" * 64, ir_version="1.0"),
        )
    )
    monkeypatch.setattr(verb, "workflow_diff", lambda before, after: residue)

    plain = run_cli("diff", "base.ir.yaml", "final.ir.yaml", "--store", ".gebra")
    signalled = run_cli("diff", "base.ir.yaml", "final.ir.yaml", "--store", ".gebra", "--exit-code")

    for result in (plain, signalled):
        assert result.exit_code == 2
        assert result.stdout == ""
        assert "coverage defect in the diff engine, not a workflow change" in result.stderr
        assert "please report it" in result.stderr
        assert "sha256:" + "a" * 64 in result.stderr and "sha256:" + "b" * 64 in result.stderr
        assert "only the ir_version stamp moved" not in result.stderr
        assert "Traceback" not in result.stderr


def test_a_stored_pair_differing_in_the_stamp_alone_is_named_too(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """The same answer through ``gebra.lineage.compare``: a store holding a version and its
    over-stamped twin (written through the store, since the recorder refuses to record the pair)
    diffs to the stamp line at exit ``0``."""
    store = SnapshotStore(evolved_project / ".gebra")
    store.write(
        Snapshot.of(
            restamped(STAGES[0].build(), "1.1"),
            version="9.0.0.0",
            extracted_from=provenance("tests.cli.test_diff_verb", "2026-09-07T09:00:00Z"),
        )
    )

    result = run_cli("diff", OLDEST, "9.0.0.0", "--store", ".gebra")

    assert result.exit_code == 0, result.stderr
    assert re.search(rf"before\s+{re.escape(OLDEST)}\s+sha256:", result.stdout)
    assert re.search(r"after\s+9\.0\.0\.0\s+sha256:", result.stdout)
    assert "only the ir_version stamp moved: 1.0 -> 1.1" in " ".join(result.stdout.split())
    assert "topology" not in result.stdout


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
