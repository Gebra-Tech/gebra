"""Provenance guard — vendored files must be byte-identical to their manifest (WA-11).

Everything listed in ``docs/PROVENANCE.md``'s manifest is a byte-copy snapshot of the
specification vault ``Gebra-Tech/initial-documents``. This script re-computes the SHA-256 of
every guarded file and compares it with the hash recorded in a manifest JSON, so an in-place
edit, a deletion, or a file quietly added to a guarded tree fails the build instead of being
noticed (or not) in review.

The script is deliberately dependency-free and repository-agnostic: it takes a manifest and a
root, so the same implementation guards the fixture corpus in the library repo and the
vendored documentation package in the companion delivery repo. It reads and hashes files —
it never imports, executes, or fetches anything (WA-07).

Reviewing a change asks a narrower question than gating a repository: not "is the vendored
surface intact" but "what does the guard say about the paths this change touches, and where
does each finding route". ``--only`` answers the first with the run above rather than a second
reading — :func:`verify` reads the whole guarded surface exactly as the CI job does and
:func:`scope_report` then keeps what that run said about the named paths. ``--format json``
answers the second by publishing each finding's routing beside it, so no surface reporting
these findings has to compose remediation copy of its own.

**A review scope narrows what is listed, never the verdict.** The exit status and the JSON
``ok`` are always the whole run's, because a change's *effect* need not land on a path the
change touches: deleting a manifest row leaves the file unlisted, and editing a
``docs/PROVENANCE.md`` row moves the cross-check — neither shows up under a scope naming only
the edited file. A scoped run that finds nothing in its own scope while the surface is broken
therefore still exits 1, says how many findings lie outside the scope, and tells the reader to
re-run without ``--only``. Nothing that reads this guard can pass a tree the CI job blocks.

Routing is not uniform, because the vendored surface is not: ``docs/PROVENANCE.md``'s sync
rules can record that a file has been *transferred* to living-document status, after which
editing it in place is sanctioned and owes no spec defect — while the manifest still has to be
refreshed in the same commit, so out-of-commit tampering is still caught. That state is read
from the provenance record at run time (:func:`parse_living_documents`); this script hard-codes
no path's exemption and no transfer's date.

Usage::

    python tools/provenance_guard.py                      # verify, using the defaults
    python tools/provenance_guard.py --provenance-doc docs/PROVENANCE.md
    python tools/provenance_guard.py --only <path> ...    # review scope: a change's own files
    python tools/provenance_guard.py --format json        # the same run, machine-readable
    python tools/provenance_guard.py --regenerate         # sanctioned re-vendor only

Exit status is 0 when every guarded file matches, 1 otherwise — in either output format.

A sanctioned re-vendor (vault-first, per WA-11/WA-04) updates the vendored bytes and
regenerates this manifest **in the same commit**; there is no bypass flag. See
``docs/governance/re-vendoring.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 1

#: How a guarded path's bytes are governed. ``VENDORED`` is the default and the rule: a
#: byte-copy snapshot of the vault, read-only here. ``LIVING_DOCUMENT`` is what a recorded
#: transfer in ``docs/PROVENANCE.md`` makes of a path — see :func:`parse_living_documents`.
VENDORED = "vendored"
LIVING_DOCUMENT = "living-document"

#: The four things the guard reports, in the order the report prints them.
MODIFIED = "modified"
MISSING = "missing"
UNLISTED = "unlisted"
MANIFEST = "manifest"
FINDING_KINDS = (MODIFIED, MISSING, UNLISTED, MANIFEST)

_KIND_PREFIX = {
    MODIFIED: "  modified: ",
    MISSING: "  missing:  ",
    UNLISTED: "  unlisted: ",
    MANIFEST: "  manifest: ",
}

#: What a reader does about a finding on a read-only vendored file. Carried in both output
#: formats so that no surface reporting this guard's findings composes remediation of its own.
REMEDIATION_VENDORED = (
    "Vendored files are byte-copy snapshots of the specification vault and are read-only "
    "(WA-11). If this is an in-place edit, revert it and file a spec defect instead; if it "
    "is a sanctioned vault-first re-vendor, update docs/PROVENANCE.md and regenerate this "
    "manifest in the same commit — see docs/governance/re-vendoring.md."
)

#: The other routing: a path the provenance record has transferred. Editing it is sanctioned,
#: so the WA-03 spec-defect protocol is not what it owes — the same-commit manifest refresh is.
REMEDIATION_LIVING = (
    "{paths}: not a read-only snapshot. docs/PROVENANCE.md records this repository's transfer "
    "of it to living-document status ({records}), so an in-place edit is sanctioned and owes "
    "no spec defect. What the transfer does not waive is this manifest: land the edit as "
    "exactly one commit that cites the justification the file's own update-discipline section "
    "requires and regenerates the manifest in that same commit "
    "(python tools/provenance_guard.py --regenerate), so an edit arriving without its refresh "
    "is still caught here."
)

#: What a reader does when the run failed somewhere the review scope does not name. The
#: verdict is the whole run's, so this is never a milder outcome than the unscoped one.
REMEDIATION_OUTSIDE_SCOPE = (
    "A review scope narrows what this report lists, never what it decides: the exit status "
    "above is the whole run's. Some of what failed is on a path the scope does not name — a "
    "manifest row removed, a docs/PROVENANCE.md row moved, or a file the change did not "
    "touch — so re-run without --only to list every finding before judging the change."
)

#: Local clutter that is never part of a vendored snapshot and never committed.
IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db"})
IGNORED_DIRS = frozenset({"__pycache__"})

#: A manifest row of ``docs/PROVENANCE.md``:
#: ``| `path` | `vault source` | `commit` | date |``
_PROVENANCE_ROW = re.compile(
    r"^\|\s*`(?P<path>[^`]+)`\s*\|\s*`(?P<source>[^`]+)`\s*\|\s*`(?P<commit>[^`]+)`\s*\|"
    r"\s*(?P<copied>[^|]*?)\s*\|\s*$"
)

#: A sync rule of ``docs/PROVENANCE.md`` that carves a path out of the read-only policy. The
#: rule runs from the ``**Exception (WA-11):**`` label and its backticked path to the end of
#: its own block — a blank line, the next numbered rule, or the next heading, whichever comes
#: first, so a rule written without a trailing blank line cannot absorb the section after it.
#: :data:`_LIVING_MARKER` and :data:`_TRANSFER_RECORD` decide what the block says.
_EXCEPTION_RULE = re.compile(
    r"\*\*Exception \(WA-11\):\*\*\s*`(?P<path>[^`]+)`(?P<body>.*?)"
    r"(?=\n[ \t]*\n|\n[ \t]*\d+\.\s|\n#|\Z)",
    re.DOTALL,
)

#: The status such a rule must record for the carve-out to be a transfer rather than a note.
_LIVING_MARKER = "living-document status"

#: …and the ratified decision record that transferred it. WA-11 makes a file the repository's
#: living document *only after the transfer is recorded*, so a rule naming no ratified record
#: records no transfer, and the path stays read-only vendored.
_TRANSFER_RECORD = re.compile(r"\((?P<record>[A-Z]+-\d+), ratified (?P<date>\d{4}-\d{2}-\d{2})\)")


class ManifestError(RuntimeError):
    """The manifest itself is unusable (missing, malformed, wrong schema)."""


@dataclass(frozen=True)
class Entry:
    """One vendored file: where it came from and what its bytes must hash to."""

    path: str
    sha256: str
    vault_source: str
    vault_commit: str


@dataclass(frozen=True)
class Manifest:
    """The recorded expectation for one repository's share of the vendored surface."""

    schema_version: int
    vault_repo: str
    snapshot_commit: str
    guarded_trees: tuple[str, ...]
    guarded_files: tuple[str, ...]
    entries: tuple[Entry, ...]

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(entry.path for entry in self.entries)

    def covers(self, path: str) -> bool:
        """Is ``path`` (repo-relative, POSIX) inside this manifest's guarded scope?"""
        if path in self.guarded_files:
            return True
        return any(path.startswith(f"{tree}/") for tree in self.guarded_trees)


@dataclass(frozen=True)
class Finding:
    """One thing the guard found, and where it routes.

    ``classification`` is what governs the path's bytes (:data:`VENDORED` or
    :data:`LIVING_DOCUMENT`) and therefore which remediation applies; it is computed from the
    provenance record, never from the path's name.
    """

    kind: str
    path: str
    detail: str
    classification: str = VENDORED
    record: str = ""

    @property
    def line(self) -> str:
        """The report line, without its kind prefix."""
        separator = ": " if self.kind == MANIFEST else " — "
        return f"{self.path}{separator}{self.detail}"

    @property
    def remediation(self) -> str:
        """The route this finding takes — the copy every surface relays instead of writing."""
        if self.classification == LIVING_DOCUMENT:
            return REMEDIATION_LIVING.format(paths=self.path, records=self.record)
        return REMEDIATION_VENDORED


@dataclass(frozen=True)
class Scope:
    """A review scope: the paths ``--only`` named, split by whether this manifest covers them."""

    selected: tuple[str, ...]
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]


@dataclass
class Report:
    """What the verification found.

    ``findings`` is what this report *lists*; ``outside_scope`` is what the same run found on
    paths a review scope did not name. The verdict reads both, so narrowing the listing can
    never narrow the verdict — see :func:`scope_report`.
    """

    checked: int = 0
    findings: tuple[Finding, ...] = ()
    outside_scope: tuple[Finding, ...] = ()
    living_documents: Mapping[str, str] = field(default_factory=dict)
    scope: Scope | None = None

    @property
    def ok(self) -> bool:
        return not (self.findings or self.outside_scope)

    def of_kind(self, kind: str) -> list[str]:
        return [finding.path for finding in self.findings if finding.kind == kind]

    @property
    def modified(self) -> list[str]:
        return self.of_kind(MODIFIED)

    @property
    def missing(self) -> list[str]:
        return self.of_kind(MISSING)

    @property
    def unlisted(self) -> list[str]:
        return self.of_kind(UNLISTED)

    @property
    def provenance_mismatch(self) -> list[str]:
        return [finding.line for finding in self.findings if finding.kind == MANIFEST]


def sha256_of(path: Path) -> str:
    """Hash a file in binary mode — no decoding, no newline translation."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(manifest_path: Path) -> Manifest:
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")
    try:
        raw: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ManifestError(f"manifest is not valid JSON: {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):  # pragma: no cover - defensive
        raise ManifestError(f"manifest must be a JSON object: {manifest_path}")
    version = raw.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"manifest schema_version {version!r} is not the supported "
            f"{MANIFEST_SCHEMA_VERSION} ({manifest_path})"
        )
    entries = tuple(
        Entry(
            path=str(item["path"]),
            sha256=str(item["sha256"]),
            vault_source=str(item["vault_source"]),
            vault_commit=str(item["vault_commit"]),
        )
        for item in raw["entries"]
    )
    return Manifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        vault_repo=str(raw["vault_repo"]),
        snapshot_commit=str(raw["snapshot_commit"]),
        guarded_trees=tuple(str(tree) for tree in raw.get("guarded_trees", ())),
        guarded_files=tuple(str(name) for name in raw.get("guarded_files", ())),
        entries=entries,
    )


def files_in_guarded_trees(root: Path, manifest: Manifest) -> list[str]:
    """Every file currently inside a guarded tree, repo-relative and POSIX-separated."""
    found: list[str] = []
    for tree in manifest.guarded_trees:
        base = root / tree
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.name in IGNORED_NAMES or IGNORED_DIRS.intersection(path.parts):
                continue
            found.append(path.relative_to(root).as_posix())
    return sorted(found)


def parse_provenance_rows(provenance_doc: Path) -> dict[str, tuple[str, str]]:
    """Read ``docs/PROVENANCE.md``'s manifest table as ``{path: (vault_source, commit)}``."""
    rows: dict[str, tuple[str, str]] = {}
    for line in provenance_doc.read_text(encoding="utf-8").splitlines():
        match = _PROVENANCE_ROW.match(line.strip())
        if match is None:
            continue
        rows[match["path"]] = (match["source"], match["commit"])
    if not rows:
        raise ManifestError(f"no manifest rows found in {provenance_doc}")
    return rows


def parse_living_documents(provenance_doc: Path) -> dict[str, str]:
    """Paths ``docs/PROVENANCE.md``'s sync rules record as transferred living documents.

    Returns ``{path: the record that transferred it}``. WA-11 makes such a path the
    repository's living document *only after the transfer is recorded*, so a carve-out rule
    that names no ratified decision record is not a transfer and yields nothing here: the path
    stays read-only vendored, and an edit to it routes to the spec-defect protocol as usual.

    Reading the state instead of hard-coding it is the point. The exemption a reviewer applies
    and the exemption CI applies are then one parse of one record rather than two readings.
    """
    text = provenance_doc.read_text(encoding="utf-8")
    living: dict[str, str] = {}
    for rule in _EXCEPTION_RULE.finditer(text):
        body = rule["body"]
        if _LIVING_MARKER not in body:
            continue
        record = _TRANSFER_RECORD.search(body)
        if record is None:
            continue
        living[rule["path"]] = f"{record['record']}, ratified {record['date']}"
    return living


def verify(
    manifest: Manifest,
    root: Path,
    provenance_doc: Path | None = None,
) -> Report:
    """Compare the working tree under ``root`` with the manifest."""
    living = parse_living_documents(provenance_doc) if provenance_doc is not None else {}

    def found(kind: str, path: str, detail: str) -> Finding:
        record = living.get(path)
        if record is None:
            return Finding(kind, path, detail, VENDORED)
        return Finding(kind, path, detail, LIVING_DOCUMENT, record)

    checked = 0
    modified: list[Finding] = []
    missing: list[Finding] = []
    for entry in manifest.entries:
        target = root / entry.path
        if not target.is_file():
            missing.append(
                found(MISSING, entry.path, "listed in the manifest, absent from the tree")
            )
            continue
        checked += 1
        if sha256_of(target) != entry.sha256:
            modified.append(
                found(
                    MODIFIED,
                    entry.path,
                    (
                        "bytes differ from the recorded hash (living document; the manifest "
                        "was not refreshed in this commit)"
                        if entry.path in living
                        else "bytes differ from the recorded snapshot"
                    ),
                )
            )

    listed = manifest.paths
    unlisted = [
        found(UNLISTED, path, "inside a guarded tree, absent from the manifest")
        for path in files_in_guarded_trees(root, manifest)
        if path not in listed
    ]

    mismatch: list[Finding] = []
    if provenance_doc is not None:
        mismatch = _cross_check_provenance(manifest, provenance_doc, found)

    return Report(
        checked=checked,
        findings=tuple(modified + missing + unlisted + mismatch),
        living_documents=living,
    )


def _cross_check_provenance(
    manifest: Manifest,
    provenance_doc: Path,
    found: Callable[[str, str, str], Finding],
) -> list[Finding]:
    """The manifest must mirror the PROVENANCE.md rows that fall in its guarded scope.

    This is what stops a manifest row from being quietly deleted to unguard a file, and what
    ties a re-vendor's hash refresh to its PROVENANCE row update.
    """
    rows = parse_provenance_rows(provenance_doc)
    in_scope = {path: value for path, value in rows.items() if manifest.covers(path)}
    problems: list[Finding] = []

    for path in sorted(set(in_scope) - manifest.paths):
        problems.append(
            found(MANIFEST, path, "listed in PROVENANCE.md but absent from the manifest")
        )
    for path in sorted(manifest.paths - set(in_scope)):
        problems.append(
            found(MANIFEST, path, "in the manifest but not a PROVENANCE.md row in scope")
        )
    for entry in manifest.entries:
        recorded = in_scope.get(entry.path)
        if recorded is None:
            continue
        source, commit = recorded
        if (entry.vault_source, entry.vault_commit) != (source, commit):
            problems.append(
                found(
                    MANIFEST,
                    entry.path,
                    f"manifest records {entry.vault_source}@{entry.vault_commit}, "
                    f"PROVENANCE.md records {source}@{commit}",
                )
            )
    return problems


def normalize_selection(tokens: Iterable[str]) -> tuple[str, ...]:
    """``--only`` tokens as repo-relative POSIX paths, de-duplicated, order preserved.

    ``git diff --name-only`` output pastes in unchanged; so does the same list with ``./``
    prefixes or Windows separators.
    """
    seen: dict[str, None] = {}
    for token in tokens:
        path = token.strip().replace("\\", "/").lstrip()
        while path.startswith("./"):
            path = path[2:]
        if path:
            seen.setdefault(path.rstrip("/"), None)
    return tuple(seen)


def scope_report(report: Report, manifest: Manifest, selected: Sequence[str]) -> Report:
    """Narrow what a report *lists* to the paths a change touched — never what it decides.

    The run that produced ``report`` read the whole guarded surface exactly as the CI job
    does. This keeps what it said about the named paths, and moves everything else to
    :attr:`Report.outside_scope`, which the verdict still counts.

    That split is the whole point. A change's *effect* need not land on a path the change
    touches: deleting a manifest row leaves the file itself unlisted, and editing a
    ``docs/PROVENANCE.md`` row moves the cross-check — neither appears under a scope naming
    only what the diff edited. A scope that decided the verdict would therefore pass trees the
    CI job blocks, which is exactly the disagreement a review scope exists to make impossible.

    A named path this manifest does not cover is not an error: a change's file list spans the
    whole repository, and most of it is not vendored. Such paths are recorded as out of scope,
    which is the answer to "does the provenance guard apply to this change at all".
    """
    in_scope = tuple(path for path in selected if manifest.covers(path))
    covered = set(in_scope)
    return Report(
        checked=report.checked,
        findings=tuple(finding for finding in report.findings if finding.path in covered),
        outside_scope=tuple(finding for finding in report.findings if finding.path not in covered),
        living_documents=report.living_documents,
        scope=Scope(
            selected=tuple(selected),
            in_scope=in_scope,
            out_of_scope=tuple(path for path in selected if path not in covered),
        ),
    )


def regenerate(manifest: Manifest, root: Path, manifest_path: Path) -> Manifest:
    """Rewrite the manifest from the working tree — the sanctioned re-vendor step."""
    listed = {entry.path: entry for entry in manifest.entries}
    present = sorted(set(listed) | set(files_in_guarded_trees(root, manifest)))

    entries: list[Entry] = []
    for path in present:
        target = root / path
        if not target.is_file():
            continue
        previous = listed.get(path)
        entries.append(
            Entry(
                path=path,
                sha256=sha256_of(target),
                vault_source=previous.vault_source if previous else "UNRECORDED",
                vault_commit=previous.vault_commit if previous else "UNRECORDED",
            )
        )

    refreshed = Manifest(
        schema_version=manifest.schema_version,
        vault_repo=manifest.vault_repo,
        snapshot_commit=manifest.snapshot_commit,
        guarded_trees=manifest.guarded_trees,
        guarded_files=manifest.guarded_files,
        entries=tuple(entries),
    )
    write_manifest(refreshed, manifest_path)
    return refreshed


def write_manifest(manifest: Manifest, manifest_path: Path) -> None:
    document: dict[str, Any] = {
        "schema_version": manifest.schema_version,
        "_comment": (
            "Byte-copy expectations for the vendored files this repository holds (WA-11). "
            "Regenerated only by a sanctioned vault-first re-vendor, in the same commit as "
            "the new bytes and the docs/PROVENANCE.md row update — see "
            "docs/governance/re-vendoring.md."
        ),
        "vault_repo": manifest.vault_repo,
        "snapshot_commit": manifest.snapshot_commit,
        "guarded_trees": list(manifest.guarded_trees),
        "guarded_files": list(manifest.guarded_files),
        "entries": [
            {
                "path": entry.path,
                "sha256": entry.sha256,
                "vault_source": entry.vault_source,
                "vault_commit": entry.vault_commit,
            }
            for entry in manifest.entries
        ],
    }
    serialized = json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False)
    manifest_path.write_text(serialized + "\n", encoding="utf-8")


def _headline(report: Report, manifest: Manifest) -> str:
    """The verdict line, and — under ``--only`` — what the scope it was reached over covers."""
    vault = f"(vault {manifest.vault_repo}@{manifest.snapshot_commit})"
    if report.scope is None:
        return (
            f"provenance guard: OK — {report.checked} vendored file(s) byte-identical to the "
            f"manifest {vault}"
        )
    named = len(report.scope.selected)
    if not report.scope.in_scope:
        return (
            f"provenance guard: OK — no guarded file in the review scope ({named} path(s) "
            f"named, none of them vendored here); {report.checked} guarded file(s) read"
        )
    return (
        f"provenance guard: OK — {len(report.scope.in_scope)} path(s) in the review scope "
        f"byte-identical to the manifest {vault}; {report.checked} guarded file(s) read"
    )


def _remediation_paragraphs(report: Report) -> list[str]:
    """One paragraph per routing present, so each failure is answered in its own terms."""
    paragraphs: list[str] = []
    if any(finding.classification == VENDORED for finding in report.findings):
        paragraphs.append(REMEDIATION_VENDORED)
    living = [finding for finding in report.findings if finding.classification == LIVING_DOCUMENT]
    if living:
        paragraphs.append(
            REMEDIATION_LIVING.format(
                paths=", ".join(dict.fromkeys(finding.path for finding in living)),
                records="; ".join(dict.fromkeys(finding.record for finding in living)),
            )
        )
    return paragraphs


def format_report(report: Report, manifest: Manifest, root: Path) -> str:
    lines: list[str] = []
    if report.ok:
        return _headline(report, manifest)

    lines.append(f"provenance guard: FAILED under {root}")
    for kind in FINDING_KINDS:
        for finding in report.findings:
            if finding.kind == kind:
                lines.append(f"{_KIND_PREFIX[kind]}{finding.line}")
    if report.outside_scope:
        lines.append(
            f"  outside:  {len(report.outside_scope)} further finding(s) on path(s) this "
            "review scope does not name — the guarded surface is not intact"
        )
    if report.scope is not None:
        lines.append(
            f"  (review scope: {len(report.scope.in_scope)} of {len(report.scope.selected)} "
            f"named path(s) guarded here; {report.checked} guarded file(s) read)"
        )
    paragraphs = _remediation_paragraphs(report)
    if report.outside_scope:
        paragraphs.append(REMEDIATION_OUTSIDE_SCOPE)
    for paragraph in paragraphs:
        lines.append("")
        lines.append(paragraph)
    return "\n".join(lines)


def format_json(report: Report, manifest: Manifest, root: Path) -> str:
    """The same run, machine-readable: every finding beside the route it takes."""
    payload: dict[str, Any] = {
        "ok": report.ok,
        "root": str(root),
        "checked": report.checked,
        "vault_repo": manifest.vault_repo,
        "snapshot_commit": manifest.snapshot_commit,
        "guarded_trees": list(manifest.guarded_trees),
        "guarded_files": list(manifest.guarded_files),
        "living_documents": [
            {"path": path, "record": record}
            for path, record in sorted(report.living_documents.items())
        ],
        # The verdict counts these; the listing does not. A reader that reports `findings`
        # without this number would be reporting a milder outcome than `ok` records.
        "findings_outside_scope": len(report.outside_scope),
        "findings": [
            {
                "kind": finding.kind,
                "path": finding.path,
                "classification": finding.classification,
                "detail": finding.detail,
                "remediation": finding.remediation,
            }
            for kind in FINDING_KINDS
            for finding in report.findings
            if finding.kind == kind
        ],
        "scope": None
        if report.scope is None
        else {
            "selected": list(report.scope.selected),
            "in_scope": list(report.scope.in_scope),
            "out_of_scope": list(report.scope.out_of_scope),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_parser(default_root: Path, default_manifest: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="provenance_guard.py",
        description="Verify that vendored files are byte-identical to the recorded manifest.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=default_manifest,
        help=f"hash manifest to verify against (default: {default_manifest})",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"repository root the manifest paths are relative to (default: {default_root})",
    )
    parser.add_argument(
        "--provenance-doc",
        type=Path,
        default=None,
        help="also cross-check the manifest against this docs/PROVENANCE.md manifest table",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="PATH",
        default=None,
        help=(
            "review scope: report only what this run found about the named path(s). "
            "Repeatable; takes repo-relative paths, so `git diff --name-only` output pastes "
            "in unchanged, and a named path this manifest does not guard is reported as out "
            "of scope rather than narrowing the run quietly"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help=(
            "text (default) prints the human report; json prints every finding with its "
            "classification and its remediation, plus the transferred living documents this "
            "run read from the provenance record"
        ),
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="rewrite the manifest from the working tree (sanctioned re-vendor commits only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = build_parser(here.parent, here / "provenance-manifest.json")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        root: Path = args.root
        if args.regenerate and args.only is not None:
            # A review scope filters a report; it never selects what a re-vendor rewrites.
            # Silently accepting both would read as "regenerate just these paths", which is
            # not what happens and not something the manifest can express.
            raise ManifestError(
                "--only is a review scope over the report, not a selection for --regenerate; "
                "run the regeneration without it"
            )
        if args.regenerate:
            manifest = regenerate(manifest, root, args.manifest)
            print(
                f"provenance guard: manifest regenerated from {root} "
                f"({len(manifest.entries)} entries). This is a sanctioned-re-vendor action: "
                "the same commit must carry the new bytes, the docs/PROVENANCE.md row update, "
                "and the vault hash in its message (WA-11; WA-04 for fixtures)."
            )
        report = verify(manifest, root, args.provenance_doc)
        if args.only is not None:
            report = scope_report(report, manifest, normalize_selection(args.only))
    except ManifestError as exc:
        print(f"provenance guard: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        # One machine-readable document on stdout in both outcomes; the exit status carries
        # the verdict, exactly as it does for the text report.
        print(format_json(report, manifest, root), file=sys.stdout)
    else:
        print(format_report(report, manifest, root), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
