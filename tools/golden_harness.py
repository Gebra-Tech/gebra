"""Golden harness gate — run the corpus, and hold ``FIDELITY-MATRIX.md`` to what it says.

Two jobs, one command.

**Run the corpus.** Every vendored fixture becomes one obligation per property it exercises
(:mod:`gebra.testing.harness`), each obligation is compared against the validator that owns
it as PROPERTY-CATALOG-SPEC §0.3 model equality, and every outcome is counted:
``matched``, the two structured skips (``pending-validator`` for a wedge validator whose card
has not landed, ``deferred-to-phase-1`` for the eight properties SOW §8 puts outside Phase 0),
and the two deviation statuses. PD-006 R3.3 asks that the skips be "surfaced in the run report
and counted, never a silent pass"; ``--report`` is that report.

**Hold the matrix to the run.** ``docs/governance/FIDELITY-MATRIX.md`` is the WA-04 decision
log: every disagreement between a validator and a fixture is an entry there, with its route —
fix the validator, or request a fixture revision through R-05. This gate cross-checks the
file against the live run in *both* directions, which is what keeps it a log rather than a
snapshot: a deviation with no open entry fails, and an open entry that no longer reproduces
fails too. A resolved deviation therefore cannot linger as an open row, and a new one cannot
land unrecorded. The cross-check is not optional — there is no flag that skips it; ``--report``
and ``--deviations`` only add listings to the same run.

**What this gate does not carry.** It has a floor under ``matched`` (:func:`_check_wiring`:
a registered validator's obligations may never read ``pending-validator``) but no floor on
*how many* validators are registered — that is `PROPERTY_REGISTRY`'s own business, and the
pinned green set lives in ``tests/testing/test_golden_harness.py``, which is where a lost
assertion fails.

Deliberately a standalone gate rather than only a pytest module, on the same reasoning as
``tools/corpus_lint.py``: WA-04's proposal flow needs to run the harness against a *candidate*
corpus (``--corpus DIR``) before anything is vendored, and the per-obligation report is what
an implementer reads while burning a deviation down. The parametrized per-fixture assertions
live in ``tests/testing/test_golden_harness.py`` and share this module's harness core.

WA-07: nothing here executes a workflow node, calls a model, or opens a network connection.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from gebra.testing.harness import (
    PROJECTION_RULES,
    STATUS_ORDER,
    CorpusRun,
    run_corpus,
)
from gebra.verify import PROPERTY_REGISTRY, validator_for

#: The matrix section each parsed table lives under, by leading section number.
_RULES_SECTION: Final = "2"
_OPEN_SECTION: Final = "3"
_CLOSED_SECTION: Final = "4"
_PROPERTY_SECTION: Final = "5"

_HEADING = re.compile(r"^##\s+(\d+)\.")
_SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")
_CODE = re.compile(r"^`(?P<value>[^`]+)`$")


class MatrixError(RuntimeError):
    """The fidelity matrix itself is unreadable — missing, or missing a required table."""


@dataclass(frozen=True)
class MatrixRow:
    """One parsed table row: its cells, and the line it came from (for diagnostics)."""

    cells: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class Matrix:
    """The machine-checked tables of ``FIDELITY-MATRIX.md``."""

    path: Path
    rules: tuple[MatrixRow, ...]
    open_entries: tuple[MatrixRow, ...]
    closed_entries: tuple[MatrixRow, ...]
    properties: tuple[MatrixRow, ...]


@dataclass
class GateReport:
    """What one gate run found."""

    run: CorpusRun
    matrix: Matrix
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


# ── Reading the matrix ───────────────────────────────────────────────────────────────────


def parse_matrix(path: Path) -> Matrix:
    """Read the four machine-checked tables out of the fidelity matrix.

    Tables are located by the section they sit under, not by position, so prose may be added
    or reordered freely. A row is any pipe-delimited line under a numbered section that is
    neither the header nor the ``|---|`` separator; a table's header row is recognised by
    being the first row before a separator.

    Raises:
        MatrixError: if the file is missing or a required section holds no table.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MatrixError(f"{path} cannot be read: {exc}") from exc

    sections: dict[str, list[MatrixRow]] = {}
    current: str | None = None
    pending_header = False
    for number, raw in enumerate(text.splitlines(), start=1):
        heading = _HEADING.match(raw)
        if heading:
            current = heading.group(1)
            pending_header = False
            continue
        line = raw.strip()
        if not line.startswith("|") or current is None:
            pending_header = False
            continue
        if _SEPARATOR.match(line):
            pending_header = True
            continue
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if not pending_header:
            continue  # the header row, or a line before this table's separator
        sections.setdefault(current, []).append(MatrixRow(cells, number))

    for section, name in (
        (_RULES_SECTION, "projection rules"),
        (_OPEN_SECTION, "open deviations"),
        (_PROPERTY_SECTION, "per-property fidelity status"),
    ):
        if not sections.get(section):
            raise MatrixError(f"{path}: section {section} carries no {name} table")

    return Matrix(
        path=path,
        rules=tuple(sections.get(_RULES_SECTION, ())),
        open_entries=tuple(sections.get(_OPEN_SECTION, ())),
        closed_entries=tuple(sections.get(_CLOSED_SECTION, ())),
        properties=tuple(sections.get(_PROPERTY_SECTION, ())),
    )


def open_obligations(matrix: Matrix) -> frozenset[str]:
    """Every obligation id §3 carries an open row for — "which deviations are routed".

    Public because a second gate turns on it: ``tools/corpus_green.py`` reads this to tell a
    *routed* criterion-2 shortfall from an unrecorded one, and that question deserves a
    contract rather than a reach into this module's cell-parsing internals.
    """
    return frozenset(_code(row.cells[1]) for row in matrix.open_entries)


def _code(cell: str) -> str:
    """A table cell's backticked value, or the cell itself when it carries none."""
    match = _CODE.match(cell)
    return match.group("value") if match else cell


# ── The cross-check ──────────────────────────────────────────────────────────────────────


def check(corpus: Path, matrix_path: Path) -> GateReport:
    """Run the corpus and cross-check the matrix against it.

    Raises:
        MatrixError: if the matrix cannot be read.
        gebra.testing.FixtureError: if a fixture cannot be loaded — that is the corpus
            lint's report to make, not this one's.
    """
    report = GateReport(run=run_corpus(corpus), matrix=parse_matrix(matrix_path))
    _check_wiring(report)
    _check_rules(report)
    _check_deviations(report)
    _check_properties(report)
    return report


def _check_wiring(report: GateReport) -> None:
    """A registered validator leaves none of its obligations ``pending-validator``.

    The floor under ``matched``. Without it the gate has an asymmetry worth naming: 38 of the
    78 obligations are ``pending-validator`` today and that is green, so a validator silently
    dropped from the registry would take its obligations from ``matched`` back to
    ``pending-validator`` and the gate would still exit 0 — a weakened check reading as a
    passing one. ``pending-validator`` is only ever honest when *nothing* is registered for
    the slug, and that is exactly what this asserts.
    """
    for outcome in report.run.outcomes:
        slug = outcome.obligation.property_slug
        if outcome.status == "pending-validator" and validator_for(slug) is not None:
            report.violations.append(
                f"{outcome.obligation.id} reports 'pending-validator' while a validator is "
                f"registered for {slug!r}; a wired property's obligations are compared, "
                f"never skipped"
            )


def _check_rules(report: GateReport) -> None:
    """§2 and :data:`PROJECTION_RULES` name the same ids, with the same obligation kinds."""
    declared = {rule.id: rule.kind for rule in PROJECTION_RULES}
    recorded = {_code(row.cells[0]): _code(row.cells[1]) for row in report.matrix.rules}
    for rule_id in sorted(set(declared) - set(recorded)):
        report.violations.append(
            f"§2 projection rules: {rule_id} is implemented in gebra.testing.harness but has "
            f"no row — every projection rule is logged in the matrix (PD-006 R3.2)"
        )
    for rule_id in sorted(set(recorded) - set(declared)):
        report.violations.append(
            f"§2 projection rules: {rule_id} has a row but no implementation in "
            f"gebra.testing.harness.PROJECTION_RULES"
        )
    for rule_id in sorted(set(declared) & set(recorded)):
        if declared[rule_id] != recorded[rule_id]:
            report.violations.append(
                f"§2 projection rules: {rule_id} is recorded as producing "
                f"{recorded[rule_id]!r} obligations, but produces {declared[rule_id]!r}"
            )


def _check_deviations(report: GateReport) -> None:
    """§3 and §4 against the live run, in both directions, with unique ids."""
    live = {outcome.obligation.id: outcome for outcome in report.run.deviations}
    recorded = {_code(row.cells[1]): row for row in report.matrix.open_entries}

    for obligation_id in sorted(set(live) - set(recorded)):
        outcome = live[obligation_id]
        report.violations.append(
            f"§3 open deviations: {obligation_id} is {outcome.status} and has no entry. "
            f"A deviation is a logged decision, never a quiet edit (WA-04) — add a row "
            f"naming its route. Observed: {outcome.detail}"
        )
    for obligation_id in sorted(set(recorded) - set(live)):
        report.violations.append(
            f"§3 open deviations: {_code(recorded[obligation_id].cells[0])} records "
            f"{obligation_id} as an open deviation, and it no longer reproduces. Move the "
            f"row to §4 with what resolved it."
        )
    for obligation_id in sorted(set(recorded) & set(live)):
        row_status = _code(recorded[obligation_id].cells[2])
        if row_status != live[obligation_id].status:
            report.violations.append(
                f"§3 open deviations: {_code(recorded[obligation_id].cells[0])} records "
                f"{obligation_id} as {row_status!r}; it is now "
                f"{live[obligation_id].status!r}"
            )

    for row in report.matrix.closed_entries:
        obligation_id = _code(row.cells[1])
        if obligation_id in live:
            report.violations.append(
                f"§4 closed deviations: {_code(row.cells[0])} is closed, but "
                f"{obligation_id} is deviating again ({live[obligation_id].status}). A "
                f"regression is a new §3 row, never a quiet reopen."
            )

    seen: dict[str, int] = {}
    for row in (*report.matrix.open_entries, *report.matrix.closed_entries):
        entry_id = _code(row.cells[0])
        if entry_id in seen:
            report.violations.append(
                f"fidelity-matrix entry {entry_id} appears twice (lines {seen[entry_id]} "
                f"and {row.line}); ids are never reused"
            )
        seen[entry_id] = row.line


def _check_properties(report: GateReport) -> None:
    """§5 lists all thirteen properties with the obligation and fixture counts of the run."""
    obligations: dict[str, int] = dict.fromkeys(PROPERTY_REGISTRY, 0)
    fixtures: dict[str, set[str]] = {slug: set() for slug in PROPERTY_REGISTRY}
    for outcome in report.run.outcomes:
        obligations[outcome.obligation.property_slug] += 1
        fixtures[outcome.obligation.property_slug].add(outcome.obligation.fixture_id)

    recorded = {_code(row.cells[1]): row for row in report.matrix.properties}
    declared = set(PROPERTY_REGISTRY)
    for missing in sorted(declared - set(recorded)):
        report.violations.append(
            f"§5 per-property status: {missing} has no row; the matrix is complete for every "
            f"catalog property (D-10 deliverable 4)"
        )
    for unknown in sorted(set(recorded) - declared):
        report.violations.append(f"§5 per-property status: {unknown!r} is not a catalog slug")
    for slug in sorted(declared & set(recorded)):
        row = recorded[slug]
        for index, observed, what in (
            (3, obligations[slug], "obligation"),
            (4, len(fixtures[slug]), "fixture"),
        ):
            if _code(row.cells[index]) != str(observed):
                report.violations.append(
                    f"§5 per-property status: {slug} records "
                    f"{_code(row.cells[index])} {what}(s); the run has {observed}"
                )


# ── Rendering ────────────────────────────────────────────────────────────────────────────


def format_run(run: CorpusRun) -> str:
    """The per-obligation table, grouped by fixture — the run report PD-006 R3.3 asks for."""
    lines: list[str] = []
    width = max((len(outcome.obligation.id) for outcome in run.outcomes), default=0)
    for fixture_id in run.fixture_ids:
        for outcome in run.for_fixture(fixture_id):
            lines.append(f"  {outcome.obligation.id:<{width}}  {outcome.status}")
    return "\n".join(lines)


def format_summary(report: GateReport) -> str:
    """The counted summary, then either the violations or the green line."""
    run = report.run
    counts = run.counts
    tally = "; ".join(f"{status} {counts[status]}" for status in STATUS_ORDER)
    head = (
        f"golden harness: {len(run.outcomes)} obligation(s) over {len(run.fixture_ids)} "
        f"fixture(s) — {tally}"
    )
    matrix = report.matrix.path.name
    if report.ok:
        return (
            f"{head}\n"
            f"{matrix}: OK — {len(report.matrix.open_entries)} open entr(y/ies), "
            f"{len(report.matrix.closed_entries)} closed, and the run reproduces exactly "
            f"the open set"
        )
    body = "\n".join(f"  - {violation}" for violation in report.violations)
    return f"{head}\n{matrix}: {len(report.violations)} violation(s)\n{body}\n\n{_REMEDIATION}"


def format_deviations(run: CorpusRun) -> str:
    """Every live deviation with its detail — what a new matrix row is written from."""
    if not run.deviations:
        return "  (none)"
    return "\n".join(
        f"  {outcome.obligation.id}\n    [{outcome.status}] {outcome.detail}"
        for outcome in run.deviations
    )


_REMEDIATION = (
    "A validator/fixture disagreement is a logged decision, never a quiet edit (WA-04): fix "
    "the validator, or route a fixture revision through R-05 sign-off recorded vault-first. "
    "Record it in docs/governance/FIDELITY-MATRIX.md §3 with its route, and move the row to "
    "§4 when it stops reproducing. The corpus at tests/fixtures/properties/ is never edited "
    "in this repository."
)


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def build_parser(default_corpus: Path, default_matrix: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="golden_harness.py",
        description=(
            "Run the golden harness over the property-fixture corpus and cross-check "
            "docs/governance/FIDELITY-MATRIX.md against what it observed."
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=default_corpus,
        help=f"corpus root to run (default: {default_corpus})",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=default_matrix,
        help=f"fidelity matrix to cross-check (default: {default_matrix})",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="list every obligation and its outcome, grouped by fixture",
    )
    parser.add_argument(
        "--deviations",
        action="store_true",
        help="list every live deviation with the detail a matrix row is written from",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    root = here.parent
    args = build_parser(
        root / "tests" / "fixtures" / "properties",
        root / "docs" / "governance" / "FIDELITY-MATRIX.md",
    ).parse_args(argv)

    try:
        report = check(args.corpus, args.matrix)
    except MatrixError as exc:
        print(f"golden harness: {exc}", file=sys.stderr)
        return 1

    stream = sys.stdout if report.ok else sys.stderr
    if args.report:
        print(format_run(report.run), file=stream)
    if args.deviations:
        print(format_deviations(report.run), file=stream)
    print(format_summary(report), file=stream)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
