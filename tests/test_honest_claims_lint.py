"""Behaviour tests for the honest-claims lint (TE-15, WA-06).

The lint is the CI enforcement of one rule: repo-authored prose never claims more than "a
static check over the extracted IR passed" (SOW.md §6). These tests pin what that means in
practice — a seeded banned phrase anywhere in scanned source/docs fails the build and names
its location, the vendored fixture corpus is exempt by path regardless of content, and an
allow-pragma with a real justification (never a bare one) is the only other way past it.

Everything here reads files and matches substrings. The subprocess tests run the lint script
itself — the exact command CI runs, so its exit status is observed rather than assumed. No
workflow node is executed, no LLM is called, no socket is opened (WA-07).

Note on fixture text: several tests seed a banned phrase into scanned *file content* to
prove the lint's own detection logic actually fires. `_phrase()` assembles that seeded text
from word fragments at call time, so the reconstructed phrase exists in the tmp-file content
under test but never as a contiguous substring on any single line of *this* source file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.honest_claims_lint import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    PhraseListError,
    load_phrases,
    scan,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LINT = REPO_ROOT / "tools" / "honest_claims_lint.py"
PHRASES = REPO_ROOT / "tools" / "honest-claims-phrases.txt"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked —
# mirrors tests/test_provenance_guard.py's `requires_companion` pattern.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
COMPANION_PHRASES = COMPANION / "tools" / "honest-claims" / "banned-phrases.txt"

requires_companion = pytest.mark.skipif(
    not COMPANION_PHRASES.is_file(),
    reason="the development-process repository is not checked out beside this one",
)


def _phrase(*parts: str, sep: str = " ") -> str:
    """Assemble a banned phrase from fragments — see the module docstring's note."""
    return sep.join(parts)


@pytest.fixture
def phrases() -> tuple[str, ...]:
    return load_phrases(PHRASES)


def _run_lint(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the lint exactly as CI does — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(LINT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


# ── The recorded state of this repository ──


def test_the_repository_is_clean_right_now(phrases: tuple[str, ...]) -> None:
    """The premise of every other test: nothing repo-authored is overstated today."""
    report = scan(REPO_ROOT, phrases)
    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]
    assert report.checked > 0


def test_the_phrase_list_carries_the_wa_06_named_bans(phrases: tuple[str, ...]) -> None:
    """SOW.md §6 names two phrases explicitly banned everywhere; both must be enforced."""
    assert _phrase("proves", "termination") in phrases
    assert _phrase("verified", "agent", "behavior") in phrases


# ── What the lint rejects: acceptance box 1 ──


def test_a_seeded_banned_phrase_in_source_is_reported(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    (tmp_path / "src").mkdir()
    seeded = tmp_path / "src" / "seeded.py"
    seed_phrase = _phrase("formally", "verified")
    seeded.write_text(f'"""This gebra check {seed_phrase} the workflow."""\n', encoding="utf-8")

    report = scan(tmp_path, phrases)

    assert not report.ok
    assert len(report.violations) == 1
    violation = report.violations[0]
    assert violation.path == "src/seeded.py"
    assert violation.line_no == 1
    assert violation.detail == seed_phrase


def test_a_seeded_banned_phrase_in_docs_is_reported(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("guaran", "tees", sep="")
    (tmp_path / "docs" / "guide.md").write_text(
        f"gebra {seed_phrase} your agent halts.\n", encoding="utf-8"
    )

    report = scan(tmp_path, phrases)

    assert not report.ok
    assert any(v.detail == seed_phrase for v in report.violations)


def test_multiple_banned_phrases_on_one_line_are_all_reported(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    first = _phrase("guaran", "tees", sep="")
    second = _phrase("cannot", "fail")
    (tmp_path / "README.md").write_text(
        f"This tool {first} correctness and {second}.\n", encoding="utf-8"
    )

    report = scan(tmp_path, phrases)

    detected = {v.detail for v in report.violations}
    assert {first, second} <= detected


def test_the_ci_command_fails_on_a_seeded_violation(tmp_path: Path) -> None:
    """The acceptance criterion: a seeded banned phrase fails the build and is named."""
    (tmp_path / "src").mkdir()
    seed_phrase = _phrase("verified", "agent", "behavior")
    (tmp_path / "src" / "seeded.py").write_text(
        f'MESSAGE = "{seed_phrase}, always."\n', encoding="utf-8"
    )

    result = _run_lint("--root", str(tmp_path), "--phrases", str(PHRASES))

    assert result.returncode == 1
    assert "src/seeded.py:1" in result.stderr
    assert seed_phrase in result.stderr


def test_the_ci_command_passes_on_the_working_tree() -> None:
    result = _run_lint()
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# ── What the lint exempts: acceptance box 2 ──


def test_a_banned_phrase_inside_the_vendored_corpus_is_exempt(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    """Vendored fixtures are frozen (WA-04/WA-11); their content is out of scope by path."""
    vendored = tmp_path / "tests" / "fixtures" / "properties" / "mixed"
    vendored.mkdir(parents=True)
    seed_phrase = _phrase("formally", "verified")
    (vendored / "seeded.yaml").write_text(
        f"note: this fixture {seed_phrase} the cycle\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "clean.py").write_text('"""Nothing to see here."""\n', encoding="utf-8")

    report = scan(tmp_path, phrases, include=DEFAULT_INCLUDE + ("tests/**/*.yaml",))

    assert report.ok
    assert "tests/fixtures/properties/mixed/seeded.yaml" not in {v.path for v in report.violations}


def test_the_ci_command_exempts_the_vendored_corpus(tmp_path: Path) -> None:
    vendored = tmp_path / "tests" / "fixtures" / "properties"
    vendored.mkdir(parents=True)
    seed_phrase = _phrase("formally", "verified")
    (vendored / "seeded.yaml").write_text(
        f"note: this fixture {seed_phrase} the cycle\n", encoding="utf-8"
    )

    result = _run_lint(
        "--root",
        str(tmp_path),
        "--phrases",
        str(PHRASES),
        "--include",
        "tests/**/*.yaml",
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_default_exclude_covers_the_vendored_fixture_tree() -> None:
    assert "tests/fixtures/properties/**" in DEFAULT_EXCLUDE


# ── The allow-pragma: the spec-quotation escape hatch ──


def test_a_justified_pragma_on_the_same_line_exempts_the_phrase(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("formally", "verified")
    (tmp_path / "docs" / "wa06.md").write_text(
        f'The banned phrase is "{seed_phrase}".  '
        "<!-- honest-claims: allow: citing the ban itself -->\n",
        encoding="utf-8",
    )

    report = scan(tmp_path, phrases)

    assert report.ok


def test_a_justified_pragma_on_the_line_above_exempts_the_phrase(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("formally", "verified")
    (tmp_path / "docs" / "wa06.md").write_text(
        "<!-- honest-claims: allow: citing the ban itself -->\n"
        f'The banned phrase is "{seed_phrase}".\n',
        encoding="utf-8",
    )

    report = scan(tmp_path, phrases)

    assert report.ok


def test_a_pragma_without_justification_is_itself_a_violation(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("formally", "verified")
    (tmp_path / "docs" / "wa06.md").write_text(
        f'<!-- honest-claims: allow -->\nThe banned phrase is "{seed_phrase}".\n',
        encoding="utf-8",
    )

    report = scan(tmp_path, phrases)

    assert not report.ok
    kinds = {v.kind for v in report.violations}
    assert "pragma" in kinds
    # The unjustified pragma does not launder the phrase it sits next to either.
    assert any(v.detail == seed_phrase for v in report.violations)


def test_the_pragma_cannot_be_used_to_silence_a_distant_line(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("formally", "verified")
    (tmp_path / "docs" / "wa06.md").write_text(
        "honest-claims: allow: unrelated justification\n"
        "\n"
        f'The banned phrase is "{seed_phrase}" three lines down.\n',
        encoding="utf-8",
    )

    report = scan(tmp_path, phrases)

    assert not report.ok
    assert any(v.detail == seed_phrase for v in report.violations)


# ── The phrase list itself ──


def test_a_missing_phrase_list_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PhraseListError):
        load_phrases(tmp_path / "absent.txt")


def test_the_ci_command_fails_when_the_phrase_list_is_missing(tmp_path: Path) -> None:
    result = _run_lint("--phrases", str(tmp_path / "absent.txt"))
    assert result.returncode == 1
    assert "phrase list not found" in result.stderr


def test_there_is_no_bypass_flag() -> None:
    help_text = _run_lint("--help").stdout
    for bypass in ("--skip", "--force", "--ignore", "--no-fail"):
        assert bypass not in help_text


@requires_companion
def test_the_phrase_list_matches_the_companion_skills_copy() -> None:
    """The CI-enforced list and the interactive skill's list must not silently drift.

    Two independent lists exist by design (tools/honest-claims-phrases.txt is this
    repo's own CI-enforced copy; the companion repository's
    `tools/honest-claims/banned-phrases.txt` drives the interactive review), but nothing keeps a
    phrase added to one from being forgotten in the other except this assertion.
    """
    ci_phrases = set(load_phrases(PHRASES))
    skill_phrases = set(load_phrases(COMPANION_PHRASES))
    assert ci_phrases == skill_phrases


# ── Wiring: the lint runs in CI ──


def _ci_run_steps() -> list[str]:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step.get("run"), str)
    ]


def test_ci_runs_the_honest_claims_lint() -> None:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "honest-claims" in workflow["jobs"], "the lint needs its own CI job"
    assert any("tools/honest_claims_lint.py" in step for step in _ci_run_steps())
