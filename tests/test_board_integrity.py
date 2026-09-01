"""Behaviour tests for the board-integrity check (TOOL-02; master plan §6/§7).

Two halves, matching the tool's own split:

* the **judgement** — parsing, every §6/§7 rule, the stale arithmetic and the transition
  diagram — tested on miniature plans written to disk in the boards' own format, and on the
  real boards where the development-process repository is checked out beside this one:
  clean as merged, and failing on a seeded dangling prerequisite, a seeded cycle and a seeded
  stale claim, each applied to a copy so the boards themselves are untouched;
* the **plumbing** — the CLI and its exit statuses, the GitHub annotations, and the
  git-backed range walk and activity lookup — tested against a faked ``_git`` boundary, plus
  the cross-repository pins on the companion's copy of the script, its workflow and the skill.

WA-07: nothing here spawns git — the boundary is replaced wholesale, and an autouse fixture arms
``subprocess.Popen`` to fail for every test in the module, so any process a future change tried
to spawn would fail the test that spawned it. The one exemption runs the script itself under
this interpreter, which is the exact command the CI job runs.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import board_integrity as bi
from tools.board_integrity import (
    BoardIntegrityError,
    Finding,
    Plan,
    activity_from_git,
    check_plan,
    check_range,
    check_transitions,
    commits_in_range,
    expand_exit_cell,
    find_cycles,
    load_plan,
    main,
    working_days_after,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "board_integrity.py"

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked —
# the pattern tests/test_provenance_guard.py established.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
COMPANION_PLAN = COMPANION / "docs" / "plan"
COMPANION_SCRIPT = COMPANION / "tools" / "board_integrity.py"
COMPANION_WORKFLOW = COMPANION / ".github" / "workflows" / "board-integrity.yml"
# The companion exposes the skill at a neutral tools/ surface (a symlink there) so the
# public tree carries no agent-tooling path — the arrangement tests/docs/test_contributor_guide.py
# uses for the next-task skill (PD-050 hygiene).
COMPANION_SKILL = COMPANION / "tools" / "plan-status.md"
SETUP_NOTE = "docs/setups/TOOL-02.md in the development-process repository"

requires_companion = pytest.mark.skipif(
    not (COMPANION_PLAN / "00-master-plan.md").is_file(),
    reason="the development-process repository is not checked out beside this one",
)
requires_companion_copy = pytest.mark.skipif(
    not COMPANION_SCRIPT.is_file(),
    reason=f"the companion's copy of the script is not installed — see {SETUP_NOTE}",
)
requires_companion_workflow = pytest.mark.skipif(
    not COMPANION_WORKFLOW.is_file(),
    reason=f"the companion's board-integrity workflow is not installed — see {SETUP_NOTE}",
)
requires_the_skill = pytest.mark.skipif(
    not COMPANION_SKILL.is_file(),
    reason=f"the companion's neutral tools/plan-status.md surface is absent — see {SETUP_NOTE}",
)

#: A Tuesday. Every stale-check expectation below is counted against it by hand.
TODAY = date(2026, 9, 1)
SIGNED = "signed 2026-01-01 — owner"

#: The one test allowed to spawn a process: it runs this script under the interpreter.
SPAWNS_THE_SCRIPT = "test_the_script_runs_as_a_plain_command"


@pytest.fixture(autouse=True)
def no_process_is_spawned(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """WA-07, module-wide: `run`, `check_output` and `call` all route through `Popen`."""
    if request.node.name == SPAWNS_THE_SCRIPT:
        return

    def armed(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"a subprocess was spawned: {args[0] if args else kwargs}")

    monkeypatch.setattr(subprocess, "Popen", armed)


# ── Miniature plans, in the boards' own format ──────────────────────────────────────────


@dataclass(frozen=True)
class MiniCard:
    id: str
    status: str = "todo"
    prereqs: str = "none"
    claimed_by: str = "—"
    estimate: str = "S"
    boxes: tuple[bool, ...] = (False,)
    artifacts: str = "—"
    section: str = "Cards"
    after_status: tuple[str, ...] = ()
    after_artifacts: tuple[str, ...] = ()
    title: str = "A miniature card"


@dataclass(frozen=True)
class MiniGate:
    id: str
    exit_cards: str = "none"
    status: str = "open"


def render_card(card: MiniCard) -> str:
    boxes = [
        f"  - [{'x' if checked else ' '}] acceptance item {number}"
        for number, checked in enumerate(card.boxes, 1)
    ]
    lines = [
        f"### {card.id} — {card.title}",
        f"- **status:** {card.status}",
        *card.after_status,
        f"- **claimed_by:** {card.claimed_by}",
        f"- **estimate:** {card.estimate}",
        f"- **prereqs:** {card.prereqs}",
        "- **spec_refs:** master plan §6",
        "- **objective:** Something the miniature plan needs.",
        "- **acceptance:**",
        *boxes,
        "- **decisions_to_implementer:**",
        "  - none",
        f"- **artifacts:** {card.artifacts}",
        *card.after_artifacts,
        "",
    ]
    return "\n".join(lines)


def render_board(prefix: str, cards: Sequence[MiniCard]) -> str:
    head = [
        f"# Track {prefix} — task board",
        f"- **prefix:** {prefix}-",
        "- **charter:** a miniature board",
        "",
        "## Cards",
        "",
    ]
    open_cards = [render_card(card) for card in cards if card.section == "Cards"]
    done_cards = [render_card(card) for card in cards if card.section == "Done"]
    return "\n".join(head) + "\n" + "\n".join(open_cards) + "\n## Done\n\n" + "\n".join(done_cards)


def render_master(
    boards: Mapping[str, Sequence[MiniCard]],
    gates: Sequence[MiniGate],
    counts: Mapping[str, int] | None = None,
    totals: tuple[int, int] | None = None,
    totals_line: bool = True,
) -> str:
    rows = [
        f"| **{gate.id}** | Gate {gate.id} | {gate.exit_cards} | evidence | — | owner | "
        f"{gate.status} |"
        for gate in gates
    ]
    if counts is None:
        counts = {prefix: len(cards) for prefix, cards in boards.items()}
    if totals is None:
        totals = (
            sum(len(cards) for cards in boards.values()),
            sum(1 for cards in boards.values() for card in cards if "-D" in card.id),
        )
    index = [
        f"| [boards/{prefix.lower()}.md](boards/{prefix.lower()}.md) | `{prefix}-` | {count} | "
        "a miniature board |"
        for prefix, count in counts.items()
    ]
    parts = [
        "# Miniature master plan",
        "",
        "## 4. Milestones & gates",
        "",
        "| Gate | Name | Exit cards | Evidence checklist | SOW §2 | Sign-off | Status |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## 6. Plan maintenance protocol",
        "",
        (
            "**Status vocabulary (stored):** `todo | in-progress | in-review | on-hold | done | "
            "dropped | superseded`."
        ),
        "",
        "## 7. Board index & ID scheme",
        "",
    ]
    if totals_line:
        parts += [f"**{totals[0]} cards; {totals[1]} decision cards.**", ""]
    parts += [
        "| Board file | Prefix | Cards | Charter (one line) |",
        "|---|---|---|---|",
        *index,
        "",
    ]
    return "\n".join(parts)


def plan_files(
    boards: Mapping[str, Sequence[MiniCard]],
    gates: Sequence[MiniGate] = (MiniGate("G0"),),
    **master: Any,
) -> dict[str, str]:
    """The plan as repository-relative paths → texts (what a commit would record)."""
    files = {"docs/plan/00-master-plan.md": render_master(boards, gates, **master)}
    for prefix, cards in boards.items():
        files[f"docs/plan/boards/{prefix.lower()}.md"] = render_board(prefix, cards)
    return files


def build_plan(
    root: Path,
    boards: Mapping[str, Sequence[MiniCard]],
    gates: Sequence[MiniGate] = (MiniGate("G0"),),
    **master: Any,
) -> Path:
    """Write a miniature plan under ``root/docs/plan`` and return that plan root."""
    for path, text in plan_files(boards, gates, **master).items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root / "docs" / "plan"


CLEAN_BOARDS: dict[str, list[MiniCard]] = {
    "AA": [
        MiniCard("AA-01", "done", section="Done", boxes=(True, True), artifacts="the models"),
        MiniCard("AA-02", prereqs="AA-01"),
        MiniCard("AA-D1", "done", section="Done", boxes=(True,), artifacts="PD-001 (ratified)"),
    ],
    "BB": [MiniCard("BB-01", prereqs="AA-02, G0")],
}
CLEAN_GATES = (MiniGate("G0", "AA-01, AA-D1", SIGNED), MiniGate("G1", "AA-02, BB-01"))


@pytest.fixture
def clean_plan(tmp_path: Path) -> Path:
    return build_plan(tmp_path, CLEAN_BOARDS, CLEAN_GATES)


def findings_of(plan_root: Path, activity: Mapping[str, date] | None = None) -> list[Finding]:
    return check_plan(load_plan(plan_root), today=TODAY, activity=activity)


def errors_of(plan_root: Path) -> list[Finding]:
    return [finding for finding in findings_of(plan_root) if finding.severity == "ERROR"]


def messages(findings: Sequence[Finding]) -> list[str]:
    return [f"{finding.subject}: {finding.message}" for finding in findings]


def one_error(plan_root: Path, subject: str, fragment: str) -> Finding:
    """Exactly one ERROR, on ``subject``, whose message carries ``fragment``."""
    errors = errors_of(plan_root)
    assert len(errors) == 1, messages(errors)
    assert errors[0].subject == subject, messages(errors)
    assert fragment in errors[0].message, errors[0].message
    return errors[0]


# ── A well-formed plan ───────────────────────────────────────────────────────────────────


def test_a_well_formed_miniature_plan_is_clean(clean_plan: Path) -> None:
    assert findings_of(clean_plan) == []
    assert main(["--plan", str(clean_plan), "--today", "2026-09-01"]) == 0


def test_the_parser_reads_sections_fields_boxes_and_prereqs(clean_plan: Path) -> None:
    plan = load_plan(clean_plan)

    assert sorted(plan.cards) == ["AA-01", "AA-02", "AA-D1", "BB-01"]
    assert plan.boards == ["aa.md", "bb.md"]
    assert plan.board_prefixes == {"aa.md": "AA", "bb.md": "BB"}
    assert plan.cards["AA-01"].section == "Done"
    assert plan.cards["AA-02"].section == "Cards"
    assert plan.cards["AA-01"].acceptance == [
        (True, "acceptance item 1"),
        (True, "acceptance item 2"),
    ]
    assert plan.cards["BB-01"].prereq_tokens == ["AA-02", "G0"]
    assert plan.cards["BB-01"].prereq_cards == ["AA-02"]
    assert plan.cards["BB-01"].prereq_gates == ["G0"]
    assert plan.cards["AA-D1"].is_decision and not plan.cards["AA-01"].is_decision
    assert plan.index == {"aa.md": ("AA", 3), "bb.md": ("BB", 1)}
    assert plan.totals == (4, 1)
    assert plan.gates["G0"].signed and not plan.gates["G1"].signed
    assert plan.gates["G1"].exit_cards == ("AA-02", "BB-01")


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("AA-01, AA-02", ("AA-01", "AA-02")),
        ("EX-D1, EX-01…EX-03, EX-13", ("EX-01", "EX-02", "EX-03", "EX-13", "EX-D1")),
        ("GOV-04…08", ("GOV-04", "GOV-05", "GOV-06", "GOV-07", "GOV-08")),
        ("none", ()),
    ],
)
def test_exit_cells_expand_their_ellipsis_ranges(cell: str, expected: tuple[str, ...]) -> None:
    assert expand_exit_cell(cell) == expected


@pytest.mark.parametrize(
    ("cell", "signed"),
    [("open", False), ("", False), ("OPEN", False), (SIGNED, True), ("**signed** — HS", True)],
)
def test_a_gate_is_signed_iff_its_status_cell_is_not_open(cell: str, signed: bool) -> None:
    assert bi.Gate("G0", "Foundations", (), cell, 1).signed is signed


# ── Prerequisites: resolution and cycles ────────────────────────────────────────────────


def test_a_dangling_prereq_is_an_error_naming_the_token(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", prereqs="AA-01x, ZZ-99")]})

    errors = errors_of(plan_root)

    assert [error.subject for error in errors] == ["AA-01", "AA-01"]
    assert "prereq token 'AA-01x' is neither a card ID" in errors[0].message
    assert "prereq 'ZZ-99' does not resolve to any card (dangling)" in errors[1].message
    assert main(["--plan", str(plan_root), "--today", "2026-09-01"]) == 1


def test_a_prereq_gate_must_be_in_the_gate_table(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", prereqs="G7")]})

    one_error(plan_root, "AA-01", "prereq gate 'G7' is not in the master plan §4 gate table")


def test_none_stands_alone(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path, {"AA": [MiniCard("AA-01"), MiniCard("AA-02", prereqs="none, AA-01")]}
    )

    one_error(plan_root, "AA-02", "`none` mixed with other prereq tokens")


def test_an_empty_prereqs_field_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", prereqs="")]})

    one_error(plan_root, "AA-01", "prereqs is empty")


def test_a_card_may_not_require_itself(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", prereqs="AA-01")]})

    errors = errors_of(plan_root)
    assert any("lists itself as a prerequisite" in error.message for error in errors)


def test_a_dependency_cycle_is_reported_as_its_full_path(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard("AA-01", prereqs="AA-02"),
                MiniCard("AA-02", prereqs="AA-03"),
                MiniCard("AA-03", prereqs="AA-01"),
                MiniCard("AA-04", prereqs="AA-01"),
            ]
        },
    )

    error = one_error(plan_root, "AA-01", "dependency cycle: AA-01 -> AA-02 -> AA-03 -> AA-01")
    assert error.file == "aa.md"
    assert main(["--plan", str(plan_root), "--today", "2026-09-01"]) == 1


def test_a_two_card_cycle_is_reported_once() -> None:
    cycles = find_cycles({"A": ["B"], "B": ["A"], "C": ["A"], "D": ["ZZ"]})

    assert cycles == [["A", "B", "A"]]


def test_cycle_detection_ignores_unresolved_tokens_and_handles_long_chains() -> None:
    chain = {f"N{i}": [f"N{i + 1}"] for i in range(3000)}
    chain["N3000"] = ["missing"]

    assert find_cycles(chain) == []


# ── Identity: unique IDs, the §7 grammar, board prefixes ────────────────────────────────


def test_a_duplicate_id_across_boards_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")], "BB": [MiniCard("AA-01")]})

    errors = errors_of(plan_root)
    duplicate = [error for error in errors if "duplicate card ID" in error.message]
    assert len(duplicate) == 1
    assert duplicate[0].file == "bb.md" and "aa.md:" in duplicate[0].message


@pytest.mark.parametrize("card_id", ["AA-1", "AA-D", "aa-01", "AA01", "AA-01a"])
def test_an_id_outside_the_section_7_grammar_is_an_error(tmp_path: Path, card_id: str) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard(card_id)]})

    assert any(
        "card ID is not `<PREFIX>-<NN>` or `<PREFIX>-D<N>`" in error.message
        for error in errors_of(plan_root)
    )


def test_a_card_carries_its_boards_prefix(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("BB-01")]})

    assert any(
        "card prefix BB- on a board whose header declares AA-" in error.message
        for error in errors_of(plan_root)
    )


def test_a_card_heading_off_the_format_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")]})
    board = plan_root / "boards" / "aa.md"
    board.write_text(
        board.read_text(encoding="utf-8").replace("### AA-01 — ", "### AA-01 - "),
        encoding="utf-8",
    )

    errors = errors_of(plan_root)
    assert any("card heading is not `### <ID> — <Title>`" in error.message for error in errors)


def test_a_repeated_field_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path, {"AA": [MiniCard("AA-01", after_status=("- **status:** done",))]}
    )

    one_error(plan_root, "AA-01", "field `status` appears twice")


def test_a_missing_field_and_an_odd_estimate_are_errors(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", estimate="XL")]})
    board = plan_root / "boards" / "aa.md"
    board.write_text(
        board.read_text(encoding="utf-8").replace("- **spec_refs:** master plan §6\n", ""),
        encoding="utf-8",
    )

    found = messages(errors_of(plan_root))
    assert "AA-01: missing field(s): spec_refs" in found
    assert "AA-01: estimate 'XL' is not S, M or L (§7)" in found


# ── Statuses and claims ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("stored", ["READY", "BLOCKED", "pending", "Done"])
def test_only_the_seven_statuses_are_legal(tmp_path: Path, stored: str) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", stored)]})

    errors = errors_of(plan_root)
    assert len(errors) == 1, messages(errors)
    assert f"status {stored!r} is not one of todo, in-progress" in errors[0].message
    assert ("derived, never stored" in errors[0].message) is (stored in {"READY", "BLOCKED"})


@pytest.mark.parametrize("status", ["in-progress", "in-review"])
def test_a_claimed_status_needs_a_claim(tmp_path: Path, status: str) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", status)]})

    one_error(plan_root, "AA-01", f"{status} but claimed_by is empty")


def test_a_todo_card_carries_no_claim(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", claimed_by="ada (2026-08-01)")]})

    one_error(plan_root, "AA-01", "todo but claimed_by is 'ada (2026-08-01)'")


def test_a_note_under_a_one_line_field_does_not_join_its_value(tmp_path: Path) -> None:
    """The EX-06 shape: `released_from_hold` written directly under `status`."""
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard(
                    "AA-01",
                    "done",
                    section="Done",
                    boxes=(True,),
                    artifacts="the thing",
                    after_status=(
                        "- **released_from_hold:** 2026-08-03 — every disposition verified",
                        "  and ratified as built",
                    ),
                )
            ]
        },
    )

    assert findings_of(plan_root) == []
    assert load_plan(plan_root).cards["AA-01"].status == "done"


def test_an_html_comment_is_not_part_of_a_prereq_list(tmp_path: Path) -> None:
    """The SD-11 shape: an HTML comment on the prereq list's continuation line."""
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard("AA-01", "done", section="Done", boxes=(True,), artifacts="x"),
                MiniCard(
                    "AA-02",
                    prereqs="AA-01\n    <!-- prereqs completed 2026-08-31 to the card's own table -->",
                ),
            ]
        },
    )

    assert findings_of(plan_root) == []
    assert load_plan(plan_root).cards["AA-02"].prereq_tokens == ["AA-01"]


# ── `done`, `## Done`, `on-hold`, `superseded` ──────────────────────────────────────────


def done_card(**overrides: Any) -> MiniCard:
    base: dict[str, Any] = {
        "id": "AA-01",
        "status": "done",
        "section": "Done",
        "boxes": (True,),
        "artifacts": "the thing",
    }
    base.update(overrides)
    return MiniCard(**base)


def test_a_done_card_belongs_in_the_done_section(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [done_card(section="Cards")]})

    one_error(plan_root, "AA-01", "done but sits under `## Cards`")


def test_a_done_card_has_every_box_checked(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [done_card(boxes=(True, False, False))]})

    one_error(plan_root, "AA-01", "done with 2 unchecked acceptance box(es)")


def test_a_done_card_has_acceptance_boxes_at_all(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [done_card(boxes=())]})

    one_error(plan_root, "AA-01", "done but has no acceptance checkboxes")


@pytest.mark.parametrize("artifacts", ["—", "", "none"])
def test_a_done_card_has_its_artifacts_filled(tmp_path: Path, artifacts: str) -> None:
    plan_root = build_plan(tmp_path, {"AA": [done_card(artifacts=artifacts)]})

    one_error(plan_root, "AA-01", "done but artifacts is empty")


def test_evidence_maintenance_under_artifacts_counts_as_artifacts(tmp_path: Path) -> None:
    """The DOC-16 shape: a PD-008 confirming-run note written directly under `artifacts`."""
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                done_card(
                    artifacts="",
                    after_artifacts=(
                        "- **PD-008 confirming run (recorded 2026-09-01):** run 1 green",
                        "  - **The page.** docs/tutorials/the-page.md",
                    ),
                )
            ]
        },
    )

    assert findings_of(plan_root) == []
    assert "docs/tutorials/the-page.md" in load_plan(plan_root).cards["AA-01"].artifacts


@pytest.mark.parametrize("status", ["todo", "in-progress", "in-review", "on-hold"])
def test_a_live_card_does_not_sit_in_the_done_section(tmp_path: Path, status: str) -> None:
    card = MiniCard(
        "AA-01",
        status,
        section="Done",
        claimed_by="—" if status == "todo" else "ada (2026-09-01)",
        after_status=("- **hold_reason:** [PD-099](decisions/PD-099.md)",)
        if status == "on-hold"
        else (),
    )
    plan_root = build_plan(tmp_path, {"AA": [card]})

    one_error(plan_root, "AA-01", f"{status} card sits under `## Done`")


def test_a_terminal_card_may_sit_in_either_section(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard("AA-01", "dropped", section="Done"),
                MiniCard("AA-02", "dropped", section="Cards"),
            ]
        },
    )

    assert findings_of(plan_root) == []


def test_on_hold_needs_a_hold_reason(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path, {"AA": [MiniCard("AA-01", "on-hold", claimed_by="ada (2026-08-01)")]}
    )

    one_error(plan_root, "AA-01", "on-hold without a hold_reason")


def test_a_hold_reason_carries_a_link(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard(
                    "AA-01",
                    "on-hold",
                    claimed_by="ada (2026-08-01)",
                    after_status=("- **hold_reason:** waiting for someone to decide",),
                )
            ]
        },
    )

    one_error(plan_root, "AA-01", "hold_reason carries no link")


@pytest.mark.parametrize(
    "reason",
    [
        "[PD-099](../decisions/PD-099-something.md)",
        "spec defect https://github.com/Gebra-Tech/gebra/issues/7",
        "pending PD-099 (drafted 2026-08-01)",
        "issue #12",
        "spec defect filed —\n  [the write-up](../decisions/PD-099.md) on line two",
    ],
)
def test_a_linked_hold_reason_is_accepted(tmp_path: Path, reason: str) -> None:
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard(
                    "AA-01",
                    "on-hold",
                    claimed_by="ada (2026-08-01)",
                    after_status=(f"- **hold_reason:** {reason}",),
                )
            ]
        },
    )

    assert findings_of(plan_root) == []


def test_superseded_names_its_replacement(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01", "superseded"), MiniCard("AA-02")]})

    one_error(plan_root, "AA-01", "superseded without naming its replacement card")


@pytest.mark.parametrize(
    "card",
    [
        MiniCard("AA-01", "superseded", after_status=("- **superseded_by:** AA-02",)),
        MiniCard("AA-01", "superseded", artifacts="replaced by AA-02 at the 2026-08-09 review"),
    ],
)
def test_a_superseded_card_naming_a_real_replacement_is_accepted(
    tmp_path: Path, card: MiniCard
) -> None:
    plan_root = build_plan(tmp_path, {"AA": [card, MiniCard("AA-02")]})

    assert findings_of(plan_root) == []


def test_a_superseded_card_naming_a_missing_replacement_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {"AA": [MiniCard("AA-01", "superseded", after_status=("- **superseded_by:** AA-77",))]},
    )

    one_error(plan_root, "AA-01", "superseded without naming its replacement card")


# ── Stale claims ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 9, 1), date(2026, 9, 1), 0),
        (date(2026, 9, 1), date(2026, 8, 31), 0),
        (date(2026, 8, 28), date(2026, 8, 31), 1),  # Friday → Monday
        (date(2026, 8, 28), date(2026, 9, 4), 5),  # Friday → next Friday
        (date(2026, 8, 29), date(2026, 8, 30), 0),  # Saturday → Sunday
        (date(2026, 8, 24), date(2026, 9, 1), 6),
    ],
)
def test_working_days_are_weekdays_strictly_after_the_start(
    start: date, end: date, expected: int
) -> None:
    assert working_days_after(start, end) == expected


def in_progress(claimed: str) -> dict[str, list[MiniCard]]:
    return {"AA": [MiniCard("AA-01", "in-progress", claimed_by=f"ada ({claimed})")]}


@pytest.mark.parametrize(
    ("claimed", "stale"),
    [
        ("2026-09-01", False),
        ("2026-08-25", False),  # exactly five working days before the Tuesday
        ("2026-08-24", True),  # six
        ("2026-08-21", True),  # a Friday, seven working days back
    ],
)
def test_an_in_progress_claim_is_stale_after_five_working_days(
    tmp_path: Path, claimed: str, stale: bool
) -> None:
    plan_root = build_plan(tmp_path, in_progress(claimed))

    findings = findings_of(plan_root)

    if stale:
        assert len(findings) == 1 and findings[0].severity == "WARNING"
        assert findings[0].subject == "AA-01"
        assert f"stale: in-progress with no linked activity since {claimed}" in findings[0].message
        assert "release is preferred over squatting" in findings[0].message
    else:
        assert findings == []


def test_stale_is_a_warning_that_leaves_the_exit_status_at_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance box 3: a seeded in-progress card with no linked activity is flagged."""
    plan_root = build_plan(tmp_path, in_progress("2026-08-03"))

    assert main(["--plan", str(plan_root), "--today", "2026-09-01"]) == 0

    out = capsys.readouterr().out
    assert "WARNING  aa.md                AA-01     stale: in-progress" in out
    assert "board integrity: clean with 1 warning(s) — 1 cards, 1 gates, 1 boards" in out


def test_linked_activity_resets_the_stale_clock(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, in_progress("2026-08-03"))

    assert findings_of(plan_root, activity={"AA-01": date(2026, 8, 28)}) == []
    assert len(findings_of(plan_root, activity={"AA-01": date(2026, 8, 21)})) == 1
    # Activity older than the claim never moves the clock backwards.
    assert len(findings_of(plan_root, activity={"AA-01": date(2026, 7, 1)})) == 1


def test_a_claim_without_a_date_cannot_be_judged_and_says_so(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path, {"AA": [MiniCard("AA-01", "in-progress", claimed_by="ada, last week")]}
    )

    findings = findings_of(plan_root)
    assert [finding.severity for finding in findings] == ["WARNING"]
    assert "carries no (YYYY-MM-DD) date; the stale check cannot run" in findings[0].message


def test_a_claim_dated_after_today_is_flagged(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, in_progress("2026-09-02"))

    findings = findings_of(plan_root)
    assert [finding.severity for finding in findings] == ["WARNING"]
    assert "claim date 2026-09-02 is after today (2026-09-01)" in findings[0].message


# ── The §4 gate table and the §7 index ──────────────────────────────────────────────────


def test_an_exit_card_must_resolve(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")]}, (MiniGate("G0", "AA-01, AA-09"),))

    error = one_error(plan_root, "G0", "exit card 'AA-09' does not resolve to any card")
    assert error.file == "00-master-plan.md"


def test_a_signed_gate_has_every_exit_card_done(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {"AA": [done_card(), MiniCard("AA-02")]},
        (MiniGate("G0", "AA-01, AA-02", SIGNED),),
    )

    one_error(plan_root, "G0", "signed but exit card(s) not done: AA-02 (WA-09)")


def test_an_exit_card_never_requires_a_card_of_a_later_gate(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {"AA": [MiniCard("AA-01", prereqs="AA-02"), MiniCard("AA-02")]},
        (MiniGate("G0", "AA-01"), MiniGate("G1", "AA-02")),
    )

    one_error(
        plan_root,
        "G0",
        "exit card AA-01 requires AA-02, an exit card only of the later gate G1 — G0 could "
        "never close (WA-09)",
    )


def test_a_prereq_listed_in_an_earlier_gate_as_well_is_fine(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path,
        {"AA": [MiniCard("AA-01", prereqs="AA-02"), MiniCard("AA-02")]},
        (MiniGate("G0", "AA-01, AA-02"), MiniGate("G1", "AA-02")),
    )

    assert findings_of(plan_root) == []


def test_a_plan_without_a_gate_table_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")]}, ())

    one_error(plan_root, "-", "no §4 gate rows found")


def test_a_gate_row_with_too_few_cells_is_an_error(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")]}, (MiniGate("G0"),))
    master = plan_root / "00-master-plan.md"
    master.write_text(
        master.read_text(encoding="utf-8").replace("| evidence | — | owner | open |", "| open |"),
        encoding="utf-8",
    )

    assert any("§4 row has 4 cells, expected 7" in error.message for error in errors_of(plan_root))


def test_a_pipe_inside_backticks_does_not_split_a_gate_row(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [done_card()]}, (MiniGate("G0", "AA-01", SIGNED),))
    master = plan_root / "00-master-plan.md"
    master.write_text(
        master.read_text(encoding="utf-8").replace(
            "| evidence |", "| `gebra verify | snapshot | diff` green |"
        ),
        encoding="utf-8",
    )

    assert findings_of(plan_root) == []
    assert load_plan(plan_root).gates["G0"].signed


def test_the_index_count_must_match_the_board(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")]}, counts={"AA": 2})

    error = one_error(plan_root, "§7", "aa.md: index says 2 cards, the board holds 1")
    assert error.file == "00-master-plan.md"


def test_a_board_listed_in_the_index_must_exist(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path, {"AA": [MiniCard("AA-01")]}, counts={"AA": 1, "BB": 1}, totals=(1, 0)
    )

    one_error(plan_root, "§7", "board bb.md is listed but missing")


def test_a_board_the_index_does_not_list_is_a_warning(tmp_path: Path) -> None:
    plan_root = build_plan(
        tmp_path, {"AA": [MiniCard("AA-01")], "BB": [MiniCard("BB-01")]}, counts={"AA": 1}
    )
    (plan_root / "00-master-plan.md").write_text(
        (plan_root / "00-master-plan.md")
        .read_text(encoding="utf-8")
        .replace("**2 cards; 0 decision cards.**", "**1 cards; 0 decision cards.**"),
        encoding="utf-8",
    )

    findings = findings_of(plan_root)
    assert [(finding.severity, finding.file) for finding in findings] == [("WARNING", "bb.md")]
    assert "not listed in the §7 index" in findings[0].message


def test_the_totals_line_is_checked(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01"), MiniCard("AA-D1")]}, totals=(3, 0))

    findings = findings_of(plan_root)
    assert messages(findings) == [
        "§7: totals line says 3 cards, the indexed boards hold 2",
        "§7: totals line says 0 decision cards, the indexed boards hold 1",
    ]
    assert [finding.severity for finding in findings] == ["ERROR", "WARNING"]


def test_a_plan_without_a_totals_line_skips_that_check(tmp_path: Path) -> None:
    plan_root = build_plan(tmp_path, {"AA": [MiniCard("AA-01")]}, totals_line=False)

    assert findings_of(plan_root) == []


# ── Transitions (§6 diagram) ─────────────────────────────────────────────────────────────


def plan_of(boards: Mapping[str, Sequence[MiniCard]], gates: Sequence[MiniGate] = ()) -> Plan:
    files = plan_files(boards, gates or (MiniGate("G0"),))
    return bi.load_plan_from_texts(
        files["docs/plan/00-master-plan.md"],
        {Path(path).name: text for path, text in files.items() if "/boards/" in path},
    )


def transition(before: MiniCard, after: MiniCard, *others: MiniCard) -> list[Finding]:
    return check_transitions(plan_of({"AA": [before, *others]}), plan_of({"AA": [after, *others]}))


DONE_PREREQ = MiniCard("AA-09", "done", section="Done", boxes=(True,), artifacts="x")


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            MiniCard("AA-01", prereqs="AA-09"),
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
        ),
        (MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"), MiniCard("AA-01")),
        (
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
            MiniCard("AA-01", "in-review", claimed_by="a (2026-09-01)"),
        ),
        (MiniCard("AA-01", "in-review", claimed_by="a (2026-09-01)"), done_card()),
        (MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"), done_card()),
        (
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
            MiniCard("AA-01", "on-hold", claimed_by="a (2026-09-01)"),
        ),
        (MiniCard("AA-01", "on-hold"), MiniCard("AA-01")),
        (MiniCard("AA-01"), MiniCard("AA-01", "dropped")),
        (MiniCard("AA-01"), MiniCard("AA-01", "superseded")),
        (MiniCard("AA-01", "on-hold"), MiniCard("AA-01", "superseded")),
        (MiniCard("AA-01"), MiniCard("AA-01")),
    ],
    ids=[
        "claim",
        "release",
        "pr-open",
        "merged",
        "work-pr-carries-the-flip",
        "hold",
        "re-planned",
        "drop",
        "supersede",
        "supersede-from-hold",
        "unchanged",
    ],
)
def test_every_arrow_of_the_diagram_is_legal(before: MiniCard, after: MiniCard) -> None:
    assert transition(before, after, DONE_PREREQ) == []


@pytest.mark.parametrize(
    ("before", "after", "why"),
    [
        (done_card(), MiniCard("AA-01"), "done is terminal (§6: regressions are new cards)"),
        (
            done_card(),
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
            "done is terminal",
        ),
        (MiniCard("AA-01", "dropped"), MiniCard("AA-01"), "dropped is terminal"),
        (MiniCard("AA-01"), done_card(), "not an arrow of the §6 transition diagram"),
        (
            MiniCard("AA-01"),
            MiniCard("AA-01", "in-review", claimed_by="a (2026-09-01)"),
            "not an arrow",
        ),
        (
            MiniCard("AA-01", "in-review", claimed_by="a (2026-09-01)"),
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
            "not an arrow",
        ),
        (
            MiniCard("AA-01", "on-hold"),
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
            "not an arrow",
        ),
        (
            MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)"),
            MiniCard("AA-01", "dropped"),
            "not an arrow",
        ),
    ],
    ids=[
        "done-to-todo",
        "done-to-in-progress",
        "dropped-to-todo",
        "todo-to-done",
        "todo-to-in-review",
        "in-review-to-in-progress",
        "on-hold-to-in-progress",
        "in-progress-to-dropped",
    ],
)
def test_a_change_off_the_diagram_is_an_illegal_transition(
    before: MiniCard, after: MiniCard, why: str
) -> None:
    findings = transition(before, after)

    assert len(findings) == 1 and findings[0].severity == "ERROR"
    assert findings[0].subject == "AA-01"
    assert f"illegal transition {before.status} -> {after.status}: {why}" in findings[0].message


def test_a_claim_is_only_legal_on_a_ready_card() -> None:
    before = MiniCard("AA-01", prereqs="AA-02, G1")
    after = MiniCard("AA-01", "in-progress", prereqs="AA-02, G1", claimed_by="a (2026-09-01)")
    other = MiniCard("AA-02", "in-review", claimed_by="b (2026-09-01)")
    gates = (MiniGate("G0"), MiniGate("G1"))

    findings = check_transitions(
        plan_of({"AA": [before, other]}, gates), plan_of({"AA": [after, other]}, gates)
    )

    assert len(findings) == 1
    assert (
        "claimed while BLOCKED — unmet: AA-02 (in-review), G1 (open) (WA-01: only READY cards "
        "are claimed)" in findings[0].message
    )


def test_a_removed_card_is_an_error_and_a_new_card_is_not() -> None:
    before = plan_of({"AA": [MiniCard("AA-01"), MiniCard("AA-02")]})
    after = plan_of({"AA": [MiniCard("AA-01"), MiniCard("AA-03")]})

    findings = check_transitions(before, after)

    assert len(findings) == 1 and findings[0].subject == "AA-02"
    assert "card removed — IDs are never reused" in findings[0].message


def test_base_plan_on_the_command_line_judges_the_transition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = build_plan(tmp_path / "before", {"AA": [MiniCard("AA-01")]})
    after = build_plan(tmp_path / "after", {"AA": [done_card()]})

    assert main(["--plan", str(after), "--base-plan", str(before), "--today", "2026-09-01"]) == 1
    assert "illegal transition todo -> done" in capsys.readouterr().err
    assert main(["--plan", str(after), "--base-plan", str(after), "--today", "2026-09-01"]) == 0


# ── The git boundary, faked ──────────────────────────────────────────────────────────────


class FakeGit:
    """A scripted ``_git``: a linear history of plan snapshots, answered per plumbing command."""

    def __init__(
        self,
        toplevel: Path,
        history: Sequence[tuple[str, tuple[str, ...], Mapping[str, str] | None]],
        log: str = "",
    ) -> None:
        self.toplevel = toplevel
        self.log = log
        self.calls: list[tuple[str, ...]] = []
        self.order = [sha for sha, _, _ in history]
        self.parents = {sha: parents for sha, parents, _ in history}
        self.snapshots: dict[str, dict[str, str]] = {}
        for sha, parents, files in history:
            snapshot = dict(self.snapshots[parents[0]]) if parents else {}
            if files:
                snapshot.update(files)
            self.snapshots[sha] = snapshot

    def __call__(self, cwd: Path, *args: str) -> str:
        self.calls.append(args)
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return f"{self.toplevel}\n"
        if args[:2] == ("rev-list", "--parents"):
            sha = args[4]
            return f"{sha} {' '.join(self.parents[sha])}\n"
        if args[:2] == ("rev-list", "--reverse"):
            base, head = args[2].split("..")
            if base not in self.order:
                raise BoardIntegrityError(f"git rev-list failed (exit 128): unknown {base}")
            start, stop = self.order.index(base), self.order.index(head)
            return "".join(f"{sha}\n" for sha in self.order[start + 1 : stop + 1])
        if args[:2] == ("rev-list", "-n"):
            return f"{args[3]}\n"
        if args[0] == "diff":
            before_files, after_files = self.snapshots[args[2]], self.snapshots[args[3]]
            prefix = args[5]
            changed = sorted(
                path
                for path in set(before_files) | set(after_files)
                if path.startswith(f"{prefix}/") and before_files.get(path) != after_files.get(path)
            )
            return "".join(f"{path}\n" for path in changed)
        if args[0] == "show":
            revision, path = args[1].split(":", 1)
            try:
                return self.snapshots[revision][path]
            except KeyError as missing:
                raise BoardIntegrityError(f"git show failed: {path} not in {revision}") from missing
        if args[0] == "ls-tree":
            revision, prefix = args[2], args[3]
            return "".join(
                f"{path}\n" for path in sorted(self.snapshots[revision]) if path.startswith(prefix)
            )
        if args[0] == "log":
            return self.log
        raise AssertionError(f"unexpected git call: {args}")


STATE_TODO = plan_files({"AA": [MiniCard("AA-01")]})
STATE_CLAIMED = plan_files({"AA": [MiniCard("AA-01", "in-progress", claimed_by="a (2026-09-01)")]})
STATE_DONE = plan_files({"AA": [done_card()]})


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, FakeGit]:
    """A working tree at the `done` state, with a scripted history behind it."""
    plan_root = build_plan(tmp_path, {"AA": [done_card()]})
    fake = FakeGit(
        tmp_path,
        [
            ("c0", (), STATE_TODO),
            ("c1", ("c0",), STATE_CLAIMED),
            ("c2", ("c1",), {"README.md": "unrelated"}),
            ("c3", ("c2",), STATE_DONE),
            ("c4", ("c3", "c1"), None),
            ("c5", ("c4",), STATE_TODO),
        ],
    )
    monkeypatch.setattr(bi, "_git", fake)
    return plan_root, fake


def test_the_range_walk_judges_each_commit_against_its_parent(
    repo: tuple[Path, FakeGit], capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root, fake = repo

    assert check_range(plan_root, "c0", "c3") == []
    # c1 and c3 were judged (parent + self listed for each); c2 touched nothing under the
    # plan and was skipped after its diff came back empty.
    assert [call for call in fake.calls if call[0] == "diff"] == [
        ("diff", "--name-only", "c0", "c1", "--", "docs/plan"),
        ("diff", "--name-only", "c1", "c2", "--", "docs/plan"),
        ("diff", "--name-only", "c2", "c3", "--", "docs/plan"),
    ]
    assert sum(1 for call in fake.calls if call[0] == "ls-tree") == 4
    assert "note" not in capsys.readouterr().out


def test_a_commit_that_skips_the_claim_fails_and_names_the_commit(
    repo: tuple[Path, FakeGit],
) -> None:
    plan_root, fake = repo
    # c1 no longer claims (and c2 inherits that), so c3 takes the card from todo to done.
    fake.snapshots["c1"] = dict(fake.snapshots["c0"])
    fake.snapshots["c2"] = {**fake.snapshots["c0"], "README.md": "unrelated"}

    findings = check_range(plan_root, "c0", "c3")

    assert len(findings) == 1
    assert "illegal transition todo -> done" in findings[0].message
    assert "[commit c3]" in findings[0].message


def test_a_merge_commit_is_skipped_with_a_note_and_a_regression_after_it_is_caught(
    repo: tuple[Path, FakeGit], capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root, _ = repo

    findings = check_range(plan_root, "c3", "c5")

    assert "note: c4 is a merge commit" in capsys.readouterr().out
    assert len(findings) == 1
    assert "illegal transition done -> todo" in findings[0].message
    assert "[commit c5]" in findings[0].message


def test_a_null_base_judges_the_head_commit_only(
    repo: tuple[Path, FakeGit], capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root, _ = repo

    assert commits_in_range(plan_root, "0" * 40, "c3") == ["c3"]
    assert "no base revision" in capsys.readouterr().out
    assert check_range(plan_root, "0" * 40, "c3") == []


def test_an_unknown_base_judges_the_head_commit_only_and_says_so(
    repo: tuple[Path, FakeGit], capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root, _ = repo

    assert commits_in_range(plan_root, "deadbeef" * 5, "c3") == ["c3"]
    assert "judging head only" in capsys.readouterr().out


def test_a_parent_with_no_plan_is_skipped_with_a_note(
    repo: tuple[Path, FakeGit], capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root, fake = repo
    fake.snapshots["c0"] = {}
    fake.parents["c1"] = ("c0",)

    assert check_range(plan_root, "c0", "c1") == []
    assert "note: no plan readable at c0" in capsys.readouterr().out


def test_the_range_is_available_from_the_command_line(
    repo: tuple[Path, FakeGit], capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root, _ = repo

    assert (
        main(["--plan", str(plan_root), "--base", "c3", "--head", "c5", "--today", "2026-09-01"])
        == 1
    )
    assert "illegal transition done -> todo" in capsys.readouterr().err


def test_base_and_head_go_together(clean_plan: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--plan", str(clean_plan), "--base", "c0"])

    assert exit_info.value.code == 2


def test_activity_is_the_newest_commit_mentioning_the_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = (
        "2026-09-01\x1fdocs(plan): note\x1fmentions AA-010, which is another card\x1e\n"
        "2026-08-28\x1fchore(plan): claim AA-01\x1f\x1e\n"
        "2026-08-20\x1ffeat(x): thing [AA-01]\x1fbody\x1e\n"
        "2026-08-19\x1fchore(plan): claim AA-02\x1f\x1e\n"
    )
    fake = FakeGit(tmp_path, [("c0", (), None)], log=log)
    monkeypatch.setattr(bi, "_git", fake)

    assert activity_from_git(tmp_path, ["AA-01", "AA-02", "AA-03"]) == {
        "AA-01": date(2026, 8, 28),
        "AA-02": date(2026, 8, 19),
    }
    assert fake.calls == [("log", "--format=%cs%x1f%s%x1f%b%x1e")]


def test_no_in_progress_card_means_no_git_call(
    clean_plan: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGit(clean_plan.parents[1], [("c0", (), None)])
    monkeypatch.setattr(bi, "_git", fake)

    assert main(["--plan", str(clean_plan), "--git", "--today", "2026-09-01"]) == 0
    assert fake.calls == []


def test_git_activity_feeds_the_stale_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root = build_plan(tmp_path, in_progress("2026-08-03"))
    fake = FakeGit(tmp_path, [("c0", (), None)], log="2026-08-31\x1fdocs: touch AA-01\x1f\x1e\n")
    monkeypatch.setattr(bi, "_git", fake)

    assert main(["--plan", str(plan_root), "--git", "--today", "2026-09-01"]) == 0
    assert "stale" not in capsys.readouterr().out


def test_a_git_failure_is_exit_status_2_never_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root = build_plan(tmp_path, in_progress("2026-08-03"))

    def failing(cwd: Path, *arguments: str) -> str:
        raise BoardIntegrityError("git log failed (exit 128): not a git repository")

    monkeypatch.setattr(bi, "_git", failing)

    assert main(["--plan", str(plan_root), "--git", "--today", "2026-09-01"]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_the_default_check_runs_with_subprocess_disabled(
    clean_plan: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WA-07: without --git or --base/--head the tool never spawns anything."""

    def armed(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("subprocess.run was called")

    monkeypatch.setattr(subprocess, "run", armed)
    stale = build_plan(clean_plan.parents[1] / "stale", in_progress("2026-08-03"))

    assert main(["--plan", str(clean_plan), "--today", "2026-09-01"]) == 0
    assert main(["--plan", str(stale), "--today", "2026-09-01"]) == 0


def test_the_real_git_boundary_reports_a_failing_command_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_git` itself, over a faked `subprocess.run`: a non-zero exit becomes the error."""

    class Completed:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    def fake_run(*args: Any, **kwargs: Any) -> Completed:
        assert args[0][:2] == ["git", "log"] and kwargs["cwd"] == tmp_path
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BoardIntegrityError, match="git log failed \\(exit 128\\): fatal"):
        bi._git(tmp_path, "log")


# ── The CLI ──────────────────────────────────────────────────────────────────────────────


def test_a_missing_plan_is_exit_status_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--plan", str(tmp_path / "nowhere")]) == 2
    assert "master plan not found" in capsys.readouterr().err

    (tmp_path / "00-master-plan.md").write_text("# nothing\n", encoding="utf-8")
    assert main(["--plan", str(tmp_path)]) == 2
    assert "boards directory not found" in capsys.readouterr().err


def test_no_discoverable_plan_names_both_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bi, "REPO_ROOT", tmp_path / "repo")

    assert main([]) == 2
    err = capsys.readouterr().err
    assert "no plan found — pass --plan" in err
    assert str(tmp_path / "repo" / "docs" / "plan") in err
    assert str(tmp_path / "gebra-dev-doc" / "docs" / "plan") in err


def test_the_plan_beside_the_script_is_preferred_over_the_sibling_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = build_plan(tmp_path / "repo", {"AA": [MiniCard("AA-01")]})
    sibling = build_plan(tmp_path / "gebra-dev-doc", {"BB": [MiniCard("BB-01")]})
    monkeypatch.setattr(bi, "REPO_ROOT", tmp_path / "repo")

    assert bi.default_plan_root() == own

    shutil.rmtree(own)
    assert bi.default_plan_root() == sibling


def test_errors_go_to_stderr_and_a_clean_report_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = build_plan(tmp_path / "broken", {"AA": [MiniCard("AA-01", prereqs="ZZ-99")]})
    clean = build_plan(tmp_path / "clean", {"AA": [MiniCard("AA-01")]})

    assert main(["--plan", str(broken), "--today", "2026-09-01"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[0] == f"board integrity: {broken}"
    assert "ERROR    aa.md                AA-01     prereq 'ZZ-99' does not resolve" in captured.err
    assert captured.err.splitlines()[-1] == (
        "board integrity: 1 error(s), 0 warning(s) — 1 cards, 1 gates, 1 boards"
    )

    assert main(["--plan", str(clean), "--today", "2026-09-01"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines()[-1] == "board integrity: clean — 1 cards, 1 gates, 1 boards"


def test_annotations_anchor_each_finding_to_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan_root = build_plan(
        tmp_path,
        {
            "AA": [
                MiniCard("AA-01", prereqs="ZZ-99"),
                MiniCard("AA-02", "in-progress", claimed_by="a (2026-08-03)"),
            ]
        },
        (MiniGate("G0", "AA-07"),),
    )
    monkeypatch.chdir(tmp_path)
    board_lines = (plan_root / "boards" / "aa.md").read_text(encoding="utf-8").splitlines()
    master_lines = (plan_root / "00-master-plan.md").read_text(encoding="utf-8").splitlines()
    prereq_line = board_lines.index("- **prereqs:** ZZ-99") + 1
    claim_line = board_lines.index("- **claimed_by:** a (2026-08-03)") + 1
    gate_line = next(n for n, line in enumerate(master_lines, 1) if line.startswith("| **G0** |"))

    assert main(["--plan", str(plan_root), "--today", "2026-09-01", "--annotations"]) == 1

    out = capsys.readouterr().out.splitlines()
    assert out == [
        (
            f"::error file=docs/plan/boards/aa.md,line={prereq_line},title=board integrity::"
            "AA-01: prereq 'ZZ-99' does not resolve to any card (dangling)"
        ),
        (
            f"::warning file=docs/plan/boards/aa.md,line={claim_line},title=board integrity::"
            "AA-02: stale: in-progress with no linked activity since 2026-08-03 (21 working "
            "days > 5; §6: release is preferred over squatting)"
        ),
        (
            f"::error file=docs/plan/00-master-plan.md,line={gate_line},title=board integrity::"
            "G0: exit card 'AA-07' does not resolve to any card"
        ),
    ]


def test_a_finding_renders_as_the_skills_line() -> None:
    finding = Finding("ERROR", "aa.md", "AA-01", "what went wrong", 3)

    assert finding.render() == "ERROR    aa.md                AA-01     what went wrong"


def test_the_script_runs_as_a_plain_command(tmp_path: Path) -> None:
    """The CI job's own invocation shape, exit status observed rather than assumed."""
    broken = build_plan(tmp_path / "broken", {"AA": [MiniCard("AA-01", prereqs="ZZ-99")]})
    clean = build_plan(tmp_path / "clean", {"AA": [MiniCard("AA-01")]})

    failed = subprocess.run(
        [sys.executable, str(SCRIPT), "--plan", str(broken), "--today", "2026-09-01"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 1, failed.stderr
    assert "does not resolve to any card (dangling)" in failed.stderr

    passed = subprocess.run(
        [sys.executable, str(SCRIPT), "--plan", str(clean), "--today", "2026-09-01"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert passed.returncode == 0, passed.stderr
    assert passed.stdout.splitlines()[-1] == "board integrity: clean — 1 cards, 1 gates, 1 boards"


# ── The real boards ──────────────────────────────────────────────────────────────────────


def board_digests() -> dict[str, str]:
    """The master plan and every board, hashed — what a seeded test must leave untouched."""
    files = [
        COMPANION_PLAN / "00-master-plan.md",
        *sorted((COMPANION_PLAN / "boards").glob("*.md")),
    ]
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def copy_of_the_plan(tmp_path: Path) -> Path:
    """The master plan and the boards, copied; seeded edits land here, never on the originals."""
    plan_root = tmp_path / "plan"
    (plan_root / "boards").mkdir(parents=True)
    shutil.copy(COMPANION_PLAN / "00-master-plan.md", plan_root / "00-master-plan.md")
    for board in (COMPANION_PLAN / "boards").glob("*.md"):
        shutil.copy(board, plan_root / "boards" / board.name)
    return plan_root


def card_block(text: str, card_id: str) -> re.Match[str]:
    match = re.search(
        rf"^### {re.escape(card_id)} — .*?(?=^### |^## |\Z)", text, flags=re.MULTILINE | re.DOTALL
    )
    assert match is not None, card_id
    return match


def set_field(board: Path, card_id: str, name: str, value: str) -> None:
    """Rewrite one bold field's first line inside one card's block, leaving the rest as is."""
    text = board.read_text(encoding="utf-8")
    block = card_block(text, card_id)
    edited = re.sub(
        rf"^- \*\*{name}:\*\*.*$",
        lambda _: f"- **{name}:** {value}",
        block.group(0),
        count=1,
        flags=re.MULTILINE,
    )
    assert edited != block.group(0), f"{card_id} has no {name} field"
    board.write_text(text[: block.start()] + edited + text[block.end() :], encoding="utf-8")


def add_prereq(board: Path, card_id: str, token: str) -> None:
    text = board.read_text(encoding="utf-8")
    block = card_block(text, card_id)
    line = re.search(r"^- \*\*prereqs:\*\* (.*)$", block.group(0), flags=re.MULTILINE)
    assert line is not None
    current = line.group(1).strip()
    set_field(board, card_id, "prereqs", token if current == "none" else f"{current}, {token}")


@requires_companion
def test_the_real_boards_are_clean_as_merged(capsys: pytest.CaptureFixture[str]) -> None:
    """Acceptance box 2's local half: the check the CI job runs, green on the boards."""
    plan = load_plan(COMPANION_PLAN)

    assert [f for f in check_plan(plan) if f.severity == "ERROR"] == []
    assert main(["--plan", str(COMPANION_PLAN)]) == 0
    assert len(plan.cards) >= 139
    assert len(plan.gates) == 8
    assert capsys.readouterr().out.splitlines()[-1].startswith("board integrity: clean")


@requires_companion
def test_the_default_plan_root_is_the_companion_checkout() -> None:
    assert bi.default_plan_root() == COMPANION_PLAN


@requires_companion
def test_a_seeded_dangling_prereq_on_the_real_boards_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance box 1, first half: the edit is made on a copy, so 'reverted' is by construction."""
    before = board_digests()
    plan_root = copy_of_the_plan(tmp_path)
    plan = load_plan(plan_root)
    victim = next(card for card in plan.cards.values() if card.status == "todo")
    add_prereq(plan_root / "boards" / victim.board, victim.id, "ZZ-99")

    assert main(["--plan", str(plan_root)]) == 1
    err = capsys.readouterr().err
    assert f"{victim.id:<9} prereq 'ZZ-99' does not resolve to any card (dangling)" in err
    assert board_digests() == before


@requires_companion
def test_a_seeded_cycle_on_the_real_boards_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance box 1, second half: a card made to require one of its own dependents."""
    before = board_digests()
    plan_root = copy_of_the_plan(tmp_path)
    plan = load_plan(plan_root)
    dependent = next(card for card in plan.cards.values() if card.prereq_cards)
    prerequisite = plan.cards[dependent.prereq_cards[0]]
    add_prereq(plan_root / "boards" / prerequisite.board, prerequisite.id, dependent.id)

    assert main(["--plan", str(plan_root)]) == 1
    err = capsys.readouterr().err
    assert "dependency cycle: " in err
    assert (
        f"{dependent.id} -> {prerequisite.id}" in err
        or f"{prerequisite.id} -> {dependent.id}" in err
    )
    assert board_digests() == before


@requires_companion
def test_a_seeded_stale_claim_on_the_real_boards_is_flagged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance box 3 on the real boards: in-progress since early August, no activity."""
    before = board_digests()
    plan_root = copy_of_the_plan(tmp_path)
    plan = load_plan(plan_root)
    victim = next(card for card in plan.cards.values() if card.status == "todo")
    board = plan_root / "boards" / victim.board
    set_field(board, victim.id, "status", "in-progress")
    set_field(board, victim.id, "claimed_by", "someone (2026-08-03)")

    assert main(["--plan", str(plan_root), "--today", "2026-09-01"]) == 0
    out = capsys.readouterr().out
    assert f"WARNING  {victim.board:<20} {victim.id:<9} stale: in-progress" in out
    assert "since 2026-08-03 (21 working days > 5" in out
    assert board_digests() == before


@requires_companion
def test_the_real_boards_parse_the_way_the_miniature_ones_do() -> None:
    plan = load_plan(COMPANION_PLAN)
    tool_01 = plan.cards["TOOL-01"]

    assert tool_01.board == "tooling.md" and tool_01.section == "Done"
    assert tool_01.status == "done" and tool_01.is_claimed
    assert tool_01.prereq_tokens == ["none"]
    assert len(tool_01.acceptance) == 3 and all(checked for checked, _ in tool_01.acceptance)
    assert "TOOL-01-validation-notes.md" in tool_01.artifacts
    assert plan.board_prefixes["tooling.md"] == "TOOL"
    assert plan.index["tooling.md"][0] == "TOOL"


# ── The companion's copy, its workflow, and the skill ───────────────────────────────────


@requires_companion_copy
def test_the_companion_copy_is_byte_identical() -> None:
    """One implementation, two repositories: drift between the copies is a defect."""
    assert COMPANION_SCRIPT.read_bytes() == SCRIPT.read_bytes()


@requires_companion_workflow
def test_the_companion_workflow_runs_the_check_on_every_push() -> None:
    # PyYAML reads the bare `on:` key as the boolean True (YAML 1.1), hence the untyped keys.
    workflow: dict[Any, Any] = yaml.safe_load(COMPANION_WORKFLOW.read_text(encoding="utf-8"))
    triggers: dict[str, Any] = workflow.get("on") or workflow[True]

    assert "push" in triggers and "pull_request" in triggers
    jobs = list(workflow["jobs"].values())
    assert len(jobs) == 1
    steps = jobs[0]["steps"]
    checkout = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0
    commands = [step["run"] for step in steps if isinstance(step.get("run"), str)]
    assert any("python tools/board_integrity.py" in command for command in commands)
    command = next(command for command in commands if "board_integrity.py" in command)
    for flag in ("--git", "--base", "--head", "--annotations"):
        assert flag in command, flag


@requires_the_skill
def test_the_skill_runs_the_same_script() -> None:
    """The /plan-status check mode computes its verdict with this script, so the two agree."""
    skill = COMPANION_SKILL.read_text(encoding="utf-8")

    assert "python tools/board_integrity.py" in skill
    assert "Mode B" in skill
