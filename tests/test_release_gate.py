"""The release gate's contract (GOV-03; PD-036) — grammar, consistency, notes, artifacts.

The gate is the mechanical half of the release policy: tags parse inside the Phase-0
grammar and equal the declared version byte for byte, the changelog carries the section the
tag's kind requires, the built artifacts are exactly one wheel + one sdist for exactly that
version, and ``publish`` is ``true`` only for the bare final form — never for a dev cut, a
release candidate, or a dry run. These tests drive every refusal as well as every pass:
a gate whose refusals were never watched firing would be a gate only by intention.

Hermetic on purpose: policy cases run against trees written under ``tmp_path``. Two pins at
the end run against the repository's own ``pyproject.toml`` and ``CHANGELOG.md`` — the same
invariant CI's dry-run step enforces on every push, kept red-locally-first.

WA-07: everything here reads and writes plain text under ``tmp_path``; nothing builds,
publishes, executes a workflow, or opens a socket.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools import release_gate
from tools.release_gate import (
    GateError,
    GateInputError,
    Verdict,
    changelog_notes,
    classify_version,
    emit_github_output,
    main,
    parse_ref,
    project_version,
    run_gate,
    verify_dist,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

CHANGELOG_TEXT = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- An unreleased entry.
- Another unreleased entry.

## [0.1.0] - 2026-09-01

### Added

- The launch entry.
"""


def write_tree(tmp_path: Path, version: str, changelog: str = CHANGELOG_TEXT) -> tuple[Path, Path]:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'[project]\nname = "gebra"\nversion = "{version}"\n', encoding="utf-8")
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(changelog, encoding="utf-8")
    return pyproject, changelog_path


def touch_dist(tmp_path: Path, *names: str) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    for name in names:
        (dist / name).write_bytes(b"")
    return dist


# ── The tag grammar: three shapes in, everything else refused ────────────────────────────


@pytest.mark.parametrize(
    ("version", "kind"),
    [
        ("0.0.1", "final"),
        ("1.2.3", "final"),
        ("10.20.30", "final"),
        ("0.0.1.dev0", "dev"),
        ("0.0.1.dev12", "dev"),
        ("2.0.0.dev1", "dev"),
        ("0.0.1rc1", "prerelease"),
        ("0.0.1a0", "prerelease"),
        ("0.0.1b7", "prerelease"),
    ],
)
def test_the_grammar_admits_exactly_the_three_release_shapes(version: str, kind: str) -> None:
    assert classify_version(version) == kind


@pytest.mark.parametrize(
    "version",
    [
        "",
        "0.0",  # two components
        "0.0.1.2",  # four components
        "0.01.1",  # leading zero — non-canonical
        "0.0.1.dev",  # dev without N
        "0.0.1.post1",  # post-release: not a Phase-0 form
        "1!0.0.1",  # epoch
        "0.0.1+local",  # local version
        "0.0.1rc1.dev1",  # combined pre+dev: publish policy would be ambiguous
        "0.0.1-rc1",  # non-canonical separator
        "0.0.1.DEV0",  # non-canonical case
        "v0.0.1",  # the prefix is the tag's, never the version's
    ],
)
def test_everything_outside_the_grammar_is_refused_loudly(version: str) -> None:
    with pytest.raises(GateError, match="outside the Phase-0 release grammar"):
        classify_version(version)


# ── Refs and tags ────────────────────────────────────────────────────────────────────────


def test_parse_ref_takes_the_tag_out_of_a_tag_ref() -> None:
    assert parse_ref("refs/tags/v0.0.1.dev0") == "v0.0.1.dev0"


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/tags/", "v0.0.1", ""])
def test_parse_ref_refuses_anything_that_is_not_a_tag_ref(ref: str) -> None:
    with pytest.raises(GateError, match="not a tag ref"):
        parse_ref(ref)


def test_a_tag_without_the_v_prefix_is_refused(tmp_path: Path) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    with pytest.raises(GateError, match="does not carry the 'v' prefix"):
        run_gate(
            ref=None,
            tag="0.0.1.dev0",
            dry_run=False,
            pyproject=pyproject,
            changelog=changelog,
            verify_dist_dir=None,
        )


# ── The publish gate: true for the final form only, and never on a dry run ───────────────


def test_a_dev_tag_gates_publish_false_and_ships_unreleased_notes(tmp_path: Path) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    verdict = run_gate(
        ref="refs/tags/v0.0.1.dev0",
        tag=None,
        dry_run=False,
        pyproject=pyproject,
        changelog=changelog,
        verify_dist_dir=None,
    )
    assert verdict.kind == "dev"
    assert verdict.publish is False
    assert verdict.tag == "v0.0.1.dev0"
    assert verdict.notes_heading == release_gate.UNRELEASED_HEADING
    assert "An unreleased entry." in verdict.notes
    assert "The launch entry." not in verdict.notes


def test_a_final_tag_gates_publish_true_and_ships_its_dated_section(tmp_path: Path) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.1.0")
    verdict = run_gate(
        ref="refs/tags/v0.1.0",
        tag=None,
        dry_run=False,
        pyproject=pyproject,
        changelog=changelog,
        verify_dist_dir=None,
    )
    assert verdict.kind == "final"
    assert verdict.publish is True
    assert verdict.notes_heading == "## [0.1.0] - 2026-09-01"
    assert "The launch entry." in verdict.notes
    assert "An unreleased entry." not in verdict.notes


def test_a_dry_run_never_publishes_even_when_the_tree_declares_a_final_version(
    tmp_path: Path,
) -> None:
    """The dispatch/CI rehearsal path must be unable to publish, whatever the tree says."""
    pyproject, changelog = write_tree(tmp_path, "0.1.0")
    verdict = run_gate(
        ref=None,
        tag=None,
        dry_run=True,
        pyproject=pyproject,
        changelog=changelog,
        verify_dist_dir=None,
    )
    assert verdict.kind == "dry-run"
    assert verdict.publish is False
    assert verdict.tag is None
    assert verdict.notes_heading == release_gate.UNRELEASED_HEADING


def test_a_dry_run_still_holds_the_declared_version_to_the_grammar(tmp_path: Path) -> None:
    """The per-push CI invariant: the tree's own version stays a release form."""
    pyproject, changelog = write_tree(tmp_path, "0.0.1.post1")
    with pytest.raises(GateError, match="outside the Phase-0 release grammar"):
        run_gate(
            ref=None,
            tag=None,
            dry_run=True,
            pyproject=pyproject,
            changelog=changelog,
            verify_dist_dir=None,
        )


# ── Version consistency: the tag names the commit's own version, byte for byte ───────────


def test_a_tag_naming_a_different_version_than_pyproject_is_refused(tmp_path: Path) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    with pytest.raises(GateError) as excinfo:
        run_gate(
            ref="refs/tags/v0.0.1.dev1",
            tag=None,
            dry_run=False,
            pyproject=pyproject,
            changelog=changelog,
            verify_dist_dir=None,
        )
    message = str(excinfo.value)
    assert "0.0.1.dev1" in message
    assert "0.0.1.dev0" in message


# ── The changelog contract ───────────────────────────────────────────────────────────────


def test_a_final_tag_without_its_dated_section_is_refused(tmp_path: Path) -> None:
    changelog_without_release = "# Changelog\n\n## [Unreleased]\n\n- Entry.\n"
    pyproject, changelog = write_tree(tmp_path, "0.2.0", changelog_without_release)
    with pytest.raises(GateError, match=r"no dated section for 0\.2\.0"):
        run_gate(
            ref="refs/tags/v0.2.0",
            tag=None,
            dry_run=False,
            pyproject=pyproject,
            changelog=changelog,
            verify_dist_dir=None,
        )


def test_an_undated_release_heading_does_not_satisfy_a_final_tag(tmp_path: Path) -> None:
    undated = "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - someday\n\n- Entry.\n"
    _pyproject, changelog = write_tree(tmp_path, "0.2.0", undated)
    with pytest.raises(GateError, match="no dated section"):
        changelog_notes(changelog, "0.2.0", "final")


def test_a_missing_unreleased_heading_is_refused(tmp_path: Path) -> None:
    _pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0", "# Changelog\n\n- stuff\n")
    with pytest.raises(GateError, match=r"no `## \[Unreleased\]` section"):
        changelog_notes(changelog, "0.0.1.dev0", "dev")


def test_notes_extraction_stops_at_the_next_section_and_trims_blank_edges(
    tmp_path: Path,
) -> None:
    _pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    heading, body = changelog_notes(changelog, "0.0.1.dev0", "dev")
    assert heading == release_gate.UNRELEASED_HEADING
    assert body.startswith("### Added")
    assert body.endswith("- Another unreleased entry.")
    assert "## [0.1.0]" not in body


def test_an_empty_unreleased_section_is_allowed(tmp_path: Path) -> None:
    """Right after a release the Unreleased section is legitimately empty."""
    text = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-09-01\n\n- Entry.\n"
    _pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0", text)
    heading, body = changelog_notes(changelog, "0.0.1.dev0", "dev")
    assert heading == release_gate.UNRELEASED_HEADING
    assert body == ""


# ── No-verdict inputs (exit 2, never a quiet pass) ───────────────────────────────────────


def test_a_missing_pyproject_is_a_no_verdict(tmp_path: Path) -> None:
    with pytest.raises(GateInputError, match="no pyproject.toml"):
        project_version(tmp_path / "pyproject.toml")


def test_a_pyproject_without_a_version_is_a_no_verdict(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "gebra"\n', encoding="utf-8")
    with pytest.raises(GateInputError, match="no \\[project\\].version"):
        project_version(pyproject)


def test_a_missing_changelog_is_a_no_verdict(tmp_path: Path) -> None:
    with pytest.raises(GateInputError, match="no changelog"):
        changelog_notes(tmp_path / "CHANGELOG.md", "0.0.1.dev0", "dev")


def test_a_missing_dist_directory_is_a_no_verdict(tmp_path: Path) -> None:
    with pytest.raises(GateInputError, match="no dist directory"):
        verify_dist(tmp_path / "dist", "0.0.1.dev0")


# ── The distribution check: exactly one wheel + one sdist, exactly this version ──────────


def test_verify_dist_accepts_exactly_the_two_expected_artifacts(tmp_path: Path) -> None:
    dist = touch_dist(tmp_path, "gebra-0.0.1.dev0-py3-none-any.whl", "gebra-0.0.1.dev0.tar.gz")
    assert verify_dist(dist, "0.0.1.dev0") == (
        "gebra-0.0.1.dev0-py3-none-any.whl",
        "gebra-0.0.1.dev0.tar.gz",
    )


def test_verify_dist_ignores_files_that_are_not_distributions(tmp_path: Path) -> None:
    """Only wheels and sdists are policed; a stray text file is not a distribution."""
    dist = touch_dist(
        tmp_path, "gebra-0.0.1.dev0-py3-none-any.whl", "gebra-0.0.1.dev0.tar.gz", "notes.txt"
    )
    assert len(verify_dist(dist, "0.0.1.dev0")) == 2


def test_two_wheels_side_by_side_are_refused(tmp_path: Path) -> None:
    dist = touch_dist(
        tmp_path,
        "gebra-0.0.1.dev0-py3-none-any.whl",
        "gebra-0.0.1.dev1-py3-none-any.whl",
        "gebra-0.0.1.dev0.tar.gz",
    )
    with pytest.raises(GateError, match="exactly one wheel and one sdist"):
        verify_dist(dist, "0.0.1.dev0")


def test_a_missing_sdist_is_refused(tmp_path: Path) -> None:
    dist = touch_dist(tmp_path, "gebra-0.0.1.dev0-py3-none-any.whl")
    with pytest.raises(GateError, match="exactly one wheel and one sdist"):
        verify_dist(dist, "0.0.1.dev0")


def test_artifacts_for_a_different_version_are_refused(tmp_path: Path) -> None:
    dist = touch_dist(tmp_path, "gebra-0.0.1.dev1-py3-none-any.whl", "gebra-0.0.1.dev1.tar.gz")
    with pytest.raises(GateError, match="do not carry the gated version 0.0.1.dev0"):
        verify_dist(dist, "0.0.1.dev0")


def test_a_platform_wheel_tag_is_refused(tmp_path: Path) -> None:
    """This package is pure Python by construction; a platform tag is build drift."""
    dist = touch_dist(
        tmp_path, "gebra-0.0.1.dev0-cp313-cp313-linux_x86_64.whl", "gebra-0.0.1.dev0.tar.gz"
    )
    with pytest.raises(GateError, match="do not carry the gated version"):
        verify_dist(dist, "0.0.1.dev0")


# ── Workflow outputs and notes files ─────────────────────────────────────────────────────


def test_github_output_appends_the_three_outputs_without_truncating(tmp_path: Path) -> None:
    output = tmp_path / "github_output.txt"
    output.write_text("existing=kept\n", encoding="utf-8")
    verdict = Verdict(
        version="0.0.1.dev0",
        kind="dev",
        tag="v0.0.1.dev0",
        notes_heading="## [Unreleased]",
        notes="",
    )
    emit_github_output(output, verdict)
    assert output.read_text(encoding="utf-8") == (
        "existing=kept\nversion=0.0.1.dev0\nkind=dev\npublish=false\n"
    )


def test_publish_emits_true_only_for_the_final_kind(tmp_path: Path) -> None:
    output = tmp_path / "github_output.txt"
    verdict = Verdict(version="0.1.0", kind="final", tag="v0.1.0", notes_heading="h", notes="")
    emit_github_output(output, verdict)
    assert "publish=true" in output.read_text(encoding="utf-8")


# ── The CLI: exit codes are the workflow's contract ──────────────────────────────────────


def test_cli_happy_dev_tag_exits_zero_and_writes_notes_and_outputs(tmp_path: Path) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    notes = tmp_path / "release-notes.md"
    output = tmp_path / "github_output.txt"
    code = main(
        [
            "--ref",
            "refs/tags/v0.0.1.dev0",
            "--pyproject",
            str(pyproject),
            "--changelog",
            str(changelog),
            "--notes-out",
            str(notes),
            "--github-output",
            str(output),
        ]
    )
    assert code == 0
    assert notes.read_text(encoding="utf-8").startswith("## [Unreleased]\n\n")
    assert "publish=false" in output.read_text(encoding="utf-8")


def test_cli_refusal_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    code = main(
        [
            "--ref",
            "refs/tags/v0.0.1.dev1",
            "--pyproject",
            str(pyproject),
            "--changelog",
            str(changelog),
        ]
    )
    assert code == 1
    assert "REFUSED" in capsys.readouterr().err


def test_cli_no_verdict_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject, _changelog = write_tree(tmp_path, "0.0.1.dev0")
    code = main(
        [
            "--dry-run",
            "--pyproject",
            str(pyproject),
            "--changelog",
            str(tmp_path / "missing-changelog.md"),
        ]
    )
    assert code == 2
    assert "no verdict" in capsys.readouterr().err


def test_cli_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["--ref", "refs/tags/v0.0.1.dev0", "--dry-run"])


def test_cli_verify_dist_is_wired_through(tmp_path: Path) -> None:
    pyproject, changelog = write_tree(tmp_path, "0.0.1.dev0")
    dist = touch_dist(tmp_path, "gebra-0.0.1.dev0-py3-none-any.whl", "gebra-0.0.1.dev0.tar.gz")
    code = main(
        [
            "--tag",
            "v0.0.1.dev0",
            "--pyproject",
            str(pyproject),
            "--changelog",
            str(changelog),
            "--verify-dist",
            str(dist),
        ]
    )
    assert code == 0


# ── WA-07: the gate itself reaches nothing ───────────────────────────────────────────────


ALLOWED_GATE_IMPORTS = {
    "__future__",
    "argparse",
    "dataclasses",
    "pathlib",
    "re",
    "sys",
    "typing",
    # The TOML parser, under both its stdlib name and its pre-3.11 name — the import is
    # version-guarded and `tomli` is already a base dependency below 3.11.
    "tomllib",
    "tomli",
}


def test_the_gate_imports_stdlib_only() -> None:
    """The module's stdlib-only claim, held by a sweep rather than by its own docstring.

    Same guard as the coverage gate and the CI-gate action driver: both workflows run this
    tool on a bare `setup-python` before any environment sync, so a third-party import
    would fail the job — and importing it must reach no gebra code, no substrate, no
    subprocess and no network client.
    """
    tree = ast.parse((REPO_ROOT / "tools" / "release_gate.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None and node.level == 0
            imported.add(node.module.partition(".")[0])
    assert imported <= ALLOWED_GATE_IMPORTS
    assert "gebra" not in imported
    assert "subprocess" not in imported
    assert "socket" not in imported
    assert "urllib" not in imported


# ── The repository's own tree stays release-ready (what CI's dry-run step enforces) ──────


def test_the_declared_version_parses_inside_the_release_grammar() -> None:
    version = project_version(REPO_ROOT / "pyproject.toml")
    assert classify_version(version) in {"dev", "prerelease", "final"}


def test_the_changelog_carries_its_unreleased_section() -> None:
    heading, _body = changelog_notes(REPO_ROOT / "CHANGELOG.md", "0.0.0.dev0", "dev")
    assert heading == release_gate.UNRELEASED_HEADING


def test_the_full_dry_run_gate_passes_on_this_tree() -> None:
    """`python tools/release_gate.py --dry-run` — the CI step, executed in-process."""
    assert main(["--dry-run"]) == 0
