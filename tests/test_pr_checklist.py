"""The pre-merge checks that read their own records, and the skill that relays them (TOOL-07).

Three of the obligations a review owes before a merge have a record or a gate that already
answers them — the CLA signature record (GOV-09), the WA-05 golden guard, and the GOV-03
release gate — and before this card the review answered them a second time, from prose. Two
readings of one contract is one drift away from a review passing what CI refuses, which is the
same failure the fixture, honest-claims and provenance upgrades closed on their own surfaces.

Four things are held here.

**A verdict is the record's, not a second opinion.** The golden check blocks exactly when
:func:`tools.golden_guard.evaluate_commit` returns a violation — asserted as agreement across a
seeded matrix rather than on one example — and the release check blocks exactly when
:func:`tools.release_gate.run_gate` raises. The CLA check is the one with no CI job behind it,
so what is pinned instead is that it reads the record's *columns by their headers* and applies
the three rules the record and the agreement state in their own prose.

**A refusal names a step, not a warning.** Every blocking finding carries a remediation that
names the file, row or command that clears it, and the tests read those strings rather than
just the status, because "BLOCKED" without a next action is the checklist this card replaced.

**A check that cannot be evaluated is not a pass.** An unreadable record, a git range that
cannot be walked, a missing ``pyproject.toml`` — each reports ERROR and exits 2.

**The skill and this module stay one computation.** The staged skill must take its three
verdicts by running this script, must restate neither the WA-05 trailer forms nor the tag
grammar, and must keep the half no script can reach — commit format, card linkage, board sync
and the prose review. Once the owner installs it (see the setup note) the installed file must
be the staged one byte for byte.

WA-07: nothing here builds a workflow, runs a node, calls a model or opens a socket, and the
module's own import closure is swept rather than asserted in prose. The git boundary is faked
exactly as ``tests/test_golden_guard.py`` fakes it — no test spawns git — and the command-line
children run this repository's own script under this interpreter, which is the command the skill
runs.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tools import golden_guard, release_gate
from tools.pr_checklist import (
    CLA_AGREEMENT,
    CLA_RECORD,
    CODEOWNERS,
    Check,
    ChecklistInputError,
    Commit,
    Report,
    agreement_version,
    as_json,
    check_cla,
    check_goldens,
    check_release,
    code_owner_handles,
    commits_from_range,
    format_report,
    load_signatures,
    main,
    normalize_handle,
    review,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "pr_checklist.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

#: The development-process repository: present in a working checkout, absent in the library
#: repository's own CI, where cross-repository assertions skip rather than fake.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
#: The skill as staged for the owner to install — writable by the session that built it.
STAGED_SKILL = COMPANION / "docs" / "setups" / "TOOL-07" / "pr-checklist-SKILL.md"
#: The installed skill, reached through the companion's neutral ``tools/`` surface so the
#: public tree carries no agent-tooling path (the arrangement TOOL-03/04/05 established).
INSTALLED_SKILL = COMPANION / "tools" / "pr-checklist.md"

requires_staged_skill = pytest.mark.skipif(
    not STAGED_SKILL.is_file(), reason="the staged skill file is not present"
)
requires_installed_skill = pytest.mark.skipif(
    not INSTALLED_SKILL.is_file(),
    reason="the upgraded skill is not installed yet (see docs/setups/TOOL-07.md)",
)

# ── The two sample pull requests the card's acceptance is measured on ─────────────────────


@dataclass(frozen=True)
class Sample:
    """One sample pull request: everything the checklist reads about a change."""

    author: str
    files: tuple[str, ...]
    message: str
    tag: str

    @property
    def commit(self) -> Commit:
        return Commit(sha=None, files=self.files, message=self.message)

    def reviewed(self) -> Report:
        return review(author=self.author, commits=(self.commit,), tag=self.tag)


#: A compliant sample: the repository owner's own change, no golden touched, the tree at the
#: version its tag would name. Every input here is real — the author is the account CODEOWNERS
#: names, and the release check runs against this repository's own pyproject and changelog.
COMPLIANT_SAMPLE = Sample(
    author="hesam-shams",
    files=(
        "src/gebra/verify/properties/termination_witness.py",
        "tests/verify/test_termination_witness.py",
        "CHANGELOG.md",
    ),
    message="fix(val): count a bounded loop's guard once [VAL-07]",
    tag="v0.0.1.dev0",
)

#: A non-compliant sample, breaking all three at once: an author with no row in the record, a
#: golden moved in a commit carrying no justification, and a tag naming a version the tree
#: does not declare.
NON_COMPLIANT_SAMPLE = Sample(
    author="octocat",
    files=(
        "tests/ir/golden/vector-001.canonical.json",
        "src/gebra/ir/canonical.py",
    ),
    message="fix(ir): retune the golden vector [IR-05]",
    tag="v0.0.1.dev9",
)


# ── Fixtures: synthetic records, written to a copy, never to the real ones ────────────────

RECORD_TEMPLATE = """# CLA signature record

Prose the maintainer keeps.

## Columns

| Column | Meaning |
|---|---|
| `GitHub handle` | The account. |

## Signatures

| GitHub handle | Legal name | Type | CLA version | Signed | Recorded | Archive | Notes |
|---|---|---|---|---|---|---|---|
{rows}

Closing prose, which is not a row.
"""

AGREEMENT_TEMPLATE = "# Contributor License Agreement\n\n**Version {version}.** Adapted from…\n"


def write_record(root: Path, rows: str) -> Path:
    path = root / "cla-signatures.md"
    path.write_text(RECORD_TEMPLATE.format(rows=rows), encoding="utf-8")
    return path


def write_agreement(root: Path, version: str = "1.0") -> Path:
    path = root / "CLA.md"
    path.write_text(AGREEMENT_TEMPLATE.format(version=version), encoding="utf-8")
    return path


def write_codeowners(root: Path, line: str = "* @hesam-shams\n") -> Path:
    path = root / "CODEOWNERS"
    path.write_text(line, encoding="utf-8")
    return path


ICLA_ROW = "| octocat | Octo Cat | ICLA | 1.0 | 2026-08-01 | 2026-08-02 | email 2026-08-02 | — |"
CCLA_ROW = "| octocat | Octo Cat | CCLA | 1.0 | 2026-08-03 | 2026-08-03 | email 2026-08-03 | Ac |"
PLACEHOLDER_ROW = "| _(none recorded yet)_ | | | | | | | |"


# ── Reading the CLA record ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    ["octocat", "@octocat", " @Octocat ", "`octocat`", "[octocat](https://github.com/octocat)"],
)
def test_a_handle_is_the_account_however_the_record_spells_it(raw: str) -> None:
    """Backticks, an `@`, a link to the account and case are presentation, not identity."""
    assert normalize_handle(raw) == "octocat"


def test_the_real_record_parses_and_holds_no_invented_row() -> None:
    """The record ships empty; the placeholder line is prose in a table, not a signature."""
    assert load_signatures(CLA_RECORD) == ()


def test_the_placeholder_row_is_not_a_signature(tmp_path: Path) -> None:
    record = write_record(tmp_path, PLACEHOLDER_ROW)
    assert load_signatures(record) == ()


def test_a_row_is_read_by_its_headers_not_its_position(tmp_path: Path) -> None:
    """A column added or moved later must not silently shift what the check compares."""
    record = tmp_path / "reordered.md"
    record.write_text(
        "## Signatures\n\n"
        "| Legal name | GitHub handle | CLA version | Type | Signed | Recorded | Archive | "
        "Notes |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| Octo Cat | octocat | 1.0 | ICLA | 2026-08-01 | 2026-08-02 | email | — |\n",
        encoding="utf-8",
    )
    (signature,) = load_signatures(record)
    assert signature.handle == "octocat"
    assert signature.kind == "ICLA"
    assert signature.version == "1.0"
    assert signature.legal_name == "Octo Cat"


def test_only_the_signatures_table_is_read(tmp_path: Path) -> None:
    """The record carries a `## Columns` table too; a row there is documentation."""
    record = write_record(tmp_path, ICLA_ROW)
    assert [signature.handle for signature in load_signatures(record)] == ["octocat"]


def test_a_missing_record_is_an_error_not_an_empty_record(tmp_path: Path) -> None:
    with pytest.raises(ChecklistInputError, match="no CLA signature record"):
        load_signatures(tmp_path / "absent.md")


def test_a_record_without_the_table_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "record.md"
    path.write_text("# CLA signature record\n\nThe table was deleted.\n", encoding="utf-8")
    with pytest.raises(ChecklistInputError, match="carries no"):
        load_signatures(path)


def test_a_table_missing_a_column_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "record.md"
    path.write_text(
        "## Signatures\n\n| GitHub handle | Legal name |\n|---|---|\n| octocat | Octo Cat |\n",
        encoding="utf-8",
    )
    with pytest.raises(ChecklistInputError, match="missing the column"):
        load_signatures(path)


def test_the_agreement_version_comes_from_the_agreements_own_title_line() -> None:
    assert agreement_version(CLA_AGREEMENT) == "1.0"


def test_an_agreement_with_no_version_line_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "CLA.md"
    path.write_text("# Agreement\n\nNo version anywhere.\n", encoding="utf-8")
    with pytest.raises(ChecklistInputError, match="declares no version"):
        agreement_version(path)


def test_the_owner_is_read_from_codeowners_and_a_team_is_not_a_handle(tmp_path: Path) -> None:
    assert "hesam-shams" in code_owner_handles(CODEOWNERS)
    path = write_codeowners(tmp_path, "# comment @ghost\n*.py @octocat @Gebra-Tech/reviewers\n")
    assert code_owner_handles(path) == frozenset({"octocat"})


# ── The CLA check ────────────────────────────────────────────────────────────────────────


def cla(
    author: str, tmp_path: Path, *, rows: str = PLACEHOLDER_ROW, version: str = "1.0", **kw: bool
) -> Check:
    return check_cla(
        author,
        record=write_record(tmp_path, rows),
        agreement=write_agreement(tmp_path, version),
        codeowners=write_codeowners(tmp_path),
        **kw,
    )


def test_a_code_owner_needs_no_row(tmp_path: Path) -> None:
    """The record says the owner's own commits are not contributions under the agreement."""
    check = cla("hesam-shams", tmp_path)
    assert check.status == "PASS"
    assert "code owner" in check.detail


def test_an_author_with_no_row_is_blocked_and_told_how_to_sign(tmp_path: Path) -> None:
    check = cla("octocat", tmp_path)
    assert check.status == "BLOCK"
    (finding,) = check.findings
    assert "no row" in finding.summary
    assert "CLA.md" in finding.remediation
    assert "gebra.dev@gmail.com" in finding.remediation
    assert "cla-signatures.md" in finding.remediation


def test_a_recorded_author_passes_with_the_row_named(tmp_path: Path) -> None:
    check = cla("octocat", tmp_path, rows=ICLA_ROW)
    assert check.status == "PASS"
    assert "ICLA" in check.detail
    assert "1.0" in check.detail


def test_the_author_argument_may_carry_an_at_sign(tmp_path: Path) -> None:
    assert cla("@OctoCat", tmp_path, rows=ICLA_ROW).status == "PASS"


def test_a_row_naming_an_older_agreement_version_does_not_cover_the_contribution(
    tmp_path: Path,
) -> None:
    """CLA.md: a new version applies to contributions submitted after it lands."""
    check = cla("octocat", tmp_path, rows=ICLA_ROW, version="1.1")
    assert check.status == "BLOCK"
    (finding,) = check.findings
    assert "1.0" in finding.summary and "1.1" in finding.summary
    assert "append-only" in finding.remediation
    assert "second row" in finding.remediation


def test_an_employer_owned_contribution_needs_a_corporate_row(tmp_path: Path) -> None:
    check = cla("octocat", tmp_path, rows=ICLA_ROW, employer_owned=True)
    assert check.status == "BLOCK"
    (finding,) = check.findings
    assert "CCLA" in finding.summary
    assert "CCLA row" in finding.remediation


def test_a_corporate_row_covers_an_employer_owned_contribution(tmp_path: Path) -> None:
    assert cla("octocat", tmp_path, rows=CCLA_ROW, employer_owned=True).status == "PASS"


def test_an_individual_row_still_covers_an_individually_owned_contribution(
    tmp_path: Path,
) -> None:
    assert cla("octocat", tmp_path, rows=ICLA_ROW, employer_owned=False).status == "PASS"


def test_an_unreadable_record_reaches_no_verdict_and_is_not_a_pass(tmp_path: Path) -> None:
    check = check_cla(
        "octocat",
        record=tmp_path / "absent.md",
        agreement=write_agreement(tmp_path),
        codeowners=write_codeowners(tmp_path),
    )
    assert check.status == "ERROR"
    assert "not a pass" in check.findings[0].remediation


def test_an_empty_author_reaches_no_verdict(tmp_path: Path) -> None:
    assert cla("  ", tmp_path).status == "ERROR"


def test_the_cla_check_reads_this_repositorys_own_record_by_default() -> None:
    """The compliant sample is real: the account CODEOWNERS names passes against the record."""
    check = check_cla("hesam-shams")
    assert check.status == "PASS"
    assert check.subject == "docs/governance/cla-signatures.md"


# ── The WA-05 golden check ───────────────────────────────────────────────────────────────

JUSTIFIED = (
    "fix(ir): re-extract after the ordering change [IR-05]\n\n"
    "Golden-Justification: DEC-11 ir_version=1.2 branch child ordering"
)
GOLDEN = "tests/ir/golden/vector-001.canonical.json"


def one(files: tuple[str, ...], message: str) -> Check:
    return check_goldens((Commit(sha=None, files=files, message=message),))


def test_a_change_touching_no_golden_passes() -> None:
    check = one(("src/gebra/ir/canonical.py",), "fix(ir): tidy [IR-05]")
    assert check.status == "PASS"
    assert check.findings == ()


def test_an_unjustified_golden_diff_is_blocked_with_the_guards_own_words() -> None:
    check = one((GOLDEN,), "fix(ir): retune [IR-05]")
    assert check.status == "BLOCK"
    (finding,) = check.findings
    assert GOLDEN in finding.summary
    assert golden_guard.TRAILER_KEY in finding.summary
    assert golden_guard.TRAILER_KEY in finding.remediation
    assert "golden_guard.py" in finding.remediation


def test_a_justified_golden_diff_passes_and_the_reviewed_half_is_still_named() -> None:
    check = one((GOLDEN,), JUSTIFIED)
    assert check.status == "PASS"
    assert any("stays with review" in note for note in check.notes)


def test_a_justified_commit_does_not_cover_an_unjustified_one() -> None:
    """The guard judges per commit; so does this, or a branch could launder a golden diff."""
    check = check_goldens(
        (
            Commit(sha="a" * 40, files=(GOLDEN,), message=JUSTIFIED),
            Commit(sha="b" * 40, files=(GOLDEN,), message="fix(ir): one more [IR-05]"),
        )
    )
    assert check.status == "BLOCK"
    (finding,) = check.findings
    assert finding.summary.startswith("bbbbbbbbbbbb")


@pytest.mark.parametrize(
    "files",
    [
        (),
        ("src/gebra/ir/canonical.py",),
        (GOLDEN,),
        ("tests/extraction/golden/parity.canonical.json", "CHANGELOG.md"),
        ("tests/version_drift/golden/langgraph-0.6.json",),
        ("tests/ir/golden/README.md",),
        ("tests/cli/goldens/report.txt",),
    ],
)
@pytest.mark.parametrize(
    "message",
    [
        "fix(ir): tidy [IR-05]",
        JUSTIFIED,
        "fix(ir): x [IR-05]\n\nGolden-Justification: drift-run=33394665484 langgraph 0.6/0.7",
        "fix(ir): x [IR-05]\n\nGolden-Justification: because I said so",
        "fix(ir): x [IR-05]\n\n    Golden-Justification: DEC-11 ir_version=1.2 indented",
    ],
)
def test_the_check_blocks_exactly_when_the_guard_reports_a_violation(
    files: tuple[str, ...], message: str
) -> None:
    """One verdict, reached once: this check has no rule of its own to drift from the job's."""
    expected = golden_guard.evaluate_commit(list(files), message) is not None
    assert (one(files, message).status == "BLOCK") is expected


def test_the_direct_mode_never_reaches_for_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """A review of a pasted file list runs where there may be no checkout at all."""

    def explode(*_: str) -> str:
        raise AssertionError("the direct mode must not run git")

    monkeypatch.setattr(golden_guard, "_git", explode)
    assert one((GOLDEN,), JUSTIFIED).status == "PASS"


def test_a_range_is_walked_through_the_guards_own_git_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(*arguments: str) -> str:
        calls.append(arguments)
        if arguments[0] == "rev-list":
            return "aaa\nbbb\n"
        if arguments[0] == "diff-tree":
            return f"{GOLDEN}\n" if arguments[-1] == "bbb" else "src/gebra/ir/canonical.py\n"
        return JUSTIFIED if arguments[-1] == "bbb" else "fix(ir): tidy [IR-05]"

    monkeypatch.setattr(golden_guard, "_git", fake_git)
    commits = commits_from_range("main", "HEAD")
    assert [commit.sha for commit in commits] == ["aaa", "bbb"]
    assert commits[1].files == (GOLDEN,)
    assert check_goldens(commits).status == "PASS"
    assert calls[0][0] == "rev-list"


def test_a_range_that_cannot_be_walked_reaches_no_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_git(*_: str) -> str:
        raise golden_guard.GoldenGuardError("git rev-list failed (exit 128): unknown revision")

    monkeypatch.setattr(golden_guard, "_git", fake_git)
    with pytest.raises(ChecklistInputError, match="unknown revision"):
        commits_from_range("nope", "HEAD")


# ── The GOV-03 release check ─────────────────────────────────────────────────────────────


def test_the_dry_run_over_this_tree_passes_as_cis_build_job_does() -> None:
    check = check_release(())
    assert check.status == "PASS"
    assert "dry-run" in check.detail
    assert "publish=false" in check.detail


def test_the_declared_version_is_reviewable_as_its_own_tag() -> None:
    check = check_release((), tag=f"v{release_gate.project_version(PYPROJECT)}")
    assert check.status == "PASS"
    assert check.subject.startswith("tools/release_gate.py (--tag v")


def test_a_tag_naming_another_version_is_blocked_with_the_gates_own_refusal() -> None:
    check = check_release((), tag="v0.0.1.dev9")
    assert check.status == "BLOCK"
    (finding,) = check.findings
    assert "pyproject.toml declares" in finding.summary
    assert "release_gate.py --tag v0.0.1.dev9" in finding.remediation
    assert "before tagging" in finding.remediation


def test_a_tag_outside_the_grammar_is_blocked() -> None:
    check = check_release((), tag="v0.0.1.post1")
    assert check.status == "BLOCK"
    assert "grammar" in check.findings[0].summary


def test_a_final_tag_without_its_dated_changelog_section_is_blocked(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "gebra"\nversion = "1.0.0"\n', encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n- pending\n", encoding="utf-8")
    check = check_release((), tag="v1.0.0", pyproject=pyproject, changelog=changelog)
    assert check.status == "BLOCK"
    assert "dated section" in check.findings[0].summary


def test_a_dry_run_refusal_names_the_job_that_will_repeat_it(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "gebra"\nversion = "1.0.0.post1"\n', encoding="utf-8")
    check = check_release((), pyproject=pyproject, changelog=CHANGELOG)
    assert check.status == "BLOCK"
    assert "build job" in check.findings[0].remediation
    assert "--dry-run" in check.findings[0].remediation


def test_an_unreadable_pyproject_reaches_no_verdict(tmp_path: Path) -> None:
    check = check_release((), pyproject=tmp_path / "absent.toml", changelog=CHANGELOG)
    assert check.status == "ERROR"


def test_editing_the_release_machinery_is_reported_as_outside_this_verdict() -> None:
    check = check_release((".github/workflows/release.yml", "CHANGELOG.md"))
    assert check.status == "PASS"
    assert any("test_release_wiring.py" in note for note in check.notes)
    assert check_release(("CHANGELOG.md",)).notes == ()


@pytest.mark.parametrize("tag", [None, "v0.0.1.dev0", "v0.0.1.dev9", "v0.0.1.post1", "0.0.1"])
def test_the_release_check_agrees_with_the_gate_it_relays(tag: str | None) -> None:
    """The gate decides; this check reports. They cannot disagree about one tree."""
    try:
        release_gate.run_gate(
            ref=None,
            tag=tag,
            dry_run=tag is None,
            pyproject=PYPROJECT,
            changelog=CHANGELOG,
            verify_dist_dir=None,
        )
    except release_gate.GateError:
        expected = "BLOCK"
    except release_gate.GateInputError:  # pragma: no cover - no such input in this matrix
        expected = "ERROR"
    else:
        expected = "PASS"
    assert check_release((), tag=tag).status == expected


# ── The report ───────────────────────────────────────────────────────────────────────────


def test_every_check_runs_even_when_an_earlier_one_refuses() -> None:
    """Collecting failures rather than stopping at the first is the checklist's whole shape."""
    report = NON_COMPLIANT_SAMPLE.reviewed()
    assert [check.status for check in report.checks] == ["BLOCK", "BLOCK", "BLOCK"]
    assert len(report.findings) == 3


def test_every_finding_carries_a_remediation_that_names_something_concrete() -> None:
    for finding in NON_COMPLIANT_SAMPLE.reviewed().findings:
        assert finding.remediation.strip()
        assert any(token in finding.remediation for token in (".md", ".py", "row", "trailer"))


def test_the_exit_status_separates_a_refusal_from_a_missing_verdict() -> None:
    passing = Report(checks=(Check(key="cla", subject="s", status="PASS", detail="d"),))
    blocking = Report(checks=(Check(key="cla", subject="s", status="BLOCK", detail="d"),))
    erroring = Report(checks=(Check(key="cla", subject="s", status="ERROR", detail="d"),))
    assert (passing.exit_status, passing.verdict) == (0, "MERGE-READY")
    assert (blocking.exit_status, blocking.verdict) == (1, "BLOCKED")
    assert (erroring.exit_status, erroring.verdict) == (2, "BLOCKED")


def test_the_text_report_prints_each_finding_beside_its_remediation() -> None:
    text = format_report(NON_COMPLIANT_SAMPLE.reviewed())
    assert text.splitlines()[0] == "pr-checklist: BLOCKED"
    assert text.count("remediation") == 3
    for key in ("cla", "goldens", "release"):
        assert f"  {key:<8} BLOCK" in text


def test_the_json_report_carries_the_same_verdicts_and_remediations() -> None:
    payload = json.loads(as_json(NON_COMPLIANT_SAMPLE.reviewed()))
    assert payload["verdict"] == "BLOCKED"
    assert payload["exit_status"] == 1
    assert [check["key"] for check in payload["checks"]] == ["cla", "goldens", "release"]
    for check in payload["checks"]:
        assert check["status"] == "BLOCK"
        assert check["findings"][0]["remediation"]


# ── The two sample pull requests (the card's acceptance) ─────────────────────────────────


def test_the_compliant_sample_reports_all_three_checks_green() -> None:
    report = COMPLIANT_SAMPLE.reviewed()
    assert [(check.key, check.status) for check in report.checks] == [
        ("cla", "PASS"),
        ("goldens", "PASS"),
        ("release", "PASS"),
    ]
    assert report.verdict == "MERGE-READY"
    assert report.exit_status == 0
    assert report.findings == ()


def test_the_non_compliant_sample_reports_the_three_failing_verdicts() -> None:
    report = NON_COMPLIANT_SAMPLE.reviewed()
    cla_check, goldens_check, release_check = report.checks
    assert "no row for @octocat" in cla_check.detail
    assert "without a well-formed justification" in goldens_check.detail
    assert "refused this tree" in release_check.detail
    assert report.verdict == "BLOCKED"
    assert report.exit_status == 1


def test_each_sample_names_files_this_repository_has_and_writes_to_none_of_them() -> None:
    """A sample is a list of paths, and every one is real — a sample that named a file this
    tree no longer has would demonstrate the checks against a fiction. None is opened."""
    digests = {}
    for sample in (COMPLIANT_SAMPLE, NON_COMPLIANT_SAMPLE):
        for path in sample.files:
            assert not Path(path).is_absolute()
            assert (REPO_ROOT / path).is_file(), path
            digests[path] = (REPO_ROOT / path).read_bytes()
    COMPLIANT_SAMPLE.reviewed()
    NON_COMPLIANT_SAMPLE.reviewed()
    for path, before in digests.items():
        assert (REPO_ROOT / path).read_bytes() == before


# ── The command line, observed as CI and the skill observe it ────────────────────────────


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_compliant_sample_exits_zero_from_the_command_line() -> None:
    completed = run(
        "--author",
        COMPLIANT_SAMPLE.author,
        "--files",
        *COMPLIANT_SAMPLE.files,
        "--message",
        COMPLIANT_SAMPLE.message,
        "--tag",
        COMPLIANT_SAMPLE.tag,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.startswith("pr-checklist: MERGE-READY")


def test_the_non_compliant_sample_exits_one_from_the_command_line() -> None:
    completed = run(
        "--author",
        NON_COMPLIANT_SAMPLE.author,
        "--files",
        *NON_COMPLIANT_SAMPLE.files,
        "--message",
        NON_COMPLIANT_SAMPLE.message,
        "--tag",
        NON_COMPLIANT_SAMPLE.tag,
        "--format",
        "json",
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert [check["status"] for check in payload["checks"]] == ["BLOCK", "BLOCK", "BLOCK"]


def test_the_two_modes_are_exclusive() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--author", "octocat"])
    assert caught.value.code == 2
    with pytest.raises(SystemExit):
        main(["--author", "octocat", "--files", "a.py", "--message", "m", "--base", "main"])


def test_a_range_that_cannot_be_walked_exits_two_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_git(*_: str) -> str:
        raise golden_guard.GoldenGuardError("git rev-list failed (exit 128)")

    monkeypatch.setattr(golden_guard, "_git", fake_git)
    assert main(["--author", "octocat", "--base", "main", "--head", "HEAD"]) == 2
    assert "error:" in capsys.readouterr().out


def test_the_help_offers_no_bypass_flag() -> None:
    completed = run("--help")
    assert completed.returncode == 0
    for flag in ("--skip", "--force", "--allow", "--ignore", "--no-cla"):
        assert flag not in completed.stdout


# ── WA-07, held by a sweep rather than by the module's own docstring ─────────────────────

#: What this module may import: the standard library it uses, plus the two tool modules whose
#: verdicts it relays. `subprocess` is legitimately reachable *through* `tools.golden_guard` —
#: that boundary is the one thing this module means to relay — and must not appear here, where
#: a second, unrelayed process boundary would be.
ALLOWED_IMPORTS = {
    "__future__",
    "argparse",
    "collections",
    "dataclasses",
    "json",
    "pathlib",
    "re",
    "sys",
    "tools",
    "typing",
}


def test_the_checklist_imports_the_two_modules_it_relays_and_otherwise_the_stdlib() -> None:
    """The docstring's WA-07 claim, held mechanically: nothing fails today, so sweep it.

    The sibling tools hold the same class of claim this way (`test_the_gate_imports_stdlib_only`,
    `test_the_router_reads_definitions_and_runs_nothing`). Reaching `gebra` is what would put
    this module inside the never-invokes surface at all, so its absence is the load-bearing
    assertion; the other three name the boundaries a review would otherwise have to re-read.
    """
    tree = ast.parse((REPO_ROOT / "tools" / "pr_checklist.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    from_tools: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None and node.level == 0
            imported.add(node.module.partition(".")[0])
            if node.module == "tools":
                from_tools.update(alias.name for alias in node.names)

    assert imported <= ALLOWED_IMPORTS
    assert from_tools == {"golden_guard", "release_gate"}
    for forbidden in ("gebra", "subprocess", "socket", "urllib"):
        assert forbidden not in imported, forbidden


def test_the_checklist_reads_records_and_runs_nothing_itself() -> None:
    """Past the docstring, which names the invariant, and past the one compile a matcher is."""
    source = (REPO_ROOT / "tools" / "pr_checklist.py").read_text(encoding="utf-8")
    body = source.split('"""', 2)[2].replace("re.compile(", "«pattern»(")

    for hazard in (".invoke(", ".stream(", ".batch(", ".compile(", "subprocess", "socket"):
        assert hazard not in body, hazard


# ── The skill this module backs ──────────────────────────────────────────────────────────


@requires_staged_skill
def test_the_skill_takes_its_three_verdicts_by_running_this_script() -> None:
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    assert "tools/pr_checklist.py" in skill
    assert "--author" in skill and "--files" in skill


@requires_staged_skill
def test_the_skill_restates_neither_the_trailer_forms_nor_the_tag_grammar() -> None:
    """A rule named in prose is a rule that can drift; the computed half has one home."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    for vocabulary in ("drift-run=", "DEC-<n>", "ir_version=", "X.Y.Z.devN", "vX.Y.Z"):
        assert vocabulary not in skill


@requires_staged_skill
def test_the_skill_keeps_the_half_no_script_reaches() -> None:
    skill = STAGED_SKILL.read_text(encoding="utf-8").lower()
    for obligation in ("conventional commit", "card", "board", "honest-claims"):
        assert obligation in skill


@requires_staged_skill
def test_the_skill_still_refuses_to_merge_or_to_waive() -> None:
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    assert "## NEVER" in skill
    assert "never merge" in skill.lower()


@requires_installed_skill
def test_the_installed_skill_is_the_staged_one() -> None:
    """Once installed, the two cannot drift — the pin is byte equality."""
    assert INSTALLED_SKILL.read_bytes() == STAGED_SKILL.read_bytes()
