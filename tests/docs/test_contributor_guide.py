"""``docs/contributing/index.md`` held to the rules it describes (DOC-19).

The contributor guide is the one page whose subject is the build's own process rather than the
package's behaviour, and process prose rots in a way that is hard to notice: a job gets renamed,
a guard grows a fourth failure class, a status leaves the vocabulary, and the page keeps reading
plausibly. So nothing on it is left as prose where the thing it describes can be read:

* the provenance guard's failure classes are read off ``Report``'s own fields, in both
  directions, and the guard's own message strings are what the page's transcript prints;
* the readiness rule, the status vocabulary and the claim commit are reconciled against the
  plan's §6 definition of each, where the development-process repository is checked out;
* the miniature board in the readiness example is proved to be in the format the *real* boards
  use — the page's own two patterns are extracted from its example and run over the real
  documentation board;
* the golden-file trailer's two forms are the two ``tools.golden_guard`` accepts, filled in and
  passed through its own validator;
* the CI job table, the job count and the four local gates are read off ``ci.yml`` and
  ``CONTRIBUTING.md``;
* the CLA route is the one ``CLA.md`` and the signature record actually describe;
* every repository file the page links to exists, and the banned-phrase lint runs over the page
  on every test run.

The walkthrough section describes this page's own card, so its facts are reconciled against that
card where the board is present: a stale prerequisite list fails here rather than in a reader's
understanding.

The module reads Markdown, YAML and Python source as text and imports three stdlib-only tooling
modules. From ``tools.golden_guard`` it takes ``GOLDEN_PATHS``, ``TRAILER_KEY`` and
``well_formed`` only: that module imports ``subprocess`` and defines ``_git``, but every call
site is inside a function this module does not import, and nothing at its import time runs one.
It builds no workflow, runs no node, executes no example and opens no connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
import yaml

from tools.golden_guard import GOLDEN_PATHS, TRAILER_KEY, golden_paths_touched, well_formed
from tools.honest_claims_lint import load_phrases, scan
from tools.provenance_guard import (
    FINDING_KINDS,
    MANIFEST,
    MISSING,
    MODIFIED,
    UNLISTED,
    Finding,
    build_parser,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "contributing" / "index.md"
CONTRIBUTING: Final = REPO_ROOT / "CONTRIBUTING.md"
CLA: Final = REPO_ROOT / "CLA.md"
SIGNATURES: Final = REPO_ROOT / "docs" / "governance" / "cla-signatures.md"
CI_WORKFLOW: Final = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PHRASES: Final = REPO_ROOT / "tools" / "honest-claims-phrases.txt"

#: The card this page is the output of, and the three cards its `prereqs` line names. The
#: walkthrough states both; the reconciliation below is that statement made mechanical.
CARD: Final = "DOC-19"
CARD_PREREQS: Final[tuple[str, ...]] = ("DOC-01", "GOV-09", "TOOL-01")

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked —
# the pattern tests/test_provenance_guard.py established.
COMPANION: Final = REPO_ROOT.parent / "gebra-dev-doc"
MASTER_PLAN: Final = COMPANION / "docs" / "plan" / "00-master-plan.md"
DOC_BOARD: Final = COMPANION / "docs" / "plan" / "boards" / "docs-tutorials.md"
BOARDS: Final = COMPANION / "docs" / "plan" / "boards"
# The companion exposes the skill at a neutral tools/ surface (a symlink there) so
# the public tree carries no agent-tooling path — the same arrangement the
# honest-claims phrase list uses (PD-050 hygiene).
NEXT_TASK_SKILL: Final = COMPANION / "tools" / "next-task.md"

requires_companion = pytest.mark.skipif(
    not BOARDS.is_dir(),
    reason="the development-process repository is not checked out beside this one",
)

requires_the_plan = pytest.mark.skipif(
    not MASTER_PLAN.is_file(),
    reason="the development-process repository is not checked out beside this one",
)

requires_the_skill = pytest.mark.skipif(
    not NEXT_TASK_SKILL.is_file(),
    reason="the development-process repository is not checked out beside this one",
)


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(page_text: str) -> str:
    """The page with every run of whitespace collapsed, for sentence-level assertions.

    A sentence this module pins may be re-wrapped without changing a word, and a check that
    broke on a line break would be a check on the paragraph shape rather than on the claim.
    Table, fence and heading assertions read ``page_text`` instead, where layout is content.
    """
    return re.sub(r"\s+", " ", page_text)


@pytest.fixture(scope="module")
def headings(page_text: str) -> list[str]:
    return re.findall(r"^#{2,3} (.+)$", page_text, flags=re.MULTILINE)


def _example(page_text: str, example_id: str) -> str:
    """The Python source of one marked example, exactly as the harness will run it."""
    match = re.search(
        rf"<!-- gebra:example id={example_id} -->\n```python\n(.*?)```",
        page_text,
        flags=re.DOTALL,
    )
    assert match is not None, f"no example {example_id!r} on the page"
    return match.group(1)


def _card_field(board: str, card: str, field: str) -> str:
    """One `- **field:** value` line of one card on one board."""
    section = re.search(rf"^### {card} —.*?(?=^### |\Z)", board, flags=re.MULTILINE | re.DOTALL)
    assert section is not None, f"{card} is not on this board"
    value = re.search(rf"^- \*\*{field}:\*\* (.+)$", section.group(0), flags=re.MULTILINE)
    assert value is not None, f"{card} has no {field} line"
    return value.group(1).strip()


def _card_statuses() -> dict[str, str]:
    """Every card on every board, as `{id: status}` — the boards' own format."""
    statuses: dict[str, str] = {}
    for board in sorted(BOARDS.glob("*.md")):
        card: str | None = None
        for line in board.read_text(encoding="utf-8").splitlines():
            heading = re.match(r"^### ([A-Z]+-[A-Z0-9]+) —", line)
            if heading is not None:
                card = heading.group(1)
                continue
            status = re.match(r"^- \*\*status:\*\* (\S+)", line)
            if status is not None and card is not None:
                statuses[card] = status.group(1)
                card = None
    return statuses


# ── The page itself, and the two counts its landing moved ────────────────────────────────


def test_the_page_is_documentation_rather_than_a_reservation(page_text: str) -> None:
    assert not page_text.startswith("<!--")
    assert "Reserved for:" not in page_text


def _nav_pages(entries: list[object]) -> list[str]:
    """Every page path in `mkdocs.yml`'s `nav:` tree, in navigation order."""
    pages: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            pages.append(entry)
        elif isinstance(entry, dict):
            for value in entry.values():
                if isinstance(value, str):
                    pages.append(value)
                elif isinstance(value, list):
                    pages += _nav_pages(value)
    return pages


@pytest.fixture(scope="module")
def site_pages() -> list[str]:
    nav = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
    assert isinstance(nav, list)
    return _nav_pages(nav)


def test_the_readme_counts_the_pages_the_navigation_lists(site_pages: list[str]) -> None:
    """This card wrote the last reserved page, so the README stopped saying "the rest is a
    skeleton" and started giving a total instead. A total is a number that can go stale, and it
    appears twice — the status row's note and the documentation list's lead — so both are held
    to the navigation's own count here rather than to each other.
    """
    assert len(site_pages) == 20

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count("twenty pages") == 2

    # And the two sentences that replaced the skeleton wording are held to the tree rather
    # than to each other: a page reserved later carries the marker again, and both fail.
    placeholders = [
        page.name
        for page in (REPO_ROOT / "docs").rglob("*.md")
        if page.read_text(encoding="utf-8").startswith("<!-- docs:placeholder")
    ]
    assert placeholders == []
    assert "no placeholder is left" in readme
    assert "no reserved placeholder is left in it." in readme


def test_the_home_page_lists_every_page_the_site_has(site_pages: list[str]) -> None:
    """`docs/index.md` says these are the pages; the claim is completeness, so it is counted."""
    home = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    listing = home[
        home.index("The pages, in the order they were written:") : home.index(
            "## How the site is arranged"
        )
    ]

    assert len(re.findall(r"^- ", listing, flags=re.MULTILINE)) == len(site_pages)
    assert "contributing/index.md" in listing


#: The six topics the card names, each with the heading that owns it and a phrase that
#: distinguishes covering the topic from mentioning it. A topic dropped to a passing reference
#: fails here, which is what the card's second acceptance box asks.
REQUIRED_TOPICS: Final[tuple[tuple[str, str, str], ...]] = (
    ("CLA", "1. Sign the CLA", "docs/governance/cla-signatures.md"),
    (
        "boards and the dependency gate",
        "3. Find a card: the boards and the dependency gate",
        "every prerequisite **gate** it names has been signed",
    ),
    ("provenance rules", "4. What you may not edit: vendored files", "tools/provenance_guard.py"),
    (
        "the spec-defect protocol",
        "5. When a frozen document cannot be implemented",
        "Do not improvise the semantics",
    ),
    (
        "the fixture-revision flow",
        "6. The fixture corpus, and how a fixture changes",
        "vault-side fixture-review sign-off",
    ),
    ("conventional commits", "7. Commit messages", "Conventional Commits"),
)


@pytest.mark.parametrize(("topic", "heading", "phrase"), REQUIRED_TOPICS, ids=lambda item: item[0])
def test_every_topic_the_card_names_has_a_section(
    topic: str, heading: str, phrase: str, page_text: str, headings: list[str]
) -> None:
    assert heading in headings, topic
    assert phrase in page_text, f"{topic}: the section does not cover it"


def test_the_page_links_only_to_repository_files_that_exist(page_text: str) -> None:
    """Every `blob/main/<path>` link the page carries names a file that is really there."""
    targets = re.findall(r"https://github\.com/Gebra-Tech/gebra/blob/main/([^)\s]+)", page_text)

    assert targets, "the page links to no repository file"
    assert [target for target in targets if not (REPO_ROOT / target).exists()] == []


def test_the_page_carries_no_banned_phrase() -> None:
    """WA-06, run here as well as in CI, so the page cannot drift between lint runs."""
    report = scan(REPO_ROOT, load_phrases(PHRASES), include=("docs/contributing/index.md",))

    assert report.violations == []


def test_the_pages_allow_pragma_example_is_a_live_one() -> None:
    """The page shows a pragma exempting a quoted phrase; it is the lint that exempts it.

    A worked example nothing enforces is decoration one edit away from being wrong. This
    holds that the demonstrated line really does carry a phrase the list rejects, and that
    the report which came back clean above is clean *because* the pragma covers it.
    """
    phrases = load_phrases(PHRASES)
    report = scan(REPO_ROOT, phrases, include=("docs/contributing/index.md",))
    lines = PAGE.read_text(encoding="utf-8").splitlines()

    quoted = [
        exemption.line_no
        for exemption in report.exemptions
        if any(phrase in lines[exemption.line_no - 1].lower() for phrase in phrases)
    ]

    assert quoted, "the page's pragma example exempts no line the list would reject"
    assert report.violations == []


# ── Section 3: the dependency gate ───────────────────────────────────────────────────────

#: The stored statuses the page lists as "not a candidate at all", plus the one it calls
#: claimable. Together these are the plan's whole status vocabulary; the reconciliation below
#: holds that claim rather than trusting it.
PAGE_STATUSES: Final[tuple[str, ...]] = (
    "todo",
    "in-progress",
    "in-review",
    "on-hold",
    "done",
    "dropped",
    "superseded",
)


def test_the_page_names_the_whole_status_vocabulary(page_text: str) -> None:
    assert [status for status in PAGE_STATUSES if f"`{status}`" not in page_text] == []


@requires_the_plan
def test_the_status_vocabulary_is_the_plans_own() -> None:
    """A status added to or removed from §6 must not leave the page listing the old set."""
    plan = MASTER_PLAN.read_text(encoding="utf-8")
    declared = re.search(r"\*\*Status vocabulary \(stored\):\*\* `([^`]+)`", plan)

    assert declared is not None, "§6 no longer declares the status vocabulary in that form"
    assert tuple(part.strip() for part in declared.group(1).split("|")) == PAGE_STATUSES


@requires_the_plan
def test_the_readiness_rule_is_the_plans_own(prose: str) -> None:
    """The three conditions, and that they are conjunctive — §6's definition, not a reading."""
    plan = re.sub(r"\s+", " ", MASTER_PLAN.read_text(encoding="utf-8"))

    assert "READY = `todo` ∧ all prereq cards `done` ∧ all prereq gates signed" in plan
    assert "its own status is `todo`;" in prose
    assert "every prerequisite **card** it names has status `done`;" in prose
    assert "every prerequisite **gate** it names has been signed." in prose
    assert "when three things hold at once" in prose


@requires_the_plan
def test_the_page_does_not_present_readiness_as_something_stored(prose: str) -> None:
    """§6: READY is derived, never stored. A page that implied otherwise would teach a bug."""
    plan = re.sub(r"\s+", " ", MASTER_PLAN.read_text(encoding="utf-8"))

    assert "**Derived (never stored):** READY" in plan
    assert "READY is never stored anywhere." in prose


@requires_the_plan
def test_the_claim_commit_is_the_one_the_plan_prescribes(prose: str) -> None:
    plan = re.sub(r"\s+", " ", MASTER_PLAN.read_text(encoding="utf-8"))

    assert "`chore(plan): claim <ID>` commit" in plan
    assert "in a `chore(plan): claim <ID>` commit" in prose
    assert "first merged wins" in plan.lower()
    assert "First merged wins." in prose


@requires_the_skill
def test_the_refusal_the_page_describes_is_the_one_the_tooling_performs(prose: str) -> None:
    """`/next-task` names the blocking tokens rather than softening the verdict — its words."""
    skill = re.sub(r"\s+", " ", NEXT_TASK_SKILL.read_text(encoding="utf-8"))

    assert "Name every blocking token exactly" in skill
    assert 'do not soften "BLOCKED" to "almost ready"' in skill
    assert "refuses and names the blocking tokens with their current statuses" in prose


def test_the_readiness_example_covers_all_four_verdicts(page_text: str) -> None:
    """A demonstration that only ever prints READY would demonstrate half the rule."""
    output = re.search(
        r"<!-- gebra:output id=the-dependency-gate -->\n```text\n(.*?)```",
        page_text,
        flags=re.DOTALL,
    )
    assert output is not None
    lines = output.group(1).splitlines()

    assert [line for line in lines if "not a candidate" in line]
    assert len([line for line in lines if line.endswith(": READY")]) == 2
    blocked = [line for line in lines if "BLOCKED" in line]
    assert len(blocked) == 1
    # Both arms of the rule, in one refusal: an unfinished card and an unsigned gate.
    assert "(todo)" in blocked[0] and "(open)" in blocked[0]


@requires_companion
def test_the_miniature_board_is_in_the_format_the_real_boards_use(page_text: str) -> None:
    """The example's own two patterns, run over a real board.

    This is what stops the miniature from being a format only this page believes in: the
    heading and field patterns are lifted out of the example's source and applied to the
    documentation board, which must yield real cards — this page's own among them — with the
    two fields the rule reads.
    """
    patterns = re.findall(
        r're\.match\(r"([^"]+)", line\)', _example(page_text, "the-dependency-gate")
    )
    assert len(patterns) == 2, patterns
    heading_pattern, field_pattern = patterns

    board = DOC_BOARD.read_text(encoding="utf-8")
    cards: dict[str, dict[str, str]] = {}
    current = ""
    for line in board.splitlines():
        heading = re.match(heading_pattern, line)
        if heading is not None:
            current = heading.group(1)
            cards[current] = {}
        field = re.match(field_pattern, line)
        if field is not None and current:
            cards[current][field.group(1)] = field.group(2)

    assert len(cards) > 10, "the page's heading pattern read almost nothing off a real board"
    assert CARD in cards
    assert set(cards[CARD]) == {"status", "prereqs"}


# ── Section 4: the provenance guard ──────────────────────────────────────────────────────


def test_the_page_names_every_failure_class_the_guard_reports(prose: str) -> None:
    """Both directions against the guard's own kind vocabulary: a fifth cannot land unmentioned."""
    assert set(FINDING_KINDS) == {MODIFIED, MISSING, UNLISTED, MANIFEST}
    for name in (MODIFIED, MISSING, UNLISTED):
        assert f"**{name}**" in prose, name
    assert "**manifest drift**" in prose
    assert "fails on four distinct things" in prose


def test_the_page_says_which_three_the_bare_command_runs() -> None:
    """The fourth class needs a flag, and the page may not imply otherwise.

    `verify()` computes `provenance_mismatch` only when handed a provenance document, the flag
    for it defaults to `None`, and the command this repository's CI runs passes no flag — so a
    page that listed four classes and then showed the bare command would be describing a check
    the reader cannot run. Read off the parser and the workflow rather than trusted.
    """
    parser = build_parser(REPO_ROOT, REPO_ROOT / "tools" / "provenance-manifest.json")
    (option,) = [
        action for action in parser._actions if "--provenance-doc" in action.option_strings
    ]
    assert option.default is None

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "python tools/provenance_guard.py\n" in workflow
    assert "--provenance-doc" not in workflow

    prose = re.sub(r"\s+", " ", PAGE.read_text(encoding="utf-8"))
    assert "only when it is handed the provenance table to compare against" in prose
    assert "The bare command below runs the first three." in prose
    # And the reason nothing is unguarded by that split, which the page also states.
    assert "the **unlisted** check finds it" in prose


def test_the_guards_transcript_is_the_guards_own_wording(page_text: str) -> None:
    """The three diagnostic lines the page shows are the strings `format_report` builds."""
    output = re.search(
        r"<!-- gebra:output id=the-provenance-guard -->\n```text\n(.*?)```",
        page_text,
        flags=re.DOTALL,
    )
    assert output is not None
    printed = output.group(1)

    source = (REPO_ROOT / "tools" / "provenance_guard.py").read_text(encoding="utf-8")
    for kind, detail in (
        (MODIFIED, "bytes differ from the recorded snapshot"),
        (MISSING, "listed in the manifest, absent from the tree"),
        (UNLISTED, "inside a guarded tree, absent from the manifest"),
    ):
        assert detail in source
        # The separator is the report's, not the page's: build the line the way the guard does.
        assert Finding(kind, "any/path", detail).line == f"any/path — {detail}"
        assert f"— {detail}" in printed


def test_the_guarded_tree_the_page_names_is_the_one_this_repository_guards(prose: str) -> None:
    """`tests/fixtures/properties/` is the library repo's whole share of the vendored surface."""
    manifest = (REPO_ROOT / "tools" / "provenance-manifest.json").read_text(encoding="utf-8")

    assert '"guarded_trees": [\n    "tests/fixtures/properties"\n  ]' in manifest
    assert "`tests/fixtures/properties/`" in prose
    assert "There is no bypass flag" in prose


def test_the_re_vendor_route_is_the_documented_one(prose: str) -> None:
    """One commit, vault-first, citing the new hash — the same four facts re-vendoring.md holds."""
    route = re.sub(r"\s+", " ", (REPO_ROOT / "docs" / "governance" / "re-vendoring.md").read_text())

    assert "A vendored file changes **vault-first**, never here." in route
    assert "The sanctioned way for a vendored file to change** is vault-first" in prose
    assert "the commit message cites the new vault commit hash" in route
    assert "in **one** commit citing the new vault hash" in prose


# ── Section 6: the fixture corpus ────────────────────────────────────────────────────────


def test_what_the_page_says_a_fixture_is_matches_the_corpus_own_account(prose: str) -> None:
    """The corpus README is emphatic about this and the page must not soften it.

    Read-only is a rule about writing, not about reading: the corpus's own header is the right
    source for what a fixture *is*, and pinning to it is what stopped an earlier draft's
    "serialized workflow documents" — a fourth noun for the thing — from surviving.
    """
    corpus = re.sub(
        r"\s+", " ", (REPO_ROOT / "tests" / "fixtures" / "properties" / "README.md").read_text()
    )

    assert "Fixtures carry **serialized Gebra IR**, never live LangGraph Python" in corpus
    assert "a set of serialized IR documents" in prose
    assert "never live LangGraph Python" in prose


def test_the_fidelity_matrix_the_page_sends_a_mismatch_to_exists(prose: str) -> None:
    matrix = REPO_ROOT / "docs" / "governance" / "FIDELITY-MATRIX.md"

    assert matrix.is_file()
    assert "logged in the fidelity matrix" in prose


def test_the_corpus_tool_really_refuses_to_write_inside_the_corpus(prose: str) -> None:
    """The one property the page promises about `corpus_reconcile.py`, read off the tool."""
    tool = (REPO_ROOT / "tools" / "corpus_reconcile.py").read_text(encoding="utf-8")

    assert "tests/fixtures/properties" in tool
    assert "refuses to write inside the corpus directory at all" in prose
    assert "refuse" in tool


# ── Section 7: commit messages ───────────────────────────────────────────────────────────


def test_the_commit_examples_carry_their_card(page_text: str) -> None:
    """Every card-scoped example on the page is `type(scope): subject [CARD-ID]`."""
    shown = re.findall(r"^([a-z]+\([a-z]+\): .+ \[[A-Z]+-\d+\])$", page_text, flags=re.MULTILINE)

    assert len(shown) == 3, shown
    assert f"docs(contributing): contributor guide [{CARD}]" in shown


def test_the_conventional_commit_types_are_the_ones_contributing_declares(page_text: str) -> None:
    declared = re.search(
        r"`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`",
        CONTRIBUTING.read_text(encoding="utf-8"),
    )
    assert declared is not None, "CONTRIBUTING.md no longer lists the types in that form"

    for kind in ("feat", "fix", "docs", "test", "refactor", "chore", "ci"):
        assert f"`{kind}`" in page_text, kind


def test_the_two_trailer_forms_are_the_two_the_guard_accepts(page_text: str, prose: str) -> None:
    """Filled in and passed through `golden_guard.well_formed` — not merely transcribed."""
    assert TRAILER_KEY in page_text
    assert f"{TRAILER_KEY} drift-run=<Actions run id> <substrate pair>" in page_text
    assert f"{TRAILER_KEY} DEC-<n> ir_version=<x.y> <what changed>" in page_text

    assert well_formed("drift-run=33336160085 langgraph 1.2 / langchain-core 1.1")
    assert well_formed("DEC-28 ir_version=1.1 the dynamic edge kind")
    # Two forms and no third: a trailer naming neither is what the guard refuses, which is
    # why the page says "exactly two" rather than "such as".
    assert not well_formed("because the goldens needed updating")
    assert "in one of exactly two forms" in prose


def test_the_page_counts_the_golden_trees_the_guard_watches(prose: str) -> None:
    assert len(GOLDEN_PATHS) == 3
    assert "Three test trees pin extracted bytes and digests as golden files." in prose


def test_the_markdown_carve_out_the_page_states_is_the_guards_own(prose: str) -> None:
    """ "A commit that touches one of them" would over-state it: a README there is not a golden.

    Fired against `golden_paths_touched` in both directions, inside the same golden tree, so
    the carve-out is read off the classifier rather than off `CONTRIBUTING.md`'s account of it.
    """
    tree = GOLDEN_PATHS[0]

    assert golden_paths_touched([f"{tree}/vector-001.json"]) == [f"{tree}/vector-001.json"]
    assert golden_paths_touched([f"{tree}/README.md"]) == []

    assert "documentation inside a golden tree is not a golden" in prose
    assert "the guard classifies only non-Markdown files" in prose


def test_the_squash_merge_caveat_is_the_guards_own(prose: str) -> None:
    contributing = re.sub(r"\s+", " ", CONTRIBUTING.read_text(encoding="utf-8"))

    assert "the squashed commit message is what the guard judges" in contributing
    assert "the squashed message is the one the guard judges" in prose


# ── Sections 2 and 8: what runs ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow() -> dict[str, object]:
    parsed = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


#: The jobs the page's table names, with the row's first cell. Every one must be a job the
#: workflow declares; the count below is the other half of the same claim.
NAMED_JOBS: Final[tuple[str, ...]] = (
    "provenance",
    "honest-claims",
    "golden-guard",
    "corpus-lint",
    "docs",
    "test-matrix",
)


def test_every_job_the_page_names_is_a_job_the_workflow_declares(
    workflow: dict[str, object], page_text: str
) -> None:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)

    for job in NAMED_JOBS:
        assert job in jobs, job
        assert f"| `{job}` |" in page_text, job


def test_the_job_count_on_the_page_is_the_workflows_own(
    workflow: dict[str, object], prose: str
) -> None:
    """The word on the page is a count, not a hedge — a job added or removed moves it."""
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert len(jobs) == 18

    assert "CI runs **eighteen jobs**" in prose
    assert "Eighteen CI jobs, on every push and every pull request." in prose


def test_the_four_local_gates_are_the_four_contributing_declares(page_text: str) -> None:
    """The commands are copied from one place: a divergence between the two files fails here."""
    contributing = CONTRIBUTING.read_text(encoding="utf-8")

    for command in (
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy",
        "uv run pytest",
    ):
        assert command in page_text, command
        assert command in contributing, command


def test_the_matrix_size_agrees_with_contributing(prose: str) -> None:
    contributing = re.sub(r"\s+", " ", CONTRIBUTING.read_text(encoding="utf-8"))

    assert "twelve blocking cells" in contributing
    assert "twelve tested Python and substrate pairings" in prose


def test_the_review_path_is_the_one_codeowners_encodes(prose: str) -> None:
    owners = (REPO_ROOT / "CODEOWNERS").read_text(encoding="utf-8")

    assert owners.strip() == "* @hesam-shams"
    assert "needs the code owner's review, and the maintainer is the one who merges" in prose


def test_the_lint_command_the_page_shows_is_a_command_ci_runs(page_text: str) -> None:
    workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")

    for command in ("python tools/provenance_guard.py", "python tools/honest_claims_lint.py"):
        assert command in page_text, command
        assert command in workflow_text, command


# ── Section 1: the CLA ───────────────────────────────────────────────────────────────────


def test_the_cla_route_the_page_gives_is_the_one_cla_md_describes(prose: str) -> None:
    cla = re.sub(r"\s+", " ", CLA.read_text(encoding="utf-8"))

    assert "gebra.dev@gmail.com" in cla
    assert "`gebra.dev@gmail.com`" in prose
    assert "The CLA process is **manual for now**." in cla
    assert "The process is manual today." in prose
    assert "deferred to the 1.0 launch" in cla
    assert "deferred to the 1.0 launch" in prose


def test_the_signature_record_is_where_the_page_says_it_is(prose: str) -> None:
    record = re.sub(r"\s+", " ", SIGNATURES.read_text(encoding="utf-8"))

    assert SIGNATURES.is_file()
    assert "`docs/governance/cla-signatures.md`" in prose
    assert "Rows are append-only." in record
    assert "Rows are append-only." in prose


def test_the_employer_clause_the_page_cites_is_section_4(prose: str) -> None:
    cla = re.sub(r"\s+", " ", CLA.read_text(encoding="utf-8"))

    assert "section 4 applies" in cla
    assert "section 4 of the CLA applies" in prose


# ── The walkthrough, against the card it walks ───────────────────────────────────────────


@requires_companion
def test_the_walkthrough_names_this_pages_own_card(prose: str) -> None:
    board = DOC_BOARD.read_text(encoding="utf-8")

    assert f"`{CARD} — Contributor guide`" in prose
    assert _card_field(board, CARD, "estimate") == "M"
    assert "estimate `M`" in prose


@requires_companion
def test_the_prerequisites_the_walkthrough_lists_are_the_cards_own(prose: str) -> None:
    """A prerequisite added to or dropped from the card must not leave the paragraph standing."""
    board = DOC_BOARD.read_text(encoding="utf-8")
    declared = tuple(token.strip() for token in _card_field(board, CARD, "prereqs").split(","))

    assert declared == CARD_PREREQS
    for token in CARD_PREREQS:
        assert f"`{token}`" in prose, token


@requires_companion
def test_no_prerequisite_of_this_card_is_a_gate(prose: str) -> None:
    """The walkthrough says no gate token appears in the list; that is checked, not assumed."""
    assert [token for token in CARD_PREREQS if re.fullmatch(r"G\d", token)] == []
    assert "no gate token appeared in the list" in prose


@requires_companion
def test_every_prerequisite_was_done_which_is_what_made_the_card_claimable(prose: str) -> None:
    statuses = _card_statuses()

    assert [token for token in CARD_PREREQS if statuses[token] != "done"] == []
    assert "All three were `done`" in prose


@requires_companion
def test_the_card_is_finished_and_finished_is_terminal(prose: str) -> None:
    """`done` is terminal (§6), which is what the walkthrough's last paragraph tells a reader."""
    board = DOC_BOARD.read_text(encoding="utf-8")

    assert _card_field(board, CARD, "status") == "done"
    assert "a defect in this page is a new card, not a reopening of this one" in prose
