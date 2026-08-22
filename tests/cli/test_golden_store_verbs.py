"""Golden coverage for the three store-facing verbs — CLI-05's first acceptance box.

Each subcommand is captured against a **prepared store** and byte-compared with a
committed golden, through ``main()`` — the same discipline as ``tests/cli/test_golden.py``,
with the same single normalization (``tool.version``, reachable only in the snapshot
refusal's rendered report). The stores are functions of their fixtures alone: the corpus
documents' digests are deterministic, the evolved store's labels are engine-derived and its
timestamps fixed, and every path in an invocation is a bare relative name under a per-test
working directory. The snapshot verb's own outputs carry no timestamp, so recording *now*
still renders byte-stably.

The goldens double as the §5.2 stream record: stdout is compared alone, and stderr is
asserted beside it — empty where the run had nothing to say, and exactly the diagnostic
family where it did.

Regeneration is the suite-wide deliberate act::

    GEBRA_REGENERATE_GOLDENS=1 .venv/bin/python -m pytest tests/cli -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import RunCli
from tests.cli.goldens import compare_golden


@pytest.fixture
def awkward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from tests.lineage.stores import awkward_store

    monkeypatch.chdir(tmp_path)
    awkward_store(tmp_path)
    return tmp_path


# ── gebra snapshot, against a store it prepares and then re-reads ────────────────────────


def test_golden_snapshot_first_record(run_cli: RunCli, project_dir: Path) -> None:
    result = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/snapshot-first.txt", result.stdout)


def test_golden_snapshot_recorded_over_previous(run_cli: RunCli, project_dir: Path) -> None:
    run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")
    result = run_cli("snapshot", "noted.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/snapshot-recorded.txt", result.stdout)


def test_golden_snapshot_unchanged(run_cli: RunCli, project_dir: Path) -> None:
    run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")
    result = run_cli("snapshot", "pass.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/snapshot-unchanged.txt", result.stdout)


def test_golden_snapshot_refused_on_fatal(run_cli: RunCli, project_dir: Path) -> None:
    """The §0.2 refusal: the rendered report on stdout (the golden), the refusal on
    stderr, and exit ``1``."""
    result = run_cli("snapshot", "fail.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 1
    assert "not recorded" in result.stderr
    compare_golden("store/snapshot-refused.txt", result.stdout)


# ── gebra diff, against the prepared five-version store ──────────────────────────────────


def test_golden_diff_stored_pair(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("diff", "1.0.0.0", "1.2.2.1", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/diff-stored-pair.txt", result.stdout)


def test_golden_diff_mixed_sides(run_cli: RunCli, evolved_project: Path) -> None:
    """A stored label against a working document — §4.3's mixed invocation."""
    result = run_cli("diff", "1.1.2.0", "final.ir.yaml", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/diff-mixed.txt", result.stdout)


def test_golden_diff_identical_pair(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("diff", "1.2.2.1", "1.2.2.1", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/diff-identical.txt", result.stdout)


# ── gebra history, against the prepared, the awkward, and the absent store ───────────────


def test_golden_history_full(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/history-full.txt", result.stdout)


def test_golden_history_window(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli(
        "history", "--store", ".gebra", "--since", "1.1.1.0", "--until", "1.1.2.1", "--limit", "2"
    )

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/history-window.txt", result.stdout)


def test_golden_history_reverse(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--reverse")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/history-reverse.txt", result.stdout)


def test_golden_history_awkward(run_cli: RunCli, awkward_project: Path) -> None:
    """The full n/a vocabulary on one screen: a bare label, a backwards step, a V step."""
    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/history-awkward.txt", result.stdout)


def test_golden_history_empty(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/history-empty.txt", result.stdout)


def test_golden_history_json(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--format", "json")

    assert result.exit_code == 0 and result.stderr == ""
    compare_golden("store/history.json", result.stdout)


# ── Styling is the only difference between the styled and plain renderings (§5.1) ────────


def test_the_styled_diff_equals_the_golden_after_escape_stripping(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """PD-031's degradation rule held as an equality on this card's richest surface."""
    import re

    plain = run_cli("diff", "1.0.0.0", "1.2.2.1", "--store", ".gebra")
    styled = run_cli("diff", "1.0.0.0", "1.2.2.1", "--store", ".gebra", "--color")

    assert "\x1b[" in styled.stdout  # forced styling actually styled something
    stripped = re.sub(r"\x1b\[[0-9;]*m", "", styled.stdout)
    assert stripped == plain.stdout
