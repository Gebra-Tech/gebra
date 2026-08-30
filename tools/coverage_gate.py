"""Coverage gate — the >80% floor on the three surfaces the briefs name (TE-12).

**The mandate is not this tool's to choose.** Brief D-10 Deliverable 8 and its DoD box ask
for "coverage > 80% across ``gebra.testing`` + plugin"; brief D-09 Deliverable 6 and its DoD
box ask the same of the validator module (``gebra.verify``); SOW §2's supporting-facts
paragraph carries both as one acceptance fact ("harness/plugin test coverage exceeds 80%").
This gate is those clauses executed: three named scopes, each measured on its own and each
required to be **strictly above 80.0%**. Strictly, because that is what the briefs wrote
(``> 80%``) — a scope sitting at exactly 80.00% fails here, which also satisfies the master
plan's ``>= 80%`` phrasing of the same gate.

**Why three scopes and not one project total.** A single number over the whole package can
sit comfortably above the floor while one of the three named surfaces rots underneath it —
which is the regression this card exists to block. Each scope is therefore gated on its own,
and the project total is printed as *context only*, never as a verdict. There is no
``fail_under`` in ``[tool.coverage.report]`` for the same reason: it is one number over
everything measured, and it compares with ``>=``.

**The measurement mode is load-bearing.** ``gebra.pytest_plugin`` is a ``pytest11`` entry
point: pytest imports it while loading plugins, which is *before* ``pytest-cov`` starts
measuring. Under ``pytest --cov`` its 161 module-level statements (imports, ``def`` lines,
decorators, constants) are therefore recorded as never executed, and the scope reads 18.9
points below its real exercise. Starting coverage before pytest — ``coverage run -m pytest``
— is what makes the plugin's number honest, so that is what CI runs and what this gate
insists on (see :func:`check_report`: a report whose plugin module shows no executed
module-level line is refused as a mis-measured run rather than failed as a coverage
regression).

**Exemption policy, in full.**

*Structural exclusions* live in one reviewed place, ``[tool.coverage.report] exclude_also``:
``if TYPE_CHECKING:``, ``raise NotImplementedError``, ``@overload``. They are class-wide
rules about code that cannot run, not per-case waivers.

*Per-line exclusions* — ``# pragma: no cover`` — are allowed inside a gated scope **only with
a stated reason on the same line**, exactly as the honest-claims lint treats its allow-pragma:
a bare pragma is a silent bypass of the floor and this gate rejects it. The pragma is
recognised by coverage.py's own default pattern (:data:`PRAGMA_PATTERN`), not by a literal
substring, so the spellings coverage.py honours — ``# pragma:no cover``, ``# PRAGMA: NO
COVER``, ``# pragma  no cover`` — are the spellings this rule polices; a policy that read
only one of them would be a bypass with an extra keystroke. Any separator introduces the
reason (``-``, an en or em dash, or ``:``) or none at all, but the reason must be prose: a
remainder that just starts another comment (``# pragma: no cover  # noqa: E501``) is a
machine directive, not a human saying why, and is rejected as bare.

*There is no third form.* No file-level waiver, no scope-level waiver, no threshold flag, no
bypass environment variable. Lowering the floor means editing the mandate, which is a
frozen-brief question (WA-03), not a command-line option.

The reason-required rule is enforced over the gated scopes only — the surfaces this gate is
answerable for. The rest of ``src/`` follows the same convention by hand today; widening the
rule to code TE-12 does not gate would be a policy this card was not asked to set.

Usage::

    # the full sequence, from a clean tree (what CI's `test-locked` job runs)
    coverage run -m pytest -q
    coverage json
    python tools/coverage_gate.py

    python tools/coverage_gate.py --report path/to/coverage.json
    python tools/coverage_gate.py --root /path/to/checkout

Exit status: ``0`` when every gated scope is above the floor and every exemption carries its
reason; ``1`` when a scope is at or below the floor, or an exemption does not; ``2`` when no
verdict was reached at all — the report is missing, unreadable, measured without branch
coverage, mis-measured, or a scope matched no measured file. A vacuous pass is never a pass.

WA-07: this reads two kinds of text file — a JSON report and Python sources — and executes
nothing. It imports no gebra module, no workflow, and opens no network connection.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

__all__ = [
    "GATED_SCOPES",
    "PLUGIN_SCOPE",
    "PRAGMA_PATTERN",
    "THRESHOLD",
    "CoverageDataError",
    "GateReport",
    "PragmaScan",
    "PragmaViolation",
    "Scope",
    "ScopeResult",
    "Totals",
    "check_report",
    "format_report",
    "gate",
    "load_report",
    "main",
    "scan_pragmas",
]

#: The briefs' floor, strictly (D-09 Deliverable 6 / DoD; D-10 Deliverable 8 / DoD; SOW §2).
THRESHOLD: Final = 80.0

#: coverage.py's own default exclusion pattern, byte for byte (``coverage.config``'s
#: ``DEFAULT_EXCLUDE[0]``, 7.15.2). Copied rather than imported to keep this gate
#: dependency-free, and held equal to the installed library by a test — the policy must
#: police every spelling coverage.py honours, or it is a bypass with an extra keystroke.
PRAGMA_PATTERN: Final = re.compile(r"#\s*(pragma|PRAGMA)[:\s]?\s*(no|NO)\s*(cover|COVER)")

#: Punctuation that may introduce the reason. Not ``#``: a remainder that starts another
#: comment is a machine directive (a ``noqa`` or ``type: ignore``), and the policy asks for
#: prose. See the module docstring's exemption-policy section.
_REASON_SEPARATORS: Final = ("-", "—", "–", ":")


@dataclass(frozen=True)
class Scope:
    """One gated surface, named as the briefs name it: a dotted import path.

    ``kind`` is ``"package"`` (every module under it) or ``"module"`` (one file). The
    distinction is only how a measured path is recognised as belonging here.
    """

    name: str
    kind: Literal["package", "module"]
    mandate: str

    @property
    def needle(self) -> str:
        """The path fragment a measured file must contain to belong to this scope.

        Anchored on both sides by ``/`` so ``gebra/verify/`` never matches
        ``gebra/verifying/``, and layout-independent on purpose: the same scope must be
        recognised whether coverage reports ``src/gebra/verify/base.py`` (editable install,
        what CI measures) or ``.../site-packages/gebra/verify/base.py`` (installed wheel).
        """
        parts = self.name.split(".")
        if self.kind == "package":
            return "/".join(parts) + "/"
        return "/".join(parts) + ".py"

    @property
    def source_dir(self) -> Path:
        """Where this scope's sources live in a checkout, relative to the repository root."""
        parts = self.name.split(".")
        if self.kind == "package":
            return Path("src", *parts)
        return Path("src", *parts[:-1])

    def matches(self, measured_path: str) -> bool:
        """Does a path from the coverage report belong to this scope?"""
        anchored = "/" + measured_path.replace("\\", "/").lstrip("/")
        needle = "/" + self.needle
        if self.kind == "package":
            return needle in anchored
        return anchored.endswith(needle)

    def source_files(self, root: Path) -> list[Path]:
        """The scope's ``.py`` sources in a checkout, sorted; empty if the tree moved."""
        directory = root / self.source_dir
        if self.kind == "module":
            candidate = directory / (self.name.split(".")[-1] + ".py")
            return [candidate] if candidate.is_file() else []
        return sorted(path for path in directory.rglob("*.py") if path.is_file())


#: The plugin, named once: it is both a gated scope and the module whose measurement mode
#: :func:`check_report` verifies (see the module docstring).
PLUGIN_SCOPE: Final = Scope(
    name="gebra.pytest_plugin",
    kind="module",
    mandate="D-10 Deliverable 8 / DoD: coverage >80% across the plugin",
)

#: The card's objective, verbatim: "`gebra.verify`, `gebra.testing`, and the plugin".
GATED_SCOPES: Final = (
    Scope(
        name="gebra.verify",
        kind="package",
        mandate="D-09 Deliverable 6 / DoD: unit-test coverage >80% over the validators",
    ),
    Scope(
        name="gebra.testing",
        kind="package",
        mandate="D-10 Deliverable 8 / DoD: coverage >80% across gebra.testing",
    ),
    PLUGIN_SCOPE,
)


class CoverageDataError(RuntimeError):
    """The coverage report itself is unusable — missing, malformed, or mis-measured.

    Distinct from "coverage is too low" on purpose: this is the no-verdict exit (2), never a
    quiet pass and never a reported regression that did not happen.
    """


@dataclass(frozen=True)
class Totals:
    """coverage.py's own counters for a set of files, aggregated its way.

    ``percent`` reproduces ``coverage report``'s Cover column under
    ``[tool.coverage.run] branch = true``: statements and branch arcs in one ratio. The two
    components are carried alongside so a report says *where* a scope is thin, but the gate
    compares one number — the one a contributor sees locally.
    """

    statements: int = 0
    covered_statements: int = 0
    branches: int = 0
    covered_branches: int = 0

    @property
    def measured(self) -> int:
        return self.statements + self.branches

    @property
    def percent(self) -> float:
        if self.measured == 0:
            return 0.0
        return 100.0 * (self.covered_statements + self.covered_branches) / self.measured

    @property
    def statement_percent(self) -> float:
        if self.statements == 0:
            return 0.0
        return 100.0 * self.covered_statements / self.statements

    @property
    def branch_percent(self) -> float:
        if self.branches == 0:
            return 0.0
        return 100.0 * self.covered_branches / self.branches

    def plus(self, other: Totals) -> Totals:
        return Totals(
            statements=self.statements + other.statements,
            covered_statements=self.covered_statements + other.covered_statements,
            branches=self.branches + other.branches,
            covered_branches=self.covered_branches + other.covered_branches,
        )


@dataclass(frozen=True)
class ScopeResult:
    """One gated scope, measured."""

    scope: Scope
    totals: Totals
    files: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.totals.percent > THRESHOLD


@dataclass(frozen=True)
class PragmaViolation:
    """A ``# pragma: no cover`` inside a gated scope with no reason written beside it."""

    path: str
    line_no: int
    text: str


@dataclass(frozen=True)
class PragmaScan:
    """What the exemption scan read, so a scan that read nothing cannot look like a pass."""

    files: int = 0
    pragmas: int = 0
    violations: tuple[PragmaViolation, ...] = ()


@dataclass
class GateReport:
    """What the gate observed: the scopes, the exemption scan, and the context total."""

    scopes: list[ScopeResult] = field(default_factory=list)
    pragmas: PragmaScan = PragmaScan()
    project: Totals = Totals()
    project_files: int = 0

    @property
    def failing(self) -> list[ScopeResult]:
        return [result for result in self.scopes if not result.ok]

    @property
    def ok(self) -> bool:
        return not self.failing and not self.pragmas.violations


def _as_mapping(value: object, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoverageDataError(f"{what} is not an object")
    mapping: Mapping[str, Any] = value
    return mapping


def _as_int(summary: Mapping[str, Any], key: str, what: str) -> int:
    if key not in summary:
        raise CoverageDataError(f"{what}: no {key!r} in the file summary")
    value = summary[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise CoverageDataError(f"{what}: {key!r} is not an integer")
    return value


def load_report(path: Path) -> Mapping[str, Any]:
    """Read a coverage.py JSON report, refusing anything the gate cannot read honestly."""
    if not path.is_file():
        raise CoverageDataError(
            f"no coverage report at {path} — run `coverage run -m pytest` then `coverage json`"
        )
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CoverageDataError(f"unreadable coverage report {path}: {exc}") from exc

    report = _as_mapping(parsed, f"{path}")
    meta = _as_mapping(report.get("meta", {}), f"{path}: meta")
    if meta.get("branch_coverage") is not True:
        raise CoverageDataError(
            f"{path} was measured without branch coverage; "
            "[tool.coverage.run] branch = true is what the gated percentage means"
        )
    _as_mapping(report.get("files"), f"{path}: files")
    return report


def _totals_for(summary: Mapping[str, Any], what: str) -> Totals:
    return Totals(
        statements=_as_int(summary, "num_statements", what),
        covered_statements=_as_int(summary, "covered_lines", what),
        branches=_as_int(summary, "num_branches", what),
        covered_branches=_as_int(summary, "covered_branches", what),
    )


#: One refusal, two ways of reaching it (see :func:`check_report`).
_MISMEASURED: Final = (
    "{path} measured " + PLUGIN_SCOPE.name + " only after pytest had imported it — its first "
    "statement (line {line}) reads as never executed. The plugin is a pytest11 entry point, so "
    "its module body runs during plugin loading: under `pytest --cov` every module-level "
    "statement is recorded missed and the scope's percentage is an artifact. Measure with "
    "`coverage run -m pytest`, which starts before plugin loading."
)


def _int_lines(entry: Mapping[str, Any], key: str) -> list[int]:
    value = entry.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


def check_report(report: Mapping[str, Any], path: Path) -> None:
    """Refuse a report that measured the plugin *after* pytest imported it.

    Under ``pytest --cov`` the plugin module's body has already run by the time measurement
    starts, so every module-level statement reads as missed and the scope's number is a
    measurement artifact rather than a fact about the tests. That mode has an exact signature
    needing no magic constant: **the module's first statement** — its ``from __future__``
    import — is *missing* rather than executed, because nothing re-imports the module. Under
    ``coverage run -m pytest`` measurement is already on when the import happens, so the same
    line is executed.

    Refusing here keeps a mis-measured run from being reported as a coverage regression — a
    red the gate would be lying about — and keeps the opposite mistake, a plugin scope quietly
    dropping 18.9 points because someone changed the CI command, from ever reading as data.
    """
    files = _as_mapping(report.get("files"), f"{path}: files")
    plugin = next(
        (
            entry
            for name, entry in files.items()
            if PLUGIN_SCOPE.matches(name) and isinstance(entry, Mapping)
        ),
        None,
    )
    if plugin is None:
        return
    executed = _int_lines(plugin, "executed_lines")
    missing = _int_lines(plugin, "missing_lines")
    if not missing:
        # Nothing missed at all: the first statement was necessarily executed.
        return
    if not executed:
        # Not "a plugin nobody tested" — a session running pytest has the module imported by
        # definition. Zero executed lines is the mis-measurement in its extreme form.
        raise CoverageDataError(_MISMEASURED.format(path=path, line=min(missing)))
    first_statement = min(min(executed), min(missing))
    if first_statement not in executed:
        raise CoverageDataError(_MISMEASURED.format(path=path, line=first_statement))


def measure(report: Mapping[str, Any], scopes: Sequence[Scope] = GATED_SCOPES) -> GateReport:
    """Aggregate a coverage report into one result per gated scope, plus the project total."""
    files = _as_mapping(report.get("files"), "files")
    gate_report = GateReport()

    for name, entry in sorted(files.items()):
        summary = _as_mapping(
            _as_mapping(entry, f"files[{name!r}]").get("summary"), f"files[{name!r}].summary"
        )
        gate_report.project = gate_report.project.plus(_totals_for(summary, name))
        gate_report.project_files += 1

    for scope in scopes:
        totals = Totals()
        matched: list[str] = []
        for name, entry in sorted(files.items()):
            if not scope.matches(name):
                continue
            summary = _as_mapping(
                _as_mapping(entry, f"files[{name!r}]").get("summary"), f"files[{name!r}].summary"
            )
            totals = totals.plus(_totals_for(summary, name))
            matched.append(name)
        if not matched:
            raise CoverageDataError(
                f"scope {scope.name} matched no measured file. Either the run did not cover "
                "it or the tree moved under the gate; neither is a pass."
            )
        gate_report.scopes.append(
            ScopeResult(scope=scope, totals=totals, files=tuple(matched)),
        )

    return gate_report


def _pragma_reason(line: str) -> str | None:
    """``None`` if the line carries no pragma; ``""`` if it carries one with no reason."""
    match = PRAGMA_PATTERN.search(line)
    if match is None:
        return None
    rest = line[match.end() :].strip()
    while rest and rest[0] in _REASON_SEPARATORS:
        rest = rest[1:].strip()
    if rest.startswith("#"):
        return ""
    return rest


def _iter_source_lines(paths: Sequence[Path], root: Path) -> Iterator[tuple[str, int, str]]:
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # An unreadable gated source is a scan that did not happen, not a coverage
            # regression: it belongs to the no-verdict exit, like an unreadable report.
            raise CoverageDataError(f"unreadable gated source {rel}: {exc}") from exc
        for line_no, line in enumerate(text.splitlines(), start=1):
            yield rel, line_no, line


def scan_pragmas(root: Path, scopes: Sequence[Scope] = GATED_SCOPES) -> PragmaScan:
    """Every ``# pragma: no cover`` in the gated scopes must say why it cannot be exercised."""
    files = 0
    pragmas = 0
    violations: list[PragmaViolation] = []
    for scope in scopes:
        sources = scope.source_files(root)
        files += len(sources)
        for rel, line_no, line in _iter_source_lines(sources, root):
            reason = _pragma_reason(line)
            if reason is None:
                continue
            pragmas += 1
            if not reason:
                violations.append(PragmaViolation(path=rel, line_no=line_no, text=line.strip()))
    return PragmaScan(files=files, pragmas=pragmas, violations=tuple(violations))


def gate(report: Mapping[str, Any], root: Path, path: Path) -> GateReport:
    """Measure, then hold the exemptions to the policy. Raises on a no-verdict condition."""
    check_report(report, path)
    gate_report = measure(report)
    gate_report.pragmas = scan_pragmas(root)
    if gate_report.pragmas.files == 0:
        raise CoverageDataError(
            f"no gated source found under {root} — the exemption policy would be checked "
            "against nothing. Point --root at the checkout the report was measured from."
        )
    return gate_report


def format_report(report: GateReport) -> str:
    """The gate's own words: one line per scope, the verdict, and how to reproduce it."""
    width = max(len(result.scope.name) for result in report.scopes)
    lines: list[str] = []
    verdict = (
        f"coverage gate: OK — every gated scope above {THRESHOLD:g}%"
        if report.ok
        else f"coverage gate: FAILED — the floor is >{THRESHOLD:g}%"
    )
    lines.append(verdict)
    lines.append("")
    for result in report.scopes:
        totals = result.totals
        mark = "ok  " if result.ok else "FAIL"
        lines.append(
            f"  {mark} {result.scope.name:<{width}}  {totals.percent:6.2f}%   "
            f"statements {totals.covered_statements}/{totals.statements}, "
            f"branches {totals.covered_branches}/{totals.branches}, "
            f"{len(result.files)} file(s)"
        )
    lines.append("")
    lines.append(
        f"  context (not gated): whole package {report.project.percent:6.2f}% over "
        f"{report.project_files} file(s); {report.pragmas.pragmas} exemption(s) read in "
        f"{report.pragmas.files} gated source file(s)"
    )

    if report.failing:
        lines.append("")
        for result in report.failing:
            lines.append(
                f"  {result.scope.name} is at {result.totals.percent:.2f}% — {result.scope.mandate}"
            )
    if report.pragmas.violations:
        lines.append("")
        for violation in report.pragmas.violations:
            lines.append(
                f"  {violation.path}:{violation.line_no}: `# pragma: no cover` with no reason "
                f"— {violation.text!r}"
            )
        lines.append(
            "  An exemption with no stated reason is a silent hole in the floor. Write why the "
            "line cannot be exercised, or delete the pragma and cover it."
        )
    if not report.ok:
        lines.append("")
        lines.append(
            "  Reproduce locally: `coverage run -m pytest -q && coverage json && "
            "python tools/coverage_gate.py`."
        )
    return "\n".join(lines)


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coverage_gate.py",
        description=(
            f"Hold gebra.verify, gebra.testing and the pytest plugin above {THRESHOLD:g}% "
            "coverage (TE-12; briefs D-09/D-10, SOW §2)."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"repository root holding the gated sources (default: {default_root})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        metavar="JSON",
        help="coverage.py JSON report to read (default: <root>/coverage.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = build_parser(here.parent)
    args = parser.parse_args(argv)
    root: Path = args.root
    report_path: Path = args.report if args.report is not None else root / "coverage.json"

    try:
        raw = load_report(report_path)
        report = gate(raw, root, report_path)
    except CoverageDataError as exc:
        print(f"coverage gate: no verdict — {exc}", file=sys.stderr)
        return 2

    print(format_report(report), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
