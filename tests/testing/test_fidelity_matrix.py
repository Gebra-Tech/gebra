"""``docs/governance/FIDELITY-MATRIX.md`` held to the corpus it describes.

The fidelity matrix is D-10's deliverable 4 and WA-04's ledger: every disagreement between a
validator and a vendored fixture is an entry there, carrying its route — fix the validator, or
request a fixture revision through R-05 sign-off. A prose ledger rots the day someone forgets
to update it, so ``python tools/golden_harness.py`` runs the harness and cross-checks the
file against what it observed, in **both** directions. This module is that gate under test:
green on the repository as it stands, and a seeded violation of each rule proves the gate is
armed rather than vacuous.

Both directions matter, and for different reasons. An unrecorded deviation is the WA-04
failure the ledger exists to prevent. A *stale* entry — an open row whose deviation no longer
reproduces — is the quieter one: it makes the matrix overstate the outstanding work, and it is
exactly the state TE-04's "zero unexplained entries" has to be judged against.

WA-07: nothing here executes a workflow node, calls a model, or opens a network connection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gebra.testing.harness import PROJECTION_RULES, run_corpus
from gebra.verify import PROPERTY_REGISTRY
from tests.conftest import FIXTURES_DIR
from tools.golden_harness import (
    GateReport,
    MatrixError,
    check,
    format_deviations,
    format_run,
    format_summary,
    main,
    parse_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "governance" / "FIDELITY-MATRIX.md"

#: A live deviation and its recorded entry — the pair every seeded test perturbs.
#: (Was mixed/10's P-04 share until DEC-23 closed FM-003; FM-006 is the open `unmodelled`
#: row that now anchors the seeds.)
RECORDED = "mixed/05-evolution-drops-witness-and-state-field::dataflow-completeness"

#: An obligation that is *not* a deviation, for the stale-entry and reopen seeds.
NOT_A_DEVIATION = "determinism-replay/positive-02-pure-fare-normalizer::determinism-replay"


@pytest.fixture(scope="module")
def report() -> GateReport:
    """One gate run against the repository's own matrix."""
    return check(FIXTURES_DIR, MATRIX)


def _seeded(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of the matrix with one substring replaced — the seeded-violation harness."""
    text = MATRIX.read_text(encoding="utf-8")
    assert old in text, f"the seed text {old!r} is not in the matrix; the test is stale"
    seeded = tmp_path / "FIDELITY-MATRIX.md"
    seeded.write_text(text.replace(old, new, 1), encoding="utf-8")
    return seeded


# ── The gate is green as the repository stands ───────────────────────────────────────────


def test_the_gate_is_green(report: GateReport) -> None:
    assert report.ok, "\n".join(report.violations)


def test_every_live_deviation_has_an_open_entry(report: GateReport) -> None:
    """The direction WA-04 is about: a disagreement is a logged decision, never a quiet edit."""
    live = {outcome.obligation.id for outcome in report.run.deviations}
    recorded = {row.cells[1].strip("`") for row in report.matrix.open_entries}
    assert live == recorded


def test_no_open_entry_is_stale(report: GateReport) -> None:
    """And the other direction: the matrix never overstates what is outstanding."""
    live = {outcome.obligation.id for outcome in report.run.deviations}
    for row in report.matrix.open_entries:
        assert row.cells[1].strip("`") in live, row.cells


def test_every_projection_rule_is_logged(report: GateReport) -> None:
    """PD-006 R3.2 requires each mixed-fixture projection rule be logged in the matrix."""
    logged = {row.cells[0].strip("`"): row.cells[1].strip("`") for row in report.matrix.rules}
    assert logged == {rule.id: rule.kind for rule in PROJECTION_RULES}


def test_the_matrix_covers_every_catalog_property(report: GateReport) -> None:
    """D-10 deliverable 4 asks for completeness over every property *with a fixture*.

    All thirteen carry a row anyway — the four with no fixture say so — which is a superset of
    what the deliverable requires and keeps a future fixture from landing unrepresented.
    """
    recorded = {row.cells[1].strip("`") for row in report.matrix.properties}
    assert recorded == set(PROPERTY_REGISTRY)


def test_every_entry_id_is_unique_and_well_formed(report: GateReport) -> None:
    ids = [
        row.cells[0].strip("`")
        for row in (*report.matrix.open_entries, *report.matrix.closed_entries)
    ]
    assert len(ids) == len(set(ids))
    assert all(entry.startswith("FM-") and entry[3:].isdigit() for entry in ids), ids


def test_every_open_entry_carries_a_route_and_a_disposition(report: GateReport) -> None:
    """An entry that names no route is a note, not a decision (WA-04).

    The three routes are §6's own enumeration; a fourth value here would mean the file and its
    instructions had drifted apart.
    """
    routes = {"R-05 fixture revision", "fix the validator", "no change (recorded)"}
    for row in report.matrix.open_entries:
        assert row.cells[3] in routes, row.cells
        assert len(row.cells[4]) > 80, f"{row.cells[0]}: the disposition is a stub"


# ── The gate is armed: one seeded violation per rule ─────────────────────────────────────


def test_an_unrecorded_deviation_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, f"`{RECORDED}`", "`mixed/10-nothing::graph-well-formed`")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any(RECORDED in violation and "no entry" in violation for violation in result.violations)


def test_a_stale_open_entry_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, f"`{RECORDED}`", f"`{NOT_A_DEVIATION}`")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("no longer reproduces" in violation for violation in result.violations)


def test_a_wrong_recorded_status_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, f"`{RECORDED}` | `unmodelled`", f"`{RECORDED}` | `mismatched`")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("is now 'unmodelled'" in violation for violation in result.violations)


def test_a_reopened_closed_entry_fails_the_gate(tmp_path: Path) -> None:
    """A closed entry that starts deviating again is a new §3 row, never a quiet reopen."""
    closed = (
        "determinism-replay/negative-01-seedless-deterministic-llm-classifier::determinism-replay"
    )
    seeded = _seeded(tmp_path, f"`{closed}`", f"`{RECORDED}`")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("deviating again" in violation for violation in result.violations)


def test_a_missing_projection_rule_row_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, "| `PR-3` | `cross-property-advisory` |", "| `PR-3x` | `x` |")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("PR-3 is implemented" in violation for violation in result.violations)
    assert any("PR-3x has a row" in violation for violation in result.violations)


def test_a_wrong_projection_rule_kind_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, "| `PR-2` | `cross-property-co-failure` |", "| `PR-2` | `report` |")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("recorded as producing 'report'" in violation for violation in result.violations)


def test_a_wrong_property_count_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(
        tmp_path,
        "| P-08 | `determinism-replay` | wedge | 6 | 6 |",
        "| P-08 | `determinism-replay` | wedge | 7 | 6 |",
    )
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("records 7 obligation(s); the run has 6" in v for v in result.violations)


def test_a_missing_property_row_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, "| P-11 | `join-key-soundness` |", "| P-11 | `join-key-unsound` |")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("join-key-soundness has no row" in violation for violation in result.violations)
    assert any("'join-key-unsound' is not a catalog slug" in v for v in result.violations)


def test_a_wired_property_reporting_pending_fails_the_gate() -> None:
    """The floor under ``matched``: a registered validator's obligations are never skipped.

    Without it the gate would stay green if a validator were dropped from the registry — its
    obligations would fall back from ``matched`` to ``pending-validator``, a status the gate
    accepts whenever the slug is genuinely unwired (zero live occurrences since VAL-07
    completed the wedge). Seeded directly, because the corpus cannot produce the state:
    `run_obligation` only reports ``pending-validator`` when `validator_for` returns
    ``None``.
    """
    from gebra.testing.harness import CorpusRun, Obligation, Outcome
    from tools.golden_harness import _check_wiring

    seeded = GateReport(
        run=CorpusRun(
            (
                Outcome(
                    Obligation(
                        "determinism-replay/positive-01-x.yaml", "determinism-replay", "report"
                    ),
                    "pending-validator",
                    "seeded",
                ),
            )
        ),
        matrix=parse_matrix(MATRIX),
    )
    _check_wiring(seeded)
    assert not seeded.ok
    assert "while a validator is registered" in seeded.violations[0]


def test_the_wiring_floor_is_silent_on_the_real_run(report: GateReport) -> None:
    """The vendored run has no `pending-validator` outcome left to trip the floor on.

    The wedge five are all wired (VAL-07 landed the last, P-02), so the floor's live half is
    the seeded test above; what the real run contributes is the absence — a pending outcome
    reappearing here would mean a shipped validator fell out of the registry.
    """
    from gebra.verify import WEDGE_SLUGS, validator_for

    pending = [o for o in report.run.outcomes if o.status == "pending-validator"]
    assert pending == []
    assert all(validator_for(slug) is not None for slug in WEDGE_SLUGS)


def test_a_duplicate_entry_id_fails_the_gate(tmp_path: Path) -> None:
    seeded = _seeded(tmp_path, "| `FM-006` |", "| `FM-005` |")
    result = check(FIXTURES_DIR, seeded)
    assert not result.ok
    assert any("appears twice" in violation for violation in result.violations)


# ── Parsing ──────────────────────────────────────────────────────────────────────────────


def test_the_parser_finds_the_four_tables() -> None:
    matrix = parse_matrix(MATRIX)
    assert len(matrix.rules) == len(PROJECTION_RULES)
    assert matrix.open_entries and matrix.closed_entries
    assert len(matrix.properties) == len(PROPERTY_REGISTRY)


def test_the_parser_ignores_prose_tables() -> None:
    """§1's five-status table is prose, not a checked table — it must not be parsed as one."""
    matrix = parse_matrix(MATRIX)
    parsed = {row.cells[0] for row in (*matrix.rules, *matrix.open_entries, *matrix.properties)}
    assert "`matched`" not in parsed


def test_a_missing_matrix_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MatrixError, match="cannot be read"):
        parse_matrix(tmp_path / "absent.md")


def test_a_matrix_without_a_required_table_is_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "FIDELITY-MATRIX.md"
    empty.write_text("# empty\n\n## 2. Projection rules\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="section 2 carries no projection rules table"):
        parse_matrix(empty)


# ── The CLI ──────────────────────────────────────────────────────────────────────────────


def test_the_gate_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--corpus", str(FIXTURES_DIR), "--matrix", str(MATRIX)]) == 0
    out = capsys.readouterr().out
    assert "78 obligation(s) over 60 fixture(s)" in out
    assert "FIDELITY-MATRIX.md: OK" in out


def test_the_gate_command_exits_one_on_a_seeded_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seeded = _seeded(tmp_path, f"`{RECORDED}`", f"`{NOT_A_DEVIATION}`")
    assert main(["--corpus", str(FIXTURES_DIR), "--matrix", str(seeded)]) == 1
    assert "no longer reproduces" in capsys.readouterr().err


def test_the_gate_command_exits_one_on_an_unreadable_matrix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--matrix", str(tmp_path / "absent.md")]) == 1
    assert "cannot be read" in capsys.readouterr().err


def test_the_report_lists_every_obligation(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--corpus", str(FIXTURES_DIR), "--matrix", str(MATRIX), "--report"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert sum(1 for line in lines if "::" in line) == 78


def test_the_deviation_listing_carries_the_detail(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--corpus", str(FIXTURES_DIR), "--matrix", str(MATRIX), "--deviations"]) == 0
    out = capsys.readouterr().out
    assert "[unmodelled]" in out
    assert "[mismatched]" in out


def test_the_summary_names_every_status() -> None:
    run = run_corpus(FIXTURES_DIR)
    summary = format_summary(check(FIXTURES_DIR, MATRIX))
    for status in run.counts:
        assert status in summary


def test_the_formatters_hold_up_on_an_empty_run() -> None:
    """Rendering must not assume a non-empty corpus — ``--corpus`` can name anything."""
    from gebra.testing.harness import CorpusRun

    assert format_run(CorpusRun(())) == ""
    assert format_deviations(CorpusRun(())) == "  (none)"
