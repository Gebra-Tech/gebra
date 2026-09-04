"""Behaviour tests for the provenance guard (GOV-09, GOV-10, WA-11).

The guard is the CI enforcement of one rule: every vendored file is a byte-copy of its
recorded snapshot. These tests pin what that means in practice — the working tree matches
today, an in-place edit fails the build, so does a deletion and so does a file added to a
guarded tree, and the sanctioned re-vendor path (regenerate the manifest in the same commit)
turns it green again.

The last section holds the four evasions GOV-09's owner review demonstrated against the guard
and GOV-10 closed: a rogue file reachable through a symlinked directory, a manifest that shrinks
its own scope so that provenance rows leave the comparison, a regeneration that drops the entry
of a deleted file without saying so, and a malformed manifest reported as a traceback rather
than as a sentence. Each is seeded in a temporary copy; nothing here writes to the vendored
corpus.

Which of these run where matters, and the split is deliberate. The cross-repository cases below
are marked ``requires_companion`` and **skip in this repository's CI**, which can never check
out the private development-process repository — they are enforced on a maintainer's machine,
where both checkouts sit side by side. So every case that can be written against a synthetic
two-repository record is written that way instead, and the one fact CI must not lose — that this
repository's manifest still declares both halves of the split — is pinned by a test that reads
no companion at all.

Everything here reads, copies, links and hashes files. The subprocess calls run the guard
script itself — the exact command the CI job runs, so its exit status is observed rather than
assumed. No workflow node is executed, no LLM is called, no socket is opened (WA-07).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.provenance_guard import (
    MANIFEST_SCHEMA_VERSION,
    SCOPE_DECLARATION,
    Entry,
    Manifest,
    ManifestError,
    dropped_paths,
    files_in_guarded_trees,
    load_manifest,
    parse_provenance_rows,
    regenerate,
    sha256_of,
    verify,
    write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "tools" / "provenance_guard.py"
MANIFEST = REPO_ROOT / "tools" / "provenance-manifest.json"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PR_TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"
CLA = REPO_ROOT / "CLA.md"
SIGNATURES = REPO_ROOT / "docs" / "governance" / "cla-signatures.md"
RE_VENDORING = REPO_ROOT / "docs" / "governance" / "re-vendoring.md"

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
COMPANION_GUARD = COMPANION / "tools" / "provenance_guard.py"
COMPANION_MANIFEST = COMPANION / "tools" / "provenance-manifest.json"
COMPANION_WORKFLOW = COMPANION / ".github" / "workflows" / "provenance.yml"
PROVENANCE_DOC = COMPANION / "docs" / "PROVENANCE.md"

requires_companion = pytest.mark.skipif(
    not PROVENANCE_DOC.is_file(),
    reason="the development-process repository is not checked out beside this one",
)


@pytest.fixture
def manifest() -> Manifest:
    return load_manifest(MANIFEST)


@pytest.fixture
def sandbox(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway copy of the guarded tree and its manifest: ``(root, manifest path)``.

    Tampering happens here so the tests never touch the real vendored corpus.
    """
    root = tmp_path / "repo"
    for tree in load_manifest(MANIFEST).guarded_trees:
        shutil.copytree(REPO_ROOT / tree, root / tree)
    manifest_copy = root / "tools" / "provenance-manifest.json"
    manifest_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANIFEST, manifest_copy)
    return root, manifest_copy


def _run_guard(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the guard exactly as CI does — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


# ── The recorded state of this repository ──


def test_the_working_tree_matches_the_manifest(manifest: Manifest) -> None:
    """The premise of every other test: nothing vendored has drifted right now."""
    report = verify(manifest, REPO_ROOT)
    assert report.ok, report.modified + report.missing + report.unlisted
    assert report.checked == len(manifest.entries)


def test_the_manifest_covers_the_whole_guarded_tree(manifest: Manifest) -> None:
    """No corner of a guarded tree is unlisted — coverage is what makes the guard total.

    Set *equality*, not containment: the tree is the manifest's whole subject here
    (``guarded_files`` is empty), so a walk that started finding fewer files would be a
    regression a subset assertion would sit through.
    """
    assert set(files_in_guarded_trees(REPO_ROOT, manifest)) == set(manifest.paths)
    assert manifest.guarded_trees == ("tests/fixtures/properties",)
    assert len(manifest.entries) == 74


# ── What the guard rejects ──


def test_an_in_place_edit_is_reported(sandbox: tuple[Path, Path]) -> None:
    root, manifest_path = sandbox
    target = (
        root
        / "tests/fixtures/properties/graph-well-formed/positive-01-linear-document-pipeline.yaml"
    )
    target.write_bytes(target.read_bytes() + b"\n# local tweak\n")

    report = verify(load_manifest(manifest_path), root)

    assert not report.ok
    assert report.modified == [
        "tests/fixtures/properties/graph-well-formed/positive-01-linear-document-pipeline.yaml"
    ]
    assert not report.missing and not report.unlisted


def test_a_one_byte_change_is_reported(sandbox: tuple[Path, Path]) -> None:
    """Byte-copy means byte-copy: a single character is drift."""
    root, manifest_path = sandbox
    target = root / "tests/fixtures/properties/schema.yaml"
    original = target.read_bytes()
    target.write_bytes(original.replace(b"a", b"A", 1))

    report = verify(load_manifest(manifest_path), root)

    assert report.modified == ["tests/fixtures/properties/schema.yaml"]


def test_a_deleted_vendored_file_is_reported(sandbox: tuple[Path, Path]) -> None:
    root, manifest_path = sandbox
    (
        root / "tests/fixtures/properties/mixed/01-witnessed-cycle-with-unkeyed-billable-node.yaml"
    ).unlink()

    report = verify(load_manifest(manifest_path), root)

    assert not report.ok
    assert report.missing == [
        "tests/fixtures/properties/mixed/01-witnessed-cycle-with-unkeyed-billable-node.yaml"
    ]


def test_a_file_added_to_a_guarded_tree_is_reported(sandbox: tuple[Path, Path]) -> None:
    """A fixture added by hand bypasses fixture review; the guard treats it as drift."""
    root, manifest_path = sandbox
    (root / "tests/fixtures/properties/mixed/99-local-invention.yaml").write_text(
        "id: local-invention\n", encoding="utf-8"
    )

    report = verify(load_manifest(manifest_path), root)

    assert not report.ok
    assert report.unlisted == ["tests/fixtures/properties/mixed/99-local-invention.yaml"]


def test_local_clutter_is_not_mistaken_for_drift(sandbox: tuple[Path, Path]) -> None:
    """`.DS_Store` and `__pycache__` are never committed and never vendored."""
    root, manifest_path = sandbox
    (root / "tests/fixtures/properties/.DS_Store").write_bytes(b"\x00")
    cache = root / "tests/fixtures/properties/__pycache__"
    cache.mkdir()
    (cache / "stale.pyc").write_bytes(b"\x00")

    assert verify(load_manifest(manifest_path), root).ok


# ── The exit status CI actually observes ──


def test_the_ci_command_passes_on_the_working_tree() -> None:
    result = _run_guard()
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_ci_command_fails_on_an_unsanctioned_edit(sandbox: tuple[Path, Path]) -> None:
    """The acceptance criterion: an edited vendored file fails the build, and is named."""
    root, manifest_path = sandbox
    target = (
        root
        / "tests/fixtures/properties/termination-witness/positive-01-counter-guarded-retry-loop.yaml"
    )
    target.write_bytes(target.read_bytes().replace(b"witness", b"wittness", 1))

    result = _run_guard("--root", str(root), "--manifest", str(manifest_path))

    assert result.returncode == 1
    assert "positive-01-counter-guarded-retry-loop.yaml" in result.stderr
    assert "modified" in result.stderr
    assert "re-vendoring.md" in result.stderr


def test_the_ci_command_fails_when_the_manifest_is_missing(tmp_path: Path) -> None:
    result = _run_guard("--manifest", str(tmp_path / "absent.json"))
    assert result.returncode == 1
    assert "manifest not found" in result.stderr


# ── The sanctioned re-vendor path ──


def test_regenerating_the_manifest_clears_a_sanctioned_re_vendor(
    sandbox: tuple[Path, Path],
) -> None:
    """A re-vendor commit updates the bytes and the manifest together — then CI is green."""
    root, manifest_path = sandbox
    target = root / "tests/fixtures/properties/README.md"
    target.write_bytes(b"# re-vendored from a later vault commit\n")
    before = load_manifest(manifest_path)
    assert not verify(before, root).ok

    after = regenerate(before, root, manifest_path)

    assert verify(load_manifest(manifest_path), root).ok
    entry = next(
        item for item in after.entries if item.path == "tests/fixtures/properties/README.md"
    )
    original = next(
        item for item in before.entries if item.path == "tests/fixtures/properties/README.md"
    )
    assert entry.sha256 != original.sha256
    # Provenance fields are carried forward, never invented: docs/PROVENANCE.md is what
    # updates them, and the cross-check is what proves the two records agree.
    assert (entry.vault_source, entry.vault_commit) == (
        original.vault_source,
        original.vault_commit,
    )


def test_regenerating_marks_a_newly_added_file_unrecorded(sandbox: tuple[Path, Path]) -> None:
    """Regeneration cannot launder an addition into the corpus: its provenance is blank."""
    root, manifest_path = sandbox
    (root / "tests/fixtures/properties/mixed/99-local-invention.yaml").write_text(
        "id: local-invention\n", encoding="utf-8"
    )

    after = regenerate(load_manifest(manifest_path), root, manifest_path)

    added = next(item for item in after.entries if item.path.endswith("99-local-invention.yaml"))
    assert added.vault_source == "UNRECORDED"
    assert added.vault_commit == "UNRECORDED"


def test_there_is_no_bypass_flag() -> None:
    """The exemption path is a manifest update in the same commit, not a CI switch."""
    help_text = _run_guard("--help").stdout
    assert "--regenerate" in help_text
    for bypass in ("--skip", "--force", "--allow", "--ignore"):
        assert bypass not in help_text


# ── Wiring: the guard runs in CI, and the governance documents reference each other ──


def _ci_run_steps() -> list[str]:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step.get("run"), str)
    ]


def test_ci_runs_the_provenance_guard() -> None:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "provenance" in workflow["jobs"], "the guard needs its own CI job"
    assert any("tools/provenance_guard.py" in step for step in _ci_run_steps())


def test_the_pull_request_template_references_the_cla_and_the_record() -> None:
    template = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "CLA.md" in template
    assert "docs/governance/cla-signatures.md" in template
    assert "tools/provenance_guard.py" in template
    assert "re-vendoring.md" in template


def test_the_cla_and_its_signature_record_exist() -> None:
    cla = CLA.read_text(encoding="utf-8")
    signatures = SIGNATURES.read_text(encoding="utf-8")
    assert "Individual Contributor License Agreement" in cla
    assert "docs/governance/cla-signatures.md" in cla
    # The record is the table a reviewer reads, and later the data a bot reads.
    for column in ("GitHub handle", "CLA version", "Signed", "Recorded"):
        assert column in signatures


def test_the_re_vendor_procedure_is_documented() -> None:
    procedure = RE_VENDORING.read_text(encoding="utf-8")
    assert "--regenerate" in procedure
    assert "PROVENANCE.md" in procedure
    assert "vault" in procedure


# ── Cross-repository: the other half of the vendored surface ──


@requires_companion
def test_the_manifest_agrees_with_the_provenance_record(manifest: Manifest) -> None:
    """Manifest rows mirror docs/PROVENANCE.md, so neither can drop a file unnoticed."""
    report = verify(manifest, REPO_ROOT, PROVENANCE_DOC)
    assert report.provenance_mismatch == []


@requires_companion
def test_every_provenance_row_is_guarded_by_exactly_one_manifest(manifest: Manifest) -> None:
    """The 85 vendored rows split across two repositories; none is unguarded or double-counted."""
    companion = load_manifest(COMPANION_MANIFEST)
    rows = set(parse_provenance_rows(PROVENANCE_DOC))

    assert manifest.paths | companion.paths == rows
    assert manifest.paths & companion.paths == set()


@requires_companion
def test_the_companion_manifest_matches_the_vendored_documentation_package() -> None:
    companion = load_manifest(COMPANION_MANIFEST)
    report = verify(companion, COMPANION, PROVENANCE_DOC)
    assert report.ok, report.modified + report.missing + report.unlisted
    assert report.provenance_mismatch == []


@requires_companion
def test_the_companion_guard_is_a_byte_identical_copy() -> None:
    """One implementation, two repositories: drift between the copies is a defect."""
    assert COMPANION_GUARD.read_bytes() == GUARD.read_bytes()


@requires_companion
def test_the_companion_workflow_runs_the_guard() -> None:
    workflow: dict[str, Any] = yaml.safe_load(COMPANION_WORKFLOW.read_text(encoding="utf-8"))
    steps = [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step.get("run"), str)
    ]
    assert any("tools/provenance_guard.py" in step for step in steps)
    assert any("--provenance-doc" in step for step in steps)


@requires_companion
def test_the_manifest_is_derived_from_the_provenance_rows(manifest: Manifest) -> None:
    """Every entry names the vault file and commit its bytes were copied from."""
    rows = parse_provenance_rows(PROVENANCE_DOC)
    for entry in manifest.entries:
        assert rows[entry.path] == (entry.vault_source, entry.vault_commit)
    assert json.loads(MANIFEST.read_text(encoding="utf-8"))["vault_repo"] == (
        "Gebra-Tech/initial-documents"
    )


# ── The evasions the GOV-09 owner review demonstrated, and GOV-10 closed ──
#
# (1) a rogue file reachable through `ln -s` verified OK; (2) a manifest that shrank its own
# scope took provenance rows out of the comparison with it; (3) `--regenerate` dropped the entry
# of a deleted file in silence; (4) a manifest missing a top-level key died as a traceback.


def test_a_symlinked_directory_inside_a_guarded_tree_is_reported(
    sandbox: tuple[Path, Path],
) -> None:
    """Gap 1, as the review demonstrated it: a fixture smuggled in behind a directory link.

    The guard does not follow the link. Following it would mean hashing whatever the link
    happened to point at — outside the repository, or nowhere at all — so what the guard reports
    is the link itself, which stays true whatever lies on the other side.
    """
    root, manifest_path = sandbox
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "99-local-invention.yaml").write_text("id: local-invention\n", encoding="utf-8")
    (root / "tests/fixtures/properties/mixed/linked").symlink_to(outside)

    report = verify(load_manifest(manifest_path), root)

    assert not report.ok
    assert report.unlisted == ["tests/fixtures/properties/mixed/linked"]
    assert "symlinked directory" in report.findings[0].detail


def test_a_symlinked_file_inside_a_guarded_tree_is_reported(sandbox: tuple[Path, Path]) -> None:
    """A link beside the corpus is not a copy of the corpus, even pointing at a listed file."""
    root, manifest_path = sandbox
    corpus = root / "tests/fixtures/properties"
    (corpus / "mixed" / "11-linked.yaml").symlink_to(
        corpus / "mixed" / "10-all-properties-pass-healthy-research-pipeline.yaml"
    )

    report = verify(load_manifest(manifest_path), root)

    assert report.unlisted == ["tests/fixtures/properties/mixed/11-linked.yaml"]


def test_a_vendored_file_replaced_by_a_symlink_is_reported(sandbox: tuple[Path, Path]) -> None:
    """Byte-equality is not enough: the recorded bytes have to be *this* file.

    The link points at a copy carrying identical bytes, so hashing through it matched and the
    tree verified — while the snapshot the manifest claims is here lived somewhere else.
    """
    root, manifest_path = sandbox
    listed = root / "tests/fixtures/properties/schema.yaml"
    stand_in = root.parent / "schema.yaml"
    stand_in.write_bytes(listed.read_bytes())
    listed.unlink()
    listed.symlink_to(stand_in)
    recorded = next(
        entry.sha256
        for entry in load_manifest(manifest_path).entries
        if entry.path == "tests/fixtures/properties/schema.yaml"
    )
    assert sha256_of(listed) == recorded, "the seed must be invisible to a hash alone"

    report = verify(load_manifest(manifest_path), root)

    assert report.modified == ["tests/fixtures/properties/schema.yaml"]
    assert "symlink" in report.findings[0].detail


def test_regenerating_cannot_launder_a_symlink(sandbox: tuple[Path, Path]) -> None:
    """A re-vendor records files; a link is not one, so regeneration leaves it reported."""
    root, manifest_path = sandbox
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "rogue.yaml").write_text("id: rogue\n", encoding="utf-8")
    (root / "tests/fixtures/properties/linked").symlink_to(outside)

    after = regenerate(load_manifest(manifest_path), root, manifest_path)

    assert "tests/fixtures/properties/linked" not in after.paths
    assert verify(load_manifest(manifest_path), root).unlisted == [
        "tests/fixtures/properties/linked"
    ]


def test_a_guarded_tree_that_is_itself_a_symlink_is_reported(sandbox: tuple[Path, Path]) -> None:
    """The same substitution one level up, where `os.walk` would have followed it anyway.

    Nothing else can catch this one: every listed path resolves through the link, so each file
    hashes clean, and the entry loop's own check looks only at a path's last component.
    """
    root, manifest_path = sandbox
    corpus = root / "tests/fixtures/properties"
    stand_in = root.parent / "corpus-copy"
    corpus.rename(stand_in)
    corpus.symlink_to(stand_in)

    report = verify(load_manifest(manifest_path), root)

    assert not report.ok, "every listed file still hashes clean through the link"
    assert report.modified == [] and report.missing == []
    assert report.unlisted == ["tests/fixtures/properties"]
    assert "the guarded tree itself is a symlink" in report.findings[0].detail


def test_the_ci_command_fails_on_a_smuggled_symlink(sandbox: tuple[Path, Path]) -> None:
    """The exit status CI observes, on the seed that used to come back green."""
    root, manifest_path = sandbox
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "rogue.yaml").write_text("id: rogue\n", encoding="utf-8")
    (root / "tests/fixtures/properties/graph-well-formed/linked").symlink_to(outside)

    result = _run_guard("--root", str(root), "--manifest", str(manifest_path))

    assert result.returncode == 1
    assert "unlisted: tests/fixtures/properties/graph-well-formed/linked" in result.stderr


# ── Gap 2: the manifest declares both halves of the record, and neither may go missing ──
#
# Written against a synthetic two-repository record on purpose. The real pair is readable only
# where the companion repository is checked out, which this repository's CI never is — so the
# cases that matter most are the ones that run everywhere.

_TWO_REPO_DOC = """# Provenance — sandbox

## Sync rules

1. **The vault copy is authoritative.** Never edit a vendored file here.

## Manifest

| Vendored file | Vault source | Vault commit | Copied |
|---|---|---|---|
| `here/spec.md` | `vault/spec.md` | `abc1234` | 2026-01-01 |
| `there/fixture.yaml` | `vault/fixture.yaml` | `abc1234` | 2026-01-01 |
"""


def _declared_pair(
    tmp_path: Path,
    *,
    guarded_trees: tuple[str, ...] = ("here",),
    foreign_trees: tuple[str, ...] = ("there",),
    listed: bool = True,
) -> tuple[Path, Path, Path]:
    """One repository of a two-repository record: ``(root, manifest path, provenance doc)``.

    The record carries one row on each side of the split. ``listed=False`` is the second half of
    the evasion: the entries go when the scope that covered them goes.
    """
    root = tmp_path / "repo"
    (root / "here").mkdir(parents=True)
    (root / "here" / "spec.md").write_bytes(b"frozen bytes\n")
    doc = root / "docs" / "PROVENANCE.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(_TWO_REPO_DOC, encoding="utf-8")
    manifest_path = root / "tools" / "provenance-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    write_manifest(
        Manifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            vault_repo="Example-Org/sandbox-vault",
            snapshot_commit="abc1234",
            guarded_trees=guarded_trees,
            guarded_files=(),
            entries=(
                Entry(
                    "here/spec.md",
                    sha256_of(root / "here" / "spec.md"),
                    "vault/spec.md",
                    "abc1234",
                ),
            )
            if listed
            else (),
            foreign_trees=foreign_trees,
            foreign_files=(),
        ),
        manifest_path,
    )
    return root, manifest_path, doc


def test_a_declared_split_that_covers_the_whole_record_passes(tmp_path: Path) -> None:
    """The premise: one row guarded here, one handed to the sibling, and nothing left over."""
    root, manifest_path, doc = _declared_pair(tmp_path)

    assert verify(load_manifest(manifest_path), root, doc).ok


def test_shrinking_the_guarded_scope_no_longer_hides_a_row(tmp_path: Path) -> None:
    """Gap 2, as the review demonstrated it: edit the manifest and the file it guards, together.

    The scope shrinks, the entries go with it, and the row it covered used to leave the
    comparison — a standalone run then read a smaller surface as an intact one, and reported OK
    over an edited vendored file.
    """
    root, manifest_path, doc = _declared_pair(tmp_path, guarded_trees=(), listed=False)
    (root / "here" / "spec.md").write_bytes(b"edited to make a test pass\n")

    report = verify(load_manifest(manifest_path), root, doc)

    assert not report.ok
    assert report.provenance_mismatch == [
        "here/spec.md: a PROVENANCE.md row this manifest neither guards nor hands to its sibling"
    ]
    assert report.findings[0].classification == SCOPE_DECLARATION


def test_a_row_handed_to_the_sibling_while_its_file_is_here_is_reported(tmp_path: Path) -> None:
    """The same evasion in its other spelling: move the tree across rather than delete it.

    Whether the sibling really guards its half is a second checkout's question. Whether this
    repository is still holding what it just handed away is not — and that is the half a
    standalone run can answer.
    """
    root, manifest_path, doc = _declared_pair(
        tmp_path, guarded_trees=(), foreign_trees=("there", "here"), listed=False
    )

    report = verify(load_manifest(manifest_path), root, doc)

    assert report.provenance_mismatch == [
        "here/spec.md: declared as the sibling repository's share but present in this tree"
    ]


def test_a_row_claimed_by_both_scopes_is_reported(tmp_path: Path) -> None:
    """A row claimed twice is owned by neither declaration: the split stops being a partition."""
    root, manifest_path, doc = _declared_pair(tmp_path, foreign_trees=("there", "here"))

    report = verify(load_manifest(manifest_path), root, doc)

    assert report.provenance_mismatch == [
        "here/spec.md: claimed by both this manifest's guarded scope and its foreign scope"
    ]


def test_a_broken_declaration_reports_each_path_once(tmp_path: Path) -> None:
    """The scope shrinks but the entries stay — one finding per path, routed to the declaration.

    The row comparison reads the same shrunk scope that produced the first finding, so left to
    itself it would add "in the manifest but not a PROVENANCE.md row in scope" and answer a
    broken declaration with advice about bytes nobody has touched.
    """
    root, manifest_path, doc = _declared_pair(tmp_path, guarded_trees=())

    findings = verify(load_manifest(manifest_path), root, doc).findings

    assert [(f.path, f.classification) for f in findings] == [("here/spec.md", SCOPE_DECLARATION)]


def test_a_scope_finding_asks_for_the_declaration_not_for_the_bytes(tmp_path: Path) -> None:
    """Routing: nothing is asked of the file — the manifest's account of it is what is wrong."""
    root, manifest_path, doc = _declared_pair(tmp_path, guarded_trees=(), listed=False)

    remediation = verify(load_manifest(manifest_path), root, doc).findings[0].remediation

    assert "foreign_trees" in remediation and "guarded_trees" in remediation
    assert "spec defect" not in remediation


def test_the_manifest_declares_both_halves_of_the_record(manifest: Manifest) -> None:
    """The declaration as it stands, pinned where CI can see it — no companion checkout needed.

    This is the one fact about the split that must not be able to change quietly in a repository
    whose CI cannot read the other side: shrink either list and this test is red, with or
    without the companion.
    """
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.guarded_trees == ("tests/fixtures/properties",)
    assert manifest.guarded_files == ()
    assert manifest.foreign_trees == ("docs/specs", "docs/briefs", "docs/decisions", "docs/notes")
    assert manifest.foreign_files == ("docs/SOW.md",)


@requires_companion
def test_each_manifest_declares_the_other_repositorys_share(manifest: Manifest) -> None:
    """The two declarations are mirrors, which is what makes the pair a partition."""
    companion = load_manifest(COMPANION_MANIFEST)
    assert manifest.foreign_trees == companion.guarded_trees
    assert manifest.foreign_files == companion.guarded_files
    assert companion.foreign_trees == manifest.guarded_trees
    assert companion.foreign_files == manifest.guarded_files


@requires_companion
def test_every_provenance_row_falls_in_exactly_one_declared_scope(manifest: Manifest) -> None:
    """…and the mirrors between them cover the real record, row by row."""
    for path in parse_provenance_rows(PROVENANCE_DOC):
        assert manifest.covers(path) != manifest.foreign_covers(path), path


# ── Gap 3: a regeneration says which entries it drops ──


def test_regenerating_names_the_entries_it_drops(sandbox: tuple[Path, Path]) -> None:
    """Dropping an entry is how a re-vendor records a deletion — and how one goes unrecorded.

    Afterwards the path is simply not in the manifest, and a run without ``--provenance-doc``
    (which is what this repository's CI runs) has nothing left to notice.
    """
    root, manifest_path = sandbox
    deleted = "tests/fixtures/properties/mixed/01-witnessed-cycle-with-unkeyed-billable-node.yaml"
    (root / deleted).unlink()

    assert dropped_paths(load_manifest(manifest_path), root) == (deleted,)

    result = _run_guard("--root", str(root), "--manifest", str(manifest_path), "--regenerate")

    assert result.returncode == 0
    assert "1 entry(ies) dropped" in result.stdout
    assert f"dropped:  {deleted}" in result.stdout
    assert deleted not in load_manifest(manifest_path).paths


def test_regenerating_an_intact_tree_names_no_drop(sandbox: tuple[Path, Path]) -> None:
    """The other polarity: a re-vendor that removes nothing says nothing about removals."""
    root, manifest_path = sandbox

    assert dropped_paths(load_manifest(manifest_path), root) == ()

    result = _run_guard("--root", str(root), "--manifest", str(manifest_path), "--regenerate")

    assert result.returncode == 0
    assert "dropped" not in result.stdout


# ── Gap 4: an unusable manifest is a sentence, not a traceback ──


@pytest.mark.parametrize(
    "key",
    [
        "vault_repo",
        "snapshot_commit",
        "guarded_trees",
        "guarded_files",
        "foreign_trees",
        "foreign_files",
        "entries",
    ],
)
def test_a_manifest_missing_a_top_level_key_names_the_key(tmp_path: Path, key: str) -> None:
    """Every key the guard needs, refused by name — the quiet shapes included.

    An absent ``guarded_trees`` would guard nothing and an absent ``foreign_trees`` would hand
    the sibling nothing, so neither may be read as an empty default.
    """
    document: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    del document[key]
    broken = tmp_path / "provenance-manifest.json"
    broken.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ManifestError) as raised:
        load_manifest(broken)

    assert f"missing the required key {key!r}" in str(raised.value)


def test_a_manifest_entry_missing_a_key_names_the_entry(tmp_path: Path) -> None:
    """Down one level, the same rule: which entry, and which key it lacks."""
    document: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    del document["entries"][3]["sha256"]
    broken = tmp_path / "provenance-manifest.json"
    broken.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ManifestError) as raised:
        load_manifest(broken)

    assert "entry 3 is missing the required key 'sha256'" in str(raised.value)


def test_the_ci_command_reports_a_malformed_manifest_without_a_traceback(tmp_path: Path) -> None:
    """Exit 1 either way; what changed is whether the reader is told what is wrong."""
    document: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    del document["entries"]
    broken = tmp_path / "provenance-manifest.json"
    broken.write_text(json.dumps(document), encoding="utf-8")

    result = _run_guard("--manifest", str(broken))

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "manifest is missing the required key 'entries'" in result.stderr
