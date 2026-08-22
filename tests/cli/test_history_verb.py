"""``gebra history`` — CLI-SPEC §4.5 and §3.2's ``history`` row, through ``main()``.

PD-033's table is pinned shape by shape: oldest first, one row per ``LineageEntry``, the
six columns, per-row step summaries sourced only from ``LineageStep`` with an explicit
``n/a`` and a distinct decreased marker, the window statement however small the window,
and never a full structural diff inline. ``--format json`` is asserted **equal** to
``dump_lineage`` over the same engine listing — the projection unchanged, byte for byte.
Exit codes: ``0`` on every listing (an absent store included), ``1`` never, ``2`` for a
damaged index or a window anchor the history does not hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gebra.lineage import dump_lineage, lineage
from gebra.store import SnapshotStore
from tests.cli.conftest import RunCli

LABELS = ("1.0.0.0", "1.1.1.0", "1.1.2.0", "1.1.2.1", "1.2.2.1")


def table_rows(stdout: str) -> list[str]:
    """The table's entry rows — everything after the column-header line."""
    lines = stdout.splitlines()
    header = next(index for index, line in enumerate(lines) if "version  graph_version" in line)
    return lines[header + 1 :]


@pytest.fixture
def awkward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The lineage suite's awkward store: a bare label, a backwards step, a V step."""
    from tests.lineage.stores import awkward_store

    monkeypatch.chdir(tmp_path)
    awkward_store(tmp_path)
    return tmp_path


# ── The listing (§3.2 exit 0, PD-033's table) ────────────────────────────────────────────


def test_the_whole_history_lists_oldest_first_with_the_current_marked(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 0
    assert result.stderr == ""
    assert "history of .gebra — 5 versions; current 1.2.2.1" in result.stdout
    rows = table_rows(result.stdout)
    assert [label for label in LABELS for line in rows if f" {label} " in line] == list(LABELS)
    current_row = next(line for line in rows if " 1.2.2.1 " in line)
    assert current_row.startswith("* ")


def test_the_columns_are_pd_033s_six(run_cli: RunCli, evolved_project: Path) -> None:
    """Index, version, digest-as-a-prefix, created-at, the current marker, and the step."""
    result = run_cli("history", "--store", ".gebra")

    assert "#  version  graph_version" in result.stdout
    assert "created" in result.stdout and "step" in result.stdout
    assert "sha256:" in result.stdout and "..." in result.stdout  # a prefix that reads as one
    assert "2026-08-04T09:00:00Z" in result.stdout  # the store's own timestamp spelling


def test_the_oldest_row_states_an_explicit_n_a(run_cli: RunCli, evolved_project: Path) -> None:
    """PD-033: never a blank cell that could be read as "no change"."""
    result = run_cli("history", "--store", ".gebra")

    oldest_row = next(line for line in result.stdout.splitlines() if "1.0.0.0" in line)
    assert "n/a (oldest version)" in oldest_row


def test_the_step_summaries_read_off_the_labels(run_cli: RunCli, evolved_project: Path) -> None:
    """Each row's step is the label-recorded movement plus the content bit, and no row
    renders a full structural diff (PD-033: that answer is ``gebra diff``'s)."""
    result = run_cli("history", "--store", ".gebra")

    by_label = {
        label: next(line for line in table_rows(result.stdout) if f" {label} " in line)
        for label in LABELS[1:]
    }
    assert "+S +F, content changed" in by_label["1.1.1.0"]
    assert "+F, content changed" in by_label["1.1.2.0"]
    assert "+E, content changed" in by_label["1.1.2.1"]
    assert "+S, content changed" in by_label["1.2.2.1"]
    for line in result.stdout.splitlines():  # no delta vocabulary anywhere in a listing
        assert "+ node" not in line and "- node" not in line and "+ key" not in line


def test_an_awkward_store_lists_totally(run_cli: RunCli, awkward_project: Path) -> None:
    """The store's label floor is path-safety, not the V.S.F.E grammar: a bare label, a
    backwards step and a V step all list, each stated distinctly."""
    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    backwards = next(line for line in lines if " 1.1.0.0 " in line)
    assert "-S, content changed" in backwards  # the distinct decreased marker
    draft = next(line for line in lines if " draft " in line)
    assert "n/a (label not V.S.F.E)" in draft  # non-comparable, explicitly
    revived = next(line for line in lines if " 2.0.0.0 " in line)
    assert "n/a (label not V.S.F.E)" in revived  # its predecessor is the bare label
    v_step = next(line for line in lines if " 3.0.0.0 " in line)
    assert "+V" in v_step and "content changed" in v_step


def test_an_absent_store_lists_as_empty_and_exits_0(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2.5/§3.2: a store that does not exist reads as an empty one."""
    monkeypatch.chdir(tmp_path)
    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 0
    assert "the store holds no versions" in result.stdout
    assert not (tmp_path / ".gebra").exists()  # listing created nothing


# ── Windows (§4.5: a window states that it is one) ───────────────────────────────────────


def test_a_window_names_what_it_dropped(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--since", "1.1.1.0", "--until", "1.1.2.1")

    assert result.exit_code == 0
    assert "showing 3 of 5 (1 omitted before, 1 after)" in result.stdout
    rows = table_rows(result.stdout)
    assert len(rows) == 3
    assert not any(" 1.0.0.0 " in row or " 1.2.2.1 " in row for row in rows)


def test_a_windowed_first_row_keeps_its_absolute_index_and_true_step(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """The engine's absolute indices and store-relative steps survive presentation."""
    result = run_cli("history", "--store", ".gebra", "--limit", "2")

    rows = table_rows(result.stdout)
    assert len(rows) == 2
    assert rows[0].lstrip("* ").startswith("3")  # absolute index, not 0
    assert "+E, content changed" in rows[0]  # the step to it from the row the page dropped


def test_limit_0_is_a_legal_empty_window(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--limit", "0")

    assert result.exit_code == 0
    assert "showing 0 of 5 (5 omitted before, 0 after)" in result.stdout


def test_reverse_is_display_only(run_cli: RunCli, evolved_project: Path) -> None:
    """PD-033: newest-first display is a presentation-layer reversal; the statement says
    so and the machine projection is untouched by it."""
    forward = run_cli("history", "--store", ".gebra")
    reversed_ = run_cli("history", "--store", ".gebra", "--reverse")

    assert "newest first" in reversed_.stdout
    assert reversed_.stdout.index("1.2.2.1") < reversed_.stdout.index("1.0.0.0")
    assert sorted(forward.stdout.splitlines()[2:]) == sorted(reversed_.stdout.splitlines()[2:])


# ── --format json (§4.5: dump_lineage, unchanged) ────────────────────────────────────────


def test_json_is_dump_lineage_verbatim(run_cli: RunCli, evolved_project: Path) -> None:
    """The §4.5 sentence held as an equality: the bytes on stdout are ``dump_lineage``
    over the same engine listing, trailing newline included, ``lineage_version`` stamped."""
    result = run_cli("history", "--store", ".gebra", "--format", "json")

    expected = dump_lineage(lineage(SnapshotStore(evolved_project / ".gebra")))
    assert result.exit_code == 0
    assert result.stdout == expected
    assert json.loads(result.stdout)["lineage_version"] == "1.0"


def test_json_carries_the_window_arguments_through(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--limit", "2", "--format", "json")

    expected = dump_lineage(lineage(SnapshotStore(evolved_project / ".gebra"), limit=2))
    assert result.stdout == expected
    document = json.loads(result.stdout)
    assert document["omitted_before"] == 3 and document["total"] == 5


def test_output_writes_the_listing_to_a_file(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--format", "json", "-o", "lineage.json")

    assert result.exit_code == 0
    assert result.stdout == ""
    written = (evolved_project / "lineage.json").read_text(encoding="utf-8")
    assert written == dump_lineage(lineage(SnapshotStore(evolved_project / ".gebra")))


# ── Exit 2 — the engine's refusals, reported (§4.5) ──────────────────────────────────────


def test_an_unknown_since_label_is_exit_2_with_a_suggestion(
    run_cli: RunCli, evolved_project: Path
) -> None:
    result = run_cli("history", "--store", ".gebra", "--since", "1.1.1.1")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "the history was not listed" in result.stderr
    assert "Did you mean" in result.stderr


def test_an_inverted_window_is_the_engines_refusal(run_cli: RunCli, evolved_project: Path) -> None:
    result = run_cli("history", "--store", ".gebra", "--since", "1.2.2.1", "--until", "1.0.0.0")

    assert result.exit_code == 2
    assert "empty by construction" in result.stderr


def test_a_negative_limit_reaches_the_engines_own_refusal(
    run_cli: RunCli, evolved_project: Path
) -> None:
    """§4.5 files negativity under the engine's refusals, not under usage: ``-1`` parses
    as an integer here and is refused there."""
    result = run_cli("history", "--store", ".gebra", "--limit", "-1")

    assert result.exit_code == 2
    assert "cannot be -1" in result.stderr


def test_a_damaged_index_is_exit_2(
    run_cli: RunCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gebra").mkdir()
    (tmp_path / ".gebra" / "meta.yaml").write_text("history: [broken\n", encoding="utf-8")

    result = run_cli("history", "--store", ".gebra")

    assert result.exit_code == 2
    assert "the history was not listed" in result.stderr


# ── Usage errors (§3.4, §4.5) ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        pytest.param(("history", "1.0.0.0"), "history takes no TARGET", id="a-target"),
        pytest.param(
            ("history", "--format", "sarif"),
            "SARIF is a findings format and a history has no findings",
            id="no-sarif",
        ),
        pytest.param(("history", "--format", "jsn"), "Did you mean json", id="format-suggestion"),
        pytest.param(("history", "--limit", "many"), "is not an integer", id="limit-shape"),
        pytest.param(("history", "--strict"), "accepted by gebra verify only", id="strict-refused"),
    ],
)
def test_usage_problems_are_refused(
    run_cli: RunCli, evolved_project: Path, argv: tuple[str, ...], fragment: str
) -> None:
    result = run_cli(*argv)

    assert result.exit_code == 2
    assert fragment in result.stderr
    assert result.stdout == ""
