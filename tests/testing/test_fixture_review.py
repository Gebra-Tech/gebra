"""The corpus lint's review scope, and the fixture-review skill that reads it (TOOL-03).

Reviewing a change to the fixture corpus asks a narrower question than gating the corpus:
not "is it clean" but "what does the gate say about the files this change touches". Before
this card, `/fixture-review` answered that from a checklist written in prose beside the lint,
which is two readings of one contract and one drift away from a skill passing what CI fails.
``--only`` makes it one reading, and this module pins that it stays one.

Three things are held here.

**A scoped run says exactly what the full run said about the fixtures it names.** The invariant
is set equality, not a summary verdict — ``scope_report`` filters the report :func:`check`
already produced, so for every fixture the scoped violations must be precisely the full run's
violations attributed to it, plus the corpus-wide ones that no file can own. It is asserted
over every fixture of the corpus under every seed of the lint's rule suite, which is why
:data:`~tests.testing.test_corpus_lint.SEEDS` is imported rather than re-invented: a rule the
scope started hiding would have to hide from all of them.

**The two acceptance demonstrations**, through the process rather than an in-process call: a
seeded nonconforming fixture, where the scoped command and the lint's own command return the
same status and name the same rule; and a conforming fixture of the vendored corpus, where
both are green. Every seed is applied to a *copy* — the corpus is a read-only vendored
contract surface (WA-04/WA-11), and one test watches its bytes across a scoped run.

**The skill and this lint stay one computation.** The staged skill must reach its conformance
verdict by running this script, must still carry the WA-04 routing evidence the lint cannot
compute, and must restate none of the lint's rule vocabulary — a rule named in prose is a rule
that can drift. Once the owner installs it (see the setup note), the installed file must be
the staged one byte for byte.

Nothing here executes a workflow node, calls a model, or opens a socket (WA-07). The one
subprocess runs this repository's own lint under this interpreter, which is the exact command
the skill and the CI job run.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.testing import SCHEMA_FILENAME, iter_fixture_paths
from tests.conftest import FIXTURES_DIR
from tests.testing.test_corpus_lint import GWF_POS, SEEDS, Mutation
from tools.corpus_lint import (
    CORPUS_FLOOR,
    DIRECTORY_MINIMUMS,
    RULES,
    CorpusLintError,
    CorpusReport,
    Violation,
    check,
    format_report,
    resolve_selection,
    scope_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "tools" / "corpus_lint.py"
SCHEMA = FIXTURES_DIR / SCHEMA_FILENAME

#: A fixture of the vendored corpus that conforms — acceptance 2's subject.
CONFORMING = "graph-well-formed/positive-01-linear-document-pipeline.yaml"

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI, where cross-repository assertions skip rather than fake (the pattern
# tests/test_provenance_guard.py established and tests/test_board_integrity.py follows).
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
#: The skill as staged for the owner to install — writable by the session that built it.
STAGED_SKILL = COMPANION / "docs" / "setups" / "TOOL-03" / "fixture-review-SKILL.md"
#: The installed skill, reached through the companion's neutral ``tools/`` surface so the
#: public tree pins it without naming an agent-tooling path (PD-050 hygiene, as for
#: ``tools/next-task.md`` and ``tools/plan-status.md``).
COMPANION_SKILL = COMPANION / "tools" / "fixture-review.md"
SETUP_NOTE = "docs/setups/TOOL-03.md in the development-process repository"

requires_staged_skill = pytest.mark.skipif(
    not STAGED_SKILL.is_file(),
    reason="the development-process repository is not checked out beside this one",
)
requires_installed_skill = pytest.mark.skipif(
    not COMPANION_SKILL.is_file(),
    reason=f"the upgraded skill is not installed yet — see {SETUP_NOTE}",
)


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def corpus_copy(tmp_path: Path) -> Path:
    """A working copy of the vendored corpus — the only corpus any seed is applied to."""
    root = tmp_path / "properties"
    shutil.copytree(FIXTURES_DIR, root)
    return root


def _check(root: Path) -> CorpusReport:
    return check(root, root / SCHEMA_FILENAME)


def _run_lint(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the lint exactly as the skill and CI do — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(LINT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _fixture_ids(root: Path) -> list[str]:
    """Every fixture under ``root``, in the identity the lint attributes violations to."""
    return [f"{path.parent.name}/{path.name}" for path in iter_fixture_paths(root)]


def _attributed(report: CorpusReport, fixture: str) -> list[Violation]:
    """What the full run said about one fixture, plus what no fixture can own."""
    return [
        violation
        for violation in report.violations
        if not violation.fixture or violation.fixture == fixture
    ]


def _drop_witness(path: Path) -> None:
    """Take ``expected.witness`` off a passing fixture — nonconforming, and obviously so."""
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    del document["expected"]["witness"]
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ── A scoped run says what the full run said ─────────────────────────────────────────────


def test_a_scoped_run_reports_exactly_what_the_full_run_says_about_that_fixture() -> None:
    """The vendored corpus: every fixture agrees, and agrees green."""
    full = _check(FIXTURES_DIR)
    assert full.ok, "the invariant is about agreement; a dirty corpus is a different test"
    for fixture in _fixture_ids(FIXTURES_DIR):
        scoped = scope_report(full, [fixture])
        assert scoped.violations == _attributed(full, fixture), fixture
        assert scoped.ok, fixture


@pytest.mark.parametrize(("rule", "mutation"), SEEDS, ids=[rule for rule, _ in SEEDS])
def test_the_scope_cannot_hide_a_violation_from_any_seeded_rule(
    corpus_copy: Path, rule: str, mutation: Mutation
) -> None:
    """Under every rule of the lint's closed vocabulary, scoped and full agree per fixture."""
    mutation(corpus_copy)
    full = _check(corpus_copy)
    assert not full.ok, f"the {rule} seed did not break the corpus"
    corpus_wide = [violation for violation in full.violations if not violation.fixture]

    for fixture in _fixture_ids(corpus_copy):
        scoped = scope_report(full, [fixture])
        assert scoped.violations == _attributed(full, fixture), f"{rule}: {fixture}"
        if not corpus_wide:
            attributed = any(violation.fixture == fixture for violation in full.violations)
            assert scoped.ok is not attributed, f"{rule}: {fixture}"


def test_a_corpus_wide_violation_is_in_scope_whatever_is_selected(corpus_copy: Path) -> None:
    """A deleted fixture leaves no file to attribute to; the minimums still have to hold."""
    (corpus_copy / GWF_POS).unlink()
    full = _check(corpus_copy)
    reported = {violation.rule for violation in full.violations}
    assert {"directory-minimum-unmet", "corpus-below-floor"} <= reported
    assert all(not violation.fixture for violation in full.violations)

    scoped = scope_report(full, [CONFORMING])
    assert not scoped.ok
    assert scoped.violations == full.violations


def test_a_scoped_report_still_reads_the_whole_corpus() -> None:
    """Narrowing the report never narrows the computation the corpus-wide rules need."""
    scoped = scope_report(_check(FIXTURES_DIR), [CONFORMING])
    assert scoped.fixtures_checked == CORPUS_FLOOR
    assert scoped.directories_checked == len(DIRECTORY_MINIMUMS)
    assert scoped.selected == (CONFORMING,)


def test_the_envelope_ledger_is_scoped_with_the_report() -> None:
    scoped = scope_report(_check(FIXTURES_DIR), [CONFORMING])
    assert [status.fixture for status in scoped.envelope] == [CONFORMING]


def test_a_scoped_review_never_writes_to_the_vendored_corpus() -> None:
    """WA-04/WA-11: the corpus is read-only, and a review over it is a reader."""
    before = _digest(FIXTURES_DIR)
    scope_report(check(FIXTURES_DIR, SCHEMA), [CONFORMING])
    assert _digest(FIXTURES_DIR) == before


# ── The two acceptance demonstrations, through the process ───────────────────────────────


def test_a_conforming_vendored_fixture_and_the_lint_agree_green() -> None:
    """TOOL-03 acceptance 2 — the vendored corpus, unmodified, through both commands."""
    direct = _run_lint()
    scoped = _run_lint("--only", CONFORMING)

    assert direct.returncode == 0, direct.stderr
    assert scoped.returncode == direct.returncode, scoped.stderr
    assert "corpus lint: OK" in direct.stdout
    assert "corpus lint: OK" in scoped.stdout
    assert CONFORMING in scoped.stdout


def test_a_seeded_nonconforming_fixture_gets_the_lints_own_verdict(corpus_copy: Path) -> None:
    """TOOL-03 acceptance 1 — same status, same rule, on a copy the corpus never sees."""
    _drop_witness(corpus_copy / GWF_POS)

    direct = _run_lint("--corpus", str(corpus_copy))
    scoped = _run_lint("--corpus", str(corpus_copy), "--only", GWF_POS)

    assert direct.returncode == 1
    assert scoped.returncode == direct.returncode
    assert "witness-missing-on-pass" in direct.stderr
    assert "witness-missing-on-pass" in scoped.stderr
    assert "corpus lint: FAILED" in scoped.stderr


def test_the_seeded_fixture_is_the_one_the_scope_fails_on(corpus_copy: Path) -> None:
    """The verdict is per fixture: its neighbours in the same directory stay green."""
    _drop_witness(corpus_copy / GWF_POS)

    failed = _run_lint("--corpus", str(corpus_copy), "--only", GWF_POS)
    neighbour = "graph-well-formed/negative-01-unreachable-escalation-node.yaml"
    passed = _run_lint("--corpus", str(corpus_copy), "--only", neighbour)

    assert failed.returncode == 1
    assert passed.returncode == 0, passed.stderr


# ── Resolving what a diff names ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "token",
    [
        CONFORMING,
        f"tests/fixtures/properties/{CONFORMING}",
        f"./tests/fixtures/properties/{CONFORMING}",
        str(FIXTURES_DIR / CONFORMING),
    ],
    ids=["corpus-relative", "repo-relative", "dot-prefixed", "absolute"],
)
def test_every_path_form_a_diff_produces_resolves(token: str) -> None:
    """`git diff --name-only` output pastes in unchanged, and so does an identity."""
    assert resolve_selection(FIXTURES_DIR, [token]) == (CONFORMING,)


def test_the_same_fixture_named_twice_is_selected_once() -> None:
    tokens = [CONFORMING, f"tests/fixtures/properties/{CONFORMING}"]
    assert resolve_selection(FIXTURES_DIR, tokens) == (CONFORMING,)


def test_a_token_naming_no_fixture_stops_the_run() -> None:
    """A scope that narrowed on a typo would report green over the fixture it meant to judge.

    The refusal also names the one legitimate reason a diff carries a path the corpus has not
    got — the change deletes it — and where its effect is judged instead.
    """
    with pytest.raises(CorpusLintError, match="no fixture 'mixed/99-not-a-fixture.yaml'") as raised:
        resolve_selection(FIXTURES_DIR, ["mixed/99-not-a-fixture.yaml"])
    assert "deletes has no fixture left to lint" in str(raised.value)


def test_the_schema_is_not_reviewable_inside_one_fixtures_scope() -> None:
    """It states the rules every fixture is read against, so the whole corpus is its scope."""
    with pytest.raises(CorpusLintError, match="lint the whole corpus, without --only"):
        resolve_selection(FIXTURES_DIR, [f"tests/fixtures/properties/{SCHEMA_FILENAME}"])


def test_a_bare_filename_is_refused() -> None:
    with pytest.raises(CorpusLintError, match="name the fixture's directory too"):
        resolve_selection(FIXTURES_DIR, ["positive-01-linear-document-pipeline.yaml"])


def test_the_cli_reports_an_unresolvable_scope_without_a_traceback() -> None:
    result = _run_lint("--only", "mixed/99-not-a-fixture.yaml")
    assert result.returncode == 1
    assert "no fixture" in result.stderr
    assert "Traceback" not in result.stderr


# ── What the report says it covers ───────────────────────────────────────────────────────


def test_the_scoped_headline_names_the_scope_it_was_reached_over() -> None:
    rendered = format_report(scope_report(_check(FIXTURES_DIR), [CONFORMING]))
    assert rendered.startswith(
        f"corpus lint: OK — review scope: 1 of {CORPUS_FLOOR} fixture(s), 0 violation(s) in scope"
    )
    assert f"  scope: {CONFORMING}" in rendered
    assert "corpus-wide rules" in rendered


def test_the_gates_own_headline_is_unchanged_by_the_review_scope() -> None:
    """The CI job's output is what it was; scoping is an addition, not a rewrite."""
    rendered = format_report(_check(FIXTURES_DIR))
    assert rendered.startswith(
        f"corpus lint: OK — {CORPUS_FLOOR} fixture(s) in {len(DIRECTORY_MINIMUMS)} "
        "director(y/ies), 0 violation(s)"
    )
    assert "review scope" not in rendered


def test_a_failing_scoped_report_still_names_the_remediation_route(corpus_copy: Path) -> None:
    """A violation must never read as an invitation to edit a fixture (WA-04)."""
    _drop_witness(corpus_copy / GWF_POS)
    rendered = format_report(scope_report(_check(corpus_copy), [GWF_POS]))
    assert "corpus lint: FAILED" in rendered
    assert "R-05 sign-off" in rendered


# ── The skill and this lint are one computation ──────────────────────────────────────────


@requires_staged_skill
def test_the_skill_computes_its_conformance_verdict_with_this_lint() -> None:
    """The card's objective: a front-end to the gate, not a second reading of it."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")

    assert "python tools/corpus_lint.py" in skill
    assert "--only" in skill


@requires_staged_skill
def test_the_skill_restates_none_of_the_lints_rule_vocabulary() -> None:
    """A rule named in prose is a rule that can drift from the one the gate applies."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    assert [rule for rule in RULES if rule in skill] == []


@requires_staged_skill
def test_the_skill_keeps_the_routing_evidence_the_lint_cannot_compute() -> None:
    """WA-04 is more than conformance: the vault sign-off is still a human reading."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")

    assert "R-05" in skill
    assert "vault hash" in skill
    assert "PROVENANCE.md" in skill


@requires_staged_skill
def test_the_skill_no_longer_claims_to_be_the_lint_itself() -> None:
    """The interim note this card retires — it stood while the checklist was the only check."""
    skill = STAGED_SKILL.read_text(encoding="utf-8")
    assert "this skill IS the corpus lint" not in skill
    assert "arrives with TOOL-03" not in skill


@requires_installed_skill
def test_the_installed_skill_is_the_staged_one() -> None:
    """Once installed, the two copies may not drift — the byte-compare is the pin."""
    assert COMPANION_SKILL.read_text(encoding="utf-8") == STAGED_SKILL.read_text(encoding="utf-8")
