"""Board integrity — the ``/plan-status check`` rules, computed (TOOL-02).

The task boards under ``docs/plan/boards/`` and the gate table in master plan §4 are the plan's
single source of truth (WA-02), and §6 says what a well-formed board is: unique card IDs; a
prerequisite list whose every token is a real card or a §4 gate; no dependency cycles; only the
seven stored statuses, with a claim recorded exactly when the status says one exists; a ``done``
card that sits in ``## Done`` with every acceptance box checked and its artifacts filled; an
``on-hold`` card that links its reason; a ``superseded`` card that names its replacement; and an
``in-progress`` claim flagged stale after five working days without linked activity. §7 adds
the ID scheme and the board-index counts, and §6's transition diagram says which status changes
are legal at all. This module is those rules as code, so that the skill's verdict and the CI
job's verdict are one computation rather than two readings.

Two kinds of finding. ``ERROR`` means the boards are not well-formed and the exit status is 1.
``WARNING`` is advisory — a stale claim, a decision-card count that drifted, a board the index
does not list — and leaves the exit status at 0. Exit status 2 means the plan could not be
evaluated at all (no plan found, git unavailable), which is never a pass.

Usage::

    python tools/board_integrity.py                          # plan root found automatically
    python tools/board_integrity.py --plan path/to/docs/plan
    python tools/board_integrity.py --git                    # stale check also reads git log
    python tools/board_integrity.py --base <sha> --head <sha> # transitions, commit by commit
    python tools/board_integrity.py --base-plan <dir>        # transitions against a plan copy
    python tools/board_integrity.py --annotations            # GitHub Actions annotations too

The plan root defaults to ``docs/plan`` beside this script's ``tools/`` directory (the layout
of the development-process repository, where the CI job runs a byte-identical copy of this
file) and otherwise to the sibling checkout of that repository.

WA-07: this tool reads Markdown, and — only when asked to with ``--git`` or ``--base``/``--head``
— git metadata through one subprocess boundary. It imports, executes and fetches nothing;
``tests/test_board_integrity.py`` fakes the boundary and never spawns git.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MASTER_PLAN_NAME = "00-master-plan.md"
BOARDS_DIR_NAME = "boards"

#: §6 — the seven stored statuses. READY and BLOCKED are derived and never stored.
STATUSES: tuple[str, ...] = (
    "todo",
    "in-progress",
    "in-review",
    "on-hold",
    "done",
    "dropped",
    "superseded",
)
LIVE_STATUSES = frozenset({"todo", "in-progress", "in-review", "on-hold"})
TERMINAL_STATUSES = frozenset({"done", "dropped", "superseded"})
DERIVED_STATUSES = frozenset({"ready", "blocked"})

#: §6 — the legal transitions, exactly the arrows of the diagram.
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("todo", "in-progress"),  # claim (READY only)
        ("in-progress", "todo"),  # release
        ("in-progress", "in-review"),  # PR open
        ("in-review", "done"),  # merged + acceptance
        ("in-progress", "done"),  # the work PR carries the flip (§6 note)
        ("in-progress", "on-hold"),  # spec defect / pending PD
        ("todo", "superseded"),
        ("todo", "dropped"),
        ("on-hold", "superseded"),
        ("on-hold", "dropped"),
        ("on-hold", "todo"),  # ruling re-vendored + card re-planned
    }
)

#: The normative card format — every card carries these nine fields.
REQUIRED_FIELDS: tuple[str, ...] = (
    "status",
    "claimed_by",
    "estimate",
    "prereqs",
    "spec_refs",
    "objective",
    "acceptance",
    "decisions_to_implementer",
    "artifacts",
)

#: The fields that start a new value. Any other bold line inside a card — a PD-008
#: confirming-run note, a rescope note, a released-from-hold record — is evidence maintenance:
#: under a free-text field it is read as part of that field's value; under a one-line field
#: (status, claimed_by, estimate, prereqs) it ends the value instead.
KNOWN_FIELDS = frozenset(REQUIRED_FIELDS) | {"hold_reason", "superseded_by"}
SCALAR_FIELDS = frozenset({"status", "claimed_by", "estimate", "prereqs"})

#: §6 — "`in-progress` with no linked activity for 5 working days is flagged stale."
STALE_AFTER_WORKING_DAYS = 5
DONE_SECTION = "Done"
EMPTY_VALUES = frozenset({"", "—", "-", "none", "n/a"})
ESTIMATES = frozenset({"S", "M", "L"})

CARD_HEADING = re.compile(r"^### (?P<id>\S+)\s+—\s+(?P<title>.*)$")
ID_LIKE = re.compile(r"^[A-Z]{2,}-")
#: §7 — `<PREFIX>-<NN>` build cards, `<PREFIX>-D<N>` decision cards.
ID_GRAMMAR = re.compile(r"^(?P<prefix>[A-Z]+)-(?:D(?P<decision>\d+)|(?P<build>\d{2,}))$")
GATE_GRAMMAR = re.compile(r"^G\d+$")
FIELD_LINE = re.compile(r"^- \*\*(?P<name>[^*]+?):\*\*\s*(?P<value>.*)$")
CHECKBOX = re.compile(r"^\s*- \[(?P<mark>[ xX])\]\s*(?P<text>.*)$")
SECTION_HEADING = re.compile(r"^## (?P<name>.+?)\s*$")
BOARD_PREFIX = re.compile(r"^- \*\*prefix:\*\*\s*(?P<prefix>[A-Z]+)-\s*$", re.MULTILINE)
GATE_ROW = re.compile(r"^\|\s*\*\*(?P<id>G\d+)\*\*\s*\|")
INDEX_ROW = re.compile(
    r"^\|\s*\[boards/(?P<file>[a-z0-9-]+\.md)\][^|]*\|\s*`(?P<prefix>[A-Z]+)-`\s*\|"
    r"\s*(?P<count>\d+)\s*\|"
)
TOTALS = re.compile(r"\*\*(?P<cards>\d+) cards;\s*(?P<decisions>\d+) decision cards\.\*\*")
ID_TOKEN = re.compile(r"\b([A-Z]{2,}-D?\d+)\b")
RANGE_TOKEN = re.compile(r"([A-Z]+)-(\d+)…(?:[A-Z]+-)?(\d+)")
CLAIM_DATE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
#: An HTML comment is invisible in rendered Markdown, so it is not part of a field's value.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
LINK_MARKERS = (
    re.compile(r"\]\("),
    re.compile(r"https?://"),
    re.compile(r"\b(?:PD|DEC)-\d+"),
    re.compile(r"#\d+"),
)

#: A push event's "before" on a newly created ref: no base to walk from.
_NULL_SHAS = frozenset({"0" * 40, "0" * 64})


class PlanError(RuntimeError):
    """The plan could not be read at all — always exit 2, never a silent pass."""


class BoardIntegrityError(RuntimeError):
    """The evaluation could not complete (git failed) — always exit 2."""


# ── The findings ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """One violation: ``SEVERITY  <file>  <card-or-gate>  <what>`` (the skill's own line)."""

    severity: str  # "ERROR" | "WARNING"
    file: str  # board file name, or the master plan's
    subject: str  # card ID, gate ID, or "-"
    message: str
    line: int | None = None

    def render(self) -> str:
        return f"{self.severity:<8} {self.file:<20} {self.subject:<9} {self.message}"


def error(file: str, subject: str, message: str, line: int | None = None) -> Finding:
    return Finding("ERROR", file, subject, message, line)


def warning(file: str, subject: str, message: str, line: int | None = None) -> Finding:
    return Finding("WARNING", file, subject, message, line)


# ── The plan ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Card:
    """One card block: its heading, the section it sits under, and its bold fields."""

    id: str
    title: str
    board: str
    line: int
    section: str
    fields: dict[str, str] = field(default_factory=dict)
    field_lines: dict[str, int] = field(default_factory=dict)
    acceptance: list[tuple[bool, str]] = field(default_factory=list)

    def value(self, name: str) -> str:
        """A field's value with its continuation lines, HTML comments removed."""
        return HTML_COMMENT.sub(" ", self.fields.get(name, "")).strip()

    @property
    def status(self) -> str:
        return self.value("status")

    @property
    def claimed_by(self) -> str:
        return self.value("claimed_by")

    @property
    def is_claimed(self) -> bool:
        return self.claimed_by.lower() not in EMPTY_VALUES

    @property
    def artifacts(self) -> str:
        return self.value("artifacts")

    @property
    def hold_reason(self) -> str:
        return self.value("hold_reason")

    @property
    def prereq_tokens(self) -> list[str]:
        raw = self.value("prereqs").replace("\n", " ")
        return [token.strip() for token in raw.split(",") if token.strip()]

    @property
    def prereq_cards(self) -> list[str]:
        return [token for token in self.prereq_tokens if ID_GRAMMAR.match(token)]

    @property
    def prereq_gates(self) -> list[str]:
        return [token for token in self.prereq_tokens if GATE_GRAMMAR.match(token)]

    @property
    def prefix(self) -> str:
        return self.id.split("-", 1)[0]

    @property
    def is_decision(self) -> bool:
        match = ID_GRAMMAR.match(self.id)
        return bool(match and match["decision"] is not None)

    def line_of(self, name: str) -> int:
        return self.field_lines.get(name, self.line)


@dataclass(frozen=True)
class Gate:
    """One §4 row. A gate is signed iff its Status cell is anything other than ``open``."""

    id: str
    name: str
    exit_cards: tuple[str, ...]
    status_cell: str
    line: int

    @property
    def number(self) -> int:
        return int(self.id[1:])

    @property
    def signed(self) -> bool:
        cell = self.status_cell.strip().lower()
        return bool(cell) and cell != "open"


@dataclass
class Plan:
    """Everything the checks read: cards, gates, the §7 index, and what parsing itself found."""

    cards: dict[str, Card] = field(default_factory=dict)
    gates: dict[str, Gate] = field(default_factory=dict)
    boards: list[str] = field(default_factory=list)
    board_prefixes: dict[str, str | None] = field(default_factory=dict)
    index: dict[str, tuple[str, int]] = field(default_factory=dict)
    totals: tuple[int, int] | None = None
    findings: list[Finding] = field(default_factory=list)

    def cards_on(self, board: str) -> list[Card]:
        return [card for card in self.cards.values() if card.board == board]


def _split_cells(row: str) -> list[str]:
    """Split a Markdown table row on ``|``, leaving pipes inside backticks alone."""
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    for char in row.strip().strip("|"):
        if char == "`":
            in_code = not in_code
        if char == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def expand_exit_cell(cell: str) -> tuple[str, ...]:
    """The card IDs an exit-cards cell names, with ``EX-01…EX-11`` ranges spelled out."""
    ids = set(ID_TOKEN.findall(cell))
    for prefix, low, high in RANGE_TOKEN.findall(cell):
        width = len(low)
        for number in range(int(low), int(high) + 1):
            ids.add(f"{prefix}-{number:0{width}d}")
    return tuple(sorted(ids))


def parse_master(text: str) -> tuple[Plan, None]:
    """The §4 gate table, the §7 board index and the §7 totals line, into a fresh plan."""
    plan = Plan()
    for line_no, line in enumerate(text.splitlines(), 1):
        gate = GATE_ROW.match(line)
        if gate:
            cells = _split_cells(line)
            if len(cells) < 7:
                plan.findings.append(
                    error(
                        MASTER_PLAN_NAME,
                        gate["id"],
                        f"§4 row has {len(cells)} cells, expected 7",
                        line_no,
                    )
                )
                continue
            plan.gates[gate["id"]] = Gate(
                id=gate["id"],
                name=cells[1],
                exit_cards=expand_exit_cell(cells[2]),
                status_cell=cells[6],
                line=line_no,
            )
            continue
        index = INDEX_ROW.match(line)
        if index:
            plan.index[index["file"]] = (index["prefix"], int(index["count"]))
    totals = TOTALS.search(text)
    if totals:
        plan.totals = (int(totals["cards"]), int(totals["decisions"]))
    if not plan.gates:
        plan.findings.append(error(MASTER_PLAN_NAME, "-", "no §4 gate rows found"))
    return plan, None


def parse_board(name: str, text: str, plan: Plan) -> None:
    """Every ``### <ID> — <Title>`` block of one board, with the section it sits under."""
    plan.boards.append(name)
    prefix = BOARD_PREFIX.search(text)
    plan.board_prefixes[name] = prefix["prefix"] if prefix else None
    section = ""
    current: Card | None = None
    current_field: str | None = None
    for line_no, line in enumerate(text.splitlines(), 1):
        heading = SECTION_HEADING.match(line)
        if heading:
            section = heading["name"]
            current, current_field = None, None
            continue
        card_heading = CARD_HEADING.match(line)
        if card_heading:
            card = Card(
                id=card_heading["id"],
                title=card_heading["title"].strip(),
                board=name,
                line=line_no,
                section=section,
            )
            if card.id in plan.cards:
                other = plan.cards[card.id]
                plan.findings.append(
                    error(
                        name,
                        card.id,
                        f"duplicate card ID — also at {other.board}:{other.line} (§6: IDs are "
                        "never reused)",
                        line_no,
                    )
                )
                current, current_field = None, None
                continue
            plan.cards[card.id] = card
            current, current_field = card, None
            continue
        if line.startswith("#"):
            words = line.lstrip("#").split()
            if line.startswith("### ") and words and ID_LIKE.match(words[0]):
                plan.findings.append(
                    error(name, words[0], "card heading is not `### <ID> — <Title>`", line_no)
                )
            current, current_field = None, None
            continue
        if current is None:
            continue
        bold = FIELD_LINE.match(line)
        if bold:
            field_name = bold["name"].strip()
            if field_name in KNOWN_FIELDS:
                if field_name in current.fields:
                    plan.findings.append(
                        error(name, current.id, f"field `{field_name}` appears twice", line_no)
                    )
                    current_field = None
                    continue
                current.fields[field_name] = bold["value"].strip()
                current.field_lines[field_name] = line_no
                current_field = field_name
                continue
            if current_field in SCALAR_FIELDS:
                current_field = None
                continue
        if current_field is None:
            continue
        box = CHECKBOX.match(line)
        if box and current_field == "acceptance":
            current.acceptance.append((box["mark"].lower() == "x", box["text"].strip()))
        stripped = line.strip()
        if stripped:
            joined = f"{current.fields[current_field]}\n{stripped}"
            current.fields[current_field] = joined.strip()


def load_plan_from_texts(master_text: str, boards: Mapping[str, str]) -> Plan:
    """Build a plan from texts — the working tree, or one commit's ``git show`` output."""
    plan, _ = parse_master(master_text)
    for name in sorted(boards):
        parse_board(name, boards[name], plan)
    return plan


def load_plan(plan_root: Path) -> Plan:
    """Read ``00-master-plan.md`` and every ``boards/*.md`` under ``plan_root``."""
    master = plan_root / MASTER_PLAN_NAME
    boards_dir = plan_root / BOARDS_DIR_NAME
    if not master.is_file():
        raise PlanError(f"master plan not found: {master}")
    if not boards_dir.is_dir():
        raise PlanError(f"boards directory not found: {boards_dir}")
    boards = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(boards_dir.glob("*.md"))
    }
    return load_plan_from_texts(master.read_text(encoding="utf-8"), boards)


def default_plan_root() -> Path | None:
    """``docs/plan`` beside this script's repository, else the sibling companion checkout."""
    for candidate in default_plan_candidates():
        if (candidate / MASTER_PLAN_NAME).is_file() and (candidate / BOARDS_DIR_NAME).is_dir():
            return candidate
    return None


def default_plan_candidates() -> tuple[Path, Path]:
    return (
        REPO_ROOT / "docs" / "plan",
        REPO_ROOT.parent / "gebra-dev-doc" / "docs" / "plan",
    )


# ── The checks ───────────────────────────────────────────────────────────────────────────


def check_fields(plan: Plan) -> list[Finding]:
    """The normative card format: nine fields, an S/M/L estimate."""
    findings: list[Finding] = []
    for card in plan.cards.values():
        missing = [name for name in REQUIRED_FIELDS if name not in card.fields]
        if missing:
            findings.append(
                error(card.board, card.id, f"missing field(s): {', '.join(missing)}", card.line)
            )
        if "estimate" in card.fields and card.value("estimate") not in ESTIMATES:
            findings.append(
                error(
                    card.board,
                    card.id,
                    f"estimate {card.value('estimate')!r} is not S, M or L (§7)",
                    card.line_of("estimate"),
                )
            )
    return findings


def check_ids(plan: Plan) -> list[Finding]:
    """§7 ID scheme, and every card on the board whose prefix it carries."""
    findings: list[Finding] = []
    for card in plan.cards.values():
        if not ID_GRAMMAR.match(card.id):
            findings.append(
                error(
                    card.board,
                    card.id,
                    "card ID is not `<PREFIX>-<NN>` or `<PREFIX>-D<N>` (§7)",
                    card.line,
                )
            )
            continue
        declared = plan.board_prefixes.get(card.board)
        if declared is not None and card.prefix != declared:
            findings.append(
                error(
                    card.board,
                    card.id,
                    f"card prefix {card.prefix}- on a board whose header declares {declared}-",
                    card.line,
                )
            )
    return findings


def check_prereqs(plan: Plan) -> list[Finding]:
    """Every prereq token is `none`, an existing card ID, or a §4 gate ID."""
    findings: list[Finding] = []
    for card in plan.cards.values():
        if "prereqs" not in card.fields:
            continue
        line = card.line_of("prereqs")
        tokens = card.prereq_tokens
        if not tokens:
            findings.append(
                error(card.board, card.id, "prereqs is empty — write `none` or a list", line)
            )
            continue
        if any(token.lower() == "none" for token in tokens):
            if len(tokens) > 1:
                findings.append(
                    error(card.board, card.id, "`none` mixed with other prereq tokens", line)
                )
            continue
        for token in tokens:
            if GATE_GRAMMAR.match(token):
                if token not in plan.gates:
                    findings.append(
                        error(
                            card.board,
                            card.id,
                            f"prereq gate {token!r} is not in the master plan §4 gate table",
                            line,
                        )
                    )
            elif ID_GRAMMAR.match(token):
                if token == card.id:
                    findings.append(
                        error(card.board, card.id, "lists itself as a prerequisite", line)
                    )
                elif token not in plan.cards:
                    findings.append(
                        error(
                            card.board,
                            card.id,
                            f"prereq {token!r} does not resolve to any card (dangling)",
                            line,
                        )
                    )
            else:
                findings.append(
                    error(
                        card.board,
                        card.id,
                        f"prereq token {token!r} is neither a card ID (<PREFIX>-<NN> / "
                        "<PREFIX>-D<N>) nor a gate ID (G<n>)",
                        line,
                    )
                )
    return findings


def find_cycles(edges: Mapping[str, Iterable[str]]) -> list[list[str]]:
    """Every elementary cycle a depth-first walk meets, as a closed ID path."""
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(edges, white)
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    for root in edges:
        if color[root] != white:
            continue
        color[root] = gray
        stack = [(root, iter(edges[root]))]
        path = [root]
        while stack:
            node, successors = stack[-1]
            for successor in successors:
                if successor not in color:
                    continue
                if color[successor] == gray:
                    cycle = path[path.index(successor) :] + [successor]
                    members = frozenset(cycle)
                    if members not in seen:
                        seen.add(members)
                        cycles.append(cycle)
                elif color[successor] == white:
                    color[successor] = gray
                    stack.append((successor, iter(edges[successor])))
                    path.append(successor)
                    break
            else:
                color[node] = black
                stack.pop()
                path.pop()
    return cycles


def check_cycles(plan: Plan) -> list[Finding]:
    """No dependency cycles over card → prereq edges; each reported as its full ID path."""
    edges = {cid: card.prereq_cards for cid, card in plan.cards.items()}
    findings: list[Finding] = []
    for cycle in find_cycles(edges):
        first = plan.cards[cycle[0]]
        findings.append(
            error(
                first.board,
                cycle[0],
                "dependency cycle: " + " -> ".join(cycle),
                first.line_of("prereqs"),
            )
        )
    return findings


def check_statuses(plan: Plan) -> list[Finding]:
    """Only the seven stored statuses; a claim recorded exactly when the status says so."""
    findings: list[Finding] = []
    for card in plan.cards.values():
        if "status" not in card.fields:
            continue
        status = card.status
        line = card.line_of("status")
        if status not in STATUSES:
            hint = (
                " — READY/BLOCKED are derived, never stored"
                if status.lower() in DERIVED_STATUSES
                else ""
            )
            findings.append(
                error(
                    card.board,
                    card.id,
                    f"status {status!r} is not one of {', '.join(STATUSES)}{hint}",
                    line,
                )
            )
            continue
        if status in ("in-progress", "in-review") and not card.is_claimed:
            findings.append(error(card.board, card.id, f"{status} but claimed_by is empty", line))
        if status == "todo" and card.is_claimed:
            findings.append(
                error(
                    card.board,
                    card.id,
                    f"todo but claimed_by is {card.claimed_by!r} — a todo card carries `—`",
                    line,
                )
            )
    return findings


def check_done(plan: Plan) -> list[Finding]:
    """`done` invariants, and `## Done` holding completed cards only."""
    findings: list[Finding] = []
    for card in plan.cards.values():
        status = card.status
        line = card.line_of("status")
        if status == "done":
            if card.section != DONE_SECTION:
                where = f"`## {card.section}`" if card.section else "no section"
                findings.append(
                    error(
                        card.board,
                        card.id,
                        f"done but sits under {where} — completed cards move to `## Done` "
                        "verbatim (§6)",
                        line,
                    )
                )
            if not card.acceptance:
                findings.append(
                    error(card.board, card.id, "done but has no acceptance checkboxes", line)
                )
            else:
                unchecked = sum(1 for checked, _ in card.acceptance if not checked)
                if unchecked:
                    findings.append(
                        error(
                            card.board,
                            card.id,
                            f"done with {unchecked} unchecked acceptance box(es) (§6)",
                            line,
                        )
                    )
            if card.artifacts.lower() in EMPTY_VALUES:
                findings.append(
                    error(card.board, card.id, "done but artifacts is empty (§6)", line)
                )
        elif status in LIVE_STATUSES and card.section == DONE_SECTION:
            findings.append(
                error(
                    card.board,
                    card.id,
                    f"{status} card sits under `## Done`, which holds completed cards only",
                    line,
                )
            )
    return findings


def _has_link(text: str) -> bool:
    return any(marker.search(text) for marker in LINK_MARKERS)


def check_holds(plan: Plan) -> list[Finding]:
    """`on-hold` links its reason; `superseded` names its replacement."""
    findings: list[Finding] = []
    for card in plan.cards.values():
        status = card.status
        if status == "on-hold":
            if card.hold_reason.lower() in EMPTY_VALUES:
                findings.append(
                    error(
                        card.board,
                        card.id,
                        "on-hold without a hold_reason (§6: link a spec-defect issue or a "
                        "pending PD)",
                        card.line_of("status"),
                    )
                )
            elif not _has_link(card.hold_reason):
                findings.append(
                    error(
                        card.board,
                        card.id,
                        "hold_reason carries no link (a Markdown link, URL, PD-/DEC- record "
                        "or #issue)",
                        card.line_of("hold_reason"),
                    )
                )
        elif status == "superseded":
            named = set(ID_TOKEN.findall(card.value("superseded_by")))
            if not named:
                named = {
                    token
                    for name, value in card.fields.items()
                    if name != "prereqs"
                    for token in ID_TOKEN.findall(value)
                }
            replacements = [token for token in named if token != card.id and token in plan.cards]
            if not replacements:
                findings.append(
                    error(
                        card.board,
                        card.id,
                        "superseded without naming its replacement card (§6)",
                        card.line_of("status"),
                    )
                )
    return findings


def claim_date(claimed_by: str) -> date | None:
    """The ``(YYYY-MM-DD)`` a claim carries, or None when it carries none."""
    match = CLAIM_DATE.search(claimed_by)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def working_days_after(start: date, end: date) -> int:
    """Weekdays strictly after ``start`` up to and including ``end``."""
    if end <= start:
        return 0
    count = 0
    day = start + timedelta(days=1)
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def check_stale(plan: Plan, today: date, activity: Mapping[str, date]) -> list[Finding]:
    """§6: an in-progress claim with no linked activity for five working days is stale.

    ``activity`` maps a card ID to the date of the newest commit mentioning it; the later of
    that and the claim date is when the card was last touched.
    """
    findings: list[Finding] = []
    for card in plan.cards.values():
        if card.status != "in-progress":
            continue
        line = card.line_of("claimed_by")
        claimed = claim_date(card.claimed_by)
        if claimed is None:
            findings.append(
                warning(
                    card.board,
                    card.id,
                    f"claimed_by {card.claimed_by!r} carries no (YYYY-MM-DD) date; the stale "
                    "check cannot run",
                    line,
                )
            )
            continue
        if claimed > today:
            findings.append(
                warning(card.board, card.id, f"claim date {claimed} is after today ({today})", line)
            )
            continue
        last = max(claimed, activity.get(card.id, claimed))
        idle = working_days_after(last, today)
        if idle > STALE_AFTER_WORKING_DAYS:
            findings.append(
                warning(
                    card.board,
                    card.id,
                    f"stale: in-progress with no linked activity since {last} ({idle} working "
                    f"days > {STALE_AFTER_WORKING_DAYS}; §6: release is preferred over "
                    "squatting)",
                    line,
                )
            )
    return findings


def lowest_gate(plan: Plan) -> dict[str, int]:
    """Card ID → the lowest gate number whose exit list names it."""
    lowest: dict[str, int] = {}
    for gate in plan.gates.values():
        for cid in gate.exit_cards:
            lowest[cid] = min(lowest.get(cid, gate.number), gate.number)
    return lowest


def check_gates(plan: Plan) -> list[Finding]:
    """§4 consistency: exit cards resolve, no prereq lives only in a later gate, signed = done."""
    findings: list[Finding] = []
    lowest = lowest_gate(plan)
    for gate in sorted(plan.gates.values(), key=lambda g: g.number):
        for cid in gate.exit_cards:
            if cid not in plan.cards:
                findings.append(
                    error(
                        MASTER_PLAN_NAME,
                        gate.id,
                        f"exit card {cid!r} does not resolve to any card",
                        gate.line,
                    )
                )
                continue
            for prereq in plan.cards[cid].prereq_cards:
                later = lowest.get(prereq)
                if later is not None and later > gate.number:
                    findings.append(
                        error(
                            MASTER_PLAN_NAME,
                            gate.id,
                            f"exit card {cid} requires {prereq}, an exit card only of the "
                            f"later gate G{later} — {gate.id} could never close (WA-09)",
                            gate.line,
                        )
                    )
        if gate.signed:
            undone = [
                cid
                for cid in gate.exit_cards
                if cid in plan.cards and plan.cards[cid].status != "done"
            ]
            if undone:
                findings.append(
                    error(
                        MASTER_PLAN_NAME,
                        gate.id,
                        f"signed but exit card(s) not done: {', '.join(undone)} (WA-09)",
                        gate.line,
                    )
                )
    return findings


def check_index(plan: Plan) -> list[Finding]:
    """§7 board index: every listed board exists and holds the count it states."""
    findings: list[Finding] = []
    indexed_total = 0
    indexed_decisions = 0
    for name, (prefix, count) in plan.index.items():
        if name not in plan.boards:
            findings.append(error(MASTER_PLAN_NAME, "§7", f"board {name} is listed but missing"))
            continue
        cards = plan.cards_on(name)
        indexed_total += len(cards)
        indexed_decisions += sum(1 for card in cards if card.is_decision)
        if len(cards) != count:
            findings.append(
                error(
                    MASTER_PLAN_NAME,
                    "§7",
                    f"{name}: index says {count} cards, the board holds {len(cards)}",
                )
            )
        declared = plan.board_prefixes.get(name)
        if declared is not None and declared != prefix:
            findings.append(
                error(
                    MASTER_PLAN_NAME,
                    "§7",
                    f"{name}: index says prefix {prefix}-, the board header says {declared}-",
                )
            )
    for name in plan.boards:
        if plan.index and name not in plan.index:
            findings.append(
                warning(name, "-", "board is not listed in the §7 index (excluded from totals)")
            )
    if plan.totals is not None and plan.index:
        total, decisions = plan.totals
        if indexed_total != total:
            findings.append(
                error(
                    MASTER_PLAN_NAME,
                    "§7",
                    f"totals line says {total} cards, the indexed boards hold {indexed_total}",
                )
            )
        if indexed_decisions != decisions:
            findings.append(
                warning(
                    MASTER_PLAN_NAME,
                    "§7",
                    f"totals line says {decisions} decision cards, the indexed boards hold "
                    f"{indexed_decisions}",
                )
            )
    return findings


def blocking_tokens(plan: Plan, card: Card) -> list[str]:
    """Why a card is not READY: each unmet prereq with its stored status, each open gate."""
    unmet: list[str] = []
    for token in card.prereq_cards:
        prereq = plan.cards.get(token)
        if prereq is None:
            unmet.append(f"{token} (unresolved)")
        elif prereq.status != "done":
            unmet.append(f"{token} ({prereq.status})")
    for token in card.prereq_gates:
        gate = plan.gates.get(token)
        if gate is None:
            unmet.append(f"{token} (unresolved)")
        elif not gate.signed:
            unmet.append(f"{token} (open)")
    return unmet


def check_transitions(before: Plan, after: Plan) -> list[Finding]:
    """Every status change between two board states is an arrow of the §6 diagram."""
    findings: list[Finding] = []
    for cid, old in before.cards.items():
        new = after.cards.get(cid)
        if new is None:
            findings.append(
                error(
                    old.board,
                    cid,
                    "card removed — IDs are never reused and a voided card becomes "
                    "`superseded` or `dropped` (§6)",
                )
            )
            continue
        if old.status == new.status:
            continue
        if (old.status, new.status) not in LEGAL_TRANSITIONS:
            why = (
                f"{old.status} is terminal (§6: regressions are new cards)"
                if old.status in TERMINAL_STATUSES
                else "not an arrow of the §6 transition diagram"
            )
            findings.append(
                error(
                    new.board,
                    cid,
                    f"illegal transition {old.status} -> {new.status}: {why}",
                    new.line_of("status"),
                )
            )
            continue
        if (old.status, new.status) == ("todo", "in-progress"):
            unmet = blocking_tokens(after, new)
            if unmet:
                findings.append(
                    error(
                        new.board,
                        cid,
                        "claimed while BLOCKED — unmet: "
                        + ", ".join(unmet)
                        + " (WA-01: only READY cards are claimed)",
                        new.line_of("status"),
                    )
                )
    return findings


def today_utc() -> date:
    """The calendar date the stale check counts to when none is given (CI runs in UTC)."""
    return datetime.now(timezone.utc).date()


def check_plan(
    plan: Plan,
    today: date | None = None,
    activity: Mapping[str, date] | None = None,
) -> list[Finding]:
    """Every stateless check over one board state, in the skill's order."""
    findings = list(plan.findings)
    findings += check_fields(plan)
    findings += check_ids(plan)
    findings += check_prereqs(plan)
    findings += check_cycles(plan)
    findings += check_statuses(plan)
    findings += check_done(plan)
    findings += check_holds(plan)
    findings += check_stale(plan, today or today_utc(), activity or {})
    findings += check_gates(plan)
    findings += check_index(plan)
    return findings


# ── The git boundary (CI and `--git` only; tests fake `_git`) ────────────────────────────


def _git(cwd: Path, *arguments: str) -> str:
    """Run one git plumbing command under ``cwd``; loud on failure."""
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BoardIntegrityError(
            f"git {' '.join(arguments)} failed (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def activity_from_git(cwd: Path, card_ids: Iterable[str]) -> dict[str, date]:
    """Card ID → the committer date of the newest commit whose message mentions it."""
    patterns = {cid: re.compile(rf"(?<![A-Za-z0-9-]){re.escape(cid)}(?![0-9])") for cid in card_ids}
    if not patterns:
        return {}
    newest: dict[str, date] = {}
    log = _git(cwd, "log", "--format=%cs%x1f%s%x1f%b%x1e")
    for record in log.split("\x1e"):
        parts = record.strip("\n").split("\x1f")
        if len(parts) < 2:
            continue
        try:
            day = date.fromisoformat(parts[0].strip())
        except ValueError:
            continue
        text = " ".join(parts[1:])
        for cid, pattern in patterns.items():
            if cid not in newest and pattern.search(text):
                newest[cid] = day
        if len(newest) == len(patterns):
            break
    return newest


def plan_relative_path(cwd: Path) -> str:
    """The plan root's path inside its repository, POSIX-separated."""
    toplevel = Path(_git(cwd, "rev-parse", "--show-toplevel").strip()).resolve()
    return cwd.resolve().relative_to(toplevel).as_posix()


def commits_in_range(cwd: Path, base: str, head: str) -> list[str]:
    """The commits the event delivered, oldest first.

    A null ``base`` (the push that created a ref) or a base git no longer knows leaves no
    range to walk; the head commit is then judged alone, and the narrowing is printed.
    """
    if base not in _NULL_SHAS:
        try:
            listed = _git(cwd, "rev-list", "--reverse", f"{base}..{head}")
        except BoardIntegrityError as exc:
            print(f"note: cannot walk {base[:12]}..{head[:12]} ({exc}); judging head only")
        else:
            return [line.strip() for line in listed.splitlines() if line.strip()]
    else:
        print("note: the event has no base revision; judging the head commit only")
    return [_git(cwd, "rev-list", "-n", "1", head).strip()]


def plan_at(cwd: Path, revision: str, plan_rel: str) -> Plan:
    """The plan as one commit recorded it."""
    master = _git(cwd, "show", f"{revision}:{plan_rel}/{MASTER_PLAN_NAME}")
    listing = _git(cwd, "ls-tree", "--name-only", revision, f"{plan_rel}/{BOARDS_DIR_NAME}/")
    boards = {
        Path(path).name: _git(cwd, "show", f"{revision}:{path}")
        for path in (line.strip() for line in listing.splitlines())
        if path.endswith(".md")
    }
    return load_plan_from_texts(master, boards)


def check_range(cwd: Path, base: str, head: str) -> list[Finding]:
    """§6 transitions judged commit by commit over ``base..head`` (merge commits skipped)."""
    plan_rel = plan_relative_path(cwd)
    findings: list[Finding] = []
    for sha in commits_in_range(cwd, base, head):
        parents = _git(cwd, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if len(parents) != 1:
            kind = "a merge commit" if parents else "the root commit"
            print(f"note: {sha[:12]} is {kind}; its transitions are judged on its own commits")
            continue
        changed = _git(cwd, "diff", "--name-only", parents[0], sha, "--", plan_rel)
        if not changed.strip():
            continue
        try:
            before = plan_at(cwd, parents[0], plan_rel)
        except BoardIntegrityError as exc:
            print(f"note: no plan readable at {parents[0][:12]} ({exc}); skipping {sha[:12]}")
            continue
        after = plan_at(cwd, sha, plan_rel)
        for finding in check_transitions(before, after):
            findings.append(
                Finding(
                    finding.severity,
                    finding.file,
                    finding.subject,
                    f"{finding.message} [commit {sha[:12]}]",
                    finding.line,
                )
            )
    return findings


# ── Reporting and the CLI ────────────────────────────────────────────────────────────────


def format_report(plan: Plan, findings: list[Finding], plan_root: Path | str) -> str:
    errors = sum(1 for finding in findings if finding.severity == "ERROR")
    warnings = len(findings) - errors
    lines = [f"board integrity: {plan_root}"]
    lines.extend(finding.render() for finding in findings)
    counts = f"{len(plan.cards)} cards, {len(plan.gates)} gates, {len(plan.boards)} boards"
    if errors:
        lines.append(f"board integrity: {errors} error(s), {warnings} warning(s) — {counts}")
    elif warnings:
        lines.append(f"board integrity: clean with {warnings} warning(s) — {counts}")
    else:
        lines.append(f"board integrity: clean — {counts}")
    return "\n".join(lines)


def github_annotations(findings: list[Finding], plan_root: Path) -> list[str]:
    """GitHub Actions workflow commands, one per finding, anchored to the board line."""
    lines: list[str] = []
    for finding in findings:
        if finding.file == MASTER_PLAN_NAME:
            path = plan_root / MASTER_PLAN_NAME
        else:
            path = plan_root / BOARDS_DIR_NAME / finding.file
        location = f"file={os.path.relpath(path)}"
        if finding.line is not None:
            location += f",line={finding.line}"
        level = "error" if finding.severity == "ERROR" else "warning"
        message = finding.message.replace("%", "%25").replace("\n", "%0A")
        lines.append(f"::{level} {location},title=board integrity::{finding.subject}: {message}")
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="board_integrity.py",
        description="Check the task boards against master plan §6/§7 (the /plan-status rules).",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="plan root holding 00-master-plan.md and boards/ (default: found automatically)",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="the date the stale check counts to (default: today)",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        help="read git log so the newest commit mentioning a card counts as activity",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="with --head: judge status transitions commit by commit over BASE..HEAD",
    )
    parser.add_argument("--head", default=None, help="see --base")
    parser.add_argument(
        "--base-plan",
        type=Path,
        default=None,
        help="judge status transitions against this earlier copy of the plan root",
    )
    parser.add_argument(
        "--annotations",
        action="store_true",
        help="also print GitHub Actions ::error/::warning annotations",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.base is None) != (args.head is None):
        parser.error("--base and --head go together")

    plan_root: Path | None = args.plan or default_plan_root()
    if plan_root is None:
        candidates = ", ".join(str(candidate) for candidate in default_plan_candidates())
        print(
            f"board integrity: no plan found — pass --plan; looked in {candidates}",
            file=sys.stderr,
        )
        return 2

    try:
        plan = load_plan(plan_root)
        today: date = args.today or today_utc()
        in_progress = [cid for cid, card in plan.cards.items() if card.status == "in-progress"]
        activity = activity_from_git(plan_root, in_progress) if args.git else {}
        findings = check_plan(plan, today=today, activity=activity)
        if args.base_plan is not None:
            findings += check_transitions(load_plan(args.base_plan), plan)
        if args.base is not None and args.head is not None:
            findings += check_range(plan_root, args.base, args.head)
    except (PlanError, BoardIntegrityError) as exc:
        print(f"board integrity: {exc}", file=sys.stderr)
        return 2

    errors = any(finding.severity == "ERROR" for finding in findings)
    print(format_report(plan, findings, plan_root), file=sys.stderr if errors else sys.stdout)
    if args.annotations:
        for line in github_annotations(findings, plan_root):
            print(line)
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
