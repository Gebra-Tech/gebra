"""Honest-claims lint — the WA-06 banned-phrase gate over repo-authored prose.

gebra statically analyzes serialized IR; it never executes workflows and proves nothing
about runtime behavior. WA-06 (SOW.md §6) requires that no repo-authored copy overstate
that boundary — the overclaiming phrases listed in ``tools/honest-claims-phrases.txt`` are
witness-presence violations everywhere they appear: source, docs, CLI copy, plugin output
templates.

The scan is text-only — it reads files and matches substrings, and never imports, executes,
or fetches anything (WA-07). It covers ``src/``, ``docs/`` and the top-level prose files, and
exempts the vendored fixture corpus (``tests/fixtures/properties/``, frozen under WA-04/
WA-11) by path, unconditionally.

A line that genuinely needs to quote banned wording (e.g. explaining the ban itself) can
carry an allow-pragma with a justification, on that line or the line directly above/below::

    # honest-claims: allow: quoting the banned phrase to describe the ban, not claiming it
    "the list in tools/honest-claims-phrases.txt names what this lint rejects"

A pragma with no justification text is itself a violation — it is not a silent bypass.

Usage::

    python tools/honest_claims_lint.py                 # scan the repo with the defaults
    python tools/honest_claims_lint.py --root some/dir  # scan a different root (e.g. the
                                                         # companion repo, pointed at its
                                                         # own include/exclude scope)

Exit status is 0 when no violation is found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: The objective's surface: source (incl. future CLI/plugin copy under src/), docs, and the
#: top-level prose a reader meets first.
DEFAULT_INCLUDE = (
    "src/**/*.py",
    "docs/**/*.md",
    "README.md",
    "CHANGELOG.md",
)

#: Vendored, frozen, out of scope by design (WA-04/WA-11) — never flagged, pragma or not.
DEFAULT_EXCLUDE = ("tests/fixtures/properties/**",)

PRAGMA_MARKER = "honest-claims: allow"
_ADJACENT_WINDOW = (-1, 0, 1)


class PhraseListError(RuntimeError):
    """The phrase list itself is unusable (missing or empty)."""


@dataclass(frozen=True)
class Violation:
    """One offending line: either a banned phrase or an unjustified allow-pragma."""

    path: str
    line_no: int
    kind: str  # "phrase" | "pragma"
    detail: str  # the matched phrase, or why the pragma is rejected
    text: str  # the offending line, stripped


@dataclass
class Report:
    """What the scan found. An empty violation list means the gate passed."""

    checked: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def load_phrases(path: Path) -> tuple[str, ...]:
    """Read the banned-phrase list: one phrase per line, ``#`` and blank lines ignored."""
    if not path.is_file():
        raise PhraseListError(f"phrase list not found: {path}")
    phrases = tuple(
        stripped.lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )
    if not phrases:
        raise PhraseListError(f"no banned phrases found in {path}")
    return phrases


def _matches_any(rel_path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in patterns)


def scan_files(root: Path, include: tuple[str, ...], exclude: tuple[str, ...]) -> list[str]:
    """Every included, non-excluded file, repo-relative and POSIX-separated, de-duplicated."""
    found: set[str] = set()
    for pattern in include:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(root).as_posix()
            if _matches_any(rel, exclude):
                continue
            found.add(rel)
    return sorted(found)


def _pragma_justification(line: str) -> str | None:
    """``None`` if the line carries no pragma; ``""`` if it does but lacks a justification."""
    lowered = line.lower()
    marker_at = lowered.find(PRAGMA_MARKER)
    if marker_at == -1:
        return None
    rest = line[marker_at + len(PRAGMA_MARKER) :].lstrip()
    if rest.startswith(":"):
        justification = rest[1:].strip()
        if justification:
            return justification
    return ""


def _scan_text(rel_path: str, lines: list[str], phrases: tuple[str, ...]) -> list[Violation]:
    pragma_justifications = [_pragma_justification(line) for line in lines]
    violations: list[Violation] = []

    for line_no, line in enumerate(lines, start=1):
        justification = pragma_justifications[line_no - 1]
        if justification is not None and not justification:
            violations.append(
                Violation(
                    path=rel_path,
                    line_no=line_no,
                    kind="pragma",
                    detail="allow-pragma with no justification",
                    text=line.strip(),
                )
            )

        lowered = line.lower()
        matched = [phrase for phrase in phrases if phrase in lowered]
        if not matched:
            continue

        exempted = any(
            0 <= (line_no - 1 + offset) < len(lines) and pragma_justifications[line_no - 1 + offset]
            for offset in _ADJACENT_WINDOW
        )
        if exempted:
            continue

        for phrase in matched:
            violations.append(
                Violation(
                    path=rel_path,
                    line_no=line_no,
                    kind="phrase",
                    detail=phrase,
                    text=line.strip(),
                )
            )

    return violations


def scan(
    root: Path,
    phrases: tuple[str, ...],
    include: tuple[str, ...] = DEFAULT_INCLUDE,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
) -> Report:
    """Scan every included file under ``root`` for banned phrases and bare allow-pragmas."""
    report = Report()
    for rel_path in scan_files(root, include, exclude):
        report.checked += 1
        lines = (root / rel_path).read_text(encoding="utf-8").splitlines()
        report.violations.extend(_scan_text(rel_path, lines, phrases))
    return report


def format_report(report: Report) -> str:
    if report.ok:
        return f"honest-claims lint: OK — {report.checked} file(s) scanned, no violation"

    lines = [f"honest-claims lint: FAILED — {report.checked} file(s) scanned"]
    for violation in report.violations:
        if violation.kind == "phrase":
            lines.append(
                f"  {violation.path}:{violation.line_no}: banned phrase "
                f"{violation.detail!r} — {violation.text!r}"
            )
        else:
            lines.append(
                f"  {violation.path}:{violation.line_no}: {violation.detail} — {violation.text!r}"
            )
    lines.append("")
    lines.append(
        "Repo-authored copy stays within witness-presence wording (WA-06, SOW.md §6): gebra "
        "statically analyzes serialized IR and proves nothing about runtime behavior. Reword "
        "the offending line, or if it genuinely needs to quote the banned wording (e.g. "
        "explaining the ban itself), add an allow-pragma with a reason on that line or the "
        "line directly above/below: `honest-claims: allow: <why this is not a claim>`."
    )
    return "\n".join(lines)


def build_parser(default_root: Path, default_phrases: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="honest_claims_lint.py",
        description="Scan repo-authored prose for WA-06 banned overclaiming phrases.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"repository root to scan (default: {default_root})",
    )
    parser.add_argument(
        "--phrases",
        type=Path,
        default=default_phrases,
        help=f"banned-phrase list to load (default: {default_phrases})",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        metavar="GLOB",
        help=f"glob to scan, relative to --root; repeatable (default: {list(DEFAULT_INCLUDE)})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="GLOB",
        help=(f"glob to exempt, relative to --root; repeatable (default: {list(DEFAULT_EXCLUDE)})"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = build_parser(here.parent, here / "honest-claims-phrases.txt")
    args = parser.parse_args(argv)

    try:
        phrases = load_phrases(args.phrases)
    except PhraseListError as exc:
        print(f"honest-claims lint: {exc}", file=sys.stderr)
        return 1

    include = tuple(args.include) if args.include else DEFAULT_INCLUDE
    exclude = tuple(args.exclude) if args.exclude else DEFAULT_EXCLUDE
    report = scan(args.root, phrases, include, exclude)

    print(format_report(report), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
