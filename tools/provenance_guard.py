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

Usage::

    python tools/provenance_guard.py                      # verify, using the defaults
    python tools/provenance_guard.py --provenance-doc docs/PROVENANCE.md
    python tools/provenance_guard.py --regenerate         # sanctioned re-vendor only

Exit status is 0 when every guarded file matches, 1 otherwise.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 1

#: Local clutter that is never part of a vendored snapshot and never committed.
IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db"})
IGNORED_DIRS = frozenset({"__pycache__"})

#: A manifest row of ``docs/PROVENANCE.md``:
#: ``| `path` | `vault source` | `commit` | date |``
_PROVENANCE_ROW = re.compile(
    r"^\|\s*`(?P<path>[^`]+)`\s*\|\s*`(?P<source>[^`]+)`\s*\|\s*`(?P<commit>[^`]+)`\s*\|"
    r"\s*(?P<copied>[^|]*?)\s*\|\s*$"
)


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


@dataclass
class Report:
    """What the verification found. Empty lists everywhere means the guard passed."""

    checked: int = 0
    modified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)
    provenance_mismatch: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.modified or self.missing or self.unlisted or self.provenance_mismatch)


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


def verify(
    manifest: Manifest,
    root: Path,
    provenance_doc: Path | None = None,
) -> Report:
    """Compare the working tree under ``root`` with the manifest."""
    report = Report()

    for entry in manifest.entries:
        target = root / entry.path
        if not target.is_file():
            report.missing.append(entry.path)
            continue
        report.checked += 1
        if sha256_of(target) != entry.sha256:
            report.modified.append(entry.path)

    listed = manifest.paths
    report.unlisted = [
        path for path in files_in_guarded_trees(root, manifest) if path not in listed
    ]

    if provenance_doc is not None:
        report.provenance_mismatch = _cross_check_provenance(manifest, provenance_doc)

    return report


def _cross_check_provenance(manifest: Manifest, provenance_doc: Path) -> list[str]:
    """The manifest must mirror the PROVENANCE.md rows that fall in its guarded scope.

    This is what stops a manifest row from being quietly deleted to unguard a file, and what
    ties a re-vendor's hash refresh to its PROVENANCE row update.
    """
    rows = parse_provenance_rows(provenance_doc)
    in_scope = {path: value for path, value in rows.items() if manifest.covers(path)}
    problems: list[str] = []

    for path in sorted(set(in_scope) - manifest.paths):
        problems.append(f"{path}: listed in PROVENANCE.md but absent from the manifest")
    for path in sorted(manifest.paths - set(in_scope)):
        problems.append(f"{path}: in the manifest but not a PROVENANCE.md row in scope")
    for entry in manifest.entries:
        recorded = in_scope.get(entry.path)
        if recorded is None:
            continue
        source, commit = recorded
        if (entry.vault_source, entry.vault_commit) != (source, commit):
            problems.append(
                f"{entry.path}: manifest records {entry.vault_source}@{entry.vault_commit}, "
                f"PROVENANCE.md records {source}@{commit}"
            )
    return problems


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


def format_report(report: Report, manifest: Manifest, root: Path) -> str:
    lines: list[str] = []
    if report.ok:
        lines.append(
            f"provenance guard: OK — {report.checked} vendored file(s) byte-identical to the "
            f"manifest (vault {manifest.vault_repo}@{manifest.snapshot_commit})"
        )
        return "\n".join(lines)

    lines.append(f"provenance guard: FAILED under {root}")
    for path in report.modified:
        lines.append(f"  modified: {path} — bytes differ from the recorded snapshot")
    for path in report.missing:
        lines.append(f"  missing:  {path} — listed in the manifest, absent from the tree")
    for path in report.unlisted:
        lines.append(f"  unlisted: {path} — inside a guarded tree, absent from the manifest")
    for problem in report.provenance_mismatch:
        lines.append(f"  manifest: {problem}")
    lines.append("")
    lines.append(
        "Vendored files are byte-copy snapshots of the specification vault and are read-only "
        "(WA-11). If this is an in-place edit, revert it and file a spec defect instead; if it "
        "is a sanctioned vault-first re-vendor, update docs/PROVENANCE.md and regenerate this "
        "manifest in the same commit — see docs/governance/re-vendoring.md."
    )
    return "\n".join(lines)


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
        if args.regenerate:
            manifest = regenerate(manifest, root, args.manifest)
            print(
                f"provenance guard: manifest regenerated from {root} "
                f"({len(manifest.entries)} entries). This is a sanctioned-re-vendor action: "
                "the same commit must carry the new bytes, the docs/PROVENANCE.md row update, "
                "and the vault hash in its message (WA-11; WA-04 for fixtures)."
            )
        report = verify(manifest, root, args.provenance_doc)
    except ManifestError as exc:
        print(f"provenance guard: {exc}", file=sys.stderr)
        return 1

    print(format_report(report, manifest, root), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
