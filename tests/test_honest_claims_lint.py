"""Behaviour tests for the honest-claims lint (TE-15, WA-06).

The lint is the CI enforcement of one rule: repo-authored prose never claims more than "a
static check over the extracted IR passed" (SOW.md §6). These tests pin what that means in
practice — a seeded banned phrase anywhere in scanned source/docs fails the build and names
its location, the vendored fixture corpus is exempt by path regardless of content, and an
allow-pragma with a real justification (never a bare one) is the only other way past it.

Since TOOL-04 the module also pins the surfaces that *read* this gate rather than
reimplementing it. The allow-pragma's window is computed once, by :func:`exempt_lines`, and
published by ``--format json`` beside the violations, so the ``/honest-claims`` review skill
can honor exactly the exemptions CI honors instead of deciding for itself what "adjacent"
means. The skill assertions read the staged file where the private development-process
repository is checked out beside this one, and the installed file once the owner has
installed it — the same two-stage pin ``tests/testing/test_fixture_review.py`` uses.

Everything here reads files and matches substrings. The subprocess tests run the lint script
itself — the exact command CI runs, so its exit status is observed rather than assumed. No
workflow node is executed, no LLM is called, no socket is opened (WA-07).

Note on fixture text: several tests seed a banned phrase into scanned *file content* to
prove the lint's own detection logic actually fires. `_phrase()` assembles that seeded text
from word fragments at call time, so the reconstructed phrase exists in the tmp-file content
under test but never as a contiguous substring on any single line of *this* source file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.honest_claims_lint import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    REMEDIATION,
    PhraseListError,
    exempt_lines,
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
#: The upgraded skill as staged for the owner to install — writable by the session that
#: built it, unlike the installed skill's own directory.
STAGED_SKILL = COMPANION / "docs" / "setups" / "TOOL-04" / "honest-claims-SKILL.md"
#: The installed skill, reached through the companion's neutral ``tools/`` surface so the
#: public tree pins it without naming an agent-tooling path (PD-050 hygiene, as for
#: ``tools/fixture-review.md`` and ``tools/plan-status.md``).
COMPANION_SKILL = COMPANION / "tools" / "honest-claims.md"
SETUP_NOTE = "docs/setups/TOOL-04.md in the development-process repository"

requires_companion = pytest.mark.skipif(
    not COMPANION_PHRASES.is_file(),
    reason="the development-process repository is not checked out beside this one",
)
requires_staged_skill = pytest.mark.skipif(
    not STAGED_SKILL.is_file(),
    reason="the development-process repository is not checked out beside this one",
)
requires_installed_skill = pytest.mark.skipif(
    not COMPANION_SKILL.is_file(),
    reason=f"the upgraded skill is not installed yet — see {SETUP_NOTE}",
)


def _phrase(*parts: str, sep: str = " ") -> str:
    """Assemble a banned phrase from fragments — see the module docstring's note."""
    return sep.join(parts)


#: PROPERTY-CATALOG-SPEC §B.1 names three phrasings banned in any P-08 rendering. One of the
#: three has been listed since TE-15; TOOL-04 adds the other two, which the VAL-13 pre-review
#: filed as a follow-up on this track.
_B1_ADDITIONS = (_phrase("proves", "determinism"), _phrase("guaranteed", "reproducible"))
#: The singular-guarantee forms that evade the plural entry, in the claim-shaped variants
#: that collide with nothing — see docs/setups/TOOL-04.md for why the bare word is not one
#: of them.
_GUARANTEE_ADDITIONS = (
    _phrase("guarantee", "termination"),
    _phrase("we", "guarantee"),
    _phrase("guarantee", "ing", sep=""),
)

requires_extended_list = pytest.mark.skipif(
    not set(_B1_ADDITIONS + _GUARANTEE_ADDITIONS) <= set(load_phrases(PHRASES)),
    reason=(
        "the phrase-list additions are owner-reviewed and owner-committed (TE-15 "
        f"convention) — see {SETUP_NOTE}"
    ),
)


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


def test_the_exemption_map_covers_the_pragma_line_and_its_neighbours() -> None:
    """The window, computed in one place — every consumer reads it rather than deciding."""
    lines = [
        "untouched",
        "honest-claims: allow: citing the ban itself",
        "the quoted line",
        "out of reach",
    ]

    covered = exempt_lines(lines)

    assert set(covered) == {1, 2, 3}
    assert all(pragma_line == 2 for pragma_line, _ in covered.values())
    assert covered[3][1] == "citing the ban itself"


def test_a_bare_pragma_covers_nothing_not_even_its_own_line() -> None:
    assert exempt_lines(["honest-claims: allow", "a line"]) == {}


@pytest.mark.parametrize(
    "pragma",
    [
        "<!-- honest-claims: allow: -->",
        "/* honest-claims: allow: */",
        "# honest-claims: allow:",
    ],
)
def test_a_comment_closer_is_not_a_justification(pragma: str) -> None:
    """A bare pragma in a comment syntax that has to be closed is still a bare pragma."""
    assert exempt_lines([pragma, "a line"]) == {}


def test_a_justification_is_reported_without_its_comment_closer() -> None:
    """It is published to reviewers now, so the reason is the reason and nothing else."""
    covered = exempt_lines(["<!-- honest-claims: allow: citing the ban itself -->"])

    assert covered[1] == (1, "citing the ban itself")


def test_overlapping_pragmas_report_the_earlier_one() -> None:
    """Two pragmas reaching one line make the mapping ambiguous unless it is ruled."""
    lines = [
        "honest-claims: allow: the first reason",
        "the line both reach",
        "honest-claims: allow: the second reason",
    ]

    assert exempt_lines(lines)[2] == (1, "the first reason")


def test_the_exemption_map_is_the_one_the_phrase_gate_applies(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    """Not two computations that agree today — the gate skips exactly what the map holds."""
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("formally", "verified")
    page = tmp_path / "docs" / "wa06.md"
    page.write_text(
        f'A quoted "{seed_phrase}" claim.\n'
        "<!-- honest-claims: allow: citing the ban itself -->\n"
        f'Another quoted "{seed_phrase}".\n'
        "\n"
        f'An unquoted "{seed_phrase}" claim, out of the pragma\'s reach.\n',
        encoding="utf-8",
    )

    report = scan(tmp_path, phrases)
    covered = set(exempt_lines(page.read_text(encoding="utf-8").splitlines()))

    assert covered == {1, 2, 3}
    assert [violation.line_no for violation in report.violations] == [5]
    assert {exemption.line_no for exemption in report.exemptions} == covered
    assert {exemption.path for exemption in report.exemptions} == {"docs/wa06.md"}


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


# ── The machine surface: what a reviewer past the substring list reads ──


def _seeded_page(tmp_path: Path) -> str:
    """A docs page holding one exempted phrase and one that is not. Returns the phrase."""
    (tmp_path / "docs").mkdir()
    seed_phrase = _phrase("proven", "correct")
    (tmp_path / "docs" / "wa06.md").write_text(
        "<!-- honest-claims: allow: naming what the list rejects, not claiming it -->\n"
        f'The list rejects "{seed_phrase}".\n'
        "\n"
        f"This page is {seed_phrase}.\n",
        encoding="utf-8",
    )
    return seed_phrase


def _json_run(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = _run_lint(*args, "--format", "json")
    payload: dict[str, Any] = json.loads(result.stdout)
    return result, payload


def test_the_json_report_names_the_violations_and_the_exempted_lines(tmp_path: Path) -> None:
    seed_phrase = _seeded_page(tmp_path)

    result, payload = _json_run("--root", str(tmp_path), "--phrases", str(PHRASES))

    assert result.returncode == 1
    assert payload["ok"] is False
    assert payload["checked"] == 1
    assert [(v["path"], v["line"], v["detail"]) for v in payload["violations"]] == [
        ("docs/wa06.md", 4, seed_phrase)
    ]
    assert [(e["line"], e["pragma_line"]) for e in payload["exemptions"]] == [(1, 1), (2, 1)]
    assert all(
        e["justification"] == "naming what the list rejects, not claiming it"
        for e in payload["exemptions"]
    )


def test_the_json_report_carries_the_lints_own_remediation(tmp_path: Path) -> None:
    """A surface reporting these findings quotes this rather than composing advice."""
    _seeded_page(tmp_path)

    _, payload = _json_run("--root", str(tmp_path), "--phrases", str(PHRASES))

    assert payload["remediation"] == REMEDIATION


def test_the_json_report_reaches_stdout_at_either_verdict(tmp_path: Path) -> None:
    """The text form moves a failure to stderr; a machine reader must not have to follow."""
    _seeded_page(tmp_path)
    failing, failing_payload = _json_run("--root", str(tmp_path), "--phrases", str(PHRASES))

    (tmp_path / "docs" / "wa06.md").write_text("Nothing overstated here.\n", encoding="utf-8")
    clean, clean_payload = _json_run("--root", str(tmp_path), "--phrases", str(PHRASES))

    assert (failing.returncode, failing_payload["ok"]) == (1, False)
    assert (clean.returncode, clean_payload["ok"]) == (0, True)
    assert clean_payload["violations"] == []


def test_the_two_formats_reach_the_same_verdict_on_the_working_tree() -> None:
    text = _run_lint()
    machine, payload = _json_run()

    assert text.returncode == machine.returncode == 0
    assert payload["ok"] is True
    assert payload["checked"] > 0


def test_a_review_scope_is_the_changed_paths_passed_as_includes(tmp_path: Path) -> None:
    """How the skill scopes a review: one --include per path a diff named."""
    _seeded_page(tmp_path)
    (tmp_path / "README.md").write_text("Untouched by this change.\n", encoding="utf-8")

    _, payload = _json_run(
        "--root", str(tmp_path), "--phrases", str(PHRASES), "--include", "docs/wa06.md"
    )

    assert payload["checked"] == 1
    assert {v["path"] for v in payload["violations"]} == {"docs/wa06.md"}


# ── The phrase list itself ──


def test_a_phrase_added_to_the_shared_list_changes_the_verdict(tmp_path: Path) -> None:
    """Acceptance box 1, on the half of it a test can hold: behaviour follows the data file.

    The same tree is scanned twice by the same command — once against the list as merged,
    once against a copy carrying one extra phrase. Nothing but the data file differs, and the
    verdict flips; scanning against the merged list again is the "then reverted" half.
    """
    (tmp_path / "docs").mkdir()
    probe = _phrase("halts", "on", "every", "input")
    (tmp_path / "docs" / "page.md").write_text(f"This workflow {probe}.\n", encoding="utf-8")
    extended = tmp_path / "phrases.txt"
    extended.write_text(
        f"{PHRASES.read_text(encoding='utf-8')}{probe}\n",
        encoding="utf-8",
    )

    before = _run_lint("--root", str(tmp_path), "--phrases", str(PHRASES))
    during = _run_lint("--root", str(tmp_path), "--phrases", str(extended))
    reverted = _run_lint("--root", str(tmp_path), "--phrases", str(PHRASES))

    assert before.returncode == 0
    assert during.returncode == 1
    assert probe in during.stderr
    assert reverted.returncode == 0


def test_a_phrase_list_cannot_reach_an_overstatement_that_spells_no_phrase(
    tmp_path: Path, phrases: tuple[str, ...]
) -> None:
    """Why the review skill keeps a second pass — acceptance box 2's premise, seeded here.

    Every sentence below promises something about a running agent, and not one of them uses a
    listed phrase. A substring gate passes them; only a reader catches them, which is what the
    skill's prose-level pass is for and why this lint is half of WA-06 rather than all of it.
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "pitch.md").write_text(
        "gebra makes sure your agent halts.\n"
        "Your workflow is safe to ship once the check is green.\n"
        "It eliminates infinite loops before they reach production.\n",
        encoding="utf-8",
    )

    report = scan(tmp_path, phrases)

    assert report.ok, [f"{v.line_no}: {v.detail}" for v in report.violations]


@requires_extended_list
def test_the_phrase_list_carries_the_property_catalog_b1_phrasings(
    phrases: tuple[str, ...],
) -> None:
    """PROPERTY-CATALOG-SPEC §B.1 bans three phrasings in any P-08 rendering; all three are
    enforced here, which is what the VAL-13 pre-review filed as a follow-up on this track."""
    assert set(_B1_ADDITIONS) <= set(phrases)
    assert _phrase("verified", "agent", "behavior") in phrases


@requires_extended_list
def test_the_phrase_list_covers_the_singular_guarantee_forms(
    phrases: tuple[str, ...],
) -> None:
    """The plural entry alone let the singular through — the mid-plan audit's finding."""
    assert set(_GUARANTEE_ADDITIONS) <= set(phrases)


@requires_extended_list
def test_the_extended_list_leaves_the_repository_clean(phrases: tuple[str, ...]) -> None:
    """Coverage that needed a pragma on a line it should not have would be over-reach."""
    report = scan(REPO_ROOT, phrases)
    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]


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


# ── The review skill reads this gate rather than reimplementing it (TOOL-04) ──


def _skill_text() -> str:
    return STAGED_SKILL.read_text(encoding="utf-8")


@requires_staged_skill
def test_the_skill_reaches_its_phrase_verdict_by_running_this_lint() -> None:
    text = _skill_text()
    assert "tools/honest_claims_lint.py" in text
    assert "--format json" in text
    assert "exit status" in text


@requires_staged_skill
def test_the_skill_scopes_the_lint_to_the_paths_the_diff_named() -> None:
    """An unscoped run answers the repository's question, not the change's."""
    text = _skill_text()
    assert "--include" in text
    assert "git diff --name-only" in text


@requires_staged_skill
def test_the_skill_keeps_vendored_prose_out_of_scope() -> None:
    """The library's corpus is out by default; the other root's frozen trees are not."""
    text = _skill_text()
    assert "--exclude" in text
    for tree in ("docs/specs/**", "docs/briefs/**", "docs/decisions/**", "docs/notes/**"):
        assert tree in text, tree


@requires_staged_skill
def test_the_skill_reads_the_exemptions_instead_of_recomputing_the_window() -> None:
    """The point of the card: one pragma computation, honored on both surfaces.

    The skill's own pass is where the drift used to live — it could flag a line the lint was
    told to leave alone. It now takes the exempted lines from the lint's output, which is
    only credible if it never restates the rules that produce them.
    """
    text = _skill_text()
    assert "exemptions" in text

    lowered = text.lower()
    restated = [
        rule
        for rule in (
            "directly above",
            "above/below",
            "line above",
            "line below",
            "adjacent",
            "without justification",
            "no justification",
        )
        if rule in lowered
    ]
    assert not restated, f"the skill restates the pragma's own rules: {restated}"


@requires_staged_skill
def test_the_skill_keeps_the_pass_the_lint_cannot_compute() -> None:
    """The skill's remaining value: overstatement no substring list can express."""
    text = _skill_text().lower()
    assert "claim class" in text
    assert "witness" in text
    assert any(marker in text for marker in ("paraphrase", "implication", "prose-level"))


@requires_staged_skill
def test_the_skill_still_refuses_to_launder_a_finding() -> None:
    never = _skill_text().rsplit("## NEVER", 1)[-1].lower()
    assert "never edit the banned-phrase list" in never
    assert "never insert an allow-pragma" in never


@requires_installed_skill
def test_the_installed_skill_is_the_staged_one() -> None:
    """Once installed, the two cannot drift: the pin is a byte comparison."""
    assert COMPANION_SKILL.read_bytes() == STAGED_SKILL.read_bytes()
