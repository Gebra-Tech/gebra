"""The provenance guard's review scope and routing, and the skill that reads them (TOOL-05).

Reviewing a change asks a narrower question than gating a repository: not "is the vendored
surface intact" but "what does the guard say about the paths this change touches, and what does
each finding owe". Before this card `/provenance-check` answered both from prose written beside
the guard — two readings of one contract, and one drift away from a skill waving through what CI
fails. ``--only`` and ``--format json`` make it one reading, and this module pins that it stays
one.

Three things are held here.

**A scoped run says exactly what the full run said about the paths it names — and reaches the
full run's verdict.** :func:`~tools.provenance_guard.scope_report` filters the report
:func:`~tools.provenance_guard.verify` already produced, and the invariant on the listing is
set equality per path, asserted with all four finding kinds seeded at once. The invariant on
the *verdict* is stronger and separate, because the adversarial pre-review found the first
version of this card failing it: a change's effect need not land on a path the change touches
— a deleted manifest row leaves the *fixture* unlisted, a moved ``docs/PROVENANCE.md`` row
moves the cross-check — so a scope that decided the verdict would report green over a tree CI
blocks. All three of the reviewers' reproductions are held below, plus a parametrised pin that
no scope shape changes the verdict either way.

**The one sanctioned special case is computed, not remembered.** ``docs/PROVENANCE.md``'s sync
rules can record that a path has been transferred to living-document status; after that, an
in-place edit is sanctioned and owes no spec defect, while the manifest refresh is still owed
(PD-035's ratified guard mechanics). The guard reads that state from the record at run time, so
the pre-transfer and post-transfer routings of *the same seeded edit* differ only in what the
record says — which is what the tests here demonstrate, on the real provenance record and on
synthetic ones alike.

**The skill and this guard stay one computation.** The staged skill must reach its integrity
verdict by running this script, must still carry the WA-11 re-vendor evidence no script can find
in a working tree, and must restate neither the transfer rule nor the file it applies to — a
rule named in prose is a rule that can drift. Once the owner installs it (see the setup note),
the installed file must be the staged one byte for byte.

Nothing here executes a workflow node, calls a model, or opens a socket (WA-07). Every subprocess
runs this repository's own guard under this interpreter, which is the exact command the skill and
the CI jobs run, and every seeded edit is applied to a *copy* — the vendored surface is read-only
(WA-11), and one test watches its bytes across a scoped run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.provenance_guard import (
    LIVING_DOCUMENT,
    MANIFEST,
    MANIFEST_SCHEMA_VERSION,
    MISSING,
    MODIFIED,
    REMEDIATION_VENDORED,
    UNLISTED,
    VENDORED,
    Entry,
    Manifest,
    Report,
    format_report,
    load_manifest,
    normalize_selection,
    parse_living_documents,
    regenerate,
    scope_report,
    verify,
    write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "tools" / "provenance_guard.py"
MANIFEST_PATH = REPO_ROOT / "tools" / "provenance-manifest.json"
CORPUS = REPO_ROOT / "tests" / "fixtures" / "properties"

#: A fixture of the vendored corpus, used as a review scope that names a real guarded path.
GUARDED_FIXTURE = (
    "tests/fixtures/properties/graph-well-formed/positive-01-linear-document-pipeline.yaml"
)

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI, where cross-repository assertions skip rather than fake (the pattern
# tests/test_provenance_guard.py established and tests/test_board_integrity.py follows).
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
COMPANION_MANIFEST = COMPANION / "tools" / "provenance-manifest.json"
PROVENANCE_DOC = COMPANION / "docs" / "PROVENANCE.md"
#: The skill as staged for the owner to install — writable by the session that built it.
STAGED_SKILL = COMPANION / "docs" / "setups" / "TOOL-05" / "provenance-check-SKILL.md"
#: The installed skill, reached through the companion's neutral ``tools/`` surface so the public
#: tree pins it without naming an agent-tooling path (PD-050 hygiene, as for the other skills).
INSTALLED_SKILL = COMPANION / "tools" / "provenance-check.md"

requires_companion = pytest.mark.skipif(
    not PROVENANCE_DOC.is_file(),
    reason="the development-process repository is not checked out beside this one",
)
requires_staged_skill = pytest.mark.skipif(
    not STAGED_SKILL.is_file(), reason="the staged skill file is not present"
)
requires_installed_skill = pytest.mark.skipif(
    not INSTALLED_SKILL.is_file(),
    reason="the upgraded skill is not installed yet (see docs/setups/TOOL-05.md)",
)


# ── A synthetic repository, so the mechanism is testable without the vendored trees ──

_SYNTHETIC_DOC = """# Provenance — sandbox

## Sync rules

1. **The vault copy is authoritative.** Never edit a vendored file here.
2. **Fixture corpus**: refreshed only alongside a decision record.
{exception}
## Manifest

| Vendored file | Vault source | Vault commit | Copied |
|---|---|---|---|
| `vendored/spec.md` | `vault/spec.md` | `abc1234` | 2026-01-01 |
| `vendored/notes.md` | `vault/notes.md` | `abc1234` | 2026-01-01 |
"""

#: The record of a transfer: the carve-out, the status it confers, and the ratified ruling.
_TRANSFERRED = """3. **Exception (WA-11):** `vendored/spec.md` (row below) transferred to
   living-document status at the sandbox kickoff transfer (PD-999, ratified 2026-01-02). From
   that date the manifest row records origin only, and the file is edited directly here.

"""

#: The same carve-out with no ratified ruling behind it — a proposal, not a transfer.
_UNRATIFIED = """3. **Exception (WA-11):** `vendored/spec.md` (row below) is proposed for
   living-document status at a sandbox kickoff transfer (PD-999, drafted 2026-01-02).

"""


def _synthetic(tmp_path: Path, exception: str = "") -> tuple[Path, Path, Path]:
    """A guarded tree, its manifest and its provenance record: ``(root, manifest, doc)``."""
    root = tmp_path / "sandbox"
    (root / "vendored").mkdir(parents=True)
    (root / "vendored" / "spec.md").write_text("frozen bytes\n", encoding="utf-8")
    (root / "vendored" / "notes.md").write_text("more frozen bytes\n", encoding="utf-8")

    doc = root / "docs" / "PROVENANCE.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(_SYNTHETIC_DOC.format(exception=exception), encoding="utf-8")

    manifest_path = root / "tools" / "provenance-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    write_manifest(
        Manifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            vault_repo="Example-Org/sandbox-vault",
            snapshot_commit="abc1234",
            guarded_trees=("vendored",),
            guarded_files=(),
            entries=tuple(
                Entry(
                    path=f"vendored/{name}",
                    sha256=hashlib.sha256((root / "vendored" / name).read_bytes()).hexdigest(),
                    vault_source=f"vault/{name}",
                    vault_commit="abc1234",
                )
                for name in ("notes.md", "spec.md")
            ),
        ),
        manifest_path,
    )
    return root, manifest_path, doc


def _report(root: Path, manifest_path: Path, doc: Path | None = None) -> Report:
    return verify(load_manifest(manifest_path), root, doc)


def _run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the guard exactly as CI does — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_every_kind(root: Path, manifest_path: Path, doc: Path) -> None:
    """One tree carrying all four findings at once: modified, missing, unlisted, manifest."""
    (root / "vendored" / "spec.md").write_text("edited in place\n", encoding="utf-8")
    (root / "vendored" / "notes.md").unlink()
    (root / "vendored" / "extra.md").write_text("added by hand\n", encoding="utf-8")
    manifest = load_manifest(manifest_path)
    write_manifest(
        Manifest(
            schema_version=manifest.schema_version,
            vault_repo=manifest.vault_repo,
            snapshot_commit=manifest.snapshot_commit,
            guarded_trees=manifest.guarded_trees,
            guarded_files=manifest.guarded_files,
            entries=tuple(
                entry
                if entry.path != "vendored/notes.md"
                else Entry(entry.path, entry.sha256, entry.vault_source, "0000000")
                for entry in manifest.entries
            ),
        ),
        manifest_path,
    )
    assert doc.is_file()


# ── The review scope: a filter over the run CI made, never a second reading ──


def test_a_scoped_run_reports_exactly_what_the_full_run_says_about_that_path(
    tmp_path: Path,
) -> None:
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    _seed_every_kind(root, manifest_path, doc)
    manifest = load_manifest(manifest_path)
    full = verify(manifest, root, doc)

    scoped = scope_report(full, manifest, ("vendored/spec.md",))

    assert [f.path for f in scoped.findings] == ["vendored/spec.md"]
    assert set(scoped.findings) == {f for f in full.findings if f.path == "vendored/spec.md"}


def test_the_scope_cannot_hide_a_finding_of_any_kind(tmp_path: Path) -> None:
    """Set equality per path, over a tree seeded with every kind the guard reports."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    _seed_every_kind(root, manifest_path, doc)
    manifest = load_manifest(manifest_path)
    full = verify(manifest, root, doc)
    assert {f.kind for f in full.findings} == {MODIFIED, MISSING, UNLISTED, MANIFEST}

    for path in sorted({f.path for f in full.findings}):
        scoped = scope_report(full, manifest, (path,))
        assert set(scoped.findings) == {f for f in full.findings if f.path == path}

    everything = scope_report(full, manifest, tuple(sorted({f.path for f in full.findings})))
    assert set(everything.findings) == set(full.findings)


def test_a_path_the_manifest_does_not_guard_is_reported_out_of_scope(tmp_path: Path) -> None:
    """A change's file list spans the whole repository; most of it is not vendored."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    manifest = load_manifest(manifest_path)

    scoped = scope_report(
        verify(manifest, root, doc), manifest, ("vendored/spec.md", "src/gebra/ir/model.py")
    )

    assert scoped.scope is not None
    assert scoped.scope.in_scope == ("vendored/spec.md",)
    assert scoped.scope.out_of_scope == ("src/gebra/ir/model.py",)


def test_a_scope_naming_nothing_guarded_is_green_on_an_intact_tree(tmp_path: Path) -> None:
    """The skill's "does this apply at all" question, answered by the guard rather than a rule."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    manifest = load_manifest(manifest_path)

    scoped = scope_report(verify(manifest, root, doc), manifest, ("README.md", "pyproject.toml"))

    assert scoped.ok
    headline = format_report(scoped, manifest, root)
    assert "no guarded file in the review scope" in headline
    assert "2 path(s) named" in headline


def test_the_same_scope_is_not_green_when_the_surface_is_broken(tmp_path: Path) -> None:
    """The scope narrows the listing, never the verdict — the pre-review's blocking finding.

    A change's *effect* need not land on a path the change touches, so a scope that decided
    the verdict would report green over a tree the CI job blocks.
    """
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    _seed_every_kind(root, manifest_path, doc)
    manifest = load_manifest(manifest_path)
    full = verify(manifest, root, doc)

    scoped = scope_report(full, manifest, ("README.md", "pyproject.toml"))

    assert not scoped.ok
    assert scoped.findings == ()
    assert set(scoped.outside_scope) == set(full.findings)
    printed = format_report(scoped, manifest, root)
    assert "FAILED" in printed
    assert f"{len(full.findings)} further finding(s)" in printed
    assert "re-run without --only" in printed


@pytest.mark.parametrize(
    "scope",
    [
        (),
        ("README.md",),
        ("vendored/spec.md",),
        ("vendored/notes.md", "src/gebra/ir/model.py"),
        ("vendored/spec.md", "vendored/notes.md", "vendored/extra.md"),
    ],
)
def test_no_review_scope_can_change_the_verdict(tmp_path: Path, scope: tuple[str, ...]) -> None:
    """The structural claim, over every scope shape a diff can produce."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    manifest = load_manifest(manifest_path)
    clean = verify(manifest, root, doc)
    assert scope_report(clean, manifest, scope).ok is clean.ok is True

    _seed_every_kind(root, manifest_path, doc)
    broken = verify(load_manifest(manifest_path), root, doc)

    assert scope_report(broken, manifest, scope).ok is broken.ok is False


def test_a_scoped_run_still_reads_the_whole_guarded_surface(tmp_path: Path) -> None:
    """`checked` is the full count under any scope: one reading, then a filter."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    manifest = load_manifest(manifest_path)
    full = verify(manifest, root, doc)

    assert scope_report(full, manifest, ("vendored/spec.md",)).checked == full.checked == 2


@pytest.mark.parametrize(
    "token",
    ["vendored/spec.md", "./vendored/spec.md", "vendored\\spec.md", "  vendored/spec.md  "],
)
def test_every_path_form_a_diff_produces_resolves(token: str) -> None:
    assert normalize_selection([token]) == ("vendored/spec.md",)


def test_the_same_path_named_twice_is_selected_once() -> None:
    assert normalize_selection(["a/b.md", "./a/b.md", "a/b.md"]) == ("a/b.md",)


def test_a_scoped_review_never_writes_to_the_vendored_corpus() -> None:
    """The corpus is read-only (WA-11); a review reads it and nothing else."""

    def digest() -> str:
        rolling = hashlib.sha256()
        for path in sorted(CORPUS.rglob("*")):
            if path.is_file():
                rolling.update(path.relative_to(CORPUS).as_posix().encode())
                rolling.update(path.read_bytes())
        return rolling.hexdigest()

    before = digest()
    result = _run_guard("--only", GUARDED_FIXTURE)
    assert result.returncode == 0, result.stderr
    assert digest() == before


def test_the_unscoped_report_is_unchanged_by_the_review_scope(tmp_path: Path) -> None:
    """The gate's own output is what the contributor guide renders; the scope never touches it."""
    root, manifest_path, doc = _synthetic(tmp_path)
    manifest = load_manifest(manifest_path)
    assert format_report(verify(manifest, root), manifest, root) == (
        "provenance guard: OK — 2 vendored file(s) byte-identical to the manifest "
        "(vault Example-Org/sandbox-vault@abc1234)"
    )

    (root / "vendored" / "spec.md").write_text("edited to make a test pass\n", encoding="utf-8")
    (root / "vendored" / "notes.md").unlink()
    (root / "vendored" / "extra.md").write_text("added by hand\n", encoding="utf-8")

    lines = format_report(verify(manifest, root), manifest, root).splitlines()
    assert lines[:4] == [
        f"provenance guard: FAILED under {root}",
        "  modified: vendored/spec.md — bytes differ from the recorded snapshot",
        "  missing:  vendored/notes.md — listed in the manifest, absent from the tree",
        "  unlisted: vendored/extra.md — inside a guarded tree, absent from the manifest",
    ]
    assert lines[-1] == REMEDIATION_VENDORED
    assert doc.is_file()


# ── The recorded transfer: which paths the read-only rule no longer governs ──


def test_a_provenance_record_with_no_carve_out_transfers_nothing(tmp_path: Path) -> None:
    _, _, doc = _synthetic(tmp_path)
    assert parse_living_documents(doc) == {}


def test_a_carve_out_without_a_ratified_record_is_not_a_transfer(tmp_path: Path) -> None:
    """WA-11 confers living-document status only once the transfer is *recorded*."""
    _, _, doc = _synthetic(tmp_path, _UNRATIFIED)
    assert parse_living_documents(doc) == {}


def test_a_recorded_transfer_names_its_path_and_its_ruling(tmp_path: Path) -> None:
    _, _, doc = _synthetic(tmp_path, _TRANSFERRED)
    assert parse_living_documents(doc) == {"vendored/spec.md": "PD-999, ratified 2026-01-02"}


def test_the_classification_follows_the_record_rather_than_the_path(tmp_path: Path) -> None:
    """Nothing here is keyed to a filename: move the carve-out, and the exemption moves."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("`vendored/spec.md`", "`vendored/notes.md`", 1),
        encoding="utf-8",
    )
    for name in ("spec.md", "notes.md"):
        (root / "vendored" / name).write_text("edited in place\n", encoding="utf-8")

    routes = {f.path: f.classification for f in _report(root, manifest_path, doc).findings}

    assert routes == {"vendored/spec.md": VENDORED, "vendored/notes.md": LIVING_DOCUMENT}


def test_a_transferred_path_is_still_hashed(tmp_path: Path) -> None:
    """PD-035's ratified mechanics: an edit arriving without its manifest refresh still fails."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    (root / "vendored" / "spec.md").write_text("a ceiling extension\n", encoding="utf-8")

    report = _report(root, manifest_path, doc)

    assert not report.ok
    assert report.modified == ["vendored/spec.md"]


def test_the_refresh_the_transfer_requires_clears_the_finding(tmp_path: Path) -> None:
    """…and the same-commit regeneration is what turns it green again."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    (root / "vendored" / "spec.md").write_text("a ceiling extension\n", encoding="utf-8")

    regenerate(load_manifest(manifest_path), root, manifest_path)

    refreshed = _report(root, manifest_path, doc)
    assert refreshed.ok
    entry = next(e for e in load_manifest(manifest_path).entries if e.path == "vendored/spec.md")
    assert (entry.vault_source, entry.vault_commit) == ("vault/spec.md", "abc1234")


def test_the_transfer_changes_the_routing_and_nothing_else(tmp_path: Path) -> None:
    """The special case, isolated: one seeded edit, two records, two routes.

    Same guard, same tree, same finding kind and path. What differs is whether the provenance
    record carries the transfer — which is exactly what "per the recorded state" has to mean if
    the exemption is computed rather than remembered.
    """
    before_root, before_manifest, before_doc = _synthetic(tmp_path / "before")
    after_root, after_manifest, after_doc = _synthetic(tmp_path / "after", _TRANSFERRED)
    for root in (before_root, after_root):
        (root / "vendored" / "spec.md").write_text("a ceiling extension\n", encoding="utf-8")

    before = _report(before_root, before_manifest, before_doc).findings
    after = _report(after_root, after_manifest, after_doc).findings

    assert [(f.kind, f.path) for f in before] == [(f.kind, f.path) for f in after]
    assert (before[0].classification, after[0].classification) == (VENDORED, LIVING_DOCUMENT)
    assert "file a spec defect" in before[0].remediation
    assert "spec defect" not in after[0].remediation.replace("owes no spec defect", "")
    assert "--regenerate" in after[0].remediation
    assert "PD-999, ratified 2026-01-02" in after[0].remediation


# ── The two records that actually govern this repository pair ──


@requires_companion
def test_the_provenance_record_transfers_exactly_one_path() -> None:
    """The state as recorded today: one carve-out, and it names its ratified ruling."""
    living = parse_living_documents(PROVENANCE_DOC)
    assert list(living) == ["docs/specs/VERSION-COMPAT.md"]
    assert living["docs/specs/VERSION-COMPAT.md"].startswith("PD-035, ratified ")


@requires_companion
def test_the_library_repositorys_own_surface_transfers_nothing() -> None:
    """The fixture corpus carries no carve-out: every one of its paths routes the same way."""
    manifest = load_manifest(MANIFEST_PATH)
    living = parse_living_documents(PROVENANCE_DOC)
    assert not [path for path in living if manifest.covers(path)]


@pytest.fixture
def companion_sandbox(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A throwaway copy of the companion's guarded surface, its manifest and its record.

    Seeding happens here so no test writes to a vendored file (WA-11).
    """
    manifest = load_manifest(COMPANION_MANIFEST)
    root = tmp_path / "companion"
    for tree in manifest.guarded_trees:
        shutil.copytree(COMPANION / tree, root / tree)
    for name in manifest.guarded_files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(COMPANION / name, root / name)
    manifest_copy = root / "tools" / "provenance-manifest.json"
    manifest_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMPANION_MANIFEST, manifest_copy)
    doc_copy = root / "docs" / "PROVENANCE.md"
    doc_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROVENANCE_DOC, doc_copy)
    return root, manifest_copy, doc_copy


def _before_the_transfer(doc: Path) -> None:
    """The provenance record as it stood before the transfer: its carve-out rule removed."""
    text = doc.read_text(encoding="utf-8")
    start = text.index("4. **Exception (WA-11):**")
    doc.write_text(text[:start] + text[text.index("## Manifest") :], encoding="utf-8")


@requires_companion
def test_the_transferred_spec_is_exempt_from_the_read_only_rule_as_recorded(
    companion_sandbox: tuple[Path, Path, Path],
) -> None:
    """Post-transfer: the edit is sanctioned, so no spec defect is owed — the refresh is."""
    root, manifest_path, doc = companion_sandbox
    target = root / "docs" / "specs" / "VERSION-COMPAT.md"
    target.write_bytes(target.read_bytes() + b"\n<!-- a ceiling extension -->\n")

    findings = _report(root, manifest_path, doc).findings

    assert [(f.kind, f.path, f.classification) for f in findings] == [
        (MODIFIED, "docs/specs/VERSION-COMPAT.md", LIVING_DOCUMENT)
    ]
    assert findings[0].remediation != REMEDIATION_VENDORED
    assert "--regenerate" in findings[0].remediation


@requires_companion
def test_the_same_edit_before_the_transfer_routes_to_the_spec_defect_protocol(
    companion_sandbox: tuple[Path, Path, Path],
) -> None:
    """Pre-transfer: the identical edit to the identical file is a read-only violation."""
    root, manifest_path, doc = companion_sandbox
    target = root / "docs" / "specs" / "VERSION-COMPAT.md"
    target.write_bytes(target.read_bytes() + b"\n<!-- a ceiling extension -->\n")
    _before_the_transfer(doc)

    findings = _report(root, manifest_path, doc).findings

    assert [(f.kind, f.path, f.classification) for f in findings] == [
        (MODIFIED, "docs/specs/VERSION-COMPAT.md", VENDORED)
    ]
    assert findings[0].remediation == REMEDIATION_VENDORED


@requires_companion
def test_an_edit_to_any_other_vendored_spec_routes_the_same_way_either_side_of_the_transfer(
    companion_sandbox: tuple[Path, Path, Path],
) -> None:
    """The carve-out is one path wide: its neighbour in the same tree is untouched by it."""
    root, manifest_path, doc = companion_sandbox
    target = root / "docs" / "specs" / "IR-SPEC.md"
    target.write_bytes(target.read_bytes() + b"\n<!-- an in-place edit -->\n")

    after = _report(root, manifest_path, doc).findings
    _before_the_transfer(doc)
    before = _report(root, manifest_path, doc).findings

    assert [(f.path, f.classification) for f in after] == [("docs/specs/IR-SPEC.md", VENDORED)]
    assert [(f.path, f.classification) for f in before] == [("docs/specs/IR-SPEC.md", VENDORED)]


# ── The exit status a reviewer and a CI job both observe ──


def test_the_ci_command_and_a_scoped_run_reach_the_same_verdict_on_a_seeded_edit(
    tmp_path: Path,
) -> None:
    """One violation, two commands: the gate's own, and the review scope's."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    (root / "vendored" / "notes.md").write_text("edited in place\n", encoding="utf-8")
    common = ["--root", str(root), "--manifest", str(manifest_path), "--provenance-doc", str(doc)]

    gate = _run_guard(*common)
    scoped = _run_guard(*common, "--only", "vendored/notes.md", "--only", "README.md")

    assert gate.returncode == scoped.returncode == 1
    line = "  modified: vendored/notes.md — bytes differ from the recorded snapshot"
    assert line in gate.stderr and line in scoped.stderr
    assert REMEDIATION_VENDORED in gate.stderr and REMEDIATION_VENDORED in scoped.stderr


def test_a_seeded_edit_to_a_real_vendored_file_reads_the_same_both_ways(tmp_path: Path) -> None:
    """The same agreement over a copy of this repository's own vendored corpus.

    The seed lives in the copy, so "then reverted" holds by construction — and the test after
    this one is the check that the corpus itself never moved.
    """
    manifest = load_manifest(MANIFEST_PATH)
    root = tmp_path / "repo"
    for tree in manifest.guarded_trees:
        shutil.copytree(REPO_ROOT / tree, root / tree)
    manifest_copy = root / "tools" / "provenance-manifest.json"
    manifest_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANIFEST_PATH, manifest_copy)
    target = root / GUARDED_FIXTURE
    target.write_bytes(target.read_bytes().replace(b"witness", b"wittness", 1))
    common = ["--root", str(root), "--manifest", str(manifest_copy)]

    gate = _run_guard(*common)
    scoped = _run_guard(*common, "--only", GUARDED_FIXTURE, "--only", "CHANGELOG.md")

    assert gate.returncode == scoped.returncode == 1
    line = f"  modified: {GUARDED_FIXTURE} — bytes differ from the recorded snapshot"
    assert line in gate.stderr and line in scoped.stderr


def _corpus_sandbox(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway copy of this repository's guarded tree and manifest: ``(root, manifest)``."""
    manifest = load_manifest(MANIFEST_PATH)
    root = tmp_path / "repo"
    for tree in manifest.guarded_trees:
        shutil.copytree(REPO_ROOT / tree, root / tree)
    manifest_copy = root / "tools" / "provenance-manifest.json"
    manifest_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANIFEST_PATH, manifest_copy)
    return root, manifest_copy


def test_a_deleted_manifest_row_fails_the_scoped_run_too(tmp_path: Path) -> None:
    """Reproduction (A): the diff touches only the manifest; the finding lands on the fixture."""
    root, manifest_path = _corpus_sandbox(tmp_path)
    manifest = load_manifest(manifest_path)
    write_manifest(
        Manifest(
            schema_version=manifest.schema_version,
            vault_repo=manifest.vault_repo,
            snapshot_commit=manifest.snapshot_commit,
            guarded_trees=manifest.guarded_trees,
            guarded_files=manifest.guarded_files,
            entries=tuple(e for e in manifest.entries if e.path != GUARDED_FIXTURE),
        ),
        manifest_path,
    )
    common = ["--root", str(root), "--manifest", str(manifest_path)]

    bare = _run_guard(*common)
    scoped = _run_guard(*common, "--only", "tools/provenance-manifest.json")

    assert bare.returncode == 1
    assert GUARDED_FIXTURE in bare.stderr and "unlisted" in bare.stderr
    assert scoped.returncode == 1, "a scope naming only the manifest must not report green"
    assert "1 further finding(s)" in scoped.stderr
    assert "re-run without --only" in scoped.stderr


def test_a_scope_naming_only_unguarded_paths_still_fails_a_tampered_tree(tmp_path: Path) -> None:
    """Reproduction (C): the tamper is real, the scope names nothing vendored, exit stays 1."""
    root, manifest_path = _corpus_sandbox(tmp_path)
    target = root / GUARDED_FIXTURE
    target.write_bytes(target.read_bytes().replace(b"witness", b"wittness", 1))
    common = ["--root", str(root), "--manifest", str(manifest_path)]

    bare = _run_guard(*common)
    scoped = _run_guard(*common, "--only", "src/gebra/ir/model.py")

    assert bare.returncode == scoped.returncode == 1
    assert "1 further finding(s)" in scoped.stderr


@requires_companion
def test_a_provenance_row_edit_fails_the_scoped_run_too(
    companion_sandbox: tuple[Path, Path, Path],
) -> None:
    """Reproduction (B): the diff touches only the record; the finding lands on the row's file."""
    root, manifest_path, doc = companion_sandbox
    original = doc.read_text(encoding="utf-8")
    edited = original.replace(
        "`09-RnD-Docs/R-06/drafts/IR-SPEC.draft.md` | `9955ec8`",
        "`09-RnD-Docs/R-06/drafts/IR-SPEC.draft.md` | `0000000`",
        1,
    )
    assert edited != original, "the seed must actually move the row it names"
    doc.write_text(edited, encoding="utf-8")
    common = [
        "--root",
        str(root),
        "--manifest",
        str(manifest_path),
        "--provenance-doc",
        str(doc),
    ]

    bare = _run_guard(*common)
    scoped = _run_guard(*common, "--only", "docs/PROVENANCE.md")

    assert bare.returncode == 1
    assert "manifest:" in bare.stderr and "docs/specs/IR-SPEC.md" in bare.stderr
    assert scoped.returncode == 1, (
        "the record is not itself guarded; the verdict is still the run's"
    )
    assert "1 further finding(s)" in scoped.stderr


def test_the_ci_command_is_green_on_this_repositorys_vendored_surface() -> None:
    """The premise of the demonstrations above: nothing real was touched to produce them."""
    assert _run_guard().returncode == 0


def test_a_review_scope_is_refused_as_a_regeneration_selection(tmp_path: Path) -> None:
    """`--only` filters a report; reading it as "regenerate these" would be a quiet lie."""
    root, manifest_path, _ = _synthetic(tmp_path)

    result = _run_guard(
        "--root", str(root), "--manifest", str(manifest_path), "--regenerate", "--only", "x.md"
    )

    assert result.returncode == 1
    assert "review scope" in result.stderr
    assert "not a selection for --regenerate" in result.stderr


# ── The machine-readable report the skill relays ──


def _json_run(*args: str) -> tuple[int, dict[str, object]]:
    result = _run_guard(*args, "--format", "json")
    return result.returncode, json.loads(result.stdout)


def test_the_json_report_carries_each_findings_route(tmp_path: Path) -> None:
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    _seed_every_kind(root, manifest_path, doc)

    status, payload = _json_run(
        "--root", str(root), "--manifest", str(manifest_path), "--provenance-doc", str(doc)
    )

    assert status == 1 and payload["ok"] is False
    findings = payload["findings"]
    assert isinstance(findings, list)
    assert [f["kind"] for f in findings] == [MODIFIED, MISSING, UNLISTED, MANIFEST]
    assert all(f["remediation"] for f in findings)
    spec = next(f for f in findings if f["path"] == "vendored/spec.md")
    assert spec["classification"] == LIVING_DOCUMENT
    assert payload["living_documents"] == [
        {"path": "vendored/spec.md", "record": "PD-999, ratified 2026-01-02"}
    ]


def test_the_json_report_names_the_scope_it_was_reached_over(tmp_path: Path) -> None:
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)

    _, payload = _json_run(
        "--root",
        str(root),
        "--manifest",
        str(manifest_path),
        "--provenance-doc",
        str(doc),
        "--only",
        "vendored/spec.md",
        "--only",
        "CHANGELOG.md",
    )

    assert payload["scope"] == {
        "selected": ["vendored/spec.md", "CHANGELOG.md"],
        "in_scope": ["vendored/spec.md"],
        "out_of_scope": ["CHANGELOG.md"],
    }


def test_the_json_verdict_counts_the_findings_it_does_not_list(tmp_path: Path) -> None:
    """`ok` is the whole run's; a reader relaying `findings` alone must see what it is missing."""
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    _seed_every_kind(root, manifest_path, doc)

    status, payload = _json_run(
        "--root",
        str(root),
        "--manifest",
        str(manifest_path),
        "--provenance-doc",
        str(doc),
        "--only",
        "README.md",
    )

    assert status == 1 and payload["ok"] is False
    assert payload["findings"] == []
    assert payload["findings_outside_scope"] == 4


def test_the_two_output_formats_agree_on_the_verdict(tmp_path: Path) -> None:
    root, manifest_path, doc = _synthetic(tmp_path, _TRANSFERRED)
    common = ["--root", str(root), "--manifest", str(manifest_path), "--provenance-doc", str(doc)]
    assert _run_guard(*common).returncode == _json_run(*common)[0] == 0

    (root / "vendored" / "spec.md").write_text("a ceiling extension\n", encoding="utf-8")

    assert _run_guard(*common).returncode == _json_run(*common)[0] == 1


# ── The skill: one computation with the guard, plus the evidence no script can find ──


@requires_staged_skill
def test_the_skill_computes_its_integrity_verdict_with_this_guard() -> None:
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    assert "tools/provenance_guard.py" in skill
    assert "--only" in skill and "--format json" in skill
    assert "exit status" in skill


@requires_staged_skill
def test_the_skill_runs_the_command_each_repository_gates_with() -> None:
    """The companion half is guarded with `--provenance-doc`; without it the record is unread."""
    assert "--provenance-doc docs/PROVENANCE.md" in STAGED_SKILL.read_text(encoding="utf-8")


@requires_staged_skill
def test_the_skill_restates_neither_the_transfer_rule_nor_the_path_it_covers() -> None:
    """A rule named in prose is a rule that can drift: the guard reads it, the skill relays it."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    for restated in ("VERSION-COMPAT", "PD-035", "living-document status", "GOV-D2"):
        assert restated not in skill, f"the skill restates {restated!r} instead of reading it"


@requires_staged_skill
def test_the_skill_keeps_the_routing_evidence_the_guard_cannot_compute() -> None:
    """A vault hash in a commit message is not a property of the bytes; the review still owes it."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    assert "vault hash" in skill
    assert "PROVENANCE.md" in skill
    assert "/fixture-review" in skill


@requires_installed_skill
def test_the_installed_skill_is_the_staged_one() -> None:
    """Once installed, the two cannot drift — the pin is byte equality."""
    assert INSTALLED_SKILL.read_bytes() == STAGED_SKILL.read_bytes()
