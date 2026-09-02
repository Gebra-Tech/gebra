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

That window is computed in exactly one place, :func:`exempt_lines` — the phrase gate below
applies it, and ``--format json`` publishes it, so that a reviewer working past a substring
list can honor the same exemptions instead of reimplementing them. A rule restated somewhere
else is a rule that can drift, and the drift would be an exemption honored on one surface and
refused on another.

Usage::

    python tools/honest_claims_lint.py                 # scan the repo with the defaults
    python tools/honest_claims_lint.py --root some/dir  # scan a different root (e.g. the
                                                         # companion repo, pointed at its
                                                         # own include/exclude scope)
    python tools/honest_claims_lint.py --format json    # the same run, machine-readable:
                                                         # violations *and* the lines the
                                                         # allow-pragmas exempt

Exit status is 0 when no violation is found, 1 otherwise — in either output format.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
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

#: What a reader does about a violation. Carried in both output formats so that no surface
#: reporting this gate's findings has to compose remediation copy of its own.
REMEDIATION = (
    "Repo-authored copy stays within witness-presence wording (WA-06, SOW.md §6): gebra "
    "statically analyzes serialized IR and proves nothing about runtime behavior. Reword "
    "the offending line, or if it genuinely needs to quote the banned wording (e.g. "
    "explaining the ban itself), add an allow-pragma with a reason on that line or the "
    "line directly above/below: `honest-claims: allow: <why this is not a claim>`."
)


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


@dataclass(frozen=True)
class Exemption:
    """One line an allow-pragma covers — the pragma's own line and its two neighbours.

    Emitted so that a reviewer working beyond this lint — the WA-06 overstatement no phrase
    list can express — can honor the same exemptions without recomputing the window.
    """

    path: str
    line_no: int  # the covered line
    pragma_line_no: int  # where the pragma that covers it sits
    justification: str
    text: str  # the covered line, stripped


@dataclass
class Report:
    """What the scan found. An empty violation list means the gate passed."""

    checked: int = 0
    violations: list[Violation] = field(default_factory=list)
    exemptions: list[Exemption] = field(default_factory=list)

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


#: Closers of the comment syntaxes the scanned file types use. They belong to the comment,
#: not to the reason — left in, `<!-- honest-claims: allow: -->` would read as justified.
_COMMENT_CLOSERS = ("-->", "*/")


def _pragma_justification(line: str) -> str | None:
    """``None`` if the line carries no pragma; ``""`` if it does but lacks a justification."""
    lowered = line.lower()
    marker_at = lowered.find(PRAGMA_MARKER)
    if marker_at == -1:
        return None
    rest = line[marker_at + len(PRAGMA_MARKER) :].lstrip()
    if rest.startswith(":"):
        justification = rest[1:].strip()
        for closer in _COMMENT_CLOSERS:
            if justification.endswith(closer):
                justification = justification[: -len(closer)].strip()
        if justification:
            return justification
    return ""


def exempt_lines(lines: list[str]) -> dict[int, tuple[int, str]]:
    """Every line a justified allow-pragma covers: ``line_no -> (pragma_line_no, reason)``.

    A pragma covers its own line and the two directly adjacent to it, and only when it
    carries a justification — a bare pragma exempts nothing, including itself. Where two
    pragmas reach the same line the earlier one is reported, so the mapping is stable.

    This is the single definition of the WA-06 exemption window. Both the phrase gate below
    and every reviewer reading ``--format json`` take the window from here.
    """
    covered: dict[int, tuple[int, str]] = {}
    for index, line in enumerate(lines):
        justification = _pragma_justification(line)
        if not justification:  # None (no pragma) or "" (no justification)
            continue
        pragma_line_no = index + 1
        for offset in _ADJACENT_WINDOW:
            neighbour = index + offset
            if 0 <= neighbour < len(lines):
                covered.setdefault(neighbour + 1, (pragma_line_no, justification))
    return covered


def _scan_text(
    rel_path: str, lines: list[str], phrases: tuple[str, ...]
) -> tuple[list[Violation], list[Exemption]]:
    covered = exempt_lines(lines)
    violations: list[Violation] = []
    exemptions = [
        Exemption(
            path=rel_path,
            line_no=line_no,
            pragma_line_no=pragma_line_no,
            justification=justification,
            text=lines[line_no - 1].strip(),
        )
        for line_no, (pragma_line_no, justification) in sorted(covered.items())
    ]

    for line_no, line in enumerate(lines, start=1):
        justification = _pragma_justification(line)
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
        if not matched or line_no in covered:
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

    return violations, exemptions


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
        violations, exemptions = _scan_text(rel_path, lines, phrases)
        report.violations.extend(violations)
        report.exemptions.extend(exemptions)
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
    lines.append(REMEDIATION)
    return "\n".join(lines)


def format_json(report: Report) -> str:
    """The same run, machine-readable — violations *and* the lines the pragmas exempt.

    A reviewer who reasons past a substring list needs both halves: what this gate rejected,
    and which lines it was told to leave alone. Reading ``exemptions`` is how such a reviewer
    honors the pragma identically instead of forming a second opinion about what "adjacent"
    means.
    """
    payload = {
        "ok": report.ok,
        "checked": report.checked,
        "remediation": REMEDIATION,
        "violations": [
            {
                "path": violation.path,
                "line": violation.line_no,
                "kind": violation.kind,
                "detail": violation.detail,
                "text": violation.text,
            }
            for violation in report.violations
        ],
        "exemptions": [
            {
                "path": exemption.path,
                "line": exemption.line_no,
                "pragma_line": exemption.pragma_line_no,
                "justification": exemption.justification,
                "text": exemption.text,
            }
            for exemption in report.exemptions
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


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
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help=(
            "text (default) prints the human report; json prints the violations and the "
            "lines the allow-pragmas exempt, on stdout, at the same exit status"
        ),
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

    if args.format == "json":
        # Machine output goes to stdout whatever the verdict — a consumer that has to
        # switch streams to read a failure is a consumer that will read half of one.
        print(format_json(report), file=sys.stdout)
    else:
        print(format_report(report), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
