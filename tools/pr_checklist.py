"""The pre-merge obligations a script can settle, computed from their own records (TOOL-07).

Working agreement WA-08 lets a change merge only when its author's contributor licence is on
file and its commits are conventional; WA-05 lets a golden file move only in a commit carrying
its justification; GOV-03 makes the tag the whole release procedure. Three of those obligations
have a record or a gate that already answers them, and until this module the pre-merge review
answered them a second time, from prose written beside the record — which is one drift away
from a review passing what CI refuses.

This module is the half of that review a script can hold. Each check reads the source of truth
the repository already keeps, and each failing check names the step that clears it:

* **CLA** — ``docs/governance/cla-signatures.md``, the append-only record GOV-09 made the
  process (and the record the deferred bot is meant to read). A row covers a contribution when
  its handle is the author's, its ``CLA version`` is the version ``CLA.md`` currently
  publishes — the agreement's own versioning clause says a new version applies to contributions
  submitted after it lands — and its ``Type`` covers how the work is owned. A code owner needs
  no row: the record says the owner's own commits are not contributions under the agreement.
* **Golden files (WA-05)** — :mod:`tools.golden_guard`, the same module the ``golden-guard`` CI
  job runs, called per commit, so a justified commit never covers an unjustified one here
  either. This module reaches no golden verdict of its own; it relays the guard's.
* **Release workflow (GOV-03)** — :mod:`tools.release_gate`, the same gate ``release.yml`` runs
  on a tag push and ``ci.yml``'s ``build`` job runs in dry-run mode on every push. Reviewing a
  release cut before it is tagged is the ``--tag`` spelling; reviewing any other change is the
  dry run, which is what keeps a tree from drifting out of release-readiness between cuts.

What is deliberately *not* here: commit format, card linkage, board sync, and the prose review.
The first three have their own computed homes (``tools/board_integrity.py`` and the plan
tooling) and the last is ``tools/honest_claims_lint.py`` plus the reading no substring search
can do. A verdict from this module is one input to the review, never the review.

Usage::

    python tools/pr_checklist.py --author octocat \
        --files $(git diff --name-only main...HEAD) --message "$(git log -1 --format=%B)"

    # the spelling that judges each commit of the branch separately, as CI does
    python tools/pr_checklist.py --author octocat --base main --head HEAD

    # the release pull request, before the tag exists
    python tools/pr_checklist.py --author octocat --base main --head HEAD --tag v0.0.1.dev1

Exit status: ``0`` when every check passes, ``1`` when one refuses, ``2`` when a check could
not be evaluated at all (an unreadable record, a git range that cannot be walked). A vacuous
pass is never a pass, and there is no bypass flag.

WA-07: this reads text files and, in ``--base``/``--head`` mode, git metadata through
:mod:`tools.golden_guard`'s own subprocess boundary. It imports no gebra module, executes no
workflow node, calls no model, and opens no network connection.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

if __package__ in (None, ""):  # pragma: no cover - executed as `python tools/…`, as CI does
    # A script's `sys.path[0]` is `tools/`, not the repository root, so the two modules whose
    # verdicts this one relays would be unimportable. `python -m tools.pr_checklist` needs no
    # such help.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import golden_guard, release_gate

__all__ = [
    "CLA_AGREEMENT",
    "CLA_RECORD",
    "CODEOWNERS",
    "RELEASE_SURFACE",
    "Check",
    "ChecklistInputError",
    "Commit",
    "Finding",
    "Report",
    "Signature",
    "agreement_version",
    "as_json",
    "check_cla",
    "check_goldens",
    "check_release",
    "code_owner_handles",
    "commits_from_range",
    "format_report",
    "load_signatures",
    "main",
    "normalize_handle",
    "review",
]

#: The repository root — this file lives in ``tools/``.
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: The CLA signature record: the source of truth GOV-09 chose, append-only and maintainer-kept.
CLA_RECORD: Final = REPO_ROOT / "docs" / "governance" / "cla-signatures.md"

#: The agreement itself; its title line carries the version a row has to name.
CLA_AGREEMENT: Final = REPO_ROOT / "CLA.md"

#: Code owners need no row — the record says the owner's own commits are not contributions.
CODEOWNERS: Final = REPO_ROOT / "CODEOWNERS"

#: The heading above the record's signature table.
SIGNATURES_HEADING: Final = "## Signatures"

#: The release machinery the gate itself does not read: a change here is reviewed against
#: ``tests/test_release_wiring.py``'s pins rather than by running the gate.
RELEASE_SURFACE: Final = (
    ".github/workflows/release.yml",
    "tools/release_gate.py",
)

#: ``**Version 1.0.**`` — the agreement's title line, which is where its version lives.
_AGREEMENT_VERSION = re.compile(r"^\*\*Version\s+(?P<version>[^*]+?)\.\*\*")

#: A GitHub handle: the shape a row's first column and a ``--author`` argument must have.
_HANDLE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")

#: ``[text](url)`` — a record row may write a handle as a link to the account.
_MARKDOWN_LINK = re.compile(r"^\[(?P<text>[^\]]*)\]\([^)]*\)$")

#: The record's columns, by the header each one is written under (GOV-09 decision 1).
_COLUMNS: Final = {
    "github handle": "handle",
    "legal name": "legal_name",
    "type": "kind",
    "cla version": "version",
    "signed": "signed",
    "recorded": "recorded",
    "archive": "archive",
    "notes": "notes",
}

Status = Literal["PASS", "BLOCK", "ERROR"]


class ChecklistInputError(RuntimeError):
    """A source of truth could not be read — the no-verdict exit 2, never a quiet pass."""


@dataclass(frozen=True)
class Finding:
    """One refusal: what the record or the gate said, and the step that clears it."""

    #: The check that produced it (``cla``, ``goldens``, ``release``).
    check: str
    #: The refusal in its source's own words — quoted, never paraphrased into something milder.
    summary: str
    #: The concrete step, naming the file, command or row that has to change.
    remediation: str


@dataclass(frozen=True)
class Check:
    """What one obligation's own record answered."""

    key: str
    #: The source of truth this verdict was read from, named so a reader can go there.
    subject: str
    status: Status
    #: One line on what was computed — for a passing check, why it passed.
    detail: str
    findings: tuple[Finding, ...] = ()
    #: Boundaries worth stating even when the check passes.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Commit:
    """One commit as the golden guard judges it: the paths it changed and its message."""

    sha: str | None
    files: tuple[str, ...]
    message: str

    @property
    def label(self) -> str:
        """How a finding names this commit: its abbreviated hash, or its subject line."""
        if self.sha:
            return self.sha[:12]
        subject = self.message.splitlines()[0].strip() if self.message.strip() else ""
        return f"the change under review ({subject})" if subject else "the change under review"


@dataclass(frozen=True)
class Report:
    """The three checks and the one verdict they compose into."""

    checks: tuple[Check, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(finding for check in self.checks for finding in check.findings)

    @property
    def ok(self) -> bool:
        return all(check.status == "PASS" for check in self.checks)

    @property
    def verdict(self) -> str:
        return "MERGE-READY" if self.ok else "BLOCKED"

    @property
    def exit_status(self) -> int:
        """0 every check passed · 1 one refused · 2 one reached no verdict at all."""
        if any(check.status == "ERROR" for check in self.checks):
            return 2
        return 0 if self.ok else 1


# ── The CLA record ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Signature:
    """One row of the signature record, in the columns GOV-09 gave it."""

    handle: str
    legal_name: str
    kind: str
    version: str
    signed: str
    recorded: str
    archive: str
    notes: str


def normalize_handle(raw: str) -> str:
    """A handle as the record and an author argument may each spell it.

    Backticks, an ``@`` prefix and a link to the account are presentation; the account is
    what the check compares, and GitHub handles are case-insensitive.
    """
    text = raw.strip().strip("`").strip()
    link = _MARKDOWN_LINK.match(text)
    if link is not None:
        text = link.group("text").strip().strip("`").strip()
    return text.lstrip("@").strip().lower()


def _table_rows(lines: Sequence[str], heading: str) -> list[list[str]]:
    """Every ``|``-delimited row under ``heading``, up to the next section."""
    rows: list[list[str]] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip() == heading
            continue
        if not inside:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


def load_signatures(path: Path = CLA_RECORD) -> tuple[Signature, ...]:
    """The rows of the signature record, keyed by the headers the record itself carries.

    The table's placeholder row is not a signature: a row counts only when its first column
    is a handle. Reading the columns by header rather than by position means a column added
    to the record later does not silently shift what this check compares.
    """
    if not path.is_file():
        raise ChecklistInputError(f"no CLA signature record at {path}")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:  # pragma: no cover - unreadable file
        raise ChecklistInputError(f"unreadable {path}: {error}") from error

    rows = _table_rows(lines, SIGNATURES_HEADING)
    if len(rows) < 2:
        raise ChecklistInputError(
            f"{path} carries no `{SIGNATURES_HEADING}` table — the record a review reads is "
            "missing, which is a broken record rather than an empty one"
        )
    header = [cell.lower() for cell in rows[0]]
    missing = [name for name in _COLUMNS if name not in header]
    if missing:
        raise ChecklistInputError(
            f"{path}'s signature table is missing the column(s) {', '.join(missing)}"
        )
    index = {_COLUMNS[name]: header.index(name) for name in _COLUMNS}

    signatures: list[Signature] = []
    for cells in rows[2:]:  # rows[1] is the header separator
        if len(cells) != len(header):
            continue
        handle = normalize_handle(cells[index["handle"]])
        if not _HANDLE.match(handle):
            continue  # the placeholder row, or a note written into the table
        signatures.append(
            Signature(
                handle=handle,
                legal_name=cells[index["legal_name"]],
                kind=cells[index["kind"]].strip().upper(),
                version=cells[index["version"]].strip(),
                signed=cells[index["signed"]].strip(),
                recorded=cells[index["recorded"]].strip(),
                archive=cells[index["archive"]].strip(),
                notes=cells[index["notes"]].strip(),
            )
        )
    return tuple(signatures)


def agreement_version(path: Path = CLA_AGREEMENT) -> str:
    """The version ``CLA.md`` publishes, read from its title line."""
    if not path.is_file():
        raise ChecklistInputError(f"no contributor agreement at {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:  # pragma: no cover - unreadable file
        raise ChecklistInputError(f"unreadable {path}: {error}") from error
    for line in text.splitlines():
        match = _AGREEMENT_VERSION.match(line)
        if match is not None:
            return match.group("version").strip()
    raise ChecklistInputError(
        f"{path} declares no version in its title line (`**Version <x.y>.**`), so no row can "
        "be checked against it"
    )


def code_owner_handles(path: Path = CODEOWNERS) -> frozenset[str]:
    """The accounts CODEOWNERS names. A team (``@org/team``) is never a pull request's author."""
    if not path.is_file():
        return frozenset()
    handles: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0]
        for token in text.split():
            if token.startswith("@") and "/" not in token:
                handles.add(token[1:].lower())
    return frozenset(handles)


def check_cla(
    author: str,
    *,
    employer_owned: bool = False,
    record: Path = CLA_RECORD,
    agreement: Path = CLA_AGREEMENT,
    codeowners: Path = CODEOWNERS,
) -> Check:
    """Whether the author's contributor licence is on file, per the GOV-09 record."""
    subject = _relative(record)
    handle = normalize_handle(author)
    if not handle:
        return _error("cla", subject, "no pull-request author was given to look up")
    try:
        owners = code_owner_handles(codeowners)
        signatures = load_signatures(record)
        current = agreement_version(agreement)
    except ChecklistInputError as error:
        return _error("cla", subject, str(error))

    if handle in owners:
        return Check(
            key="cla",
            subject=subject,
            status="PASS",
            detail=(
                f"@{handle} is a code owner; the record records that the owner's own commits "
                "are not contributions under the agreement, so no row is required"
            ),
        )

    rows = [signature for signature in signatures if signature.handle == handle]
    if not rows:
        return Check(
            key="cla",
            subject=subject,
            status="BLOCK",
            detail=f"no row for @{handle} among {len(signatures)} recorded signature(s)",
            findings=(
                Finding(
                    check="cla",
                    summary=(
                        f"@{handle} has no row in {subject}, and a contribution cannot be "
                        "merged while the record has no row for its author (WA-08)"
                    ),
                    remediation=(
                        f"@{handle} signs CLA.md by its 'How to sign' section — email "
                        "gebra.dev@gmail.com with the signing statement — and the maintainer "
                        f"archives it and appends the row to {subject}. Point the contributor "
                        "at CLA.md; do not merge and follow up."
                    ),
                ),
            ),
        )

    covering = [signature for signature in rows if signature.version == current]
    if not covering:
        signed = ", ".join(sorted({signature.version or "(blank)" for signature in rows}))
        return Check(
            key="cla",
            subject=subject,
            status="BLOCK",
            detail=f"@{handle} is recorded against CLA version {signed}; CLA.md is {current}",
            findings=(
                Finding(
                    check="cla",
                    summary=(
                        f"@{handle}'s row(s) name CLA version {signed}, but CLA.md publishes "
                        f"{current}, and a new version applies to contributions submitted "
                        "after it lands (CLA.md, 'Versioning and amendments')"
                    ),
                    remediation=(
                        f"@{handle} signs version {current} and the maintainer appends a "
                        f"second row to {subject} — rows are append-only, so the earlier "
                        "signature stays visible against the period it covered rather than "
                        "being rewritten."
                    ),
                ),
            ),
        )

    if employer_owned and not any(signature.kind == "CCLA" for signature in covering):
        kinds = ", ".join(sorted({signature.kind or "(blank)" for signature in covering}))
        return Check(
            key="cla",
            subject=subject,
            status="BLOCK",
            detail=f"employer-owned contribution; @{handle}'s covering row(s) are {kinds}",
            findings=(
                Finding(
                    check="cla",
                    summary=(
                        f"the contribution is employer-owned and @{handle} has only a {kinds} "
                        "row on file; section 4 of the CLA asks for written permission or a "
                        "corporate agreement, recorded as a CCLA row"
                    ),
                    remediation=(
                        "the contributor emails gebra.dev@gmail.com so the maintainer handles "
                        f"the corporate agreement directly and records it in {subject} as a "
                        "CCLA row naming the entity in Notes (CLA.md, 'Employers and "
                        "corporate contributions')."
                    ),
                ),
            ),
        )

    row = covering[0]
    detail = (
        f"@{handle} — {row.kind} against CLA version {row.version}, signed {row.signed}, "
        f"archived {row.archive}"
    )
    return Check(key="cla", subject=subject, status="PASS", detail=detail)


# ── The WA-05 golden justification, relayed from the guard CI runs ────────────────────────


def commits_from_range(base: str, head: str) -> tuple[Commit, ...]:
    """The commits an event delivered, read through the golden guard's own git boundary."""
    try:
        shas = golden_guard.commits_in_range(base, head)
        return tuple(
            Commit(
                sha=sha,
                files=tuple(golden_guard.commit_files(sha)),
                message=golden_guard.commit_message(sha),
            )
            for sha in shas
        )
    except golden_guard.GoldenGuardError as error:
        raise ChecklistInputError(str(error)) from error


def check_goldens(commits: Sequence[Commit]) -> Check:
    """Whether every commit touching a golden carries its WA-05 justification.

    The verdict per commit is :func:`tools.golden_guard.evaluate_commit` — the same call the
    ``golden-guard`` job makes — so this check cannot pass a commit that job fails. What it
    adds is the remediation, which names the commit and the paths rather than the rule.
    """
    subject = "tools/golden_guard.py (the WA-05 golden-guard job)"
    findings: list[Finding] = []
    touched_total = 0
    for commit in commits:
        touched = golden_guard.golden_paths_touched(list(commit.files))
        touched_total += len(touched)
        verdict = golden_guard.evaluate_commit(list(commit.files), commit.message)
        if verdict is None:
            continue
        findings.append(
            Finding(
                check="goldens",
                summary=f"{commit.label}: {verdict}",
                remediation=(
                    f"add a `{golden_guard.TRAILER_KEY}` trailer at column 0 of {commit.label}, "
                    "in one of the two forms the guard just listed, and re-run "
                    '`python tools/golden_guard.py --files <paths...> --message "<message>"` '
                    "— that is the same check the golden-guard job runs, and a justified "
                    "commit does not cover an unjustified one in the same push."
                ),
            )
        )
    if findings:
        return Check(
            key="goldens",
            subject=subject,
            status="BLOCK",
            detail=(
                f"{len(findings)} of {len(commits)} commit(s) move a golden without a "
                "well-formed justification"
            ),
            findings=tuple(findings),
        )
    if touched_total == 0:
        detail = f"no golden path in {len(commits)} commit(s) under review"
    else:
        detail = (
            f"{touched_total} golden path change(s) across {len(commits)} commit(s), each in a "
            "commit carrying a well-formed justification"
        )
    notes: tuple[str, ...] = ()
    if touched_total:
        notes = (
            (
                "the guard checks that a justification is present and well-formed; whether the "
                "run or the decision it cites justifies this diff stays with review"
            ),
        )
    return Check(key="goldens", subject=subject, status="PASS", detail=detail, notes=notes)


# ── Release-workflow conformance, relayed from the gate the workflow runs ─────────────────


def check_release(
    files: Iterable[str] = (),
    *,
    tag: str | None = None,
    pyproject: Path = REPO_ROOT / "pyproject.toml",
    changelog: Path = REPO_ROOT / "CHANGELOG.md",
    dist: Path | None = None,
) -> Check:
    """Whether the tree (or the tag proposed for it) satisfies the GOV-03 release contract.

    With ``tag`` this is the review of a release cut before the tag exists: the gate holds the
    tag to the Phase-0 grammar, to byte equality with ``[project].version``, and to the
    changelog section that tag's kind requires. Without one it is the dry run ``ci.yml``'s
    ``build`` job makes on every push, which is what keeps an ordinary change from leaving the
    tree unable to release.
    """
    mode = f"--tag {tag}" if tag else "--dry-run"
    subject = f"tools/release_gate.py ({mode}) — the gate release.yml runs on a tag"
    notes: list[str] = []
    edited = sorted(path for path in files if path in RELEASE_SURFACE)
    if edited:
        notes.append(
            "this change edits the release machinery itself ("
            + ", ".join(edited)
            + "); the gate does not read the workflow file, so that edit is reviewed against "
            "tests/test_release_wiring.py's pins rather than by this verdict"
        )
    try:
        verdict = release_gate.run_gate(
            ref=None,
            tag=tag,
            dry_run=tag is None,
            pyproject=pyproject,
            changelog=changelog,
            verify_dist_dir=dist,
        )
    except release_gate.GateError as error:
        if tag:
            remediation = (
                f"the release workflow runs this same gate on the push of {tag}, so the tag "
                "would fail there: land the fix the refusal names before tagging, then re-run "
                f"`python tools/release_gate.py --tag {tag}`."
            )
        else:
            remediation = (
                "CI's build job runs this same gate in dry-run mode on every push, so this "
                "change is red before any tag exists: land the fix the refusal names, then "
                "re-run `python tools/release_gate.py --dry-run`."
            )
        return Check(
            key="release",
            subject=subject,
            status="BLOCK",
            detail="the release gate refused this tree",
            findings=(Finding(check="release", summary=str(error), remediation=remediation),),
            notes=tuple(notes),
        )
    except release_gate.GateInputError as error:
        return _error("release", subject, str(error), notes=tuple(notes))

    detail = (
        f"{verdict.version} ({verdict.kind}) — publish={'true' if verdict.publish else 'false'}"
        f"; notes from {verdict.notes_heading}"
    )
    if verdict.dist_files:
        detail += "; dist " + ", ".join(verdict.dist_files)
    return Check(key="release", subject=subject, status="PASS", detail=detail, notes=tuple(notes))


# ── The report ───────────────────────────────────────────────────────────────────────────


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _error(key: str, subject: str, message: str, *, notes: tuple[str, ...] = ()) -> Check:
    """A check that reached no verdict: loud, and never counted as a pass."""
    return Check(
        key=key,
        subject=subject,
        status="ERROR",
        detail="no verdict reached",
        findings=(
            Finding(
                check=key,
                summary=message,
                remediation=(
                    "this check reached no verdict, which is not a pass: make the source it "
                    "names readable and run the checklist again before merging."
                ),
            ),
        ),
        notes=notes,
    )


def review(
    *,
    author: str,
    commits: Sequence[Commit],
    employer_owned: bool = False,
    tag: str | None = None,
    record: Path = CLA_RECORD,
    agreement: Path = CLA_AGREEMENT,
    codeowners: Path = CODEOWNERS,
    pyproject: Path = REPO_ROOT / "pyproject.toml",
    changelog: Path = REPO_ROOT / "CHANGELOG.md",
    dist: Path | None = None,
) -> Report:
    """Every check, collected — a refusal never stops the ones after it."""
    files = sorted({path for commit in commits for path in commit.files})
    return Report(
        checks=(
            check_cla(
                author,
                employer_owned=employer_owned,
                record=record,
                agreement=agreement,
                codeowners=codeowners,
            ),
            check_goldens(commits),
            check_release(files, tag=tag, pyproject=pyproject, changelog=changelog, dist=dist),
        )
    )


def format_report(report: Report) -> str:
    """The report a reviewer reads: a verdict, then each check with its own remediation."""
    lines = [f"pr-checklist: {report.verdict}"]
    for check in report.checks:
        lines.append("")
        lines.append(f"  {check.key:<8} {check.status:<5} {check.subject}")
        lines.append(f"      {check.detail}")
        for note in check.notes:
            lines.append(f"      note: {note}")
        for finding in check.findings:
            summary = finding.summary.splitlines()
            lines.append(f"      finding      {summary[0]}")
            lines.extend(f"                   {line}" for line in summary[1:])
            lines.append(f"      remediation  {finding.remediation}")
    return "\n".join(lines)


def as_json(report: Report) -> str:
    """The same report as data, for a caller that would rather not parse prose."""
    return json.dumps(
        {
            "verdict": report.verdict,
            "exit_status": report.exit_status,
            "checks": [
                {
                    "key": check.key,
                    "subject": check.subject,
                    "status": check.status,
                    "detail": check.detail,
                    "notes": list(check.notes),
                    "findings": [
                        {"summary": finding.summary, "remediation": finding.remediation}
                        for finding in check.findings
                    ],
                }
                for check in report.checks
            ],
        },
        indent=2,
        sort_keys=False,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr_checklist.py",
        description=(
            "Compute the pre-merge obligations that have a record: the author's CLA row "
            "(GOV-09), the WA-05 justification on any golden diff, and GOV-03 "
            "release-workflow conformance. Each refusal names its remediation."
        ),
    )
    parser.add_argument("--author", required=True, help="the pull request author's GitHub handle")
    parser.add_argument(
        "--employer-owned",
        action="store_true",
        help="the contribution is owned by the author's employer (CLA section 4)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        metavar="PATH",
        help="the changed paths, as `git diff --name-only` prints them (with --message)",
    )
    parser.add_argument("--message", help="the commit message for --files mode")
    parser.add_argument("--base", help="the revision below the reviewed range (exclusive)")
    parser.add_argument("--head", help="the last revision of the reviewed range")
    parser.add_argument(
        "--tag",
        help="review a release cut against this tag (e.g. v0.0.1.dev1) instead of a dry run",
    )
    parser.add_argument(
        "--dist", type=Path, help="also hold built artifacts in this directory to the tag"
    )
    parser.add_argument("--record", type=Path, default=CLA_RECORD, help="the CLA record to read")
    parser.add_argument(
        "--agreement", type=Path, default=CLA_AGREEMENT, help="the agreement to read"
    )
    parser.add_argument(
        "--codeowners", type=Path, default=CODEOWNERS, help="the CODEOWNERS file to read"
    )
    parser.add_argument(
        "--pyproject", type=Path, default=REPO_ROOT / "pyproject.toml", help="pyproject.toml"
    )
    parser.add_argument(
        "--changelog", type=Path, default=REPO_ROOT / "CHANGELOG.md", help="CHANGELOG.md"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    direct = arguments.files is not None or arguments.message is not None
    ranged = arguments.base is not None or arguments.head is not None
    if direct == ranged:
        parser.error("use exactly one mode: --files/--message, or --base/--head")
    commits: tuple[Commit, ...]
    try:
        if direct:
            if arguments.files is None or arguments.message is None:
                parser.error("--files and --message go together")
            commits = (Commit(sha=None, files=tuple(arguments.files), message=arguments.message),)
        else:
            if not arguments.base or not arguments.head:
                parser.error("--base and --head go together")
            commits = commits_from_range(arguments.base, arguments.head)
    except ChecklistInputError as error:
        print(f"error: {error}")
        return 2

    report = review(
        author=arguments.author,
        commits=commits,
        employer_owned=arguments.employer_owned,
        tag=arguments.tag,
        record=arguments.record,
        agreement=arguments.agreement,
        codeowners=arguments.codeowners,
        pyproject=arguments.pyproject,
        changelog=arguments.changelog,
        dist=arguments.dist,
    )
    print(as_json(report) if arguments.format == "json" else format_report(report))
    return report.exit_status


if __name__ == "__main__":
    sys.exit(main())
