"""Behaviour tests for the provenance guard (GOV-09, WA-11).

The guard is the CI enforcement of one rule: every vendored file is a byte-copy of its
recorded snapshot. These tests pin what that means in practice — the working tree matches
today, an in-place edit fails the build, so does a deletion and so does a file added to a
guarded tree, and the sanctioned re-vendor path (regenerate the manifest in the same commit)
turns it green again.

Everything here reads, copies and hashes files. The two subprocess calls run the guard
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
    Manifest,
    files_in_guarded_trees,
    load_manifest,
    parse_provenance_rows,
    regenerate,
    verify,
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
    """No corner of a guarded tree is unlisted — coverage is what makes the guard total."""
    assert set(files_in_guarded_trees(REPO_ROOT, manifest)) <= manifest.paths
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
